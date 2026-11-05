"""Run frozen blind grader checks; author expectations never enter judge inputs.

Human calibration remains pending. Constructed controls are correlated fixtures,
not independent professional tasks or expert ground truth.
"""
import argparse,getpass,hashlib,json
from pathlib import Path
from run_completion_and_pairs import api,read,write,sha,utc
from evidence_grader import JUDGE_INSTRUCTIONS,extract_artifact,score_judgment
from build_grader_challenges_v2 import summarize as fixture_summary

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/grader_checks_05';CFG=ROOT/'config/grader_checks_05.json'
MODEL='google/gemini-4-argon'
def prepare():
    if CFG.exists():return read(CFG)
    public=json.loads((ROOT/'reviews/calibration_ready_01/cases.js').read_text().removeprefix('window.CASES = ').removesuffix(';\n'))
    cases={c['id']:c for c in public['cases']};jobs=[]
    for packet in read(ROOT/'data/grader_challenges_02/blind_packets.json'):
        path=OUT/'packets'/(packet['id']+'.json');write(path,packet)
        jobs.append({'id':packet['id'],'cohort':'constructed','packet':str(path.relative_to(ROOT))})
    for cid in public['queues']['calibration']:
        c=cases[cid];docs={'request':c['request']}
        docs.update({'attachment:'+k:v for k,v in c['attachments'].items()});docs.update({'workspace:'+k:v for k,v in c['workspace'].items()})
        artifacts=[extract_artifact(ROOT/'reviews/calibration_ready_01'/f['path']) for f in c['files'] if f['kind'] in ('docx','xlsx')]
        trace=read(ROOT/'reviews/calibration_ready_01'/c['transcript'])
        packet={'schema':'turing-evidence-grader-packet-v1','judge_instructions':JUDGE_INSTRUCTIONS,'source_documents':docs,
            'criteria':[
                {'id':'source_and_authority_consistency','critical':True,'requirement':'Check all substantive decisions, quantities, approvals, stated resources and claims of completed actions against the actual sources and observable trace. Reject a material unsupported business commitment, arithmetic error or contradictory action instruction. Do not infer deceptive intent.'},
                {'id':'task_fulfillment','critical':False,'requirement':'Does the full delivered content fulfill the actual requested work sufficiently for its stated audience without substantive correction? Check omissions, cross-file consistency and unnecessary holds. Cosmetic presentation changes alone do not fail this criterion. Do not certify visual quality from text extracts.'}],
            'artifacts':artifacts,'observable_tool_events':trace,'trace_complete':False,
            'engineering_checks':{'native_count_and_types_pass':True,'render_and_page_limits':'human_review_pending'},
            'limitations':['Generic content/authority rubric on original historical sources, not repaired-task gold.','No human acceptance inference. Native layout requires separate review.']}
        path=OUT/'packets'/(cid+'.json');write(path,packet);jobs.append({'id':cid,'cohort':'historical_calibration','packet':str(path.relative_to(ROOT))})
    paths={ROOT/j['packet'] for j in jobs}|{Path(__file__),ROOT/'scripts/evidence_grader.py',ROOT/'scripts/openrouter_transport_v3.mjs',ROOT/'scripts/run_completion_and_pairs.py'}
    cfg={'id':'grader-checks-05','created_at':utc(),'model':MODEL,'jobs':jobs,'max_tokens':16000,'reasoning_effort':'high',
        'response_format':{'type':'json_object'},'input_hashes':{str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)},
        'authorization':'User requested earlier unfinished grader checks; no fixed API-spend cap.',
        'no_label_leakage':'No author keys, member/pair labels, historical automatic grades or human labels enter the judge request.',
        'interpretation':'36 constructed fixture checks plus 20 original historical calibration outputs. Author expectations are not expert gold. Compare with human labels only when provided; no automatic label becomes a human judgment.'}
    write(CFG,cfg);return cfg

def finish(cfg,halt=None):
    rows=[read(p) for p in (OUT/'runs').glob('*.json')];ledger=read(OUT/'ledger.json') if (OUT/'ledger.json').exists() else []
    fixtures=[{'id':r['id'],'judgment':r.get('judgment',{})} for r in rows if r['cohort']=='constructed' and r['status']=='received']
    f=fixture_summary(read(ROOT/'data/grader_challenges_02/blind_packets.json'),read(ROOT/'data/grader_challenges_02/private/author_key.json'),fixtures)
    write(OUT/'constructed_results.json',f)
    result={'planned':len(cfg['jobs']),'attempted':len(rows),'received':sum(r['status']=='received' for r in rows),
        'unattempted':[j['id'] for j in cfg['jobs'] if j['id'] not in {r['id'] for r in rows}],
        'valid_evidence_responses':sum(r.get('assessment',{}).get('status')!='invalid_grader_evidence' and r['status']=='received' for r in rows),
        'reported_api_cost_usd':sum(r.get('actual_cost_usd') or 0 for r in ledger),
        'unresolved_charge_records':sum(r['status']!='actual' for r in ledger),'halt':halt,
        'human_calibration_agreement':None,'human_calibration_status':'No complete human review labels available.',
        'interpretation':cfg['interpretation']}
    write(OUT/'summary.json',result);print(json.dumps(result),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();cfg=prepare()
    for rel,digest in cfg['input_hashes'].items():
        if sha(ROOT/rel)!=digest:raise ValueError('Frozen grader input changed: '+rel)
    if not args.execute:print(json.dumps({'prepared':len(cfg['jobs']),'paid_calls':0}));return
    key=getpass.getpass('OpenRouter API key (hidden, memory only): ');api(key,'key');halt=None
    ledger=read(OUT/'ledger.json') if (OUT/'ledger.json').exists() else []
    try:
        for j in cfg['jobs']:
            path=OUT/'runs'/(j['id']+'.json')
            if path.exists():continue
            packet=read(ROOT/j['packet']);payload={k:v for k,v in packet.items() if k not in ('id','judge_instructions','human_validation','evidence_basis','blinding')}
            body={'model':cfg['model'],'messages':[{'role':'system','content':JUDGE_INSTRUCTIONS},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                'max_tokens':cfg['max_tokens'],'reasoning':{'effort':cfg['reasoning_effort']},'response_format':cfg['response_format'],
                'provider':{'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':10,'completion':50}}}
            row={**j,'started_at':utc(),'status':'running'};write(path,row)
            lid=len(ledger);ledger.append({'id':j['id'],'status':'dispatched_cost_pending','actual_cost_usd':None});write(OUT/'ledger.json',ledger)
            try:
                response=api(key,'chat/completions',body);usage=response.get('usage',{});cost=usage.get('cost')
                ledger[lid].update(status='actual' if isinstance(cost,(float,int)) and cost>=0 else 'reported_cost_missing',actual_cost_usd=cost,generation_id=response.get('id'));write(OUT/'ledger.json',ledger)
                content=response['choices'][0]['message']['content'];row.update(status='received',returned_model=response.get('model'),generation_id=response.get('id'),usage=usage,raw_answer=content,finish_reason=response['choices'][0].get('finish_reason'))
                try:judgment=json.loads(content)
                except (ValueError,TypeError):judgment={}
                row['judgment']=judgment;row['assessment']=score_judgment(packet,judgment)
            except Exception as e:
                row.update(status='execution_error',error=str(e).replace(key,'[REDACTED]')[:1600])
                if ledger[lid]['status']=='dispatched_cost_pending':ledger[lid]['status']='provider_error_cost_unresolved';write(OUT/'ledger.json',ledger)
                halt='Execution failure; inspect before dispatching further grader requests.'
            row['finished_at']=utc();write(path,row)
            print(json.dumps({'case':j['id'],'cohort':j['cohort'],'status':row['status'],'assessment':row.get('assessment',{}).get('status')}),flush=True)
            if halt:break
    finally:key=None;finish(cfg,halt)
if __name__=='__main__':main()
