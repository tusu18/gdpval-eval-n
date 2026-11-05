"""Offline replay of recorded shipping tool arguments, never a solver result."""
import json
from pathlib import Path
from evaluation_v2_compat_workspace import CompatibilityWorkspace, TASK, normalize_import_copy
from run_evaluation_v2 import ROOT, OUT, digest, read, write, now

parent = OUT / 'runs' / (TASK + '__openai_gpt-6.1-sol__primary')
task = read(parent / 'task.json')
state = read(parent / 'workspace/state.json')
folder = OUT / 'compatibility/offline-shipping-test'
if folder.exists():
    raise SystemExit('Offline verification already exists; inspect it rather than overwrite it')
ws = CompatibilityWorkspace(task, folder / 'workspace')
source_hashes = {ref['path']: digest(ref['path']) for ref in task['references']}
result = {'started_at': now(), 'task_id': TASK, 'paid_calls': 0,
          'scope': 'Offline replay of exact historical tool arguments to validate an infrastructure adapter; not a model run, human review, or business acceptance.', 'checks': []}
for event in state['events']:
    if event['tool'] not in ('view_source', 'write_workbook'):
        continue
    reply = ws.call(event['tool'], event['arguments'])
    row = {'tool': event['tool'], 'arguments_sha256': __import__('hashlib').sha256(json.dumps(event['arguments'], sort_keys=True).encode()).hexdigest(),
           'reply': reply, 'successful': 'error' not in reply}
    if event['tool'] == 'write_workbook' and row['successful']:
        artifact = ws.files[event['arguments']['filename']]
        row['artifact_sha256'] = artifact['sha256']
        row['rendered_views'] = len(artifact['previews'])
        row['formula_error_scan'] = artifact['metadata'].get('formula_error_scan')
        row['sheets'] = artifact['metadata'].get('sheets')
    result['checks'].append(row)
    write(folder / 'verification.json', result)
for path, expected in source_hashes.items():
    assert digest(path) == expected
result['original_source_hashes_unchanged'] = True
result['original_primary_result_sha256'] = digest(parent / 'result.json')
manifests = [read(p) for p in (folder / 'workspace').rglob('source-import-compatibility.json')]
assert manifests and all(x['all_other_member_bytes_identical'] and x['xml_expanded_names_attributes_child_order_and_text_preserved'] for x in manifests)
result['all_normalization_manifests_verified'] = True
result['normalizations'] = manifests
result['completed_at'] = now()
write(folder / 'verification.json', result)
print(json.dumps({'offline_checks': len(result['checks']), 'successes': sum(x['successful'] for x in result['checks']),
                  'source_hashes_unchanged': True, 'normalizations_verified': len(manifests), 'paid_calls': 0,
                  'evidence': str(folder / 'verification.json')}))
if not all(x['successful'] for x in result['checks']):
    raise SystemExit(1)
