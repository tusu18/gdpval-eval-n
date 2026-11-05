"""Continue a NEW failed logical request within a prior recovery attempt.

The executed primary/recovery runners and their freezes are never edited. The
existing continuation loop is reused with a new, validated parent adapter. Each
failed logical request may be physically replayed only once by this chain.
"""
import argparse
import copy
import hashlib
import json
import re
import tempfile
from pathlib import Path

import recover_evaluation_v2 as base
from dispatch_evaluation_v2_remaining import amended_client
from run_evaluation_v2 import ROOT, OUT, canonical, digest, freeze, image_part, now, read, write

DEFAULT_PARENT = '58ac1cc5-5754-4580-8c9c-8c67e1a9d619__openai_gpt-6.1-sol__recovery'
CHAIN = []
CONFIG = None


def configure(parent_name):
    global CHAIN, CONFIG
    if Path(parent_name).name != parent_name or not re.fullmatch(r'[0-9a-f-]+__openai_gpt-6\.1-sol__recovery\d*', parent_name):
        raise ValueError('Use an existing GPT-6.1 Sol recovery run ID')
    parent = OUT / 'runs' / parent_name
    result = read(parent / 'result.json')
    checkpoint = read(parent / 'checkpoint.json')
    eligible = []
    for ident in result['calls']:
        row = read(OUT / 'calls' / ident / 'reservation.json')
        if row['status'] == 'failed_unknown_charge' and row.get('label') == f"{parent_name}:turn{checkpoint['turn']+1}":
            eligible.append(ident)
    if len(eligible) != 1:
        raise ValueError('Expected exactly one failed physical request at the parent checkpoint')
    chain = []
    name = parent_name
    while True:
        if name in [x['run_id'] for x in chain]:
            raise ValueError('Cyclic recovery ancestry')
        path = OUT / 'runs' / name / 'result.json'
        record = read(path)
        chain.append({'run_id': name, 'result_path': str(path), 'sha256': digest(path),
                      'known_cost_usd': record.get('known_cost_usd', 0),
                      'unresolved_reserved_usd': record.get('unresolved_reserved_usd', 0),
                      'replayed_call_id': record.get('failed_call_id')})
        previous = record.get('recovery_of')
        if not previous:
            if not name.endswith('__primary'):
                raise ValueError('Recovery chain does not terminate in an original primary run')
            break
        name = previous
    CHAIN = list(reversed(chain))
    failed = eligible[0]
    candidate_hash = read(OUT / 'calls' / failed / 'reservation.json')['request_sha256']
    for ancestor in CHAIN:
        prior_failed = ancestor.get('replayed_call_id')
        if prior_failed:
            prior = read(OUT / 'calls' / prior_failed / 'reservation.json')
            if prior_failed == failed or prior['request_sha256'] == candidate_hash:
                raise ValueError('This would replay a previously recovered logical request twice')
    # A deterministic suffix prevents aliasing one failed request into new runs.
    suffix = len(CHAIN)
    stem = parent_name.split('__recovery')[0]
    base.PARENT = parent_name
    base.FAILED = failed
    base.RECOVERY = stem + '__recovery' + str(suffix)
    CONFIG = ROOT / 'config/evaluation_v2_recovery' / (base.RECOVERY + '.json')
    base.inspect_parent = inspect_followup_parent


def inspect_followup_parent():
    parent = OUT / 'runs' / base.PARENT
    checkpoint = read(parent / 'checkpoint.json')
    original = read(parent / 'result.json')
    state = read(parent / 'workspace/state.json')
    folder = OUT / 'calls' / base.FAILED
    request, reservation, response = read(folder / 'request.json'), read(folder / 'reservation.json'), read(folder / 'response.json')
    if checkpoint['state'] != 'before_request' or original['status'] != 'infrastructure_or_adapter_failure' or state.get('submitted'):
        raise ValueError('Parent must be an unsubmitted recovery stopped before a request')
    if reservation['status'] != 'failed_unknown_charge' or reservation['route'] != 'responses':
        raise ValueError('Failed call classification changed')
    if response.get('status') is not None or 'bad record mac' not in response.get('transport_error', '').lower():
        raise ValueError('Only a separately recorded TLS bad-record-MAC failure is eligible')
    if request['model'] != 'openai/gpt-6.1-sol' or request['input'] != checkpoint['history']:
        raise ValueError('Saved request differs from the parent checkpoint/model')
    if hashlib.sha256(canonical(request).encode()).hexdigest() != reservation['request_sha256']:
        raise ValueError('Failed request hash changed')
    acknowledged = checkpoint.get('inherited_calls', []) + checkpoint['calls']
    if len(acknowledged) != len(set(acknowledged)) or len(acknowledged) != checkpoint['turn']:
        raise ValueError('Acknowledged response counters do not span the full chain')
    for ident in acknowledged:
        if read(OUT / 'calls' / ident / 'reservation.json')['status'] != 'response_recorded':
            raise ValueError('An inherited response was not successfully recorded')
    turns = [read(p) for p in sorted(parent.glob('turn-*.json'))]
    if original['tool_calls'] != original['inherited_tool_calls'] + sum(len(t['tool_calls']) for t in turns):
        raise ValueError('Inherited and current tool counters do not reconcile')
    pending = checkpoint.get('pending_images', state.get('image_queue', []))
    content = checkpoint['history'][-1].get('content', [])
    if not isinstance(content, list):
        content = []
    labels = [json.loads(x['text']) for x in content if x['type'] == 'input_text']
    encoded = [x for x in content if x['type'] == 'input_image']
    if labels != [{k: v for k, v in item.items() if k != 'path'} for item in pending]:
        raise ValueError('Queued images do not match the exact pending history')
    if encoded != [image_part(item['path'], True) for item in pending]:
        raise ValueError('Pending image bytes changed')
    # Adapter views only: files on disk remain untouched. The reused loop needs
    # cumulative counters and the unacknowledged queue when making its copy.
    checkpoint['calls'] = acknowledged
    state['image_queue'] = copy.deepcopy(pending)
    original['known_cost_usd'] = sum(x['known_cost_usd'] for x in CHAIN)
    original['unresolved_reserved_usd'] = sum(x['unresolved_reserved_usd'] for x in CHAIN)
    original['started_at'] = read(CHAIN[0]['result_path'])['started_at']
    return parent, checkpoint, original, state, request, reservation


def prepare():
    freeze()
    parent, checkpoint, original, state, request, reservation = inspect_followup_parent()
    protected = {}
    for ancestor in CHAIN:
        protected.update(base.file_hashes(OUT / 'runs' / ancestor['run_id']))
    protected.update(base.file_hashes(OUT / 'calls' / base.FAILED))
    config = {
        'schema': 'evaluation-v2-new-logical-request-recovery-v1', 'run_id': base.RECOVERY,
        'parent_run': base.PARENT, 'original_primary_run': CHAIN[0]['run_id'],
        'failed_call_id': base.FAILED, 'failed_request_sha256': reservation['request_sha256'],
        'resume_turn_zero_based': checkpoint['turn'], 'cumulative_tool_calls': original['tool_calls'],
        'acknowledged_responses_before_resume': len(checkpoint['calls']), 'pending_images': len(state['image_queue']),
        'recovery_chain': CHAIN,
        'policy': 'One replay of this new logical request. No replay of earlier recovered requests, no task restart, no reset of turn/tool limits, no mutation of previous files or charges.',
        'implementation': 'Reuse the frozen original continuation loop with an explicitly versioned parent/counter adapter; identical saved first request and copied workspace.',
        'protected_input_hashes': protected,
    }
    if CONFIG.exists():
        if read(CONFIG) != config:
            raise ValueError('Followup configuration changed after preparation')
    else:
        write(CONFIG, config)
    paths = [Path(__file__).resolve(), Path(base.__file__).resolve(), CONFIG,
             ROOT / 'scripts/dispatch_evaluation_v2_remaining.py', ROOT / 'config/evaluation_v2_budget_amendment.json', OUT / 'freeze.json']
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    target = OUT / 'recovery' / base.RECOVERY / 'freeze-followup-v1.json'
    record = {'files': hashes, 'protected_input_hashes': protected}
    if target.exists():
        old = read(target)
        if old['files'] != hashes or old['protected_input_hashes'] != protected:
            raise ValueError('Followup recovery freeze changed')
    else:
        write(target, {'created_at': now(), **record})
    base.assert_hashes(hashes); base.assert_hashes(protected)
    return config, target


def execute(client, freeze_path=None):
    result = base.continue_run(client, freeze_path)
    result.update(recovery_chain=CHAIN, original_primary_run=CHAIN[0]['run_id'],
                  recovery_kind='new_failed_logical_request_continuation',
                  failed_logical_request_sha256=read(OUT / 'calls' / base.FAILED / 'reservation.json')['request_sha256'])
    write(client.root / 'runs' / base.RECOVERY / 'result.json', result)
    return result


def self_test():
    _, checkpoint, original, state, expected, _ = inspect_followup_parent()
    class DummyClient:
        def __init__(self, root, fail):
            self.root, self.fail = Path(root), fail
            self.cfg = read(ROOT / 'config/evaluation_v2_run.json')
            self.seen = 0
        def call(self, body, route, scope, label):
            self.seen += 1
            assert self.seen == 1 and canonical(body) == canonical(expected)
            assert label.endswith(f":turn{checkpoint['turn']+1}")
            current = read(self.root / 'runs' / base.RECOVERY / 'workspace/state.json')
            assert {k: v['viewed_pages'] for k, v in current['files'].items()} == {k: v['viewed_pages'] for k, v in state['files'].items()}
            ident = 'offline_failure' if self.fail else 'offline_success'
            write(self.root / 'calls' / ident / 'reservation.json', {
                'id': ident, 'label': label, 'reserved_usd': .83314063,
                'actual_cost_usd': None if self.fail else 0,
            })
            if self.fail:
                raise RuntimeError('Offline failure')
            return {'id': 'offline', 'output': []}, {'call_id': ident}
    protected = {}
    for ancestor in CHAIN:
        protected.update(base.file_hashes(OUT / 'runs' / ancestor['run_id']))
    for failure in (False, True):
        with tempfile.TemporaryDirectory(prefix='evaluation_v2_followup_offline_') as temp:
            client = DummyClient(temp, failure)
            result = execute(client)
            assert client.seen == 1 and result['tool_calls'] == original['tool_calls']
            assert result['inherited_model_responses'] == checkpoint['turn']
            assert result['status'] == ('infrastructure_or_adapter_failure' if failure else 'ended_without_submission')
            assert result['unresolved_calls'] == int(failure)
            assert result['inherited_known_cost_usd'] == sum(x['known_cost_usd'] for x in CHAIN)
            base.assert_hashes(protected)
    return {'offline_self_test': 'passed', 'run_id': base.RECOVERY, 'resume_turn': checkpoint['turn'] + 1,
            'cumulative_tool_calls': original['tool_calls'], 'paid_calls': 0,
            'checks': ['exact first request', 'new logical request distinct from earlier recovery',
                       'full ancestor counters and costs preserved', 'failure charge retained', 'all ancestors unchanged']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-run', default=DEFAULT_PARENT)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    configure(args.parent_run)
    if args.self_test:
        if args.execute:
            parser.error('--self-test cannot dispatch requests')
        print(json.dumps(self_test())); return
    config, path = prepare()
    if not args.execute:
        print(json.dumps({'prepared': config['run_id'], 'freeze': str(path), 'paid_calls': 0})); return
    if not args.key_file:
        parser.error('--execute requires --key-file')
    result = execute(amended_client(args.key_file), path)
    print(json.dumps({'run': result['run_id'], 'status': result['status'], 'new_cost_usd': result['known_cost_usd'],
                      'new_unresolved_reserved_usd': result['unresolved_reserved_usd']}))


if __name__ == '__main__':
    main()
