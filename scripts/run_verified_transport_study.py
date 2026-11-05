"""Prespecified transport amendment before any paired outcome; no media thinning.

Keep the earlier upload failures. Retry an identical failed network request once,
record the extra unresolved charge, never retry a model/HTTP outcome or a tool.
"""
import argparse,copy,getpass,hashlib,json,subprocess,time
from pathlib import Path
import run_native_models as runner
from run_completion_and_pairs import read,write,sha,utc,infrastructure_error,NODE
ROOT=Path(__file__).resolve().parents[1];CURRENT_OUT=None
STAGES=('paired_native_08','native_completion_07')
def api(key,route,body=None):
    arg={'key':key,'route':route}
    if body is not None:arg['body']=body
    payload=json.dumps(arg);body_hash=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest() if body else None
    for attempt in range(2):
        started=utc();p=subprocess.run([NODE,str(ROOT/'scripts/openrouter_transport_v4.mjs')],input=payload,text=True,capture_output=True,timeout=930)
        error=p.stderr.replace(key,'[REDACTED]')[:1800]
        retryable=bool(p.returncode and any(x in error for x in ('EPIPE','ECONNRESET','Upload connection closed','socket hang up','ETIMEDOUT','Request timed out')) and 'OpenRouter HTTP' not in error)
        retry=route=='chat/completions' and retryable and attempt==0
        if route=='chat/completions':
            CURRENT_OUT.mkdir(parents=True,exist_ok=True)
            event={'started_at':started,'finished_at':utc(),'request_sha256':body_hash,'body_bytes':len(json.dumps(body).encode()),'model':body.get('model'),
                'network_attempt':attempt+1,'status':'failed' if p.returncode else 'received','error':error or None,'will_retry':retry,
                'extra_unresolved_charge_record':retry,'interpretation':'Failed upload may have been charged. An identical network request is retried at most once; no tool execution is repeated.'}
            with (CURRENT_OUT/'transport_events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        if not p.returncode:return json.loads(p.stdout)
        if not retry:raise RuntimeError(error)
        time.sleep(2)

def prepare(stage):
    path=ROOT/'config'/(stage+'.json')
    if path.exists():return read(path)
    parent='paired_native_04' if stage=='paired_native_08' else 'native_completion_03';cfg=copy.deepcopy(read(ROOT/'config'/(parent+'.json')))
    if stage=='paired_native_08':
        if list((ROOT/'output/paired_native_04/runs').glob('*.json')):raise ValueError('Paired protocol already ran; cannot amend before outcomes.')
        cfg['jobs']=[{**j,'run_id':j['run_id'].replace('__paired_r1','__paired_v2_r1')} for j in cfg['jobs']]
    else:
        jobs=[];excluded=[]
        for old in cfg['jobs']:
            p=ROOT/'output/native_completion_03/runs'/(old['run_id']+'.json');r=read(p) if p.exists() else None
            if r is None or infrastructure_error(r) or (r['status']=='execution_error' and any(x in r.get('error','') for x in ('EPIPE','UND_ERR_SOCKET'))):
                jobs.append({**old,'parent_run_id':old['run_id'],'run_id':old['run_id'].replace('__completion_r3','__completion_r4'),'repeat':4})
            else:excluded.append({'run_id':old['run_id'],'status':r['status']})
        cfg['jobs']=jobs;cfg['excluded_completion_runs']=excluded
    cfg.update(id=stage,created_at=utc(),parent_config=str(('config/'+parent+'.json')),parent_config_sha256=sha(ROOT/'config'/(parent+'.json')),
        transport='Verified Node HTTPS, HTTP/1.1 Content-Length, Expect: 100-continue and backpressure. Retry the identical request once for socket/time-out failures only. No redirects, weakened TLS, media thinning, model or provider fallback.',
        transport_retry_limit=1,amendment_reason='Fetch uploads failed with EPIPE and remote socket closure. This amendment was frozen before any paired solver outcome.',
        authorization={'api_spend_limit':'No fixed cap; user asked to complete interrupted work after increasing limit.','bounded_scope':f"{len(cfg['jobs'])} attempts with at most one identical-request network retry; preserve old failures."})
    cfg['input_hashes'].update({str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'scripts/openrouter_transport_v4.mjs']})
    write(path,cfg);return cfg

def summarize(stage,cfg,halt):
    out=ROOT/'output'/stage;rows=[read(p) for p in (out/'runs').glob('*.json')];ledger=read(out/'ledger.json') if (out/'ledger.json').exists() else []
    events=[json.loads(x) for x in (out/'transport_events.jsonl').read_text().splitlines()] if (out/'transport_events.jsonl').exists() else []
    done={r['run_id'] for r in rows if r['status']!='running'}
    r={'stage':stage,'planned':len(cfg['jobs']),'attempted':len(rows),'finished':len(done),'submitted':sum(r['status']=='submitted' for r in rows),
        'unattempted':[j['run_id'] for j in cfg['jobs'] if j['run_id'] not in done],'complete':len(done)==len(cfg['jobs']),'execution_finished':True,'halt':halt,
        'reported_api_cost_usd':sum(x['actual_cost_usd'] or 0 for x in ledger),'extra_unresolved_retry_charge_records':sum(x['extra_unresolved_charge_record'] for x in events),
        'unresolved_charge_records':sum(x['status']!='actual' for x in ledger)+sum(x['extra_unresolved_charge_record'] for x in events),'human_accepted':None}
    write(out/'run_summary.json',r);print(json.dumps(r),flush=True)
def main():
    global CURRENT_OUT
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();configs={s:prepare(s) for s in STAGES}
    for cfg in configs.values():
        for path,digest in cfg['input_hashes'].items():
            if sha(ROOT/path)!=digest:raise ValueError('Frozen input changed: '+path)
    if not args.execute:print(json.dumps({s:len(c['jobs']) for s,c in configs.items()}));return
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ');api(key,'key');runner.api=api
    try:
        for stage,cfg in configs.items():
            CURRENT_OUT=runner.OUT=ROOT/'output'/stage;halt=None;network_failures=0
            for job in cfg['jobs']:
                if (CURRENT_OUT/'runs'/(job['run_id']+'.json')).exists():continue
                r=runner.one(job,cfg,key)
                print(json.dumps({'stage':stage,'finished':r['run_id'],'status':r['status'],'cost':r.get('reported_api_cost_usd')}),flush=True)
                network_failures=network_failures+1 if r['status']=='execution_error' and any(t in r.get('error','') for t in ('EPIPE','ECONNRESET','socket','Upload','timed out')) else 0
                if any('OpenRouter HTTP '+x in r.get('error','') for x in ('401','402','403','429')):halt='Account/rate rejection';break
                if network_failures>=2:halt='Two consecutive attempts failed despite bounded transport repair';break
            summarize(stage,cfg,halt)
            if halt:break
    finally:key=None
if __name__=='__main__':main()
