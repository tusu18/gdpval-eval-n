"""Continue planned Sonnet judging with a documented new-call image bound.

No request payload or old reservation changes. Prior zero-request budget stops
are preserved; continuations have distinct paths and their own execution freeze.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_evaluation_v2 import ROOT, OUT, Client, read, write, digest, now
from grade_evaluation_v2_cross_family import CFG, BUDGET_AMENDMENT, BASE, planned_rows, freeze_execution, BoundedSecondaryClient
from dispatch_evaluation_v2_grading_amended import execute_plan
from dispatch_evaluation_v2_grading_amended import select_destination

AMENDMENT = ROOT / "config/evaluation_v2_cross_family_image_reservation_amendment.json"
SHARED_MODULE = ROOT / "scripts/evaluation_v2_verified_sonnet_budget.py"
EVIDENCE = ROOT / "docs/evaluation_v2/continuation-sonnet-image-budget-evidence.json"
GEMINI_SHIPPING = "76418a2c-a3c0-4894-b89d-2493369135d9"


def eligible_solver_continuation(original, continued, configuration, first_call):
    return (original.get("status") == "budget_limited" and original.get("unresolved_calls", 0) == 0
            and continued.get("status") == "submitted" and continued.get("continuation_kind") == "budget_continuation"
            and continued.get("stage") == "supplemental" and continued.get("recovery_stage") == "recovery"
            and sorted(continued.get("inherited_calls", [])) == sorted(original.get("calls", []))
            and configuration.get("kind") == "budget_continuation" and configuration.get("budget_blocked_first_dispatch") is True
            and configuration.get("physical_replays_of_failed_request") == 0 and configuration.get("original_turn_tool_limits_continue") is True
            and configuration.get("request_settings_changed") is False
            and configuration.get("request_sha256") == continued.get("first_continuation_request_sha256") == first_call.get("request_sha256"))


def allow_recorded_shipping_continuation(row, cfg, freeze_binding=False):
    if row.get("action") != "not_eligible_no_submitted_output" or row.get("task_id") != GEMINI_SHIPPING or row.get("solver_model") != "google/gemini-4-argon":
        return row
    parent_name = GEMINI_SHIPPING + "__google_gemini-4-argon__supplemental"
    parent_path = OUT / "runs" / parent_name / "result.json"
    if not parent_path.exists():
        return row
    original = read(parent_path)
    binding_path = BASE / "image-reservation-bindings" / (parent_name + ".json")
    if binding_path.exists():
        bound = read(binding_path)
        candidates = [Path(bound["solver_result_path"])]
        if digest(candidates[0]) != bound["solver_result_sha256"]:
            raise ValueError("Bound first-attempt continuation result changed")
    else:
        candidates = sorted((OUT / "runs").glob(GEMINI_SHIPPING + "__google_gemini-4-argon*/result.json"), key=lambda p: read(p).get("completed_at") or "9999")
    for source in candidates:
        continued = read(source)
        if continued.get("recovery_of") != parent_name or continued.get("model") != row["solver_model"] or not continued.get("calls"):
            continue
        config_path = ROOT / "config/evaluation_v2_saved_request_continuations" / (source.parent.name + ".json")
        freeze_path = OUT / "saved-request-continuations" / source.parent.name / "freeze.json"
        if not config_path.exists() or not freeze_path.exists():
            continue
        configuration = read(config_path)
        freeze = read(freeze_path)
        if freeze.get("files", {}).get(str(config_path.relative_to(ROOT))) != digest(config_path):
            raise ValueError("Solver continuation configuration is not the frozen version")
        first_label = source.parent.name + ":turn" + str(configuration["resume_turn_zero_based"] + 1)
        calls = [read(OUT / "calls" / identity / "reservation.json") for identity in continued["calls"]]
        first_calls = [r for r in calls if r.get("label") == first_label]
        if len(first_calls) != 1:
            continue
        first_call = first_calls[0]
        blocked_parent_label = parent_name + ":turn" + str(configuration["resume_turn_zero_based"] + 1)
        if any(read(p).get("label") == blocked_parent_label for p in (OUT / "calls").glob("*/reservation.json")):
            continue
        if not eligible_solver_continuation(original, continued, configuration, first_call):
            continue
        binding = {"task_id": GEMINI_SHIPPING, "solver_model": row["solver_model"], "solver_result_path": str(source), "solver_result_sha256": digest(source),
                   "solver_run_id": source.parent.name, "stage": continued["stage"], "recovery_stage": continued["recovery_stage"], "recovery_of": parent_name,
                   "solver_status": continued["status"], "judge_model": cfg["secondary_judge"],
                   "original_result_path": str(parent_path), "original_result_sha256": digest(parent_path),
                   "solver_continuation_kind": "budget_continuation_same_first_attempt", "continuation_config_sha256": digest(config_path),
                   "first_continuation_request_sha256": configuration["request_sha256"], "bound_at": now(),
                   "primary_judge_relationship": "same_family", "secondary_judge_relationship": "cross_family"}
        if freeze_binding and not binding_path.exists():
            write(binding_path, binding)
        return {**binding, **select_destination(source.parent.name, cfg["secondary_judge"])}
    return row


def continuation_row(row, root=OUT):
    row = dict(row)
    if row.get("action") != "continue_zero_request_budget_stop":
        return row
    original = Path(row["continuation_of_result"])
    destination = Path(root) / "grades_continuations" / (original.parent.name + "__sonnet_image_reservation_01")
    row.update(destination=str(destination), continuation_reason="Zero physical requests under prior generic image bound; new-call Sonnet image reservation amendment, unchanged USD30 ceiling and unchanged grading payload")
    if (destination / "result.json").exists():
        row.update(action="preserve_existing", prior_status=read(destination / "result.json").get("status"), effective_result=str(destination / "result.json"))
    elif (destination / "in_progress.json").exists():
        row.update(action="checkpoint_review_required", reason="Interrupted image-bound continuation; no automatic duplicate request")
    return row


def unknown_snapshot(root=OUT):
    return {str(p): {"sha256": digest(p), "reserved_usd": r["reserved_usd"]} for p in (Path(root) / "calls").glob("*/reservation.json")
            if (r := read(p)).get("status") == "failed_unknown_charge" and r.get("actual_cost_usd") is None}


def verify_unknown_unchanged(snapshot):
    return all(Path(path).exists() and digest(path) == value["sha256"] for path, value in snapshot.items())


def freeze_amendment():
    freeze_execution()  # verifies the already executed semantic protocol unchanged
    paths = [Path(__file__), AMENDMENT, SHARED_MODULE, EVIDENCE, CFG, BUDGET_AMENDMENT,
             ROOT / "scripts/grade_evaluation_v2_cross_family.py", ROOT / "scripts/dispatch_evaluation_v2_grading_amended.py",
             ROOT / "scripts/grade_evaluation_v2.py", ROOT / "scripts/evaluation_v2_grading.py",
             ROOT / "scripts/run_evaluation_v2.py", ROOT / "scripts/extend_evaluation_v2_models.py",
             ROOT / "data/evaluation_v2/model-catalog.json", ROOT / "config/evaluation_v2_run.json",
             ROOT / "config/evaluation_v2_budget_amendment.json"]
    record = {"schema": "evaluation-v2-cross-family-image-reservation-freeze-v1", "created_at": now(),
              "files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
              "original_execution_freeze_sha256": digest(BASE / "execution-freeze.json"),
              "unknown_reservations_before": unknown_snapshot(), "api_calls_at_freeze": 0,
              "authorized_total_usd": 30, "request_payload_changed": False}
    path = BASE / "image-reservation-amendment-freeze.json"
    if path.exists():
        prior = read(path)
        if prior["files"] != record["files"]:
            raise ValueError("Image reservation amendment inputs changed since execution freeze")
        if not verify_unknown_unchanged(prior["unknown_reservations_before"]):
            raise ValueError("An old unknown-charge reservation changed; independent accounting review required")
        return prior
    write(path, record)
    return record


def make_client(key_file, cfg):
    from evaluation_v2_verified_sonnet_budget import SonnetImageReservationMixin
    class NewCallSonnetClient(SonnetImageReservationMixin, Client):
        pass
    client = NewCallSonnetClient(key_file)
    budget = read(ROOT / "config/evaluation_v2_budget_amendment.json")
    if budget["authorized_total_usd"] != 30:
        raise ValueError("This amendment is frozen to the existing USD30 ceiling")
    client.cfg["authorized_available_budget_usd"] = 30
    client.cfg["solver_ceiling_usd"] = budget["solver_ceiling_usd"]
    return BoundedSecondaryClient(client, cfg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--key-file")
    parser.add_argument("--task", action="append", help="Optional task prefixes, repeated to prioritize NPV/GMP; other planned cells remain visible")
    args = parser.parse_args()
    cfg = read(CFG)
    cfg["budget"]["per_phase_maximum_additional_commitment_usd"] = read(BUDGET_AMENDMENT)["per_phase_maximum_additional_commitment_usd"]
    all_rows = [continuation_row(allow_recorded_shipping_continuation(r, cfg, freeze_binding=args.execute)) for r in planned_rows(cfg, freeze_bindings=args.execute)]
    selected = [r for r in all_rows if not args.task or any(r["task_id"].startswith(t) for t in args.task)]
    plan = {"created_at": now(), "rows": all_rows, "selected_task_prefixes": args.task, "authorized_total_usd": 30,
            "amendment_sha256": digest(AMENDMENT), "human_acceptance": None}
    write(BASE / "image-reservation-amendment-plan.json", plan)
    if not args.execute:
        print(json.dumps([{k: r.get(k) for k in ("task_id", "solver_model", "stage", "action", "destination")} for r in selected], indent=2))
        return
    if not args.key_file:
        parser.error("--execute requires --key-file")
    frozen = freeze_amendment()
    client = make_client(args.key_file, cfg)
    execute_plan(client, [r for r in selected if r["action"] != "not_eligible_no_submitted_output"], cfg["secondary_judge"])
    preserved = verify_unknown_unchanged(frozen["unknown_reservations_before"])
    write(BASE / "image-reservation-amendment-postcheck.json", {"checked_at": now(), "old_unknown_reservations_unchanged": preserved,
                                                             "unknowns_checked": len(frozen["unknown_reservations_before"]), "authorized_total_usd": 30})
    if not preserved:
        raise ValueError("Old unknown reservations changed during execution; inspect accounting before any further calls")


if __name__ == "__main__":
    main()
