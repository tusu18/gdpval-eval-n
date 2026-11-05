"""Freeze the twenty new execution inputs and method before solver contexts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    target = ROOT / 'output/evaluation_v4/freeze.json'
    paths = [ROOT / x for x in (
        'config/evaluation_v4_run.json', 'data/evaluation_v4/tasks.jsonl',
        'data/evaluation_v4/execution-tasks.jsonl', 'data/evaluation_v4/selection-freeze.json',
        'data/evaluation_v4/project-rubrics.json', 'data/evaluation_v4/sources-manifest.json',
        'docs/evaluation_v4/execution-protocol.txt', 'docs/evaluation_v4/judge-instructions.txt',
        'docs/evaluation_v4/solver-instructions.txt',
        'docs/evaluation_v4/source-audit.json', 'docs/evaluation_v4/artificial-analysis-method-addendum.txt',
        'scripts/evaluation_v4_workspace.py', 'scripts/evaluation_v3_workspace.py',
        'scripts/evaluation_v2_workspace.py', 'scripts/evaluation_v2_engine.mjs',
        'scripts/prepare_evaluation_v4_execution.py', 'scripts/freeze_evaluation_v4.py',
        'scripts/prepare_evaluation_v4_judge_packet.py', 'scripts/validate_evaluation_v4_assessments.py',
        'output/evaluation_v4/budget-before.json',
        'scripts/evaluation_v4_harness.md', 'scripts/test_evaluation_v4_harness.py',
        'output/evaluation_v4/preflight/native-capabilities-v3/test-summary.json')]
    paths += list((ROOT / 'scripts').glob('evaluation_v4_native*'))
    tasks = [json.loads(x) for x in (ROOT / 'data/evaluation_v4/execution-tasks.jsonl').read_text().split('\n') if x.strip()]
    assert len(tasks) == len({t['task_id'] for t in tasks}) == 20
    for task in tasks:
        prompt_path = ROOT / 'data/evaluation_v4/solver' / task['task_id'] / 'prompt.txt'
        assert prompt_path.read_text() == task['prompt']
        paths += [prompt_path, prompt_path.with_name('task.json')]
        for ref in task['references']:
            p = ROOT / ref['local_path']
            assert sha(p) == ref['sha256']
            paths.append(p)
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths)) if p.is_file()}
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise RuntimeError('Missing freeze inputs: ' + ', '.join(missing))
    if target.exists():
        assert json.loads(target.read_text())['files'] == frozen, 'Frozen inputs changed; document amendment'
        print('V4 freeze verified')
        return
    if list((ROOT / 'output/evaluation_v4/solver').glob('*/state.json')):
        raise RuntimeError('Cannot claim pre-run freeze after solver states exist')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(), 'files': frozen,
        'new_solver_runs_at_freeze': 0, 'fresh_human_reviews_at_freeze': 0,
        'rubric_is_project_defined_not_official_gdpval_scoring': True}, indent=2) + '\n')
    print('Frozen before new solver runs:', len(frozen), 'files')

if __name__ == '__main__':
    main()
