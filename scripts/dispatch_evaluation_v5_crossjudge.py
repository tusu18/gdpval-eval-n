"""Resume the frozen 80-cell study with bounded independent concurrency.

Each physical request still uses the shared locked cumulative USD30 guard.
This scheduler neither retries ambiguous calls nor changes the grader design.
"""
import argparse
import concurrent.futures
import json

from run_evaluation_v5_crossjudge import (
    DEFAULT_MODELS, INVENTORY, OUT, SCOPE, freeze, grade, make_client,
)
from run_evaluation_v2 import digest, now, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("Use one to four workers")
    settings = {"models": DEFAULT_MODELS, "max_turns": 8, "max_tokens": 6000,
                "initial_text_threshold_chars": 12000, "initial_max_images": 2,
                "max_new_images_per_turn": 4, "reasoning_effort": "low",
                "automatic_retries": 0, "scope": SCOPE}
    freeze(settings)
    client = make_client(args.key_file)
    inventory = read(INVENTORY)
    cells = [(row, model) for row in inventory["tasks"] for model in DEFAULT_MODELS]
    record = {"started_at": now(), "script_sha256": digest(__file__),
              "workers": args.workers, "settings": settings,
              "task_count": 40, "requested_assessments": len(cells),
              "budget_before": client.totals(), "completed_cells": [],
              "stop_reason": None,
              "selection": "All forty pinned task bundles; existing completed cells reused without new requests."}
    log = OUT / ("dispatch-" + now().replace(":", "-") + ".json")
    write(log, record)
    iterator = iter(cells)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}

        def enqueue():
            try:
                row, model = next(iterator)
            except StopIteration:
                return False
            future = pool.submit(grade, client, row, model, 8, 6000, True)
            active[future] = (row["task_id"], model)
            return True

        for _ in range(args.workers):
            enqueue()
        while active:
            done, _ = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                task_id, model = active.pop(future)
                try:
                    result = future.result()
                    summary = {k: result.get(k) for k in
                               ("task_id", "judge_requested_model", "status", "overall", "known_cost_usd", "unresolved_reserved_usd", "error")}
                except Exception as error:
                    summary = {"task_id": task_id, "judge_requested_model": model,
                               "status": "scheduler_error", "error": str(error)[:500]}
                record["completed_cells"].append(summary)
                if summary["status"] in ("budget_blocked", "transport_or_runner_error", "checkpoint_review_required", "scheduler_error"):
                    record["stop_reason"] = summary
                record["budget_latest"] = client.totals()
                write(log, record)
                print(json.dumps({**summary, "completed_cells": len(record["completed_cells"]),
                                  "committed_usd": record["budget_latest"]["committed_usd"]}), flush=True)
            if not record["stop_reason"]:
                while len(active) < args.workers and enqueue():
                    pass
    record["finished_at"] = now()
    record["budget_after"] = client.totals()
    write(log, record)
    print(json.dumps({"dispatch_finished": True, "completed_cells": len(record["completed_cells"]),
                      "stop_reason": record["stop_reason"], "budget": record["budget_after"]}), flush=True)


if __name__ == "__main__":
    main()
