"""User-authorized continuation; immutable old attempts, one fixed-model paired phase.

No performance-selected model, no retries inside an attempt, no hidden gold access.
The five inspected families are development diagnostics, not held-out evidence.
"""
import argparse,copy,getpass,hashlib,json,random,subprocess
from datetime import datetime,timezone
from pathlib import Path
import run_native_models as runner
from build_evidence_upgrade import validate

ROOT=Path(__file__).resolve().parents[1]
NODE='/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
STAGES=('native_completion_03','paired_native_04')
FAMILIES=['original_supplier_landed_cost','supplier_exit','sourcing_approvals','change_control','original_delivery_appointment']
FIXED_MODEL='anthropic/claude-opus-5.5'
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def api(key,route,body=None):
    arg={'key':key,'route':route}
    if body is not None:arg['body']=body
    p=subprocess.run([NODE,str(ROOT/'scripts/openrouter_transport_v3.mjs')],input=json.dumps(arg),text=True,capture_output=True,timeout=930)
    if p.returncode:raise RuntimeError(p.stderr.replace(key,'[REDACTED]')[:1800])
    return json.loads(p.stdout)
def infrastructure_error(r):
    return r['status']=='execution_error' and any(x in r.get('error','').lower() for x in ('openrouter http','ssl','broken pipe','transport','fetch failed','connection','timeout','timed out'))

def prepare(stage):
    path=ROOT/'config'/(stage+'.json')
    if path.exists():return read(path)
    base=read(ROOT/'config/native_workflow_01.json');cfg=copy.deepcopy(base)
    if stage=='native_completion_03':
        recovery=read(ROOT/'config/native_transport_02.json');jobs=[];excluded=[]
        for old in recovery['jobs']:
            p=ROOT/'output/native_transport_02/runs'/(old['run_id']+'.json');r=read(p) if p.exists() else None
            if r is None or infrastructure_error(r):
                jobs.append({**old,'parent_run_id':old['run_id'],'selection_reason':'unattempted' if r is None else 'infrastructure_failure',
                    'repeat':3,'run_id':old['run_id'].replace('__transport_r2','__completion_r3')})
            else:excluded.append({'run_id':old['run_id'],'status':r['status'],'reason':'Completed submission or model/attempt-budget outcome; not infrastructure recovery.'})
        cfg.update(jobs=jobs,excluded=excluded,interpretation='Completion after user increased key limit. One new attempt for every unattempted or infrastructure-failed recovery slot. Older outcomes and costs remain. No ranking or causal repair-effect claim.')
    else:
        jobs=[{'family_id':f,'instance_id':f+'__'+condition,'condition':condition,'model':FIXED_MODEL,'repeat':1,
               'run_id':f+'__'+condition+'__paired_r1'} for f in FAMILIES for condition in ('baseline','conflict')]
        random.Random(20261105).shuffle(jobs)
        cfg.update(jobs=jobs,models=[m for m in cfg['models'] if m['id']==FIXED_MODEL],
            interpretation='One prespecified Claude model, five inspected development families, baseline/conflict pairs, one attempt per member. Same sources of truth, objective, tool access, output contract and limits within each pair. Human labels pending. Not held out, not a model comparison or training intervention.',
            model_choice='Fixed before this phase for the Anthropic-focused workflow study, not selected by observed success rate.',
            primary_endpoint='Paired difference in human acceptance; unresolved until full-output human review.',
            secondary_endpoints=['Human-supported consequential errors','Requirement commitments supported by source evidence','Native completion','Total generation/judging/human correction cost'],
            analysis_unit='Source family; preserve each incomplete or defective pair and report denominator explicitly.',
            seed=20261105,seed_scope='Run order only; no deterministic generation claim')
    cfg.update(id=stage,created_at=utc(),status='frozen_development_protocol',
        authorization={'api_spend_limit':'User confirmed no fixed cap; explicitly requested completion after increasing account limit.',
                       'bounded_scope':f"{len(cfg['jobs'])} attempts; no within-attempt retries or outcome-selected expansion."},
        transport='Node fetch, default certificate verification, fresh process per call, 900-second timeout, sequential dispatch; no provider/model fallback.',
        human_reviews_pending=True,independent_task_validation=False,
        parent_config_sha256=sha(ROOT/'config/native_workflow_01.json'))
    paths={ROOT/p for p in base['input_hashes']}
    paths.update(ROOT/'data/evidence_upgrade_01/solver'/(j['instance_id']+'.json') for j in cfg['jobs'])
    paths.update([Path(__file__),ROOT/'scripts/openrouter_transport_v3.mjs'])
    cfg['input_hashes']={str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}
    maps={m['instance_id']:m for m in read(ROOT/'data/evidence_upgrade_01/grader/evidence_maps.json')}
    rubrics={m['id']:m for m in read(ROOT/'data/evidence_upgrade_01/grader/rubrics.json')}
    for j in cfg['jobs']:
        errors=validate(read(ROOT/'data/evidence_upgrade_01/solver'/(j['instance_id']+'.json')),maps[j['instance_id']],rubrics[j['family_id']])
        if errors:raise ValueError((j['instance_id'],errors))
    write(path,cfg);return cfg

def summary(stage,cfg,halt=None):
    out=ROOT/'output'/stage;rows=[read(p) for p in sorted((out/'runs').glob('*.json'))];ledger=read(out/'ledger.json') if (out/'ledger.json').exists() else []
    done={r['run_id'] for r in rows if r['status']!='running'}
    result={'stage':stage,'planned':len(cfg['jobs']),'attempted':len(rows),'finished':len(done),
        'submitted':sum(r['status']=='submitted' for r in rows),'unattempted':[j['run_id'] for j in cfg['jobs'] if j['run_id'] not in done],
        'execution_finished':True,'complete':len(done)==len(cfg['jobs']),'halt':halt,
        'reported_api_cost_usd':sum(x['actual_cost_usd'] or 0 for x in ledger),
        'unresolved_charge_records':sum(x['status']!='actual' for x in ledger),
        'interpretation':cfg['interpretation'],'human_accepted':None,'consequential_errors':None}
    write(out/'run_summary.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--stage',choices=STAGES+('all',),default='all');args=p.parse_args()
    stages=STAGES if args.stage=='all' else [args.stage];configs={s:prepare(s) for s in stages}
    for cfg in configs.values():
        for path,digest in cfg['input_hashes'].items():
            if sha(ROOT/path)!=digest:raise ValueError('Frozen input changed: '+path)
    if not args.execute:print(json.dumps({s:len(c['jobs']) for s,c in configs.items()}));return
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ')
    account=api(key,'key').get('data',{})
    out=ROOT/'output/native_completion_03';write(out/'account_limit_snapshot.json',{'observed_at':utc(),**{k:account.get(k) for k in ('limit','limit_remaining','usage')},'interpretation':'Private API-key limit metadata; not campaign expense or verified cash balance.'})
    catalog=api(key,'models');write(out/'model_catalog.json',catalog);current={m['id']:m for m in catalog['data']}
    for cfg in configs.values():
        for j in cfg['jobs']:
            if j['model'] not in current:raise ValueError('Configured model unavailable: '+j['model'])
    print(json.dumps({'credential_validated':True,'configured_models_available':True,'paid_calls_so_far':0}),flush=True)
    runner.api=api
    try:
        for stage,cfg in configs.items():
            runner.OUT=ROOT/'output'/stage;consecutive_infrastructure_errors=0;halt=None
            for job in cfg['jobs']:
                dest=runner.OUT/'runs'/(job['run_id']+'.json')
                if dest.exists():continue
                r=runner.one(job,cfg,key)
                print(json.dumps({'stage':stage,'finished':r['run_id'],'status':r['status'],'reported_cost':r.get('reported_api_cost_usd')}),flush=True)
                consecutive_infrastructure_errors=consecutive_infrastructure_errors+1 if infrastructure_error(r) else 0
                if any('OpenRouter HTTP '+code in r.get('error','') for code in ('401','402','403','429')):
                    halt='Account or rate rejection; queued calls not dispatched.';break
                if consecutive_infrastructure_errors>=2:
                    halt='Two consecutive infrastructure failures; inspect transport before spending further.';break
            result=summary(stage,cfg,halt);print(json.dumps(result),flush=True)
            if halt:break
    finally:key=None
if __name__=='__main__':main()
