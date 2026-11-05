"""A bounded five-model native-file DEVELOPMENT comparison via OpenRouter.

Credentials are read once with getpass and stay in memory. No hidden answer map
enters solver context. No automatic retries, model fallbacks or training calls.
"""
import argparse,base64,copy,getpass,hashlib,json,os,random,threading,time,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from native_file_workflow import ROOT,NativeWorkspace,TOOLS,SYSTEM,initial_message,write,sha
from check_evidence_upgrade import budget_status

OUT=ROOT/'output/native_workflow_01';CONFIG=ROOT/'config/native_workflow_01.json';LOCK=threading.Lock()
MODELS=['openai/gpt-6-astra','anthropic/claude-opus-5.5','google/gemini-4-argon','meta/muse-wonder','moonshotai/kimi-k3.1-pro']
FAMILIES=['original_supplier_landed_cost','supplier_exit','sourcing_approvals','change_control']
def utc():return datetime.now(timezone.utc).isoformat()
def api(key,route,body=None):
    request=urllib.request.Request('https://openrouter.ai/api/v1/'+route,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
       headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','X-Title':'Turing native workflow diagnostic'})
    try:
        with urllib.request.urlopen(request,timeout=180) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        raw=e.read().decode(errors='replace').replace(key,'[REDACTED]')
        raise RuntimeError(f'OpenRouter HTTP {e.code}: {raw[:1500]}') from None

def prepare():
    if CONFIG.exists():return json.loads(CONFIG.read_text())
    catalog=json.loads((OUT/'openrouter_catalog_2026-11-04.json').read_text())['data'];by_id={r['id']:r for r in catalog}
    models=[]
    for mid in MODELS:
        r=by_id[mid]
        if 'tools' not in r['supported_parameters'] or 'image' not in r['architecture']['input_modalities'] or 'high' not in r.get('reasoning',{}).get('supported_efforts',[]):raise ValueError('Requested common tools/image/high configuration unavailable: '+mid)
        models.append({k:r.get(k) for k in ['id','canonical_slug','pricing','supported_parameters','architecture','reasoning']})
    jobs=[{'family_id':f,'instance_id':f+'__conflict','model':m,'repeat':1,'run_id':f+'__'+m.replace('/','_')+'__native_r1'} for f in FAMILIES for m in MODELS]
    random.Random(20261104).shuffle(jobs)
    paths=[ROOT/'data/evidence_upgrade_01/solver'/f'{f}__conflict.json' for f in FAMILIES]
    paths += [ROOT/'scripts'/p for p in ['native_file_engine.mjs','native_file_workflow.py','run_native_models.py','workflow_workspace.py','evidence_grader.py']]
    cfg={'id':'native-workflow-01','created_at':utc(),'status':'frozen_development_comparison',
      'authorization':{'date_local':'2026-11-04','api_spend_limit':'no fixed cap, explicitly confirmed by user','bounded_scope':'20 attempts: four development tasks per model; no automatic expansion','prior_campaign_cap_superseded':True},
      'models':models,'jobs':jobs,'system':SYSTEM,'tools':TOOLS,'max_turns':16,'max_tool_calls':80,'max_tokens':10000,
      'reasoning_effort':'high','max_request_bytes':8000000,'provider_price_ceiling_per_million':{'prompt':10,'completion':50},
      'input_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths},'seed':20261104,'seed_scope':'run order only',
      'interpretation':'Four selected/inspected development families, conflict condition only, one attempt per model. No independent domain review, held-out transfer, model ranking or causal prompt-effect claim.',
      'metrics':['native submission completion','current-revision inspection and image exposure','tool/render errors','page constraints','actual provider cost','human acceptance and consequential error pending review'],
      'source_limits':'Inputs use the adapted text/table extracts already defined by the task. Native output tools are shared; spreadsheet engine is artifact-tool, not Excel desktop. Equal limits do not establish equal internal compute.',
      'prior_api_spend':budget_status()['charged_or_reserved_usd']}
    write(CONFIG,cfg);return cfg

def image_message(items):
    from PIL import Image
    import io
    content=[{'type':'text','text':'Rendered views requested through view_page. Inspect these exact revisions; the images contain no grading annotations.'}]
    for item in items:
        im=Image.open(item['path']).convert('RGB');im.thumbnail((1600,1800));buf=io.BytesIO();im.save(buf,format='JPEG',quality=85)
        content.extend([{'type':'text','text':f"{item['filename']} revision {item['revision']} view {item['page']}"},
                        {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}}])
    return {'role':'user','content':content}

def one(job,cfg,key):
    dest=OUT/'runs'/(job['run_id']+'.json')
    if dest.exists():return json.loads(dest.read_text())
    task=json.loads((ROOT/'data/evidence_upgrade_01/solver'/(job['instance_id']+'.json')).read_text())
    env=NativeWorkspace(task,OUT/'workspaces'/job['run_id'])
    record={**job,'started_at':utc(),'status':'running','calls':[],'tool_events':[],'image_exposures':[],'task_sha256':cfg['input_hashes']['data/evidence_upgrade_01/solver/'+job['instance_id']+'.json']}
    messages=[{'role':'system','content':cfg['system']},{'role':'user','content':initial_message(task)}]
    count=0;start=time.monotonic();pending_images=[];write(dest,record)
    try:
        for turn in range(cfg['max_turns']):
            body={'model':job['model'],'messages':messages,'tools':cfg['tools'],'max_tokens':cfg['max_tokens'],
                  'reasoning':{'effort':cfg['reasoning_effort']},'provider':{'allow_fallbacks':False,'require_parameters':True,'max_price':cfg['provider_price_ceiling_per_million']}}
            if len(json.dumps(body).encode())>cfg['max_request_bytes']:raise ValueError('request_size_limit')
            with LOCK:
                ledger_path=OUT/'ledger.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
                lid=len(ledger);ledger.append({'id':lid,'run_id':job['run_id'],'turn':turn,'status':'dispatched_cost_pending','started_at':utc(),'actual_cost_usd':None});write(ledger_path,ledger)
            try:response=api(key,'chat/completions',body)
            except Exception as e:
                with LOCK:
                    ledger=json.loads(ledger_path.read_text());ledger[lid].update(status='provider_error_cost_unresolved',error=str(e)[:500]);write(ledger_path,ledger)
                raise
            usage=response.get('usage',{});cost=usage.get('cost')
            env.acknowledge_images(pending_images);record['image_exposures']+=pending_images;pending_images=[]
            with LOCK:
                ledger=json.loads(ledger_path.read_text());ledger[lid].update(status='actual' if type(cost) in (float,int) and cost>=0 else 'reported_cost_missing',actual_cost_usd=cost,generation_id=response.get('id'),provider=response.get('provider'));write(ledger_path,ledger)
            message=response['choices'][0]['message'];calls=message.get('tool_calls') or []
            # Continuation-only reasoning state stays in memory; observable transcript omits hidden reasoning.
            assistant={'role':'assistant','content':message.get('content')}
            for field in ('tool_calls','reasoning_details'):
                if message.get(field):assistant[field]=message[field]
            messages.append(assistant)
            record['calls'].append({'turn':turn,'generation_id':response.get('id'),'returned_model':response.get('model'),'provider':response.get('provider'),'usage':usage,
                'assistant_content':message.get('content'),'tool_calls':calls,'finish_reason':response['choices'][0].get('finish_reason')})
            if not calls:
                record['status']='ended_without_submission';break
            if len(calls)>12 or count+len(calls)>cfg['max_tool_calls']:raise ValueError('tool_call_limit')
            for call in calls:
                count+=1
                try:args=json.loads(call['function']['arguments'])
                except (ValueError,TypeError):args=None
                reply=env.call(call['function']['name'],args)
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(reply,ensure_ascii=False)})
            if env.image_queue:
                messages.append(image_message(env.image_queue));pending_images=env.image_queue;env.image_queue=[]
            record['tool_events']=env.events;write(dest,record)
            with LOCK:print(json.dumps({'model':job['model'],'family':job['family_id'],'turn':turn+1,'tools':count,'submitted':bool(env.submitted)}),flush=True)
            if env.submitted:record['status']='submitted';record['submission']=env.submitted;break
        else:record['status']='turn_limit'
    except Exception as e:record.update(status='execution_error',error=str(e).replace(key,'[REDACTED]')[:1500])
    record.update(tool_events=env.events,finished_at=utc(),elapsed_seconds=time.monotonic()-start,
      reported_api_cost_usd=sum(c['usage'].get('cost') or 0 for c in record['calls']))
    write(dest,record)
    return record

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    cfg=prepare()
    for rel,h in cfg['input_hashes'].items():
        if sha(ROOT/rel)!=h:raise SystemExit('Frozen input changed: '+rel)
    smoke=json.loads((OUT/'engineering_smoke/results.json').read_text())
    if smoke['status']!='local_engine_checks_pass':raise SystemExit('Local engine smoke failed')
    if not args.execute:print(json.dumps({'prepared_attempts':len(cfg['jobs']),'models':len(cfg['models']),'paid_calls':0}));return
    if not 1<=args.workers<=2:raise SystemExit('Use 1-2 workers to keep native render jobs isolated.')
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ')
    api(key,'key')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(one,j,cfg,key) for j in cfg['jobs']]
        for f in as_completed(futures):
            r=f.result();print(json.dumps({'finished':r['run_id'],'status':r['status'],'cost':r.get('reported_api_cost_usd')}),flush=True)
    key=None
    rows=[json.loads(p.read_text()) for p in (OUT/'runs').glob('*.json')]
    ledger=json.loads((OUT/'ledger.json').read_text())
    summary={'attempts':len(rows),'submitted':sum(r['status']=='submitted' for r in rows),
       'reported_new_api_cost_usd':sum(x['actual_cost_usd'] or 0 for x in ledger),
       'unresolved_charge_records':sum(x['status']!='actual' for x in ledger),
       'prior_api_spend_usd':cfg['prior_api_spend'],'human_acceptance':None,'consequential_error_rate':None,'model_selected':None,
       'interpretation':cfg['interpretation']}
    write(OUT/'run_summary.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
