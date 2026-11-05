"""Package the follow-up run's deliverables for OpenAI's official GDPval auto-grader.

Format follows inspect_evals/gdpval (UK AISI): a Hugging Face dataset repo holding the openai/gdpval table
(data/train-00000-of-00001.parquet) with two added columns, deliverable_text and deliverable_files, plus a
deliverable_files/<task_id>/ folder per task. One repo per solver. Only unmodified gold tasks are included
(conflict variants are not GDPval tasks). The grader compares each deliverable against the expert deliverable
(GPT-5-based, three grades per submission, free): https://evals.openai.com/gdpval/grading

Needs only huggingface_hub and pyarrow (no pandas, no datasets).
  python3 scripts/build_gdpval_submission.py
  hf auth login
  hf upload <hf-username>/<folder name> output/gdpval_submission/<folder name> --repo-type dataset
  # then submit each repo id at https://evals.openai.com/gdpval/grading
"""
import json, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'output/study_v3'; INST = ROOT / 'data/study_v3/instances'; OUT = ROOT / 'output/gdpval_submission'
REVISION = '11e7900cdcac61bc4daf59e65feb238acda98fbf'
read = lambda p: json.loads(Path(p).read_text())


def source_table():
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, hf_hub_download
    files = [f for f in HfApi().list_repo_files('openai/gdpval', repo_type='dataset', revision=REVISION) if f.endswith('.parquet')]
    if not files: raise SystemExit('no parquet in openai/gdpval')
    local = hf_hub_download('openai/gdpval', files[0], repo_type='dataset', revision=REVISION)
    return pq.read_table(local), files[0]


def main():
    import pyarrow as pa, pyarrow.parquet as pq
    table, src_name = source_table(); cols = table.to_pydict(); n = table.num_rows
    task_ids = cols['task_id']
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%Splus00-00')
    runs = [read(p) for p in sorted((V3 / 'solver_runs').glob('*.json'))]
    manifest = {}
    for model in ('sonnet', 'opus'):
        folder = OUT / f'{ts}_gdpval-{model}'; (folder / 'data').mkdir(parents=True, exist_ok=True)
        text = [''] * n; dfiles = [[] for _ in range(n)]; rows = []
        for r in runs:
            if r.get('status') != 'submitted' or r['model'] != model or r['variant'] != 'original': continue
            inst = read(INST / (r['instance_id'] + '.json')); tid = inst.get('source_task_id') or inst.get('task_id')
            if tid not in task_ids: print('skip', r['run_id'], 'task not in table', tid); continue
            i = task_ids.index(tid); dest = folder / 'deliverable_files' / tid; dest.mkdir(parents=True, exist_ok=True); files = []
            for o in r['outputs']:
                src = V3 / 'claudecode' / r['run_id'] / 'outputs' / o['name']
                if src.is_file(): shutil.copy(src, dest / o['name']); files.append(f'deliverable_files/{tid}/{o["name"]}')
            text[i] = (r.get('final_message') or '').strip()[:2000]; dfiles[i] = files
            rows.append({'task_id': tid, 'run_id': r['run_id'], 'files': files})
        out = table.append_column('deliverable_text', pa.array(text, pa.string())).append_column('deliverable_files', pa.array(dfiles, pa.list_(pa.string())))
        pq.write_table(out, folder / 'data' / 'train-00000-of-00001.parquet')
        (folder / 'README.md').write_text(f'# GDPval submission: anthropic/claude-{model}-5.5 via Claude Code CLI\n\n{len(rows)} unmodified gold tasks from three occupations; table = openai/gdpval@{REVISION[:7]} ({src_name}) + deliverable_text + deliverable_files. Built {ts} by scripts/build_gdpval_submission.py.\n')
        manifest[model] = {'folder': str(folder.relative_to(ROOT)), 'tasks': rows}
        print(f'{model}: {len(rows)} tasks -> {folder.name}')
        print(f'  hf upload <hf-username>/{folder.name} {folder} --repo-type dataset')
    (OUT / 'manifest.json').write_text(json.dumps({'built_at': ts, 'submissions': manifest}, indent=1))


if __name__ == '__main__':
    main()
