"""Prepare a research decision protocol from saved evidence; no paid calls."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/research_next_step'


def read(path): return json.loads((ROOT / path).read_text())
def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n')


def main():
    ledgers = ['output/paired_v1/ledger.json', 'output/paired_v1/judge_ledger.json',
               'output/repair_probe_01/ledger.json']
    rows = [r for path in ledgers for r in read(path)]
    exposure = sum((Decimal(str(r['charged_or_reserved'])) for r in rows), Decimal(0))
    unresolved = sum(r['status'] in ['reserved', 'unresolved_charge_reserved'] for r in rows)
    mapping = {r['review_id']: r for r in read('output/submission_audit/private_review_key.json')}
    selected = read('output/submission_audit/review_selection.json')
    purchasing = [rid for rid in selected['calibration_ids'] if mapping[rid]['family_id'] in
                  ['supplier_exit', 'sourcing_approvals', 'ev_localization']]
    save('purchasing_review_batch.json', {
        'status': 'unreviewed_navigation_subset_of_existing_frozen_queue',
        'review_ids': purchasing, 'count': len(purchasing),
        'sampling_changed': False, 'model_or_judge_labels_included': False,
        'qualification_declared': False,
        'instructions': 'These are the 12 purchasing cases from the existing 20-output calibration queue. Review the complete source and output in site/review/index.html. Leave uncertain labels explicit. Export actual labels and minutes; do not infer them from the two prior issue judgments.',
    })
    verified = []
    for path in ['config/paired_protocol.v1.json', 'config/paired_v2/protocol.json', 'config/repair_probe_01.json']:
        for rel, expected in read(path)['input_hashes'].items():
            if hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Frozen input mismatch: ' + rel)
        verified.append(path)
    for row in read('data/paired_v2_1/manifest.json')['files']:
        if hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError('Chronology candidate changed: ' + row['path'])
    protocol = {
        'version': 'research-next-step-01', 'date_local': '2026-10-31',
        'status': 'draft_not_preregistered_not_executed', 'audience': 'Anthropic',
        'central_question': 'Under adequate native-file tools, do recoverable missing information and conflicting authority cause consequential artifact errors, and does a generic evidence-check prompt repair them without unnecessary holds?',
        'hypotheses': [
            'H1: matched information variants lower expert acceptance or increase adjudicated consequential errors relative to complete-information baseline.',
            'H2: evidence-check prompting improves acceptance and reduces consequential errors with the same tools and budgets, without increasing unnecessary holds.',
        ],
        'failure_to_support': 'Null or reversed paired effects do not demonstrate a better evaluation. Successful tool/prompt repair argues against a training-data expansion for that failure.',
        'order': [
            {'step': 1, 'work': 'Human calibration and failure review',
             'deliverable': 'Complete the existing 20-output calibration, beginning with its 12 purchasing cases. Classify the 35 flagged attempts from full evidence. Obtain a second qualified independent reviewer on calibration; report which taxonomy cases were double-coded.',
             'gate': 'Counts, missing labels, unknowns, defects, source/output evidence, role/experience and actual minutes are explicit. No claimed independent expertise is inferred.'},
            {'step': 2, 'work': 'Task and harness validity',
             'deliverable': 'Independently review chronology candidates and the separate three-file contract repair. Implement and smoke-test native DOCX/XLSX write, render/recalculate, inspect and revision tools in isolated task workspaces.',
             'gate': 'Source, request, artifact contract and grader agree; a human reference solution is feasible with the actual tools. Hidden truths never enter solver context.'},
            {'step': 3, 'work': 'Small development-only causal comparison',
             'deliverable': 'Conditional 36-attempt design: three purchasing development families x three information variants x two prompt arms x two repeats x one fixed Claude configuration. Both prompt arms receive identical native tools.',
             'gate': 'Model identity, prices, per-attempt budget, stage cap, tools, input hashes and analysis are frozen before execution. This is an engineering pilot, not population validation or model selection.'},
            {'step': 4, 'work': 'Fresh private transfer evaluation',
             'deliverable': 'Proposed 30 newly permissioned families: ten development and twenty untouched evaluation. Choose repairs on development only; freeze before testing. Validate the information variants and include authorized-action controls.',
             'gate': 'Rights, independent domain review and task ancestry are documented. Any tuning after test exposure requires a new untouched test. New collection and run costs must be priced separately.'},
            {'step': 5, 'work': 'Cost-based configuration choice, then conditional training',
             'deliverable': 'Compare configurations on the same fresh families and select lowest total cost per accepted deliverable among those meeting prespecified error and utility gates. Collect separate verified training families only for persistent failures.',
             'gate': 'Customer thresholds, complete expert outcomes, enough independent families and review labor costs exist. Current data do not meet these conditions.'},
        ],
        'development_pilot': {
            'status': 'conditional_design_harness_not_implemented',
            'families': ['supplier_exit', 'sourcing_approvals', 'original_supplier_landed_cost'],
            'source': 'data/paired_v2_1/solver', 'all_are_development_only': True,
            'variants': ['baseline', 'recovery', 'conflict'],
            'arms': ['baseline', 'evidence_check'], 'repeats': 2,
            'models': 1, 'attempts': 36,
            'model_policy': 'Use one verified available Claude snapshot for this within-model diagnostic; freeze exact ID and pricing before dispatch. No automatic model replacement.',
            'output_budget': None, 'call_limit': None,
            'proposed_stage_cap_usd': 6, 'cost_feasibility_verified': False,
            'warning': 'These selected/inspected families cannot supply untouched transfer evidence. Three families yield weak uncertainty even with 36 attempts.',
        },
        'analysis': {
            'acceptance': 'Accepted / all attempts on validated tasks; no output is not accepted; unreviewed is unknown, not a fabricated label.',
            'consequential_errors': 'At least one adjudicated material error / fully reviewed deliverables; report missing outputs and review coverage separately. Missing outcomes cannot count as safe.',
            'paired_effect': 'Average repeats within each family/variant/arm. Report recovery-minus-baseline and conflict-minus-baseline acceptance, then evidence_check-minus-baseline prompt effect within variant. Family is the uncertainty unit.',
            'controls': 'Authorized completion, justified holds and unnecessary holds each have prespecified eligibility/denominators. Targeted facts and page compliance remain diagnostic.',
            'judge_validity': 'Show complete human-versus-judge confusion counts, error sensitivity and false-accept counts with their denominators. Zero human-positive cases leaves sensitivity unmeasurable, regardless of total agreement.',
            'small_sample': 'Show all three development-family differences. Do not use a narrow bootstrap interval or non-significant p-value as proof of reliability/equivalence. Twenty independent zero-error families still have about a 14% one-sided 95% upper risk bound.',
            'exclusions': 'Task defects are adjudicated independently of which model benefits; retain all records, reasons, cost and a sensitivity view. No selective reruns or silent replacement of bad outputs.',
            'cost': 'API + tools + retries + measured human review/correction labor, divided by accepted deliverables. Quote data-production assumptions separately. No accepted outputs means no finite observed unit cost.',
        },
        'decision_thresholds': {'minimum_acceptance': None, 'maximum_consequential_error': None,
                                'maximum_unnecessary_hold': None, 'human_hourly_rate': None,
                                'status': 'must_be_agreed_before_configuration_selection'},
        'budget': {'campaign_cap_usd': 25, 'charged_or_reserved_usd': float(exposure),
                   'remaining_cap_usd': float(Decimal(25)-exposure), 'unresolved_reservations': unresolved,
                   'new_paid_calls': 0, 'note': 'Remaining cap is not proof a proposed study fits. Verify native-tool/image pricing and reserve before dispatch; retain uncertain charges.'},
        'research_basis': [
            {'url': 'https://www.anthropic.com/research/demystifying-evals-for-ai-agents',
             'use': 'Methodological support for isolated trials, outcome-focused grading, transcript inspection and human calibration; no imported performance values.'},
            {'url': 'https://arxiv.org/html/2606.09809v2',
             'use': 'Evidence documentation; not a validity guarantee.'},
        ],
    }
    save('protocol.draft.json', protocol)
    save('readiness.json', {
        'paid_run_ready': False, 'model_selection_ready': False, 'training_ready': False,
        'completed_now': ['Separate three-variant task/output-contract repair', 'Five contract regression tests',
                          'Fresh draft protocol and ledger reconciliation', 'Twelve-case purchasing navigation subset'],
        'requires_human_input': ['Full-output judgments and actual review time', 'Domain review of task candidates',
                                'Permission/ownership attestations', 'Customer decision thresholds'],
        'requires_engineering': ['Native-file create/render/inspect/revise loop', 'Matched-budget runner and cost reservations',
                                 'End-to-end smoke tests against expert reference outputs'],
        'frozen_protocol_hashes_verified': verified,
        'chronology_candidate_hashes_verified': True, 'human_labels_created': 0,
        'api_exposure_usd': float(exposure), 'remaining_api_cap_usd': float(Decimal(25)-exposure),
    })
    print(json.dumps({'purchasing_calibration_cases': len(purchasing),
                      'charged_or_reserved_usd': float(exposure),
                      'remaining_cap_usd': float(Decimal(25)-exposure),
                      'frozen_inputs_verified': True, 'paid_run_ready': False}))


if __name__ == '__main__': main()
