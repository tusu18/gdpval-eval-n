"""Bind an already permitted format pilot to its first submitted recovery.

The executed pilot selector recognized only the first recovery directory name.
This explicit preparation amendment supports numbered recovery attempts without
changing the frozen prompt, case list, tools, request settings or analysis.
No API requests are made here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import evaluation_v2_judge_checks as pilot
from run_evaluation_v2 import OUT, ROOT, read, write, digest, now


def recovery_candidates(spec, cfg, root=OUT):
    prefix = spec["task_id"] + "__" + cfg["solver_model"].replace("/", "_") + "__recovery"
    candidates = []
    for directory in (Path(root) / "runs").glob(prefix + "*"):
        match = re.fullmatch(re.escape(prefix) + r"(\d*)", directory.name)
        if not match or not (directory / "result.json").exists():
            continue
        row = read(directory / "result.json")
        if row.get("task_id") != spec["task_id"] or row.get("model") != cfg["solver_model"]:
            continue
        if row.get("status") == "submitted" and row.get("recovery_stage") == "recovery":
            candidates.append((int(match.group(1) or 1), directory))
    return [directory for _, directory in sorted(candidates)]


def prepare_recovery_case(case_id):
    cfg = read(pilot.CFG)
    spec = next(s for s in pilot.case_specs(cfg) if s["case_id"] == case_id)
    if not spec.get("allow_recovery"):
        raise ValueError("Frozen pilot plan does not permit a recovery for this case")
    pilot.freeze_execution()  # verifies all executed pilot inputs remain unchanged
    manifest_path = pilot.BASE / "cases" / case_id / "manifest.json"
    if manifest_path.exists() and read(manifest_path).get("status") == "ready":
        return pilot.prepare_case(spec, cfg)  # never change a frozen ready case
    if pilot.select_run(spec, cfg) is not None:
        return pilot.prepare_case(spec, cfg)
    candidates = recovery_candidates(spec, cfg)
    if not candidates:
        return {"case_id": case_id, "status": "not_ready", "reason": "No submitted permitted recovery"}
    selected = candidates[0]
    files = [Path(__file__), Path(pilot.__file__), pilot.CFG, selected / "result.json"]
    record = {"schema": "evaluation-v2-pilot-recovery-binding-amendment-v1", "created_at": now(),
              "case_id": case_id, "task_id": spec["task_id"], "selected_run": selected.name,
              "eligible_submitted_recoveries": [p.name for p in candidates],
              "selection_rule": "Lowest numbered submitted allowed recovery; no selection by judge score or output quality",
              "reason": "Executed selector recognized only the first recovery folder, while the already permitted task recovered on a numbered later attempt",
              "semantic_changes": [], "api_requests": 0,
              "files": {str(p.relative_to(ROOT)): digest(p) for p in files},
              "timing": "Other format-pilot outputs were already observed; this task's extension judgments have not run"}
    amendment = pilot.BASE / "recovery-bindings" / (case_id + ".json")
    if amendment.exists():
        prior = read(amendment)
        if prior["files"] != record["files"] or prior["selected_run"] != selected.name:
            raise ValueError("Recovery binding changed after freezing; preserve the previous selection")
    else:
        write(amendment, record)
    # Supply the declared run only for preparation. The original executed runner
    # subsequently loads the ready, hash-checked manifest through its usual path.
    original_selector = pilot.select_run
    try:
        pilot.select_run = lambda chosen_spec, chosen_cfg: selected if chosen_spec["case_id"] == case_id else original_selector(chosen_spec, chosen_cfg)
        return pilot.prepare_case(spec, cfg)
    finally:
        pilot.select_run = original_selector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    result = prepare_recovery_case(args.case)
    print(json.dumps({k: result.get(k) for k in ("case_id", "status", "solver_run_id", "recovery_stage", "reason")}, indent=2))


if __name__ == "__main__":
    main()
