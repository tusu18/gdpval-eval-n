"""Continue unattempted original tasks with a recorded budget-only amendment.

No existing result is replaced or retried. Solver implementation remains frozen.
"""
import argparse
import json
from run_evaluation_v2 import Client,ROOT,OUT,read,write,digest,freeze,solve,now

def amended_client(key_file):
    client=Client(key_file)
    path=ROOT/'config/evaluation_v2_budget_amendment.json';amend=read(path)
    client.cfg['authorized_available_budget_usd']=amend['authorized_total_usd']
    client.cfg['solver_ceiling_usd']=amend['solver_ceiling_usd']
    return client

def main():
    p=argparse.ArgumentParser();p.add_argument('--key-file',required=True);p.add_argument('--model');p.add_argument('--stage',default='primary',choices=['primary','supplemental']);p.add_argument('--task');a=p.parse_args()
    freeze();client=amended_client(a.key_file);model=a.model or client.cfg['primary_model']
    tasks=[json.loads(l) for l in (ROOT/'data/evaluation_v2/effective-inputs.jsonl').read_text().splitlines()]
    if a.task:tasks=[t for t in tasks if t['task_id'].startswith(a.task)]
    queue=[t for t in tasks if not (OUT/'runs'/(t['task_id']+'__'+model.replace('/','_')+'__'+a.stage)).exists()]
    record={'created_at':now(),'task_ids':[t['task_id'] for t in queue],'model':model,'stage':a.stage,'script_sha256':digest(__file__),'budget_amendment_sha256':digest(ROOT/'config/evaluation_v2_budget_amendment.json'),'primary_freeze_sha256':digest(OUT/'freeze.json'),'rule':'Only previously unattempted task/model/stage combinations; no silent retries'}
    write(OUT/'dispatches'/(record['created_at'].replace(':','-')+'.json'),record)
    consecutive_failures=0
    for task in queue:
        r=solve(client,task,model,a.stage)
        print(json.dumps({'task':task['task_id'][:8],'model':model,'status':r['status'],'cost':r.get('known_cost_usd'),'budget':client.totals()}),flush=True)
        consecutive_failures=consecutive_failures+1 if r['status']=='infrastructure_or_adapter_failure' else 0
        if r['status']=='budget_limited' or consecutive_failures>=2:break

if __name__=='__main__':main()
