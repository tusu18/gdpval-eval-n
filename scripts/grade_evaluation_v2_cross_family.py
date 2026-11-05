"""Optional bounded cross-family judging of frozen matched solver outputs.

Offline planning is the default. No solver is rerun, no prior judgment retried,
and each exact artifact selection is recorded before any secondary request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_evaluation_v2 import ROOT, OUT, read, write, digest, now, BudgetStop
from dispatch_evaluation_v2_remaining import amended_client
from dispatch_evaluation_v2_grading_amended import select_destination, execute_plan

CFG = ROOT / "config/evaluation_v2_cross_family_judging.json"
BUDGET_AMENDMENT = ROOT / "config/evaluation_v2_cross_family_budget_amendment.json"
BASE = OUT / "cross_family_judging"


def freeze_plan():
    record = {"schema": "evaluation-v2-cross-family-plan-freeze-v1", "created_at": now(), "config_sha256": digest(CFG),
              "timing": read(CFG)["selection_timing"], "api_requests": 0}
    path = BASE / "plan-freeze.json"
    if path.exists():
        prior = read(path)
        if prior["config_sha256"] != record["config_sha256"]:
            raise ValueError("Secondary judge plan changed after freezing")
        return prior
    write(path, record)
    return record


def candidate(task_id, model, root=OUT):
    root = Path(root)
    prefix = task_id + "__" + model.replace("/", "_")
    if model.startswith("google/"):
        path = root / "runs" / (prefix + "__supplemental") / "result.json"
        return path if path.exists() and read(path).get("status") == "submitted" else None
    original = root / "runs" / (prefix + "__primary") / "result.json"
    if original.exists() and read(original).get("status") == "submitted":
        return original
    eligible = []
    for path in (root / "runs").glob(prefix + "*/result.json"):
        row = read(path)
        if row.get("model") != model or row.get("task_id") != task_id or row.get("status") != "submitted":
            continue
        if row.get("recovery_stage") == "recovery" or row.get("stage") == "adapter_repair":
            eligible.append(path)
    return min(eligible, key=lambda p: (read(p).get("completed_at") or "9999", p.parent.name)) if eligible else None


def planned_rows(cfg, freeze_bindings=False):
    rows = []
    for task_id in cfg["task_ids"]:
        for solver in cfg["solver_models"]:
            binding_path = BASE / "bindings" / (task_id + "__" + solver.replace("/", "_") + ".json")
            if binding_path.exists():
                binding = read(binding_path)
                source = Path(binding["solver_result_path"])
                if digest(source) != binding["solver_result_sha256"]:
                    raise ValueError("Bound solver result changed")
            else:
                source = candidate(task_id, solver)
            if source is None:
                rows.append({"task_id": task_id, "solver_model": solver, "action": "not_eligible_no_submitted_output", "judge_model": cfg["secondary_judge"]})
                continue
            run = read(source)
            binding = {"task_id": task_id, "solver_model": solver, "solver_result_path": str(source), "solver_result_sha256": digest(source),
                       "solver_run_id": source.parent.name, "stage": run.get("stage"), "recovery_stage": run.get("recovery_stage"),
                       "recovery_of": run.get("recovery_of"), "bound_at": now(), "judge_model": cfg["secondary_judge"],
                       "selection_rule": cfg["candidate_policy"][solver]}
            if freeze_bindings and not binding_path.exists():
                write(binding_path, binding)
            rows.append({**binding, "solver_status": run["status"], **select_destination(source.parent.name, cfg["secondary_judge"]),
                         "primary_judge_relationship": "same_family" if solver.split("/")[0] == cfg["comparison_judge"].split("/")[0] else "cross_family",
                         "secondary_judge_relationship": "cross_family"})
    return rows


def freeze_execution():
    paths = [CFG, BUDGET_AMENDMENT, Path(__file__), ROOT / "scripts/grade_evaluation_v2.py", ROOT / "scripts/evaluation_v2_grading.py",
             ROOT / "scripts/dispatch_evaluation_v2_grading_amended.py", ROOT / "scripts/dispatch_evaluation_v2_remaining.py",
             ROOT / "config/evaluation_v2_budget_amendment.json", ROOT / "data/evaluation_v2/rubrics.json", ROOT / "data/evaluation_v2/effective-inputs.jsonl"]
    record = {"created_at": now(), "files": {str(p.relative_to(ROOT)): digest(p) for p in paths}, "semantic_change": "Judge identity only; original criterion meanings and evidence presentation unchanged"}
    path = BASE / "execution-freeze.json"
    if path.exists():
        prior = read(path)
        if prior["files"] != record["files"]:
            raise ValueError("Secondary judging code changed after first execution")
    else:
        write(path, record)


class BoundedSecondaryClient:
    def __init__(self, client, cfg):
        self.client = client
        self.cfg = client.cfg
        self.root = client.root
        self.check_cfg = cfg

    def call(self, body, route="chat/completions", scope="judge_secondary_amended", label="call"):
        previous = [read(p) for p in (self.root / "calls").glob("*/reservation.json") if read(p).get("scope") == "judge_secondary_cross_family"]
        if len(previous) >= self.check_cfg["budget"]["maximum_new_api_requests"]:
            raise BudgetStop("Secondary judge physical-request cap reached")
        commitment = sum(r["actual_cost_usd"] if r.get("actual_cost_usd") is not None else r["reserved_usd"] for r in previous)
        # Use exactly the provider-pinned body whose reservation Client.call
        # will compute, including its small metadata token contribution.
        bounded_body = json.loads(json.dumps(body))
        pricing = self.client.models[bounded_body["model"]]["pricing"]
        bounded_body.setdefault("provider", {}).update(allow_fallbacks=False, require_parameters=True,
                                                       max_price={"prompt": float(pricing["prompt"]) * 1e6, "completion": float(pricing["completion"]) * 1e6})
        if commitment + self.client.reservation(bounded_body) > self.check_cfg["budget"]["per_phase_maximum_additional_commitment_usd"]:
            raise BudgetStop("Secondary judge phase dollar reservation cap reached")
        return self.client.call(bounded_body, route=route, scope="judge_secondary_cross_family", label=label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--key-file")
    args = parser.parse_args()
    cfg = read(CFG)
    cfg["budget"]["per_phase_maximum_additional_commitment_usd"] = read(BUDGET_AMENDMENT)["per_phase_maximum_additional_commitment_usd"]
    freeze_plan()
    rows = planned_rows(cfg, freeze_bindings=args.execute)
    write(BASE / "latest-plan.json", {"created_at": now(), "rows": rows, "human_acceptance": None,
                                   "budget_amendment_path": str(BUDGET_AMENDMENT), "budget_amendment_sha256": digest(BUDGET_AMENDMENT),
                                   "effective_phase_cap_usd": cfg["budget"]["per_phase_maximum_additional_commitment_usd"]})
    if not args.execute:
        print(json.dumps([{k: r.get(k) for k in ("task_id", "solver_model", "stage", "action")} for r in rows], indent=2))
        return
    if not args.key_file:
        parser.error("Execution requires --key-file")
    freeze_execution()
    client = BoundedSecondaryClient(amended_client(args.key_file), cfg)
    execute_plan(client, [r for r in rows if r["action"] != "not_eligible_no_submitted_output"], cfg["secondary_judge"])


if __name__ == "__main__":
    main()
