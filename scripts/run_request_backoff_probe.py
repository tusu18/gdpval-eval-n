"""One separate engineering probe of bounded, identical-request recovery.

Do not change the fixed paired study or replace any earlier outcome. Credentials
remain in memory. TLS verification stays on; tools execute only after a response.
"""
import argparse,copy,getpass,hashlib,json,re,subprocess,time
from pathlib import Path
import run_native_models as runner
from run_completion_and_pairs import read,write,sha,utc,NODE
from run_verified_transport_study import summarize

ROOT=Path(__file__).resolve().parents[1]
STAGE='native_backoff_probe_09'
CURRENT_OUT=ROOT/'output'/STAGE

def retry_delay(error, attempt):
    if attempt>=2:return None
    if 'OpenRouter HTTP 402' in error and 'in_flight_budget_exhausted' in error:
        m=re.search(r'"Retry-After"\s*:\s*"?(\d+)',error)
        delay=max(120,int(m.group(1))) if m else 120
        return delay if delay<=300 else None
    if 'OpenRouter HTTP 429' in error and 'openrouter_admission_control' in error:
        m=re.search(r'"Retry-After"\s*:\s*"?(\d+)',error)
        delay=int(m.group(1)) if m else 60
        return max(10,delay) if delay<=300 else None
    if attempt==0 and any(x in error for x in ('ERR_SSL_SSL/TLS_ALERT_BAD_RECORD_MAC','EPIPE','ECONNRESET','Upload connection closed','socket hang up','ETIMEDOUT','Request timed out')) and 'OpenRouter HTTP' not in error:
        return 2
    return None

def pause(seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        remaining=until-time.monotonic()
        print(json.dumps({'transport_wait_seconds_remaining':round(remaining)}),flush=True)
        time.sleep(min(30,remaining))

def api(key,route,body=None):
    arg={'key':key,'route':route}
    if body is not None:arg['body']=body
    payload=json.dumps(arg)
    digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest() if body else None
    for attempt in range(3):
        started=utc()
        p=subprocess.run([NODE,str(ROOT/'scripts/openrouter_transport_v4.mjs')],input=payload,text=True,capture_output=True,timeout=930)
        error=p.stderr.replace(key,'[REDACTED]')[:1800]
        delay=retry_delay(error,attempt) if p.returncode and route=='chat/completions' else None
        if route=='chat/completions':
            CURRENT_OUT.mkdir(parents=True,exist_ok=True)
            event={'started_at':started,'finished_at':utc(),'request_sha256':digest,'body_bytes':len(json.dumps(body).encode()),'model':body.get('model'),
                'network_attempt':attempt+1,'status':'failed' if p.returncode else 'received','error':error or None,
                'will_retry':delay is not None,'retry_delay_seconds':delay,'extra_unresolved_charge_record':delay is not None,
                'interpretation':'An identical request is resent after bounded verified-connection recovery or provider-directed admission wait. No tool execution is repeated. Failed request charges remain unknown.'}
            with (CURRENT_OUT/'transport_events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        if not p.returncode:return json.loads(p.stdout)
        if delay is None:raise RuntimeError(error)
        pause(delay)

def prepare():
    path=ROOT/'config'/(STAGE+'.json')
    if path.exists():return read(path)
    parent=ROOT/'config/native_completion_07.json';cfg=copy.deepcopy(read(parent))
    old=next(j for j in cfg['jobs'] if j['family_id']=='sourcing_approvals' and j['model']=='google/gemini-4-argon')
    record=ROOT/'output/native_completion_07/runs'/(old['run_id']+'.json');r=read(record)
    if r['status']!='execution_error' or 'BAD_RECORD_MAC' not in r.get('error',''):raise ValueError('The specified failed diagnostic target is not eligible.')
    job={**old,'parent_run_id':old['run_id'],'run_id':old['run_id'].replace('__completion_r4','__backoff_probe_r5'),'repeat':5}
    cfg.update(id=STAGE,created_at=utc(),jobs=[job],models=[m for m in cfg['models'] if m['id']==job['model']],
        status='frozen_single_case_engineering_probe_not_primary_evaluation',parent_config=str(parent.relative_to(ROOT)),parent_config_sha256=sha(parent),
        transport='Existing verified Node HTTPS transport. Up to three identical network attempts; transient TLS/socket retry once; in-flight-credit rejection waits at least 120 seconds and honors Retry-After up to 300 seconds; admission-control 429 honors a bounded Retry-After. No model, tool, provider, media or certificate-validation changes.',
        transport_retry_limit=2,
        amendment_reason='Post-hoc, single-case request-recovery check prepared after the paired study finished. This does not amend or replace the paired protocol or its outcomes.',
        authorization={'api_spend_limit':'Existing user authorization: no fixed cap; complete the native workflow and request funds if needed.','bounded_scope':'One prespecified Gemini sourcing-approvals engineering probe. No automatic expansion.'},
        selection='One known TLS-failed sourcing case chosen to inspect recovery behavior. Post-hoc engineering selection, not a random sample or model comparison.',
        interpretation='Separate single-case transport probe; excludes every paired-study denominator. Preserve earlier failure and all charges. A successful run without a retry does not establish live recovery; neither outcome establishes business quality or a reliability rate.')
    cfg['input_hashes'].update({str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),str(record.relative_to(ROOT)):sha(record)})
    write(path,cfg);return cfg

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();cfg=prepare()
    for rel,digest in cfg['input_hashes'].items():
        if sha(ROOT/rel)!=digest:raise ValueError('Frozen input changed: '+rel)
    if not args.execute:print(json.dumps({'planned':len(cfg['jobs']),'scope':cfg['interpretation']}));return
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ')
    try:
        api(key,'key');runner.OUT=CURRENT_OUT;runner.api=api
        for job in cfg['jobs']:
            r=runner.one(job,cfg,key)
            print(json.dumps({'stage':STAGE,'finished':r['run_id'],'status':r['status'],'reported_api_cost_usd':r.get('reported_api_cost_usd')}),flush=True)
        summarize(STAGE,cfg,None)
    finally:key=None

if __name__=='__main__':main()
