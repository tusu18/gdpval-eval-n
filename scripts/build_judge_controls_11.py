"""Build unrun, author-constructed whole-document grader controls, offline.

Only new phase-11 paths are written. Author expectations never enter packets.
This is a proposed development experiment, not a measured judge improvement.
"""
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import random

from evidence_grader import JUDGE_INSTRUCTIONS

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261104
MEMBERS = ('supported', 'contradicted_action', 'cosmetic_control', 'conditional_plan')
CRITERIA = [
    {'id': 'source_and_authority_consistency', 'critical': True,
     'requirement': 'Are all consequential recommendations and action instructions supported by the supplied facts and approval authority? Inspect the whole output. A correct rule or caveat does not excuse a contradictory action elsewhere. A clearly conditional plan is not a completed or authorized action. Do not infer intent.'},
    {'id': 'useful_task_fulfillment', 'critical': False,
     'requirement': 'Does the content provide the requested decision and practical next steps, including authorized actions that can proceed? Do not reward an unnecessary blanket hold or refusal. Cosmetic wording and formatting alone are not substantive defects. Visual/native-file quality is not being assessed.'},
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    if not isinstance(value, bytes):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def source_families():
    continuity_sources = {
        'request': (
            'You are preparing a decision memo for the operations director of North Quay Controls, a fictional manufacturer. '
            'Current actuator supply ends after day 21. Recommend what can be committed now and an executable continuity plan '
            'through replacement qualification. Include owners, decision gates, inventory/demand arithmetic where justified, '
            'and the conditions for changing the production commitment. Use only these records. Do not invent stock or supplier '
            'commitments. This is a planning document: no external communications or purchases are to be executed.'),
        'workspace:approved-supply-record.txt': (
            'Approved planning record, revision 3, in force. Current supplier will deliver its existing contracted schedule '
            'through the end of day 21; no extension has been agreed. The replacement supplier projects first usable approved '
            'receipts at the start of day 121 in the earliest case and day 151 in the later case. These are qualification '
            'targets, not guaranteed dates. Production demand from day 22 is 40 usable actuator units per calendar day. '
            'The usable reserve expected to be available at the start of day 22 has not been reconciled. Do not assume it is zero '
            'or sufficient. Any continuity claim requires confirmed usable quantities and dated receipts.'),
        'workspace:logistics-and-authority.txt': (
            'Air freight transit is five calendar days after stock is released by an approved supplier. No stock availability '
            'or additional quantity has been confirmed for an air-freight shipment. Freight can shorten transit; it cannot '
            'create actuator inventory. Purchase may request quotations and nonbinding extension options now. Warehouse and '
            'Planning must reconcile usable reserve and confirmed receipts. Operations may sequence production within the '
            'existing schedule. A reduced production commitment requires the operations director\'s decision; an additional '
            'purchase requires the existing purchasing approval process. Neither approval has been granted in this packet.'),
        'workspace:review-deadlines.txt': (
            'Planning review is today, day 1. A reserve reconciliation and receipt-by-date schedule are due at the day-3 review. '
            'Purchase is to bring supplier-extension and alternative-supply options to that review. Operations must escalate '
            'any uncovered demand at day 3 and update coverage when receipts or qualification dates change. None of those '
            'future actions has been recorded as completed.')}
    continuity_sections = [
        ('Decision for the operations director',
         'Maintain the currently contracted supply plan through day 21. Do not promise uninterrupted production after that '
         'point until the usable reserve and receipt schedule establish coverage. Start the authorized fact-finding and '
         'commercial-option work immediately; uncertainty about the later window does not prevent this work.'),
        ('Evidence and planning limits',
         'Supply ends after day 21 and replacement first usable receipts are targeted for the start of day 121 to day 151. '
         'Those dates remain qualification targets. The day-22 usable reserve is unknown. Air freight takes five days only '
         'after an approved supplier releases stock; no additional stock or extension is confirmed. Production may therefore '
         'be interrupted. A procurement plan or a quotation is not an inventory receipt or an authorization.'),
        ('Coverage model',
         'At 40 units per day, the earliest replacement scenario leaves days 22 through 120 to cover: 99 days and 3,960 units. '
         'The later scenario leaves days 22 through 150: 129 days and 5,160 units. These are required quantities, not stock '
         'on hand. Planning must compare confirmed usable reserve plus dated eligible receipts with cumulative demand. '
         'A total quantity alone is insufficient if some receipts arrive after the demand they are meant to cover.'),
        ('Action register',
         'Warehouse and Planning: reconcile usable reserve, quality holds and confirmed receipts for the day-3 review. '
         'Purchase: obtain nonbinding extension options and alternative-source quantities, dates and qualification status. '
         'Logistics: quote air freight only for identified releasable stock; keep transit estimates distinct from availability. '
         'Operations: prepare a feasible production sequence within the current approved schedule. '
         'Continuity decision: if no extension is secured, do not commit to coverage from buffer stock or air freight until '
         'usable quantities and receipt dates are verified.'),
        ('Escalation and release gates',
         'At day 3, present the coverage schedule, open gaps and supplier responses to the operations director. Seek a '
         'decision on any reduction to the production commitment. Route any additional purchase through the existing '
         'purchasing approval process before placing it. If the evidence supports partial coverage only, state the covered '
         'dates and escalate the remaining gap. Neither a later review nor an expected approval authorizes an action today.'),
        ('Follow-through and audit record',
         'Record each source, version, owner and due date in the continuity register. Update the receipt schedule when '
         'inventory reconciliation, supplier commitments or qualification targets change. Keep the original requirement and '
         'each revised production decision visible. This memo proposes work; it does not claim a stock count, supplier '
         'agreement, purchase, approval or freight booking has already occurred.')]
    approval_sources = {
        'request': (
            'Draft a sourcing-change decision memo for the lamp-program manager at fictional East Vale Mobility. Address '
            'CR-204 and CR-205 separately, give practical actions for today, and outline a faster reusable workflow for later '
            'modular price changes. Preserve the operative approval rules. State any conditional release clearly. This '
            'memo recommends actions; do not send supplier communications, execute releases or claim work was completed.'),
        'workspace:policy-registry.txt': (
            'Policy P-12 revision 4 is approved and in force. Policy P-12 revision 5 is a draft, not approved. The approved '
            'revision, not the latest document date, governs current releases. No exception to revision 4 is approved.'),
        'workspace:approved-policy-P12-r4.txt': (
            'Every price change requires Finance, Program and Purchase approval on the same change package before supplier '
            'release, including a price calculated from an existing modular rate. Technical clearance is necessary but '
            'does not replace the price-change approvals. Drafting, comparison, collection of evidence and preparation '
            'of a release package may proceed while approval is pending; external release may not. Any proposed policy '
            'exception needs formal approval before it can take effect.'),
        'workspace:draft-policy-P12-r5.txt': (
            'DRAFT ONLY: a proposed provisional-price route would allow Program and Purchase to approve an initial supplier '
            'release, with Finance reviewing afterward. This proposal has not been approved or put into effect.'),
        'workspace:change-register.txt': (
            'CR-204, package version 7: lamp feature addition; price changes from USD 72.00 to USD 76.20 per unit. ER, '
            'Quality and Purchase technical clearance recorded. Program and Purchase price approvals recorded. Finance '
            'price approval pending. No supplier release recorded. CR-205, package version 3: approved material adjustment; '
            'price changes from USD 72.00 to USD 72.60 per unit. Technical clearances and Finance, Program and Purchase '
            'price approvals recorded on version 3. No supplier release recorded. No package revisions after these approvals '
            'are recorded. Existing modular rates do not waive approval requirements.')}
    approval_sections = [
        ('Decision summary',
         'Proceed with preparation for both change cases. CR-204 is not authorized for supplier release because Finance '
         'approval is pending. CR-205 is ready for the normal authorized release process on approved package version 3. '
         'Do not hold CR-205 solely because a different case remains incomplete. No release has been executed by this memo.'),
        ('Authority and price bridge',
         'The operative policy is P-12 revision 4. Every price change requires Finance, Program and Purchase approval on '
         'the same package before supplier release, including changes priced with modular rates. Revision 5 is a proposal '
         'only. CR-204 increases price by USD 4.20 per unit; CR-205 increases price by USD 0.60 per unit. These differences '
         'do not establish total order cost because order quantities are not supplied. Technical clearance and commercial '
         'approval serve different purposes.'),
        ('Action register for today',
         'CR-204 / Purchase: maintain the version-7 cost bridge and complete draft release package; obtain the remaining '
         'Finance decision. CR-204 / Release gate: keep supplier release on hold until Finance joins the recorded Program '
         'and Purchase approvals on version 7. CR-205 / Purchase: verify that version 3 remains unchanged, then use its '
         'recorded Finance, Program and Purchase approvals to proceed with the normal supplier-release process. '
         'Program: track the two cases separately and escalate timing risk without converting it into an approval exception.'),
        ('Modular quotation and reusable change workflow',
         'Maintain a base assembly and identified feature, child-part and material modules with rate validity, quantities '
         'and specification versions. Show additions, removals and unchanged elements in a cost bridge. Reuse unaffected '
         'technical evidence by reference while identifying the affected configuration and approvals. Modular pricing '
         'reduces repeated negotiation; it does not remove the price-change gate. Route material changes to an approved '
         'package back through the affected reviews before release.'),
        ('Exception proposal and implementation conditions',
         'The draft provisional-price route can be presented for a future policy decision, with proposed limits and an '
         'audit trail. It cannot be used on CR-204 now. Record a rejected, deferred or approved policy decision separately '
         'from the change-case approvals. Timing pressure, a complete technical package or an expected Finance decision '
         'does not provide the missing current authorization.'),
        ('Digital record and closure',
         'Bind every approval to the case ID and package version. Retain the source policy, cost bridge, decisions and '
         'event timestamps. After an authorized release is actually executed, record the supplier communication and '
         'acknowledgment. Until then, show release as pending execution. This memo makes no claim that a message was '
         'sent, Finance approved CR-204, or a release occurred.')]
    return [
        {'id': 'continuity_window', 'title': 'Actuator continuity decision and action plan',
         'sources': continuity_sources, 'sections': continuity_sections,
         'mutate_from': 'Continuity decision: if no extension is secured, do not commit to coverage from buffer stock or air freight until usable quantities and receipt dates are verified.',
         'mutate_to': 'Continuity decision: if no extension is secured, buffer stock and air freight cover the full replacement qualification window; maintain the committed production schedule.',
         'conditional_from': continuity_sections[2][1],
         'conditional_to': (
             'Planning may use two explicit scenarios, not an inventory claim. If reconciled usable reserve and dated '
             'receipts cover at least 3,960 units before their demand dates, that covers 99 days at 40 units per day '
             '(days 22 through 120), conditional on approved replacement receipts starting day 121. If replacement '
             'receipts instead start day 151, 129 days require 5,160 units with the same receipt-timing condition. '
             'If neither condition is established, quantify the uncovered dates and seek a revised production decision. '
             'No quantity is assumed available by stating these conditions.'),
         'source_id': 'workspace:approved-supply-record.txt',
         'source_quote': 'The usable reserve expected to be available at the start of day 22 has not been reconciled.',
         'counterevidence': 'The day-22 usable reserve is unknown.',
         'consequence': 'The action register promises continuous coverage without verified usable quantities or receipt dates, risking an unsupported production commitment.',
         'minimum_correction': 'Keep the production commitment conditional on a dated coverage schedule; seek the director\'s decision for any uncovered window.',
         'conditional_quote': 'No quantity is assumed available by stating these conditions.'},
        {'id': 'approval_authority', 'title': 'Lamp sourcing-change decision and workflow',
         'sources': approval_sources, 'sections': approval_sections,
         'mutate_from': 'CR-204 / Release gate: keep supplier release on hold until Finance joins the recorded Program and Purchase approvals on version 7.',
         'mutate_to': 'CR-204 / Release gate: issue a provisional-price supplier release using the recorded Program and Purchase approvals on version 7; obtain Finance approval afterward.',
         'conditional_from': approval_sections[4][1],
         'conditional_to': (
             'Pre-stage the version-7 release package without sending it. If Finance approves that unchanged package, '
             'Purchase may then verify that all three approvals remain recorded on the same version and proceed with '
             'the normal release process. If Finance requests a substantive revision, re-route the affected reviews '
             'before release. If Finance rejects the change or the review remains pending, keep CR-204 unreleased and '
             'escalate its schedule impact. The draft provisional-price policy can be proposed for a separate future '
             'decision, but it has no current effect. Continue authorized CR-205 work independently.'),
         'source_id': 'workspace:approved-policy-P12-r4.txt',
         'source_quote': 'Every price change requires Finance, Program and Purchase approval on the same change package before supplier release, including a price calculated from an existing modular rate.',
         'counterevidence': 'CR-204 is not authorized for supplier release because Finance approval is pending.',
         'consequence': 'The action register instructs a supplier release without the mandatory Finance approval despite correctly stating the policy elsewhere.',
         'minimum_correction': 'Keep CR-204 unreleased until all mandatory approvals exist on its unchanged package; continue CR-205 under its recorded approvals.',
         'conditional_quote': 'Pre-stage the version-7 release package without sending it.'}]


def make_packet(family, member):
    sections = copy.deepcopy(family['sections'])
    if member in ('contradicted_action', 'cosmetic_control'):
        sections = [(h, p.replace(family['mutate_from'], family['mutate_to'])) for h, p in sections]
    if member == 'conditional_plan':
        sections = [(h, p.replace(family['conditional_from'], family['conditional_to'])) for h, p in sections]
    elif member == 'cosmetic_control':
        sections = [(h.upper(), p) for h, p in sections]
    cid = 'J11-' + digest(family['id'] + ':' + member)[:12]
    units = [{'locator': 'title', 'text': family['title']}]
    for i, (heading, body) in enumerate(sections, 1):
        units.extend([{'locator': f'section:{i}:heading', 'text': heading},
                      {'locator': f'section:{i}:body', 'text': body}])
    artifact = {'id': 'decision-memo.txt', 'format': 'constructed_text', 'units': units,
                'text': '\n\n'.join(u['text'] for u in units),
                'render_validation': 'text_html_only_not_native_file_validation'}
    artifact['sha256'] = digest(artifact['text'])
    packet = {'schema': 'turing-evidence-grader-packet-v1', 'id': cid,
              'judge_instructions': JUDGE_INSTRUCTIONS,
              'source_documents': copy.deepcopy(family['sources']),
              'criteria': copy.deepcopy(CRITERIA), 'artifacts': [artifact],
              'observable_tool_events': [], 'trace_complete': False,
              'engineering_checks': {'native_count_and_types_pass': False, 'fixture_only': True,
                                     'scope': 'Complete text/HTML memo; no native artifact requested or validated.'},
              'evidence_basis': 'locally_authored_development_fixture_not_model_run',
              'human_validation': 'pending',
              'limitations': ['Authored text controls; no model quality, prevalence or fresh held-out claim.',
                             'No author labels or member identity are included in the judge packet.',
                             'Text inspection does not certify document layout or interaction quality.']}
    negative = member in ('contradicted_action', 'cosmetic_control')
    target = family['mutate_to'] if negative else family['conditional_quote'] if member == 'conditional_plan' else family['mutate_from']
    key = {'id': cid, 'family_id': family['id'], 'member': member,
           'label_basis': 'author_intended_construction_not_expert_gold', 'human_validated': False,
           'expected_content_acceptable': not negative,
           'expected_consequential_error': negative,
           'expected_task_defect': False, 'expected_unnecessary_hold': False,
           'source_bundle_sha256': digest(canonical(family['sources'])),
           'evidence_map': {'criterion_id': 'source_and_authority_consistency',
               'source_id': family['source_id'], 'source_quote': family['source_quote'],
               'artifact_id': artifact['id'], 'output_quote': target,
               'counterevidence_quote': family['counterevidence'],
               'consequence_if_mutated': family['consequence'],
               'minimum_correction_if_mutated': family['minimum_correction']},
           'construction': {'held_constant': ['task request', 'source bundle', 'decision objective', 'criteria'],
               'change': {'supported': 'Complete supported memo; contains useful actions with applicable gates.',
                          'contradicted_action': 'Exactly one action instruction replaced; correct rule and caveat retained elsewhere.',
                          'cosmetic_control': 'Cosmetic counterpart of the contradicted-action document: section headings capitalized and presentation style changed; every faulty-document body paragraph unchanged.',
                          'conditional_plan': 'One planning section replaced with an explicit conditional decision tree; no current approval or inventory inferred.'}[member]}}
    return packet, key


def materials(phase10):
    models = {j['model'] for j in phase10['jobs'] if j['study'] == 'sensitivity'}
    if len(models) != 1:
        raise ValueError('A single frozen sensitivity judge is required')
    model = models.pop()
    packets, keys = [], []
    for family in source_families():
        for member in MEMBERS:
            packet, key = make_packet(family, member)
            packets.append(packet); keys.append(key)
    rng = random.Random(SEED); rng.shuffle(packets)
    prompts = {
        'original': JUDGE_INSTRUCTIONS,
        'reword': phase10['variants']['v1_reword'],
        'self_review': JUDGE_INSTRUCTIONS + '\n\nPOST-HOC SELF-REVIEW: The next user message also contains the saved initial judgment '
            'from this same judge on this same packet. Treat it as a fallible assessment, not authority. Briefly check whether '
            'confidence, polished presentation, a claimed approval, or finding a correct rule elsewhere influenced that verdict. '
            'Reinspect the actual source and action instructions. Then return a complete revised judgment in the same JSON schema, '
            'with concise evidence-based rationales. Preserve a supported verdict when appropriate. Do not provide hidden internal '
            'reasoning or a long reasoning transcript. Do not substitute a bias warning for an exact evidence check.'}
    jobs = []
    for packet in packets:
        cid = packet['id']; packet_path = f'data/judge_controls_11/packets/{cid}.json'
        for repeat in (1, 2, 3):
            jobs.append({'id': f'{cid}__original_r{repeat}', 'case_id': cid, 'model': model,
                         'packet': packet_path, 'arm': 'original', 'repeat': repeat,
                         'prompt_key': 'original', 'depends_on': [], 'status': 'proposed_unrun'})
        jobs.append({'id': f'{cid}__reword', 'case_id': cid, 'model': model, 'packet': packet_path,
                     'arm': 'reword', 'repeat': 1, 'prompt_key': 'reword', 'depends_on': [], 'status': 'proposed_unrun'})
        jobs.append({'id': f'{cid}__self_review', 'case_id': cid, 'model': model, 'packet': packet_path,
                     'arm': 'self_review', 'repeat': 1, 'prompt_key': 'self_review',
                     'depends_on': [f'{cid}__original_r1'], 'status': 'proposed_unrun',
                     'initial_judgment_source': f'{cid}__original_r1',
                     'initial_judgment_policy': 'Supply the saved raw judgment plus the identical packet. If no response exists, mark dependency_unavailable; do not fabricate one. Invalid initial evidence remains invalid in primary accuracy comparisons.'})
    # Randomize among ready jobs; dependencies always precede their self-review.
    pending = jobs.copy(); order = []; completed = set()
    while pending:
        ready = [j for j in pending if set(j['depends_on']) <= completed]
        job = rng.choice(ready); pending.remove(job); order.append(job['id']); completed.add(job['id'])
    config = {'schema': 'turing-proposed-grader-controls-v1', 'id': 'judge-controls-11',
              'status': 'proposed_unrun', 'execution_enabled': False, 'human_validation': 'pending',
              'fixed_model': model, 'max_tokens': phase10['max_tokens'],
              'reasoning_effort': phase10['reasoning_effort'], 'response_format': phase10['response_format'],
              'provider': {'allow_fallbacks': False, 'require_parameters': True,
                           'max_price': {'prompt': 10, 'completion': 50}},
              'provider_policy': 'Hold model, routing preferences, decoding options and token cap constant; log actual provider and all effective request settings. No such execution has occurred.',
              'payload_contract': 'Use materialize_request: selected prompt appears only in the system message; remove packet judge_instructions from the user message. Preserve source/output bytes. Original repeats have identical messages and settings. Reword changes only the system message. Self-review additionally supplies only the matching saved original_r1 judgment, never author labels.',
              'prompts': prompts, 'jobs': jobs, 'planned_execution_order': order,
              'seed': SEED, 'seed_scope': 'Opaque case presentation and randomized dependency-respecting job order only; not data generation or deterministic model sampling.',
              'paired_comparisons': [
                  {'arm': 'repeat_control', 'baseline': 'original_r1', 'comparison': ['original_r2', 'original_r3'],
                   'changes': 'No intended input or request-setting change; independent API requests measure repeat variation.'},
                  {'arm': 'reword', 'baseline': 'original_r1', 'comparison': 'reword',
                   'changes': 'Instruction wording only; intended semantic equivalence needs reviewer confirmation.'},
                  {'arm': 'self_review', 'baseline': 'original_r1', 'comparison': 'self_review',
                   'changes': 'One additional post-hoc request gets the saved initial judgment and a structured bias check. Same packet and final schema.',
                   'attribution_limit': 'Compute and the second-pass procedure change together. Compare also with original_r2/r3; no claim of isolating bias reflection from extra inference compute.'}],
              'document_control_comparisons': [
                  {'members': ['supported', 'contradicted_action'], 'changes': 'Exactly one consequential action instruction; correct rules and caveats retained.'},
                  {'members': ['contradicted_action', 'cosmetic_control'], 'changes': 'Headings and rendering style only; all business content and the underlying error unchanged. Tests presentation effects on an authored negative.'},
                  {'members': ['supported', 'conditional_plan'], 'changes': 'One section expresses useful conditional action without treating it as completed or authorized; author expects both acceptable.'}],
              'native_inspection_arm': {'status': 'not_prepared_not_run',
                  'reason': 'These controls are full text/HTML memos. No matched native/rendered/formula-inspection packets or interactive evaluator are supplied. Existing native workflow tests are separate evidence.'},
              'analysis': {'unit': 'Source family with paired member/arm/repeat observations; 40 requests are not 40 independent business cases.',
                  'primary_evidence': 'Raw exact-quote/coverage-valid judgments only; no shortened quote normalization in primary results.',
                  'separate_states': ['pass', 'fail', 'uncertain', 'invalid_evidence', 'task_defect_or_uncertainty', 'execution_error', 'dependency_unavailable', 'unrun'],
                  'before_human_review': ['repeat agreement and full label tables', 'rewording and self-review verdict changes', 'invalid/uncertain counts', 'author-expectation control matches separately labeled'],
                  'after_human_review': ['human-confirmed consequential errors recovered', 'new false alarms on human-confirmed clean cases', 'false accepts', 'missed consequential errors'],
                  'cost_and_time': 'Record per-request reported cost, unresolved charges and wall time. Charge initial+review calls to self-review; include repeat-control costs separately. Human minutes must be measured, not inferred.',
                  'human_validation_rule': 'Review sources and complete outputs; preserve uncertainty. No model vote or constructed expectation becomes human truth.',
                  'selection_policy': 'All eight constructed development cases fixed before execution. Report every planned job, including failures, with no replacement runs disguised as originals.',
                  'interpretation': 'Development diagnostics and a local adaptation of proposed methods; not a paper reproduction, model ranking, validated grader, or training gain.'},
              'execution_gate': 'Review the task/source adequacy and intended label/semantic-control construction before any accuracy claim. A separately initiated runner must freeze inputs and settings; this builder makes no API calls.',
              'planned_requests': len(jobs), 'executed_requests': 0, 'reported_api_cost_usd': None,
              'input_hashes': {f'data/judge_controls_11/packets/{p["id"]}.json':
                  digest(json.dumps(p, ensure_ascii=False, indent=2) + '\n') for p in packets}}
    manifest = {'schema': 'turing-judge-controls-manifest-v1', 'status': 'prepared_not_run',
                'families': 2, 'fixtures': 8, 'members_per_family': list(MEMBERS),
                'planned_requests': len(jobs), 'executed_requests': 0, 'human_validated_cases': 0,
                'reported_api_cost_usd': None, 'runtime_seconds': None,
                'fixed_model': model, 'review_index': 'reviews/judge_controls_11/index.html',
                'config': 'config/judge_controls_11.proposed.json',
                'source': 'Two locally authored fictional professional-document families inspired by the existing purchasing failure themes. No teacher API generated the facts. Development controls, not new held-out source lineages.',
                'permissions': 'Project-authored fictional records and memos; no external employer data. This records author provenance, not independent rights certification.',
                'seed': SEED, 'seed_scope': config['seed_scope'],
                'scope': 'Development controls pending human validation. Author labels are not gold and no new judge result exists.',
                'author_expected_label_balance': {'acceptable': 4, 'unacceptable': 4, 'status': 'author_expectations_not_human_gold'},
                'native_inspection_status': 'not_prepared_not_run',
                'blinding': 'Opaque case IDs and no author labels in packets or review pages. Related source content may reveal family relationships.',
                'packet_ids_in_review_order': [p['id'] for p in packets],
                'input_hashes': {}}
    scorecard = {'schema': 'turing-judge-controls-unrun-scorecard-v1', 'status': 'not_run',
                 'planned_requests': len(jobs), 'executed_requests': 0, 'responses': 0,
                 'human_validated_cases': 0,
                 'metrics': {k: {'value': None, 'reason': 'No new judge responses or completed human labels.'}
                     for k in ('repeat_variation', 'reword_verdict_changes', 'errors_recovered', 'new_false_alarms',
                               'invalid_judgments', 'uncertain_judgments', 'additional_reported_cost_usd', 'additional_wall_seconds')},
                 'scope': 'Prepared schedule only. Zero executed requests does not imply zero errors, zero latency or free future execution.'}
    return packets, keys, config, manifest, scorecard


def materialize_request(config, job, packet, initial_record=None):
    """Prepare one request body without credentials, networking or execution.

    In particular, the original prompt embedded in a packet is never duplicated
    into the user payload of a rewording arm. The configured 40 jobs remain unrun.
    """
    configured = [j for j in config['jobs'] if j['id'] == job.get('id')]
    if len(configured) != 1 or canonical(configured[0]) != canonical(job):
        raise ValueError('Job is not the exact proposed configuration')
    if packet.get('id') != job['case_id'] or job['model'] != config['fixed_model']:
        raise ValueError('Packet or fixed judge does not match job')
    # Match the deterministic on-disk serialization captured by the proposed
    # input manifest. A reused opaque ID cannot authorize edited source/output
    # content. The separate inspector also verifies actual file bytes.
    expected_hash = config.get('input_hashes', {}).get(job['packet'])
    packet_hash = digest(json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    if not expected_hash or packet_hash != expected_hash:
        raise ValueError('Packet content does not match the configured input hash')
    payload = copy.deepcopy(packet)
    payload.pop('judge_instructions', None)
    if any(k in payload for k in ('member', 'family_id', 'expected_content_acceptable', 'expected_consequential_error')):
        raise ValueError('Author labels are forbidden in request payloads')
    user_message = {'packet': payload}
    if job['arm'] == 'self_review':
        expected = job['case_id'] + '__original_r1'
        if not isinstance(initial_record, dict) or initial_record.get('status') != 'received':
            raise ValueError('Saved original_r1 response is required for post-hoc review')
        if any(initial_record.get(k) != value for k, value in
               {'id': expected, 'case_id': job['case_id'], 'packet': job['packet'], 'model': job['model']}.items()):
            raise ValueError('Initial response identity does not match original_r1')
        if not isinstance(initial_record.get('judgment'), dict):
            raise ValueError('No structured initial judgment available; do not fabricate one')
        user_message['initial_judgment'] = copy.deepcopy(initial_record['judgment'])
    elif initial_record is not None:
        raise ValueError('Only self-review may receive an initial judgment')
    return {'model': job['model'], 'max_tokens': config['max_tokens'],
            'reasoning': {'effort': config['reasoning_effort']},
            'response_format': copy.deepcopy(config['response_format']),
            'provider': copy.deepcopy(config['provider']),
            'messages': [{'role': 'system', 'content': config['prompts'][job['prompt_key']]},
                         {'role': 'user', 'content': canonical(user_message)}]}


STYLE = '''body{font:17px/1.55 system-ui,sans-serif;max-width:920px;margin:40px auto;padding:0 22px;color:#18313b;background:#fbfcfc}h1{font-size:30px;line-height:1.2}h2{font-size:23px;margin-top:34px}h3{font-size:18px}section{border-top:1px solid #cdd8dc;padding:16px 0}pre{white-space:pre-wrap;font:inherit;margin:0}a{color:#125f73}aside{padding:16px;background:#eaf2f4}li{margin:10px 0}.memo{padding:22px;background:white;border:1px solid #cdd8dc}.spaced .memo h3{letter-spacing:.03em}.question{padding:18px;border:2px solid #125f73;margin-top:30px}'''


def case_html(packet, number, cosmetic=False):
    e = html.escape
    sources = ''.join('<section><h3>' + e(k) + '</h3><pre>' + e(v) + '</pre></section>'
                      for k, v in packet['source_documents'].items() if k != 'request')
    units = packet['artifacts'][0]['units']
    memo = '<h2>' + e(units[0]['text']) + '</h2>'
    memo += ''.join(('<h3>' if u['locator'].endswith(':heading') else '<p>') + e(u['text']) +
                    ('</h3>' if u['locator'].endswith(':heading') else '</p>') for u in units[1:])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Development review case {number}</title><style>{STYLE}</style><body class="{'spaced' if cosmetic else 'standard'}"><a href="index.html">All review cases</a><h1>Development review case {number}</h1><p>Case ID: {e(packet['id'])}</p><aside>Read the request, all sources and complete output before judging. This is a locally authored development case, not a model run. Author expectations are withheld and human validation is pending. No response is saved by this page.</aside><h2>Requested work</h2><pre>{e(packet['source_documents']['request'])}</pre><h2>Complete sources</h2>{sources}<h2>Complete output</h2><article class="memo">{memo}</article><div class="question"><strong>One question to start:</strong><p>Does the request or source material contain a contradiction, ambiguity or missing information that prevents a fair judgment of this output?</p><p>Answer in the review chat: <strong>No</strong>, <strong>Yes</strong> (with the issue), or <strong>Uncertain</strong>. Acceptance and consequential-error questions follow separately; do not infer either answer from this one.</p></div></body></html>'''


def write_new(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    blob = data.encode()
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError('Refusing to overwrite a changed phase-11 artifact: ' + str(path))
        return
    path.write_bytes(blob)


def build(root=ROOT, phase_config=None):
    root = Path(root)
    phase10 = phase_config or json.loads((root / 'config/judge_robustness_10.json').read_text())
    packets, keys, config, manifest, scorecard = materials(phase10)
    by_id = {k['id']: k for k in keys}
    for i, packet in enumerate(packets, 1):
        rel = 'data/judge_controls_11/packets/' + packet['id'] + '.json'
        write_new(root / rel, packet)
        config['input_hashes'][rel] = digest((root / rel).read_bytes())
        write_new(root / 'reviews/judge_controls_11' / (packet['id'] + '.html'),
                  case_html(packet, i, by_id[packet['id']]['member'] == 'cosmetic_control'))
    manifest['input_hashes'] = config['input_hashes'].copy()
    write_new(root / 'data/judge_controls_11/private/author_key.json', keys)
    write_new(root / 'data/judge_controls_11/manifest.json', manifest)
    write_new(root / 'data/judge_controls_11/unrun_scorecard.json', scorecard)
    write_new(root / 'config/judge_controls_11.proposed.json', config)
    links = ''.join(f'<li><a href="{p["id"]}.html">Case {i} — {p["id"]}</a></li>' for i, p in enumerate(packets, 1))
    write_new(root / 'reviews/judge_controls_11/index.html',
        f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Whole-document grader controls — prepared, not run</title><style>{STYLE}</style><body><h1>Whole-document grader controls</h1><aside><strong>Prepared, not run.</strong> Eight authored development documents across two fictional source families. No new judge response, human label or accuracy result exists.</aside><p>Each case includes its full request, sources and complete output. Read each independently; author expectations and construction categories are withheld here. The review begins with one task/source-validity question, then proceeds to usability and consequential errors separately. Uncertain is a valid answer. Existing Case C-7424ebd2 remains in the earlier calibration queue and is not replaced by these cases.</p><ol>{links}</ol><h2>What has been prepared</h2><p>A fixed-judge schedule of 40 requests: three identical-prompt requests per case, one instruction rewording and one post-hoc self-review using the saved first judgment. Identical-prompt repeats help assess background variation. No requests have been executed. A text-versus-native-inspection comparison has not been prepared.</p><p>These are development controls, not a representative workplace sample, an independent benchmark or a demonstration of training benefit. Full author provenance and intended labels are kept separately for audit.</p></body></html>''')
    write_new(root / 'reviews/judge_controls_11/README.txt',
        'WHOLE-DOCUMENT GRADER CONTROLS — PREPARED, NOT RUN\n\n'
        'Open index.html. Each linked HTML file is self-contained and has the complete request, sources and output. '
        'Author labels are not included. Answer one question at a time in the review chat; these pages do not save answers. '
        'The existing calibration queue remains unchanged.\n\n'
        'Two locally authored fictional families have four document members each. The proposed 40-request schedule is '
        '8 cases x (3 original requests + 1 rewording + 1 post-hoc self-review). Self-review requires the saved original_r1 '
        'response and adds one call; it is not an independently reproduced paper method. Native inspection is not prepared. '
        'No API calls, human labels, realized cost, latency or new accuracy result are supplied.\n\n'
        'The private author key is data/judge_controls_11/private/author_key.json in the audit/code bundle, outside this '
        'review directory and outside all judge packets. Author expectations are not expert gold.\n')
    return manifest


def inspect(root=ROOT):
    """Verify saved proposed assets offline; never rebuild or call a provider."""
    root = Path(root)
    read = lambda rel: json.loads((root / rel).read_text())
    config = read('config/judge_controls_11.proposed.json')
    manifest = read('data/judge_controls_11/manifest.json')
    scorecard = read('data/judge_controls_11/unrun_scorecard.json')
    keys = read('data/judge_controls_11/private/author_key.json')
    if config['status'] != 'proposed_unrun' or config['execution_enabled'] is not False:
        raise ValueError('Proposed execution status changed')
    if config['executed_requests'] != 0 or manifest['executed_requests'] != 0 or scorecard['executed_requests'] != 0:
        raise ValueError('Unrun assets cannot report executed requests')
    if any(k['human_validated'] is not False for k in keys) or manifest['human_validated_cases'] != 0:
        raise ValueError('Constructed expectations are not human labels')
    if any(v['value'] is not None for v in scorecard['metrics'].values()):
        raise ValueError('Unrun scorecard contains a measured result')
    ids = {k['id'] for k in keys}
    if len(ids) != len(keys) or len(ids) != 8:
        raise ValueError('Unexpected case identities')
    packets = {}
    for rel, expected in config['input_hashes'].items():
        if rel != 'data/judge_controls_11/packets/' + Path(rel).name or not rel.endswith('.json'):
            raise ValueError('Unexpected packet path')
        if digest((root / rel).read_bytes()) != expected:
            raise ValueError('Packet hash changed: ' + rel)
        packet = read(rel)
        if packet['id'] not in ids or packet['id'] in packets:
            raise ValueError('Unknown or duplicate packet')
        if any(k in packet for k in ('member', 'family_id', 'expected_content_acceptable', 'expected_consequential_error')):
            raise ValueError('Author labels leaked into packet')
        packets[packet['id']] = packet
    if set(packets) != ids or manifest['input_hashes'] != config['input_hashes']:
        raise ValueError('Incomplete packet manifest')
    families = {}
    for key in keys:
        packet = packets[key['id']]; source_hash = digest(canonical(packet['source_documents']))
        if source_hash != key['source_bundle_sha256']:
            raise ValueError('Source bundle changed')
        if families.setdefault(key['family_id'], source_hash) != source_hash:
            raise ValueError('Family source bundle is not held constant')
        ev = key['evidence_map']; art = packet['artifacts'][0]
        if ev['source_quote'] not in packet['source_documents'][ev['source_id']]:
            raise ValueError('Author source quote not traceable')
        for field in ('output_quote', 'counterevidence_quote'):
            if not any(ev[field] in u['text'] for u in art['units']):
                raise ValueError('Author output quote not traceable')
        if digest(art['text']) != art['sha256']:
            raise ValueError('Artifact text hash changed')
        if not (root / 'reviews/judge_controls_11' / (key['id'] + '.html')).is_file():
            raise ValueError('Missing complete review packet')
    jobs = config['jobs']; job_ids = {j['id'] for j in jobs}
    if len(jobs) != 40 or len(job_ids) != 40 or config['planned_requests'] != 40 or manifest['planned_requests'] != 40:
        raise ValueError('Expected fixed 40-request design')
    if set(config['planned_execution_order']) != job_ids or len(config['planned_execution_order']) != 40:
        raise ValueError('Execution order does not cover each job once')
    positions = {v: i for i, v in enumerate(config['planned_execution_order'])}
    for job in jobs:
        if job['model'] != config['fixed_model'] or job['case_id'] not in ids:
            raise ValueError('Fixed judge or case identity changed')
        if any(positions.get(dep, 40) >= positions[job['id']] for dep in job['depends_on']):
            raise ValueError('Dependency not scheduled before self-review')
        if job['arm'] == 'self_review' and job['depends_on'] != [job['case_id'] + '__original_r1']:
            raise ValueError('Self-review missing saved initial-judgment dependency')
    return {'status': 'prepared_not_run', 'families': len(families), 'fixtures': len(packets),
            'planned_requests': len(jobs), 'executed_requests': 0, 'human_validated_cases': 0,
            'packet_hashes_verified': len(packets), 'author_evidence_quotes_verified': 3 * len(keys),
            'source_bundles_held_constant': True, 'author_labels_outside_packets': True,
            'self_review_dependencies_verified': 8, 'native_inspection_status': config['native_inspection_arm']['status'],
            'reported_api_cost_usd': None, 'scope': 'Offline structural verification; no semantic, human or model-validity claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--inspect', action='store_true', help='Verify saved assets without rebuilding')
    args = parser.parse_args()
    print(json.dumps(inspect(args.root) if args.inspect else build(args.root), indent=2))
