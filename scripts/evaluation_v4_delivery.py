"""Transport-only wrapper: deliver at most four queued image records at a time.

Frozen workspace implementation, native files and visual coverage stay intact.
Acknowledgement still uses the original workspace's exact-record validation.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAX_IMAGES=4

def main():
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--area',choices=['solver','preflight'],default='solver')
    p.add_argument('--request');p.add_argument('--ack');p.add_argument('--describe',action='store_true');p.add_argument('--queue',action='store_true')
    a=p.parse_args()
    if a.queue:
        tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v4/execution-tasks.jsonl').read_text().split('\n') if x.strip()]
        found=[t for t in tasks if t['task_id'].startswith(a.task)]
        if len(found)!=1:raise ValueError('Ambiguous task')
        state=json.loads((ROOT/'output/evaluation_v4'/a.area/found[0]['task_id']/'state.json').read_text())
        result={'queued_images':state.get('image_queue',[])}
    else:
        args=[sys.executable,str(ROOT/'scripts/evaluation_v4_workspace.py'),'--task',a.task,'--area',a.area]
        for key in ('request','ack'):
            if getattr(a,key):args += ['--'+key,getattr(a,key)]
        if a.describe:args.append('--describe')
        completed=subprocess.run(args,capture_output=True,text=True,cwd=ROOT)
        if completed.stderr:print(completed.stderr,file=sys.stderr,end='')
        if completed.returncode:print(completed.stdout,end='');raise SystemExit(completed.returncode)
        result=json.loads(completed.stdout)
    if 'queued_images' in result:
        total=len(result['queued_images']);result['queued_images']=result['queued_images'][:MAX_IMAGES]
        result.update(queued_images_total=total,image_delivery_limit=MAX_IMAGES,
            delivery_instruction='Display only this batch, acknowledge exact displayed records through --ack, then use --queue for the next batch. Never acknowledge unseen images. Full coverage remains required.')
    if a.describe:result['transport_delivery_policy']='Use this wrapper for requests and --queue; at most four image records returned per call. Native workspace and full coverage are unchanged.'
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
