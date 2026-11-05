"""Rebuild a task inventory report without pooling unlike evaluation cohorts.

Reads only existing records. Missing submissions, assessments and human labels
stay missing. Native submission and contract validity do not imply acceptance.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import hashlib
import html
import json
import os
import csv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evaluation_v4'


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def relative(path):
    path = Path(path)
    return str(path.relative_to(ROOT)) if path.is_absolute() and path.is_relative_to(ROOT) else str(path)


def short_artifact(a):
    return {k: a.get(k) for k in ('filename', 'path', 'sha256', 'kind', 'revision', 'inspected') if k in a}


def link(path, label):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    target = quote(os.path.relpath(path, OUT), safe='/')
    return f'<a href="{target}">{html.escape(str(label))}</a>'


def trace_files(folder):
    paths = []
    for pattern in ('state.json', 'checkpoint.json', 'result.json', 'turn-*.json', 'trace*.json*', 'events*.json*', 'requests/*.json', 'builder*.json*', 'builds/*/build.json', 'builds/*/builder.*', 'external-sources.json', 'history/*/r*/provenance.json'):
        paths += sorted(folder.glob(pattern))
    return sorted({relative(p) for p in paths})


def validation_map(cohort):
    data = read(ROOT / f'output/{cohort}/assessments/validation.json', {})
    checks = data.get('checks', data.get('tasks', [])) if isinstance(data, dict) else data
    return {r['task_id']: {k: r.get(k) for k in ('contract_valid', 'contract_problems', 'criteria_counts')} for r in checks if isinstance(r, dict) and r.get('task_id')}


def assessment_summary(a, path, validation=None):
    return {'path': relative(path), 'overall': a.get('overall'), 'decision': a.get('decision'),
            'assessment_status': a.get('assessment_status'), 'contract_validation': validation,
            'criterion_counts': dict(Counter(c.get('verdict', 'unknown') for c in a.get('criteria', []))),
            'highest_flag_severity':max([c.get('severity') or 0 for c in a.get('criteria',[]) if c.get('verdict')=='fail'] or [0]),
            'provisional_flags':[{'criterion_id':c.get('criterion_id'),'severity':c.get('severity'),'failure_class':c.get('failure_class'),'reason':c.get('reason')} for c in a.get('criteria',[]) if c.get('verdict')=='fail'],
            'unresolved_questions': a.get('unresolved_questions', []),
            'suggested_first_human_question': a.get('suggested_first_human_question')}


def build():
    roster_path = ROOT / 'data/evaluation_v4/task-roster.json'
    roster = read(roster_path)
    assert len(roster) == 40 and len({r['task_id'] for r in roster}) == 40
    v2 = read(ROOT / 'output/evaluation_v2/report.json', {})
    v3 = read(ROOT / 'output/evaluation_v3/report.json', {})
    config = read(ROOT / 'config/evaluation_v4_run.json', {})
    source = read(ROOT / 'docs/evaluation_v4/source-audit.json', {})
    source_tasks = {r['task_id']: r for r in source.get('tasks', [])}
    prior2 = {r['task_id']: r for r in v2.get('task_roster', [])}
    prior3 = {r['task_id']: r for r in v3.get('tasks', [])}
    validations = {c: validation_map(c) for c in ('evaluation_v3', 'evaluation_v4')}
    execution_path = ROOT / 'output/evaluation_v4/execution-manifest.json'
    if not execution_path.exists():
        execution_path = ROOT / 'data/evaluation_v4/execution-manifest.json'
    execution = read(execution_path)
    runs = [r for k in ('primary_runs', 'recovery_runs', 'adapter_repair_runs', 'supplemental_runs') for r in v2.get(k, [])]
    solver_execution={r['task_id']:r for r in (execution or {}).get('solver_agents',[])}
    rows = []
    for frozen in roster:
        tid = frozen['task_id']
        row = {**frozen, 'selected': True, 'started': False, 'submitted': False, 'assessment_records': [],
               'artifacts': [], 'traces': [], 'runs': [], 'human_review_count': 0, 'human_acceptance': None,
               'source_issues': source_tasks.get(tid, {}).get('issues', [])}
        if frozen['status'] == 'existing_v2_native_output':
            row['cohort'] = 'v2 API (including separate recoveries)'
            row['title'] = prior2.get(tid, {}).get('name', tid[:8])
            task_runs = [r for r in runs if r.get('task_id') == tid]
            row['started'] = bool(task_runs)
            for r in task_runs:
                row['artifacts'] += [short_artifact(a) for a in r.get('submission', [])]
                folder = ROOT / 'output/evaluation_v2/runs' / r['run_id']
                row['traces'] += trace_files(folder)
                row['runs'].append({k: r.get(k) for k in ('run_id', 'model', 'stage', 'status', 'cost', 'served_providers')})
            for j in v2.get('judgments', []):
                if j.get('task_id') == tid:
                    row['assessment_records'].append({k: j.get(k) for k in ('record_path', 'run_id', 'judge_model', 'status', 'validation_status', 'validation_errors', 'project_rubric_pass', 'solver_cohort')})
            row['source_issues'] += [{'kind': 'historical_source_flag', 'evidence': flag} for flag in prior2.get(tid, {}).get('source_quality_flags', [])]
            row['contract_valid_assessment_present'] = any(j.get('status') == 'graded' for j in row['assessment_records'])
        else:
            cohort = 'evaluation_v3' if frozen['status'] == 'existing_v3_native_output' else 'evaluation_v4'
            row['cohort'] = 'v3 in-app extension' if cohort == 'evaluation_v3' else 'v4 in-app, native builders and research'
            folder = ROOT / 'output' / cohort / 'solver' / tid
            manifest = read(folder / 'submission_manifest.json', [])
            if isinstance(manifest, dict):
                manifest = manifest.get('artifacts', manifest.get('files', manifest.get('submission', [])))
            row['artifacts'] = [short_artifact(a) for a in manifest]
            row['started'] = (folder / 'state.json').exists() or bool(manifest)
            row['traces'] = trace_files(folder)
            row['title'] = prior3.get(tid, {}).get('title', source_tasks.get(tid, {}).get('title', tid[:8]))
            row['prompt_path'] = f'data/{cohort}/solver/{tid}/prompt.txt'
            if not (ROOT / row['prompt_path']).exists():
                row['prompt_path'] = f'data/{cohort}/tasks.jsonl'
            grade_path = ROOT / 'output' / cohort / 'assessments' / f'{tid}.json'
            grade = read(grade_path)
            validation = validations[cohort].get(tid)
            if grade is not None:
                row['assessment_records'] = [assessment_summary(grade, grade_path, validation)]
            row['contract_valid_assessment_present'] = bool(grade and validation and validation.get('contract_valid') is True)
        row['submitted'] = bool(row['artifacts'])
        row['assessment_record_present'] = bool(row['assessment_records'])
        row['status_now'] = 'assessed' if row['assessment_record_present'] and row['submitted'] else 'submitted' if row['submitted'] else 'started' if row['started'] else 'not started'
        row['artifact_count'] = len(row['artifacts'])
        row['execution_record']=solver_execution.get(tid)
        row['transport_interruption_count']=len((row['execution_record'] or {}).get('continuations',[]))
        row['fresh_context_recovery']=bool((row['execution_record'] or {}).get('active_recovery_agent'))
        review_path = OUT / 'human-reviews' / f'{tid}.json'
        review = read(review_path)
        row['human_review'] = review
        row['human_review_path'] = relative(review_path) if review else None
        if review and review.get('status') == 'complete':
            row['human_review_count'] = 1
            row['human_acceptance'] = review.get('human_acceptance')
        row['human_review_classification'] = review.get('review_classification') if review else None
        row['human_review_minutes'] = review.get('review_minutes') if review else None
        row['human_review_expert_validation'] = review.get('expert_validation') if review else None
        rows.append(row)
    reviewed = [r for r in rows if r['human_review_count']]
    human_summary = {'completed_reviews': len(reviewed),
                     'expert_reviews': sum(r['human_review'].get('expert_validation') is True for r in reviewed),
                     'blind_reviews': sum(r['human_review'].get('blind_calibration_label') is True for r in reviewed),
                     'total_review_minutes': sum(r['human_review_minutes'] or 0 for r in reviewed),
                     'record_paths': [r['human_review_path'] for r in reviewed],
                     'scope': 'Selected diagnostic user reviews; preserve expertise, exposure and criterion scope. No population acceptance rate or judge accuracy follows from this selection.'}
    groups = {}
    for cohort in dict.fromkeys(r['cohort'] for r in rows):
        group = [r for r in rows if r['cohort'] == cohort]
        groups[cohort] = {'selected_tasks': len(group), 'started_tasks': sum(r['started'] for r in group),
                         'submitted_tasks': sum(r['submitted'] for r in group),
                         'tasks_with_assessment_record': sum(r['assessment_record_present'] for r in group),
                         'tasks_with_contract_valid_assessment': sum(r['contract_valid_assessment_present'] for r in group),
                         'v4_tasks_with_recorded_transport_interruption':sum(r['transport_interruption_count']>0 for r in group) if cohort.startswith('v4 ') else None,
                         'v4_tasks_with_fresh_context_recovery':sum(r['fresh_context_recovery'] for r in group) if cohort.startswith('v4 ') else None,
                         'human_reviewed_tasks': sum(r['human_review_count'] > 0 for r in group)}
    counts = {'selected_tasks': len(rows), 'started_tasks': sum(r['started'] for r in rows),
              'submitted_tasks': sum(r['submitted'] for r in rows),
              'tasks_with_assessment_record': sum(r['assessment_record_present'] for r in rows),
              'tasks_with_contract_valid_assessment': sum(r['contract_valid_assessment_present'] for r in rows),
              'human_reviewed_tasks': len(reviewed), 'occupations': len({r['occupation'] for r in rows})}
    cost_detail=read(OUT/'costs.json',{})
    cost_by_task={r['task_id']:r for r in cost_detail.get('tasks',[])}
    for row in rows:
        row['cost_accounting']=cost_by_task.get(row['task_id'])
    cost = {'api_limit_usd': config.get('api_total_limit_usd', 30),
            'known_provider_cost_usd': config.get('budget_snapshot_confirmed_usd', 12.6855182),
            'unresolved_charge_reserve_usd': config.get('budget_snapshot_unresolved_charge_reserves_usd', 16.61936074),
            'new_v4_openrouter_spend_usd': config.get('new_openrouter_spend_usd', 0),
            'in_app_inference_cost_usd': None, 'in_app_token_usage': None,
            'note': 'Reserves are conservative commitments, not confirmed charges or wallet balances. In-app cost is unavailable, not free.'}
    cost['committed_usd'] = cost['known_provider_cost_usd'] + cost['unresolved_charge_reserve_usd'] + cost['new_v4_openrouter_spend_usd']
    cost['headroom_usd'] = cost['api_limit_usd'] - cost['committed_usd']
    queue = []
    for r in rows:
        if not r['submitted']:
            continue
        suggested = next((a.get('suggested_first_human_question') for a in r['assessment_records'] if a.get('suggested_first_human_question')), None)
        queue.append({'task_id': r['task_id'], 'title': r['title'], 'cohort': r['cohort'],
                      'question': suggested or 'Using the original sources and task, would you accept this deliverable for its intended use? Record the decisive passage or native behavior and minimum correction.',
                      'source_issues': r['source_issues'], 'artifact_paths': [a['path'] for a in r['artifacts'] if a.get('path')],
                      'highest_flag_severity':max([a.get('highest_flag_severity',0) for a in r['assessment_records']] or [0]),
                      'status': 'diagnostic user review complete; expert validation not established' if r['human_review_count'] else 'needs human review',
                      'human_review_path': r['human_review_path'], 'is_blinded': False})
    queue.sort(key=lambda r: (-r['highest_flag_severity'], not bool(r['source_issues']), r['cohort'], r['task_id']))
    return {'schema': 'evaluation-v4-inventory-report-1', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'roster_sha256': hashlib.sha256(roster_path.read_bytes()).hexdigest(), 'counts': counts,
            'cohorts': groups, 'cost': cost, 'v2_primary_grade_status_counts': v2.get('effective_primary_grade_status_counts', {}),
            'execution_manifest_path': relative(execution_path) if execution is not None else None,
            'execution_manifest': execution, 'config_path': 'config/evaluation_v4_run.json',
            'source_audit_path': 'docs/evaluation_v4/source-audit.json',
            'selection_method_path': 'docs/evaluation_v4/selection-method.txt',
            'artificial_analysis_addendum_path': 'docs/evaluation_v4/artificial-analysis-method-addendum.txt',
            'human_review_summary': human_summary,
            'human_acceptance_rate': None, 'cost_per_accepted_deliverable': None,
            'limitations': [
                'Forty unique original tasks across eight occupations; purposive occupational selection, all five public tasks per occupation.',
                'API runs, recoveries, earlier in-app runs and new in-app native-builder/research runs have different conditions. No pooled pass score or model ranking.',
                'An assessment record may be invalid, budget-limited or a no-submission record. Contract-valid means required structure and fields passed validation; quote-screen flags requiring manual review are retained. It does not establish human-confirmed accuracy.',
                'Historical five-case human reviews concern earlier outputs; they do not automatically label these forty tasks or the new deliverables.',
                'Selected diagnostic user decisions are reported with their scope and reviewer background. Expert acceptance, representative human acceptance, judge accuracy and cost per accepted deliverable remain unmeasured.',
                'In-app requested model names do not independently verify served snapshots; native tool traces are not complete provider conversation logs.',
                'Source gaps, contradictory instructions, harness failure and substantive document errors must be reported separately.',
                'The local review queue is triage, not a blinded labeling interface. Hide author and judge information before collecting calibration labels.'
            ], 'tasks': rows, 'review_queue': queue}


def render(report):
    h = lambda x: html.escape(str(x))
    c, cost = report['counts'], report['cost']
    parts = ['<h1>Forty original GDPval tasks</h1>',
             ('<p class="note"><b>New cross-family grading extension:</b> ' + link(ROOT / 'output/evaluation_v5/report.html', 'Gemini, Claude and Astra comparison, traces and reconciled API costs') + '. This page retains the original v4 assessment snapshot; the extension reports new reviews separately.</p>') if (ROOT / 'output/evaluation_v5/report.html').exists() else '',
             '<p>Traceable task inventory and provisional assessments. Submission is not acceptance.</p>',
             f'<div class="cards"><strong>{c["selected_tasks"]}<small>selected</small></strong><strong>{c["started_tasks"]}<small>started</small></strong><strong>{c["submitted_tasks"]}<small>submitted</small></strong><strong>{c["tasks_with_assessment_record"]}<small>assessment records</small></strong><strong>{c["tasks_with_contract_valid_assessment"]}<small>contract-valid assessments</small></strong><strong>{c["human_reviewed_tasks"]}<small>tasks with a diagnostic user review</small></strong></div>',
             '<p class="note">The cohorts below remain separate. Counts describe inventory, not comparable performance. Representative human acceptance, expert acceptance and cost per accepted deliverable are unmeasured.</p>',
             '<p>The new twenty-task cohort requests <b>GPT-6.1 Sol</b> as solver and a separate author-hidden <b>GPT-6 Astra</b> context as judge. Both are from the OpenAI family. Exact served builds, seeds, temperature, token usage and app inference cost are unavailable. These are project-rubric assessments, not official GDPval scores or Artificial Analysis Elo.</p>',
             f'<p>Known API charges <b>${cost["known_provider_cost_usd"]:.6f}</b>; unresolved-charge reserves <b>${cost["unresolved_charge_reserve_usd"]:.6f}</b>; committed <b>${cost["committed_usd"]:.6f}</b> of <b>${cost["api_limit_usd"]:.2f}</b>. New v4 OpenRouter charges: <b>${cost["new_v4_openrouter_spend_usd"]:.2f}</b>. In-app inference cost: <b>unavailable, not free</b>.</p>',
             '<p>' + ' · '.join(link(report[k], label) for k, label in [('selection_method_path', 'Selection rationale'), ('artificial_analysis_addendum_path', 'Artificial Analysis method comparison'), ('source_audit_path', 'Source audit'), ('config_path', 'Run configuration')]) + ' · ' + link(OUT / 'report.json', 'Report JSON') + ' · ' + link(OUT / 'costs.json', 'Cost ledger and allocation') + ' · ' + link(OUT / 'task-costs.csv', '40-task costs CSV') + ' · ' + link(OUT/'task-results.csv','40-task results and trace index') + '</p>',
             '<table><thead><tr><th>Cohort</th><th>Selected</th><th>Started</th><th>Submitted</th><th>Assessment record</th><th>Contract-valid assessment</th></tr></thead><tbody>']
    for name, stats in report['cohorts'].items():
        parts.append('<tr><td>' + h(name) + '</td>' + ''.join(f'<td>{stats[k]}</td>' for k in ('selected_tasks', 'started_tasks', 'submitted_tasks', 'tasks_with_assessment_record', 'tasks_with_contract_valid_assessment')) + '</tr>')
    parts += ['</tbody></table>']
    if report['human_review_summary']['completed_reviews']:
        parts.append('<h2>Recorded diagnostic human reviews</h2><p>These selected, evidence-assisted decisions retain their reviewer background and scope. They do not establish expert acceptance or judge accuracy.</p>')
        for row in report['tasks']:
            if not row['human_review_count']: continue
            review = row['human_review']
            correction = 'Minimum correction endorsed.' if review.get('minimum_correction_endorsed') is True else 'Minimum correction not recorded.'
            if review.get('minimum_correction_status') == 'not_required_for_original_task_acceptance_on_this_issue':
                correction = 'No correction required for acceptance on the reviewed issue; robustness improvement is optional.'
            parts.append('<p><b>'+h(row['title'])+'</b>: '+h(review.get('acceptance_decision')).replace('_',' ')+'. '+h(review.get('review_classification')).replace('_',' ')+'; '+h(review.get('review_minutes'))+' minutes. '+h(correction)+' '+link(row['human_review_path'],'Review answers and scope')+'</p>')
    new_assessments=[a for r in report['tasks'] if r['cohort'].startswith('v4 ') for a in r['assessment_records'] if (a.get('contract_validation') or {}).get('contract_valid')]
    new_counts=Counter(a.get('overall') for a in new_assessments)
    if new_assessments:
        parts.append('<h2>What the new twenty show</h2><p>'+str(len(new_assessments))+' structurally valid provisional assessments: <b>'+str(new_counts.get('project_rubric_pass',0))+' pass</b>, <b>'+str(new_counts.get('project_rubric_uncertain',0))+' uncertain</b>, and <b>'+str(new_counts.get('project_rubric_fail',0))+' flagged</b> under the frozen project rubric. These are model judgments, not expert acceptance labels.</p>')
        order_review = next((r['human_review'] for r in report['tasks'] if r['task_id']=='1137e2bb-bdf9-4876-b572-f29b7de5e595' and r['human_review_count']), None)
        order_scope = 'The added robustness criterion\'s relevance to this fixed audit needs human review.'
        if order_review and order_review.get('scope_decision',{}).get('required_for_original_task_acceptance') is False:
            order_scope = 'The completed non-specialist, evidence-assisted review treats this as optional robustness and accepts the workbook on the supplied evidence. The raw project-rubric failure remains recorded; this is not expert calibration of the judge.'
        planogram_review = next((r['human_review'] for r in report['tasks'] if r['task_id']=='0fad6023-767b-42c1-a1b3-027cd4f583cb' and r['human_review_count']), None)
        planogram_review_note = ''
        if planogram_review and planogram_review.get('acceptance_decision')=='requires_revision_before_acceptance':
            planogram_review_note = ' The completed non-specialist, evidence-assisted review requires revision based on the observed clipping. Layout correction and fresh print/Excel checks were endorsed; those corrections and checks have not been performed.'
        parts.append('<ul><li><b>Saved calculation error:</b> the tax draft understates regular tax by $2,046 under its own assumptions. The source table and arithmetic are independently reproduced; other missing tax inputs remain unresolved.</li><li><b>Conditional robustness issue:</b> the order audit is correct on the original export. Division errors appear only after changing a positive case pack to zero or blank. '+h(order_scope)+'</li><li><b>Viewer-dependent presentation issue:</b> the planogram\'s final instructions line clips in LibreOffice print export. The main planogram prints correctly; Microsoft Excel reproduction remains untested.'+h(planogram_review_note)+'</li></ul>')
    recovered=[r for r in report['tasks'] if r.get('fresh_context_recovery')]
    if recovered:
        parts.append('<p class="note">'+str(len(recovered))+' new task(s) required a separate context after transport interruption. Their initial interrupted attempts remain in the execution manifest; eventual submissions are recovered coverage, not uninterrupted first-attempt success. '+link(OUT/'execution-manifest.json','Execution and recovery record')+'</p>')
    evidence_links=[]
    for path,label in [(OUT/'analysis.txt','Analysis and interpretation'),(OUT/'analysis.json','Analysis JSON'),(OUT/'assessments/validation.json','Judgment contract and quote checks'),(OUT/'final-integrity.json','Final source, submission and packet integrity'),(ROOT/'docs/evaluation_v4/grading-scope-review.txt','Order-audit grading scope'),(ROOT/'docs/evaluation_v4/assessment-context.json','Flag context and limitations'),(OUT/'independent-checks/branch-native-quote.json','Native dropdown quote check'),(OUT/'independent-checks/tax-regular-rate.json','Independent tax-error reproduction')]:
        if path.exists():evidence_links.append(link(path,label))
    if evidence_links:parts.append('<p>'+' · '.join(evidence_links)+'</p>')
    parts += [f'<p><small>Earlier v2 primary-grade statuses: {h(report["v2_primary_grade_status_counts"])}. A task can have several attempts and judgments; recoveries do not rewrite primary-run results.</small></p>',
              '<h2>Task evidence</h2><div class="controls"><input id="search" placeholder="Search occupation, task or issue" aria-label="Search tasks"><select id="cohort"><option value="">All cohorts</option>' + ''.join(f'<option>{h(x)}</option>' for x in report['cohorts']) + '</select><select id="status"><option value="">All statuses</option><option>not started</option><option>started</option><option>submitted</option><option>assessed</option></select></div><p id="visible"></p>',
              '<table id="tasks"><thead><tr><th>Task / occupation</th><th>Cohort / status</th><th>Deliverables and traces</th><th>Assessment and source issues</th></tr></thead><tbody>']
    for row in report['tasks']:
        artifacts = '<br>'.join(link(a['path'], a.get('filename', Path(a['path']).name)) for a in row['artifacts'] if a.get('path')) or 'No submitted artifact'
        traces = '<details><summary>Native trace files (' + str(len(row['traces'])) + ')</summary>' + '<br>'.join(link(p, Path(p).name) for p in row['traces']) + '</details>' if row['traces'] else ''
        assessments = []
        for a in row['assessment_records']:
            path = a.get('path') or a.get('record_path')
            label = a.get('overall') or a.get('status') or 'Assessment record'
            assessments.append(link(path, label) if path else h(label))
        if row['human_review_count']:
            assessments.append(link(row['human_review_path'], 'Diagnostic user review: '+str(row['human_review'].get('acceptance_decision')).replace('_',' ')))
        issues = ''.join('<li>' + h(i.get('kind')) + ': ' + h(i.get('evidence')) + '</li>' for i in row['source_issues'])
        prompt = ('<br>' + link(row['prompt_path'], 'Original prompt')) if row.get('prompt_path') else ''
        if row.get('fresh_context_recovery'):prompt+='<br><small>Separate context after '+str(row['transport_interruption_count'])+' transport interruptions</small>'
        search = h(json.dumps([row['title'], row['task_id'], row['occupation'], row['source_issues']], ensure_ascii=False).lower())
        parts.append(f'<tr data-search="{search}" data-cohort="{h(row["cohort"])}" data-status="{h(row["status_now"])}"><td><b>{h(row["title"])}</b><br>{h(row["occupation"])}<br><small>{h(row["task_id"])}</small>{prompt}</td><td>{h(row["cohort"])}<br><b>{h(row["status_now"])}</b></td><td>{artifacts}{traces}</td><td>{"<br>".join(assessments) or "No assessment"}<ul>{issues}</ul></td></tr>')
    parts += ['</tbody></table><h2>Local human-review queue</h2><p>This is a review triage list, not blind calibration. Record acceptance, evidence, minimum correction and minutes spent. Hide model identity and judge verdicts in a separate labeling session.</p>']
    for q in report['review_queue']:
        recorded = '<p>'+h(q['status'])+'. '+link(q['human_review_path'],'Recorded review')+'</p>' if q.get('human_review_path') else ''
        parts.append('<details><summary>' + h(q['title']) + '</summary>'+recorded+'<p>' + h(q['question']) + '</p><p>' + '<br>'.join(link(p, Path(p).name) for p in q['artifact_paths']) + '</p></details>')
    parts += ['<h2>Interpretation limits</h2><ul>' + ''.join('<li>' + h(x) + '</li>' for x in report['limitations']) + '</ul>', '<footer>Built ' + h(report['generated_at_utc']) + '</footer>']
    style = 'body{max-width:1360px;margin:35px auto;padding:0 24px;color:#20323d;background:#f8fafb;font:16px/1.55 system-ui}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid #d2dbe1;text-align:left;vertical-align:top}a{color:#145e94}small{color:#546775;overflow-wrap:anywhere}details{margin:9px 0}summary{cursor:pointer}.cards{display:flex;gap:22px;flex-wrap:wrap;padding:20px 0}.cards strong{font-size:30px}.cards small{display:block;font-size:13px;font-weight:400}.note{padding:12px 18px;background:#fff7e5;border-left:4px solid #c99225}.controls{display:flex;gap:10px;flex-wrap:wrap}input,select{font:inherit;padding:8px}li{margin:5px 0}footer{margin:30px 0;color:#667}@media(max-width:700px){table{font-size:12px}th,td{padding:7px}.cards{gap:16px}}'
    script = "const rows=[...document.querySelectorAll('#tasks tbody tr')];function filter(){let n=0;for(const r of rows){const ok=r.dataset.search.includes(search.value.toLowerCase())&&(!cohort.value||r.dataset.cohort===cohort.value)&&(!status.value||r.dataset.status===status.value);r.hidden=!ok;n+=ok}document.getElementById('visible').textContent=n+' of '+rows.length+' tasks shown'}const search=document.getElementById('search'),cohort=document.getElementById('cohort'),status=document.getElementById('status');[search,cohort,status].forEach(e=>e.addEventListener('input',filter));filter();"
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>40-task GDPval evidence report</title><style>' + style + '</style><body>' + ''.join(parts) + '<script>' + script + '</script></body></html>'


if __name__ == '__main__':
    result = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'report.html').write_text(render(result))
    columns=['task_id','title','occupation','cohort','started','submitted','assessment_record_present','contract_valid_assessment_present','artifact_count','human_acceptance','human_review_path','human_review_classification','human_review_minutes','human_review_expert_validation','assessment_paths','trace_paths','artifact_paths','known_task_linked_api_cost_usd','unresolved_task_linked_reserve_usd','in_app_cost_usd']
    with (OUT/'task-results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for row in result['tasks']:
            cost=row.get('cost_accounting') or {}
            record={k:row.get(k) for k in columns if k in row}
            record.update(assessment_paths=' | '.join(a.get('path') or a.get('record_path') or '' for a in row['assessment_records']),
                trace_paths=' | '.join(row['traces']),artifact_paths=' | '.join(a['path'] for a in row['artifacts'] if a.get('path')),
                known_task_linked_api_cost_usd=cost.get('known_provider_cost_usd'),unresolved_task_linked_reserve_usd=cost.get('unresolved_reserved_usd'),in_app_cost_usd=None)
            writer.writerow(record)
    print(json.dumps({'counts': result['counts'], 'cohorts': result['cohorts'], 'cost': result['cost']}))
