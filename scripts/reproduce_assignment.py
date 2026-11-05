"""Recompute take-home counts from saved local evidence; never calls an API.

This entry point uses Python's standard library. It runs from the repository or
the extracted handoff's code directory and does not mutate recorded experiments.
"""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(root, pattern):
    return [read(p) for p in sorted(root.glob(pattern))]


def ledger_cost(rows):
    total=0.0
    for row in rows:
        amount=row.get('actual_cost_usd')
        if amount is None:continue
        if type(amount) not in (int,float) or not math.isfinite(amount) or amount<0:
            raise ValueError('Invalid recorded API charge')
        total+=amount
    return total


def source_hashes_explained(root, saved, recomputed):
    """Require exact bytes or an explicitly hash-bound package redaction."""
    if set(saved)!=set(recomputed):return False
    source_map_path=root/'SOURCE_MAP.json'
    source_map=({r['project_path']:r for r in read(source_map_path)['files']}
                if source_map_path.is_file() else {})
    for path,original in saved.items():
        actual=recomputed[path]
        if original==actual:continue
        entry=source_map.get(path,{})
        if (entry.get('source_sha256')!=original or entry.get('packaged_sha256')!=actual or
            entry.get('transformation')!='Provider account identifier redacted; substantive evidence unchanged.'):
            return False
    return True


def recompute(root):
    root = Path(root).resolve()
    scorer = module_at(root/'scripts/score_paired_pilot.py', 'recorded_decision_scorer')
    runs = records(root, 'output/paired_v1/runs/*.json')
    rubrics = {r['id']: r for r in read(root/'data/paired_v1/grader/rubrics.json')}
    scored = [scorer.score(r, rubrics[r['family_id']]) for r in runs]
    occupations = {read(p)['occupation'] for p in (root/'data/paired_v1/solver').glob('*.json')}
    reviews = records(root, 'output/paired_v1/judgments_v3/*.json')
    primary = {r['run_id']:r['judgment'] for r in reviews if r['status']=='completed' and r['kind']=='primary'}
    secondary = {r['run_id']:r['judgment'] for r in reviews if r['status']=='completed' and r['kind']=='secondary'}
    shared = primary.keys() & secondary.keys()
    historical = {
        'attempts':len(runs), 'source_families':len({r['family_id'] for r in runs}),
        'occupations':len(occupations), 'models':len({r['model'] for r in runs}),
        'parseable_outputs':sum(r['status']=='completed' for r in runs),
        'structured_decision_passes':sum(r['decision_pass'] for r in scored),
        'explicit_wrong_targeted_values':sum(r['explicit_wrong'] for r in scored),
        'primary_model_reviews':len(primary), 'secondary_model_reviews':len(secondary),
        'critical_label_shared_negatives':sum(not primary[k]['critical_error'] and not secondary[k]['critical_error'] for k in shared),
        'critical_label_shared_positives':sum(primary[k]['critical_error'] and secondary[k]['critical_error'] for k in shared),
        'known_ev_conflict_defect_attempts':sum(r['family_id']=='ev_localization' and r['variant']=='conflict' for r in runs),
        'scope':'Structured field checks and model reviews, not human acceptance.'}
    native = records(root, 'output/paired_native_08/runs/*.json')
    members = defaultdict(dict)
    for r in native:
        if r['condition'] in members[r['family_id']]:
            raise ValueError('Duplicate fixed-study family/condition')
        members[r['family_id']][r['condition']] = r['status']=='submitted'
    extension = {
        'attempts':len(native), 'finished':sum(r['status']!='running' for r in native),
        'submitted':sum(r['status']=='submitted' for r in native),
        'complete_pairs':sum(set(m)=={'baseline','conflict'} and all(m.values()) for m in members.values()),
        'status_counts':dict(Counter(r['status'] for r in native)),
        'scope':'Fixed-model foreground-misinformation development extension; submission is not acceptance.'}
    judge = records(root, 'output/grader_checks_05/runs/*.json')
    cohorts = {}
    for cohort in sorted({r['cohort'] for r in judge}):
        rows=[r for r in judge if r['cohort']==cohort]
        cohorts[cohort] = {'attempted':len(rows), 'received':sum(r['status']=='received' for r in rows),
            'raw_evidence_valid':sum((r.get('assessment') or {}).get('status')=='automated_assessment_not_human_acceptance' for r in rows)}
    ledger_paths = ['output/paired_v1/ledger.json','output/paired_v1/judge_ledger.json','output/repair_probe_01/ledger.json']
    ledger_paths += ['output/'+stage+'/ledger.json' for stage in ('native_workflow_01','native_transport_02','native_completion_03','native_completion_07','paired_native_08','native_backoff_probe_09','grader_checks_05')]
    costs={p:ledger_cost(read(root/p)) for p in ledger_paths}
    historical_total=sum(costs.values())
    reference=read(root/'output/current_study_06/summary.json')
    expected=read(root/'output/paired_v1/summary.json')
    checks={
        'historical_run_count':historical['attempts']==expected['saved_runs'],
        'historical_primary_review_count':len(primary)==expected['review']['valid_primary'],
        'historical_secondary_review_count':len(secondary)==expected['review']['valid_secondary'],
        'paired_finished_count':extension['finished']==reference['paired_finished_attempts'],
        'paired_submitted_count':extension['submitted']==reference['paired_submitted_attempts'],
        'complete_pair_count':extension['complete_pairs']==reference['pairs_with_both_submitted'],
        'prior_stage_cost_matches_saved_ledgers':abs(historical_total-reference['cost']['reported_cumulative_usd']) < 1e-8,
    }
    robustness=None
    robustness_cfg=root/'config/judge_robustness_10.json'
    if robustness_cfg.exists():
        import sys
        sys.path.insert(0,str(root/'scripts'))
        analyzer=module_at(root/'scripts/analyze_judge_robustness_10.py','grader_robustness_offline')
        robustness=analyzer.build(root=root)
        saved_audit=root/'output/judge_robustness_10/audited_summary.json'
        if saved_audit.exists():
            audit_reference=read(saved_audit)
            for key in ('completion','raw','sensitivity','family','injection','normalization','cost','recovery','first_attempt_provenance'):
                if key in audit_reference or key in robustness:
                    checks['grader_robustness_'+key+'_matches_recomputed']=audit_reference.get(key)==robustness.get(key)
        ledger_path='output/judge_robustness_10/ledger.json'
        ledger_paths.append(ledger_path)
        costs[ledger_path]=ledger_cost(read(root/ledger_path))
    total=sum(costs.values())
    human=None
    evidence_script=root/'scripts/assignment_evidence.py'
    if evidence_script.exists():
        # The optional integration has no network client. Its source and saved
        # human exports are bundled, including unknown/disputed labels.
        import sys
        sys.path.insert(0, str(root/'scripts'))
        integrated=module_at(evidence_script,'assignment_evidence_offline').build(root=root)
        human=integrated.get('human')
        checks['integrated_report_cost_matches_saved_ledgers']=abs(total-integrated['cost']['reported_cumulative_usd']) < 1e-8
        saved_evidence=root/'output/assignment_final/evidence.json'
        if saved_evidence.exists():
            published=read(saved_evidence)
            for key in ('historical','extension','human','cost','readiness'):
                checks['published_'+key+'_matches_recomputed']=published[key]==integrated[key]
            if published.get('review_plan') is not None or integrated.get('review_plan') is not None:
                checks['published_review_plan_matches_recomputed']=published.get('review_plan')==integrated.get('review_plan')
    proposed_controls=None
    if (root/'config/judge_controls_11.proposed.json').is_file():
        controls=module_at(root/'scripts/build_judge_controls_11.py','proposed_judge_controls_offline')
        proposed_controls=controls.inspect(root=root)
        checks['proposed_controls_invariants_pass']=(proposed_controls['status']=='prepared_not_run'
            and proposed_controls['executed_requests']==0 and proposed_controls['human_validated_cases']==0)
    evaluation_record=root/'output/assignment_final/evaluation-record.json'
    if evaluation_record.is_file():
        recorder=module_at(root/'scripts/build_evaluation_record.py','historical_evaluation_record_offline')
        checks['task_and_attempt_record_matches_frozen_inputs']=read(evaluation_record)==recorder.build(root=root)
    supplement=root/'output/strengthening_13'
    if (supplement/'lossless-audit.json').is_file():
        audited=read(supplement/'lossless-audit.json')
        new_audit=module_at(root/'scripts/audit_lossless_quotes_13.py','lossless_secondary_offline').build(root=root)
        checks['lossless_quote_audit_matches_recomputed']=(
            {k:v for k,v in audited.items() if k!='source_hashes'}==
            {k:v for k,v in new_audit.items() if k!='source_hashes'})
        checks['lossless_audit_source_hashes_explained']=source_hashes_explained(root,audited['source_hashes'],new_audit['source_hashes'])
    if (supplement/'evidence-reconciliation.json').is_file():
        reconciliation=module_at(root/'scripts/build_strengthening_13.py','triage_reconciliation_offline').build(root=root)
        checks['automated_queue_and_human_scope_reconciled']=read(supplement/'evidence-reconciliation.json')==reconciliation
    if (supplement/'inspection-summary.json').is_file():
        inspection=module_at(root/'scripts/inspection_pilot_13.py','inspection_pilot_offline').inspect(root=root)
        checks['inspection_readiness_matches_saved_evidence']=read(supplement/'inspection-summary.json')==inspection
        checks['inspection_tools_and_frozen_inputs_pass']=inspection['offline_tool_checks_pass'] and inspection['visual_integrity_qa_complete']
    judge_gap_path=root/'output/strengthening_14/judge-gap.json'
    if judge_gap_path.is_file():
        judge_gap=module_at(root/'scripts/build_judge_gap_14.py','descriptive_judge_gap_offline').build(root=root)
        checks['descriptive_judge_gap_and_null_result_recomputed']=read(judge_gap_path)==judge_gap
    return {'schema':'assignment-offline-reproduction-v1','network_calls':0,
        'historical':historical,'extension':extension,'grader_cohorts':cohorts,
        'grader_robustness':robustness,
        'proposed_judge_controls':proposed_controls,
        'reported_api_cost_usd':total,'cost_components':costs,
        'cost_scope':{'meaning':'Provider-reported cost of the explicitly listed completed study stages; not a live account balance or reconciled invoice.',
                      'covered_ledgers':ledger_paths,'grader_robustness_included':robustness is not None,
                      'additional_stages_ingested':robustness is not None},
        'unresolved_charge_records_as_recorded':reference['cost']['unresolved_charge_records'] +
             (sum(r.get('status')!='actual' or r.get('actual_cost_usd') is None for r in read(root/'output/judge_robustness_10/ledger.json')) if robustness is not None else 0),
        'human':human,'consistency_checks':checks,'all_consistency_checks_pass':all(checks.values()),
        'limits':['Recomputes recorded observations; does not rerun model inference, rendering or domain review.',
                  'Cost covers only the listed stages. Judge robustness is diagnostic, not human accuracy or calibration. Cost is not a reconciled invoice or live account total.',
                  'Human labor remains separately measured.',
                  'New controlled-document cases and their comparison schedule are unrun author proposals, not measured judge performance.',
                  'Saved assistant/model labels are never converted to human labels.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    here=Path(__file__).resolve().parent
    parser.add_argument('--root',type=Path,default=here.parent if here.name=='scripts' else here)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(); result=recompute(args.root)
    output=args.output or args.root/'reproduced-results.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(output),'checks_pass':result['all_consistency_checks_pass'],
        'historical_attempts':result['historical']['attempts'],'paired_submissions':result['extension']['submitted'],
        'reported_api_cost_usd':result['reported_api_cost_usd'],'network_calls':0}))
    if not result['all_consistency_checks_pass']:
        raise SystemExit('Saved reference values differ from recomputed counts; inspect the output.')


if __name__=='__main__':main()
