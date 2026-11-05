"""Build auditable candidate counts and identity-masked human review queues.

All assignments here are engineering triage, not completed human labels.
"""
import collections
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/submission_audit';REVIEW=ROOT/'site/review'
def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
TAXONOMY=[
 {'id':'contract_ambiguity','name':'Deliverable contract conflicts with reference','definition':'The output contract requests two Word files while a reference also asks for an Excel tracker. Attribute the missing-tracker allegation to unresolved setup/grading scope before judging output quality.','severity':'Evaluation defect / attribution unresolved','data_fix':'No - align request, tools and grader first','priority':1},
 {'id':'invalid_serialization','name':'Final answer cannot be parsed','definition':'No higher-priority contract defect; the final response cannot be decoded under the strict output schema and no native deliverable is exported.','severity':'Delivery blocker; business error unknown','data_fix':'No first-line training claim - schema/tool repair first','priority':2},
 {'id':'approval_bypass','name':'An exception weakens mandatory approval','definition':'A proposed release or work-start path omits a mandatory approval or allows work before the stated gate. A clearly bounded proposal awaiting authorization may be acceptable.','severity':'Potential material error; domain judgment required','data_fix':'Potentially - verified authority cases, only after prompt/tool repair','priority':3},
 {'id':'unsupported_continuity','name':'Continuity plan lacks supported resources','definition':'The plan relies on unverified stock, incompatible tooling timing or an unsupported fallback to cover demand. Conditional proposals alone do not establish this failure.','severity':'Potential material error; domain judgment required','data_fix':'Potentially - dependency and coverage cases after repair controls','priority':4},
 {'id':'unsupported_eligibility','name':'Unverified eligibility stated as settled','definition':'A compliance or incentive outcome is categorical despite missing supporting determination in the supplied evidence. No external legal truth is inferred.','severity':'Potential material unsupported assertion','data_fix':'Potentially - evidence sufficiency and calibrated claims','priority':5},
 {'id':'missing_comparison','name':'Requested commercial comparison is incomplete','definition':'The cost comparison omits a necessary subtotal or complete proposed total, leaving the requested before/after analysis incomplete.','severity':'Substantive omission candidate','data_fix':'Potentially - complete worked comparisons; test scaffolding first','priority':6},
 {'id':'page_overflow','name':'Rendered document exceeds requested pages','definition':'No higher-priority issue assigned; the fixed renderer exceeds the explicit 2-3-page requirement. This is a measured harness outcome, not an honesty failure.','severity':'Usability / delivery constraint','data_fix':'No first-line training claim - render feedback and editing first','priority':7},
]
def category(r):
    j=r.get('primary_review') or {}
    if r['family_id']=='change_control':return 'contract_ambiguity'
    if r['status']!='completed':return 'invalid_serialization'
    if r['family_id']=='sourcing_approvals' and j.get('critical_error'):return 'approval_bypass'
    if r['family_id']=='supplier_exit' and (j.get('critical_error') or j.get('content_acceptable') is False):return 'unsupported_continuity'
    if r['family_id']=='ev_localization' and j.get('critical_error'):return 'unsupported_eligibility'
    if j.get('content_acceptable') is False:return 'missing_comparison'
    if r['page_constraint_pass'] is False:return 'page_overflow'
    raise ValueError('Unassigned review candidate '+r['run_id'])

def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def observable(run):
    result=[]
    for call in run['calls']:
        choice=call['response'].get('choices',[{}])[0];m=choice.get('message') or {}
        result.append({'step':call['step'],'assistant_content':m.get('content'),'tool_calls':m.get('tool_calls',[]),'finish_reason':choice.get('finish_reason')})
    return {'assistant_turns':result,'tool_events':run.get('tool_events',[]),'final_status':run['status'],'parse_error':run.get('error')}

def main():
    OUT.mkdir(parents=True,exist_ok=True);REVIEW.mkdir(parents=True,exist_ok=True)
    rows=read(ROOT/'output/paired_v1/scores.json');lookup={r['run_id']:r for r in rows}
    old=read(ROOT/'reviews/purchasing_calibration/review_assignment.json')
    exposed={r['run_id'] for r in old['cases']}
    failures=[r for r in rows if not r['known_task_defect'] and not r['provisional_acceptance']]
    counts=collections.Counter(category(r) for r in failures)
    assert len(failures)==35 and sum(counts.values())==35
    # Frozen deterministic allocation: 2 parseable, non-defective, unexposed
    # outputs per family/model, except only 1 exists for GPT change control.
    # Its spare slot is allocated to GPT shipping as a positive control.
    calibration=[];allocations=[]
    for family in sorted({r['family_id'] for r in rows}):
        for model in sorted({r['model'] for r in rows}):
            pool=[r for r in rows if r['family_id']==family and r['model']==model and r['status']=='completed' and not r['known_task_defect'] and r['run_id'] not in exposed]
            pool.sort(key=lambda r:digest('calibration-v1:'+r['run_id']))
            quota=3 if family=='shipment_manifest' and model.startswith('openai/') else 2
            picked=[]
            # Include contrasting content/critical judge outcomes where available.
            for key in ['critical_error','content_acceptable']:
                for value in [True,False]:
                    same=[r for r in pool if (r.get('primary_review') or {}).get(key) is value and r not in picked]
                    if same and len(picked)<quota:picked.append(same[0])
            for r in pool:
                if r not in picked and len(picked)<quota:picked.append(r)
            calibration.extend(picked);allocations.append({'family':family,'model':model,'count':len(picked)})
    assert len(calibration)==20 and len({r['run_id'] for r in calibration})==20
    ids={rid:'C-'+digest('submission-review:'+rid)[:8] for rid in lookup}
    fail_ids=[ids[r['run_id']] for r in sorted(failures,key=lambda r:digest('failure-order:'+r['run_id']))]
    cal_ids=[ids[r['run_id']] for r in sorted(calibration,key=lambda r:digest('cal-order:'+r['run_id']))]
    selected={r['run_id'] for r in failures+calibration};packets=[];mapping=[]
    env=read(ROOT/'output/paired_v1/execution_environment.json')
    for rid in sorted(selected):
        r=lookup[rid];run=read(ROOT/'output/paired_v1/runs'/(rid+'.json'))
        task=read(ROOT/'data/paired_v1/solver'/(run['instance_id']+'.json'))
        cid=ids[rid];dest=REVIEW/'files'/cid;dest.mkdir(parents=True,exist_ok=True);native=[]
        for i,path in enumerate(sorted((ROOT/'output/paired_v1/artifacts'/rid).glob('*')),1):
            if path.suffix not in ['.docx','.xlsx']:continue
            target=dest/f'deliverable-{i}{path.suffix}';shutil.copyfile(path,target);native.append(str(target.relative_to(REVIEW)))
            pdfs=list((ROOT/'output/paired_v1/artifact_qa/documents'/rid/path.stem).glob('*.pdf'))
            if pdfs:
                target=dest/f'deliverable-{i}.pdf';shutil.copyfile(pdfs[0],target);native.append(str(target.relative_to(REVIEW)))
        packet={'id':cid,'occupation':task['occupation'],'request':task['prompt'],'attachments':task['attachments'],'workspace':task['workspace'],'contract':{'format':task['deliverable_format'],'file_count':task['deliverable_count'],'system_prompt':env['system_prompt'],'tools':env['tools']},'submission':run.get('final'),'observable_transcript':observable(run),'native_files':native,'output_available':bool(run.get('final'))}
        packets.append(packet)
        mapping.append({'review_id':cid,'run_id':rid,'family_id':r['family_id'],'model':r['model'],'failure_queue':rid in {x['run_id'] for x in failures},'calibration_queue':rid in {x['run_id'] for x in calibration},'triage_category':category(r) if rid in {x['run_id'] for x in failures} else None,'prior_user_issue_exposure':rid in exposed,'primary_judge':r.get('primary_review')})
    public={'version':'submission-review-v1','queues':{'calibration':cal_ids,'failure':fail_ids},'taxonomy':TAXONOMY,'cases':packets,'human_reviews_completed':0}
    (REVIEW/'cases.js').write_text('window.REVIEW_DATA = '+json.dumps(public,ensure_ascii=False).replace('</','<\\/')+';\n')
    save(OUT/'private_review_key.json',mapping)
    save(OUT/'review_selection.json',{'status':'frozen_before_new_human_labels','calibration_count':20,'calibration_excludes_two_previously_reviewed_issues':True,'selection':'Purposive model/family allocation with contrasting judge labels where available; not a prevalence sample. One unavailable GPT project-management slot goes to GPT shipping.','allocations':allocations,'calibration_ids':cal_ids,'failure_ids':fail_ids,'failure_count':35,'human_full_output_labels':0})
    primary={};secondary={}
    for path in (ROOT/'output/paired_v1/judgments_v3').glob('*.json'):
        j=read(path)
        if j.get('status')!='completed':continue
        (primary if j['kind']=='primary' else secondary)[j['run_id']]=j['judgment']
    matrix=collections.Counter((primary[k]['critical_error'],secondary[k]['critical_error']) for k in primary.keys()&secondary.keys())
    calibration_diag={'sample':sum(matrix.values()),'both_no_error':matrix[(False,False)],'both_error':matrix[(True,True)],'primary_only_error':matrix[(True,False)],'secondary_only_error':matrix[(False,True)],'interpretation':'All agreements are negative. This is model-model agreement, not consequential-error detection validity or human calibration.','primary_judge_model':'openai/gpt-6.1-sol','secondary_judge_model':'anthropic/claude-sonnet-5.5','primary_critical_by_solver':[{'model':m,'flagged':sum((r.get('primary_review') or {}).get('critical_error') is True for r in rows if r['model']==m),'reviewed':sum(r.get('primary_review') is not None for r in rows if r['model']==m)} for m in sorted({r['model'] for r in rows})]}
    for c in TAXONOMY:
        c['candidate_count']=counts[c['id']];c['human_confirmed_full_output_count']=None
        examples=[r for r in failures if category(r)==c['id']];c['example_run_id']=examples[0]['run_id']
    save(OUT/'taxonomy.json',{'status':'provisional_engineering_triage_not_hand_reviewed','unit':'One primary category per flagged attempt, first matching rule; secondary issues retained in original logs. Counts do not represent independent families.','denominator':35,'exclusions':'Four known EV conflict defects omitted from this review queue, not deleted from original evidence. All 16 chronology-defective probe attempts remain outside the v1 taxonomy.','categories':TAXONOMY})
    save(OUT/'grader_diagnostics.json',calibration_diag)
    save(OUT/'setup_audit.json',{'new_scope_issue':{'family':'change_control','affected_attempts':12,'completed_outputs':6,'primary_omission_only_flags':5,'evidence':['scripts/run_paired_pilot.py:82','data/paired_v1/solver/change_control__baseline.json'],'finding':'Top-level task and runner request SOP + form (two Word files); reference Section3B also requests a tracker. A missing third Excel file is not a clean model failure without contract adjudication.','disposition':'Keep historical scores; report this new scope conflict separately. No revised acceptance number is imputed.'},'file_tools':'The solver received text/table extracts, two read-only record tools and a JSON artifact schema. DOCX/XLSX were rendered afterward; it could not create, inspect or revise native files interactively. No PPTX task was in the executed slice.','response_cap':'Five GPT change-control outputs ended with length at the 6500-token cap. Treat as setup/compute confound, not a proven training-data gap.'})
    save(OUT/'summary.json',{'source_study_runs':60,'source_task_families':5,'historical_provisional_nonacceptances_after_EV_exclusion':35,'candidate_taxonomy':dict(counts),'completed_human_full_output_reviews':0,'existing_user_issue_labels':2,'calibration_queue':20,'failure_queue':35,'distinct_review_attempts':len(selected),'judge_diagnostics':calibration_diag,'campaign_api_cost_usd':read(ROOT/'output/repair_probe_01/summary.json')['campaign_charged_or_reserved_usd'],'new_paid_calls':0,'model_selected':None})
    print(json.dumps({'candidate_categories':dict(counts),'review_packets':len(packets),'calibration':20,'failure_review':35,'human_labels':0,'judge_confusion':dict((str(k),v) for k,v in matrix.items())},indent=2))

if __name__=='__main__':main()
