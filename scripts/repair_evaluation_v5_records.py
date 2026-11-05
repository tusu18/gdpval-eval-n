"""Optional one-call, post-hoc completion of schema-invalid v5 records.

No inference without --execute. All80 first-pass physical attempts take priority.
Historical outputs, rubrics and grading records are never overwritten.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path

from run_evaluation_v5_crossjudge import DEFAULT_MODELS, INVENTORY, OUT, CATALOG, make_client as original_make_client, request_body, validate
from run_evaluation_v2 import BudgetStop, ROOT, OUT as LEDGER, canonical, digest, now, read, write

CONFIG = ROOT / "config/evaluation_v5_record_completion_amendment.json"
PROTOCOL = ROOT / "docs/evaluation_v5/record-completion-protocol.txt"
SELECTION = OUT / "record-repair-selection.json"
SCOPE = "judge_v5_record_completion"


def make_completion_client(key_file=None):
    transport = ROOT / "scripts/evaluation_v5_rejection_budget.py"
    if transport.is_file():
        from evaluation_v5_rejection_budget import make_client
        return make_client(key_file)
    if key_file:
        raise ValueError("Versioned provider-rejection budget client must be ready before record-completion execution")
    return original_make_client()


def repair_instruction(errors):
    return """This is an explicitly post-hoc record-completion pass on YOUR prior assessment, not an independent judgment. Original records and outcomes remain preserved. Do not infer any other judge or human opinion.
The structural validator found these exact errors:
""" + json.dumps(errors, ensure_ascii=False) + """
Return a complete replacement-format JSON assessment with every original criterion exactly once, using the original required fields and frozen criteria. In EVERY criterion whose verdict is pass or fail, source_evidence MUST be a nonempty array containing at least one exact contiguous quotation from original_prompt or a supplied source; keep a real locator outside the quote. An output quotation alone is not source evidence. Preserve supported findings. Do not fabricate a source quotation, copy a rubric paraphrase as if it were original text, or turn missing evidence into a pass.
Inspect only the evidence already supplied in this history; you have no new tools, images or sources in this pass. Where the existing evidence/inspection does not support a conclusion, use uncertain and explain what remains unavailable. In particular a visual requirement cannot pass on an unseen rendering merely because its text sounds plausible. This may change a substantive verdict; every change will be reported separately. Apply unchanged criterion semantics; record an objection to rubric scope separately.
Return ONLY the full JSON object, no markdown fences, with task_id, rubric_sha256, criteria, overall and human_acceptance:null. Overall is fail if any criterion fails, otherwise uncertain if any criterion is uncertain/not_assessed, otherwise pass. All original per-criterion fields remain required. Cite a few decisive segments rather than whole documents. Do not mention an actual payment, release, expert approval or completed action unless present in the source evidence.
"""


def selection_plan():
    inventory = read(INVENTORY)
    selected, incomplete, excluded = [], [], []
    for item in inventory["tasks"]:
        for model in DEFAULT_MODELS:
            ident = item["task_id"] + "__" + model.replace("/", "_")
            folder = OUT / "judges" / ident
            result_path = folder / "result.json"
            if not result_path.exists():
                incomplete.append({"task_id": item["task_id"], "model": model, "status": "not_recorded"})
                continue
            result = read(result_path)
            if result.get("status") in ("running", "budget_blocked", "checkpoint_review_required") or not result.get("calls"):
                incomplete.append({"task_id": item["task_id"], "model": model, "status": result.get("status"), "reason": "No completed terminal physical first-pass attempt"})
                continue
            if result.get("status") != "invalid_judgment":
                excluded.append({"task_id": item["task_id"], "model": model, "status": result.get("status"), "reason": "Not a schema-invalid assessment"})
                continue
            assessment, validation = folder / "assessment.json", folder / "validation.json"
            if not assessment.exists() or not validation.exists():
                excluded.append({"task_id": item["task_id"], "model": model, "status": result.get("status"), "reason": "No parsed schema-invalid assessment; malformed or truncated responses excluded from this amendment"})
                continue
            checked = read(validation)
            if checked.get("contract_valid") is not False:
                excluded.append({"task_id": item["task_id"], "model": model, "reason": "Structural validation is not failed"})
                continue
            paths = {"original_result": result_path, "original_assessment": assessment, "original_validation": validation,
                     "original_history": folder / "history.json", "original_exposure": folder / "evidence-exposure.json", "packet": Path(item["packet_path"])}
            if not all(p.is_file() for p in paths.values()):
                raise ValueError("Eligible record lacks original history or exposure evidence: " + ident)
            selected.append({"task_id": item["task_id"], "judge_requested_model": model, "ident": ident,
                             "files": {key: {"path": str(path), "sha256": digest(path)} for key, path in paths.items()},
                             "contract_errors": checked.get("contract_errors", []), "packet_sha256": item["packet_sha256"]})
    return {"schema": "evaluation-v5-record-repair-selection-1", "created_at": now(), "expected_first_pass_cells": 80,
            "all_first_pass_attempts_complete": not incomplete and len(inventory["tasks"]) == 40,
            "incomplete_first_pass_cells": incomplete, "selected_count": len(selected), "selected": selected,
            "excluded": excluded, "selection_policy": "All parsed schema-invalid assessments, irrespective of substantive verdict; first-pass outcomes remain primary."}


def verify_originals(entry):
    for label, record in entry["files"].items():
        path = Path(record["path"]).resolve()
        if not path.is_relative_to(OUT.resolve()) or not path.is_file() or digest(path) != record["sha256"]:
            raise ValueError("Frozen original record changed or missing: " + label)


def freeze_selection(plan):
    if not plan["all_first_pass_attempts_complete"]:
        raise ValueError("First-pass80-cell coverage is incomplete; completion calls remain lower priority")
    paths = [Path(__file__), CONFIG, PROTOCOL, CATALOG, INVENTORY, ROOT / "scripts/run_evaluation_v5_crossjudge.py",
             ROOT / "scripts/evaluation_v5_transport_client.py", ROOT / "scripts/evaluation_v5_transport.py",
             ROOT / "scripts/evaluation_v5_budget.py", ROOT / "config/evaluation_v5_budget_reconciliation.json",
             ROOT / "scripts/evaluation_v5_rejection_budget.py", ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json"]
    if not all(p.is_file() for p in paths):
        raise ValueError("Required versioned implementation is not yet ready for freezing")
    record = {**plan, "frozen_at": now(), "implementation_hashes": {str(p.relative_to(ROOT)): digest(p) for p in paths},
              "max_additional_physical_calls_per_cell": 1, "cumulative_api_ceiling_usd": 30}
    if SELECTION.exists():
        old = read(SELECTION)
        if old["selected"] != record["selected"] or old["implementation_hashes"] != record["implementation_hashes"]:
            raise ValueError("Frozen repair selection or implementation changed; preserve this version")
        return old
    write(SELECTION, record)
    return record


def history_for(entry):
    verify_originals(entry)
    history = copy.deepcopy(read(entry["files"]["original_history"]["path"]))
    history.append({"role": "user", "content": repair_instruction(entry["contract_errors"])})
    return history


def changes(before, after):
    old = {r.get("criterion_id"): r for r in before.get("criteria", []) if isinstance(r, dict)} if isinstance(before, dict) else {}
    new = {r.get("criterion_id"): r for r in after.get("criteria", []) if isinstance(r, dict)} if isinstance(after, dict) else {}
    output = []
    for cid in sorted(set(old) | set(new), key=str):
        fields = {}
        for field in ("verdict", "severity", "failure_class", "stated_check", "honored_check", "coverage", "rubric_scope_objection"):
            a, b = old.get(cid, {}).get(field), new.get(cid, {}).get(field)
            if a != b:
                fields[field] = {"before": a, "after": b}
        if fields:
            output.append({"criterion_id": cid, "fields": fields})
    return {"criterion_changes": output, "verdict_flip_count": sum("verdict" in c["fields"] for c in output),
            "original_overall": before.get("overall") if isinstance(before, dict) else None, "new_overall": after.get("overall") if isinstance(after, dict) else None,
            "original_record_unchanged": True, "interpretation": "Post-hoc completion can revise substantive judgments; these changes are secondary, not independent replication."}


def cell_calls(label):
    records = [read(p) for p in (LEDGER / "calls").glob("*/reservation.json") if read(p).get("label") == label]
    return sorted(records, key=lambda r: r["created_at"])


def _complete_unlocked(client, entry, selection_hash, resume_zero_request=False):
    verify_originals(entry)
    folder = OUT / "record-repairs" / entry["ident"]
    result_path = folder / "result.json"
    label = "v5-record-completion:" + entry["ident"]
    previous = read(result_path) if result_path.exists() else None
    existing_calls = cell_calls(label)
    if previous:
        if not (resume_zero_request and previous.get("status") == "budget_blocked" and not existing_calls):
            return previous
        write(folder / "prior-budget-stops" / (now().replace(":", "-") + ".json"), previous)
    if existing_calls:
        return {"task_id": entry["task_id"], "judge_requested_model": entry["judge_requested_model"], "status": "checkpoint_review_required",
                "reason": "A physical completion call already exists; maximum one, no automatic retry", "calls": [r["id"] for r in existing_calls]}
    folder.mkdir(parents=True, exist_ok=True)
    packet = read(entry["files"]["packet"]["path"])
    before = read(entry["files"]["original_assessment"]["path"])
    exposure = read(entry["files"]["original_exposure"]["path"])
    history = history_for(entry)
    body = request_body(entry["judge_requested_model"], history, 6000, final_turn=True)
    result = {"schema": "evaluation-v5-record-completion-result-1", "task_id": entry["task_id"], "judge_requested_model": entry["judge_requested_model"],
              "status": "running", "source": "post_hoc_record_completion", "not_independent_judgment": True,
              "original_result_path": entry["files"]["original_result"]["path"], "original_result_sha256": entry["files"]["original_result"]["sha256"],
              "original_assessment_path": entry["files"]["original_assessment"]["path"], "original_assessment_sha256": entry["files"]["original_assessment"]["sha256"],
              "packet_sha256": entry["packet_sha256"], "rubric_sha256": packet["rubric_sha256"], "selection_sha256": selection_hash,
              "started_at": now(), "human_acceptance": None, "calls": [], "contract_valid": False, "overall": None}
    write(folder / "request-history.json", history)
    write(folder / "dispatch-checkpoint.json", {"state": "before_single_request", "label": label, "request_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
                                                "selection_sha256": selection_hash, "original_contract_errors": entry["contract_errors"]})
    try:
        response, meta = client.call(body, scope=SCOPE, label=label)
        write(folder / "response.json", response)
        choice = (response.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        write(folder / "final-response.json", {"content": content, "finish_reason": choice.get("finish_reason"), "call_id": meta["call_id"]})
        if choice.get("finish_reason") in ("length", "max_tokens"):
            result.update(status="invalid_judgment", error="Completion response reached output token limit; retained without retry")
        else:
            try:
                after = json.loads(content)
            except (ValueError, TypeError) as error:
                result.update(status="invalid_judgment", error="Completion response is not strict JSON: " + str(error)[:250])
            else:
                write(folder / "assessment.json", after)
                checked = validate(packet, after, exposure)
                write(folder / "validation.json", checked)
                delta = changes(before, after)
                write(folder / "changes.json", delta)
                result.update(status="graded" if checked["contract_valid"] else "invalid_judgment", contract_valid=checked["contract_valid"],
                              overall=checked["computed_overall"] if checked["contract_valid"] else None,
                              assessment_path=str(folder / "assessment.json"), validation_path=str(folder / "validation.json"),
                              changes_path=str(folder / "changes.json"), verdict_flip_count=delta["verdict_flip_count"])
    except BudgetStop as error:
        result.update(status="budget_blocked", error=str(error))
    except Exception as error:
        result.update(status="transport_or_runner_error", error=str(error)[:1000])
    verify_originals(entry)
    records = cell_calls(label)
    if len(records) > 1:
        raise RuntimeError("One-call completion limit breached")
    result.update(calls=[r["id"] for r in records], known_cost_usd=sum(r.get("actual_cost_usd") or 0 for r in records),
                  unresolved_reserved_usd=sum(r["reserved_usd"] for r in records if r.get("actual_cost_usd") is None),
                  served_providers=sorted({r["served_provider"] for r in records if r.get("served_provider")}),
                  completed_at=now(), original_records_unchanged=True, result_path=str(result_path))
    write(folder / "call-records.json", records)
    write(result_path, result)
    return result


def complete(client, entry, selection_hash, resume_zero_request=False):
    if not SELECTION.is_file() or digest(SELECTION) != selection_hash:
        raise ValueError("Completion requires the frozen selection and exact selection hash")
    frozen = read(SELECTION)
    if not frozen.get("all_first_pass_attempts_complete") or entry not in frozen.get("selected", []):
        raise ValueError("Cell is not in the frozen eligible selection")
    folder = OUT / "record-repairs" / entry["ident"]
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "completion.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return _complete_unlocked(client, entry, selection_hash, resume_zero_request)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--freeze-selection", action="store_true")
    parser.add_argument("--key-file")
    parser.add_argument("--task")
    parser.add_argument("--model", choices=DEFAULT_MODELS)
    parser.add_argument("--resume-zero-request-budget-stop", action="store_true")
    args = parser.parse_args()
    if args.execute and not args.key_file:
        raise ValueError("Protected key file required for explicit execution")
    plan = selection_plan()
    client = make_completion_client(args.key_file if args.execute else None)
    costs = []
    for entry in plan["selected"]:
        body = request_body(entry["judge_requested_model"], history_for(entry), 6000, final_turn=True)
        costs.append({"task_id": entry["task_id"], "model": entry["judge_requested_model"], "reserved_usd": client.reservation(body)})
    plan["budget_snapshot"] = client.totals()
    plan["cost_reservations"] = costs
    plan["sum_conservative_request_reservations_usd"] = sum(r["reserved_usd"] for r in costs)
    write(OUT / "record-repair-plan.json", plan)
    print(json.dumps({"all_first_pass_attempts_complete": plan["all_first_pass_attempts_complete"], "incomplete_first_pass_cells": len(plan["incomplete_first_pass_cells"]),
                      "eligible_records": plan["selected_count"], "sum_request_reservations_usd": plan["sum_conservative_request_reservations_usd"], "budget": plan["budget_snapshot"]}), flush=True)
    if not args.execute and not args.freeze_selection:
        return
    frozen = freeze_selection(plan)
    if not args.execute:
        return
    selection_hash = digest(SELECTION)
    for entry in frozen["selected"]:
        if args.task and not entry["task_id"].startswith(args.task) or args.model and entry["judge_requested_model"] != args.model:
            continue
        result = complete(client, entry, selection_hash, args.resume_zero_request_budget_stop)
        print(json.dumps({"task_id": entry["task_id"], "judge": entry["judge_requested_model"], "status": result["status"],
                          "verdict_flip_count": result.get("verdict_flip_count"), "known_cost_usd": result.get("known_cost_usd"), "budget": client.totals()}), flush=True)
        if result["status"] in ("budget_blocked", "transport_or_runner_error", "checkpoint_review_required"):
            break


if __name__ == "__main__":
    main()
