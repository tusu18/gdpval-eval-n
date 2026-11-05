"""Small exploratory prompt-repair probe, separate from the review-gated v2 study.

Uses only user-authorized local GDPval derivatives. No training, publication,
expert acceptance or release recommendation. Credentials remain in memory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import threading
import time
import urllib.error
import urllib.request
from workflow_workspace import Workspace, initial_message

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/repair_probe_01'
CONFIG=ROOT/'config/repair_probe_01.json'
LOCK=threading.RLock()
FAMILIES=('supplier_exit','sourcing_approvals')
MODELS=('openai/gpt-6.1-sol','anthropic/claude-sonnet-5.5')
SCHEMA='''Return exactly one JSON object, without markdown fences, containing:
facts: an object using the requested audit field names; numeric values as numbers, lists as arrays, unknown facts as null. Approval role labels are finance, program, purchase.
evidence: an array of {claim, source, reason} objects.
artifacts: the requested documents, each as {filename: "name.docx", title: string, sections: [{heading: string, paragraphs: [string], table: {headers: [string], rows: [[string or number]]}}]}. Tables are optional. Use plain text paragraphs. The content must satisfy the actual professional request, not merely the audit fields.
assumptions: an array of strings. unresolved: an array of strings.
The fixed renderer uses Letter pages, one-inch margins, Calibri 11, 1.15 line spacing, headings and tables. It preserves your words and does not repair business logic or shorten content. Respect the requested 2-3-page limit. Up to six model responses are available; the last must contain the complete final JSON deliverable. No external communications or actions are permitted.'''
TOOLS=[{'type':'function','function':{'name':name,'description':desc,'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}} for name,desc,props,required in [
    ('list_files','List paths in this task workspace, optionally by folder prefix.',{'prefix':{'type':'string'}},[]),
    ('search_files','Search filenames and contents in this task workspace; returns snippets and paths.',{'query':{'type':'string'}},['query']),
    ('read_file','Read an exact path from this task workspace.',{'path':{'type':'string'}},['path']),
    ('ask_requester','Ask a specific clarification. Returns only the simulated stakeholder information already recorded; cannot create approvals or commitments.',{'question':{'type':'string'}},['question']),
]]

def utc():return datetime.now(timezone.utc).isoformat()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def prepare():
    if CONFIG.exists():
        return read(CONFIG)
    arms=read(ROOT/'config/paired_v2/prompt_arms.json')
    jobs=[{'family_id':f,'instance_id':f+'__conflict','variant':'conflict','model':m,'arm':a,'trial':t} for f in FAMILIES for m in MODELS for a in ['baseline','evidence_check'] for t in [1,2]]
    random.Random(20261031).shuffle(jobs)
    for job in jobs:job['run_id']=job['family_id']+'__'+job['model'].replace('/','_')+'__'+job['arm']+'__r'+str(job['trial'])
    paths=[ROOT/'data/paired_v2/solver'/f'{f}__conflict.json' for f in FAMILIES]+[ROOT/'config/paired_v2/prompt_arms.json',ROOT/'scripts/workflow_workspace.py',Path(__file__).resolve()]
    cfg={'version':'repair-probe-01','prepared_at_utc':utc(),'status':'exploratory_internal_diagnostic','scope':'Two GDPval-derived purchasing families with observed v1 failure candidates; conflict condition only; 2 models x 2 prompt arms x 2 repeats = 16 runs.','amendment':'A separately recorded exploratory probe before independent review. The full v2 study and model-release selection remain review-gated. No expert-validation or cleared-dataset claim.','human_review':'User volunteered to review purchasing cases. Reviews and qualification declaration are pending; the reviewer is aware of the study hypothesis.','task_permissions':'User-authorized private local evaluation; no commercial redistribution or training permission is inferred.','primary_report':'Deterministic audit-field correctness, output validity and rendered page constraints; no unobserved expert acceptance.','secondary_review':'Blinded human review of all first repeats (8 outputs), followed by repeat review if needed. No paid model judge is substituted for human judgment.','causal_comparison':'Within this probe, compare evidence_check minus baseline prompt on the same family/model/repeat. Both arms share tools, input facts, renderer, output budget and reasoning setting. v1-v2 differences are not the repair effect.','limitations':['Only two targeted business families, selected after observing v1 failures.','No representative reliability or low-error certification.','Prompt arms cannot be fully blinded from generated writing style.','Model sampling is not exactly seed-replayable.'],'stage_cap_usd':6,'campaign_cap_usd':25,'price_cap_per_million':{'prompt':2,'completion':10},'reasoning_effort':'medium','max_tokens':9000,'max_calls':6,'max_request_bytes':120000,'max_tool_calls_per_response':12,'tools':TOOLS,'output_schema_prompt':SCHEMA,'prompt_arms':{a:arms[a] for a in ['baseline','evidence_check']},'seed':20261031,'seed_scope':'Run order only','jobs':jobs,'input_hashes':{str(p.relative_to(ROOT)):digest(p) for p in paths},'training_steps':0}
    write(CONFIG,cfg)
    return cfg

def verify_frozen(cfg):
    for path,expected in cfg['input_hashes'].items():
        if digest(ROOT/path)!=expected:raise RuntimeError('Frozen probe input changed: '+path)
    old=read(ROOT/'config/paired_protocol.v1.json')
    for path,expected in old['input_hashes'].items():
        if digest(ROOT/path)!=expected:raise RuntimeError('Original v1 input changed: '+path)

class BudgetStop(RuntimeError):pass
class APIError(RuntimeError):
    def __init__(self,message,pre_dispatch=False):super().__init__(message);self.pre_dispatch=pre_dispatch

class CampaignBudget:
    def __init__(self,base,campaign=25,stage=6,legacy_paths=None):
        self.path=base/'ledger.json';self.campaign=Decimal(str(campaign));self.stage=Decimal(str(stage))
        self.legacy_paths=legacy_paths if legacy_paths is not None else [ROOT/'output/paired_v1/ledger.json',ROOT/'output/paired_v1/judge_ledger.json']
        self.rows=read(self.path) if self.path.exists() else []
    def legacy_cost(self):
        return sum((Decimal(str(x['charged_or_reserved'])) for p in self.legacy_paths if p.exists() for x in read(p)),Decimal(0))
    def exposure(self):return sum((Decimal(str(x['charged_or_reserved'])) for x in self.rows),Decimal(0))
    def reserve(self,run_id,body):
        size=len(json.dumps(body,ensure_ascii=False).encode())
        if size>120000:raise BudgetStop('request_byte_limit')
        if type(body.get('max_tokens')) is not int or not 1<=body['max_tokens']<=9000:raise BudgetStop('invalid_output_cap')
        # Byte-based conservative input bound, framing allowance and 2x input-price
        # cushion for cache write billing; no images, paid native tools or plugins.
        amount=Decimal(size+8192)*Decimal(4)/1_000_000+Decimal(body['max_tokens'])*Decimal(10)/1_000_000
        with LOCK:
            exposure=self.exposure();legacy=self.legacy_cost()
            if exposure+amount>self.stage or legacy+exposure+amount>self.campaign:raise BudgetStop('budget_cap_before_dispatch')
            index=len(self.rows)
            self.rows.append({'id':index,'run_id':run_id,'reserved_at':utc(),'reservation_usd':float(amount),'charged_or_reserved':float(amount),'status':'reserved','input_bytes':size,'legacy_exposure_at_reservation':float(legacy)})
            write(self.path,self.rows)
            return index
    def settle(self,index,response=None,error=None):
        with LOCK:
            row=self.rows[index];row['settled_at']=utc()
            cost=(response or {}).get('usage',{}).get('cost')
            if type(cost) in (int,float) and math.isfinite(cost) and cost>=0:
                row.update({'actual_cost_usd':cost,'charged_or_reserved':cost,'status':'actual'})
                row['reservation_exceeded']=cost>row['reservation_usd']
            elif isinstance(error,APIError) and error.pre_dispatch:
                row.update({'actual_cost_usd':0,'charged_or_reserved':0,'status':'provider_rejected_before_dispatch'})
            else:row['status']='unresolved_charge_reserved'
            if error:row['error_type']=type(error).__name__
            write(self.path,self.rows)

def api(path,key=None,body=None):
    data=None if body is None else json.dumps(body).encode()
    headers={'Content-Type':'application/json','X-Title':'Turing private GDPval repair diagnostic'}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request('https://openrouter.ai/api/v1/'+path,data=data,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
    except urllib.error.HTTPError as e:
        message=e.read().decode(errors='replace')
        if key:message=message.replace(key,'[REDACTED]')
        message=re.sub(r'"user_id"\s*:\s*"[^"]+"','"user_id":"[REDACTED]"',message)
        message=re.sub(r'sk-or-v1-[a-fA-F0-9]+','[REDACTED]',message)
        pre=e.code in (401,403) or (e.code==402 and ('in_flight_budget' in message or 'before provider' in message))
        raise APIError('HTTP '+str(e.code)+': '+message[:1200],pre_dispatch=pre) from None

def validate_catalog(catalog,models):
    entries={x['id']:x for x in catalog['data']}
    selected=[]
    for model in models:
        if model not in entries:raise RuntimeError('Selected model unavailable: '+model)
        x=entries[model];price=x['pricing']
        if Decimal(str(price['prompt']))>Decimal('0.000002') or Decimal(str(price['completion']))>Decimal('0.000010'):raise RuntimeError('Model exceeds frozen price ceiling: '+model)
        if Decimal(str(price.get('request','0')))>0:raise RuntimeError('Per-request charges are outside the frozen reservation model')
        if 'tools' not in x.get('supported_parameters',[]):raise RuntimeError('Model does not advertise tool support')
        selected.append({'id':model,'pricing':price,'supported_parameters':x.get('supported_parameters'),'context_length':x.get('context_length')})
    return selected

def parse_final(content):
    text=(content or '').strip()
    if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
    result=json.loads(text)
    if not isinstance(result,dict) or not isinstance(result.get('facts'),dict) or not isinstance(result.get('artifacts'),list):raise ValueError('invalid_final_schema')
    return result

def reported_cost(response):
    cost=response.get('usage',{}).get('cost')
    return cost if type(cost) in (int,float) and math.isfinite(cost) and cost>=0 else 0

def run_one(job,key,budget,cfg,transport=api):
    path=BASE/'runs'/(job['run_id']+'.json')
    if path.exists():return read(path)
    task_path=ROOT/'data/paired_v2/solver'/(job['instance_id']+'.json')
    task=read(task_path);env=Workspace(task);start=time.monotonic()
    record={**job,'started_at':utc(),'input_sha256':digest(task_path),'probe_protocol_sha256':digest(CONFIG),'calls':[],'status':'running','evidence_scope':'exploratory_not_expert_validated'}
    messages=[{'role':'system','content':cfg['prompt_arms'][job['arm']]+'\n'+cfg['output_schema_prompt']},{'role':'user','content':initial_message(task)}]
    try:
        for step in range(cfg['max_calls']):
            body={'model':job['model'],'messages':messages,'max_tokens':cfg['max_tokens'],'reasoning':{'effort':cfg['reasoning_effort']},'tools':TOOLS,'provider':{'order':['openai' if job['model'].startswith('openai/') else 'anthropic'],'allow_fallbacks':False,'require_parameters':True,'max_price':cfg['price_cap_per_million']}}
            if step==cfg['max_calls']-1:body['tool_choice']='none'
            lid=budget.reserve(job['run_id'],body)
            try:response=transport('chat/completions',key,body)
            except Exception as e:budget.settle(lid,error=e);raise
            budget.settle(lid,response)
            record['calls'].append({'step':step,'ledger_id':lid,'response':response})
            write(path,record|{'tool_events':env.events})
            choice=response['choices'][0];message=choice['message']
            record['finish_reason']=choice.get('finish_reason')
            assistant={'role':'assistant','content':message.get('content')}
            for field in ['tool_calls','reasoning_details']:
                if message.get(field):assistant[field]=message[field]
            messages.append(assistant)
            calls=message.get('tool_calls') or []
            if not calls:
                record['final']=parse_final(message.get('content'))
                record['status']='completed';break
            if len(calls)>cfg['max_tool_calls_per_response']:raise ValueError('too_many_tool_calls')
            for call in calls:
                try:arguments=json.loads(call['function']['arguments'])
                except (ValueError,TypeError):arguments=None
                reply=env.call(call['function']['name'],arguments)
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(reply,ensure_ascii=False)})
        else:record['status']='step_limit'
    except BudgetStop as e:record.update({'status':'budget_stopped','error':str(e)})
    except APIError as e:record.update({'status':'provider_rejected' if e.pre_dispatch else 'infrastructure_error','error':str(e)})
    except (urllib.error.URLError,TimeoutError,ConnectionError) as e:record.update({'status':'infrastructure_error','error':str(e).replace(key,'[REDACTED]')[:1200]})
    except Exception as e:record.update({'status':'protocol_or_output_error','error':str(e).replace(key,'[REDACTED]')[:1200]})
    record.update({'tool_events':env.events,'finished_at':utc(),'elapsed_seconds':time.monotonic()-start,'actual_cost_usd':sum(reported_cost(c['response']) for c in record['calls'])})
    write(path,record)
    with LOCK:print(json.dumps({'run_id':job['run_id'],'status':record['status'],'cost':round(record['actual_cost_usd'],6)}),flush=True)
    return record

@contextmanager
def campaign_lock():
    path=ROOT/'output/evaluation_campaign.lock';path.parent.mkdir(exist_ok=True)
    with path.open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Another campaign runner holds the lock')
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    cfg=prepare();verify_frozen(cfg)
    if not args.execute:
        print(json.dumps({'prepared_runs':len(cfg['jobs']),'stage_cap_usd':cfg['stage_cap_usd'],'paid_calls':0,'mode':'exploratory; human review pending'}));return
    if not 1<=args.workers<=2:raise SystemExit('Use one or two workers')
    with campaign_lock():
        catalog=api('models');selected=validate_catalog(catalog,cfg['models'] if 'models' in cfg else MODELS)
        write(BASE/'catalog_snapshot.json',{'fetched_at':utc(),'models':selected})
        key=os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter key (hidden; memory only): ')
        if not key.startswith('sk-or-'):raise SystemExit('Expected OpenRouter key')
        info=api('key',key).get('data',{})
        print(json.dumps({'credential_verified':True,'provider_limit_remaining':info.get('limit_remaining'),'effective_remaining':(info.get('effective_budget') or {}).get('remaining_usd')}),flush=True)
        budget=CampaignBudget(BASE,cfg['campaign_cap_usd'],cfg['stage_cap_usd'])
        write(BASE/'execution_environment.json',{'started_at':utc(),'workers':args.workers,'python':os.sys.version,'runner_sha256':digest(Path(__file__)),'protocol_sha256':digest(CONFIG),'documentation':['https://openrouter.ai/docs/guides/routing/provider-selection','https://openrouter.ai/docs/cookbook/administration/usage-accounting']})
        jobs=[j for j in cfg['jobs'] if not (BASE/'runs'/(j['run_id']+'.json')).exists()]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(lambda j:run_one(j,key,budget,cfg),jobs))
        del key
        print(json.dumps({'saved_runs':len(list((BASE/'runs').glob('*.json'))),'probe_charged_or_reserved_usd':float(budget.exposure()),'campaign_charged_or_reserved_usd':float(budget.legacy_cost()+budget.exposure()),'human_reviews_completed':0}),flush=True)

if __name__=='__main__':main()
