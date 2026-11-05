"""Prepare four human-review cases and an unrun agentic-judge plan, offline.

Workbook fixtures are prepared separately. No human labels or model calls are
created here. Existing experiments and submission packages remain untouched.
"""
from pathlib import Path
import copy
import hashlib
import html
import json
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from evidence_grader import extract_artifact

REVIEW = ROOT / 'reviews/agentic_judge_pilot_12'
DATA = ROOT / 'data/agentic_judge_pilot_12'
ORDER = ['R-b204', 'R-58c2', 'R-7a19', 'R-d430']
APPROVAL = {'R-b204': 'J11-d07062815d90', 'R-7a19': 'J11-7eb7dddd2682'}
SHEET_IDS = ['R-58c2', 'R-d430']
CSS = '''body{font:17px/1.6 system-ui,sans-serif;color:#182b38;background:#f3f6f7;margin:0}main{max-width:980px;margin:auto;padding:36px 24px 70px}h1,h2,h3{line-height:1.25}h1{font-size:34px}h2{font-size:25px;margin-top:32px}h3{font-size:19px}a{color:#075f96}section,article{background:white;border:1px solid #d4dfe4;border-radius:10px;padding:22px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.6 ui-monospace,monospace}li{margin:9px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #d4dfe4}.note{border-left:4px solid #bc8434;padding:12px 18px;background:#fff9eb}.tag{color:#435b6b;font-size:14px}img{max-width:100%;height:auto}button{padding:12px;font:inherit} @media print{body{background:white}main{padding:0}section,article{break-inside:avoid}a{color:inherit}}'''


def load(rel):
    return json.loads((ROOT / rel).read_text())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page(title, body):
    return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style><main><h1>{html.escape(title)}</h1>{body}</main></html>'


def source_html(sources):
    return ''.join(f'<section><h3>{html.escape(k)}</h3><pre>{html.escape(v)}</pre></section>' for k, v in sources.items())


def approval_checks():
    return [
        'Read policy registry, approved P-12 revision 4, draft revision 5 and the change register. Which version governs current releases?',
        'In Action register for today, follow CR-204 version 7 from pending Finance approval to the release instruction. Does every operative instruction preserve the required approval gate?',
        'Check that CR-205 version 3, which has all required approvals, can proceed through the normal release process. Do not reward an unnecessary blanket hold.',
        'Compare the action register with Decision summary and Exception proposal and implementation conditions. Is any conflict resolved, or would a person following the action register act without authority?',
        'Distinguish preparing a release package from sending it, and a future policy proposal from an approved current exception. Record uncertainty rather than guessing intent.'
    ]


def sheet_checks():
    return [
        'Use the registry to choose the approved freight rate. Record whether the workbook uses the approved USD 150 rate rather than the newer unapproved USD 110 draft.',
        'On Shipment Manifest, inspect G3:G6, H3:H6 and I3:I6. Independently add the three shipment costs: USD 5.95, USD 150.00 and USD 75.00.',
        'Inspect the formula in G6 and recalculate a disposable copy. Does it include all three shipment rows? Record the displayed value before recalculation and the value afterward; a cached number is not proof of correctness.',
        'Check that total benchmark minus total actual cost reconciles with total savings. Compare all three totals with Selection Basis and Notes, cell B6.',
        'Open both sheets and check that headings, customer and shipment rows, cost columns and totals are readable. A cell listing or rendered preview does not prove recalculation occurred.',
        'Do not invent tracking numbers or treat their source absence as a fabricated omission. The workbook discloses an inferred date; assess that disclosure separately from the targeted arithmetic check.'
    ]


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    (DATA / 'packets').mkdir(parents=True, exist_ok=True)
    cases = []
    keys = []
    original_key = {r['id']: r for r in load('data/judge_controls_11/private/author_key.json')}
    for cid in ORDER:
        folder = REVIEW / 'files' / cid
        folder.mkdir(parents=True, exist_ok=True)
        if cid in APPROVAL:
            origin = APPROVAL[cid]
            packet = copy.deepcopy(load(f'data/judge_controls_11/packets/{origin}.json'))
            artifact = packet['artifacts'][0]
            body = []
            for u in artifact['units']:
                if u['locator'] == 'title':
                    continue
                tag = 'h2' if u['locator'].endswith(':heading') else 'p'
                body.append(f'<{tag}>{html.escape(u["text"])}</{tag}>')
            memo = folder / 'memo.html'
            memo.write_text(page(artifact['units'][0]['text'], ''.join(body)))
            artifact['id'] = 'memo.html'
            artifact['format'] = 'authored_html_memo'
            artifact['sha256'] = sha(memo)
            artifact['render_validation'] = 'not_performed'
            expected = original_key[origin]['expected_content_acceptable']
            provenance = 'Locally authored fictional approval control reused from judge_controls_11. Not an original GDPval task or historical model output. HTML memo, not an Office-native submission.'
            checks = approval_checks()
            title = 'Sourcing approval memo'
            deliverable = 'memo.html'
            origin_path = f'data/judge_controls_11/packets/{origin}.json'
            key = {'case_id': cid, 'family': 'approval_authority', 'parent_case': origin,
                   'expected_target_check_pass': expected,
                   'intended_change': original_key[origin]['construction']['change'],
                   'evidence_map': original_key[origin]['evidence_map']}
        else:
            original = 'output/grader_checks_05/packets/C-d419a44b.json'
            packet = copy.deepcopy(load(original))
            workbook = folder / 'workbook.xlsx'
            if not workbook.exists():
                raise FileNotFoundError(f'Prepare native workbook fixture first: {workbook}')
            packet['artifacts'] = [extract_artifact(workbook)]
            packet['observable_tool_events'] = None
            packet['trace_complete'] = False
            packet['engineering_checks'] = {'render_and_page_limits': 'pending_matched_evidence_preparation', 'formula_recalculation': 'requires_recorded_engine_result'}
            provenance = 'Controlled workbook derivative of historical GDPval-derived conflict case C-d419a44b. The old harness rendered a model response into XLSX. Both pilot files are isolated derivatives; an authored formula mutation is not a historical solver failure.'
            checks = sheet_checks()
            title = 'Shipment manifest workbook'
            deliverable = 'workbook.xlsx'
            origin_path = original
            key = {'case_id': cid, 'family': 'shipment_manifest', 'parent_case': 'C-d419a44b',
                   'expected_target_check_pass': cid == 'R-58c2',
                   'target': 'Shipment Manifest!G6',
                   'source_required_total_usd': 230.95,
                   'author_formula_result_usd': 230.95 if cid == 'R-58c2' else 80.95,
                   'intended_change': 'Control formula sums G3:G5.' if cid == 'R-58c2' else 'Only G6 formula omits freight row G4; retained notes provide cross-sheet counterevidence.'}
        # A common rubric is held constant across A/B/C. Native usability is a
        # separate endpoint: absent inspection evidence must remain unknown.
        packet['schema'] = 'agentic-pilot-static-packet-v1'
        packet['case_id'] = cid
        packet['criteria'] = [
            {'id': 'source_and_action_consistency', 'critical': True,
             'requirement': 'Assess consequential operative decisions and calculations against the governing sources. Check approval authority, arithmetic, internal consistency and counterevidence. Do not infer intent.'},
            {'id': 'useful_fulfillment', 'critical': False,
             'requirement': 'Assess useful fulfillment without unnecessary holds. Report task ambiguity separately. Whole-output human acceptance is not established by an automated pass.'}
        ]
        packet['limitations'] = ['Selected development cases; author expectations are not human truth.', 'Extractions do not certify visual usability or recalculation.', 'No new solver performance or benchmark prevalence is measured.']
        packet.pop('judge_instructions', None)
        write_json(DATA / 'packets' / f'{cid}.json', packet)
        (folder / 'sources.html').write_text(page(f'{cid} task and sources', source_html(packet['source_documents'])))
        checks_html = ''.join(f'<li>{html.escape(q)}</li>' for q in checks)
        preview = ''
        if cid in SHEET_IDS:
            preview = '<p>Open the workbook in your spreadsheet application. Recalculate only a disposable copy; retain the supplied file unchanged.</p>'
            for image_name, label in [('preview.png', 'Shipment Manifest'), ('notes-preview.png', 'Selection Basis and Notes')]:
                if (folder / image_name).exists():
                    preview += f'<details><summary>View {label} preview</summary><img src="{image_name}" alt="{label} rendered from this workbook"></details>'
            extracted = '\n'.join(u['locator'] + '\t' + u['text'] for u in packet['artifacts'][0]['units'])
            preview += '<details><summary>Inspect all extracted cells and formulas</summary><p>These are saved values and formulas, not evidence of a new Excel recalculation.</p><pre>' + html.escape(extracted) + '</pre></details>'
        body = f'''<p><a href="../../index.html">Back to the four cases and plan</a></p><p class="tag">{html.escape(provenance)}</p><p><a href="sources.html">Read the full task and sources</a> &nbsp; | &nbsp; <a href="{deliverable}">Open the complete deliverable</a></p>{preview}<h2>What to check</h2><ol>{checks_html}</ol><section><h2>Record your own judgment</h2><p>Target check: pass / fail / uncertain. Whole deliverable: accept / minor revision / major revision / unusable / uncertain. Consequential error: yes / no / uncertain. Task adequate: yes / no / uncertain.</p><p>Give a source quote and location, an output quote or cell, any counterevidence, the business consequence, and the minimum correction if needed. Record reviewer role, minutes spent, and whether you saw an expected answer or prior judge verdict.</p><p>These pages do not save answers. Reply with the case ID in chat, or complete the linked <a href="../../human-review.template.json">review template</a>. No human verdict has been prefilled.</p></section>'''
        (folder / 'review.html').write_text(page(f'{cid} {title}', body))
        key.update({'label_basis': 'author_expectation_not_human_gold', 'human_validated': False})
        keys.append(key)
        cases.append({'case_id': cid, 'title': title, 'source_lineage': provenance,
                      'review_page': f'reviews/agentic_judge_pilot_12/files/{cid}/review.html',
                      'packet': f'data/agentic_judge_pilot_12/packets/{cid}.json',
                      'artifact': str((folder / deliverable).relative_to(ROOT)),
                      'parent_packet': origin_path, 'human_review_status': 'pending'})

    write_json(DATA / 'private/author_key.json', keys)
    review_template = {'schema': 'agentic-pilot-human-review-v1', 'reviewer': None, 'reviewer_role': None,
                      'case_reviews': [{'case_id': c, 'target_check': None, 'whole_output_acceptance': None,
                                        'consequential_error': None, 'task_adequate': None,
                                        'source_evidence': None, 'output_evidence': None, 'counterevidence': None,
                                        'consequence': None, 'minimum_correction': None, 'minutes': None,
                                        'prior_label_exposure': None} for c in ORDER]}
    write_json(REVIEW / 'human-review.template.json', review_template)

    jobs = [{'id': f'{cid}__{arm}', 'case_id': cid, 'arm': arm,
             'max_model_requests': 4 if arm == 'C_agentic' else 1,
             'status': 'planned_not_run'} for cid in ORDER for arm in ['A_text', 'B_fixed_inspection', 'C_agentic']]
    random.Random(20261104).shuffle(jobs)
    cfg = {
        'schema': 'turing-agentic-pilot-proposed-v1', 'status': 'review_inputs_prepared_execution_unrun',
        'execution_enabled': False, 'runner_status': 'not_implemented',
        'human_validated_cases': 0, 'executed_sessions': 0, 'executed_model_requests': 0,
        'reported_api_cost_usd': None, 'fixed_model': 'google/gemini-4-argon',
        'setting_policy': 'Use the same model, provider policy, rubric and per-call output settings in every arm; freeze actual settings before execution. No prior labels or author key enter requests.',
        'cases': cases, 'jobs': jobs, 'planned_sessions': 12, 'max_planned_model_requests': 24,
        'automatic_retries': 0,
        'arm_definitions': {
            'A_text': 'Source bundle and static full artifact extraction only. One model request.',
            'B_fixed_inspection': 'A plus predetermined complete rendered views and recorded recalculation results. One model request. Evidence preparation is not yet a completed grader run.',
            'C_agentic': 'Same starting evidence as B plus read-only follow-up inspection of the same source/artifact universe. Up to four model requests including final verdict. Recalculate/render disposable copies; never repair graded artifacts.'},
        'shared_final_output': 'Per-criterion pass/fail/uncertain, exact evidence locations, short rationale, counterevidence, consequence and minimum correction. Separately report visual/recalculation check pass/fail/unknown; do not fabricate an overall human acceptance score.',
        'pilot_tool_capabilities': ['open permitted source or artifact', 'search source and extracted document', 'read worksheet values and formulas', 'render all pages/sheets', 'recalculate a disposable workbook copy'],
        'pre_execution_gates': ['Human checks all four source/output pairs; uncertain or inadequate cases remain unresolved.', 'Lossless evidence validator checked on multiline and artifact attribution cases.', 'Freeze matched B evidence, renderer/calculation-engine versions and hashes.', 'Implement and dry-run bounded inspection runner; keep author keys and reviewer labels outside judge access.', 'Check actual account balance; measure one agentic session cost before the remainder.'],
        'analysis': {'unit': 'Two source scenario blocks, with two cases each; 12 sessions are not 12 independent business tasks.',
                     'primary': ['human-confirmed targeted errors detected/missed', 'false alarms on human-confirmed controls'],
                     'secondary': ['uncertain and invalid outcomes', 'evidence inspection coverage', 'visual usability separately', 'session and per-request costs', 'elapsed time'],
                     'comparisons': ['B minus A: diagnostic of extra supplied inspection evidence.', 'C minus B: value of adaptive follow-up, confounded with extra compute and any extra retrieved evidence.'],
                     'follow_up_if_C_improves': 'Replay C-gathered evidence to a static judge as a separately planned extension before claiming agency itself caused the gain.',
                     'no_claims': ['population accuracy', 'model ranking', 'benchmark failure prevalence', 'training improvement']},
        'relationship_to_existing_plan': 'This is the next optional extension, not an automatic addition to every previously discussed schedule. Retain judge_controls_11 40-request wording/repeat/self-review schedule as deferred. The conversational 32-call control proposal is not also scheduled here.',
        'budget_policy': 'This preparation script launches no paid calls. Prior one-shot cost estimates do not cover images, tool context or multi-turn sessions. Price a bounded pilot before scaling; record unresolved charges separately.'
    }
    protected = [ROOT / 'data/judge_controls_11/packets'/f'{v}.json' for v in APPROVAL.values()] + [ROOT / 'reviews/calibration_ready_01/files/C-d419a44b/deliverable-1.xlsx', ROOT / 'output/grader_checks_05/packets/C-d419a44b.json']
    cfg['parent_input_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    cfg['input_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in sorted((DATA / 'packets').glob('*.json'))}
    cfg['artifact_hashes'] = {c['artifact']: sha(ROOT / c['artifact']) for c in cases}
    write_json(ROOT / 'config/agentic_judge_pilot_12.proposed.json', cfg)
    cards = ''.join(f'<article><h2>{i}. {c["case_id"]} {c["title"]}</h2><p><a href="files/{c["case_id"]}/review.html">Open sources, deliverable and review checks</a></p></article>' for i,c in enumerate(cases, 1))
    body = '''<p>Review these four cases before the proposed agentic-judge pilot. Each case includes the complete task, sources, deliverable and neutral checks. Expected labels are kept outside this review directory.</p><p class="note">These are development controls, not four newly discovered model failures. The approval memos are fictional authored controls. The workbook pair derives from one historical GDPval-adapted output and includes an authored formula change. Your labels are still pending. The cases share sources, so this is not fully blinded independent review.</p><p><a href="PLAN.txt">Read the updated test plan</a> | <a href="human-review.template.json">Blank review template</a></p>''' + cards + '''<h2>Planned comparison</h2><table><tr><th>Arm</th><th>What the judge receives</th></tr><tr><td>A</td><td>Sources and extracted text/cells.</td></tr><tr><td>B</td><td>A plus fixed rendered views and recalculation evidence.</td></tr><tr><td>C</td><td>B plus follow-up inspection tools, on copies.</td></tr></table><p>Four cases times three arms equals 12 sessions. With four model requests allowed per agentic session, the planned maximum is 24 model requests before any separately scheduled retry. No pilot model calls have run. Human review, matched inspection evidence and the bounded runner remain execution gates.</p>'''
    (REVIEW / 'index.html').write_text(page('Agentic judge pilot and first four reviews', body))
    (REVIEW / 'PLAN.txt').write_text('''AGENTIC JUDGE PILOT ADDED TO THE TEST PLAN

Status: four review inputs prepared; human labels pending; no paid pilot calls.
The execution runner is not implemented. This is a review-ready plan, not a
claim of completed agentic evaluation.

ORDER OF WORK
1. Finish lossless quote-validation repair and refresh the saved-results audit.
   Preserve original attempts, recovery supplements and uncertain charges.
2. Review the four cases linked in index.html before seeing author expectations.
   Record both targeted correctness and whole-output acceptance. No model vote
   becomes a human label. Mark prior exposure and uncertainty explicitly.
3. Freeze the same source and artifact bytes, rubric and model across A/B/C.
   Prepare fixed complete views and recorded recalculation outputs for B.
4. Dry-run the inspection tools on disposable copies, without model calls.
5. Run A/B/C: four artifacts x three arms = 12 sessions. A and B use one request
   each; C allows at most four requests including the final verdict. Maximum
   planned requests = 8 + 16 = 24, with no automatic retries.
6. Report all four cases individually: detected/missed confirmed errors, false
   alarms, invalid/uncertain outcomes, inspected evidence, time and cost.

WHAT EACH ARM MEANS
A: Existing extracted sources/text/cells.
B: A plus fixed rendered views and recalculation evidence.
C: Same starting evidence as B, with follow-up search/open/render/recalculate
   tools over exactly the same source and artifact universe. Work on copies;
   do not fix the document being scored.

B versus A investigates supplied evidence. C versus B investigates adaptive
follow-up but also changes compute and possibly the evidence collected. If C
improves, a later replay of its evidence to a static judge can help distinguish
those mechanisms. A cannot certify visual usability from text; record unknown
instead of treating missing visual evidence as a business error.

FOUR FIRST REVIEWS
R-b204: Sourcing approval memo. Read the approved policy, draft policy and change
register, then compare every CR-204 release instruction with Finance approval
status. Check CR-205 can proceed if authorized. Compare summary, action register
and exception section; correct statements elsewhere do not necessarily resolve
an operative contradiction.
R-58c2: Shipment workbook. Inspect Shipment Manifest G3:I6 and the formula in G6.
Reconcile the governing freight rate, every shipment, total costs, benchmark,
savings and Selection Basis and Notes B6. Recalculate a disposable copy.
R-7a19: Sourcing approval memo. Apply exactly the same checks as R-b204; also
distinguish preparation from external release and proposals from approval.
R-d430: Shipment workbook. Apply exactly the same checks as R-58c2. Record both
cached/displayed and recalculated results and any cross-sheet inconsistency.

HUMAN LABELS
For each: target check pass/fail/uncertain; overall accept/minor revision/major
revision/unusable/uncertain; consequential error yes/no/uncertain; task adequate
yes/no/uncertain; exact source and output evidence; counterevidence; consequence;
minimum correction; minutes; reviewer role; prior exposure. These four reviews
do not replace the wider historical calibration review.

LINEAGE
Approval: two fictional project-authored controls reused from judge_controls_11,
not original GDPval runs. They are HTML memos, not Office-native submissions.
Workbook: two isolated derivatives of historical GDPval-derived conflict case
C-d419a44b, created by the old JSON-to-XLSX harness. One formula alteration is a
deliberate control, not evidence of a historical solver failure. Scope the test
to these two source blocks; four outputs are not four independent tasks.

BUDGET AND PRIORITY
Replace the next optional extension with this pilot; do not automatically add
every earlier proposal. The existing 40-request judge_controls_11 schedule is
retained but deferred. The conversational 32-call proposal is not separately
scheduled here. Check current account balance and measure one agentic session
before estimating the remainder. Images and repeated context can cost more than
the historical one-shot calls. Do not impute unresolved charges as zero.

Do not run if source adequacy, human intended distinctions, evidence validation
or inspection tools remain unresolved. Preserve failures and all reviewed cases;
do not replace inconvenient results. More flags alone are not improvement.
''')
    assert len(cases) == 4 and len(jobs) == 12
    assert sum(j['max_model_requests'] for j in jobs) == 24
    assert all(v is None for r in review_template['case_reviews'] for k,v in r.items() if k != 'case_id')
    print(json.dumps({'review_index': str(REVIEW / 'index.html'), 'cases': len(cases), 'planned_sessions': 12, 'max_model_requests': 24, 'paid_calls': 0}))


if __name__ == '__main__':
    main()
