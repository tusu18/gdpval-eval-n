"""Current paired-study evidence, with engineering recovery outside the headline."""
import json
from collections import Counter
from pathlib import Path
from run_completion_and_pairs import read,write,sha,utc
from summarize_native_study import summarize
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/current_study_06'
STAGES=('native_workflow_01','native_transport_02','native_completion_03','native_completion_07','paired_native_08')
def main():
    stages=list(STAGES)+(['native_backoff_probe_09'] if (ROOT/'config/native_backoff_probe_09.json').exists() else [])
    audits={s:summarize(ROOT/'output'/s,ROOT/'config'/(s+'.json')) for s in stages}
    pairs=[];a=audits['paired_native_08'];cfg=read(ROOT/'config/paired_native_08.json')
    by={r['run_id']:r for r in a['runs']}
    for family in sorted({j['family_id'] for j in cfg['jobs']}):
        members={}
        for j in [j for j in cfg['jobs'] if j['family_id']==family]:
            r=by.get(j['run_id']);members[j['condition']]={'run_id':j['run_id'],'execution_status':r['status'] if r else 'unattempted',
                'mechanical_attribution':r['mechanical_attribution'] if r else 'unattempted',
                'native_submitted':r['status']=='submitted' if r else None,'human_accepted':None,'consequential_error':None,
                'reported_api_cost_usd':r['reported_api_cost_usd'] if r else None}
        pairs.append({'family_id':family,'members':members,'both_submitted':all(x['native_submitted'] is True for x in members.values()),'human_paired_difference':None})
    grader=read(ROOT/'output/grader_checks_05/summary.json') if (ROOT/'output/grader_checks_05/summary.json').exists() else {'planned':56,'attempted':0,'received':0,'reported_api_cost_usd':0,'unresolved_charge_records':0,'human_calibration_agreement':None,'status':'approval_pending'}
    historical=audits['native_workflow_01']['cost']['reported_prior_usd']
    stage_costs={s:a['cost']['reported_new_usd'] for s,a in audits.items()}
    probe=None
    if 'native_backoff_probe_09' in audits:
        probe_audit=audits['native_backoff_probe_09'];event_path=ROOT/'output/native_backoff_probe_09/transport_events.jsonl'
        events=[json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
        retried={e['request_sha256'] for e in events if e['will_retry']}
        received={e['request_sha256'] for e in events if e['status']=='received'}
        probe={'config':'config/native_backoff_probe_09.json','planned_attempts':1,'finished_attempts':probe_audit['finished_attempts'],
            'submitted_attempts':probe_audit['submitted_attempts'],'logical_requests_retried':len(retried),'retried_requests_with_a_received_response':len(retried&received),
            'extra_network_attempts':sum(e['will_retry'] for e in events),'reported_api_cost_usd':probe_audit['cost']['reported_new_usd'],
            'included_in_paired_results':False,'business_quality':None,
            'limitation':'One selected post-hoc engineering probe, not a model-quality or transport-reliability estimate. No retry observed means live recovery was not exercised.'}
    result={'schema':'current-paired-development-v1','updated_at':utc(),
        'submission_engineering_line':'Native-file harness built and validated; first live pass failed mainly on provider errors.',
        'fixed_model':cfg['models'][0]['id'],'paired_families':len(pairs),'paired_planned_attempts':len(cfg['jobs']),
        'paired_finished_attempts':a['finished_attempts'],'paired_submitted_attempts':a['submitted_attempts'],
        'paired_mechanical_outcome_counts':dict(Counter(r['mechanical_attribution'] for r in a['runs'] if r['status']!='running')),
        'pairs_with_both_submitted':sum(p['both_submitted'] for p in pairs),'pairs':pairs,
        'paired_execution_complete':a['complete'],'human_reviewed_outputs':0,'human_acceptance':None,'paired_acceptance_difference':None,
        'consequential_errors':None,'judge_human_agreement':None,
        'cost':{'historical_usd':historical,'stages_usd':stage_costs,'grader_usd':grader['reported_api_cost_usd'],
            'reported_cumulative_usd':historical+sum(stage_costs.values())+grader['reported_api_cost_usd'],
            'reported_this_continuation_usd':stage_costs['native_completion_03']+stage_costs['native_completion_07']+stage_costs['paired_native_08']+stage_costs.get('native_backoff_probe_09',0)+grader['reported_api_cost_usd'],
            'unresolved_charge_records':sum(a['cost']['unresolved_records'] for a in audits.values())+grader['unresolved_charge_records'],
            'human_labor_usd':None,'cost_per_accepted_deliverable':None},
        'grader':grader,'engineering_recovery':{s:{k:a[k] for k in ('planned_attempts','started_attempts','finished_attempts','submitted_attempts','complete')} for s,a in audits.items() if s!='paired_native_08'},
        'request_recovery_probe':probe,
        'paired_config':'config/paired_native_08.json','transport_amendment':cfg['amendment_reason'],
        'actual_pair_contrast':'Foreground brief/reference agrees with authoritative facts versus foreground misinformation; both versions retain the same approved and draft workspace records. This does not isolate the presence of conflict alone.',
        'pair_equivalence_audit':'output/current_study_06/paired_task_equivalence_audit.json',
        'frozen_inputs_unchanged':all(a['frozen_inputs_unchanged'] for a in audits.values()),
        'protected_historical_records_unchanged':all(a['protected_historical_records_unchanged'] for a in audits.values()),
        'interpretation':cfg['interpretation'],
        'pending':['Full-output human calibration and task-defect adjudication.','Independent validation of constructed expectations and task realism.','Fresh permissioned source families before held-out generalization claims.','Human-verified residual failures before SFT/RL or a training-effect claim.'],
        'model_ranking':None,'training_gain':None}
    write(OUT/'summary.json',result)
    print(json.dumps({'paired_finished':result['paired_finished_attempts'],'paired_submitted':result['paired_submitted_attempts'],'cost':result['cost']}));return result
if __name__=='__main__':main()
