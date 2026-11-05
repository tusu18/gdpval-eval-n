"""Versioned, development-only evidence maps and task repairs. No API calls.

The maps are grader-side authoring material, never solver inputs. Validation is
an engineering check; independent domain review and human gold remain pending.
"""
import copy
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from prepare_contract_repair import validate as validate_contract
from repair_workspace_chronology import chronology_defect
from workflow_workspace import Workspace, initial_message

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/evidence_upgrade_01'
FAMILIES = ('supplier_exit', 'sourcing_approvals', 'original_supplier_landed_cost',
            'change_control', 'original_delivery_appointment')
VARIANTS = ('baseline', 'recovery', 'conflict')
AS_OF = '2026-10-23'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def write_new(path, obj):
    blob = (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists() and path.read_bytes() != blob:
        raise RuntimeError(f'Release is immutable; create a successor: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return digest(blob)


def source_documents(task):
    docs = {'request': task['prompt']}
    docs.update({'attachment:' + k: v for k, v in task['attachments'].items()})
    docs.update({'workspace:' + k: v for k, v in task['workspace'].items()})
    docs.update({'requester:' + c['topic']: c['reply'] for c in task.get('clarifications', [])})
    return docs


def anchor(docs, source, quote):
    text = docs[source]
    if quote not in text:
        raise ValueError(f'Untraceable source quote: {source}: {quote}')
    start = text.index(quote)
    return {'source_id': source, 'quote': quote, 'char_start': start,
            'char_end': start + len(quote), 'source_sha256': digest(text.encode())}


def repair(parent):
    task = copy.deepcopy(parent)
    task['version'] = 'evidence-upgrade-01-development'
    task['scenario_as_of'] = AS_OF
    task['prompt'] += (f'\nSCENARIO CLOCK\nThis is a frozen fictional/adapted scenario as of {AS_OF}. '
                       'Today and project day 0 refer to this date, not the date the task is run. '
                       'Use the scenario records and stated durations; do not update them from current events.\n')
    changes = ['Added a shared scenario clock; existing business objective and information variants retained.']
    if task['family_id'] == 'supplier_exit':
        for path in ('operations/record-r2.txt', 'planning/proposal-r3.txt'):
            task['workspace'][path] = task['workspace'][path].replace(
                'from today.', f'from scenario day 0 ({AS_OF}).')
        changes.append('Anchored relative notice periods to day 0; no inventory or extension was invented.')
    if task['family_id'] == 'change_control':
        task['prompt'] = task['prompt'].replace('producing a completed Change Request Form.',
                                               'producing a usable blank Change Request Form template.')
        changes.append('Removed remaining completed-form wording; inherited the explicit three-file contract.')
    if task['family_id'] == 'original_delivery_appointment':
        task['workspace']['project/decision-register.txt'] = (
            'original_delivery_appointment: operations/record-r2.txt is the customer-service log '
            'recorded 2026-10-23. It requires confirmation from the receiving contact; it does not '
            'itself confirm an appointment. planning/proposal-r3.txt was created 2026-10-22 and '
            'remains unconfirmed. The recorded receiving-contact clarification is authoritative '
            'for the appointment. Dates alone do not confer authority.')
        changes.append('Replaced approval-before-log chronology with dated log and receiving-contact authority.')
    task['candidate_status'] = 'development_only_independent_review_pending'
    return task, changes


def evidence_map(task, rubric):
    docs = source_documents(task)
    rows = []
    def criterion(cid, requirement, sources, expected, locations, critical=True, checker='semantic'):
        rows.append({'id': cid, 'requirement': requirement, 'critical': critical,
                     'anchors': [anchor(docs, s, q) for s, q in sources],
                     'expected': expected, 'deliverable_locations': locations,
                     'checker': checker, 'human_validation': 'pending'})
    req = 'request'; record = 'workspace:operations/record-r2.txt'
    register = 'workspace:project/decision-register.txt'
    action = 'workspace:project/open-actions.txt'
    family = task['family_id']
    criterion('authority', 'Use operative evidence; a newer proposal is not an approved change.',
              [(register, docs[register]), (record, docs[record]),
               ('workspace:planning/proposal-r3.txt', docs['workspace:planning/proposal-r3.txt'])],
              'Resolve conflicting values using authority and status. Conditional alternatives are allowed.',
              ['recommendation', 'all action tables and summaries'])
    if family == 'supplier_exit':
        criterion('continuity', 'Distinguish the 21-day cutoff from the 4–5 month redevelopment period.',
                  [(record, docs[record]), (req, '4–5 months for electronics (including safety certification)'),
                   (req, 'current monthly demand is 800 tail lamp sets')],
                  {'notice_days': 21, 'monthly_sets': 800, 'electronics_months': [4, 5],
                   'opening_stock': None, 'agreed_extension': False,
                   'rule': 'Quantify bridge needs with explicit time/unit assumptions; stock, capacity and air freight do not establish guaranteed supply.'},
                  ['continuity narrative', 'bridge calculation', 'action table'])
        criterion('tooling', 'Reconcile tooling transfer with continuing supplier production.',
                  [(req, 'Tooling transfer from South Korea to India is estimated to take ~25 days.'),
                   (req, 'The tooling for the plastic parts has already been paid for and is fully owned by LiIon.')],
                  'Ownership is established. Availability of spare/duplicate tooling is not. Describe dependencies and conditions; do not assume simultaneous use of the same tooling.',
                  ['transition schedule', 'tooling actions'])
        criterion('negotiation', 'Supply a practical resolution path, BATNA and conditional ZOPA.',
                  [(req, 'Also mention the Zone Of Possible Agreement (ZOPA) for your strategy.')],
                  'Business recommendations may vary. Unagreed concessions remain proposals.',
                  ['negotiation strategy'], False)
    elif family == 'sourcing_approvals':
        criterion('approval_gate', 'Retain all price-change approvers in every release path.',
                  [(record, docs[record])], ['finance', 'program', 'purchase'],
                  ['standard workflow', 'fast track', 'exception path', 'approval table'])
        criterion('nomination', 'Retain TRSO and nomination signoffs.',
                  [(req, 'TRSOs are reviewed and signed off by ER, Quality, and Purchase teams.'),
                   (req, 'signoffs from Finance, Quality, ER, and Program Managers')],
                  'Digital convenience does not remove required signoffs.', ['TRSO gate', 'nomination gate'])
        criterion('modular_costs', 'Specify modular quotation inputs, version control and change routing.',
                  [(req, 'Modular quotation structure'), (req, 'full record of communication trails, negotiation summaries, internal evaluations, and signoffs')],
                  'Feature/part/material cost drivers and traceable changes; no invented active approvals.',
                  ['quotation design', 'audit history'], False)
    elif family == 'original_supplier_landed_cost':
        criterion('landed_cost', 'Use approved per-order freight and compute both landed totals.',
                  [(req, '500 enclosures'), (req, 'Alder offers $42 per unit'),
                   (req, 'Beacon offers $46 per unit, no freight charge'),
                   (req, 'Freight is a single charge per order.'), (record, docs[record])],
                  {'alder_total_usd': 23600, 'beacon_total_usd': 23000, 'savings_usd': 600,
                   'derivation': ['500 * 42 + 2600 = 23600', '500 * 46 + 0 = 23000', '23600 - 23000 = 600']},
                  ['comparison table', 'executive recommendation'], checker='arithmetic_and_semantic')
        criterion('feasibility', 'Recommend the least-cost qualified supplier meeting day 17.',
                  [(req, 'required by project day 17'), (req, 'delivery on day 15'),
                   (req, 'delivery on day 16'), (req, 'Both suppliers are qualified.')],
                  'Beacon at approved prices; both meet the deadline. Proposed Alder freight may be a conditional sensitivity only.',
                  ['recommendation', 'delivery feasibility'])
        criterion('sources', 'Cite real sources supporting the price comparison.',
                  [(req, 'source citations'), (record, docs[record])],
                  'A2 is authoritative as of the scenario date and expires 2026-11-05. No fabricated discount or source.',
                  ['citations', 'cost assumptions'])
    elif family == 'change_control':
        attachment = next(k for k in docs if k.startswith('attachment:') and k.endswith('.docx'))
        criterion('threshold', 'Use strict greater-than USD 5,000 and preserve other triggers.',
                  [(record, docs[record]), (attachment, 'Timeline shift >2 business days')],
                  {'budget_threshold_usd': 5000, 'operator': '>', 'review_at_5000_by_budget_alone': False,
                   'review_at_6000': True, 'other_triggers_independent': True},
                  ['SOP criteria', 'form instructions', 'tracker guidance'], checker='boundary_and_semantic')
        criterion('approval_gate', 'Preserve full and low-risk approval paths with written evidence.',
                  [(attachment, 'PM submits form → QA reviews → Tech Ops reviews → Finance reviews (if budget) → Regulatory reviews (if filing impact) → Final PM Lead signoff → Entry into tracker and archive'),
                   (attachment, 'joint approval from the Project Manager and QA and must still be logged')],
                  'No provisional approved status while required approvals are absent; all files agree.',
                  ['SOP workflow', 'form approval fields', 'tracker status'])
        criterion('templates', 'Provide usable blank form and tracker, with no invented events.',
                  [(req, 'Do not invent a completed change event, approval, signature or tracker history.'),
                   (attachment, 'Change ID | Project | Date Submitted | Requestor | Summary | Risk Level | Status | Outcome | Last Updated By | Date Closed'),
                   (attachment, 'Field | Description\nChange ID | Unique request identifier')],
                  'All source-required form fields and ten tracker columns; factual event entries blank or explicitly illustrative.',
                  ['request_form', 'tracker'])
    else:
        clarification = 'requester:receiving_deadline'
        criterion('confirmed_deadline', 'Use the recorded receiving confirmation, not the Monday estimate.',
                  [(record, docs[record]), (clarification, docs[clarification])],
                  '2026-11-06T16:00 local. In recovery/conflict, demonstrate a successful requester clarification in the trace for a recovery-success claim.',
                  ['dispatch recommendation', 'deadline citation'])
        criterion('service_cost', 'Select the cheapest service meeting the appointment.',
                  [(req, 'Ground costs $90 and arrives Monday 2026-11-09 at 10:00 local time.'),
                   (req, 'Express costs $165 and arrives Friday 2026-11-06 at 14:00 local time.'),
                   (clarification, docs[clarification])],
                  {'service': 'Express', 'cost_usd': 165, 'incremental_cost_usd': 75,
                   'derivation': '165 - 90 = 75; Friday 14:00 <= Friday 16:00; Monday is later'},
                  ['service', 'price', 'delivery feasibility'], checker='arithmetic_and_semantic')
    criterion('completion_claims', 'Distinguish recommendation, draft, approval and completed action.',
              [(action, docs[action])],
              'No order, shipment, approval, inventory check or reservation is completed by drafting a deliverable. Check claims against the observable trace; justified conditional plans are allowed.',
              ['all deliverables', 'executive summary', 'status fields'])
    criterion('whole_request', 'Check the complete request and reference requirements, beyond this diagnostic subset.',
              [(req, task['prompt'].split('\n\nWORKSPACE')[0])],
              rubric['rubric'], ['all deliverables'], False)
    sources = []
    for sid, text in docs.items():
        channel, _, path = sid.partition(':')
        if channel == 'workspace':
            route = [{'tool': 'search_files', 'arguments': {'query': 'approved record project'}},
                     {'tool': 'read_file', 'arguments': {'path': path}}]
        elif channel == 'requester':
            route = [{'tool': 'ask_requester', 'arguments': {'question': 'What is the latest receiving deadline?'}}]
        else:
            route = [{'channel': 'initial_request_or_attachment'}]
        sources.append({'id': sid, 'sha256': digest(text.encode()), 'recovery_route': route,
                        'authority': 'unapproved proposal' if 'proposal-r3' in sid else
                                     'archive, not current evidence' if 'archive/' in sid else
                                     'receiving-contact recorded confirmation' if channel == 'requester' else
                                     'scenario instruction or source; resolve using decision register',
                        'as_of': AS_OF, 'rights_status': 'unverified_for_commercial_use'})
    return {'schema': 'turing-evidence-map-v1', 'instance_id': task['instance_id'],
            'family_id': family, 'split': 'development_only', 'scenario_as_of': AS_OF,
            'task_sha256': digest((json.dumps(task, indent=2, ensure_ascii=False) + '\n').encode()),
            'sources': sources, 'criteria': rows, 'canonical_facts': rubric['truth'],
            'oracle_inputs': rubric.get('oracle_inputs'), 'deliverable_contract': {
                'count': task['deliverable_count'], 'format': task['deliverable_format'],
                'roles': task.get('deliverables', []),
                'page_min': 2 if family in ('supplier_exit', 'sourcing_approvals') else None,
                'page_max': 3 if family in ('supplier_exit', 'sourcing_approvals') else task.get('page_max')},
            'solver_visibility': 'excluded; only request, attachments and allowlisted tool replies',
            'independent_review': 'pending', 'training_eligible': False,
            'rights_status': 'original_fictional_authorship_recorded_not_attested' if not task.get('source_task_id') else 'public_derivative_commercial_rights_unverified'}


def validate(task, mapping, rubric):
    errors = []
    docs = source_documents(task)
    expected_hash = digest((json.dumps(task, indent=2, ensure_ascii=False) + '\n').encode())
    if expected_hash != mapping['task_sha256']:
        errors.append('task_hash_mismatch')
    for src in mapping['sources']:
        if digest(docs.get(src['id'], '').encode()) != src['sha256']:
            errors.append('source_hash_mismatch:' + src['id'])
    for c in mapping['criteria']:
        for a in c['anchors']:
            text = docs.get(a['source_id'], '')
            if text[a['char_start']:a['char_end']] != a['quote'] or digest(text.encode()) != a['source_sha256']:
                errors.append('broken_anchor:' + c['id'])
    if chronology_defect(task):
        errors.append('copied_before_created')
    if task.get('scenario_as_of') != AS_OF:
        errors.append('scenario_clock_drift')
    if 'SCENARIO CLOCK' not in task['prompt']:
        errors.append('missing_solver_clock')
    if task['family_id'] == 'change_control':
        try:
            validate_contract(task, rubric)
        except ValueError as e:
            errors.append(str(e))
        if 'producing a completed Change Request Form' in task['prompt']:
            errors.append('blank_vs_completed_form_conflict')
    env = Workspace(task)
    for path in task['workspace']:
        if env.call('read_file', {'path': path}).get('error'):
            errors.append('unreadable_source:' + path)
    if 'error' not in env.call('read_file', {'path': '../grader/evidence_maps.json'}):
        errors.append('grader_path_exposed')
    if any(k in task for k in ('truth', 'rubric', 'canonical_facts', 'criteria', 'oracle_inputs')):
        errors.append('hidden_fields_in_solver')
    if task['family_id'] == 'original_delivery_appointment':
        approval = re.search(r'approved (\d{4}-\d{2}-\d{2})', task['workspace']['project/decision-register.txt'])
        log_date = re.search(r'log dated (\d{4}-\d{2}-\d{2})', task['workspace']['operations/record-r2.txt'])
        if approval and log_date and date.fromisoformat(approval[1]) < date.fromisoformat(log_date[1]):
            errors.append('approval_predates_current_log')
        if task['variant'] != 'baseline' and '2026-11-06 at 16:00' in initial_message(task):
            errors.append('clarification_answer_leaked')
        reply = env.call('ask_requester', {'question': 'What is the latest receiving deadline?'})
        if '2026-11-06 at 16:00' not in reply.get('answer', '') or reply.get('new_approval_granted') is not False:
            errors.append('clarification_not_recoverable')
    if task['family_id'] == 'original_supplier_landed_cost':
        # Recompute from solver-visible source text, not solely from the author key.
        try:
            q = Decimal(re.search(r'(\d+) enclosures', task['prompt'])[1])
            a = Decimal(re.search(r'Alder offers \$(\d+) per unit', task['prompt'])[1])
            b = Decimal(re.search(r'Beacon offers \$(\d+) per unit', task['prompt'])[1])
            freight = Decimal(re.search(r'freight is USD (\d+)', task['workspace']['operations/record-r2.txt'])[1])
            expected = {'supplier': 'Beacon' if q*b < q*a+freight else 'Alder',
                        'alder_total_usd': float(q*a+freight), 'beacon_total_usd': float(q*b),
                        'savings_vs_alder_usd': float(q*a+freight-q*b)}
            if mapping['canonical_facts'] != expected:
                errors.append('landed_cost_source_oracle_disagrees')
            numeric = next(c for c in mapping['criteria'] if c['id'] == 'landed_cost')['expected']
            if any(numeric[k] != expected[e] for k, e in [('alder_total_usd','alder_total_usd'),
                    ('beacon_total_usd','beacon_total_usd'),('savings_usd','savings_vs_alder_usd')]):
                errors.append('landed_cost_criterion_disagrees')
        except (TypeError, KeyError, StopIteration):
            errors.append('landed_cost_source_not_parseable')
    return errors


def build():
    rubrics = {r['id']: r for r in json.loads((ROOT / 'data/paired_v2/grader/rubrics.json').read_text())}
    rubrics['change_control'] = json.loads((ROOT / 'data/contract_repair_01/grader/rubric.json').read_text())
    files = []; maps = []; checks = []; repairs = []
    for family in FAMILIES:
        tasks = []
        for variant in VARIANTS:
            parent_dir = 'contract_repair_01' if family == 'change_control' else 'paired_v2_1'
            parent_path = ROOT / 'data' / parent_dir / 'solver' / f'{family}__{variant}.json'
            task, changes = repair(json.loads(parent_path.read_text()))
            task['parent_sha256'] = digest(parent_path.read_bytes())
            mapping = evidence_map(task, rubrics[family])
            errors = validate(task, mapping, rubrics[family])
            if errors:
                raise ValueError((task['instance_id'], errors))
            path = DEST / 'solver' / parent_path.name
            files.append({'path': str(path.relative_to(ROOT)), 'sha256': write_new(path, task),
                          'parent_path': str(parent_path.relative_to(ROOT)), 'parent_sha256': task['parent_sha256']})
            maps.append(mapping); tasks.append(task)
            repairs.append({'instance_id': task['instance_id'], 'changes': changes})
            checks.append({'instance_id': task['instance_id'], 'errors': errors})
        if not all(t['workspace'] == tasks[0]['workspace'] and t.get('clarifications', []) == tasks[0].get('clarifications', []) for t in tasks):
            raise ValueError('Paired environment drift: ' + family)
    write_new(DEST / 'grader/evidence_maps.json', maps)
    write_new(DEST / 'grader/rubrics.json', [rubrics[f] for f in FAMILIES])
    write_new(DEST / 'repair_log.json', repairs)
    write_new(DEST / 'review_form.template.json', {
        'reviewer_id': None, 'role_and_experience': None, 'independent_of_author': None,
        'reviewed_hashes': [], 'family_reviews': [{
            'family_id': f, 'same_objective_across_variants': None, 'source_authority_valid': None,
            'chronology_valid': None, 'realistic_and_solvable': None, 'map_complete': None,
            'repairs_preserve_intended_challenge': None, 'approve': None,
            'evidence_and_corrections': None, 'review_minutes': None} for f in FAMILIES]})
    manifest = {'release': 'evidence-upgrade-01', 'date': '2026-11-03', 'status': 'development_candidate',
                'families': len(FAMILIES), 'purchasing_families': 3, 'instances': len(files),
                'criterion_records': sum(len(m['criteria']) for m in maps),
                'independent_reviews': 0, 'model_runs': 0, 'training_eligible': False,
                'preflight': checks, 'files': files,
                'private_map_sha256': digest((DEST / 'grader/evidence_maps.json').read_bytes()),
                'limits': ['Five selected development families, not a fresh held-out collection.',
                           'No independent review, commercial rights attestation or human gold inferred.',
                           'Maps are assistant-authored and may share source/rubric errors.',
                           'Changing contracts or task snapshots requires new runs; old outcomes are not reusable.',
                           'Native create/render/recalculate/inspect/revise agent loop is still pending.']}
    write_new(DEST / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    result = build()
    print(json.dumps({k: result[k] for k in ('release', 'families', 'instances', 'criterion_records', 'model_runs')}))
