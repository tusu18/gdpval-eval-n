"""Continue independent task/model cells after a retained transport failure.

The user asked to continue until the spending stop. Failed cells are retained
and skipped, never silently retried; unrelated cells still receive their run.
"""
from pathlib import Path

import dispatch_evaluation_v5_crossjudge as scheduler
from evaluation_v5_transport_client import make_client
from run_evaluation_v2 import ROOT, digest, now, read, write

original_grade = scheduler.grade


def grade_independent_cell(*args, **kwargs):
    result = original_grade(*args, **kwargs)
    if result.get("status") == "transport_or_runner_error":
        return {**result, "status": "infrastructure_failure_retained", "raw_status": result["status"]}
    return result


if __name__ == "__main__":
    path = ROOT / "config/evaluation_v5_continue_independent_cells.json"
    files = [Path(__file__), ROOT / "scripts/dispatch_evaluation_v5_crossjudge.py",
             ROOT / "scripts/evaluation_v5_transport_client.py", ROOT / "scripts/evaluation_v5_transport.py"]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    if path.exists():
        if read(path)["files"] != hashes:
            raise ValueError("Continuation scheduler changed after execution")
    else:
        write(path, {"created_at": now(), "files": hashes,
                     "authorization": "User requested continuing without further questions and pausing only at the spending limit.",
                     "change": "Retain and skip per-cell transport errors; continue other originally requested task/model cells. Budget, schema and checkpoint safety stops remain.",
                     "automatic_failed_request_retries": 0, "api_ceiling_usd": 30})
    scheduler.make_client = make_client
    scheduler.grade = grade_independent_cell
    scheduler.main()
