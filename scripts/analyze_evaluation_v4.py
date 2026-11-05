"""Describe provisional judgments and scoped human reviews without pooling them."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v4'

def read(p,default=None): return json.loads(p.read_text()) if p.exists() else default

def review_description(review,task):
    criterion=review.get('criterion_review',{})
    correction_status='endorsed' if review.get('minimum_correction_endorsed') is True else 'not recorded'
    correction='Endorsed minimum correction: '+json.dumps(review.get('endorsed_minimum_correction'),ensure_ascii=False)
    if review.get('minimum_correction_status')=='not_required_for_original_task_acceptance_on_this_issue':
        correction_status='not required for acceptance on this issue'
        correction='Required correction: none for acceptance on the reviewed issue. Zero/missing-pack handling is an optional robustness improvement; the changed-input defect and raw rubric failure remain documented.'
    return [
        f"{criterion.get('criterion_id','Unspecified criterion')} / {task.get('title',review['task_id'])} — {task.get('cohort',review.get('original_execution_cohort','cohort unspecified'))}",
        'Scope: '+str(review.get('review_scope','Not recorded.')),
        'User classification: '+str(criterion.get('user_classification'))+'; acceptance decision: '+str(review.get('acceptance_decision'))+'; minimum correction: '+correction_status+'.',
        correction,
        'Review limits: '+str(review.get('review_mode'))+'; background: '+str(review.get('reviewer_domain_expertise'))+'; self-reported active minutes: '+str(review.get('review_minutes'))+'; expert validation: '+str(review.get('expert_validation'))+'; blind calibration label: '+str(review.get('blind_calibration_label'))+'.',
        'Prior exposure: '+str(review.get('prior_exposure')),
        'Record: '+review['record_path']]

def main():
    report=read(OUT/'report.json');rubric=read(ROOT/'data/evaluation_v4/project-rubrics.json')
    validation=read(OUT/'assessments/validation.json',{'checks':[]})
    valid={x['task_id']:x for x in validation['checks']}
    context_notes=read(ROOT/'docs/evaluation_v4/assessment-context.json',{})
    tasks_by_id={r['task_id']:r for r in report['tasks']}
    selected_ids=set(tasks_by_id)
    new_v4_ids={t['task_id'] for t in rubric['tasks']}
    human_reviews=[]
    for p in sorted((OUT/'human-reviews').glob('*.json')):
        review=read(p)
        if review.get('status')=='complete' and review.get('task_id') in selected_ids:
            human_reviews.append({**review,'record_path':str(p.relative_to(ROOT))})
    reviewed_criteria={(r['task_id'],r.get('criterion_review',{}).get('criterion_id')):r for r in human_reviews}
    order_review=reviewed_criteria.get(('1137e2bb-bdf9-4876-b572-f29b7de5e595','PRICE-03'))
    order_scope_note='PRICE-03 applicability to the original fixed-export audit remains pending human review.'
    if order_review and order_review.get('scope_decision',{}).get('required_for_original_task_acceptance') is False:
        order_scope_note='PRICE-03: the completed non-specialist, evidence-assisted user review classifies zero/missing-pack handling as an optional robustness improvement and accepts the workbook as submitted on the supplied evidence. No correction is required for acceptance on this issue. The actual changed-input defect and raw project-rubric failure remain recorded. This scope disagreement does not establish expert gold, a judge false-positive rate or judge accuracy.'
    planogram_review=reviewed_criteria.get(('0fad6023-767b-42c1-a1b3-027cd4f583cb','POG-05'))
    planogram_review_note='POG-05 remains a localized LibreOffice print finding; Microsoft Excel reproduction is untested.'
    if planogram_review and planogram_review.get('acceptance_decision')=='requires_revision_before_acceptance':
        planogram_review_note='POG-05: the completed non-specialist, evidence-assisted user review requires correction and revision before acceptance based on the observed LibreOffice clipping. The endorsed minimum correction adjusts the instructions layout to print the final paragraph fully and readably, followed by a fresh print export and Excel Print Preview. No layout correction or new print verification has been performed; Microsoft Excel reproduction remains untested. This does not establish a substantive calculation error or expert validation.'
    human_review_summary={
        'completed_reviews':len(human_reviews),
        'expert_reviews':sum(r.get('expert_validation') is True for r in human_reviews),
        'blind_reviews':sum(r.get('blind_calibration_label') is True for r in human_reviews),
        'total_review_minutes':sum(r['review_minutes'] for r in human_reviews if isinstance(r.get('review_minutes'),(int,float))),
        'record_paths':[r['record_path'] for r in human_reviews],
        'scope':'Selected diagnostic user reviews; preserve expertise, exposure and criterion scope. No population acceptance rate or judge accuracy follows from this selection.'}
    human_reviewed_tasks=len({r['task_id'] for r in human_reviews})
    human_unreviewed_tasks=len(selected_ids)-human_reviewed_tasks
    new_v4_reviews=[r for r in human_reviews if r['task_id'] in new_v4_ids]
    prior_cohort_reviews=[r for r in human_reviews if r['task_id'] not in new_v4_ids]
    revision_reviews=sum(r.get('acceptance_decision')=='requires_revision_before_acceptance' for r in human_reviews)
    accepted_reviews=sum(r.get('human_acceptance') is True for r in human_reviews)
    assessments=[];flags=[];uncertain=[];criteria=Counter();outcomes=Counter();by_class=Counter()
    for task in rubric['tasks']:
        p=OUT/'assessments'/f"{task['task_id']}.json";a=read(p)
        if not a:continue
        contract=valid.get(task['task_id'],{}).get('contract_valid',False)
        assessments.append({'task_id':task['task_id'],'title':task['title'],'path':str(p.relative_to(ROOT)),
                            'overall':a.get('overall'),'contract_valid':contract})
        if contract:
            outcomes[a['overall']]+=1
            criteria.update(c['verdict'] for c in a['criteria'])
        for c in a.get('criteria',[]):
            human_review=reviewed_criteria.get((task['task_id'],c.get('criterion_id')))
            entry={'task_id':task['task_id'],'title':task['title'],'criterion_id':c.get('criterion_id'),
                   'verdict':c.get('verdict'),'severity':c.get('severity'),'failure_class':c.get('failure_class'),
                   'reason':c.get('reason'),'human_review_question':c.get('human_review_question'),
                   'source_evidence':c.get('source_evidence',[]),'output_evidence':c.get('output_evidence',[]),
                   'counterevidence':c.get('counterevidence',[]),'coverage':c.get('coverage'),
                   'assessment_path':str(p.relative_to(ROOT)),'contract_valid':contract,
                   'human_diagnostic_requires_correction':human_review.get('criterion_review',{}).get('user_classification')=='requires_correction' if human_review else None,
                   'human_diagnostic_review_scope':human_review.get('review_scope') if human_review else None,
                   'human_diagnostic_review':human_review,
                   'expert_confirmed':bool(human_review and human_review.get('expert_validation') is True),
                   'context_review':context_notes.get(task['task_id'],{}).get(c.get('criterion_id'))}
            if c.get('verdict')=='fail':
                flags.append(entry);by_class[c.get('failure_class','unknown')]+=1
            elif c.get('verdict') in ('uncertain','not_assessed'):uncertain.append(entry)
    candidates=[f for f in flags if f['failure_class']=='substantive_business_error' and isinstance(f['severity'],int) and f['severity']>=4]
    integrity=read(OUT/'submission-integrity.json',{})
    recovery=read(OUT/'independent-checks/audit-transport-recovery.json',{})
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'inventory_counts':report['counts'],
            'submission_integrity':integrity,'transport_recovery':recovery,
            'cohorts':report['cohorts'],'new_v4_selected_tasks':len(new_v4_ids),'new_v4_frozen_criteria':sum(len(t['criteria']) for t in rubric['tasks']),
            'new_v4_assessment_records':len(assessments),'new_v4_contract_valid_assessments':sum(a['contract_valid'] for a in assessments),
            'new_v4_provisional_task_outcomes':dict(outcomes),'new_v4_criterion_counts_not_independent_samples':dict(criteria),
            'new_v4_flagged_criteria_by_class':dict(by_class),
            'new_v4_consequential_candidate_tasks':len({f['task_id'] for f in candidates}),
            'new_v4_consequential_candidates':candidates,'new_v4_all_flags':flags,'new_v4_uncertainties':uncertain,
            'assessments':assessments,'human_review_summary':human_review_summary,'human_reviews':human_reviews,
            'human_reviewed_tasks':human_reviewed_tasks,'human_unreviewed_tasks':human_unreviewed_tasks,
            'new_v4_diagnostic_reviews':new_v4_reviews,'prior_cohort_diagnostic_reviews':prior_cohort_reviews,
            'task_human_acceptance':{r['task_id']:r.get('human_acceptance') for r in human_reviews},
            'human_acceptance':None,'human_acceptance_note':f"No aggregate acceptance estimate. {len(human_reviews)} scoped diagnostic user review(s) cover {human_reviewed_tasks} task(s); {revision_reviews} require revision before acceptance and {accepted_reviews} accept on their recorded evidence and scope. Criteria outside each recorded review scope and {human_unreviewed_tasks} other tasks remain unreviewed.",
            'judge_accuracy':None,'training_benefit_demonstrated':False,
            'hypotheses':{'H1_rubric_pass_overstates_expert_acceptance':'Not tested on fresh outputs: expert acceptance labels absent.',
                'H2_judge_misses_human_confirmed_errors':'Not calibrated: selected diagnostic user reviews are scoped to surfaced findings. Representative expert or blind paired labels are absent; these selected cases cannot measure judge misses or accuracy.',
                'H3_consequential_errors_cluster_in_approval_or_dependency_tasks':'Exploratory only. Compare distinct tasks and preserve source/tool failures separately; selected mixed cohorts and provisional labels cannot establish a general clustering claim.'},
            'cost':report['cost'],
            'interpretation':[
                'Task-level descriptive evidence for a purposive slice, not a model ranking or population prevalence estimate.',
                'Frozen requirements and exact quotations improve auditability; they do not validate the judge against experts.',
                'Only contract-valid assessments enter provisional outcome counts; invalid/raw assessments and their flags remain visible.',
                'Source issues and tool problems must be distinguished from consequential output errors. A transparent hold can be appropriate behavior.',
                'Native behavior probes use disposable copies; hypothetical edited-input failures are not observed real payments or releases.',
                'The existing v3 payroll input probe and its PAY-04 diagnostic review remain in the earlier cohort, separate from new v4 consequential candidates. The controlled behavior does not establish original-sample overpayment or any actual payment; approval suppressed the warning but added no further premium.',
                f"{len(human_reviews)} completed scoped diagnostic user review(s), covering {human_reviewed_tasks} task(s), record {human_review_summary['total_review_minutes']} self-reported active minutes, {human_review_summary['expert_reviews']} expert validations and {human_review_summary['blind_reviews']} blind labels. Classification, minimum correction, acceptance basis, expertise and exposure are preserved in each review record.",
                'Only TAX-05 is reviewed for the tax task. Its endorsed correction holds other draft assumptions unchanged and keeps unresolved source questions open: bracket base $34,337; regular tax $62,453; total tax $58,146; balance due $14,954. Remaining tax criteria and correctness of the whole return are unreviewed.',
                'PAY-04 requires correction for reusable payroll: gate the premium on quartet membership AND the whole-section condition, and retain the conflict warning while those inputs contradict each other so approval alone cannot clear it. The endorsed controlled ineligible state is $0 quartet premium and $2,992.12 gross with other inputs unchanged.',
                order_scope_note,
                planogram_review_note,
                'No acceptance rate, judge-accuracy score, false-accept rate, prevalence estimate, or confidence interval is inferred from these selected diagnostic reviews. Representative expert labels remain absent; criteria and probe variants are not independent tasks.',
                'A data opportunity requires a confirmed error, a minimal corrected example, a specified intervention, and a later held-out comparison. These runs alone do not establish training improvement.'
            ]}
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    c=report['counts'];cost=report['cost']
    lines=[f"Forty-task study analysis — {result['generated_at']}", '',
      f"Inventory: {c['selected_tasks']} selected original tasks in {c['occupations']} occupations; {c['started_tasks']} started, {c['submitted_tasks']} submitted, {c['tasks_with_assessment_record']} with assessment records. {c['tasks_with_contract_valid_assessment']} tasks have at least one contract-valid assessment; seven older v2 tasks still lack one. Tasks with a completed scoped diagnostic user review: {human_reviewed_tasks}; {human_unreviewed_tasks} tasks remain unreviewed.",
      'Selection: all five public GDPval tasks in each of eight purposively selected occupations. The new twenty were fixed before their outputs. The overall study was staged after earlier findings; it is not an untouched preregistered confirmation.', '',
      'Keep three execution cohorts separate:',
      '  v2: fifteen original tasks via API, including separately recorded recoveries and extra-model attempts. First attempts submitted eleven; eventual native coverage is fifteen. Not every judgment contract is valid.',
      '  v3: five new originals via in-app Sol/Astra. Four provisional task passes and one payroll revision candidate; 41 pass, 1 fail and 1 uncertain criteria. Those criteria are not independent observations.',
      f"  v4: twenty remaining originals, requested GPT-6.1 Sol solver and separate author-hidden GPT-6 Astra judge, through the repaired builder/research harness. Same OpenAI family; served builds and app usage settings/cost unavailable. {len(assessments)} assessment records; {sum(a['contract_valid'] for a in assessments)} contract-valid. Provisional task outcomes: {dict(outcomes)}.", '',
      'What changed in the harness: logged code builders; original-source preservation and compatible import copies; real pivot/chart/filter/dropdown/print/image features; native extraction and disclosed visual coverage; public research provenance; immutable first submissions. Artificial Analysis informed tool capability and file inspection, not an Elo or leaderboard replication.', '',
      f"Native integrity: {integrity.get('new_original_tasks_submitted','pending')} new task submissions and {integrity.get('native_files','pending')} native files checked. File hashes and recorded display acknowledgements match; acknowledgements are solver attestations, not independent gaze or business-acceptance proof.",
      'Transport recovery: one audit task experienced four stream interruptions in two contexts. Four-image delivery pagination completed all 127 queued views in a new recovery context. Both native workbook revisions remained byte-identical. Initial interruptions remain separate from eventual recovered coverage; no extra original task or independent repeat was counted.', '',
      f"New v4 consequential-error candidates: {len({f['task_id'] for f in candidates})} task(s). Completed scoped diagnostic reviews: {len(new_v4_reviews)} in the new v4 cohort and {len(prior_cohort_reviews)} in earlier cohorts. Of the new v4 flagged criteria, {sum(f['human_diagnostic_review'] is not None for f in flags)} have completed diagnostic reviews and {sum(f['human_diagnostic_review'] is None for f in flags)} remain unreviewed. Raw judge grades remain unchanged. All judge flags and unresolved interpretations follow; source problems are not counted automatically as substantive business errors.",
      'The three flagged new tasks represent different findings. Tax: a saved calculation understates regular tax by $2,046 under the draft\'s own assumptions; independent arithmetic reproduction is in independent-checks/tax-regular-rate.json, and the scoped user review supports requires-correction. Order audit: original results are correct, but a disposable zero/blank case-pack edit triggers division errors under an extra robustness clause. Planogram: a final instructions line clips in LibreOffice printing; main planogram is readable, and Excel reproduction is untested. Do not describe these as three demonstrated consequential business errors.',
      order_scope_note, planogram_review_note, '',
      f"Human review: {human_review_summary['completed_reviews']} completed review(s), {human_review_summary['expert_reviews']} expert review(s), {human_review_summary['blind_reviews']} blind review(s), {human_review_summary['total_review_minutes']} self-reported active review minutes.",
      'Review limits: each completed record preserves the criterion scope, minimum correction, acceptance basis, self-reported background, active minutes and prior exposure. A scoped diagnostic review does not establish expert gold, correctness of other criteria or whole-deliverable correctness, or judge-accuracy calibration.',
      'Human review records: '+', '.join(human_review_summary['record_paths'])]
    for review in human_reviews:
        lines += ['']+review_description(review,tasks_by_id.get(review['task_id'],{}))
    for f in flags+uncertain:
        lines += ['',f"{f['title']} / {f['criterion_id']} — {f['verdict']}, {f['failure_class']}, severity {f['severity']}",str(f['reason']),
                  'Original judge review question: '+str(f['human_review_question']), 'Evidence: '+f['assessment_path']]
        if f.get('human_diagnostic_review'):
            review=f['human_diagnostic_review']
            lines.append('Completed human review: '+str(review.get('criterion_review',{}).get('user_classification'))+'; '+str(review.get('acceptance_decision'))+'; '+str(review.get('review_mode'))+'; expert validation: '+str(review.get('expert_validation'))+'. Record: '+review['record_path'])
        else:lines.append('Human review: unreviewed.')
        if f.get('context_review'):lines.append('Scope/context: '+json.dumps(f['context_review'],ensure_ascii=False))
    lines += ['', 'Earlier strongest controlled behavior case: v3 musician payroll, separate from the new v4 candidate count. With the whole-string-section eligibility condition false, enabling the quartet role added a premium; the approval switch added no further pay but suppressed the role-conflict status. The completed PAY-04 diagnostic user review classifies this controlled editable-state behavior as requiring correction, endorses the minimum correction and requires revision before acceptance for reusable payroll. Original saved payroll was not demonstrated to be overpaid, and no actual payment is established.',
      'Evidence: output/evaluation_v3/independent-checks/payroll-behavior/result.json', '',
      'Data-opportunity interpretation: classify each issue first. Repair infrastructure for tool failures, repair the task/input for missing or contradictory evidence, and consider source-grounded corrective examples and behavioral tests for confirmed substantive failures. A later held-out intervention is required before claiming better training data improves performance.', '',
      f"Cost: ${cost['known_provider_cost_usd']:.6f} confirmed API charges plus ${cost['unresolved_charge_reserve_usd']:.6f} unresolved-charge reserves = ${cost['committed_usd']:.6f} committed under the $30 ceiling. New v4 OpenRouter cost is $0. App inference cost is unavailable, not free. Task-linked costs and shared development checks are separate in costs.json and task-costs.csv.", '',
      'Hypotheses: H1 (rubric versus expert acceptance) remains untested without fresh expert acceptance labels. Selected scoped diagnostic user reviews cannot test H2 judge misses or calibrate accuracy. H3 (errors cluster around approval/dependency rules) remains exploratory; a source-grounded error outside those tasks is relevant counterevidence, not a reason to remove the task.',
      f"Still unmeasured: representative or expert acceptance, judge accuracy and false-accept rates on these fresh outputs, cost per accepted deliverable, model ranking, and causal training benefit. No score or confidence interval is inferred from these selected diagnostic cases. {human_unreviewed_tasks} other tasks and criteria outside each recorded review scope remain unreviewed; historical five-case reviews do not label them.",
      'Trace entry point: output/evaluation_v4/report.html. Assessment records, native files, tool/build histories, source hashes, external evidence and costs remain linked.']
    (OUT/'analysis.txt').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'assessment_records':len(assessments),'task_outcomes':dict(outcomes),'consequential_candidate_tasks':result['new_v4_consequential_candidate_tasks']}))

if __name__=='__main__':main()
