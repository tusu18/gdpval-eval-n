"""Grade the explicitly separate shipping adapter-repair artifact.

No frozen input or primary result changes. Uses the frozen grader function with
its supported stage argument, the shared amended client, and a separate freeze.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_evaluation_v2 import ROOT, OUT, read, write, digest, now
from dispatch_evaluation_v2_remaining import amended_client
from dispatch_evaluation_v2_grading_amended import select_destination, resolution_index
from grade_evaluation_v2 import run_primary, prepare_run

TASK = "76418a2c-a3c0-4894-b89d-2493369135d9"
SOLVER = "openai/gpt-6.1-sol"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--key-file")
    args = parser.parse_args()
    run_dir = OUT / "runs" / (TASK + "__" + SOLVER.replace("/", "_") + "__adapter_repair")
    source = run_dir / "result.json"
    if not source.exists():
        raise ValueError("Adapter-repair run has no terminal result")
    result = read(source)
    if (result.get("task_id"), result.get("model"), result.get("stage"), result.get("status")) != (TASK, SOLVER, "adapter_repair", "submitted"):
        raise ValueError("Expected the separately submitted Sol shipping adapter-repair run")
    judge = read(ROOT / "config/evaluation_v2_run.json")["primary_judge"]
    tasks = {t["task_id"]: t for t in map(json.loads, (ROOT / "data/evaluation_v2/effective-inputs.jsonl").read_text().splitlines())}
    packet, private, images, _ = prepare_run(run_dir, tasks[TASK], read(ROOT / "data/evaluation_v2/rubrics.json"))
    if packet is None:
        raise ValueError("Submitted adapter-repair output lacks a usable native submission")
    row = {"task_id": TASK, "solver_run_id": run_dir.name, "solver_model": SOLVER, "solver_result_path": str(source),
           "stage": "adapter_repair", "solver_status": "submitted", "judge_model": judge,
           **select_destination(run_dir.name, judge)}
    if not args.execute:
        print(json.dumps({"eligible": True, "task_id": TASK, "stage": "adapter_repair", "action": row["action"],
                          "artifact_count": len(packet["artifacts"]), "image_count": len(images), "source_coverage": packet["coverage"], "api_calls": 0}, indent=2))
        return
    if not args.key_file:
        parser.error("--execute requires --key-file")
    paths = [Path(__file__), ROOT / "scripts/grade_evaluation_v2.py", ROOT / "scripts/evaluation_v2_grading.py",
             ROOT / "scripts/dispatch_evaluation_v2_remaining.py", ROOT / "config/evaluation_v2_budget_amendment.json",
             ROOT / "config/evaluation_v2_shipping_compatibility.json", ROOT / "data/evaluation_v2/rubrics.json",
             ROOT / "data/evaluation_v2/effective-inputs.jsonl", source]
    record = {"created_at": now(), "files": {str(p.relative_to(ROOT)): digest(p) for p in paths}, "stage": "adapter_repair",
              "purpose": "Grade this repair artifact separately; preserve original ended-without-submission and every previous judgment",
              "semantic_change_to_grader": None, "shared_budget_amendment": "config/evaluation_v2_budget_amendment.json"}
    freeze = OUT / "adapter-repair-grading-freeze.json"
    if freeze.exists():
        if read(freeze)["files"] != record["files"]:
            raise ValueError("Adapter-repair grading inputs changed after freeze")
    else:
        write(freeze, record)
    if row["action"] not in ("grade_unattempted", "preserve_existing"):
        raise ValueError("A prior attempt requires explicit separate continuation; no automatic retry")
    client = amended_client(args.key_file)
    run_primary(client, judge, task_prefix=TASK, solver_model=SOLVER, stage="adapter_repair", execute=True)
    write(OUT / "grade-resolution-index.json", resolution_index([row]))


if __name__ == "__main__":
    main()
