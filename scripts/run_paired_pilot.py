"""Bounded OpenRouter evaluation. API key stays in process memory (hidden prompt).

Only in-memory record tools are exposed to the model. Never evaluate model code.
Every paid request reserves a pessimistic cost before dispatch; ambiguous charges
retain the full reservation. API returns and failures are retained for audit.
"""
import argparse, concurrent.futures, datetime, getpass, hashlib, json, math, os, threading, time
import urllib.request, urllib.error, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/paired_v1'
LOCK=threading.Lock()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
TOOLS=[
 {'type':'function','function':{'name':'list_workspace','description':'List the operational records available in this task workspace.','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
 {'type':'function','function':{'name':'read_record','description':'Read one exact operational record by its filename.','parameters':{'type':'object','properties':{'filename':{'type':'string'}},'required':['filename'],'additionalProperties':False}}}
]
SYSTEM='''You are completing professional workplace tasks. Use only the supplied context and available tools. Resolve material uncertainty before making a commitment. Do not invent facts or send messages externally.
Return your final answer as one JSON object with these fields:
"facts": an object containing the specifically requested decision fields. Numeric quantities must be numbers, booleans booleans, lists arrays. Put null for a fact you cannot establish. For approval roles use canonical strings finance, program, purchase as applicable; operators use > or >=.
"evidence": an array of objects {"claim":string,"source":string,"reason":string} documenting sources and material conflicts.
"artifacts": an array of deliverables. For documents use {"filename":"name.docx","title":string,"sections":[{"heading":string,"paragraphs":[string],"table":{"headers":[string],"rows":[[string or number]]}}]}; table is optional. Do not output Markdown inside paragraphs. The renderer uses Calibri 11pt, Letter pages, section headings and tables. The content must fulfill the original professional request, not just list the decision fields.
For workbooks use {"filename":"name.xlsx","sheets":[{"name":string,"rows":[[string or number or null]]}]}. Formula cells are strings beginning =. Include the complete requested rows, columns, calculations and recommendations. The renderer styles, recalculates and exports your cells. It does not choose facts, add business logic, or repair mistakes.
"assumptions": array of strings; "unresolved": array of strings.
No text outside the JSON. You have up to five model responses and may batch record reads in one response. The final response must contain the complete deliverables.'''

class Budget:
    def __init__(self,cap):
        self.path=OUT/'ledger.json';self.cap=cap
        self.rows=json.loads(self.path.read_text()) if self.path.exists() else []
    def reserve(self,run_id,body):
        # UTF-8 byte count + ample chat/tool framing allowance upper-bounds these
        # text inputs conservatively. No images, paid native tools or plugins.
        n=len(json.dumps(body,ensure_ascii=False).encode())
        if n>55000:raise ValueError('input_byte_limit')
        amount=(n+4096)*2/1e6+body['max_tokens']*10/1e6
        with LOCK:
            charged=sum(x.get('charged_or_reserved',0) for x in self.rows)
            if charged+amount>self.cap:raise RuntimeError('budget_cap_before_dispatch')
            i=len(self.rows);self.rows.append({'id':i,'run_id':run_id,'reserved_at':utc(),'reservation_usd':amount,'charged_or_reserved':amount,'status':'reserved','input_bytes':n})
            write(self.path,self.rows);return i
    def settle(self,i,result=None,error=None):
        with LOCK:
            row=self.rows[i];row['settled_at']=utc()
            cost=(result or {}).get('usage',{}).get('cost')
            if isinstance(cost,(int,float)) and math.isfinite(cost) and cost>=0:
                row['actual_cost_usd']=cost;row['charged_or_reserved']=cost;row['status']='actual'
            else:row['status']='unresolved_charge_reserved'
            if error:row['error_type']=error
            write(self.path,self.rows)

def api(key,path,body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('https://openrouter.ai/api/v1/'+path,data=data,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','X-Title':'GDPval paired workflow pilot'})
    try:
        with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        # No request headers or credential-bearing objects enter logs.
        msg=e.read().decode(errors='replace').replace(key,'[REDACTED]')
        msg=re.sub(r'"user_id"\s*:\s*"[^"]+"','"user_id":"[REDACTED]"',msg)
        raise RuntimeError('HTTP '+str(e.code)+': '+msg[:1500]) from None

def extract_json(s):
    s=s.strip()
    if s.startswith('```'):s=s.split('\n',1)[1].rsplit('```',1)[0]
    x=json.loads(s)
    if not isinstance(x,dict):raise ValueError('final_must_be_object')
    return x

def run_one(job,key,budget,protocol):
    rid=job['instance_id']+'__'+job['model'].replace('/','_')+'__r'+str(job['trial'])
    path=OUT/'runs'/f'{rid}.json'
    if path.exists():return {'run_id':rid,'status':'already_saved'}
    inp=ROOT/'data/paired_v1/solver'/f"{job['instance_id']}.json"
    task=json.loads(inp.read_text());started=time.monotonic()
    record={'run_id':rid,**job,'family_id':task['family_id'],'variant':task['variant'],'started_at':utc(),'input_sha256':digest(inp),'protocol_sha256':digest(ROOT/'config/paired_protocol.v1.json'),'calls':[],'tool_events':[],'status':'running'}
    text=task['prompt']+'\n\nATTACHMENTS\n'+json.dumps(task['attachments'],ensure_ascii=False)+'\n\nDECISION FIELDS FOR THE ACCOMPANYING AUDIT RECORD\n'+json.dumps(task['fact_keys'])+'\nRequested format: '+task['deliverable_format']+'; requested file count: '+str(task['deliverable_count'])
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':text}]
    try:
        for step in range(protocol['max_calls_per_run']):
            body={'model':job['model'],'messages':messages,'max_tokens':protocol['max_completion_tokens_per_call'],
              'reasoning':{'effort':protocol['reasoning_effort']},'tools':TOOLS,
              'provider':{'order':['openai' if job['model'].startswith('openai/') else 'anthropic'],'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':2,'completion':10}}}
            if step==4:body['tool_choice']='none'
            ledger_id=budget.reserve(rid,body);callstart=time.monotonic()
            try:result=api(key,'chat/completions',body)
            except Exception as e:
                budget.settle(ledger_id,error=type(e).__name__);raise
            budget.settle(ledger_id,result)
            record['calls'].append({'step':step,'ledger_id':ledger_id,'seconds':time.monotonic()-callstart,'response':result})
            choices=result.get('choices') or []
            if not choices:raise ValueError('no_choices')
            message=choices[0]['message']
            # Keep standard tool transcript fields; retain original API response separately.
            assistant={'role':'assistant','content':message.get('content')}
            for k in ['tool_calls','reasoning_details']:
                if message.get(k):assistant[k]=message[k]
            messages.append(assistant)
            calls=message.get('tool_calls') or []
            if calls:
                for call in calls:
                    f=call['function'];name=f['name']
                    try:
                        args=json.loads(f['arguments'])
                        if name=='list_workspace':reply={'files':list(task['workspace'])}
                        elif name=='read_record':
                            fn=args.get('filename');reply={'filename':fn,'content':task['workspace'][fn]} if fn in task['workspace'] else {'error':'file_not_in_workspace'}
                        else:reply={'error':'unknown_tool'}
                    except (ValueError,TypeError):args={};reply={'error':'invalid_arguments'}
                    record['tool_events'].append({'step':step,'name':name,'arguments':args,'reply':reply})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(reply)})
            else:
                record['final']=extract_json(message.get('content') or '')
                record['finish_reason']=choices[0].get('finish_reason');record['status']='completed';break
        else:record['status']='step_limit'
    except Exception as e:
        record['status']='infrastructure_error' if isinstance(e,RuntimeError) else 'protocol_or_output_error'
        record['error']=str(e).replace(key,'[REDACTED]')[:1800]
    record['elapsed_seconds']=time.monotonic()-started;record['finished_at']=utc()
    record['actual_cost_usd']=sum(c['response'].get('usage',{}).get('cost',0) or 0 for c in record['calls'])
    write(path,record)
    with LOCK:print(json.dumps({'run_id':rid,'status':record['status'],'cost':round(record['actual_cost_usd'],5)}),flush=True)
    return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=3);args=p.parse_args()
    key=getpass.getpass('OpenRouter key (hidden; memory only): ')
    if not key.startswith('sk-or-'):raise SystemExit('Expected OpenRouter credential')
    OUT.mkdir(parents=True,exist_ok=True)
    info=api(key,'key').get('data',{})
    # Save only non-identifying budget fields; no label/hash/key/account details.
    write(OUT/'account_budget_start.json',{'checked_at':utc(),'limit_remaining':info.get('limit_remaining'),'effective_remaining':(info.get('effective_budget') or {}).get('remaining_usd')})
    print('Credential verified. Evaluation starting; budget cap $25, solver allocation $18.',flush=True)
    protocol=json.loads((ROOT/'config/paired_protocol.v1.json').read_text())
    for path,h in protocol['input_hashes'].items():
        if digest(ROOT/path)!=h:raise SystemExit('Frozen input changed: '+path)
    budget=Budget(protocol['solver_budget_cap_usd'])
    jobs=json.loads((ROOT/'data/paired_v1/run_order.json').read_text())
    if args.limit:jobs=jobs[:args.limit]
    write(OUT/'execution_environment.json',{'started_at':utc(),'python':os.sys.version,'workers':args.workers,'runner_sha256':digest(Path(__file__)),'protocol_sha256':digest(ROOT/'config/paired_protocol.v1.json'),'system_prompt':SYSTEM,'tools':TOOLS})
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda j:run_one(j,key,budget,protocol),jobs))
    print(json.dumps({'saved_runs':len(list((OUT/'runs').glob('*.json'))),'charged_or_reserved_usd':sum(x['charged_or_reserved'] for x in budget.rows)}),flush=True)
if __name__=='__main__':main()
