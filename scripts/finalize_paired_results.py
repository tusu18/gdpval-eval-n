"""Join decision checks, artifact constraints, blinded reviews and costs."""
import json,hashlib,datetime,statistics
from pathlib import Path
from score_paired_pilot import main as score_main,paired_summary
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/paired_v1'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False))
def main():
    score_main();scores=read(BASE/'scores.json');summary=read(BASE/'summary.json')
    judgments=[read(p) for p in (BASE/'judgments_v3').glob('*.json')]
    primary={x['run_id']:x for x in judgments if x['kind']=='primary' and x['status']=='completed'}
    secondary={x['run_id']:x for x in judgments if x['kind']=='secondary' and x['status']=='completed'}
    pages=read(BASE/'artifact_qa/page_checks.json') if (BASE/'artifact_qa/page_checks.json').exists() else []
    workbooks={x['run_id']:x for x in read(BASE/'artifact_qa/workbook_checks.json')}
    for s in scores:
        j=primary.get(s['run_id'],{}).get('judgment');s['primary_review']=j
        s['known_task_defect']=s['family_id']=='ev_localization' and s['variant']=='conflict'
        ps=[p for p in pages if p['run_id']==s['run_id']];s['page_checks']=ps
        source=read(ROOT/'data/paired_v1/solver'/f"{s['family_id']}__{s['variant']}.json")
        artifacts=list((BASE/'artifacts'/s['run_id']).glob('*.'+source['deliverable_format']))
        s['native_artifacts_exist']=len(artifacts)==source['deliverable_count']
        s['workbook_values_pass']=workbooks.get(s['run_id'],{}).get('pass')
        s['page_constraint_pass']=all(p.get('page_constraint_pass') is not False for p in ps)
        s['provisional_acceptance']=None if s['known_task_defect'] else bool(s['decision_pass'] and j and j.get('content_acceptable') and not j.get('critical_error') and not j.get('evaluation_defect') and s['native_artifacts_exist'] and s['page_constraint_pass'] and s['workbook_values_pass'] is not False)
        # This is a model-judged gate plus file/page checks, not human acceptance.
    for g in summary['groups']:
        rows=[r for r in scores if r['model']==g['model'] and r['variant']==g['variant']]
        g['provisional_acceptances']=sum(r['provisional_acceptance'] is True for r in rows)
        g['clean_denominator']=sum(not r['known_task_defect'] for r in rows)
        g['known_task_defects']=sum(r['known_task_defect'] for r in rows)
        g['content_reviewed']=sum(r['primary_review'] is not None for r in rows)
        g['content_acceptable']=sum(bool((r['primary_review'] or {}).get('content_acceptable')) for r in rows)
        g['judge_flagged_critical']=sum(bool((r['primary_review'] or {}).get('critical_error')) for r in rows)
        g['page_limit_failures']=sum(not r['page_constraint_pass'] for r in rows)
        n=g['provisional_acceptances'];g['solver_cost_per_provisional_acceptance']=g['cost_usd']/n if n else None
    shared=primary.keys()&secondary.keys();agreement={}
    for metric in ['content_acceptable','critical_error']:
        valid=[k for k in shared if isinstance(primary[k]['judgment'].get(metric),bool) and isinstance(secondary[k]['judgment'].get(metric),bool)]
        agree=sum(primary[k]['judgment'][metric]==secondary[k]['judgment'][metric] for k in valid)
        agreement[metric]={'agree':agree,'double_graded':len(valid),'rate':agree/len(valid) if valid else None,'disagreements':[k for k in valid if primary[k]['judgment'][metric]!=secondary[k]['judgment'][metric]]}
    solver=read(BASE/'ledger.json');judge=read(BASE/'judge_ledger.json')
    summary['review']={'valid_primary':len(primary),'valid_secondary':len(secondary),'judge_errors':sum(x['status']!='completed' for x in judgments),'agreement':agreement,'invalid_v1_judgments':len(list((BASE/'judgments').glob('*.json'))),'invalid_v2_judgments':len(list((BASE/'judgments_v2').glob('*.json'))),'human_experts':0}
    clean=[r for r in scores if not r['known_task_defect']]
    summary['clean_paired']=[{'model':m,'variant':v,**paired_summary(clean,m,v)} for m in sorted({r['model'] for r in clean}) for v in ['recovery','conflict']]
    summary['clean_paired_note']='Post-execution defect exclusion; raw preregistered comparisons remain under paired. EV conflict has coupled volume/cost-basis ambiguity affecting four runs.'
    summary['total_api_reported_cost_usd']=sum(x.get('actual_cost_usd',0) for x in solver+judge)
    summary['total_api_charged_or_reserved_usd']=sum(x['charged_or_reserved'] for x in solver+judge)
    summary['unresolved_cost_reservations']=sum(x['status'] not in ['actual','provider_rejected_before_dispatch'] for x in solver+judge)
    summary['provider_rejected_review_requests']=sum(x['status']=='provider_rejected_before_dispatch' for x in judge)
    summary['api_requests']=len(solver)+len(judge)
    summary['solver_requests']=len(solver);summary['judge_requests']=len(judge)
    summary['artifact_summary']={'docx':len(list((BASE/'artifacts').rglob('*.docx'))),'xlsx':len(list((BASE/'artifacts').rglob('*.xlsx'))),'rendered_docx':len(pages),'page_constraint_failures':sum(x.get('page_constraint_pass') is False for x in pages)}
    summary['artifact_summary']['workbooks_verified']=len(workbooks)
    summary['artifact_summary']['workbooks_passed']=sum(x['pass'] for x in workbooks.values())
    write(BASE/'scores.json',scores);write(BASE/'summary.json',summary)
    card={
      'schema':'local-evidence-card-v1-inspired-by-Evaluation-Cards-not-official-schema',
      'title':'GDPval paired workflow pilot','updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'summary_view':{'measures':'Recovering omitted facts and resolving approved-vs-draft conflicts while producing professional deliverables.','main_caveat':'Five purposively selected public task families; no independent expert acceptance and no measured training uplift.','intended_use':'Diagnose harness/task difficulty and design a larger rights-cleared workflow evaluation.','not_for':['claiming better-than-GDPval validity','production safety certification','claims about AfterQuery internal performance','contamination-free training claims']},
      'detailed_view':{'protocol':'../../config/paired_protocol.v1.json','source_selection':'../../data/paired_v1/selection_audit.json','results':'summary.json','per_run_metrics':'scores.json','raw_runs':'runs/','review_protocol':'judge_protocol.v3.json','review_outputs':'judgments_v3/','invalidated_reviews':['judgments/','judgments_v2/'],'defect_adjudications':'defect_adjudications.json','artifacts':'artifacts/','render_checks':'artifact_qa/page_checks.json','solver_cost_ledger':'ledger.json','review_cost_ledger':'judge_ledger.json'},
      'results':summary,'provenance':{'source':'https://huggingface.co/datasets/openai/gdpval','revision':'11e7900cdcac61bc4daf59e65feb238acda98fbf','synthetic_layers':'Assistant-authored deterministic substitutions, draft records and approval registry; authoritative business facts inherited unchanged from public source.','random_seed':20261030,'seed_scope':'run order only; semantic mutations specified explicitly','teacher_generation_calls':0,'training_steps':0,'expert_validation':'pending','permissions':'No explicit dataset license found; commercial adaptation and redistribution rights unverified.'},
      'contamination':{'training':'none','family_split':'All five sources and every variant are evaluation-only. Public diagnostic, never sealed holdout.','solver_access':'Exact record allowlist, no filesystem or web; no gold/rubric or other trial output supplied.','author_access':'Author inspected public tasks and source/grader context.','pretraining_exposure':'unknown','semantic_independence':'not established','hash_limit':'Local hashes demonstrate current bytes, not trusted chronological preregistration.'},
      'defects':[{'type':'source_data','family':'inventory_location','action':'excluded before solver calls','detail':'Received IDs do not join to location register; special-item received quantity absent.'},{'type':'source_data','family':'workload_distribution','action':'excluded before solver calls','detail':'Ellen Zhu appears in timesheets but not registry; capacity-period convention unresolved.'},*read(BASE/'defect_adjudications.json')['post_execution_amendments'],*read(BASE/'defect_adjudications.json')['review_defects'],*read(BASE/'defect_adjudications.json').get('validator_defects',[])],
      'claims_policy':'Documentation makes evidence inspectable; it does not establish realism, clean splits, correct grading or superiority.'}
    write(BASE/'evaluation_card.json',card)
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(BASE.rglob('*')) if p.is_file() and p.suffix in ['.json','.docx','.xlsx'] and p.name!='artifact_manifest.json'}
    write(BASE/'artifact_manifest.json',manifest)
    print(json.dumps({'final_runs':len(scores),'total_api_cost':summary['total_api_reported_cost_usd'],'charged_or_reserved':summary['total_api_charged_or_reserved_usd'],'reviews':summary['review'],'artifacts':summary['artifact_summary']},indent=2))
if __name__=='__main__':main()
