"""Freeze input, method and project rubric hashes before solver execution."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    target=ROOT/'output/evaluation_v3/freeze.json'
    paths=[ROOT/x for x in ['config/evaluation_v3_run.json','data/evaluation_v3/tasks.jsonl','data/evaluation_v3/selection.json','data/evaluation_v3/project-rubrics.json','docs/evaluation_v3/protocol.txt','docs/evaluation_v3/selection-screening.json','scripts/prepare_evaluation_v3.py','scripts/evaluation_v3_workspace.py','scripts/preflight_evaluation_v3.py','scripts/evaluation_v2_workspace.py','scripts/evaluation_v2_engine.mjs','output/evaluation_v3/preflight.json']]
    tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v3/tasks.jsonl').read_text().split('\n') if x.strip()]
    paths += [ROOT/'docs/evaluation_v3/judge-instructions.txt']
    paths += [ROOT/r['local_path'] for t in tasks for r in t['references']]
    paths += [ROOT/'data/evaluation_v3/solver'/t['task_id']/'prompt.txt' for t in tasks]
    frozen={str(p.relative_to(ROOT)):sha(p) for p in paths}
    if target.exists():
        old=json.loads(target.read_text())
        if old['files']!=frozen:
            raise ValueError('Frozen method/input changed; document an amendment instead')
        print('Freeze verified')
        return
    if list((ROOT/'output/evaluation_v3/solver').glob('*/state.json')):
        raise ValueError('Cannot create pre-run freeze after solver state exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'files':frozen,'solver_runs_at_freeze':0,'human_reviews_at_freeze':0,'project_rubric_not_official_gdpval_scoring':True},indent=2)+'\n')
    print('Frozen before solver runs:',len(frozen),'files')

if __name__=='__main__':
    main()
