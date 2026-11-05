"""Explicit transport-only continuation; original failed request remains reserved."""
import shutil
from pathlib import Path

import dispatch_evaluation_v5_crossjudge as scheduler
from evaluation_v5_transport_client import make_client
from run_evaluation_v2 import ROOT, digest, now, read, write


def prepare_amendment():
    out = ROOT / "output/evaluation_v5"
    path = ROOT / "config/evaluation_v5_transport_amendment.json"
    files = [Path(__file__), ROOT / "scripts/evaluation_v5_transport.py",
             ROOT / "scripts/evaluation_v5_transport_client.py",
             ROOT / "scripts/dispatch_evaluation_v5_crossjudge.py"]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    if path.exists():
        amendment = read(path)
        if amendment["files"] != hashes:
            raise ValueError("Transport amendment files changed after execution")
        return
    ident = "02aa1805-c658-4069-8a6a-02dec146063a__google_gemini-4-argon"
    folder = out / "judges" / ident
    checkpoint = read(folder / "checkpoint.json")
    result = read(folder / "result.json")
    if result["status"] != "transport_or_runner_error" or checkpoint["state"] != "before_request":
        raise ValueError("Expected exact documented transport interruption")
    failed_id = "60ae380912e647e5b9111861225af61a"
    reservation = ROOT / "output/evaluation_v2/calls" / failed_id / "reservation.json"
    old = read(reservation)
    if old["actual_cost_usd"] is not None or old["status"] != "failed_unknown_charge":
        raise ValueError("Unexpected historical charge status")
    backup = out / "transport-recovery" / ident / "before"
    shutil.copytree(folder, backup)
    amendment = {"schema": "evaluation-v5-transport-only-amendment-1", "created_at": now(), "files": hashes,
                 "reason": "Node transport produced TLS bad-record-MAC on an image-bearing request. Use one verified-TLS Python HTTPS request with unchanged model/prompt/tools/settings.",
                 "authorization": "User requested continuing the existing-output evaluation and grader improvement within USD30; this is one explicit infrastructure recovery, no automatic retry loop.",
                 "preserved_failed_call": failed_id, "original_reservation_sha256": digest(reservation),
                 "retained_failed_call_reserve_usd": old["reserved_usd"], "old_actual_cost_usd": None,
                 "task_id": result["task_id"], "resume_turn_zero_based": checkpoint["next_turn"],
                 "before_snapshot": str(backup), "before_snapshot_hashes": {str(p.relative_to(backup)): digest(p) for p in backup.rglob("*") if p.is_file()},
                 "new_independent_task_or_judgment": False, "paid_requests_authorized_by_this_amendment": "Only existing requested task/model cells under the unchanged cumulative guard; no new tasks or solver calls."}
    write(path, amendment)
    checkpoint["state"] = "ready_next_turn"
    checkpoint["explicit_transport_recovery"] = {"amendment": str(path), "prior_request_id": failed_id,
                                                 "prior_reserve_retained": True, "possible_duplicate_provider_work": True}
    result["status"] = "running"
    result["transport_recovery_amendment"] = str(path)
    write(folder / "checkpoint.json", checkpoint)
    write(folder / "result.json", result)


if __name__ == "__main__":
    prepare_amendment()
    scheduler.make_client = make_client
    scheduler.main()
