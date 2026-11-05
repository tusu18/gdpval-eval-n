"""Finish ungraded outputs under the explicit budget-only amendment.

Old grades, including a pre-dispatch budget stop, are immutable. No invalid
judgment is retried. A zero-request budget stop gets a separate continuation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_evaluation_v2 import ROOT, OUT, read, write, digest, now
from dispatch_evaluation_v2_remaining import amended_client
from grade_evaluation_v2 import prepare_run, grade_packet


def grade_directory(run_id, model, root=OUT):
    return Path(root) / "grades" / (run_id + "__" + model.replace("/", "_"))


def select_destination(run_id, model, root=OUT):
    root = Path(root)
    original = grade_directory(run_id, model, root)
    result_file = original / "result.json"
    if not result_file.exists():
        if (original / "in_progress.json").exists():
            return {"action": "checkpoint_review_required", "destination": str(original), "reason": "An interrupted grading call may already have been dispatched"}
        return {"action": "grade_unattempted", "destination": str(original)}
    previous = read(result_file)
    if previous.get("status") != "budget_limited":
        return {"action": "preserve_existing", "destination": str(original), "prior_status": previous.get("status"), "effective_result": str(result_file)}
    prefix = "grade:" + original.name + ":"
    ledger_matches = [p for p in (root / "calls").glob("*/reservation.json") if read(p).get("label", "").startswith(prefix)]
    if previous.get("calls") or previous.get("batches") or ledger_matches or previous.get("unresolved_calls", 0):
        return {"action": "checkpoint_review_required", "destination": str(original), "reason": "Budget-limited record includes physical requests; no automatic semantic retry"}
    continuation = root / "grades_continuations" / (original.name + "__budget_amendment_01")
    context = {"continuation_of_result": str(result_file), "prior_result_sha256": digest(result_file),
               "continuation_reason": "Original guard stopped before any physical request; user then restored authorized total budget to USD30"}
    if (continuation / "result.json").exists():
        return {"action": "preserve_existing", "destination": str(continuation), "prior_status": read(continuation / "result.json").get("status"), "effective_result": str(continuation / "result.json"), **context}
    if (continuation / "in_progress.json").exists():
        return {"action": "checkpoint_review_required", "destination": str(continuation), "reason": "Interrupted continuation; no automatic duplicate request", **context}
    return {"action": "continue_zero_request_budget_stop", "destination": str(continuation), **context}


def freeze_amendment():
    files = [Path(__file__), ROOT / "scripts/grade_evaluation_v2.py", ROOT / "scripts/evaluation_v2_grading.py",
             ROOT / "scripts/dispatch_evaluation_v2_remaining.py", ROOT / "config/evaluation_v2_budget_amendment.json",
             ROOT / "data/evaluation_v2/effective-inputs.jsonl", ROOT / "data/evaluation_v2/rubrics.json"]
    record = {"created_at": now(), "files": {str(p.relative_to(ROOT)): digest(p) for p in files},
              "change": "Budget client only: shared amended USD30 ceiling; frozen primary judge prompt, rubric, evidence preparation and generation settings unchanged",
              "retry_policy": "Existing graded, invalid or failed judging records preserved. Only zero-request budget guard stops receive separately stored continuations."}
    path = OUT / "grading-amendment-freeze.json"
    if path.exists():
        prior = read(path)
        if prior["files"] != record["files"]:
            raise ValueError("Amended grading inputs changed; preserve prior execution and use a separately recorded amendment")
        return prior
    write(path, record)
    return record


def plan(model, stage="all", task_prefix=None, solver_model=None, root=OUT):
    rows = []
    for path in sorted((Path(root) / "runs").glob("*/result.json")):
        run = read(path)
        if run.get("stage") not in ("primary", "supplemental"):
            continue
        if stage != "all" and run.get("stage") != stage:
            continue
        if task_prefix and not run["task_id"].startswith(task_prefix):
            continue
        if solver_model and run.get("model") != solver_model:
            continue
        row = {"task_id": run["task_id"], "solver_run_id": path.parent.name, "solver_model": run.get("model"),
               "solver_result_path": str(path), "stage": run.get("stage"), "solver_status": run.get("status"),
               "recovery_stage": run.get("recovery_stage"), "recovery_of": run.get("recovery_of"), "judge_model": model,
               **select_destination(path.parent.name, model, root)}
        if row["action"] == "grade_unattempted" and run.get("status") != "submitted":
            row["action"] = "record_no_submission"
        rows.append(row)
    return sorted(rows, key=lambda r: (r["stage"] != "primary", r["task_id"], r["solver_run_id"]))


def resolution_index(rows, root=OUT):
    root = Path(root)
    # A filtered invocation must not erase previously resolved cohort rows.
    prior_file = root / "grade-resolution-index.json"
    prior_entries = read(prior_file).get("entries", []) if prior_file.exists() else []
    entries_by_key = {(e["solver_run_id"], e["judge_model"]): e for e in prior_entries}
    for row in rows:
        destination = Path(row["destination"])
        effective = destination / "result.json"
        original = grade_directory(row["solver_run_id"], row["judge_model"], root) / "result.json"
        result = read(effective) if effective.exists() else None
        entries_by_key[(row["solver_run_id"], row["judge_model"])] = {"task_id": row["task_id"], "solver_run_id": row["solver_run_id"], "solver_model": row["solver_model"],
                        "stage": row["stage"], "recovery_stage": row.get("recovery_stage"), "judge_model": row["judge_model"],
                        "original_result_path": str(original) if original.exists() else None,
                        "original_result_sha256": digest(original) if original.exists() else None,
                        "effective_result_path": str(effective) if effective.exists() else None,
                        "effective_result_sha256": digest(effective) if effective.exists() else None,
                        "effective_status": result.get("status") if result else row["action"],
                        "continuation": destination.parent.name == "grades_continuations",
                        "human_acceptance": None}
    entries = sorted(entries_by_key.values(), key=lambda e: (e["stage"] != "primary", e["task_id"], e["solver_run_id"], e["judge_model"]))
    return {"schema": "evaluation-v2-grade-resolution-index-v1", "created_at": now(), "entries": entries,
            "policy": "Effective continuation does not overwrite the original budget-stop record. Primary and recovery cohorts remain separate."}


def execute_plan(client, rows, model):
    tasks = {t["task_id"]: t for t in map(json.loads, (ROOT / "data/evaluation_v2/effective-inputs.jsonl").read_text().splitlines())}
    rubrics = read(ROOT / "data/evaluation_v2/rubrics.json")
    outputs = []
    # All zero-cost no-submission records are written even if a later API call
    # encounters a budget or transport block.
    for row in rows:
        if row["action"] != "record_no_submission":
            continue
        result = {"task_id": row["task_id"], "solver_run_id": row["solver_run_id"], "solver_model": row["solver_model"], "model": model,
                  "stage": row["stage"], "recovery_stage": row.get("recovery_stage"), "recovery_of": row.get("recovery_of"),
                  "status": "no_submission", "solver_status": row["solver_status"], "calls": [], "known_cost_usd": 0,
                  "human_acceptance": None, "summary": {"human_accepted": None, "project_rubric_pass": None, "consequential_error_candidate": None},
                  "recorded_at": now(), "budget_amendment_sha256": digest(ROOT / "config/evaluation_v2_budget_amendment.json")}
        write(Path(row["destination"]) / "result.json", result); outputs.append(result)
    for row in rows:
        if row["action"] not in ("grade_unattempted", "continue_zero_request_budget_stop"):
            continue
        dest = Path(row["destination"])
        identity = {"task_id": row["task_id"], "solver_run_id": row["solver_run_id"], "solver_model": row["solver_model"], "stage": row["stage"],
                    "recovery_stage": row.get("recovery_stage"), "recovery_of": row.get("recovery_of"),
                    "budget_amendment_sha256": digest(ROOT / "config/evaluation_v2_budget_amendment.json")}
        for field in ("continuation_of_result", "prior_result_sha256", "continuation_reason"):
            if field in row:
                identity[field] = row[field]
        write(dest / "dispatch-context.json", {**identity, "action": row["action"], "created_at": now()})
        try:
            packet, private, images, run = prepare_run(Path(row["solver_result_path"]).parent, tasks[row["task_id"]], rubrics)
            if packet is None:
                raise ValueError("Submitted run has no usable submission manifest")
            write(dest / "identity.private.json", private)
            scope = "judge_primary_amended" if model == client.cfg["primary_judge"] else "judge_secondary_amended"
            result = grade_packet(client, packet, images, dest, model, identity=identity, scope=scope, execute=True)
        except Exception as error:
            # The core grading helper records transport/API failures itself.
            # This catches source preparation/checkpoint failures without a
            # second request or a fabricated business judgment.
            if (dest / "result.json").exists():
                result = read(dest / "result.json")
            else:
                result = {**identity, "model": model, "status": "preparation_or_checkpoint_failure", "error": str(error)[:1400],
                          "calls": [], "known_cost_usd": None, "human_acceptance": None,
                          "summary": {"human_accepted": None, "project_rubric_pass": None, "consequential_error_candidate": None}}
                write(dest / "result.json", result)
        outputs.append(result)
        print(json.dumps({"task": row["task_id"][:8], "stage": row["stage"], "judge": model, "status": result["status"], "cost": result.get("known_cost_usd"), "continuation": "continuation_of_result" in identity}), flush=True)
        write(OUT / "grade-resolution-index.json", resolution_index(rows))
        if result["status"] in ("budget_limited", "infrastructure_failure"):
            break
    write(OUT / "grade-resolution-index.json", resolution_index(rows))
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--task")
    parser.add_argument("--model")
    parser.add_argument("--solver-model")
    parser.add_argument("--stage", choices=["all", "primary", "supplemental"], default="all")
    args = parser.parse_args()
    model = args.model or read(ROOT / "config/evaluation_v2_run.json")["primary_judge"]
    rows = plan(model, args.stage, args.task, args.solver_model)
    if not args.execute:
        print(json.dumps([{k: r.get(k) for k in ("task_id", "stage", "solver_status", "action", "prior_status", "destination")} for r in rows], indent=2)); return
    if not args.key_file:
        parser.error("--execute requires --key-file")
    freeze_amendment()
    client = amended_client(args.key_file)
    dispatch = {"created_at": now(), "model": model, "rows": rows, "authorized_total_usd": client.cfg["authorized_available_budget_usd"],
                "script_sha256": digest(__file__), "zero_request_continuations_only": True}
    write(OUT / "dispatches" / ("grading-amended-" + dispatch["created_at"].replace(":", "-") + ".json"), dispatch)
    execute_plan(client, rows, model)


if __name__ == "__main__":
    main()
