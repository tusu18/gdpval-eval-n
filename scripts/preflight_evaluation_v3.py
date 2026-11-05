"""Check each pinned native input can be extracted and rendered before solving."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from evaluation_v3_workspace import Workspace, write

ROOT=Path(__file__).resolve().parents[1]

def check(task):
    workspace=Workspace(task,ROOT/'output/evaluation_v3/preflight'/task['task_id'])
    rows=[]
    for name in workspace.sources:
        text=workspace.call('read_file',{'path':name,'limit':20000})
        visual=workspace.call('view_source',{'path':name,'pages':[1]})
        rows.append({'name':name,'source':workspace.sources[name],
            'text_extracted':not bool(text.get('error')), 'text_characters':text.get('total_characters'),
            'rendered':not bool(visual.get('error')), 'total_views':visual.get('total_views'),
            'error':text.get('error') or visual.get('error'),
            'business_consistency':'not_assessed_by_preflight'})
    result={'task_id':task['task_id'],'inputs':rows,'all_readable':all(x['text_extracted'] and x['rendered'] for x in rows)}
    write(ROOT/'output/evaluation_v3/preflight'/task['task_id']/'preflight.json',result)
    print(json.dumps({'task_id':task['task_id'],'all_readable':result['all_readable'],'inputs':len(rows)}),flush=True)
    return result

if __name__=='__main__':
    tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v3/tasks.jsonl').read_text().split('\n') if x.strip()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(check,tasks))
    write(ROOT/'output/evaluation_v3/preflight.json',rows)
