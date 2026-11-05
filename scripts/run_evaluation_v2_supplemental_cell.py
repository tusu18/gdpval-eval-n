"""Scheduling-only one-cell worker; no API dispatch without --execute.

Imports the frozen extension solver/client unchanged. An external atomic lease
coordinates these workers; the frozen solver's exclusive run-directory mkdir
also protects against the older controller, which does not observe leases.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import uuid

from extend_evaluation_v2_models import (
    CONFIG, ExtensionClient, cell_status, freeze_extension, phase_gates,
    planned_cells, tasks_and_models,
)
from run_evaluation_v2 import OUT, ROOT, digest, now, read, solve, write

AMENDMENT = ROOT / 'config/evaluation_v2_parallel_scheduling_amendment.json'
WORKERS = OUT / 'extension' / 'scheduling-workers'


def select_cell(cfg, task_prefix, model):
    if not task_prefix or not model:
        raise ValueError('Both --task-prefix and exact --model are required')
    matches = [c for c in planned_cells(cfg, 'supplemental')
               if c['task_id'].startswith(task_prefix) and c['model'] == model]
    if len(matches) != 1:
        raise ValueError('Selection must identify exactly one of the original 16 first-pass cells')
    return matches[0]


def existing_state(cell, root=OUT):
    folder = Path(root) / 'runs' / cell['run_id']
    if not folder.exists():
        return None
    result = folder / 'result.json'
    if result.is_file():
        return {'action': 'skip_existing_result_preserved', 'status': read(result).get('status'),
                'result_path': str(result), 'result_sha256': digest(result)}
    return {'action': 'wait_existing_run_directory_preserved',
            'status': 'existing_run_in_progress_or_interrupted_requires_review', 'run_path': str(folder)}


def acquire_lease(cell, attempt_id, workers=WORKERS):
    leases = Path(workers) / 'leases'
    leases.mkdir(parents=True, exist_ok=True)
    lease = leases / cell['run_id']
    try:
        lease.mkdir()  # Atomic and deliberately no exist_ok.
    except FileExistsError:
        return None
    write(lease / 'owner.json', {'created_at': now(), 'attempt_id': attempt_id,
                               'pid': os.getpid(), 'cell': cell,
                               'policy': 'Retained for audit; no automatic takeover or retry'})
    return lease


def freeze_worker(extension_freeze):
    paths = [Path(__file__).resolve(), AMENDMENT, CONFIG,
             Path(extension_freeze), ROOT / 'scripts/extend_evaluation_v2_models.py']
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    path = WORKERS / 'freeze.json'
    payload = {'created_at': now(), 'files': hashes, 'changes': 'Scheduling only',
               'request_settings_changed': False, 'budget_or_reservations_changed': False}
    # All workers should observe one immutable freeze. Hard-link a fully written
    # unique candidate so a concurrent reader never sees a partial destination.
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_name('.freeze-candidate-' + uuid.uuid4().hex + '.json')
    write(candidate, payload)
    try:
        try:
            os.link(candidate, path)
        except FileExistsError:
            pass
    finally:
        candidate.unlink()
    if read(path)['files'] != hashes:
        raise RuntimeError('Scheduling worker changed after freeze; use an explicit new amendment')
    return path


def run_one(cell, tasks, key_file, event, event_path):
    """Call the unchanged solver at most once after exclusive worker lease."""
    lease = acquire_lease(cell, event['attempt_id'])
    if lease is None:
        event.update(action='wait_existing_worker_lease_preserved',
                     status='leased_in_progress_or_interrupted_requires_review',
                     lease_path=str(WORKERS / 'leases' / cell['run_id']), completed_at=now())
        write(event_path, event)
        return event
    event['lease_path'] = str(lease)
    write(event_path, event)
    # Legacy controller may have created the run after our initial inspection.
    existing = existing_state(cell)
    if existing:
        event.update(existing, completed_at=now())
        write(event_path, event)
        write(lease / 'completion.json', event)
        return event
    try:
        from evaluation_v2_compat_workspace import install_compatibility_adapter
        install_compatibility_adapter()
        client = ExtensionClient(key_file)
        event.update(budget_before=client.totals(), action='invoke_frozen_solver_once')
        write(event_path, event)
        try:
            result = solve(client, tasks[cell['task_id']], cell['model'], 'supplemental')
        except FileExistsError as exc:
            folder = OUT / 'runs' / cell['run_id']
            if exc.filename and Path(exc.filename).resolve() == folder.resolve() and folder.exists():
                event.update(existing_state(cell) or {}, action='run_directory_claim_race_preserved',
                             note='Another controller won exclusive mkdir before this worker could dispatch.')
            else:
                raise
        else:
            event.update(status=result.get('status'), solver_returned=True,
                         cell_after=cell_status(cell))
        event['budget_after'] = client.totals()
    except Exception as exc:
        # Preserve evidence and the lease. Never synthesize/overwrite solver results.
        event.update(action='worker_stopped_requires_review', status='worker_exception',
                     error_type=type(exc).__name__, error=str(exc)[:1200])
    event['completed_at'] = now()
    write(event_path, event)
    write(lease / 'completion.json', event)
    return event


def self_test():
    cfg, _, _ = tasks_and_models()
    cell = select_cell(cfg, '3c19', 'anthropic/claude-sonnet-5.5')
    with tempfile.TemporaryDirectory(prefix='v2-scheduling-test-') as tmp:
        root = Path(tmp)
        # Test1: refuse cells outside the frozen16 and preserve an existing run.
        try:
            select_cell(cfg, 'ce864', 'anthropic/claude-sonnet-5.5')
        except ValueError:
            pass
        else:
            raise AssertionError('Unplanned task accepted')
        folder = root / 'runs' / cell['run_id'];folder.mkdir(parents=True)
        marker = folder / 'checkpoint.json';marker.write_text('original checkpoint')
        before = digest(marker)
        assert existing_state(cell, root)['action'] == 'wait_existing_run_directory_preserved'
        write(folder / 'result.json', {'status': 'submitted'})
        assert existing_state(cell, root)['action'] == 'skip_existing_result_preserved'
        assert digest(marker) == before
        # Test2: only one atomic worker lease; existing owner remains unchanged.
        lease = acquire_lease(cell, 'test-owner', root / 'workers')
        owner_hash = digest(lease / 'owner.json')
        assert acquire_lease(cell, 'test-loser', root / 'workers') is None
        assert digest(lease / 'owner.json') == owner_hash
    return {'offline_checks': ['unplanned cell refused and existing run preserved',
                               'atomic lease refuses duplicate owner'], 'status': 'passed', 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-prefix')
    parser.add_argument('--model')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        if args.execute:
            parser.error('--self-test cannot execute')
        print(json.dumps(self_test()));return
    cfg, tasks, _ = tasks_and_models()
    try:
        cell = select_cell(cfg, args.task_prefix, args.model)
    except ValueError as exc:
        parser.error(str(exc))
    gates = phase_gates(cfg, tasks, second=False)
    event = {'attempt_id': uuid.uuid4().hex, 'created_at': now(), 'cell': cell,
             'gates': gates, 'execute_requested': args.execute,
             'amendment': str(AMENDMENT), 'amendment_sha256': digest(AMENDMENT),
             'request_settings_changed': False, 'budget_or_reservations_changed': False}
    existing = existing_state(cell)
    if not args.execute:
        event.update(existing or {'action': 'planned_unstarted_cell'})
        print(json.dumps(event, indent=2));return
    event_path = WORKERS / 'events' / (event['attempt_id'] + '.json')
    if existing:
        event.update(existing, completed_at=now());write(event_path, event)
        print(json.dumps(event));return
    if not gates['ready']:
        event.update(action='blocked_by_unchanged_phase_gates', completed_at=now())
        write(event_path, event);print(json.dumps(event));raise SystemExit(2)
    if not args.key_file:
        parser.error('--execute on an unstarted cell requires --key-file')
    extension_freeze = freeze_extension()
    worker_freeze = freeze_worker(extension_freeze)
    event.update(extension_freeze=str(extension_freeze), extension_freeze_sha256=digest(extension_freeze),
                 worker_freeze=str(worker_freeze), worker_freeze_sha256=digest(worker_freeze))
    write(event_path, event)
    event = run_one(cell, tasks, args.key_file, event, event_path)
    print(json.dumps(event), flush=True)
    if event.get('status') == 'worker_exception':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
