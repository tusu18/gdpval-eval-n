"""Original GDPval v2: durable single-dispatch API calls and a dollar budget.

Credentials are read from an owner-only file outside the repository. No retry
of an ambiguous request is automatic. Existing studies are never overwritten.
"""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evaluation_v2'
NODE = Path('/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
CONFIG = ROOT / 'config/evaluation_v2_run.json'

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text())
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x): return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
def write(p, x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('w') as f:
        f.write(json.dumps(x,indent=2,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

class BudgetStop(RuntimeError): pass

class Client:
    def __init__(self, key_file, root=OUT):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.cfg=read(CONFIG)
        self.models={m['id']:m for m in read(ROOT/'data/evaluation_v2/model-catalog.json')['models']}
        keypath=Path(key_file).resolve()
        if keypath.is_relative_to(ROOT): raise ValueError('Credential file must be outside the project')
        if keypath.stat().st_mode & 0o077: raise ValueError('Credential file must be owner-only')
        self.key=keypath.read_text().strip()
        if not self.key.startswith('sk-or-'):raise ValueError('Expected an OpenRouter key')

    @contextmanager
    def locked(self):
        with (self.root/'budget.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            yield
            fcntl.flock(lock,fcntl.LOCK_UN)

    def totals(self):
        rows=[read(p) for p in (self.root/'calls').glob('*/reservation.json')]
        known=sum(r.get('actual_cost_usd') or 0 for r in rows)
        pending=sum(r['reserved_usd'] for r in rows if r.get('actual_cost_usd') is None)
        solver=sum(r.get('actual_cost_usd') if r.get('actual_cost_usd') is not None else r['reserved_usd'] for r in rows if r['scope'].startswith('solver'))
        return {'known_cost_usd':known,'unresolved_reserved_usd':pending,'committed_usd':known+pending,'solver_committed_usd':solver,'physical_requests':len(rows),'unresolved_requests':sum(r.get('actual_cost_usd') is None for r in rows)}

    def reservation(self,body):
        pricing=self.models[body['model']]['pricing']
        images=0
        def text_only(v):
            nonlocal images
            if isinstance(v,dict):
                if v.get('type') in ('input_image','image_url'):
                    images+=1;return {'image_omitted_from_text_token_bound':True}
                return {k:text_only(w) for k,w in v.items()}
            if isinstance(v,list):return [text_only(w) for w in v]
            return v
        clean=text_only(body)
        # UTF-8 bytes conservatively bound ordinary text tokens. An image is
        # downscaled to <=1024px and reserves 40k input tokens independently.
        tokens=len(canonical(clean).encode())+2048+images*40000
        ip=max(float(pricing.get(k,0)) for k in ('prompt','input_cache_write','input_cache_write_1h'))
        op=float(pricing['completion'])
        for tier in pricing.get('overrides',[]):
            if tokens>=tier.get('min_prompt_tokens',math.inf):
                ip=max(ip,float(tier.get('prompt',0)),float(tier.get('input_cache_write',0)));op=max(op,float(tier.get('completion',0)))
        maximum=body.get('max_output_tokens',body.get('max_tokens'))
        return round((tokens*ip+maximum*op+images*float(pricing.get('image',0)))*1.05+0.002,8)

    def call(self,body,route='chat/completions',scope='judge',label='call'):
        if route not in ('chat/completions','responses'):raise ValueError('Unsupported endpoint')
        if (self.root/'BUDGET_BOUND_BREACH.json').exists():raise BudgetStop('Budget accounting requires review')
        body=json.loads(json.dumps(body))
        pricing=self.models[body['model']]['pricing']
        body.setdefault('provider',{}).update(allow_fallbacks=False,require_parameters=True,max_price={'prompt':float(pricing['prompt'])*1e6,'completion':float(pricing['completion'])*1e6})
        if len(canonical(body).encode())>12000000:raise ValueError('Request size exceeds preflight limit')
        reservation=self.reservation(body)
        with self.locked():
            totals=self.totals()
            if totals['committed_usd']+reservation>self.cfg['authorized_available_budget_usd']:
                raise BudgetStop('Request would exceed global dollar reservation ceiling')
            if scope.startswith('solver') and totals['solver_committed_usd']+reservation>self.cfg['solver_ceiling_usd']:
                raise BudgetStop('Solver ceiling reached; preserve money for grading')
            ident=uuid.uuid4().hex;folder=self.root/'calls'/ident;folder.mkdir(parents=True)
            record={'id':ident,'label':label,'scope':scope,'route':route,'model':body['model'],'reserved_usd':reservation,'actual_cost_usd':None,'status':'reserved_before_dispatch','created_at':now(),'request_sha256':hashlib.sha256(canonical(body).encode()).hexdigest()}
            write(folder/'request.json',body);write(folder/'reservation.json',record)
        started=time.monotonic()
        try:
            p=subprocess.run([str(NODE),str(ROOT/'scripts/evaluation_v2_transport.mjs')],input=json.dumps({'key':self.key,'route':route,'body':body,'timeout_ms':self.cfg['request_timeout_seconds']*1000}),capture_output=True,text=True,timeout=self.cfg['request_timeout_seconds']+15)
            if p.returncode: raise RuntimeError('Transport process failed: '+p.stderr.replace(self.key,'[REDACTED]')[:300])
            envelope=json.loads(p.stdout)
        except Exception as e:
            envelope={'status':None,'transport_error':str(e).replace(self.key,'[REDACTED]')[:300],'request_body_sent':'unknown'}
        write(folder/'response.json',envelope)
        result=envelope.get('body',{})
        usage=result.get('usage') or {}
        cost=usage.get('cost')
        if cost is None:cost=(usage.get('cost_details') or {}).get('total_cost')
        if isinstance(cost,(int,float)) and math.isfinite(cost) and cost>=0:record['actual_cost_usd']=cost
        routing=result.get('openrouter_metadata') or {}
        selected=[x for x in (routing.get('endpoints') or {}).get('available',[]) if x.get('selected') is True]
        served=selected[0] if len(selected)==1 else {}
        record.update(status='response_recorded' if envelope.get('status')==200 and not result.get('error') else 'failed_unknown_charge',http_status=envelope.get('status'),elapsed_seconds=round(time.monotonic()-started,3),completed_at=now(),response_id=result.get('id'),served_provider=result.get('provider') or served.get('provider'),served_model=served.get('model'),routing_metadata=routing or None,usage=usage)
        with self.locked():
            write(folder/'reservation.json',record)
            if record['actual_cost_usd'] is not None and record['actual_cost_usd']>reservation:
                write(self.root/'BUDGET_BOUND_BREACH.json',{'request_id':ident,'actual':cost,'reservation':reservation})
        if (self.root/'BUDGET_BOUND_BREACH.json').exists():raise BudgetStop('Observed charge exceeded conservative request reservation; inspect before continuing')
        if record['status']!='response_recorded':
            message=envelope.get('transport_error') or str(result.get('error') or envelope.get('status'))
            raise RuntimeError(f'Physical request {ident} failed; retained charge reserve; no retry: {message[:350]}')
        return result, {'call_id':ident,**record}

def image_part(path,responses):
    from PIL import Image
    from io import BytesIO
    with Image.open(path) as image:
        image=image.convert('RGB');image.thumbnail((1024,1024));b=BytesIO();image.save(b,format='JPEG',quality=80)
    url='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
    return {'type':'input_image','image_url':url,'detail':'low'} if responses else {'type':'image_url','image_url':{'url':url,'detail':'low'}}

def tools_responses(tools):
    return [{'type':'function',**x['function']} for x in tools]

def solve(client,task,model,stage='primary'):
    from evaluation_v2_workspace import Workspace,TOOLS,SYSTEM,initial_message
    ident=task['task_id']+'__'+model.replace('/','_')+'__'+stage
    folder=client.root/'runs'/ident
    if (folder/'result.json').exists():return read(folder/'result.json')
    if folder.exists():
        return {'task_id':task['task_id'],'model':model,'stage':stage,'status':'interrupted_requires_checkpoint_review','folder':str(folder)}
    folder.mkdir(parents=True);write(folder/'task.json',task)
    cfg=client.cfg;responses=model.startswith('openai/')
    ws=Workspace(task,folder/'workspace')
    # initial_message must return exactly the original prompt. A separate
    # system message describes tools, never gold or historical corrections.
    prompt=initial_message(task)
    if prompt!=task['original_prompt']:raise ValueError('Original prompt changed')
    history=[{'role':'user','content':prompt}] if responses else [{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]
    result={'task_id':task['task_id'],'occupation':task['occupation'],'model':model,'stage':stage,'started_at':now(),'status':'running','calls':[],'tool_calls':0,'artifact_paths':[],'human_acceptance':None}
    try:
        for turn in range(cfg['max_turns']):
            if responses:
                body={'model':model,'instructions':SYSTEM,'input':history,'tools':tools_responses(TOOLS),'max_output_tokens':cfg['max_output_tokens_per_turn'],'reasoning':{'effort':cfg['reasoning_effort']},'store':False}
                route='responses'
            else:
                body={'model':model,'messages':history,'tools':TOOLS,'max_tokens':cfg['max_output_tokens_per_turn'],'reasoning':{'effort':cfg['reasoning_effort']},'usage':{'include':True}}
                route='chat/completions'
            body['provider']={'allow_fallbacks':False,'require_parameters':True}
            write(folder/'checkpoint.json',{'state':'before_request','turn':turn,'history':history,'calls':result['calls']})
            data,meta=client.call(body,route,scope='solver_'+stage,label=f'{ident}:turn{turn+1}')
            result['calls'].append(meta['call_id'])
            # Acknowledge only images included in this successfully received request.
            if turn and pending_images:ws.acknowledge_images(pending_images)
            pending_images=[]
            if responses:
                outputs=data.get('output',[]);history.extend(outputs)
                calls=[{'id':x['call_id'],'function':{'name':x['name'],'arguments':x['arguments']}} for x in outputs if x.get('type')=='function_call']
                finish=(data.get('incomplete_details') or {}).get('reason')
            else:
                choice=(data.get('choices') or [{}])[0];message=choice.get('message') or {}
                history.append({k:v for k,v in message.items() if k in ('role','content','tool_calls','reasoning_details')})
                calls=message.get('tool_calls') or [];finish=choice.get('finish_reason')
            write(folder/f'turn-{turn+1:02d}.json',{'call_id':meta['call_id'],'finish_reason':finish,'tool_calls':calls,'response_id':data.get('id'),'served_provider':data.get('provider')})
            if not calls:
                result['status']='output_token_limit' if finish in ('length','max_output_tokens') else 'ended_without_submission';break
            for call in calls:
                result['tool_calls']+=1
                if result['tool_calls']>cfg['max_tool_calls']:raise RuntimeError('Tool call limit reached')
                try:
                    args=json.loads(call['function']['arguments'])
                    reply=ws.call(call['function']['name'],args)
                except Exception as e:reply={'error':str(e)[:1000]}
                text=json.dumps(reply,ensure_ascii=False)
                history.append({'type':'function_call_output','call_id':call['id'],'output':text} if responses else {'role':'tool','tool_call_id':call['id'],'content':text})
            pending_images=list(ws.image_queue);ws.image_queue.clear()
            if pending_images:
                image_content=[]
                for item in pending_images:
                    label=json.dumps({k:v for k,v in item.items() if k!='path'})
                    image_content.extend([{'type':'input_text' if responses else 'text','text':label},image_part(item['path'],responses)])
                history.append({'role':'user','content':image_content})
            write(folder/'checkpoint.json',{'state':'ready_next_turn','turn':turn+1,'history':history,'calls':result['calls'],'pending_images':pending_images})
            if ws.submitted:
                result['status']='submitted';result['submission']=ws.submitted;break
        else:result['status']='turn_limit'
    except BudgetStop as e:result.update(status='budget_limited',error=str(e))
    except Exception as e:result.update(status='infrastructure_or_adapter_failure',error=str(e)[:1500])
    task_calls=[read(p) for p in (client.root/'calls').glob('*/reservation.json') if read(p).get('label','').startswith(ident+':')]
    result['calls']=[x['id'] for x in task_calls]
    result['completed_at']=now();result['known_cost_usd']=sum(x.get('actual_cost_usd') or 0 for x in task_calls)
    result['unresolved_calls']=sum(x.get('actual_cost_usd') is None for x in task_calls)
    result['unresolved_reserved_usd']=sum(x['reserved_usd'] for x in task_calls if x.get('actual_cost_usd') is None)
    result['workspace']=str(folder/'workspace');write(folder/'result.json',result)
    return result

def freeze(development=False):
    names=['config/evaluation_v2_run.json','config/evaluation_v2_grader.json','data/evaluation_v2/tasks.jsonl','data/evaluation_v2/effective-inputs.jsonl','data/evaluation_v2/effective-inputs-manifest.json','data/evaluation_v2/task-contracts.json','data/evaluation_v2/model-catalog.json','data/evaluation_v2/rubrics.json','data/evaluation_v2/external_sources/manifest.json']
    # Grading orchestration has a separate pre-execution freeze. Its rubric
    # and semantic validator are already fixed here before primary outputs.
    names += ['scripts/'+name for name in ('prepare_evaluation_v2.py','run_evaluation_v2.py','evaluation_v2_transport.mjs','evaluation_v2_workspace.py','evaluation_v2_engine.mjs','evaluation_v2_grading.py')]
    files={n:digest(ROOT/n) for n in names if (ROOT/n).is_file()}
    dest=OUT/'development-freezes'/(uuid.uuid4().hex+'.json') if development else OUT/'freeze.json'
    if dest.exists():
        old=read(dest)
        if old['files']!=files:raise RuntimeError('Frozen inputs changed; record a new protocol revision before further runs')
        return old
    x={'created_at':now(),'development':development,'files':files,'models_access':'Catalog verified; successful paid calls verify runtime access','human_labels':'Five historical cases are development only; new-run acceptance pending'};write(dest,x);return x

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','status']);p.add_argument('--key-file');p.add_argument('--task');p.add_argument('--model');p.add_argument('--stage',default='primary',choices=['primary','smoke','supplemental']);a=p.parse_args()
    if a.action=='freeze':print(json.dumps(freeze(),indent=2));return
    if a.action=='status':
        rows=[read(x) for x in (OUT/'runs').glob('*/result.json')]
        print(json.dumps([{'task':x['task_id'][:8],'model':x['model'],'stage':x['stage'],'status':x['status'],'cost':x.get('known_cost_usd')} for x in rows],indent=2));return
    client=Client(a.key_file);freeze(development=a.stage=='smoke')
    source=ROOT/'data/evaluation_v2/effective-inputs.jsonl'
    if not source.exists():source=ROOT/'data/evaluation_v2/tasks.jsonl'
    tasks=[json.loads(line) for line in source.read_text().splitlines()]
    if a.task:tasks=[t for t in tasks if t['task_id'].startswith(a.task)]
    if not tasks:raise ValueError('No original task matches selector')
    for task in tasks:
        result=solve(client,task,a.model or client.cfg['primary_model'],a.stage)
        print(json.dumps({'task':task['task_id'][:8],'model':result['model'],'status':result['status'],'cost':result.get('known_cost_usd'),'budget':client.totals()}),flush=True)
        if result['status'] in ('budget_limited','infrastructure_or_adapter_failure'):break

if __name__=='__main__':main()
