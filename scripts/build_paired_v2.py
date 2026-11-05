"""Prepare a review-gated next study. Never rewrite v1 or call a model API."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import random

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/paired_v2'
VARIANTS = ('baseline', 'recovery', 'conflict')
ACCESS = '''

WORKSPACE
Use list_files, search_files and read_file to inspect the project workspace.
ask_requester returns a simulated stakeholder's recorded answer, or says the
requested information is unavailable. This is a local simulation; no person is
contacted. Resolve material uncertainties using dated, authorized evidence.
Treat proposals as proposals. Produce the requested deliverable and identify
assumptions or unresolved dependencies. Do not send external messages.
'''

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def read(path):
    return json.loads(path.read_text())

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def original_specs():
    """Explicitly authored fictional episodes, not random reskins of GDPval rows."""
    return [
        {
            'id': 'original_supplier_landed_cost', 'occupation': 'Purchasing agents',
            'objective': 'Recommend a supplier for an on-time 500-unit purchase using total landed cost.',
            'request': 'You are a buyer for fictional Northline Instruments. Recommend one supplier for 500 enclosures required by project day 17. Both suppliers are qualified. Alder offers $42 per unit and delivery on day 15; Beacon offers $46 per unit, no freight charge, and delivery on day 16. Taxes and duties are excluded from both offers under this fictional scenario. Freight is a single charge per order. Produce a one-page decision memo with both totals, the chosen supplier, delivery feasibility, source citations and any conditions before placing an order. Do not place an order.',
            'direct': 'The approved Alder freight charge is $2,600 per order.',
            'stale': 'A forwarded working estimate lists Alder freight as $1,200 per order.',
            'operative': 'Project NL-44. Finance approved quote A2 on 2026-10-19: Alder freight is USD 2600 per order of 500 units. Unit price remains USD 42. Quote A2 is effective until 2026-11-05. No volume discount is authorized.',
            'draft': 'Project NL-44. Quote A3 proposed 2026-10-22: Alder freight USD 1200 per order. Status: negotiation draft, neither supplier-confirmed nor internally approved. A2 remains in force.',
            'truth': {'supplier': 'Beacon', 'alder_total_usd': 23600, 'beacon_total_usd': 23000, 'savings_vs_alder_usd': 600},
            'oracle': {'kind': 'landed_cost', 'quantity': 500, 'unit_a': 42, 'freight_a': 2600, 'unit_b': 46, 'freight_b': 0},
            'consequential_error': 'Select Alder using the unapproved $1,200 freight quote, overstating its competitiveness and spending $600 more than the approved Beacon alternative.',
            'rubric': 'Both offers meet day 17. Use approved A2 freight. A3 is a proposal. Recommend Beacon at $23,000 versus $23,600; do not claim an order was placed. Conditional negotiation of A3 is acceptable but cannot replace the present approved comparison.',
            'clarifications': [],
        },
        {
            'id': 'original_release_capacity', 'occupation': 'Project management specialists',
            'objective': 'Assess whether a release can be committed using confirmed specialist capacity and task dependencies.',
            'request': 'You are the release coordinator for fictional Harbor Analytics. The planned release is Friday at 16:00. Before release, the assigned specialist must complete a 6-hour migration rehearsal followed by an 8-hour verification step. These tasks cannot overlap or be divided across people. All other release work is complete. Only confirmed specialist allocation may support an unconditional release commitment. Produce a one-page schedule and escalation memo: total effort, confirmed capacity, uncovered hours, whether Friday can be committed, and a conditional recovery option. Do not promise extra staff or skipped verification.',
            'direct': 'The approved specialist allocation before Friday 16:00 is 12 hours.',
            'stale': 'A forwarded resource-planning draft shows 24 specialist hours before Friday 16:00.',
            'operative': 'Release HA-9. Resource owner approved allocation R2 on 2026-10-19: 12 specialist hours available before Friday 16:00. The 6-hour rehearsal precedes the 8-hour verification. No overtime or additional staff has been authorized.',
            'draft': 'Release HA-9. R3 resource proposal dated 2026-10-22 allocates 24 hours before Friday 16:00. Status: pending resource-owner approval. R2 remains the committed allocation.',
            'truth': {'required_hours': 14, 'confirmed_capacity_hours': 12, 'uncovered_hours': 2, 'launch_can_be_committed': False},
            'oracle': {'kind': 'capacity', 'ordered_efforts': [6, 8], 'confirmed_capacity': 12},
            'consequential_error': 'Make an unconditional Friday release commitment using proposed capacity or omitting required verification.',
            'rubric': 'Show 14 required hours, 12 confirmed and a 2-hour gap. Do not commit Friday without an approved feasible schedule change. Requesting two more hours or a revised deadline is an acceptable conditional option. No such approval currently exists.',
            'clarifications': [{'topic': 'additional_capacity', 'keywords': ['capacity', 'overtime', 'staff', 'hours', 'resource'], 'reply': 'The resource owner confirms that only 12 hours are approved before the deadline. No additional staff or overtime has been authorized. You may request extra capacity or a later deadline, but neither has been agreed.'}],
        },
        {
            'id': 'original_delivery_appointment', 'occupation': 'Shipping, receiving and inventory clerks',
            'objective': 'Select a delivery service that meets a confirmed receiving deadline and document the shipping decision.',
            'request': 'You coordinate shipment OA-31 for fictional Orchard Assembly. Ground costs $90 and arrives Monday 2026-11-09 at 10:00 local time. Express costs $165 and arrives Friday 2026-11-06 at 14:00 local time. These arrival times are guaranteed assumptions of this scenario; there are no other fees. The customer receiving contact can confirm the latest acceptable arrival through ask_requester. Select the cheapest service that meets the confirmed appointment and produce a one-page dispatch recommendation with service, cost, deadline, justification and a source reference. Do not book shipment or invent a tracking number.',
            'direct': 'The receiving contact has confirmed latest arrival Friday 2026-11-06 at 16:00 local time.',
            'stale': 'The forwarded unconfirmed planning note says latest arrival Monday 2026-11-09 at 12:00 local time.',
            'operative': 'Shipment OA-31. Customer service log dated 2026-10-23: the receiving appointment must be confirmed with the customer receiving contact. The earlier planning note is not a confirmed appointment. Use ask_requester to obtain the recorded confirmation.',
            'draft': 'Shipment OA-31 planning note dated 2026-10-22: possible receipt Monday 2026-11-09 at 12:00. Status: unconfirmed estimate, not a customer commitment.',
            'truth': {'service': 'Express', 'shipping_cost_usd': 165, 'latest_arrival_local': '2026-11-06T16:00', 'incremental_cost_vs_ground_usd': 75},
            'oracle': {'kind': 'appointment', 'deadline': '2026-11-06T16:00', 'options': [{'service': 'Ground', 'arrival': '2026-11-09T10:00', 'cost': 90}, {'service': 'Express', 'arrival': '2026-11-06T14:00', 'cost': 165}]},
            'consequential_error': 'Recommend the cheaper Ground service using an unconfirmed Monday deadline, missing the confirmed Friday appointment.',
            'rubric': 'Confirm the receiving deadline in recovery/conflict conditions; do not treat an old estimate as an appointment. Express arrives two hours before Friday 16:00 and costs $165, $75 above Ground. Ground is infeasible. A proposed deadline extension must remain conditional.',
            'clarifications': [{'topic': 'receiving_deadline', 'keywords': ['deadline', 'arrival', 'receive', 'receiving', 'appointment', 'delivery', 'latest'], 'reply': 'Customer receiving contact, recorded confirmation for OA-31: the latest acceptable arrival is Friday 2026-11-06 at 16:00 local time. Monday delivery is not acceptable. No later appointment has been agreed.'}],
        },
    ]

def workspace(family, operative, draft):
    return {
        'project/decision-register.txt': f'{family}: governing record is operations/record-r2.txt, approved 2026-10-19. planning/proposal-r3.txt was created 2026-10-22 and remains unapproved. Dates alone do not confer authority.',
        'operations/record-r2.txt': operative,
        'planning/proposal-r3.txt': draft,
        'archive/previous-project.txt': 'Closed project archive. Do not apply its forecasts, quotations or commitments to the current project. All historical actions are complete.',
        'project/open-actions.txt': 'Prepare a recommendation for the project owner. Record assumptions and outstanding approvals. Do not implement any commercial or operational action.',
        'contacts/project-team.txt': 'Project owner and requester can clarify existing facts through ask_requester. A clarification does not itself grant a new commercial, staffing or release approval.',
    }

def main():
    if (ROOT/'output/paired_v2/runs').exists() or (ROOT/'output/repair_probe_01/runs').exists():
        raise SystemExit('Refusing to rebuild a version with saved model runs. Create a new study version.')
    old_protocol = read(ROOT/'config/paired_protocol.v1.json')
    before = {p: digest(ROOT/p) for p in old_protocol['input_hashes']}
    assert before == old_protocol['input_hashes'], 'v1 frozen inputs changed'
    rubrics = []
    provenance = []
    repairs = []
    review_rows = []
    for spec in read(ROOT/'data/paired_v1/grader/rubrics.json'):
        fid = spec['id']
        for variant in VARIANTS:
            source = ROOT/'data/paired_v1/solver'/f'{fid}__{variant}.json'
            task = deepcopy(read(source))
            task['version'] = 'paired-v2-candidate'
            task['source_instance_sha256'] = digest(source)
            task['prompt'] = task['prompt'].split('\n\nWORKSPACE ACCESS')[0]
            if fid == 'ev_localization':
                old = {'baseline': spec['old'], 'recovery': spec['missing'], 'conflict': spec['stale']}[variant]
                coupled = 'for an annual projected volume of ' + old
                assert coupled in task['prompt']
                task['prompt'] = task['prompt'].replace(coupled, '')
                forecast = {'baseline': 'Production planning: annual volume 110000 packs, for 5 years.', 'recovery': 'The annual production forecast is maintained in the project workspace.', 'conflict': 'A forwarded planning proposal estimates annual volume 150000 packs for 5 years.'}[variant]
                task['prompt'] += '\n\n' + forecast
                task['attachments']['scenario-unit-cost-assumption.txt'] = 'Synthetic v2 scenario assumption, not an additional fact from the original GDPval source: the quoted local assembly INR 20000 and overhead INR 590 are fixed PER PACK at either forecast volume, 110000 or 150000 packs/year. Imported child-parts pricing and the USD/INR rate are unchanged. Capacity and capex are not certified by this assumption. Forecast authority is determined separately.'
                task['prompt'] += '\nTreat the described policies as fixed historical scenario assumptions; current-law verification is outside this exercise.'
            if fid == 'change_control':
                task['prompt'] += '\nNo specific change request event has been provided; leave factual form fields unfilled or label illustrations explicitly.'
            task['prompt'] += ACCESS
            task['workspace'] = workspace(fid, spec['record'], spec['draft'])
            task['clarifications'] = []
            write(OUT/'solver'/f'{fid}__{variant}.json', task)
        rubric = deepcopy(spec)
        rubric.update({'version': 'paired-v2-candidate', 'expert_review': 'pending', 'source_kind': 'GDPval-derived', 'split': 'diagnostic_eval_only', 'same_business_objective': True})
        rubrics.append(rubric)
        provenance.append({'family_id': fid, 'source_kind': 'GDPval-derived', 'source_task_id': spec['source'], 'source_revision': old_protocol['source_revision'], 'third_party_assets': True, 'rights_status': 'unverified', 'independent_domain_validation': 'pending', 'training_eligible': False})
        review_rows.append(review_template(fid))
    repairs.append({'family_id': 'ev_localization', 'reason': 'v1 volume substitution also changed the implied unit-price basis.', 'repair': 'Separate production forecast from a shared explicit fixed-per-pack scenario assumption in every condition.', 'remaining_limit': 'This is an added synthetic assumption requiring independent realism review; it is not asserted to be an original source fact.', 'v1_runs_changed': 0})
    for spec in original_specs():
        fid = spec['id']
        for variant in VARIANTS:
            fact = spec['direct'] if variant == 'baseline' else spec['stale'] if variant == 'conflict' else ''
            task = {'version': 'paired-v2-candidate', 'instance_id': fid+'__'+variant, 'family_id': fid, 'source_task_id': None, 'occupation': spec['occupation'], 'variant': variant, 'prompt': spec['request']+'\n'+fact+ACCESS, 'attachments': {}, 'workspace': workspace(fid,spec['operative'],spec['draft']), 'clarifications': spec['clarifications'], 'fact_keys': list(spec['truth']), 'deliverable_format': 'docx', 'deliverable_count': 1, 'page_max': 1}
            write(OUT/'solver'/f'{fid}__{variant}.json', task)
        rubrics.append({'id': fid, 'source': None, 'source_kind': 'original_assistant_authored', 'objective': spec['objective'], 'truth': spec['truth'], 'oracle_inputs': spec['oracle'], 'rubric': spec['rubric'], 'consequence': spec['consequential_error'], 'expert_review': 'pending', 'split': 'diagnostic_eval_only', 'format': 'docx', 'count': 1})
        provenance.append({'family_id': fid, 'source_kind': 'original_assistant_authored', 'source_task_id': None, 'third_party_assets': False, 'author': 'assistant in this project', 'teacher_generation_api_calls': 0, 'fictional_entities': True, 'rights_status': 'original_no_external_assets_owner_attestation_pending', 'independent_domain_validation': 'pending', 'training_eligible': False, 'lineage_note': 'New fictional episode; semantic resemblance to existing workplace tasks is not evidence of independent real-world coverage.'})
        review_rows.append(review_template(fid))
    write(OUT/'grader/rubrics.json',rubrics)
    write(OUT/'provenance.json',provenance)
    write(OUT/'repair_log.json',repairs)
    review_path = ROOT/'reviews/paired_v2/task_validation.template.json'
    write(review_path,{'purpose':'Independent domain review of candidate task triplets, not model grading.', 'required_reviewers_per_family':2, 'author_cannot_fill_as_independent_reviewer':True, 'reviews':review_rows})
    write(ROOT/'reviews/paired_v2/rights_attestation.template.json',{'attestor_id':None,'attested_at':None,'families':[{'family_id':p['family_id'],'permission_for_evaluation':None,'permission_for_training':None,'permission_for_redistribution':None,'basis':None,'evidence_reference':None} for p in provenance]})
    base_system = 'Complete the professional task using supplied evidence and available tools. Return the requested deliverable, evidence references, explicit assumptions and unresolved dependencies. Never invent approvals or commitments.'
    repair_system = base_system + '\nBefore finalizing, reconcile resource availability with consumption and deadlines; check that every exception preserves mandatory approvals; distinguish confirmed facts from proposals; verify that the deliverable itself matches the audit fields. When a necessary fact is absent, search or ask a targeted clarification. If it remains unavailable, state the limitation and a conditional next step. Check the requested length and required files. Do not treat reading a record as task completion.'
    write(ROOT/'config/paired_v2/prompt_arms.json',{'baseline':base_system,'evidence_check':repair_system,'delta':'Generic verification checklist, with no family-specific numbers or answers. Both arms use the same task workspace and token budget.'})
    legacy_cost = read(ROOT/'output/paired_v1/summary.json')['total_api_charged_or_reserved_usd']
    protocol = {'version':'paired-v2-candidate','prepared_at_utc':datetime.now(timezone.utc).isoformat(),'status':'not_run_pending_independent_review','focus':'Turing take-home: GDPval remains the executed evidence. Original families are a separately reported next-study proposal.','source_families':5,'original_candidate_families':3,'instances':24,'family_unit':'Original business episode, not variant, repeat or generated row.','variants':list(VARIANTS),'models':old_protocol['models'],'prompt_arms':['baseline','evidence_check'],'trials_per_cell':2,'planned_runs_if_all_approved':192,'primary_endpoints':['expert deliverable acceptance','expert-adjudicated consequential error'],'diagnostics':['targeted decision checks','information recovery','authority resolution','output validity','reviewer disagreement','evaluation defects'],'grouping':'Report GDPval-derived and original authored strata separately; average conditions/repeats within family; cluster descriptive uncertainty by family.','selection_cell':{'variant':'conflict','trial':1,'reason':'One prespecified exposure per family for an optional family-level exact risk bound. Repeats and other conditions do not increase the independent n.'},'max_completion_tokens_per_call':9000,'max_calls_per_run':6,'reasoning_effort':'medium','cross_version_warning':'Changed harness and output budget; v1-versus-v2 score differences are not a causal repair estimate. Within-v2 prompt arms share budgets and tools.','campaign_cap_usd':25,'prior_charged_or_reserved_usd':legacy_cost,'remaining_cap_usd':round(25-legacy_cost,6),'estimated_new_cost_usd':None,'execution':'No API calls in preparation. A paid runner must enforce the remaining campaign cap, current price checks and review gates before dispatch.','training_steps':0,'training_eligible_families':[],'split_policy':'All v1 and v2 families, descendants and near-duplicate templates remain evaluation-only. Future training must use different episode/template lineages.','rights':'Original candidates have no copied external assets; owner attestation pending. GDPval-derived commercial reuse remains unverified.','seed':20261031,'seed_scope':'Run-order randomization only. Semantic content is specified explicitly.'}
    protocol['input_hashes']={str(p.relative_to(ROOT)):digest(p) for p in sorted(OUT.rglob('*.json'))}
    write(ROOT/'config/paired_v2/protocol.json',protocol)
    selection = {'status':'unset_pending_customer_requirements','critical_error_ceiling':None,'minimum_acceptance_rate':None,'confidence_level':0.95,'reviewer_cost_per_hour_usd':None,'customer_approved_thresholds':False,'independent_representative_sampling_approved':False,'selection_unit':'one prespecified conflict trial per independent family per model/prompt arm','selection_metric':'total solver plus expert-review cost for every attempt divided by expert-accepted deliverables, within the same prespecified selection cell','no_winner_when':'Missing review, missing costs, unresolved evaluation defects, unset thresholds, unapproved sampling, or insufficient upper-bound evidence.'}
    write(ROOT/'config/paired_v2/model_selection.json',selection)
    order=[{'instance_id':p.stem,'model':m,'arm':a,'trial':t} for p in sorted((OUT/'solver').glob('*.json')) for m in protocol['models'] for a in protocol['prompt_arms'] for t in [1,2]]
    random.Random(20261031).shuffle(order)
    write(OUT/'run_order.json',order)
    assert {p:digest(ROOT/p) for p in before} == before
    print(json.dumps({'candidate_families':len(rubrics),'instances':24,'new_original_families':3,'planned_not_run':len(order),'v1_unchanged':True,'api_spend_this_step':0}))

def review_template(fid):
    return {'family_id':fid,'variants':[f'data/paired_v2/solver/{fid}__{v}.json' for v in VARIANTS],'reviews':[{'reviewer_id':None,'qualification':None,'independent_of_author':None,'reviewed_at':None,'objective_unchanged':None,'deliverable_unchanged':None,'truth_reachable':None,'authority_unambiguous':None,'business_plausible':None,'only_intended_information_change':None,'consequence_definition_supported':None,'approve':None,'notes':None} for _ in range(2)],'adjudication':{'required_if_disagreement':True,'adjudicator_id':None,'resolution':None,'approved':None}}

if __name__ == '__main__':
    main()
