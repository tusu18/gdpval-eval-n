"""Prepare five new, pinned GDPval tasks without reading gold/rubric columns."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/evaluation_v3'
REVISION = '11e7900cdcac61bc4daf59e65feb238acda98fbf'
SELECTED = {
    '7b08cd4d-df60-41ae-9102-8aaa49306ba2': 'Tour profit and loss',
    '7d7fc9a7-21a7-4b83-906f-416dea5ad04f': 'Prepaid expense amortization',
    '17111c03-aac7-45c2-857d-c06d8223d6ad': 'Cleanup schedule and disruption memo',
    'c44e9b62-7cd8-4f72-8ad9-f8fbddb94083': 'Staffing reduction package',
    '4520f882-715a-482d-8e87-1cb3cbdfe975': 'Contract based musician payroll',
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    rows = [json.loads(line) for line in (DATA/'candidate-source.jsonl').read_text().split('\n') if line.strip()]
    previous = {json.loads(line)['task_id'] for line in (ROOT/'data/evaluation_v2/tasks.jsonl').read_text().split('\n') if line.strip()}
    assert not set(SELECTED) & previous
    chosen = sorted((r for r in rows if r['task_id'] in SELECTED), key=lambda r: r['task_id'])
    assert len(chosen) == 5
    tasks = []
    for row in chosen:
        refs = []
        for relative in row['reference_files']:
            if not relative.startswith('reference_files/') or '..' in Path(relative).parts:
                raise ValueError('Unexpected reference path')
            target = DATA/'sources'/relative
            url = f'https://huggingface.co/datasets/openai/gdpval/resolve/{REVISION}/{quote(relative, safe="/")}'
            if args.download and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with urlopen(url, timeout=90) as response:
                    payload = response.read()
                target.write_bytes(payload)
            if not target.exists():
                raise ValueError('Missing source; use --download')
            refs.append({'name': target.name, 'local_path': str(target.relative_to(ROOT)), 'sha256': sha(target), 'bytes': target.stat().st_size, 'url': url})
        task = {**row, 'references': refs}
        tasks.append(task)
        packet = DATA/'solver'/row['task_id']
        save(packet/'task.json', task)
        (packet/'prompt.txt').write_text(row['prompt'])
    (DATA/'tasks.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=True)+'\n' for r in tasks))
    save(DATA/'selection.json', {
        'dataset': 'openai/gdpval', 'revision': REVISION,
        'original_parquet_sha256': sha(ROOT/'research/train-00000-of-00001.parquet'),
        'new_unique_tasks': 5, 'previous_unique_tasks': 15, 'combined_unique_tasks': 20,
        'selection': [{'task_id': t['task_id'], 'title': SELECTED[t['task_id']], 'occupation': t['occupation'], 'reference_count': len(t['references']), 'prompt_sha256': hashlib.sha256(t['prompt'].encode()).hexdigest()} for t in tasks],
        'rule': 'Purposive, outcome-blind selection from three additional occupations: two accounting, two administrative services, one financial management. Closed source packets, native deliverables, and testable arithmetic, consistency or rule execution requirements. Prompts screened before outputs; source issues retained rather than repaired silently.',
        'not_representative': 'Partial coverage (2/5, 2/5, 1/5) of the new occupations. Neither random sampling nor full occupational coverage. No population rates or model ranking.',
        'original_prompts_modified': False, 'gold_or_official_rubric_used_for_selection': False,
        'api_requests': 0, 'model_runs_at_selection': 0,
        'execution_cohort': 'Separate in-app GPT-6.1 Sol cohort; not pooled with v2 OpenRouter outcomes.',
        'timezone': 'America/New_York', 'task_today': '2026-11-04',
    })
    print(json.dumps({'selected': len(tasks), 'references': sum(len(t['references']) for t in tasks), 'downloaded': True}))

if __name__ == '__main__':
    main()
