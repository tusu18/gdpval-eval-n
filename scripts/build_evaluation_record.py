"""Expose the historical task selection and run trace without new inference.

This record describes saved experiments. Proposed data interventions are not
experiments, and the human case study is not the original 60-attempt cohort.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from score_paired_pilot import score

ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    'supplier_exit': ('Supplier exit and continuity strategy',
        'A dated supply cutoff makes recovery of a critical constraint inspectable; the complete plan also exposes resource and schedule dependencies.'),
    'sourcing_approvals': ('Sourcing and price-approval workflow',
        'Named approval roles permit exact authority checks, while exception paths test whether the rule survives throughout a usable workflow.'),
    'ev_localization': ('EV battery localization recommendation',
        'A bounded volume and duration input supports an inspectable cost comparison; its conflict variant later revealed a cost-basis defect.'),
    'change_control': ('Change-control SOP and request form',
        'An explicit budget threshold supports a checkable intervention, and the SOP/form pair exposes cross-document consistency; the delivery contract was later found ambiguous.'),
    'shipment_manifest': ('Shipment manifest and savings comparison',
        'A small manifest and explicit freight rate permit arithmetic and cell-value checks on a spreadsheet deliverable.'),
}


def read(path):
    return json.loads(path.read_text())


def build(root=ROOT):
    root = Path(root)
    protocol = read(root/'config/paired_protocol.v1.json')
    rubrics = {r['id']: r for r in read(root/'data/paired_v1/grader/rubrics.json')}
    evidence = read(root/'output/assignment_final/evidence.json')
    summary = read(root/'output/paired_v1/summary.json')
    execution = read(root/'output/paired_v1/execution_environment.json')
    retained_runner_hash = hashlib.sha256((root/'scripts/run_paired_pilot.py').read_bytes()).hexdigest()
    selection = []
    source_paths = {'config/paired_protocol.v1.json', 'data/paired_v1/grader/rubrics.json',
                    'data/paired_v1/selection_audit.json', 'output/paired_v1/summary.json',
                    'output/assignment_final/evidence.json', 'output/paired_v1/execution_environment.json', 'scripts/run_paired_pilot.py',
                    'scripts/build_paired_pilot.py', 'scripts/score_paired_pilot.py'}
    for family, (name, rationale) in TASKS.items():
        path = f'data/paired_v1/solver/{family}__baseline.json'
        task = read(root/path)
        rubric = rubrics[family]
        selection.append({
            'family_id': family, 'task_name': name, 'source_task_id': task['source_task_id'],
            'occupation': task['occupation'],
            'deliverable': f"{task['deliverable_count']} {task['deliverable_format'].upper()} file(s) under the study contract",
            'why_selected': rationale,
            'variant_changes': {
                'location': rubric['where'], 'baseline': rubric['old'],
                'recovery': rubric['missing'], 'conflict': rubric['stale'],
                'operative_record': rubric['record'], 'unapproved_draft': rubric['draft']},
            'solver_inputs': [f'data/paired_v1/solver/{family}__{v}.json' for v in ('baseline','recovery','conflict')],
            'human_case_study_included': family in ('supplier_exit', 'sourcing_approvals')})
        source_paths.update(selection[-1]['solver_inputs'])
    attempts = []
    for path in sorted((root/'output/paired_v1/runs').glob('*.json')):
        run = read(path)
        raw_path = path.relative_to(root).as_posix()
        input_path = f"data/paired_v1/solver/{run['instance_id']}.json"
        input_hash = hashlib.sha256((root/input_path).read_bytes()).hexdigest()
        if input_hash != run['input_sha256']:
            raise ValueError('Historical run input hash mismatch: '+run['run_id'])
        if run['protocol_sha256'] != hashlib.sha256((root/'config/paired_protocol.v1.json').read_bytes()).hexdigest():
            raise ValueError('Historical run protocol hash mismatch: '+run['run_id'])
        result = score(run, rubrics[run['family_id']])
        confounds = []
        if run['family_id'] == 'ev_localization' and run['variant'] == 'conflict':
            confounds.append('Cost-basis defect: volume mutation also changes a coupled comparison assumption; not a clean model-failure contrast.')
        if run['family_id'] == 'change_control':
            confounds.append('Delivery-contract ambiguity: study requests two DOCX files while the source also calls for an Excel tracker.')
        attempts.append({
            **{k:run[k] for k in ('run_id','instance_id','family_id','model','variant','trial','status')},
            'source_task_id': rubrics[run['family_id']]['source'],
            'input_path': input_path, 'input_sha256': input_hash,
            'output_path': raw_path,
            'output_location': 'final contains structured artifact specifications; calls and tool_events retain the transcript. A missing final is an unsuccessful attempt, not an accepted deliverable.',
            'narrow_fact_pass': result['decision_pass'],
            'failure_attribution': 'No failure on narrow fact checks; content acceptance is separate.' if result['decision_pass'] else run['status'],
            'evaluation_confounds': confounds,
            'reported_solver_cost_usd': run.get('actual_cost_usd'),
            'elapsed_seconds': run.get('elapsed_seconds')})
        source_paths.add(raw_path)
    return {
        'schema': 'assignment-evaluation-record-v1',
        'scope': 'Historical source-derived diagnostic evaluation plus a separate five-output qualitative human case study. Not an official unchanged GDPval run.',
        'selection': selection,
        'selection_limits': [
            'Five purposively selected families from a 15-task preflight pool; three purchasing, one project-management and one shipping task. This is not representative occupational coverage.',
            'Selection favored readable sources and a bounded critical-fact intervention. Deferred tasks required external retrieval or fuller source/standards validation; two tasks were quarantined for source-data inconsistencies. See the complete selection audit.',
            'Excludes broad professional coverage, live web search, open-ended clarification with a human, long-term workplace history and unrestricted desktop work. Text extraction and supplied rendering reduce visual/navigation difficulty.',
            'The five completed human reviews cover only supplier_exit and sourcing_approvals. They were selected post hoc and purposively, not sampled to estimate a failure rate.',
            'Public-source pretraining exposure is unknown. All source families and variants are evaluation-only. Fresh rights-cleared training or private evaluation families remain a proposal.'],
        'common_input_changes': [
            'All three variants use source text/table extracts, shared workspace instructions, a registry, an approved revision-2 record and a newer unapproved revision-3 draft. Even baseline already has both records available through the tools.',
            'Recovery replaces one operative fact in the brief or extracted attachment with a workspace pointer. Conflict substitutes its draft value and adds working notes copied from the unapproved draft; the registry identifies the operative source.',
            'The model returns facts, evidence, artifact specifications, assumptions and unresolved questions as JSON. A local renderer creates DOCX/XLSX files afterward; the original solver cannot inspect or revise those native files.',
            'Additional instructions fix the EV policy assumptions to the historical scenario and require a blank or explicitly illustrative change-request form because no actual event was supplied.',
            protocol['generation']],
        'method': {
            'design': '5 families × 3 variants × 2 models × 2 attempts = 60 attempts. Related variants/repeats are not independent tasks.',
            'models': protocol['models'], 'reasoning_effort': protocol['reasoning_effort'],
            'max_completion_tokens_per_call': protocol['max_completion_tokens_per_call'],
            'max_calls_per_run': protocol['max_calls_per_run'],
            'max_input_bytes_per_call': protocol['max_input_bytes_per_call'],
            'temperature': 'No value recorded in the frozen protocol. The retained runner omits it; exact historical runner bytes have not been recovered.',
            'generation_seed': 'No model generation seed recorded in the frozen protocol. Seed 20261030 only shuffles run order.',
            'provider_routing': 'The retained runner uses OpenRouter with fixed vendor order, fallbacks disabled and required parameters enforced; these implementation details are not certified against the original runner hash. Frozen protocol price ceilings: $2/M input and $10/M completion tokens.',
            'tools': protocol['tools'], 'tool_access': protocol['tool_access'],
            'output_workflow': 'Structured specifications rendered after generation; this is distinct from the later native-file extension.',
            'solver_exclusions': 'No reference answer, private gold, grading rubric, other run output or later human label is supplied to the original solver.',
            'protocol_path': 'config/paired_protocol.v1.json',
            'source_revision': protocol['source_revision'],
            'code_provenance': 'The saved execution record names runner hash '+execution['runner_sha256']+
                '; the retained runner hash is '+retained_runner_hash+
                '. They differ. Protocol and per-run input hashes match; current runner code is supplied for inspection, not claimed to be byte-identical to the original execution.',
            'execution_environment_path': 'output/paired_v1/execution_environment.json'},
        'grading': {
            'narrow_checks': protocol['primary_metric'],
            'file_checks': 'Local renderer page counts and spreadsheet values are separate artifact checks. Renderer-related length issues do not alone establish a content or honesty failure.',
            'model_review': 'Supplemental v3 content reviews used GPT-6.1 Sol, with a Claude Sonnet 5.5 subset. Earlier incomplete-input judge versions were invalidated; their charges remain recorded.',
            'human_review': 'Five selected complete extracted-text outputs: task/source defect, usability without substantive correction and consequential business error. One project-owner reviewer; expertise and independence unspecified; review minutes unknown; no human native-layout validation.',
            'judge_validation_scope': 'Original Gemini comparison eligible on only three of the five human-reviewed outputs: two agree on both endpoints; Case C-9d21debd is a false accept and a missed consequential error relative to the reviewer. No general accuracy/sensitivity claim.',
            'failure_attribution': 'Keep infrastructure/transport, protocol/output failures, task or evaluation defects, layout checks and substantive human findings separate. Do not convert automated flags into manually confirmed failures.'},
        'data_opportunities': [
            {'category': 'Tooling release not gated on bridge supply',
             'observed_failure': 'Two reviewed outputs schedule tooling transfer before their proposed bridge supply ends. Both outputs come from the same supplier-exit source family; the single-tool dependency is a reviewer assumption.',
             'capability_hypothesis': 'Carrying a shared resource dependency through an entire conditional schedule.',
             'proposed_data': 'Fresh licensed or commissioned source inventories, bridge/no-bridge scenarios, verified coverage, complete transition plans, correction pairs and reviewer rationales. Include genuinely available duplicate tooling and adequate stock as valid proceed controls.',
             'future_test': 'On untouched task families, compare the same model before and after a prompt/tool repair; count human-confirmed premature releases, unsupported coverage claims and unnecessary holds, alongside acceptance and review/correction cost. Only test SFT/RL on separate lineages if verified failures persist.',
             'status': 'Data value is a hypothesis; no repair or training gain demonstrated.'},
            {'category': 'Provisional release omits required Finance approval',
             'observed_failure': 'One reviewed output states the three-role rule but gives an urgent provisional-release instruction naming only Program and Purchase. The correct rule elsewhere is counterevidence, not proof that the conflicting route is safe.',
             'capability_hypothesis': 'Applying mandatory approval authority consistently to exception paths while permitting authorized work.',
             'proposed_data': 'Fresh approved policies, conflicting drafts, valid fast-track permissions, invalid bypasses, complete corrected workflows, preference pairs and reviewer rationales grounded in operative actions.',
             'future_test': 'On untouched task families, check missed approval violations and false blocks on authorized releases, plus whole-output acceptance and correction cost. Compare prompt/tool repairs first; any later training intervention uses separate families and a frozen human-checked rubric.',
             'status': 'Data value is a hypothesis; no implemented bypass, spending loss or training gain observed.'}],
        'non_training_fixes_first': ['Connection/provider errors: repair and retest infrastructure.',
            'Missing native tools or artifact inspection: repair execution conditions.',
            'Ambiguous delivery contracts or coupled factual mutations: repair and independently check the task.',
            'Invalid or unsupported judge verdicts: repair measurement and compare with human judgments.'],
        'cost': {'original_evaluation_and_judging_usd': summary['total_api_reported_cost_usd'],
                 'all_recorded_stages_usd': evidence['cost']['reported_cumulative_usd'],
                 'unresolved_charge_records': evidence['cost']['unresolved_charge_records'],
                 'scope': evidence['cost']['scope'], 'human_labor_usd': None,
                 'cost_per_accepted_deliverable': None, 'new_api_calls_for_this_update': 0},
        'attempt_counts': dict(Counter(r['status'] for r in attempts)),
        'attempts': attempts,
        'source_hashes': {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(source_paths)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = build(args.root)
    path = args.root/'output/assignment_final/evaluation-record.json'
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'output': str(path), 'tasks': len(result['selection']), 'attempts': len(result['attempts']), 'new_api_calls': 0}))


if __name__ == '__main__':
    main()
