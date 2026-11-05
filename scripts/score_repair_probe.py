"""Report paired mechanical outcomes; leave human acceptance unmeasured."""
import json
from pathlib import Path
import statistics
from score_paired_pilot import matches

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/repair_probe_01'
def read(path):return json.loads(path.read_text())
def summarize():
    cfg=read(ROOT/'config/repair_probe_01.json')
    defect_path=BASE/'task_defects.json'
    defect=read(defect_path) if defect_path.exists() else None
    affected=set(defect['affected_probe_run_ids']) if defect else set()
    rubrics={r['id']:r for r in read(ROOT/'data/paired_v2/grader/rubrics.json')}
    pages=read(BASE/'artifact_qa/page_checks.json') if (BASE/'artifact_qa/page_checks.json').exists() else []
    rows=[]
    for path in sorted((BASE/'runs').glob('*.json')):
        run=read(path)
        if run['status']=='running':continue
        facts=(run.get('final') or {}).get('facts') or {}
        truth=rubrics[run['family_id']]['truth']
        checks={k:{'actual':facts.get(k),'expected':v,'correct':matches(facts.get(k),v)} for k,v in truth.items()}
        docs=list((BASE/'artifacts'/run['run_id']).glob('*.docx'))
        ps=[x for x in pages if x['run_id']==run['run_id']]
        full_render=len(docs)==1 and len(ps)==1 and ps[0]['status']=='rendered'
        tools=run.get('tool_events',[])
        reads=[x['arguments'].get('path') for x in tools if x['tool']=='read_file' and isinstance(x['arguments'],dict) and 'error' not in x['reply']]
        row={k:run[k] for k in ['run_id','family_id','model','arm','trial','status','actual_cost_usd','elapsed_seconds']}
        row.update({'decision_checks':checks,'decision_pass':run['status']=='completed' and all(x['correct'] for x in checks.values()),'explicit_wrong_targeted_field':any(x['actual'] is not None and not x['correct'] for x in checks.values()),'native_documents':len(docs),'page_count':ps[0].get('pages') if full_render else None,'page_constraint_pass':ps[0]['page_constraint_pass'] if full_render else None,'artifact_constraint_pass':run['status']=='completed' and full_render and ps[0]['page_constraint_pass'],'read_operative_record':'operations/record-r2.txt' in reads,'read_registry':'project/decision-register.txt' in reads,'tool_calls':len(tools),'expert_acceptance':None,'expert_consequential_error':None})
        rows.append(row)
        row['known_task_defect']=defect['defect_id'] if row['run_id'] in affected else None
        row['independently_validated_task']=False
    groups=[];pairs=[]
    for model in sorted({j['model'] for j in cfg['jobs']}):
        for arm in ['baseline','evidence_check']:
            selected=[r for r in rows if r['model']==model and r['arm']==arm]
            cost=sum(r['actual_cost_usd'] for r in selected)
            groups.append({'model':model,'arm':arm,'planned':4,'finished':len(selected),'completed_outputs':sum(r['status']=='completed' for r in selected),'decision_passes':sum(r['decision_pass'] for r in selected),'artifact_constraint_passes':sum(r['artifact_constraint_pass'] for r in selected),'rendered':sum(r['page_count'] is not None for r in selected),'page_counts':[r['page_count'] for r in selected],'solver_cost_usd':cost,'median_run_seconds':statistics.median(r['elapsed_seconds'] for r in selected) if selected else None,'expert_accepted':None,'cost_per_expert_accepted_deliverable':None})
        for family in sorted({j['family_id'] for j in cfg['jobs']}):
            for trial in [1,2]:
                subset={r['arm']:r for r in rows if r['model']==model and r['family_id']==family and r['trial']==trial}
                if set(subset)!={'baseline','evidence_check'}:continue
                b,e=subset['baseline'],subset['evidence_check']
                pairs.append({'model':model,'family_id':family,'trial':trial,'baseline_run_id':b['run_id'],'repair_run_id':e['run_id'],'decision_delta':int(e['decision_pass'])-int(b['decision_pass']),'artifact_constraint_delta':int(e['artifact_constraint_pass'])-int(b['artifact_constraint_pass']),'page_count_delta':e['page_count']-b['page_count'] if e['page_count'] is not None and b['page_count'] is not None else None,'solver_cost_delta_usd':e['actual_cost_usd']-b['actual_cost_usd']})
    ledger=read(BASE/'ledger.json')
    previous=read(ROOT/'output/paired_v1/summary.json')['total_api_charged_or_reserved_usd']
    summary={'status':'complete_mechanical_results_human_review_pending' if len(rows)==16 and all(r['page_count'] is not None for r in rows if r['status']=='completed') else 'in_progress','metric_definitions':{'decision_pass':'Strict JSON output with every frozen targeted audit field correct; does not grade narrative logic.', 'artifact_constraint_pass':'Completed output exported to one DOCX, rendered successfully, and satisfying the requested page constraint; does not grade business correctness.'},'scope':'Exploratory prompt repair on two selected purchasing families, conflict condition only; not a representative model ranking.','planned_runs':16,'finished_runs':len(rows),'groups':groups,'paired_cells':pairs,'independent_business_families':2,'uncertainty':'Two targeted families are insufficient for a useful population-reliability estimate. Repeats and systems are not independent task families. Show paired cells instead of a misleading tight interval.','probe_reported_cost_usd':sum(x.get('actual_cost_usd',0) for x in ledger),'probe_charged_or_reserved_usd':sum(x['charged_or_reserved'] for x in ledger),'unresolved_reservations':sum(x['status'] not in ['actual','provider_rejected_before_dispatch'] for x in ledger),'campaign_charged_or_reserved_usd':previous+sum(x['charged_or_reserved'] for x in ledger),'stage_cap_usd':6,'campaign_cap_usd':25,'human_reviews_completed':0,'expert_acceptance':None,'expert_consequential_error_rate':None,'training_steps':0,'causal_limit':'Only within-probe prompt-arm comparisons share the same harness/budget. Do not compare directly with v1 as if prompt repair were the sole change.'}
    summary['known_task_defect_attempts']=sum(r['known_task_defect'] is not None for r in rows)
    summary['task_validity_status']='All attempts have a chronology defect; retain descriptive diagnostics, not validated workplace-reliability or clean repair-effect claims.' if affected else 'Independent task validation pending.'
    summary['task_defect_evidence']='task_defects.json' if defect else None
    return rows,summary

if __name__=='__main__':
    rows,summary=summarize()
    (BASE/'scores.json').write_text(json.dumps(rows,indent=2)+'\n');(BASE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['groups','paired_cells']},indent=2))
