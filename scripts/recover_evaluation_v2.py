"""One explicit continuation per selected transport-interrupted primary run.

The original result, checkpoint, workspace and unknown charge are immutable.
This runner uses the exact saved failed request, then continues the original
turn/tool limits in a copied workspace. No automatic physical retries occur.
"""
import argparse
import copy
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

from dispatch_evaluation_v2_remaining import amended_client
from run_evaluation_v2 import ROOT, OUT, BudgetStop, canonical, digest, freeze, image_part, now, read, write
from evaluation_v2_workspace import Workspace

PARENT = '3c19c6d1-672c-467a-8437-6fe21afb8eae__openai_gpt-6.1-sol__primary'
FAILED = 'bb50d7e682e44116a86e5268bf345a32'
RECOVERY = PARENT.removesuffix('__primary') + '__recovery'
CONFIG = ROOT / 'config/evaluation_v2_recovery' / (RECOVERY + '.json')


def select_target(task_prefix):
    global PARENT, FAILED, RECOVERY, CONFIG
    candidates = []
    for folder in (OUT / 'runs').glob(task_prefix + '*__openai_gpt-6.1-sol__primary'):
        if (folder / 'result.json').is_file() and read(folder / 'result.json')['status'] == 'infrastructure_or_adapter_failure':
            candidates.append(folder)
    if len(candidates) != 1:
        raise RuntimeError('Task prefix must identify exactly one failed primary GPT-6.1 Sol run')
    parent = candidates[0]
    checkpoint = read(parent / 'checkpoint.json')
    failed = []
    for ident in read(parent / 'result.json')['calls']:
        row = read(OUT / 'calls' / ident / 'reservation.json')
        if row['status'] == 'failed_unknown_charge' and row.get('label') == f"{parent.name}:turn{checkpoint['turn']+1}":
            failed.append(ident)
    if len(failed) != 1:
        raise RuntimeError('Checkpoint must identify one recorded failed physical request')
    PARENT = parent.name
    FAILED = failed[0]
    RECOVERY = PARENT.removesuffix('__primary') + '__recovery'
    CONFIG = ROOT / 'config/evaluation_v2_recovery' / (RECOVERY + '.json')


def file_hashes(folder):
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(Path(folder).rglob('*')) if p.is_file()}


def assert_hashes(hashes):
    for name, expected in hashes.items():
        if digest(ROOT / name) != expected:
            raise RuntimeError('Protected input changed: ' + name)


def replace_owned_paths(value, old, new):
    """Relocate only copied workspace paths; never rewrite model history."""
    if isinstance(value, str):
        return new + value[len(old):] if value == old or value.startswith(old + '/') else value
    if isinstance(value, list):
        return [replace_owned_paths(x, old, new) for x in value]
    if isinstance(value, dict):
        return {k: replace_owned_paths(v, old, new) for k, v in value.items()}
    return value


def inspect_parent():
    parent = OUT / 'runs' / PARENT
    checkpoint = read(parent / 'checkpoint.json')
    result = read(parent / 'result.json')
    state = read(parent / 'workspace/state.json')
    call = OUT / 'calls' / FAILED
    request = read(call / 'request.json')
    reservation = read(call / 'reservation.json')
    if checkpoint['state'] != 'before_request' or checkpoint['turn'] < 0:
        raise RuntimeError('Recovery target must have a pre-request checkpoint')
    if result['status'] != 'infrastructure_or_adapter_failure' or state.get('submitted'):
        raise RuntimeError('Parent is not an unsubmitted infrastructure failure')
    if reservation['status'] != 'failed_unknown_charge':
        raise RuntimeError('Original failed reservation changed; re-audit recovery')
    response = read(call / 'response.json')
    if response.get('status') is not None or 'bad record mac' not in response.get('transport_error', '').lower():
        raise RuntimeError('Only the audited TLS bad-record-MAC failure class is eligible')
    if reservation['route'] != 'responses' or request['model'] != 'openai/gpt-6.1-sol':
        raise RuntimeError('Recovery supports the original GPT-6.1 Sol Responses contract only')
    if request['input'] != checkpoint['history']:
        raise RuntimeError('Failed request does not equal saved full history')
    if hashlib.sha256(canonical(request).encode()).hexdigest() != reservation['request_sha256']:
        raise RuntimeError('Saved failed request hash mismatch')
    pending = state['image_queue']
    content = checkpoint['history'][-1].get('content', [])
    if not isinstance(content, list):
        content = []
    labels = [json.loads(x['text']) for x in content if x['type'] == 'input_text']
    if labels != [{k: v for k, v in x.items() if k != 'path'} for x in pending]:
        raise RuntimeError('Pending image labels do not match workspace state')
    # Verify queued image content as well as its labels, without changing it.
    encoded = [x for x in content if x['type'] == 'input_image']
    if encoded != [image_part(x['path'], True) for x in pending]:
        raise RuntimeError('Pending rendered bytes differ from the saved request')
    turns = [read(p) for p in sorted(parent.glob('turn-*.json'))]
    if result['tool_calls'] != sum(len(t['tool_calls']) for t in turns) or len(checkpoint['calls']) != checkpoint['turn']:
        raise RuntimeError('Parent counters do not reconcile to acknowledged turn records')
    return parent, checkpoint, result, state, request, reservation


def prepare():
    freeze()  # Verify the original primary freeze before creating an amendment.
    parent, checkpoint, result, state, request, reservation = inspect_parent()
    protected = file_hashes(parent)
    protected.update(file_hashes(OUT / 'calls' / FAILED))
    config = {
        'recovery_of': PARENT, 'failed_call_id': FAILED, 'run_id': RECOVERY,
        'stage': 'supplemental', 'recovery_stage': 'recovery',
        'purpose': 'Explicit infrastructure continuation; never replaces the primary outcome.',
        'physical_replays_of_failed_request': 1, 'automatic_retries': 0,
        'resume_turn_zero_based': checkpoint['turn'], 'inherited_tool_calls': result['tool_calls'],
        'pending_images': len(state['image_queue']),
        'pending_image_labels': [{k: v for k, v in x.items() if k != 'path'} for x in state['image_queue']],
        'request_sha256': reservation['request_sha256'],
        'request_body_policy': 'Exact saved failed request, including all historical images. Later calls use the same parameters, system and tools with continued history.',
        'limits_policy': 'Original max_turns, max_tool_calls and per-request timeout continue; no task restart or limit reset.',
        'accounting_policy': 'Shared amended client ledger; original unknown charge remains reserved; all new physical requests reserved separately.',
        'workspace_policy': 'Copy all files; rewrite only copied workspace-owned paths in state. Original history and source paths remain unchanged.',
        'protected_input_hashes': protected,
    }
    if CONFIG.exists():
        if read(CONFIG) != config:
            raise RuntimeError('Recovery configuration changed after preparation')
    else:
        write(CONFIG, config)
    files = {str(p.relative_to(ROOT)): digest(p) for p in [
        Path(__file__).resolve(), CONFIG, ROOT / 'scripts/dispatch_evaluation_v2_remaining.py',
        ROOT / 'config/evaluation_v2_budget_amendment.json', OUT / 'freeze.json',
    ]}
    target = OUT / 'recovery' / RECOVERY / 'freeze-generic-v2.json'
    local_freeze = {'files': files, 'protected_input_hashes': protected}
    if target.exists():
        saved = read(target)
        if saved['files'] != files or saved['protected_input_hashes'] != protected:
            raise RuntimeError('Recovery freeze changed; do not execute')
    else:
        write(target, {'created_at': now(), **local_freeze})
    assert_hashes(files)
    assert_hashes(protected)
    return config, target


def continue_run(client, local_freeze=None):
    parent, checkpoint, original, old_state, request_template, reservation = inspect_parent()
    protected = file_hashes(parent)
    protected.update(file_hashes(OUT / 'calls' / FAILED))
    folder = client.root / 'runs' / RECOVERY
    if (folder / 'result.json').exists():
        return read(folder / 'result.json')
    if folder.exists():
        raise RuntimeError('Recovery already started; no implicit repeat is permitted')
    task = read(parent / 'task.json')
    folder.mkdir(parents=True)
    write(folder / 'task.json', task)
    shutil.copytree(parent / 'workspace', folder / 'workspace')
    state = replace_owned_paths(old_state, str(parent / 'workspace'), str(folder / 'workspace'))
    write(folder / 'workspace/state.json', state)
    # Retain the exact pre-recovery checkpoint as a forensic input.
    shutil.copyfile(parent / 'checkpoint.json', folder / 'inherited-checkpoint.json')
    shutil.copyfile(parent / 'result.json', folder / 'inherited-result.json')
    ws = Workspace(task, folder / 'workspace')
    pending_images = list(ws.image_queue)
    ws.image_queue.clear()
    ws._persist()
    history = copy.deepcopy(checkpoint['history'])
    cfg = client.cfg
    result = {
        'task_id': task['task_id'], 'occupation': task['occupation'], 'model': request_template['model'],
        'stage': 'supplemental', 'recovery_stage': 'recovery', 'recovery_of': PARENT,
        'failed_call_id': FAILED, 'run_id': RECOVERY, 'started_at': now(),
        'original_started_at': original['started_at'], 'status': 'running',
        'calls': [], 'inherited_calls': list(checkpoint['calls']),
        'inherited_tool_calls': original['tool_calls'], 'tool_calls': original['tool_calls'],
        'resume_turn_zero_based': checkpoint['turn'], 'inherited_model_responses': len(checkpoint['calls']),
        'artifact_paths': [], 'human_acceptance': None,
        'inherited_known_cost_usd': original['known_cost_usd'],
        'inherited_unresolved_reserved_usd': original['unresolved_reserved_usd'],
        'original_failure_retained': True,
        'recovery_freeze': str(local_freeze) if local_freeze else None,
        'cost_scope': 'known_cost_usd and calls contain new continuation calls only; inherited cost is separate and must not be double counted.',
    }
    started = time.monotonic()
    try:
        for turn in range(checkpoint['turn'], cfg['max_turns']):
            body = copy.deepcopy(request_template)
            body['input'] = history
            if turn == checkpoint['turn'] and canonical(body) != canonical(request_template):
                raise RuntimeError('First continuation request changed')
            write(folder / 'checkpoint.json', {
                'state': 'before_request', 'turn': turn, 'history': history,
                'calls': result['calls'], 'inherited_calls': result['inherited_calls'],
                'pending_images': pending_images, 'tool_calls': result['tool_calls'],
            })
            data, meta = client.call(body, 'responses', scope='solver_recovery', label=f'{RECOVERY}:turn{turn+1}')
            result['calls'].append(meta['call_id'])
            # The failed request did not acknowledge these views. Only this
            # successful response permits acknowledgement in the copied state.
            if pending_images:
                ws.acknowledge_images(pending_images)
            pending_images = []
            outputs = data.get('output', [])
            history.extend(outputs)
            calls = [{'id': x['call_id'], 'function': {'name': x['name'], 'arguments': x['arguments']}}
                     for x in outputs if x.get('type') == 'function_call']
            finish = (data.get('incomplete_details') or {}).get('reason')
            write(folder / f'turn-{turn+1:02d}.json', {
                'call_id': meta['call_id'], 'finish_reason': finish, 'tool_calls': calls,
                'response_id': data.get('id'), 'served_provider': data.get('provider'),
            })
            if not calls:
                result['status'] = 'output_token_limit' if finish in ('length', 'max_output_tokens') else 'ended_without_submission'
                break
            for call in calls:
                result['tool_calls'] += 1
                if result['tool_calls'] > cfg['max_tool_calls']:
                    raise RuntimeError('Original tool call limit reached')
                try:
                    reply = ws.call(call['function']['name'], json.loads(call['function']['arguments']))
                except Exception as exc:
                    reply = {'error': str(exc)[:1000]}
                history.append({'type': 'function_call_output', 'call_id': call['id'], 'output': json.dumps(reply, ensure_ascii=False)})
            pending_images = list(ws.image_queue)
            ws.image_queue.clear()
            ws._persist()
            if pending_images:
                image_content = []
                for item in pending_images:
                    image_content.extend([
                        {'type': 'input_text', 'text': json.dumps({k: v for k, v in item.items() if k != 'path'})},
                        image_part(item['path'], True),
                    ])
                history.append({'role': 'user', 'content': image_content})
            write(folder / 'checkpoint.json', {
                'state': 'ready_next_turn', 'turn': turn + 1, 'history': history,
                'calls': result['calls'], 'inherited_calls': result['inherited_calls'],
                'pending_images': pending_images, 'tool_calls': result['tool_calls'],
            })
            if ws.submitted:
                result['status'] = 'submitted'
                result['submission'] = ws.submitted
                result['artifact_paths'] = [x['path'] for x in ws.submitted]
                break
        else:
            result['status'] = 'turn_limit'
    except BudgetStop as exc:
        result.update(status='budget_limited', error=str(exc))
    except Exception as exc:
        result.update(status='infrastructure_or_adapter_failure', error=str(exc)[:1500])
    task_calls = [read(p) for p in (client.root / 'calls').glob('*/reservation.json')
                  if read(p).get('label', '').startswith(RECOVERY + ':')]
    result['calls'] = [x['id'] for x in task_calls]
    result['completed_at'] = now()
    result['continuation_elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['known_cost_usd'] = sum(x.get('actual_cost_usd') or 0 for x in task_calls)
    result['unresolved_calls'] = sum(x.get('actual_cost_usd') is None for x in task_calls)
    result['unresolved_reserved_usd'] = sum(x['reserved_usd'] for x in task_calls if x.get('actual_cost_usd') is None)
    result['workspace'] = str(folder / 'workspace')
    assert_hashes(protected)
    write(folder / 'result.json', result)
    return result


def self_test():
    """Offline exact-replay, no-premature-acknowledgement and immutability test."""
    _, checkpoint, original, original_state, expected, _ = inspect_parent()
    initial_views = {k: v['viewed_pages'] for k, v in original_state['files'].items()}
    has_artifact = bool(initial_views)
    class DummyClient:
        def __init__(self, root, fail):
            self.root = Path(root)
            self.cfg = read(ROOT / 'config/evaluation_v2_run.json')
            self.fail = fail
            self.seen = 0
        def call(self, body, route, scope, label):
            self.seen += 1
            assert self.seen == 1 and canonical(body) == canonical(expected)
            assert route == 'responses' and scope == 'solver_recovery'
            assert label.endswith(f":turn{checkpoint['turn']+1}")
            state = read(self.root / 'runs' / RECOVERY / 'workspace/state.json')
            assert {k: v['viewed_pages'] for k, v in state['files'].items()} == initial_views
            call_id = 'offline_failure' if self.fail else 'offline_success'
            write(self.root / 'calls' / call_id / 'reservation.json', {
                'id': call_id, 'label': label, 'reserved_usd': 6.4519715,
                'actual_cost_usd': None if self.fail else 0,
            })
            if self.fail:
                raise RuntimeError('Offline transport failure')
            outputs = []
            if has_artifact:
                name = next(iter(state['files']))
                outputs = [{'type': 'function_call', 'call_id': 'offline_submit',
                            'name': 'submit_files', 'arguments': json.dumps({'filenames': [name]})}]
            return {'id': 'offline', 'output': outputs}, {'call_id': call_id}
    for fail in (False, True):
        with tempfile.TemporaryDirectory(prefix='evaluation_v2_recovery_offline_') as temp:
            client = DummyClient(temp, fail)
            result = continue_run(client)
            state = read(Path(result['workspace']) / 'state.json')
            assert client.seen == 1
            expected_status = 'infrastructure_or_adapter_failure' if fail else ('submitted' if has_artifact else 'ended_without_submission')
            assert result['status'] == expected_status
            assert result['tool_calls'] == original['tool_calls'] + int(has_artifact and not fail)
            expected_views = copy.deepcopy(initial_views)
            if not fail:
                for item in original_state['image_queue']:
                    if item['filename'] in expected_views and item['page'] not in expected_views[item['filename']]:
                        expected_views[item['filename']].append(item['page'])
            assert {k: v['viewed_pages'] for k, v in state['files'].items()} == expected_views
            assert result['unresolved_calls'] == (1 if fail else 0)
    return {'offline_self_test': 'passed', 'task': PARENT, 'pending_images': len(original_state['image_queue']), 'paid_calls': 0, 'checks': [
        'exact saved request', 'turn and tool counters continued', 'acknowledgement only after success',
        'failure reservation retained', 'original files unchanged', 'separate copied submission',
    ]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--task', default='3c19', help='Unique original task UUID prefix (e.g. 3c19 or 58ac)')
    args = parser.parse_args()
    select_target(args.task)
    if args.self_test:
        if args.execute:
            parser.error('--self-test cannot be combined with --execute')
        print(json.dumps(self_test()))
        return
    config, local_freeze = prepare()
    if not args.execute:
        print(json.dumps({'prepared': config['run_id'], 'freeze': str(local_freeze), 'paid_calls': 0}))
        return
    if not args.key_file:
        parser.error('--execute requires --key-file')
    result = continue_run(amended_client(args.key_file), local_freeze)
    print(json.dumps({'run': RECOVERY, 'status': result['status'], 'new_cost_usd': result['known_cost_usd'],
                      'new_unresolved_reserved_usd': result['unresolved_reserved_usd']}))


if __name__ == '__main__':
    main()
