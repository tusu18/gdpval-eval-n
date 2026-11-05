"""Explicit serial continuation after the provider's 120-second cooldown."""
from pathlib import Path
import argparse
import json
import shutil

from evaluation_v5_rejection_budget import make_client
from run_evaluation_v5_crossjudge import DEFAULT_MODELS, INVENTORY, OUT, grade
from run_evaluation_v2 import ROOT, digest, now, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    inventory = read(INVENTORY)
    rejection = read(ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json")
    # Candidate selection is terminal infrastructure status, never a verdict.
    items = {r["task_id"]: r for r in inventory["tasks"]}
    candidates = []
    for item in inventory["tasks"]:
        for model in DEFAULT_MODELS:
            ident = item["task_id"] + "__" + model.replace("/", "_")
            folder = OUT / "judges" / ident
            result = read(folder / "result.json")
            if result["status"] == "transport_or_runner_error":
                candidates.append({"ident": ident, "task_id": item["task_id"], "model": model,
                                   "result_sha256": digest(folder / "result.json"),
                                   "checkpoint_sha256": digest(folder / "checkpoint.json")})
    pilot = "a4a9195c-5ebe-4b8d-a0c2-4a6b7a49da8b__google_gemini-4-argon"
    candidates.sort(key=lambda r: r["ident"] != pilot)
    manifest = OUT / "serial-recovery-plan.json"
    if manifest.exists():
        plan = read(manifest)
    else:
        plan = {"created_at": now(), "script_sha256": digest(__file__), "cells": candidates,
                "reason": "Provider rejected requests before inference due to simultaneous-request credit limit. Cooldown exceeded120seconds; continue serially and stop at the first renewed provider credit rejection or USD30 budget stop.",
                "first_cell_rationale": "Lowest prior first-request reservation among rejected cells, selected without using verdicts.",
                "budget_amendment_sha256": digest(ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json"),
                "max_explicit_recoveries_per_selected_cell": 1, "new_independent_judgments": False,
                "transport_exception_reserves_retained": True}
        write(manifest, plan)
    if plan["script_sha256"] != digest(__file__):
        raise ValueError("Serial continuation script changed after selection")
    client = make_client(args.key_file)
    completed = 0
    for entry in plan["cells"]:
        folder = OUT / "judges" / entry["ident"]
        receipt = OUT / "serial-recovery" / entry["ident"] / "recovery.json"
        if receipt.exists():
            continue
        if digest(folder / "result.json") != entry["result_sha256"] or digest(folder / "checkpoint.json") != entry["checkpoint_sha256"]:
            raise ValueError("Selected interrupted record changed")
        result, checkpoint = read(folder / "result.json"), read(folder / "checkpoint.json")
        if checkpoint["state"] != "before_request":
            raise ValueError("Recovery must start from the recorded interrupted turn")
        backup = receipt.parent / "before"
        shutil.copytree(folder, backup)
        write(receipt, {"created_at": now(), "selection_sha256": digest(manifest),
                        "before_hashes": {str(p.relative_to(backup)): digest(p) for p in backup.rglob("*") if p.is_file()},
                        "reason": plan["reason"], "old_call_ids": result["calls"],
                        "original_requests_preserved": True, "new_attempt_limit": 1})
        checkpoint["state"] = "ready_next_turn"
        checkpoint["explicit_serial_recovery"] = str(receipt)
        result["historical_infrastructure_error"] = result.pop("error", None)
        result["status"] = "running"
        result["serial_recovery_receipt"] = str(receipt)
        write(folder / "checkpoint.json", checkpoint)
        write(folder / "result.json", result)
        finished = grade(client, items[entry["task_id"]], entry["model"], 8, 6000, True)
        completed += 1
        summary = {k: finished.get(k) for k in ("task_id", "judge_requested_model", "status", "overall", "known_cost_usd", "error")}
        summary["budget"] = client.totals()
        write(receipt.parent / "completion.json", summary)
        print(json.dumps(summary), flush=True)
        credit_rejected = False
        if finished.get("status") == "transport_or_runner_error":
            for call_id in finished.get("calls", []):
                if call_id in result["calls"]:
                    continue
                response = read(ROOT / "output/evaluation_v2/calls" / call_id / "response.json")
                if response.get("status") == 402:
                    credit_rejected = True
        if credit_rejected or finished.get("status") in ("budget_blocked", "checkpoint_review_required"):
            print(json.dumps({"stopped": "provider_credit_limit" if credit_rejected else finished["status"],
                              "recovered_cells_this_invocation": completed}), flush=True)
            break
        if args.limit and completed >= args.limit:
            break


if __name__ == "__main__":
    main()
