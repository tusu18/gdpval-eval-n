"""Explicit new Sol cohort after the shipping import-compatibility repair."""
import argparse
import json
from dispatch_evaluation_v2_remaining import amended_client
from evaluation_v2_compat_workspace import TASK, freeze_compatibility, install_compatibility_adapter
from run_evaluation_v2 import ROOT, OUT, now, read, write, digest, solve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    args = parser.parse_args()
    frozen = freeze_compatibility()
    task = next(t for t in map(json.loads, (ROOT / 'data/evaluation_v2/effective-inputs.jsonl').read_text().splitlines()) if t['task_id'] == TASK)
    model = 'openai/gpt-6.1-sol'
    run_id = TASK + '__' + model.replace('/', '_') + '__adapter_repair'
    if not args.execute:
        print(json.dumps({'prepared': run_id, 'freeze': str(frozen), 'paid_calls': 0})); return
    if not args.key_file:
        parser.error('--execute requires --key-file')
    install_compatibility_adapter()
    client = amended_client(args.key_file)
    write(OUT / 'compatibility' / 'shipping-repair-dispatch.json', {
        'created_at': now(), 'run_id': run_id, 'freeze_sha256': digest(frozen),
        'parent_primary_result': str(OUT / 'runs' / (TASK + '__openai_gpt-6.1-sol__primary') / 'result.json'),
        'rule': 'New adapter repair cohort. Original primary stays unchanged.', 'budget_before': client.totals()})
    result = solve(client, task, model, 'adapter_repair')
    print(json.dumps({'run': run_id, 'status': result['status'], 'known_cost_usd': result.get('known_cost_usd'), 'budget': client.totals()}))


if __name__ == '__main__':
    main()
