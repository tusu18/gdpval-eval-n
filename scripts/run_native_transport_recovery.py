"""Post-hoc, sequential infrastructure recovery; original attempts stay intact.

Same solver/task/tool limits, one new attempt per infrastructure-failed slot.
Switch the HTTP client to system curl with ordinary TLS verification. No model
or budget-limit failures are retried, no provider/model fallback is enabled.
"""
import getpass,hashlib,json,re,subprocess,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
import run_native_models as original

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/native_transport_02';CFG=ROOT/'config/native_transport_02.json'
def utc():return datetime.now(timezone.utc).isoformat()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def curl_api(key,route,body=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',key):raise ValueError('Invalid credential format')
    if route not in ('key','chat/completions'):raise ValueError('Unexpected API route')
    config='url = "https://openrouter.ai/api/v1/'+route+'"\nheader = "Authorization: Bearer '+key+'"\nheader = "Content-Type: application/json"\nheader = "X-Title: Turing sequential transport recovery"\n'
    command=['curl','--config','-','--silent','--show-error','--connect-timeout','30','--max-time','900','--write-out','\n%{http_code}']
    path=None
    try:
        if body is not None:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',prefix='turing-api-body-',suffix='.json',delete=False) as f:
                json.dump(body,f,ensure_ascii=False);path=Path(f.name)
            command += ['--request','POST','--data-binary','@'+str(path)]
        # Secret is stdin-only, not an argument, environment variable or file.
        result=subprocess.run(command,input=config,text=True,capture_output=True,timeout=920)
        if result.returncode:raise RuntimeError('curl transport failure: '+result.stderr.replace(key,'[REDACTED]')[:500])
        raw,code=result.stdout.rsplit('\n',1)
        if not 200<=int(code)<300:
            raw=re.sub(r'"user_id"\s*:\s*"[^"]+"','"user_id":"[REDACTED]"',raw.replace(key,'[REDACTED]'))
            raise RuntimeError('OpenRouter HTTP '+code+': '+raw[:1500])
        return json.loads(raw)
    finally:
        if path is not None:path.unlink(missing_ok=True)

def prepare():
    if CFG.exists():return json.loads(CFG.read_text())
    base=json.loads((ROOT/'config/native_workflow_01.json').read_text())
    audit=json.loads((ROOT/'output/native_workflow_01/engineering_audit.json').read_text())
    if not audit['complete']:raise ValueError('Finish original pass before recovery selection')
    eligible={r['run_id'] for r in audit['runs'] if r['mechanical_attribution']=='transport_or_provider_failure'}
    jobs=[]
    for job in base['jobs']:
        if job['run_id'] in eligible:
            jobs.append({**job,'original_run_id':job['run_id'],'run_id':job['run_id'].replace('__native_r1','__transport_r2'),'repeat':2})
    cfg={**base,'id':'native-transport-02','created_at':utc(),'jobs':jobs,
        'status':'post_hoc_infrastructure_recovery_not_confirmatory',
        'authorization':{'api_spend_limit':'user explicitly confirmed no fixed cap','bounded_scope':f'One sequential recovery attempt for each of {len(jobs)} infrastructure-failed original slots; no retry of token/turn-limit outcomes.'},
        'changes':['Sequential execution instead of two concurrent workers.','System curl HTTP transport instead of Python urllib; TLS verification remains enabled.','One fresh restart per infrastructure-failed slot; no within-attempt automatic retry.'],
        'unchanged':'Same model, source task, native tools, system prompt, token/turn/tool limits, reasoning setting and provider price ceilings.',
        'interpretation':'Post-hoc recovery selected on infrastructure errors. Preserve and report original attempts, costs and exclusions. This is not a randomized transport experiment or a model quality ranking.',
        'parent_config_sha256':sha(ROOT/'config/native_workflow_01.json'),
        'script_sha256':sha(Path(__file__)),
        'quiescence_seconds_before_start':120}
    write(CFG,cfg);return cfg

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();cfg=prepare()
    if not args.execute:print(json.dumps({'prepared_recovery_attempts':len(cfg['jobs']),'paid_calls':0}));return
    if sha(Path(__file__))!=cfg['script_sha256']:raise ValueError('Frozen recovery script changed')
    for rel,h in cfg['input_hashes'].items():
        if sha(ROOT/rel)!=h:raise ValueError('Original frozen source changed: '+rel)
    latest=max(datetime.fromisoformat(json.loads(p.read_text())['finished_at']).timestamp() for p in (ROOT/'output/native_workflow_01/runs').glob('*.json'))
    remaining=max(0,latest+cfg['quiescence_seconds_before_start']-time.time())
    while remaining:
        time.sleep(min(remaining,30));remaining=max(0,latest+cfg['quiescence_seconds_before_start']-time.time())
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ')
    account=curl_api(key,'key').get('data',{})
    write(OUT/'account_limit_snapshot.json',{'observed_at':utc(),**{k:account.get(k) for k in ('limit','limit_remaining','usage','is_free_tier')},
        'interpretation':'API-key limit metadata, not necessarily the account cash balance. No credential or account identifier retained.'})
    original.OUT=OUT;original.api=curl_api
    for job in cfg['jobs']:
        r=original.one(job,cfg,key)
        print(json.dumps({'finished':r['run_id'],'status':r['status'],'reported_api_cost_usd':r.get('reported_api_cost_usd')}),flush=True)
        # Stop a campaign-level rejection instead of generating a cascade. The
        # remaining selected slots stay unattempted and are explicitly listed.
        if any('OpenRouter HTTP '+code in r.get('error','') for code in ('401','402','403','429')):
            print(json.dumps({'campaign_halted':'Account or rate rejection; no queued calls dispatched.'}),flush=True);break
    key=None
    rows=[json.loads(p.read_text()) for p in (OUT/'runs').glob('*.json')];ledger=json.loads((OUT/'ledger.json').read_text())
    done={r['run_id'] for r in rows}
    summary={'selected_attempts':len(cfg['jobs']),'finished_attempts':len(rows),'submitted':sum(r['status']=='submitted' for r in rows),
        'unattempted':[j['run_id'] for j in cfg['jobs'] if j['run_id'] not in done],
        'reported_api_cost_usd':sum(x['actual_cost_usd'] or 0 for x in ledger),
        'unresolved_charge_records':sum(x['status']!='actual' for x in ledger),'interpretation':cfg['interpretation']}
    write(OUT/'run_summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
