"""Build a truthful extension report and a verdict-hidden human review page."""
import hashlib
import html
import json
import os
import random
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v3'

def load(path):
    return json.loads(path.read_text())

def h(value):
    return html.escape(str(value))

def link(path, label, base=OUT):
    return f'<a href="{h(os.path.relpath(path,base))}">{h(label)}</a>'

STYLE='body{font:17px/1.55 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 22px;color:#172a39;background:#fafbfc}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;font-size:15px}th,td{border-bottom:1px solid #ccd4dc;padding:12px;text-align:left;vertical-align:top}a{color:#135f96}section{margin:35px 0}small{color:#4e5d6a}.note{border-left:4px solid #d7a540;padding:8px 16px;background:#fff9e9}label{display:block;margin:15px 0 5px}select,input,textarea,button{font:inherit;padding:8px;max-width:100%}textarea{width:95%;height:95px}button{cursor:pointer}details{margin:15px 0}pre{white-space:pre-wrap;font:14px/1.5 system-ui}'

def main():
    tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v3/tasks.jsonl').read_text().split('\n') if x.strip()]
    selection=load(ROOT/'data/evaluation_v3/selection.json')
    titles={r['task_id']:r['title'] for r in selection['selection']}
    baseline=load(ROOT/'output/evaluation_v2/report.json')
    rows=[]
    for task in tasks:
        tid=task['task_id'];folder=OUT/'solver'/tid
        manifest=folder/'submission_manifest.json'
        artifacts=load(manifest) if manifest.exists() else []
        grade=OUT/'assessments'/f'{tid}.json'
        assessment=load(grade) if grade.exists() else None
        rows.append({'task_id':tid,'title':titles[tid],'occupation':task['occupation'],
          'solver_started':(folder/'state.json').exists(),'native_submitted':bool(artifacts),
          'artifacts':artifacts,'assessment':assessment,'human_acceptance':None})
    cost=baseline['cost']
    decisions=Counter(r['assessment'].get('overall','unavailable') for r in rows if r['assessment'])
    criterion_counts=Counter(c.get('verdict','unavailable') for r in rows if r['assessment'] for c in r['assessment'].get('criteria',[]))
    report={'schema':'evaluation-v3-report-1','generated_at':datetime.now(timezone.utc).isoformat(),
      'new_original_tasks_selected':5,'new_native_submitted_tasks':sum(x['native_submitted'] for x in rows),
      'new_tasks_with_assessment':sum(x['assessment'] is not None for x in rows),
      'new_native_files':sum(len(x['artifacts']) for x in rows),
      'prior_original_tasks_with_native_outputs':15,'combined_original_tasks_selected':20,
      'combined_original_tasks_with_native_outputs':15+sum(x['native_submitted'] for x in rows),
      'original_occupations':3,'additional_occupations':3,'fresh_human_reviews':0,
      'new_openrouter_spend_usd':0,'in_app_inference_cost_usd':None,
      'existing_known_provider_cost_usd':cost['known_provider_cost_usd'],
      'existing_uncertain_charge_reserve_usd':cost['unresolved_reserved_usd'],
      'budget_headroom_usd':30-cost['known_provider_cost_usd']-cost['unresolved_reserved_usd'],
      'provisional_project_rubric_task_counts':dict(decisions),'criterion_counts_not_independent_samples':dict(criterion_counts),
      'limitations':['Separate in-app requested GPT-6.1 Sol cohort; served model snapshot and app inference price not independently reported.',
       'Purposive partial occupational coverage; no random sampling or population acceptance estimate.',
       'No standardized API turn/token limit; do not pool task outcomes with v2 as comparable rates.',
       'Model judgments are provisional; same-family judge is not independent human truth.',
       'Native tool events are retained; they are not full provider conversation traces.',
       'Fresh human acceptance and cost per accepted deliverable remain unmeasured.'], 'tasks':rows}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    body=['<h1>Five additional original GDPval tasks</h1>',
      f'<p><strong>{report["combined_original_tasks_with_native_outputs"]} original tasks have native outputs.</strong> The earlier 15 and this five-task extension use different execution setups and remain separate cohorts.</p>',
      '<p class="note">Submission is not acceptance. Fresh human reviews: 0. No model ranking, expert acceptance rate, or validated judge accuracy is claimed.</p>',
      f'<p>Extension: {report["new_native_submitted_tasks"]}/5 submitted tasks; {report["new_native_files"]} files; {report["new_tasks_with_assessment"]}/5 assessment records.</p>',
      '<table><tr><th>Original task</th><th>Occupation</th><th>Native output</th><th>Model assessment</th></tr>']
    for row in rows:
        arts='<br>'.join(link(Path(a['path']),a['filename']) for a in row['artifacts']) or 'Pending'
        assessment=row['assessment'];labels={'no_confirmed_issue':'Provisional rubric pass','requires_revision':'Revision candidate','unresolved':'Unresolved'};decision=h(labels.get(assessment.get('decision'),assessment.get('decision','recorded'))) if assessment else 'Pending'
        if assessment:decision+=' · '+link(OUT/'assessments'/f'{row["task_id"]}.json','Evidence')
        body.append(f'<tr><td>{h(row["title"])}<br><small>{h(row["task_id"])}</small></td><td>{h(row["occupation"])}</td><td>{arts}</td><td>{decision}</td></tr>')
    body+=['</table>']
    probe_path=OUT/'independent-checks/payroll-behavior/result.json'
    if probe_path.exists():
        probe=load(probe_path)
        body+=['<h2>Strongest new review case</h2>',
          '<p>The contract conditions the 15% quartet premium on the quartet constituting the entire acoustic string section. In the workbook, that condition remains false (Rates!B20 = 0). Marking one musician as a quartet player creates a conflict. Selecting premium approval then changes the warning to <strong>OK - roles approved</strong>, even though eligibility remains false.</p>',
          '<table><tr><th>Controlled input state</th><th>Role status</th><th>Quartet premium</th><th>Calculated gross</th></tr>']
        for case in probe['cases']:
            label={'baseline':'Original inputs','conflict_unapproved':'Quartet selected; approval off','conflict_approved':'Same conflict; approval on'}[case['case']]
            body.append(f'<tr><td>{label}</td><td>{h(case["role_status"])}</td><td>${case["quartet_premium_usd"]:,.2f}</td><td>${case["person_gross_usd"]:,.2f}</td></tr>')
        body+=['</table><p>The quartet input increases calculated gross by $374.02, including vacation pay. Approval changes the warning, with no additional pay change. Other workbook review flags remain. This is a controlled behavior test of the original deliverable; the original saved sample was not shown to be overpaid and no payment occurred.</p>',
          '<p><strong>Human decision:</strong> Should premium approval be allowed to remove a conflict while the contract eligibility condition remains false?</p>',
          '<p>'+link(probe_path,'Reproduction evidence')+' · '+link(OUT/'judge-packets/4520f882-715a-482d-8e87-1cb3cbdfe975/sources/S2.docx','Source contract')+' · '+link(OUT/'independent-checks/payroll-behavior/recalculated/conflict_approved.xlsx','Controlled test copy')+'</p>',
          '<p>This supports a testable data opportunity: source rules, conflicting inputs, approval states and expected warnings can form human-adjudicated evaluation examples. It does not prove that training on those examples improves a model or that another judge would miss the error.</p>']
    body+=['<h2>Other new findings</h2><p>The other four outputs received provisional project-rubric passes. Cleanup preserved all 51 schedule rows. Tour figures matched independent arithmetic. Prepaid balances reconciled under disclosed assumptions. Staffing artifacts agreed on a 237-to-224 FTE plan. Accounting and HR assumptions still need appropriate human owners to confirm them.</p>',
      '<p>These are task-level diagnostic results. The grader used 43 project criteria, not the official GDPval scoring system. Human acceptance is still unmeasured.</p>',
      '<h2>What the earlier run established</h2>',
      '<p>All 15 original tasks have deliverables after separately recorded recovery. First attempts submitted 11. Three failed through infrastructure and one ended without submission. Extra-model comparisons reached only two tasks and two occupations.</p>',
      '<p>Independent assistant checks of six outputs found no definite substantive business error in those six. Recalculation matched 379 NPV/workload cells. The GMP PDF has visible field overflow, while inventory source data contains unmatched product IDs. These findings require different remedies and do not establish expert acceptance.</p>',
      '<p>Grader validity remains incomplete. The historical five human reviews are development labels, not reviews of the fresh runs. Formatting repairs to judge responses improve usability of the records without proving the judgments correct.</p>',
      '<h2>Cost and method</h2>',
      f'<p>Earlier confirmed provider charges: ${report["existing_known_provider_cost_usd"]:.4f}. Unresolved-charge reserves: ${report["existing_uncertain_charge_reserve_usd"]:.4f}. Remaining under the $30 guard: ${report["budget_headroom_usd"]:.4f}. Reserves are commitments, not confirmed spending.</p>',
      '<p>This extension makes no OpenRouter inference calls. In-app model usage cost is unavailable and is not reported as free. Original task prompts and source bytes are retained. All 13 inputs passed native extraction/render checks before solving. Namespace-only import copies repair compatibility without rewriting source content.</p>',
      '<p>Requested in-app models: GPT-6.1 Sol for solving and GPT-6 Astra for judging. Both belong to the OpenAI family. Exact served snapshots/settings are not independently reported. The judge is author-hidden and separate from the solver, but this does not establish cross-family validation or judge accuracy.</p>',
      '<p>Five tasks were selected before observing their outputs: two accounting, two administrative services, one financial management. This is a targeted diagnostic extension, not full coverage of the new occupations.</p>',
      '<p>'+link(ROOT/'docs/evaluation_v3/protocol.txt','Protocol')+' · '+link(ROOT/'data/evaluation_v3/selection.json','Selection')+' · '+link(ROOT/'data/evaluation_v3/project-rubrics.json','Frozen project rubric')+' · '+link(OUT/'freeze.json','Input hashes')+' · '+link(ROOT/'output/evaluation_v2/report.html','Earlier report')+'</p>',
      '<h2>Human review</h2><p>Review the original task, source and output before looking at the model assessment. Record accept/revise/uncertain, evidence, business consequence and time spent.</p><p>'+link(OUT/'human-review.html','Open the five-case review page')+'</p>']
    (OUT/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>GDPval extension report</title><style>'+STYLE+'</style><body>'+''.join(body)+'</body></html>')
    order=list(rows);random.Random('gdpval-v3-review-2026-11-04').shuffle(order)
    review=['<h1>Review five original task outputs</h1><p>Read the source and output before recording your judgment. Grader verdicts and solver labels are omitted from this page. These five outputs belong to one cohort; anonymity does not create a model comparison.</p><p>Your entries stay in this browser until you download the review file. Downloading does not submit them to the study automatically.</p><button onclick="downloadReviews()">Download my reviews</button>']
    mapping=[]
    for n,row in enumerate(order,1):
        tid=row['task_id'];task=next(t for t in tasks if t['task_id']==tid)
        artifact_hashes=[a['sha256'] for a in row['artifacts']]
        case='V3-'+hashlib.sha256((tid+'|'+'|'.join(artifact_hashes)).encode()).hexdigest()[:8]
        mapping.append({'case_id':case,'task_id':tid,'artifact_sha256':artifact_hashes})
        files='<br>'.join(link(ROOT/r['local_path'],r['name']) for r in task['references'])
        artifacts='<br>'.join(link(Path(a['path']),a['filename']) for a in row['artifacts']) or 'Output not yet submitted.'
        review.append(f'<section data-case="{case}"><h2>Case {n}: {h(row["title"])}</h2><small>{case}</small><details><summary>Original task</summary><pre>{h(task["prompt"])}</pre></details><p><strong>Sources</strong><br>{files}</p><p><strong>Deliverables</strong><br>{artifacts}</p><label>Would you accept this for its intended use?</label><select data-field="acceptance"><option value="">Choose</option><option>Accept</option><option>Minor revision</option><option>Major revision</option><option>Unusable</option><option>Uncertain</option></select><label>Does it contain a consequential business error?</label><select data-field="consequential_error"><option value="">Choose</option><option>Yes</option><option>No</option><option>Uncertain</option></select><label>Evidence: source rule or value, output location, and consequence</label><textarea data-field="evidence"></textarea><label>Minimum correction, if needed</label><textarea data-field="correction"></textarea><label>Minutes spent</label><input data-field="minutes" type="number" min="0"><label>Your relevant professional experience</label><input data-field="reviewer_experience" type="text"></section>')
    exposure='<label>Have you seen the model assessment or analysis of this case?</label><select data-field="prior_exposure"><option value="">Choose</option><option>No</option><option>Yes</option><option>Unsure</option></select>'
    review=[part.replace('</section>',exposure+'</section>') for part in review]
    script='''const key='turing-v3-human-review';let saved=JSON.parse(localStorage.getItem(key)||'{}');document.querySelectorAll('[data-case]').forEach(s=>{s.querySelectorAll('[data-field]').forEach(e=>{e.value=saved[s.dataset.case]?.[e.dataset.field]||'';e.oninput=()=>{saved[s.dataset.case]||={};saved[s.dataset.case][e.dataset.field]=e.value;localStorage.setItem(key,JSON.stringify(saved));};});});function downloadReviews(){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({schema:'v3-human-review-1',exported_at:new Date().toISOString(),reviews:saved},null,2)],{type:'application/json'}));a.download='gdpval-five-human-reviews.json';a.click();URL.revokeObjectURL(a.href);}'''
    (OUT/'human-review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Five case human review</title><style>'+STYLE+'</style><body>'+''.join(review)+'<script>'+script+'</script></body></html>')
    (OUT/'review-mapping.json').write_text(json.dumps(mapping,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['new_native_submitted_tasks','new_native_files','new_tasks_with_assessment','combined_original_tasks_with_native_outputs']}))

if __name__=='__main__':
    main()
