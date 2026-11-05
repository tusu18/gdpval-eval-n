"""Reconcile existing evidence into a submission supplement, without inference.

Automated triage, human findings, parser diagnostics and unrun experiments stay
separate. This module never creates a human label or calls a model.
"""
from collections import Counter
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def queue_audit(root=ROOT):
    root = Path(root)
    evidence = read(root/'output/assignment_final/evidence.json')
    selection = read(root/'output/submission_audit/review_selection.json')
    mapping = {x['review_id']: x for x in read(root/'output/submission_audit/private_review_key.json')}
    taxonomy = read(root/'output/submission_audit/taxonomy.json')
    human = {x['review_id']: x for x in evidence['human']['calibration']['case_level_comparisons']}
    findings = {x['review_id']: x for x in evidence['human']['taxonomy']['examples']}
    rows = []
    ids = selection['failure_ids']
    if len(ids) != len(set(ids)) or len(ids) != taxonomy['denominator']:
        raise ValueError('Failure queue identity or denominator mismatch')
    for cid in ids:
        item = mapping[cid]
        if not item['failure_queue']:
            raise ValueError('Failure queue disagrees with saved identity mapping')
        record = human.get(cid)
        finding = findings.get(cid)
        rows.append({
            'review_id': cid, 'run_id': item['run_id'], 'family_id': item['family_id'],
            'original_triage_category': item['triage_category'],
            'content_review_complete': record is not None,
            'human_content_acceptable': record['endpoints']['content_acceptable']['human_label'] if record else None,
            'human_consequential_error': record['endpoints']['consequential_error']['human_label'] if record else None,
            'human_finding_category': finding.get('category') if finding else None,
            'human_finding_label': finding.get('category_label') if finding else None,
            'original_flag_disposition': (
                'Whole-content finding recorded; the manually confirmed category is shown separately from automated triage.' if finding else
                'Content accepted. Original page-overflow flag remains a separate mechanical observation; human native-layout compliance was not reviewed.' if record and item['triage_category']=='page_overflow' else
                'Content review recorded; original flag has not been independently adjudicated.' if record else
                'Automated candidate only; no completed human content review.'),
            'run_path': f"output/paired_v1/runs/{item['run_id']}.json"})
    counts = Counter(x['original_triage_category'] for x in rows)
    categories = []
    for category in taxonomy['categories']:
        if counts[category['id']] != category['candidate_count']:
            raise ValueError('Taxonomy count mismatch')
        members = [x for x in rows if x['original_triage_category']==category['id']]
        categories.append({
            'id': category['id'], 'label': category['name'], 'automated_candidates': len(members),
            'definition': category['definition'], 'original_attribution': category['data_fix'],
            'completed_content_reviews': sum(x['content_review_complete'] for x in members),
            'documented_content_findings': sum(x['human_finding_category'] is not None for x in members)})
    return {
        'scope': 'Reconciliation of the archived first-match automated triage queue with existing human content reviews. This is not a new manual failure review.',
        'automated_candidates': len(rows),
        'completed_content_reviews_in_queue': sum(x['content_review_complete'] for x in rows),
        'unreviewed_candidates': sum(not x['content_review_complete'] for x in rows),
        'documented_content_findings_in_queue': sum(x['human_finding_category'] is not None for x in rows),
        'reviewed_content_accepted_in_queue': sum(x['human_content_acceptable']=='yes' for x in rows),
        'reviewed_cases_outside_queue': sorted(set(human)-set(ids)),
        'categories': categories, 'cases': rows,
        'limits': [
            'An accepted content review does not invalidate a separate page-length flag.',
            'The two tooling findings share a single source family and originated under broader continuity triage; categories are not silently treated as identical.',
            'Contract and rendering flags are attribution questions, not proof that a harness repair would resolve the output.',
            'Do not use the selected queue to estimate prevalence, automatic-flag precision or occupation-level reliability.'],
        'source_hashes': {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in (
            'output/assignment_final/evidence.json', 'output/submission_audit/review_selection.json',
            'output/submission_audit/private_review_key.json', 'output/submission_audit/taxonomy.json')},
    }


METRICS = [
    {'id':'target_error_detection', 'name':'Confirmed errors detected / missed',
     'unit':'case within source block', 'numerator':'Human target-fail cases receiving a valid matching judge fail.',
     'denominator':'All human-confirmed target-fail cases assigned to that arm.',
     'handling':'Show valid misses, uncertain, invalid and transport failures separately. Also show detection among valid judgments; never hide missing coverage.',
     'available_now':'Only three original Gemini/human comparisons; new four-artifact pilot unrun.'},
    {'id':'false_alarms', 'name':'False alarms on valid controls',
     'unit':'case within source block', 'numerator':'Human target-pass cases receiving a valid judge fail.',
     'denominator':'All human-confirmed target-pass cases assigned to that arm.',
     'handling':'Report uncertain/invalid/missing outcomes separately; a blanket rejection policy cannot score as useful.',
     'available_now':'Prepared approval controls include authorized work; their human target labels remain pending.'},
    {'id':'judgment_coverage', 'name':'Usable judgment coverage',
     'unit':'assigned session', 'numerator':'Sessions returning a schema-valid, fully evidence-valid judgment.',
     'denominator':'All prespecified sessions in the reported cohort.',
     'handling':'Keep primary raw, frozen normalized and new lossless validation in separate columns. Quote validity is not semantic correctness.',
     'available_now':'Historical raw and secondary evidence diagnostics can be recomputed offline.'},
    {'id':'paired_change', 'name':'Errors recovered and new false alarms',
     'unit':'same artifact across A/B/C', 'numerator':'Per-case transition counts from baseline to comparison: recovered error, new miss, new false alarm, resolved false alarm.',
     'denominator':'All preassigned paired cases, with non-comparable outcomes listed.',
     'handling':'Four artifacts share two source blocks. B−A changes supplied evidence; C−B also changes compute and retrieved evidence. No population interval or causal agency claim.',
     'available_now':'Twelve sessions planned; results absent.'},
    {'id':'stability_sensitivity', 'name':'Harmless-edit stability and substantive-change sensitivity',
     'unit':'human-validated original/edited pair', 'numerator':'Stable judgments for harmless edits; correct judgment switches for material edits.',
     'denominator':'All assigned pairs of the relevant human-validated edit type.',
     'handling':'Report correctness and usable coverage alongside stability; repeated original prompts are needed as an execution-variation control.',
     'available_now':'Eight constructed documents and 40-request schedule prepared but deferred; old prompt-stability results do not measure real-document sensitivity.'},
    {'id':'human_acceptance', 'name':'Whole-deliverable acceptance',
     'unit':'prespecified solver attempt', 'numerator':'Deliverables accepted by the human under a fixed rubric.',
     'denominator':'All assigned solver attempts; also show conditional-on-submission counts.',
     'handling':'Keep extracted-text acceptance separate from native-file usability. The new pilot judges fixed artifacts; it is not a fresh solver-completion study.',
     'available_now':'Five selected original content reviews, two accepted. No population rate.'},
    {'id':'cost_utility', 'name':'Total cost per accepted deliverable',
     'unit':'prespecified solver campaign', 'numerator':'Generation, retries, grading, measured human review and correction cost, including rejected attempts.',
     'denominator':'Final human-accepted deliverables from that same campaign.',
     'handling':'Unknown labor and unresolved charges stay unknown. Do not divide all historical project cost by two selected accepted outputs.',
     'available_now':'Not estimable. The pilot can measure judge-session cost and review minutes prospectively.'},
]


def build(root=ROOT):
    root=Path(root)
    queue=queue_audit(root)
    evidence=read(root/'output/assignment_final/evidence.json')
    return {'schema':'submission-strengthening-13-v1', 'new_api_calls':0,
            'purpose':'Use existing work to improve evidence attribution and prepare a bounded inspection experiment; preserve the five-case qualitative headline.',
            'queue_audit':queue,'metrics':METRICS,
            'native_extension':evidence['extension'],
            'human_review_unchanged':{'completed_original_cases':evidence['human']['completed_count'],
                'finding_categories':evidence['human']['taxonomy']['counts']},
            'proposed_sequence':['Offline lossless evidence audit', 'Complete four new human control reviews',
                'Freeze and dry-run matched inspection evidence', 'Bounded A/B/C judge pilot',
                'Fresh permissioned families and controlled prompt/tool repairs',
                'Separate-family training only if verified failures persist'],
            'source_hashes':queue['source_hashes']}


def render_html(result, lossless=None, inspection=None, packaged=True):
    esc=lambda x:html.escape(str(x))
    q=result['queue_audit']
    rows=''.join('<tr><td>'+esc(c['label'])+'</td><td>'+str(c['automated_candidates'])+'</td><td>'+str(c['completed_content_reviews'])+'</td><td>'+str(c['documented_content_findings'])+'</td><td>'+esc(c['original_attribution'])+'</td></tr>' for c in q['categories'])
    cases=''.join('<tr><td>'+esc(c['review_id'])+'</td><td>'+esc(c['original_triage_category'])+'</td><td>'+esc(c['human_content_acceptable'])+'</td><td>'+esc(c['human_finding_label'] or 'No documented content finding')+'</td><td>'+esc(c['original_flag_disposition'])+'</td></tr>' for c in q['cases'] if c['content_review_complete'])
    metrics=''.join('<tr><td><b>'+esc(m['name'])+'</b><br>'+esc(m['unit'])+'</td><td>'+esc(m['numerator'])+'<br><b>Denominator:</b> '+esc(m['denominator'])+'</td><td>'+esc(m['handling'])+'</td><td>'+esc(m['available_now'])+'</td></tr>' for m in result['metrics'])
    quote=''
    if lossless:
        a=lossless['original_attempts'];b=lossless['later_recovery_attempts']
        quote=f'''<section><h2>Completed: strict quote-preservation audit</h2><p>The original raw result stays at <b>{a['raw_primary_scorable']}/{a['attempts']} attempts</b> meeting raw evidence checks. The frozen historical secondary parser makes {a['frozen_secondary_scorable']} scorable; the new strict lossless method makes {a['lossless_secondary_scorable']} scorable.</p><table><tr><th>Cohort</th><th>Raw primary</th><th>Historical secondary</th><th>Lossless secondary</th></tr><tr><td>Original {a['attempts']} attempts</td><td>{a['raw_primary_scorable']}</td><td>{a['frozen_secondary_scorable']}</td><td>{a['lossless_secondary_scorable']}</td></tr><tr><td>{b['attempts']} later recoveries</td><td>{b['raw_primary_scorable']}</td><td>{b['frozen_secondary_scorable']}</td><td>{b['lossless_secondary_scorable']}</td></tr></table><p>The old secondary method discards {a['frozen_discarded_value_segments']} quoted value segments in {a['frozen_cases_with_discarded_segments']} original responses. The strict method discards {a['lossless_discarded_value_segments']}; it recovers {a['raw_invalid_to_lossless_scorable']} of {a['raw_invalid_responses']} raw-invalid responses while preserving complete verified values and their artifact locators.</p><p><b>This repairs the measurement interface, not model reasoning.</b> It neither changes the saved verdicts nor establishes that the quotations support those verdicts. Raw, historical-normalized and lossless results remain distinct.</p><p><a href="lossless-audit.html">Every attempt and transformation</a> / <a href="lossless-audit.json">Machine-readable audit</a></p></section>'''
    pilot='''<section><h2>Inspection pilot: evidence preparation and execution remain separate</h2><p>Four artifacts across two source blocks are prepared: two fictional approval memos and two historical-workbook derivatives. One workbook error is deliberately constructed. They are not four new independently discovered model failures.</p><table><tr><th>Arm</th><th>Evidence</th><th>Interpretation</th></tr><tr><td>A</td><td>Sources and extracted text/cells</td><td>Static evidence baseline</td></tr><tr><td>B</td><td>A plus complete fixed rendered views and recorded recalculation</td><td>Effect of supplying additional inspection evidence</td></tr><tr><td>C</td><td>Same starting evidence as B plus bounded read-only follow-up</td><td>Also changes compute and possibly retrieved evidence; does not isolate agency</td></tr></table><p>12 planned sessions; at most 24 model requests, with no automatic retries. Human target judgments, source adequacy, complete inspection evidence and the bounded tool checks must be satisfied before execution. A dry run is an engineering check, not a model experiment.</p>'''
    if inspection:
        pilot+='<p><b>Saved offline status:</b> '+esc(inspection.get('status'))+'. Completed human control reviews: '+esc((inspection.get('human_reviews') or {}).get('complete_cases',0))+'/4. Live model requests: '+esc(inspection.get('executed_model_requests',0))+'. Complete rendered views: '+esc(inspection.get('complete_render_views','unverified'))+'. Offline tool checks pass: '+esc(inspection.get('offline_tool_checks_pass','unverified'))+'.</p>'
        pilot+='<p><a href="inspection-summary.json">Current inspection readiness, gates and evidence hashes</a></p>'
        if inspection.get('remaining_gates'):
            pilot+='<p><b>Remaining gates:</b></p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in inspection['remaining_gates'])+'</ul>'
    pilot+='<p><a href="../../code/reviews/agentic_judge_pilot_12/index.html">Four source/output review packets</a>. These new reviews are separate from the completed five-case assignment review. No unknown human label is filled from an author key or model vote.</p><p>The earlier eight-document / 40-request controls schedule remains deferred rather than being added automatically. It supplies optional repeated-prompt and substantive-edit controls after human validation.</p></section>'
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Evidence strengthening supplement</title><style>body{{font:16px/1.55 system-ui;margin:36px auto;padding:0 24px;max-width:1150px;color:#18323b}}h1{{font-size:32px}}h2{{margin-top:32px;font-size:23px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:10px;border-bottom:1px solid #d4dfdf;text-align:left;vertical-align:top;overflow-wrap:anywhere}}section{{margin:26px 0}}.note{{background:#edf5f0;padding:18px}}a{{color:#12665e}}</style><body><a href="../../index.html">Main submission</a><h1>Stronger evidence without inflating the findings</h1><p class="note">The original five-case review remains complete: two accepted outputs, three requiring correction, two source families. This supplement adds offline measurement checks, reconciles automated triage with human evidence, and records the next inspection experiment's readiness. The offline checks do not create new human findings, model rankings or training gains.</p>{quote}<section><h2>Completed: reconcile the 35 automated flags</h2><p>Only <b>{q['completed_content_reviews_in_queue']} of {q['automated_candidates']}</b> flagged outputs have completed human content reviews. Three have documented content findings; one was content-accepted but still has a separate mechanical page-overflow flag. <b>{q['unreviewed_candidates']}</b> remain unreviewed candidates. The fifth completed original review was outside this queue.</p><table><tr><th>Original triage category</th><th>Candidates</th><th>Content reviewed</th><th>Content findings</th><th>Original attribution</th></tr>{rows}</table><h3>Reviewed flags and the actual human disposition</h3><table><tr><th>Case</th><th>Original flag</th><th>Content acceptable</th><th>Human finding</th><th>Scope</th></tr>{cases}</table><p>These counts are a traceability audit, not a new taxonomy, flag precision estimate or claim that setup repairs resolve all flagged outputs.</p><p><a href="evidence-reconciliation.json">All 35 identities, source hashes and metric definitions</a></p></section>{pilot}<section><h2>Metrics with explicit denominators</h2><p>For the four-artifact pilot, show each case and each arm. Repeated artifacts share two source blocks; counts do not establish population reliability. Invalid, uncertain and missing outcomes remain visible.</p><table><tr><th>Metric / unit</th><th>Numerator and denominator</th><th>Required interpretation</th><th>Current evidence</th></tr>{metrics}</table></section><section><h2>Native workflow and commercial follow-up</h2><p>The earlier fixed-model native solver study still has ten attempts, five submissions and one complete pair. New inspection tooling can be reused, but local smoke checks cannot establish provider reliability or repair effects. Fresh permissioned families and controlled prompt/tool interventions come before any separately trained model.</p><p>Choose a model on total cost per accepted deliverable only after measuring human labor, repair cost, useful completion and a prespecified consequential-error threshold. That unit cost remains unknown; this update makes no paid calls.</p></section></body></html>'''
    if not packaged:
        page=page.replace('href="../../index.html"','href="../assignment_final/submission/index.html"').replace('href="../../code/reviews/','href="../../reviews/')
    return page


def main():
    out=ROOT/'output/strengthening_13';out.mkdir(parents=True,exist_ok=True)
    result=build(ROOT)
    (out/'evidence-reconciliation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lossless=read(out/'lossless-audit.json') if (out/'lossless-audit.json').exists() else None
    inspection=read(out/'inspection-summary.json') if (out/'inspection-summary.json').exists() else None
    (out/'index.html').write_text(render_html(result,lossless,inspection,packaged=False))
    print(json.dumps({k:result['queue_audit'][k] for k in ('automated_candidates','completed_content_reviews_in_queue','unreviewed_candidates','documented_content_findings_in_queue','reviewed_content_accepted_in_queue')}))


if __name__=='__main__':main()
