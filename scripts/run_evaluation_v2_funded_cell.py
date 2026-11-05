"""One already-planned cell using the recorded post-core allocation/image bounds.

Only administrative reservation changes; original solver, task, images and
request settings are unchanged. Earlier results and reservations are immutable.
"""
import argparse
import json
import uuid
from pathlib import Path

import run_evaluation_v2_supplemental_cell as worker
from continue_evaluation_v2_saved_request import (
    ReleasedAllocationClient, ALLOCATION, SONNET_EVIDENCE, core_grade_gate,
)
from run_evaluation_v2 import ROOT, OUT, digest, now, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-prefix', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    args = parser.parse_args()
    cfg, tasks, _ = worker.tasks_and_models()
    cell = worker.select_cell(cfg, args.task_prefix, args.model)
    gate = core_grade_gate()
    event = {'attempt_id': uuid.uuid4().hex, 'created_at': now(), 'cell': cell,
             'gates': gate, 'request_settings_changed': False,
             'budget_or_reservations_changed': True,
             'change_scope': 'New calls only: recorded solver allocation release and documented Sonnet image bound; global cap remains USD30; historical reserves unchanged.',
             'allocation_path': str(ALLOCATION), 'allocation_sha256': digest(ALLOCATION),
             'image_evidence_path': str(SONNET_EVIDENCE), 'image_evidence_sha256': digest(SONNET_EVIDENCE)}
    existing = worker.existing_state(cell)
    if existing or not args.execute:
        event.update(existing or {'action': 'prepared_no_paid_calls'})
        print(json.dumps(event)); return
    if not args.key_file or not gate['ready']:
        raise ValueError('Execution requires a key file and completed core grading')
    extension_freeze = worker.freeze_extension()
    folder = OUT / 'extension/funded-workers'
    paths = [Path(__file__).resolve(), Path(worker.__file__).resolve(),
             ROOT/'scripts/continue_evaluation_v2_saved_request.py',
             ROOT/'scripts/evaluation_v2_verified_sonnet_budget.py',
             Path(extension_freeze), ALLOCATION, SONNET_EVIDENCE]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    frozen = folder/'freeze.json'
    if frozen.exists():
        if read(frozen)['files'] != hashes:
            raise ValueError('Funded worker changed after freeze')
    else:
        write(frozen, {'created_at': now(), 'files': hashes,
                       'authorized_total_usd': 30,
                       'original_reservations_modified': False})
    event.update(freeze_path=str(frozen), freeze_sha256=digest(frozen))
    event_path = folder/'events'/(event['attempt_id']+'.json')
    write(event_path, event)
    # Reuse the audited atomic lease and exclusive run-directory claim.
    worker.ExtensionClient = ReleasedAllocationClient
    result = worker.run_one(cell, tasks, args.key_file, event, event_path)
    print(json.dumps({k: result.get(k) for k in
                      ('cell', 'action', 'status', 'budget_after')}))


if __name__ == '__main__':
    main()
