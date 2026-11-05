"""Prepare the remaining original tasks and hash immutable supplied sources.

No inference, gold-column access, source repair or evaluator answers. Download
failures remain recorded; no selected task is silently dropped.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/evaluation_v4'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');parser.add_argument('--extract',action='store_true');args=parser.parse_args()
    selection=json.loads((DATA/'selection.json').read_text())
    roster=json.loads((DATA/'task-roster.json').read_text());pending={r['task_id'] for r in roster if r['status']=='not_run'}
    catalog=[json.loads(s) for s in (DATA/'tasks.jsonl').read_text().split('\n') if s.strip()]
    selected=[r for r in catalog if r['task_id'] in pending]
    assert len(selected)==20 and len({r['task_id'] for r in selected})==20
    jobs=[]
    for task in selected:
        for relative,url in zip(task['reference_files'],task['reference_urls']):
            if not relative.startswith('reference_files/') or '..' in Path(relative).parts:raise ValueError('Unsafe source path')
            jobs.append((task['task_id'],relative,url))
    assert len(jobs)==44
    def fetch(job):
        tid,relative,url=job;target=DATA/'sources'/relative
        result={'task_id':tid,'source_relative_path':relative,'name':target.name,'local_path':str(target.relative_to(ROOT)),'url':url,'revision':selection['revision'],'checked_at_utc':datetime.now(timezone.utc).isoformat()}
        try:
            if target.exists():result['acquisition']='existing_hashed_file'
            elif args.download:
                target.parent.mkdir(parents=True,exist_ok=True)
                request=Request(url,headers={'User-Agent':'Turing-GDPval-Research/1.0'})
                with urlopen(request,timeout=120) as response:payload=response.read(100_000_001)
                if len(payload)>100_000_000:raise ValueError('Reference exceeded 100MB safeguard')
                temporary=target.with_suffix(target.suffix+'.download');temporary.write_bytes(payload);temporary.replace(target)
                result['acquisition']='downloaded_pinned_original'
            else:raise FileNotFoundError('Reference not downloaded')
            result.update(status='available',sha256=sha(target),bytes=target.stat().st_size)
            if args.extract:
                from evaluation_v2_workspace import extract_native
                try:
                    extraction=extract_native(target,target.name)
                    path=DATA/'source-extractions'/tid/(target.name+'.json');save(path,extraction)
                    result.update(extraction_status='complete',extraction_path=str(path.relative_to(ROOT)),text_characters=len(extraction['text']),native_units=len(extraction['units']),source_pages=len(extraction.get('pages',[])),source_sheets=extraction.get('sheets'))
                    if target.suffix.lower()=='.pdf' and not extraction['text'].strip():result['extraction_warning']='No text extracted; source needs visual inspection/OCR before judging.'
                except Exception as exc:result.update(extraction_status='failed',extraction_error=f'{type(exc).__name__}: {exc}')
            return result
        except Exception as exc:
            result.update(status='unavailable',error=f'{type(exc).__name__}: {exc}')
            return result
    with ThreadPoolExecutor(max_workers=4) as executor:downloads=list(executor.map(fetch,jobs))
    by_task={tid:[r for r in downloads if r['task_id']==tid] for tid in pending}
    execution=[]
    for task in selected:
        records=by_task[task['task_id']]
        refs=[{k:r[k] for k in ('name','local_path','url','sha256','bytes') if k in r} for r in records]
        row={**task,'references':refs,'task_today':'2026-11-05','timezone':'America/New_York'}
        execution.append(row)
        packet=DATA/'solver'/task['task_id'];save(packet/'task.json',row);(packet/'prompt.txt').write_text(task['prompt'])
        assert (packet/'prompt.txt').read_text()==task['prompt']
    (DATA/'execution-tasks.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=True)+'\n' for t in execution))
    save(DATA/'sources-manifest.json',{'schema':'original-source-acquisition-v4-1','created_at_utc':datetime.now(timezone.utc).isoformat(),'revision':selection['revision'],'selected_task_count':20,'source_file_count':44,'available':sum(r['status']=='available' for r in downloads),'missing':sum(r['status']!='available' for r in downloads),'records':downloads,'original_prompts_modified':False,'gold_or_official_rubric_accessed':False,'new_model_calls':0,'new_api_spend_usd':0,'extraction_note':'Native extraction is not full visual preflight or proof of business consistency.'})
    print(json.dumps({'tasks':20,'references':44,'available':sum(r['status']=='available' for r in downloads),'unavailable':[{'task_id':r['task_id'],'name':r['name'],'error':r.get('error')} for r in downloads if r['status']!='available'],'extraction_failures':[{'name':r['name'],'error':r.get('extraction_error')} for r in downloads if r.get('extraction_status')=='failed']}))

if __name__=='__main__':main()
