"""Record actual in-app dispatch/completion observations; never call a model."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','complete']);p.add_argument('role',choices=['solver','judge']);p.add_argument('task');p.add_argument('--agent');a=p.parse_args()
    tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v4/execution-tasks.jsonl').read_text().split('\n') if x.strip()]
    matches=[t['task_id'] for t in tasks if t['task_id'].startswith(a.task)]
    if len(matches)!=1:raise ValueError('Ambiguous task')
    tid=matches[0];path=ROOT/'output/evaluation_v4/execution-manifest.json';d=json.loads(path.read_text())
    rows=d[a.role+'_agents'];existing=next((r for r in rows if r['task_id']==tid),None)
    now=datetime.now(timezone.utc).isoformat()
    if a.action=='start':
        if existing:raise ValueError('Task already dispatched for this role')
        if not a.agent:raise ValueError('Provide actual returned agent name')
        rows.append({'task_id':tid,'agent_name':a.agent,'requested_model':'gpt-6.1-sol' if a.role=='solver' else 'gpt-6-astra',
            'fork_turns':'none','dispatched_at_recorded_utc':now,'status':'running',
            'exposed_inputs':'original task and sources plus neutral tool instructions' if a.role=='solver' else 'author-hidden task/source/native-output packet and frozen rubric; no builder code or prior labels',
            'served_model_snapshot':None,'in_app_cost_usd':None,'new_openrouter_cost_usd':0,
            'image_delivery_wrapper_requested':'scripts/evaluation_v4_delivery.py' if a.role=='solver' and (ROOT/'scripts/evaluation_v4_delivery.py').exists() else None})
    else:
        if not existing:raise ValueError('No dispatch record')
        output=ROOT/'output/evaluation_v4'
        evidence=output/'solver'/tid/'submission_manifest.json' if a.role=='solver' else output/'assessments'/f'{tid}.json'
        if not evidence.exists():raise ValueError('No completion evidence')
        existing.update(status='submitted' if a.role=='solver' else 'assessment_recorded',completion_observed_at=now,evidence_path=str(evidence.relative_to(ROOT)))
    path.write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({'task_id':tid,'role':a.role,'action':a.action}))

if __name__=='__main__':main()
