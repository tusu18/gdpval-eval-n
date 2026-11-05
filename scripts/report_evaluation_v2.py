"""Build a local evidence report and blinded prospective review queue. No API.

Historical labels never become new labels. The review form contains no model or
judge metadata; copied native files retain their original bytes. Existing human
entries and the private randomization key are preserved on rebuild.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default
def lines(path):
    try:return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    except (OSError,ValueError):return []
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.replace(path)
def is_cost(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
def esc(value):return html.escape(str(value if value is not None else 'Unknown'))
def href(path,base):return quote(os.path.relpath(Path(path).resolve(),Path(base).resolve()),safe='/')
def link(path,base,label):return f'<a href="{href(path,base)}">{esc(label)}</a>'
def rooted(root,path):
    candidate=Path(path);candidate=candidate.resolve() if candidate.is_absolute() else (root/candidate).resolve()
    if not candidate.is_relative_to(root.resolve()):raise ValueError('Evidence path outside project root')
    return candidate
def safe_read_text(path):
    try:return Path(path).read_text()
    except OSError:return ''

STYLE='''body{margin:0;background:#f3f5f8;color:#172a3a;font:16px/1.55 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:36px 26px}h1{font-size:32px;line-height:1.15}h2{margin-top:36px;font-size:22px}p{max-width:1000px}a{color:#13528a}table{width:100%;border-collapse:collapse;background:white;font-size:14px}td,th{text-align:left;vertical-align:top;border-bottom:1px solid #dce2e8;padding:10px}th{background:#e7edf3}code{font-size:12px;overflow-wrap:anywhere}.scroll{overflow:auto}.note{padding:16px;background:#e9eff6;border-left:4px solid #426b91}.warning{background:#fff4d9;border-left-color:#b58317}.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{flex:1;min-width:160px;background:white;padding:16px}.stat b{display:block;font-size:24px}details{background:white;margin:12px 0;padding:14px}summary{font-weight:650;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f8fa;padding:14px;font:14px/1.5 system-ui}label{display:block;margin-top:12px;font-weight:600}input,select,textarea{box-sizing:border-box;width:100%;padding:9px;border:1px solid #8b9bab;border-radius:3px;background:white;font:inherit}textarea{min-height:95px}button{background:#173b59;color:white;border:0;padding:12px 18px;cursor:pointer;font:inherit;margin:16px 8px 8px 0}.muted{color:#5b6875}.badge{font-size:12px;border:1px solid #b1becc;padding:2px 6px;white-space:nowrap}li{margin:4px 0}footer{margin-top:36px;font-size:13px;color:#5b6875}'''

def collect_calls(out):
    records=[]
    for path in sorted((out/'calls').glob('*/reservation.json')):
        record=read(path)
        if isinstance(record,dict):records.append({**record,'reservation_path':str(path)})
    return records

def cost_summary(calls):
    scopes=defaultdict(list)
    for call in calls:scopes[call.get('scope','unknown')].append(call)
    def calc(rows):return {'physical_request_records':len(rows),'known_provider_cost_usd':round(sum(x['actual_cost_usd'] for x in rows if is_cost(x.get('actual_cost_usd'))),8),'unknown_charge_records':sum(not is_cost(x.get('actual_cost_usd')) for x in rows),'unresolved_reserved_usd':round(sum(x.get('reserved_usd',0) for x in rows if not is_cost(x.get('actual_cost_usd')) and is_cost(x.get('reserved_usd'))),8)}
    usage=defaultdict(int)
    for call in calls:
        values=call.get('usage') or {}
        for name in ('input_tokens','output_tokens','prompt_tokens','completion_tokens','total_tokens'):
            if type(values.get(name)) is int:usage[name]+=values[name]
    return {**calc(calls),'by_scope':{scope:calc(rows) for scope,rows in sorted(scopes.items())},'request_status_counts':dict(Counter(c.get('status','unknown') for c in calls)),'reported_usage':dict(usage),'interpretation':'Known cost is a subtotal. Outstanding reserves are conservative budget commitments, not confirmed additional charges. Neither amount is a wallet balance.'}

def collect_runs(out,calls,tasks):
    rows=[];by_task={t['task_id']:t for t in tasks}
    for folder in sorted((out/'runs').glob('*')):
        if not folder.is_dir():continue
        task=read(folder/'task.json',{});result=read(folder/'result.json',{})
        parts=folder.name.split('__');tid=result.get('task_id') or task.get('task_id') or parts[0]
        related=[x for x in calls if x.get('label','').startswith(folder.name+':')]
        model=result.get('model') or next((x.get('model') for x in related if x.get('model')),None)
        stage=result.get('stage') or (parts[-1] if len(parts)>2 else 'unknown')
        submission=result.get('submission') or []
        state=read(folder/'workspace/state.json',{})
        if not submission and state.get('submitted'):submission=state['submitted']
        rows.append({'run_id':folder.name,'task_id':tid,'occupation':result.get('occupation') or by_task.get(tid,{}).get('occupation'),'model':model,'stage':stage,'status':result.get('status') or ('in_progress_or_interrupted' if related else 'prepared_no_request'),'physical_requests':len(related),'served_providers':sorted({x['served_provider'] for x in related if isinstance(x.get('served_provider'),str) and x['served_provider']}),'provider_unknown_requests':sum(not x.get('served_provider') for x in related),'cost':cost_summary(related),'submission':submission,'native_files':len(submission),'tool_calls':result.get('tool_calls'),'error':result.get('error'),'folder':str(folder),'result_path':str(folder/'result.json') if (folder/'result.json').exists() else None,'human_acceptance':None})
        rows[-1].update(recovery_of=result.get('recovery_of'),recovery_stage=result.get('recovery_stage'),is_recovery=bool(result.get('recovery_of') or result.get('recovery_stage')=='recovery' or stage=='recovery' or folder.name.endswith('__recovery')))
        rows[-1].update(continuation_of=result.get('continuation_of'),continuation_kind=result.get('continuation_kind'),original_supplemental_run=result.get('original_supplemental_run'),recovery_chain=result.get('recovery_chain',[]),inherited_known_cost_usd=result.get('inherited_known_cost_usd'),inherited_unresolved_reserved_usd=result.get('inherited_unresolved_reserved_usd'),inherited_calls_count=len(result.get('inherited_calls',[])),reported_new_known_cost_usd=result.get('known_cost_usd'),cost_scope='Current run cost includes new physical requests only. Inherited costs/reserves are context already counted in the global physical-call ledger, never additive to that total.')
        errors=[{'tool':e.get('tool'),'error_type':e.get('reply',{}).get('error_type'),'error':e.get('reply',{}).get('error','')[:220]} for e in state.get('events',[]) if isinstance(e.get('reply'),dict) and e['reply'].get('error')]
        native_errors=[e for e in errors if e['error_type'] in ('RuntimeError','TimeoutExpired','OSError') and e['tool'] in ('write_workbook','write_document','write_pdf','write_presentation','view_source','view_page')]
        rows[-1].update(native_tool_errors=native_errors,failure_attribution='native_engine_failures_observed_no_business_error_inferred' if native_errors and not submission else None)
    return rows

def collect_judgments(out):
    """Accept the final grader runner schema; retain future/unknown fields plainly."""
    paths=set()
    for pattern in ('judgments/*.json','judgments/*/result.json','grades/*.json','grades*/*/result.json','grading/runs/*.json'):
        paths.update(out.glob(pattern))
    result=[]
    for path in sorted(paths):
        raw=read(path)
        if not isinstance(raw,dict) or not any(k in raw for k in ('assessment','summary','judge_model','judgment')):continue
        assessment=raw.get('assessment') or raw.get('summary') or {}
        judgment=raw.get('judgment') or read(raw.get('judgment_path',''),{}) or {}
        result.append({'record_path':str(path),'run_id':raw.get('run_id') or raw.get('solver_run_id'),'task_id':raw.get('task_id'),'judge_model':raw.get('judge_model') or raw.get('model'),'status':raw.get('status'),'validation_status':assessment.get('status'),'validation_errors':assessment.get('validation_errors') or assessment.get('errors') or raw.get('validation_errors') or [],'project_rubric_pass':assessment.get('project_rubric_pass'),'consequential_error_candidate':assessment.get('consequential_error_candidate'),'failed_criteria':assessment.get('failed_criteria',[]),'uncertain_criteria':assessment.get('uncertain_criteria',[]),'task_defect':assessment.get('task_defect') or judgment.get('task_defect'),'coverage':assessment.get('coverage'),'batch_count':len(raw.get('batches',[])) or None,'human_acceptance':None})
        defects=assessment.get('task_defect_assessments',[])
        result[-1]['grading_cohort']=path.parent.parent.name
        result[-1]['task_defect_assessments']=defects
        if not result[-1]['task_defect'] and defects:
            result[-1]['task_defect']={'status':' / '.join(str(d.get('status','unknown')) for d in defects if isinstance(d,dict)),'reason':'Per-batch statuses retained without converting them to a human validity label.'}
    return result

def method_citations(root):
    text=safe_read_text(root/'docs/evaluation_v2/grader-protocol.md');result=[]
    for line in text.splitlines():
        m=re.match(r'\| \[([^]]+)\]\((https?://[^)]+)\) \| (.*?) \| (.*?) \|$',line)
        if m:result.append({'title':m[1],'url':m[2],'application':m[3],'limit':m[4]})
    return result

def effective_primary_grades(entries,primary_model,primary_judge,task_ids):
    """One slot per original primary task, with a fixed solver and judge."""
    selected=[e for e in entries if e.get('stage')=='primary' and not e.get('recovery_stage') and e.get('solver_model')==primary_model and e.get('judge_model')==primary_judge and e.get('task_id') in task_ids]
    by_task=defaultdict(list)
    for entry in selected:by_task[entry['task_id']].append(entry)
    statuses={tid:rows[0].get('effective_status','unknown') if len(rows)==1 else 'duplicate_primary_grade_records' for tid,rows in by_task.items()}
    return {'primary_solver':primary_model,'primary_judge':primary_judge,'task_denominator':len(task_ids),'counted_task_slots':len(statuses),'status_counts':dict(Counter(statuses.values())),'duplicate_task_records':{tid:rows for tid,rows in by_task.items() if len(rows)>1},'entries':selected}

def copy_blinded(root,source,target):
    source=rooted(root,source)
    if not source.is_file():return None
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or sha(target)!=sha(source):shutil.copyfile(source,target)
    return {'path':str(target),'sha256':sha(target),'bytes_unchanged':True}

def human_queue(root,out,reviews,tasks,runs,cfg,grader):
    selected=grader.get('human_validation',{}).get('selected_task_ids',[])
    primary=[r for r in runs if (r['stage']=='primary' or r['stage'].startswith('supplemental')) and not r.get('is_recovery')]
    extension_path=root/'config/evaluation_v2_model_extension.json';extension=read(extension_path,{})
    extension_tasks=[x['task_id'] for x in extension.get('tasks',[])]
    models=sorted(set([cfg.get('primary_model')]+extension.get('models',[])+[r['model'] for r in primary])-{None})
    planned_pairs={(tid,cfg.get('primary_model')) for tid in selected}
    planned_pairs.update((tid,model) for tid in extension_tasks for model in extension.get('models',[]))
    planned_pairs.update((r['task_id'],r['model']) for r in primary if r['stage']=='supplemental' and r['status']=='submitted')
    review_tasks=list(dict.fromkeys(selected+extension_tasks+[tid for tid,model in sorted(planned_pairs)]))
    amendment_path=root/'config/evaluation_v2_review_queue_amendment.json'
    if extension and not amendment_path.exists():
        write(amendment_path,{'schema':'evaluation-v2-human-queue-scope-amendment-v1','created_at':datetime.now(timezone.utc).isoformat(),'original_config_path':str(root/'config/evaluation_v2_grader.json'),'original_config_sha256':sha(root/'config/evaluation_v2_grader.json'),'extension_config_path':str(extension_path),'extension_config_sha256':sha(extension_path),'reason':'The additional-model experiment runs only four selected original tasks, not the original complete fifteen-task study. Present only those planned cells and submitted supplemental outputs; do not create nine mostly unplanned task slots for every additional model.','primary_policy':'Keep the nine frozen primary task slots and randomized opaque identities unchanged, including missing submissions.','additional_policy':'Separate additional-model review on the four-task extension. This post-primary scope amendment is not original preregistration and is not pooled into primary acceptance. Missing planned deliverables stay pending; no outcome-based replacement.','human_labels_created':0,'submission_requires_all_reviews_complete':False})
    by_task={t['task_id']:t for t in tasks}
    keypath=out/'review-private-key.json';key=read(keypath,{'schema':'v2-private-review-map','salt':secrets.token_hex(24),'case_map':{}})
    prior=read(reviews/'human-reviews.json',{'cases':[]});prior_cases={c['case_id']:c for c in prior.get('cases',[]) if isinstance(c,dict) and 'case_id' in c}
    cases=[];mapping=key['case_map']
    for tid in review_tasks:
        if tid not in by_task:continue
        task=by_task[tid]
        for model in models:
            if (tid,model) not in planned_pairs:continue
            pair=tid+'|'+model
            if pair not in mapping:mapping[pair]={'case_id':'R-'+hashlib.sha256((key['salt']+'|'+pair).encode()).hexdigest()[:10]}
            cid=mapping[pair]['case_id'];folder=reviews/'cases'/cid
            candidates=[r for r in primary if r['task_id']==tid and r['model']==model and r['stage'] in ('primary','supplemental')]
            run=candidates[0] if len(candidates)==1 else None
            mapping[pair].update(task_id=tid,model=model,run_id=run['run_id'] if run else None)
            sources=[];artifacts=[];renders=[]
            for i,ref in enumerate(task.get('references',[]),1):
                path=ref.get('path') or ref.get('local_path')
                if not path:continue
                copied=copy_blinded(root,path,folder/f'source-{i:02d}{Path(path).suffix.lower()}')
                if copied:sources.append({**copied,'name':ref.get('name') or Path(path).name,'provenance':ref.get('provenance') or ('retrieved supporting source' if ref.get('retrieved_at_utc') else 'provided source')})
            for i,artifact in enumerate((run or {}).get('submission',[]),1):
                path=artifact.get('path')
                if not path:continue
                copied=copy_blinded(root,path,folder/f'deliverable-{i:02d}{Path(path).suffix.lower()}')
                if copied:artifacts.append({**copied,'name':f'Deliverable {i:02d}','kind':artifact.get('kind') or Path(path).suffix[1:]})
                for j,view in enumerate(artifact.get('previews',[]),1):
                    copied=copy_blinded(root,view['path'],folder/f'deliverable-{i:02d}-view-{j:03d}.png')
                    if copied:renders.append({**copied,'name':f'Deliverable {i:02d}, view {j:03d}'})
            old=prior_cases.get(cid,{})
            answers=old.get('review',{})
            fields=('task_or_source_defect','accept_without_substantive_correction','consequential_error','exact_evidence','assumptions','counterevidence','native_inspections_performed','minimum_correction','minutes','reviewer','reviewer_experience','prior_exposure','completed_at')
            review={f:answers.get(f) for f in fields}
            cases.append({'case_id':cid,'task_id':tid,'review_cohort':'primary_study' if model==cfg.get('primary_model') else 'additional_model','occupation':task.get('occupation'),'prompt':task['prompt'],'status':'ready_for_review' if artifacts else 'awaiting_deliverable','sources':sources,'artifacts':artifacts,'renders':renders,'review':review})
    cases.sort(key=lambda c:c['case_id'])
    payload={'schema':'evaluation-v2-blinded-human-review-v1','selection':'Nine prespecified primary task slots plus a separate four-task additional-model extension. No replacement of missing outputs. Additional work remains pending validation rather than a submission prerequisite.','blinding':'Model, provider, judge verdict and author labels omitted from this form. Content and native-file metadata may still reveal identity. Native bytes are unchanged.','instructions':'Review complete sources and deliverables before viewing judge results. Save your own labels; machine checks never populate human answers. Missing deliverables stay pending rather than receiving invented acceptance labels.','allowed_endpoint_values':['yes','no','uncertain'],'cases':cases}
    write(keypath,key);write(reviews/'human-reviews.json',payload)
    return payload

def review_html(payload,reviews):
    blocks=[]
    for c in payload['cases']:
        cid=c['case_id'];sources=''.join(f'<li>{link(s["path"],reviews,s["name"])}</li>' for s in c['sources']) or '<li>No attached sources.</li>'
        artifacts=''.join(f'<li>{link(a["path"],reviews,a["name"]+" ("+a["kind"]+")")}</li>' for a in c['artifacts']) or '<li>Deliverable not available yet. Leave acceptance pending.</li>'
        renders=''.join(f'<li>{link(a["path"],reviews,a["name"])}</li>' for a in c['renders'])
        controls=''
        for field,label in [('task_or_source_defect','Is there a task or source defect?'),('accept_without_substantive_correction','Would you accept the entire deliverable without substantive correction?'),('consequential_error','Is there a source-supported consequential error?')]:
            options='<option value="">Not reviewed</option>'+''.join(f'<option value="{v}"'+(' selected' if c['review'].get(field)==v else '')+f'>{v.title()}</option>' for v in ('yes','no','uncertain'))
            controls+=f'<label>{label}<select data-case="{cid}" data-field="{field}">{options}</select></label>'
        for field,label in [('exact_evidence','Exact source and output evidence, with file/page/cell'),('assumptions','Assumptions needed for your conclusion'),('counterevidence','Strongest evidence against your conclusion'),('native_inspections_performed','Pages, cells, formulas and native behavior you inspected'),('minimum_correction','Minimum correction before use')]:
            controls+=f'<label>{label}<textarea data-case="{cid}" data-field="{field}">{esc(c["review"].get(field) or "")}</textarea></label>'
        for field,label in [('minutes','Minutes spent'),('reviewer','Reviewer name or identifier'),('reviewer_experience','Relevant occupational experience'),('prior_exposure','Prior exposure to this task or output')]:
            controls+=f'<label>{label}<input data-case="{cid}" data-field="{field}" value="{esc(c["review"].get(field) or "")}"></label>'
        if c.get('review_prompt'):controls='<p class="note">Review question: '+esc(c['review_prompt'])+'</p>'+controls
        blocks.append(f'<details><summary>{esc(cid)} · {esc(c["occupation"])} · {esc(c["status"].replace("_"," "))}</summary><h3>Original task</h3><pre>{esc(c["prompt"])}</pre><h3>Sources</h3><ul>{sources}</ul><h3>Deliverables</h3><ul>{artifacts}</ul><details><summary>Rendered views</summary><ul>{renders or "<li>No rendered views available.</li>"}</ul></details>{controls}<button type="button" onclick="completeCase(\'{cid}\')">Mark this review complete</button><span id="status-{cid}" class="muted"></span></details>')
    data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    script='''const payload=JSON.parse(document.getElementById('review-data').textContent);const find=id=>payload.cases.find(c=>c.case_id===id);document.querySelectorAll('[data-case]').forEach(el=>el.addEventListener('input',()=>{find(el.dataset.case).review[el.dataset.field]=el.value||null;}));function completeCase(id){const c=find(id),r=c.review;if(c.status!=='ready_for_review'){alert('This deliverable is not available yet. Leave its labels pending.');return;}if(!['task_or_source_defect','accept_without_substantive_correction','consequential_error'].every(k=>['yes','no','uncertain'].includes(r[k]))||!r.exact_evidence||!r.reviewer){alert('Please answer the three questions and record evidence and reviewer identity.');return;}r.completed_at=new Date().toISOString();document.getElementById('status-'+id).textContent='Marked complete. Download your answers to save them.';}function downloadReviews(){const b=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='human-reviews-completed.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}'''
    return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blinded human review</title><style>{STYLE}</style></head><body><main><h1>Blinded review of professional deliverables</h1><p class="note">{esc(payload["instructions"])}</p><p>{esc(payload["selection"])} {esc(payload["blinding"])}</p><p>Review order uses persistent random opaque case IDs. This page shows no automated verdicts. Your answers stay in this browser until you download them; reopening the page does not restore unsaved answers.</p><button onclick="downloadReviews()">Download review answers</button>{"".join(blocks)}<button onclick="downloadReviews()">Download review answers</button><script id="review-data" type="application/json">{data}</script><script>{script}</script></main></body></html>'

def build(root=ROOT):
    root=Path(root).resolve();out=root/'output/evaluation_v2';reviews=root/'reviews/evaluation_v2';out.mkdir(parents=True,exist_ok=True);reviews.mkdir(parents=True,exist_ok=True)
    cfg=read(root/'config/evaluation_v2_run.json',{});grader=read(root/'config/evaluation_v2_grader.json',{})
    taskpath=root/'data/evaluation_v2/effective-inputs.jsonl'
    if not taskpath.exists():taskpath=root/'data/evaluation_v2/tasks.jsonl'
    tasks=lines(taskpath);calls=collect_calls(out);runs=collect_runs(out,calls,tasks);judges=collect_judgments(out)
    primary=[r for r in runs if r['stage']=='primary' and not r.get('is_recovery')];development=[r for r in runs if r['stage'] not in ('primary','adapter_repair') and not r['stage'].startswith('supplemental') and not r.get('is_recovery')]
    supplemental=[r for r in runs if r['stage'].startswith('supplemental') and not r.get('is_recovery')]
    recovery=[r for r in runs if r.get('is_recovery')]
    adapter_repair=[r for r in runs if r['stage']=='adapter_repair']
    actual_models=sorted({r['model'] for r in primary if r['model']})
    model_roster=sorted(set([cfg.get('primary_model')]+cfg.get('other_requested_models',[])+actual_models)-{None})
    audit=read(root/'docs/evaluation_v2/task-audit.json',{});audit_by_id={t['source_task_id']:t for t in audit.get('tasks',[])}
    roster=[]
    for task in tasks:
        tid=task['task_id'];matching=[r for r in primary if r['task_id']==tid];a=audit_by_id.get(tid,{})
        roster.append({'task_id':tid,'name':task.get('name') or a.get('name') or tid[:8],'occupation':task.get('occupation'),'source_lineage':'Original GDPval task; original prompt and native references preserved','primary_run_count':len(matching),'attempted':any(r['physical_requests'] for r in matching),'submitted':any(r['status']=='submitted' for r in matching),'statuses':[r['status'] for r in matching] or ['unrun'],'run_ids':[r['run_id'] for r in matching],'dependency_gaps':task.get('contract',{}).get('dependency_gaps',[]),'source_quality_flags':task.get('contract',{}).get('source_quality_flags',[]),'external_dependency':a.get('external_dependency'),'development_exposure':a.get('development_exposure'),'human_acceptance':None})
    queue=human_queue(root,out,reviews,tasks,runs,cfg,grader)
    completed=[c for c in queue['cases'] if c['status']=='ready_for_review' and c['review'].get('completed_at') and all(c['review'].get(k) in ('yes','no','uncertain') for k in ('task_or_source_defect','accept_without_substantive_correction','consequential_error'))]
    reviewed_counts=Counter(c['review']['accept_without_substantive_correction'] for c in completed)
    report={'schema':'evaluation-v2-evidence-report-v1','generated_at':datetime.now(timezone.utc).isoformat(),'build_script_sha256':sha(Path(__file__)),'scope':'15 original tasks across three occupations; all selected tasks remain in the accounting. No model ranking.','task_input_path':str(taskpath),'task_input_sha256':sha(taskpath) if taskpath.exists() else None,'planned_tasks':len(tasks),'occupations':dict(Counter(t.get('occupation') for t in tasks)),'primary_summary':{'attempted_tasks':sum(r['attempted'] for r in roster),'submitted_tasks':sum(r['submitted'] for r in roster),'unrun_tasks':sum(not r['attempted'] for r in roster),'run_records':len(primary),'status_counts':dict(Counter(r['status'] for r in primary))},'models':[{'model':m,'primary_status':'attempted' if any(r['model']==m and r['physical_requests'] for r in primary) else 'unrun','primary_run_count':sum(r['model']==m for r in primary)} for m in model_roster],'task_roster':roster,'primary_runs':primary,'development_runs':development,'development_separation':'Smoke/development runs and historical adapted/constructed tasks are excluded from primary denominators. Five historical human reviews are development evidence only, never new validation labels.','judgments':judges,'judge_summary':dict(Counter(j.get('validation_status') or j.get('status') or 'unknown' for j in judges)),'cost':cost_summary(calls),'authorized_budget_usd':cfg.get('authorized_available_budget_usd'),'human_validation':{'prespecified_tasks':len(grader.get('human_validation',{}).get('selected_task_ids',[])),'planned_case_slots':len(queue['cases']),'ready_case_slots':sum(c['status']=='ready_for_review' for c in queue['cases']),'completed_reviews':len(completed),'acceptance_counts':dict(reviewed_counts),'expertise_verified':False,'acceptance_rate':None,'judge_accuracy':None,'cost_per_accepted_deliverable':None,'reason':'Case labels are separate human evidence. Rates and judge accuracy require an explicit reviewed-sample analysis; absent labels are never inferred.'},'agentic_judge_status':grader.get('agentic_pilot',{}).get('status','not_run'),'method_sources':method_citations(root),'limitations':['Single selected three-occupation slice; no population-wide model ranking.','New automated flags are candidates, not human-confirmed consequential errors.','Quote validity is not semantic accuracy. Uncertain and invalid judgments remain separate.','Provider identity is unknown wherever the service omitted it. Model IDs are requested routing IDs.','Source access and contradictory task requirements are separated from business errors.','Human acceptance, judge accuracy and training benefit are not established by native submission.']}
    report['supplemental_runs']=supplemental
    report['primary_judge_model']=cfg.get('primary_judge') or grader.get('judges',{}).get('primary_model')
    report['primary_solver_model']=cfg.get('primary_model')
    extension=read(root/'config/evaluation_v2_model_extension.json',{})
    planned_cells=[]
    for task in extension.get('tasks',[]):
        for model in extension.get('models',[]):
            observed=[run for run in supplemental if run['task_id']==task['task_id'] and run['model']==model and run['stage']=='supplemental']
            observed_ids={run['run_id'] for run in observed}
            continuations=[run for run in recovery if run['task_id']==task['task_id'] and run['model']==model and (run.get('original_supplemental_run') in observed_ids or run.get('continuation_of') in observed_ids or run.get('recovery_of') in observed_ids)]
            planned_cells.append({'task_id':task['task_id'],'task_name':task.get('name'),'occupation':task.get('occupation'),'planned_required_formats':task.get('formats',[]),'model':model,'stage':'supplemental','status':observed[0]['status'] if len(observed)==1 else ('multiple_records_review_required' if observed else 'unrun'),'attempted':any(run['physical_requests'] for run in observed),'native_produced':any(run['submission'] for run in observed),'run_ids':[run['run_id'] for run in observed],'submission':[artifact for run in observed for artifact in run['submission']],'separate_continuations':continuations,'continuation_native_available':any(run['submission'] for run in continuations),'original_status_preserved':True})
    report['supplemental_planned_cells']=planned_cells
    attempted_cells=[c for c in planned_cells if c['attempted']]
    delivered_artifacts=[a for c in planned_cells for a in c['submission']]+[a for c in planned_cells for run in c['separate_continuations'] for a in run['submission']]
    report['supplemental_plan_summary']={'planned_cells':len(planned_cells),'attempted_cells':len(attempted_cells),'unattempted_cells':sum(not c['attempted'] for c in planned_cells),'native_produced_cells':sum(c['native_produced'] for c in planned_cells),'native_available_cells_including_separate_continuations':sum(c['native_produced'] or c['continuation_native_available'] for c in planned_cells),'status_counts':dict(Counter(c['status'] for c in planned_cells)),'planned_tasks':len(extension.get('tasks',[])),'planned_occupations':sorted({c['occupation'] for c in planned_cells if c['occupation']}),'planned_required_formats':sorted({f for c in planned_cells for f in c['planned_required_formats']}),'actual_attempted_task_ids':sorted({c['task_id'] for c in attempted_cells}),'actual_attempted_task_names':sorted({c['task_name'] for c in attempted_cells if c['task_name']}),'actual_attempted_occupations':sorted({c['occupation'] for c in attempted_cells if c['occupation']}),'actual_attempted_required_formats':sorted({f for c in attempted_cells for f in c['planned_required_formats']}),'actual_submitted_native_formats':sorted({a.get('kind') or Path(a['path']).suffix.lower().lstrip('.') for a in delivered_artifacts}),'unattempted_task_ids':sorted({c['task_id'] for c in planned_cells}-{c['task_id'] for c in attempted_cells}),'scope_is_observed_coverage_not_generalizable_model_ranking':True}
    report['supplemental_scope']='Additional original-task runs remain separate from the complete primary roster and from smoke/development work. Unequal task coverage cannot support a model ranking.'
    for model in report['models']:model['supplemental_run_count']=sum(r['model']==model['model'] for r in supplemental)
    report['recovery_runs']=recovery
    report['adapter_repair_runs']=adapter_repair
    report['adapter_repair_scope']='Post-hoc native-engine compatibility repair, separate from primary and connection-recovery results. The original spreadsheet source bytes and original failed run remain unchanged. A derived import copy normalizes only OPC namespace serialization; business content and XML semantics are verified unchanged.'
    report['all_cohort_native_coverage']={'distinct_original_tasks_with_any_submitted_native_output':len({r['task_id'] for r in primary+recovery+adapter_repair+supplemental if r['status']=='submitted'}),'denominator_original_tasks':len(tasks),'is_primary_completion_rate':False,'is_human_acceptance':False}
    report['recovery_scope']='Explicit transport recoveries and budget continuations remain separate. Each original primary or supplemental stop and its costs stay in its original cohort. Continuation files do not replace the first-pass outcome or silently enter the prespecified primary human-review sample. New costs and inherited context are displayed separately; the global ledger counts each physical request once.'
    amendment_path=root/'config/evaluation_v2_budget_amendment.json';amendment=read(amendment_path,{})
    report['budget_correction']={'original_operative_ceiling_usd':cfg.get('authorized_available_budget_usd'),'original_key_allowance_reported_usd':14.668875725 if cfg.get('authorized_available_budget_usd')==14.66 else None,'correction':'The original remaining key spending allowance was mistaken for account-wallet funds. The frozen original config preserves that incorrect note for provenance; it is not a current balance statement.','wallet_snapshot':None,'amended_total_authorization_usd':amendment.get('authorized_total_usd'),'amendment_is_cash_balance':False,'amendment_path':str(amendment_path) if amendment else None,'amendment_sha256':sha(amendment_path) if amendment else None,'original_config_path':str(root/'config/evaluation_v2_run.json'),'amendment_reason':amendment.get('reason'),'current_wallet_balance_usd':None}
    if is_cost(amendment.get('authorized_total_usd')):report['authorized_budget_usd']=amendment['authorized_total_usd']
    correction_path=out/'budget-correction.json';machine_correction=read(correction_path)
    if machine_correction:
        report['budget_correction'].update(source_path=str(correction_path),source_sha256=sha(correction_path),machine_record=machine_correction,wallet_snapshot=None,current_wallet_balance_usd=None)
    calibration=read(out/'calibration_analysis.json')
    report['calibration_diagnostic']=calibration_summary(calibration,out/'calibration_analysis.json') if calibration else None
    by_run={run['run_id']:run for run in runs}
    for judgment in judges:
        run=by_run.get(judgment.get('run_id'),{})
        judgment['solver_cohort']='recovery' if run.get('is_recovery') else run.get('stage','unknown')
        judgment['solver_model']=run.get('model')
        solver_family=(run.get('model') or '').split('/')[0]
        judge_family=(judgment.get('judge_model') or '').split('/')[0]
        judgment['model_family_relationship']='same_requested_family' if solver_family and solver_family==judge_family else ('cross_requested_family' if solver_family and judge_family else 'unknown')
    submitted_primary_solver=[run for run in primary+recovery+adapter_repair if run['model']==report['primary_solver_model'] and run['status']=='submitted']
    native_grade_rows=[]
    for run in submitted_primary_solver:
        matching=[j for j in judges if j.get('run_id')==run['run_id'] and j.get('judge_model')==report['primary_judge_model']]
        native_grade_rows.append({'task_id':run['task_id'],'run_id':run['run_id'],'solver_cohort':'recovery' if run.get('is_recovery') else run['stage'],'grade_recorded':bool(matching),'executed_assessment_recorded':any(j.get('status') in ('graded','invalid_judgment','infrastructure_failure') for j in matching),'grade_statuses':sorted({j.get('status') or 'unknown' for j in matching}),'human_acceptance':None})
    report['primary_solver_native_grade_coverage']={'solver_model':report['primary_solver_model'],'judge_model':report['primary_judge_model'],'distinct_original_tasks_with_native_output':len({row['task_id'] for row in native_grade_rows}),'distinct_original_tasks_with_executed_assessment_record':len({row['task_id'] for row in native_grade_rows if row['executed_assessment_recorded']}),'rows':native_grade_rows,'includes_separate_recovery_and_repair_cohorts':True,'is_primary_completion_rate':False,'human_acceptance':None}
    report['judgment_cohorts']={cohort:dict(Counter(j.get('validation_status') or j.get('status') or 'unknown' for j in judges if j['grading_cohort']+' / '+j['solver_cohort']==cohort)) for cohort in sorted({j['grading_cohort']+' / '+j['solver_cohort'] for j in judges})}
    report['assistant_review_candidates']=read(root/'docs/evaluation_v2/new-output-review-candidates.json')
    report['assistant_technical_review_candidates']=read(root/'docs/evaluation_v2/new-output-review-candidates-technical.json')
    report['grade_resolution_index']=read(out/'grade-resolution-index.json')
    report['cross_family_judging_plan']=read(out/'cross_family_judging/latest-plan.json')
    report['account_reconciliation_snapshot']=read(out/'account-reconciliation-snapshot.json')
    report['administrative_solver_allocation_release']=read(root/'config/evaluation_v2_solver_allocation_release.json')
    report['future_sonnet_image_reservation_amendment']=read(root/'config/evaluation_v2_cross_family_image_reservation_amendment.json')
    report['funded_worker_freeze']=read(out/'extension/funded-workers/freeze.json')
    if report['grade_resolution_index']:
        effective=report['grade_resolution_index'].get('entries',[])
        report['effective_primary_grading']=effective_primary_grades(effective,report['primary_solver_model'],report['primary_judge_model'],{t['task_id'] for t in tasks})
        report['effective_primary_grade_status_counts']=report['effective_primary_grading']['status_counts']
        secondary=[e for e in effective if e.get('judge_model')!=report['primary_judge_model']]
        report['effective_secondary_grade_status_counts']={model:dict(Counter(e.get('effective_status','unknown') for e in secondary if e.get('judge_model')==model)) for model in sorted({e.get('judge_model') for e in secondary if e.get('judge_model')})}
    report['judge_checks']=read(out/'judge_checks/analysis.json')
    if report['judge_checks']:
        report['judge_checks']['source_path']=str(out/'judge_checks/analysis.json')
        report['agentic_judge_status']='Exploratory results available; see the bounded judge-check section for executed comparisons, validity exclusions and pending arms.'
    report['invalid_contract_diagnostic']=read(out/'invalid_judgment_audit/diagnostics.json')
    report['gmp_agentic_contrast']=gmp_contrast(root,out,report['invalid_contract_diagnostic'])
    report['unexecuted_construct_review_available']=(out/'construct_direction_review/index.html').is_file()
    primary_review_cases=[c for c in queue['cases'] if c['review_cohort']=='primary_study']
    additional_review_cases=[c for c in queue['cases'] if c['review_cohort']=='additional_model']
    report['human_validation'].update(primary_planned_case_slots=len(primary_review_cases),primary_ready_case_slots=sum(c['status']=='ready_for_review' for c in primary_review_cases),additional_model_planned_case_slots=len(additional_review_cases),additional_model_ready_case_slots=sum(c['status']=='ready_for_review' for c in additional_review_cases),denominator_policy='The primary nine task slots are separate from all additional model slots. Missing primary files remain missing; recoveries do not replace them. Additional review work is reported as pending evidence, not a prerequisite for submitting the present study.')
    primary_queue={**queue,'cases':primary_review_cases,'selection':'Nine prespecified primary-study task slots, three per occupation. Missing outputs stay in their original slots. Review these in the displayed randomized order before consulting audit findings.'}
    primary_html=review_html(primary_queue,reviews)
    if additional_review_cases:
        supplemental_queue={**queue,'cases':additional_review_cases,'selection':'Additional-model review slots on the four-task extension. This separately amended sample is outside the primary study denominator; unavailable planned cases remain pending. This is additional validation work, not a requirement to submit the current evidence.'}
        (reviews/'supplemental.html').write_text(review_html(supplemental_queue,reviews))
        primary_html=primary_html.replace('</main>','<p><a href="supplemental.html">Separate additional-model review slots</a>. These do not enter the primary denominator.</p></main>')
    write(reviews/'primary-human-reviews.json',primary_queue)
    write(out/'report.json',report);(reviews/'index.html').write_text(primary_html)
    rendered=report_html(report,out,reviews,root)
    if supplemental:
        extra='<h2>Additional original-task runs</h2><p>'+esc(report['supplemental_scope'])+'</p><table><thead><tr><th>Task</th><th>Requested model</th><th>Status</th><th>Native files</th></tr></thead><tbody>'
        for run in supplemental:
            native='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in run['submission'] if a.get('path'))
            extra+=f'<tr><td><code>{esc(run["task_id"])}</code></td><td>{esc(run["model"])}</td><td>{esc(run["status"])}<br>{esc(run["stage"])}</td><td>{native or "None"}</td></tr>'
        extra+='</tbody></table>'
        rendered=rendered.replace('<h2>Development work kept separate</h2>',extra+'<h2>Development work kept separate</h2>')
    if recovery:
        extra='<h2>Transport recovery and budget continuations</h2><p>'+esc(report['recovery_scope'])+'</p><table><thead><tr><th>Task</th><th>Model</th><th>Status and parent</th><th>New cost / inherited context</th><th>Native files</th></tr></thead><tbody>'
        for run in recovery:
            native='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in run['submission'] if a.get('path'))
            inherited=run.get('inherited_known_cost_usd');inherited_unknown=run.get('inherited_unresolved_reserved_usd')
            cost_text=f'New known ${run["cost"]["known_provider_cost_usd"]:.5f}; new unresolved reserve ${run["cost"]["unresolved_reserved_usd"]:.5f}. Inherited known: '+(f'${inherited:.5f}' if is_cost(inherited) else 'not recorded')+'; inherited unresolved reserve: '+(f'${inherited_unknown:.5f}' if is_cost(inherited_unknown) else 'not recorded')+'. Inherited amounts are not added again.'
            extra+=f'<tr><td><code>{esc(run["task_id"])}</code></td><td>{esc(run["model"])}</td><td>{esc(run["status"])}<br>{esc(run.get("continuation_kind") or "transport recovery")}<br>Parent: <code>{esc(run.get("continuation_of") or run.get("recovery_of"))}</code></td><td>{esc(cost_text)}</td><td>{native or "None"}</td></tr>'
        extra+='</tbody></table>'
        rendered=rendered.replace('<h2>Development work kept separate</h2>',extra+'<h2>Development work kept separate</h2>')
    if adapter_repair:
        extra='<h2>Native-engine compatibility repair</h2><p>'+esc(report['adapter_repair_scope'])+'</p><p>'+link(root/'config/evaluation_v2_shipping_compatibility.json',out,'Repair scope and invariance rules')+' · '+link(out/'compatibility/offline-shipping-test/verification.json',out,'Offline source and writer verification')+'</p><table><thead><tr><th>Task</th><th>Model</th><th>Status</th><th>Native files</th></tr></thead><tbody>'
        for run in adapter_repair:
            native='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in run['submission'] if a.get('path'))
            extra+=f'<tr><td><code>{esc(run["task_id"])}</code></td><td>{esc(run["model"])}</td><td>{esc(run["status"])}</td><td>{native or "None"}</td></tr>'
        extra+='</tbody></table>'
        rendered=rendered.replace('<h2>Development work kept separate</h2>',extra+'<h2>Development work kept separate</h2>')
    if amendment:
        correction='<div class="note warning"><b>Budget correction.</b> The original $'+f'{float(cfg.get("authorized_available_budget_usd") or 0):.2f}'+' was the operating ceiling derived from remaining key allowance, not account-wallet funds. Dated wallet observations are historical snapshots and are not current-balance claims. The user subsequently authorized a $'+f'{float(amendment["authorized_total_usd"]):.2f}'+' total campaign spending cap while adding credit. Authorization, key allowance, wallet balance, incurred charges and outstanding reserves are different quantities. '+link(root/'config/evaluation_v2_run.json',out,'Original frozen config (incorrect balance note retained)')+' · '+link(amendment_path,out,'Budget amendment')+' · '+(link(correction_path,out,'Recorded correction and dated browser observations') if machine_correction else link(out/'report.json',out,'Correction provenance in report JSON'))+'.</div>'
        rendered=rendered.replace('<h2>Cost and unknown charges</h2>','<h2>Cost and unknown charges</h2>'+correction)
    if report['calibration_diagnostic']:
        rendered=rendered.replace('<h2>Research methods applied</h2>',calibration_html(report['calibration_diagnostic'],out)+'<h2>Research methods applied</h2>')
    extra=additional_evidence_html(report,out,root)
    rendered=rendered.replace('<h2>Research methods applied</h2>',extra+'<h2>Research methods applied</h2>')
    (out/'report.html').write_text(rendered)
    return report

def additional_evidence_html(report,out,root):
    coverage=report.get('all_cohort_native_coverage',{})
    text='<p class="note">Across explicitly separate primary, connection-recovery, adapter-repair and supplemental runs, '+str(coverage.get('distinct_original_tasks_with_any_submitted_native_output',0))+' of '+str(coverage.get('denominator_original_tasks',0))+' original tasks have at least one native submission. This is cross-cohort file availability, not the primary completion rate or human acceptance.</p>'
    native_grades=report.get('primary_solver_native_grade_coverage',{})
    text+='<p>For '+esc(native_grades.get('solver_model'))+' across primary, recovery and repaired-adapter cohorts, '+str(native_grades.get('distinct_original_tasks_with_executed_assessment_record',0))+' distinct original tasks have native outputs with an executed assessment record from '+esc(native_grades.get('judge_model'))+'. This coverage statement includes invalid or failed assessments and does not imply accepted work.</p>'
    if report.get('supplemental_planned_cells'):
        scope=report['supplemental_plan_summary']
        actual_formats=', '.join(f.upper() for f in scope['actual_attempted_required_formats']) or 'none'
        delivered_formats=', '.join(f.upper() for f in scope['actual_submitted_native_formats']) or 'none'
        text+='<h2>Complete additional-model plan</h2><p class="note warning"><b>Observed additional-model scope:</b> '+str(scope['attempted_cells'])+' of '+str(scope['planned_cells'])+' first-pass cells attempted; '+str(scope['unattempted_cells'])+' have no physical attempt. Actual attempted tasks: '+esc('; '.join(scope['actual_attempted_task_names']) or 'none')+'. This covers '+str(len(scope['actual_attempted_occupations']))+' occupations and '+esc(actual_formats)+' requirements. Submitted native formats, including separately reported continuations: '+esc(delivered_formats)+'. '+str(scope['native_produced_cells'])+' original cells submitted files; '+str(scope['native_available_cells_including_separate_continuations'])+' cells have files when separate continuations are also considered. Planned project-management, presentation and PDF work is not completed additional-model coverage merely because it appears in the plan.</p><p>The plan contains '+str(scope['planned_tasks'])+' tasks, '+str(len(scope['planned_occupations']))+' occupations and '+esc(', '.join(f.upper() for f in scope['planned_required_formats']))+' formats. That broader plan is separate from the actual coverage above and from the completed core Sol study and selected agentic inspection pilot.</p><p>All planned first-pass cells remain visible. Unrun, prepared, active/interrupted, failed and submitted states are separate. Continuation artifacts appear beside their original stop and do not replace it. Producing a native file does not mean a human accepted it. Optional repeats, if attempted, remain separately labeled.</p><table><thead><tr><th>Original task</th><th>Requested model</th><th>Original execution state</th><th>Original native files</th><th>Separate continuation</th></tr></thead><tbody>'
        for cell in report['supplemental_planned_cells']:
            native='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in cell['submission'] if a.get('path'))
            followups=[]
            for followup in cell.get('separate_continuations',[]):
                files='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in followup['submission'] if a.get('path'))
                followups.append(esc(followup.get('continuation_kind') or 'recovery')+': '+esc(followup['status'])+'<br>'+(files or 'No native files'))
            text+=f'<tr><td>{esc(cell["task_name"])}<br><code>{esc(cell["task_id"])}</code></td><td>{esc(cell["model"])}</td><td>{esc(cell["status"])}</td><td>{native or "None"}</td><td>{"<br>".join(followups) or "None"}</td></tr>'
        text+='</tbody></table><p>'+link(root/'config/evaluation_v2_model_extension.json',out,'Four-task selection and model-extension plan')+'</p>'
    audit=report.get('assistant_review_candidates')
    if audit:
        text+='<h2>Assistant review candidates</h2><p class="note">These are assistant assessments, not human confirmation. '+esc(audit.get('overall_assessment'))+'</p><table><thead><tr><th>Task</th><th>Classification</th><th>Review question</th></tr></thead><tbody>'
        for case in audit.get('cases',[]):text+=f'<tr><td><code>{esc(case["task_id"])}</code></td><td>{esc(case["classification"])}</td><td>{esc(case["human_review_question"])}</td></tr>'
        text+='</tbody></table><p>'+esc(audit.get('prior_exposure_disclosure'))+' '+link(root/'docs/evaluation_v2/new-output-review-candidates.json',out,'Exact source/output quotes, assumptions and counterevidence')+'</p>'
    technical=report.get('assistant_technical_review_candidates')
    if technical:
        checked=technical.get('summary',{})
        text+='<h2>Assistant technical inspection</h2><p>'+esc(technical.get('independence_limits'))+'</p><p>'+str(checked.get('arithmetic_cells_checked',0))+' arithmetic cells checked; '+str(checked.get('arithmetic_mismatches',0))+' mismatches found in those checks. These cells are not independent tasks. '+esc(checked.get('caveat'))+'</p><table><thead><tr><th>Task and cohort</th><th>Inspection finding</th></tr></thead><tbody>'
        for case in technical.get('cases',[]):text+=f'<tr><td><code>{esc(case["task_id"])}</code><br>{esc(case.get("recovery_stage") or case.get("stage"))}</td><td>{esc(case.get("technical_conclusion"))}</td></tr>'
        text+='</tbody></table><p>The GMP PDF has a visible form-layout problem; that is separate from a business-rule violation. '+link(root/'docs/evaluation_v2/new-output-review-candidates-technical.json',out,'Native files, calculations, exact evidence and review questions')+'</p>'
    extras=[j for j in report['judgments'] if j.get('grading_cohort')!='grades' or j.get('solver_cohort')!='primary' or j.get('judge_model')!=report['primary_judge_model'] or j.get('solver_model')!=report['primary_solver_model']]
    if extras:
        text+='<h2>Separate grading cohorts and amendments</h2><p>Original frozen judgments remain unchanged. Budget-only continuations use the unchanged rubric; recovery, repaired-adapter and supplemental outputs appear separately. A second assessment is not a replacement for an invalid original judgment. Same-family judging and cross-family judging are labeled by requested model families and are not pooled into a ranking.</p><table><thead><tr><th>Cohort</th><th>Task, solver and judge</th><th>Status</th><th>Rubric / consequential candidate</th><th>Validation errors</th></tr></thead><tbody>'
        for j in extras:text+=f'<tr><td>{esc(j["grading_cohort"])} / {esc(j["solver_cohort"])}</td><td><code>{esc(j["task_id"])}</code><br>Solver: {esc(j["solver_model"])}<br>Judge: {esc(j["judge_model"])}<br>{esc(j["model_family_relationship"])}</td><td>{esc(j["status"])}<br>{esc(j["validation_status"])}</td><td>{esc(j["project_rubric_pass"])} / {esc(j["consequential_error_candidate"])}</td><td>{esc("; ".join(j["validation_errors"]))}<br>{link(j["record_path"],out,"Full separate record")}</td></tr>'
        text+='</tbody></table>'
    if report.get('grade_resolution_index'):
        text+='<p>Effective primary grading status for solver '+esc(report['primary_solver_model'])+' and judge '+esc(report['primary_judge_model'])+' only, after resolving eligible budget stops: '+esc(json.dumps(report.get('effective_primary_grade_status_counts',{}),sort_keys=True))+'. This count has at most one slot per original primary task. Separate secondary-judge status counts: '+esc(json.dumps(report.get('effective_secondary_grade_status_counts',{}),sort_keys=True))+'. Secondary judgments do not expand the 15-task primary denominator. '+link(out/'grade-resolution-index.json',out,'Original and effective grading records')+'</p>'
    if report.get('cross_family_judging_plan'):
        text+='<h2>Matched secondary judge cohort</h2><p>The secondary Sonnet judge is planned for four Gemini outputs and four Sol outputs on the same selected tasks. Planned or unavailable outputs are not counted as executed judgments. The four-task slice contains two project-management, one purchasing and one shipping task; it cannot establish a general model ranking. Sonnet solver outputs are excluded from this secondary cohort.</p><p>'+link(out/'cross_family_judging/latest-plan.json',out,'Exact bindings and pending actions')+'</p>'
    diagnostic=report.get('invalid_contract_diagnostic')
    if diagnostic:
        text+='<h2>Post-hoc grader-contract audit</h2><p>Diagnostic snapshot: '+esc(diagnostic.get('created_at'))+'. Later grader records may be absent until the separate audit is regenerated.</p><p class="note warning">Frozen invalid judgments remain invalid. Separate nested sensitivity diagnostics test container shape (S1), supplied-image attribution (S2), and exact packet locator wrappers (S3). These diagnose the evaluation contract; they do not establish correct judgments, replace frozen scores, or validate human accuracy.</p><p>'+esc(diagnostic.get('transformation_policy'))+'</p><table><thead><tr><th>Cohort</th><th>Raw invalid cases</th><th>Contract-valid S1</th><th>Contract-valid S2</th><th>Contract-valid S3</th><th>Still invalid after S1</th></tr></thead><tbody>'
        for cohort,counts in diagnostic.get('cohort_counts',{}).items():text+=f'<tr><td>{esc(cohort)}</td><td>{esc(counts.get("raw_invalid_cases"))}</td><td>{esc(counts.get("contract_valid_after_shape_only"))}</td><td>{esc(counts.get("contract_valid_after_S2"))}</td><td>{esc(counts.get("contract_valid_after_S3"))}</td><td>{esc(counts.get("still_invalid"))}</td></tr>'
        text+='</tbody></table><p>Recorded coverage text in the wrong container is not evidence that the judge failed to inspect the document. Some visual-attribution errors involve supplied images spanning multiple artifacts, and some quote failures involve locator-augmented packet text. These remain separate validation causes; no unseen-image or semantic-error conclusion follows automatically.</p><p>'+link(out/'invalid_judgment_audit/diagnostics.json',out,'Raw fields, transformations, remaining errors and evidence hashes')+' · '+link(out/'invalid_judgment_audit/summary.txt',out,'Contract-audit summary')+'</p>'
    queue_amendment=root/'config/evaluation_v2_review_queue_amendment.json'
    if queue_amendment.exists():text+='<p>'+link(queue_amendment,out,'Explicit amendment limiting additional-model review to the four-task extension')+'</p>'
    if report.get('account_reconciliation_snapshot'):
        snap=report['account_reconciliation_snapshot']
        text+='<p class="note">A dated account-usage reconciliation is available for '+esc(snap.get('observed_at'))+'. '+esc(snap.get('interpretation'))+' This snapshot is not a current wallet balance and does not settle individual unknown charges. '+link(out/'account-reconciliation-snapshot.json',out,'Reconciliation snapshot')+'</p>'
    if report.get('administrative_solver_allocation_release') or report.get('future_sonnet_image_reservation_amendment'):
        text+='<h2>Administrative allocation and future-request reservations</h2><p>The total authorized campaign ceiling remains $30. An internal solver allocation was released after the core fifteen native deliverables had grading attempts. This does not add account funds or raise the campaign ceiling, and unknown previous charges remain reserved.</p>'
        if report.get('administrative_solver_allocation_release'):text+='<p>'+link(root/'config/evaluation_v2_solver_allocation_release.json',out,'Administrative allocation release and eligibility gate')+'</p>'
        if report.get('future_sonnet_image_reservation_amendment'):text+='<p>A separate amendment uses an 8,192-token reservation for each verified small inline image in future Sonnet judge requests, instead of the generic 40,000-token bound. The submitted prompt, rubric, images and output limit remain the same. Original budget stops, executed judgments and unknown-charge reservations remain recorded. '+link(root/'config/evaluation_v2_cross_family_image_reservation_amendment.json',out,'Image reservation amendment, cited official documentation and continuation rules')+'</p>'
        if report.get('funded_worker_freeze'):text+='<p>The last newly funded first-pass cell has its own worker freeze and shares the existing scheduling lease. Its change concerns budget estimation and internal allocation; the total remains $30 and request settings remain recorded unchanged. '+link(out/'extension/funded-workers/freeze.json',out,'Funded-worker execution freeze and proof paths')+'</p>'
    if report.get('unexecuted_construct_review_available'):
        text+='<h2>Unfinished validation proposals</h2><p>Four proposed source-anchored edits are available for human review of their intended effect. They have not been executed as native variants, judged, accepted as gold labels or shown to improve training. This optional work is separate from the completed original-task attempts.</p><p>'+link(out/'construct_direction_review/index.html',out,'Review proposed control directions without judge verdicts')+'</p>'
    checks=report.get('judge_checks')
    if checks:
        text+='<h2>Bounded judge robustness and inspection checks</h2><p>Exploratory checks on selected outputs. Scheduled work is not an executed result. Reused fixed-arm results add no new API calls; their original validity status stays unchanged. Stable or changed verdicts do not establish accuracy.</p>'
        text+=f'<p>{esc(checks.get("physical_new_requests",0))} new physical requests; ${float(checks.get("known_incremental_cost_usd",0)):.5f} known incremental cost; {esc(checks.get("unresolved_calls",0))} unresolved calls. Human accuracy and human acceptance remain unknown.</p>'
        text+='<table><thead><tr><th>Study</th><th>Endpoint</th><th>Valid pair denominator</th><th>Flips</th><th>Unchanged</th><th>Excluded</th></tr></thead><tbody>'
        for study,group in checks.get('comparison_counts',{}).items():
            for endpoint,counts in group.get('endpoints',{}).items():text+=f'<tr><td>{esc(study)}</td><td>{esc(endpoint)}</td><td>{esc(counts.get("valid_pair_denominator"))}</td><td>{esc(counts.get("flips"))}</td><td>{esc(counts.get("unchanged"))}</td><td>{esc(json.dumps(counts.get("excluded",{}),sort_keys=True))}</td></tr>'
        text+='</tbody></table><ul>'+''.join('<li>'+esc(x)+'</li>' for x in checks.get('limits',[]))+'</ul><p>'+link(checks['source_path'],out,'Judge-check results and exclusions')+'</p>'
    contrast=report.get('gmp_agentic_contrast')
    if contrast:
        text+='<h2>GMP form: agreement on what is visible, disagreement on usability</h2><p>This is one selected recovery output, not a primary observation or proof that an agentic judge is better. The fixed and adaptive visual arms cite the same five supplied views. Both acknowledge page-one text crossing form rules; they differ on whether the result satisfies the usability requirement. A technical audit also observed the layout issue. Human acceptance remains unresolved.</p><table><thead><tr><th>Arm</th><th>Raw response status</th><th>R7 usability verdict</th><th>Post-hoc S2 contract-valid</th><th>Rationale</th></tr></thead><tbody>'
        for arm in contrast['arms']:text+=f'<tr><td>{esc(arm["arm"])}</td><td>{esc(arm["raw_status"])}</td><td>{esc(arm["criterion_status"])}</td><td>{esc(arm["posthoc_S2_contract_valid"])}</td><td>{esc(arm["rationale"])}<br>{link(arm["record_path"],out,"Original record")}</td></tr>'
        text+='</tbody></table><p>Targeted human question: Accept this form as usable without correction, or require fields/comments relayout? This post-hoc review priority is separate from the frozen primary review sample. The blind recovery review page contains the form and this question without judge verdicts.</p>'
    text+='<details><summary>Physical request states and reported token usage</summary><pre>'+esc(json.dumps({'request_states':report['cost'].get('request_status_counts',{}),'usage_fields_as_reported':report['cost'].get('reported_usage',{})},indent=2))+'</pre><p>Provider usage fields are retained as reported; input/output and prompt/completion vocabularies are not added together twice.</p></details>'
    return text

def gmp_contrast(root,out,diagnostic):
    arms=[]
    for name in ('A_text','B_fixed','C_adaptive'):
        path=out/'judge_checks/jobs'/('check_agentic__P-pdf__'+name)/'result.json';record=read(path,{})
        if not record:continue
        original=read(record['reused_result_path'],{}) if record.get('reused_result_path') else record
        judgment=read(original.get('judgment_path',''),{})
        row=next((x for x in judgment.get('criteria',[]) if x.get('id')=='R7'),None)
        if not row:continue
        source_status=original.get('status');posthoc=True if source_status=='graded' else None
        audit_target=Path(record.get('reused_result_path') or path)
        audit=next((x for x in (diagnostic or {}).get('cases',[]) if x.get('result_path')==str(audit_target.relative_to(root))),None)
        if audit:posthoc=audit.get('posthoc_levels',{}).get('S2_shape_and_visual_relation',{}).get('contract_valid')
        arms.append({'arm':name,'raw_status':source_status,'criterion_status':row.get('status'),'rationale':row.get('rationale'),'inspection_ids':row.get('inspection_ids',[]),'posthoc_S2_contract_valid':posthoc,'record_path':str(path),'record_sha256':sha(path),'human_acceptance':None})
    return {'case_id':'P-pdf','task_id':'58ac1cc5-5754-4580-8c9c-8c67e1a9d619','cohort':'recovery','arms':arms,'human_acceptance':None,'accuracy_inference':False} if len(arms)==3 else None

def calibration_summary(data,path):
    cases=[]
    for case in data.get('cases',[]):
        target=next((r for r in case.get('criteria',[]) if r.get('criterion_id')=='source_and_authority_consistency'),{})
        cases.append({'case_id':case.get('case_id'),'judge_model':case.get('judge_model'),'whole_response_status':case.get('raw_whole_response_status'),'historical_human_consequential_error':case.get('human_consequential_error'),'target_row_valid':target.get('row_valid'),'target_row_status':target.get('row_status'),'diagnostic_matrix_cell':case.get('diagnostic_matrix_cell'),'target_rationale':target.get('rationale'),'invalid_rows':[{'criterion_id':r.get('criterion_id'),'validation_errors':r.get('row_validation_errors',[]),'row_status':r.get('row_status'),'coverage_status':r.get('coverage_status')} for r in case.get('criteria',[]) if r.get('row_valid') is not True]})
    primary=[]
    for case in data.get('primary_row_diagnostics',[]):
        primary.append({'task_id':case.get('task_id'),'solver_run_id':case.get('solver_run_id'),'judge_model':case.get('judge_model'),'whole_response_status':case.get('raw_whole_response_status'),'valid_rows':sum(r.get('row_valid') is True for r in case.get('criteria',[])),'total_rows':len(case.get('criteria',[])),'whole_response_validation_errors':case.get('whole_response_validation_errors',[]),'human_labels':None})
    return {'analysis_status':data.get('analysis_status'),'source_path':str(path),'source_sha256':sha(path),'semantics':data.get('semantics'),'preservation':data.get('preservation'),'limitations':data.get('limitations',[]),'per_judge':data.get('per_judge',{}),'historical_cases':cases,'primary_row_diagnostics':primary,'whole_output_accuracy_estimated':False,'historical_labels_reused_as_new_labels':False}

def calibration_html(data,out):
    text='<h2>Selected development calibration</h2><p class="note warning">Post-hoc diagnostic of one criterion on five previously exposed historical cases. This is not whole-output accuracy, a fresh holdout, or independent expert validation. Original invalid whole-response statuses remain invalid. None of these labels enters the new blinded review queue.</p>'
    text+='<p>'+esc(data.get('semantics'))+' '+esc(data.get('preservation'))+'</p>'
    for judge,stats in data.get('per_judge',{}).items():
        matrix=stats.get('matrix',{});statuses=stats.get('whole_response_statuses',{})
        text+=f'<p><code>{esc(judge)}</code>: target criterion counts TP {matrix.get("TP",0)}, TN {matrix.get("TN",0)}, FN {matrix.get("FN",0)}, FP {matrix.get("FP",0)} across {stats.get("binary_comparable_cases",0)} selected cases. Whole-response statuses: {esc(json.dumps(statuses,sort_keys=True))}. No population accuracy estimate is derived.</p>'
    text+='<table><thead><tr><th>Historical case</th><th>Whole response</th><th>Individually validated target row</th><th>Historical human consequential label</th><th>Diagnostic cell</th><th>Invalid rows retained</th></tr></thead><tbody>'
    for case in data['historical_cases']:
        invalid='; '.join(r['criterion_id']+': '+', '.join(r['validation_errors']) for r in case['invalid_rows'])
        text+=f'<tr><td><code>{esc(case["case_id"])}</code></td><td>{esc(case["whole_response_status"])}</td><td>{esc(case["target_row_status"])}; evidence-valid: {esc(case["target_row_valid"])}</td><td>{esc(case["historical_human_consequential_error"])}</td><td>{esc(case["diagnostic_matrix_cell"])}</td><td>{esc(invalid or "none")}</td></tr>'
    text+='</tbody></table><ul>'+''.join('<li>'+esc(x)+'</li>' for x in data['limitations'])+'</ul>'
    if data['primary_row_diagnostics']:
        text+='<details><summary>New-output row eligibility diagnostics, without human labels</summary><p>Individually eligible rows do not repair an invalid full response and do not establish accuracy.</p><table><thead><tr><th>Task</th><th>Whole-response status</th><th>Eligible rows</th><th>Retained errors</th></tr></thead><tbody>'
        for case in data['primary_row_diagnostics']:
            text+=f'<tr><td><code>{esc(case["task_id"])}</code></td><td>{esc(case["whole_response_status"])}</td><td>{case["valid_rows"]}/{case["total_rows"]}</td><td>{esc("; ".join(case["whole_response_validation_errors"]))}</td></tr>'
        text+='</tbody></table></details>'
    return text+'<p>'+link(data['source_path'],out,'Complete calibration analysis and case evidence')+'</p>'

def report_html(r,out,reviews,root):
    summary=r['primary_summary'];cost=r['cost'];rows=[]
    for t in r['task_roster']:
        runs=[x for x in r['primary_runs'] if x['task_id']==t['task_id']]
        entries=[]
        for run in runs:
            native='; '.join(link(a['path'],out,a.get('filename','Native file')) for a in run['submission'] if a.get('path'))
            entries.append(f'<b>{esc(run["model"])}</b><br>{esc(run["status"])}<br>{esc(run.get("failure_attribution") or "")}<br>{native}')
        warnings=t['dependency_gaps']+t['source_quality_flags']
        rows.append(f'<tr><td>{esc(t["name"])}<br><code>{esc(t["task_id"])}</code></td><td>{esc(t["occupation"])}</td><td>{"<br>".join(entries) or "Unrun"}</td><td>{esc("; ".join(str(x) for x in warnings) or t.get("external_dependency") or "No recorded blocking source issue")}</td></tr>')
    jrows=[]
    for j in r['judgments']:
        if j.get('grading_cohort')!='grades' or j.get('solver_cohort')!='primary' or j.get('judge_model')!=r['primary_judge_model'] or j.get('solver_model')!=r['primary_solver_model']:continue
        jrows.append(f'<tr><td><code>{esc(j["task_id"] or j["run_id"])}</code><br>{link(j["record_path"],out,"Full automated record")}</td><td>{esc(j["judge_model"])}</td><td>{esc(j["validation_status"] or j["status"])}<br>{esc("; ".join(j["validation_errors"]))}</td><td>{esc(j["project_rubric_pass"])}<br>Failed: {esc(", ".join(j["failed_criteria"]) or "none recorded")}</td><td>{esc(j["consequential_error_candidate"])}</td><td>{esc(", ".join(j["uncertain_criteria"]) or "none recorded")}<br>Task/source defect: {esc((j["task_defect"] or {}).get("status"))}</td></tr>')
    drows=''.join(f'<tr><td><code>{esc(d["task_id"])}</code></td><td>{esc(d["model"])}</td><td>{esc(d["stage"])}</td><td>{esc(d["status"])}</td><td>${d["cost"]["known_provider_cost_usd"]:.5f}</td></tr>' for d in r['development_runs'])
    costs=''.join(f'<tr><td>{esc(scope)}</td><td>{c["physical_request_records"]}</td><td>${c["known_provider_cost_usd"]:.5f}</td><td>{c["unknown_charge_records"]}</td><td>${c["unresolved_reserved_usd"]:.5f}</td></tr>' for scope,c in cost['by_scope'].items())
    models=''.join(f'<li><code>{esc(m["model"])}</code>: primary cohort {esc(m["primary_status"])} ({m["primary_run_count"]} records); {m.get("supplemental_run_count",0)} separate supplemental run records.</li>' for m in r['models'])
    providers=''.join(f'<li>{esc(x["task_id"][:8])}, <code>{esc(x["model"])}</code>: {esc(", ".join(x["served_providers"]) or "provider not returned")}; {x["provider_unknown_requests"]}/{x["physical_requests"]} requests without provider identity.</li>' for x in r['primary_runs']) or '<li>No primary requests recorded.</li>'
    citations=''.join(f'<tr><td><a href="{html.escape(c["url"],quote=True)}">{esc(c["title"])}</a></td><td>{esc(c["application"])}</td><td>{esc(c["limit"])}</td></tr>' for c in r['method_sources'])
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Original GDPval evaluation v2</title><style>{STYLE}</style></head><body><main><h1>Original GDPval evaluation v2</h1><p>All 15 original tasks in three previously selected occupations. One primary model is prioritized within the available budget. This report separates execution, native delivery, automated judgments and human review.</p><p class="note warning">Human review comes first. {link(reviews/'index.html',out,'Open the blinded review queue')} before reading automated findings. New human reviews completed: <b>{r['human_validation']['completed_reviews']}</b>. No model ranking, expert acceptance estimate, validated judge accuracy or training-improvement claim follows from these runs.</p><div class="stats"><div class="stat"><b>{r['planned_tasks']}</b>Original tasks planned</div><div class="stat"><b>{summary['attempted_tasks']}</b>Tasks with primary requests</div><div class="stat"><b>{summary['submitted_tasks']}</b>Tasks with native submissions</div><div class="stat"><b>{summary['unrun_tasks']}</b>Tasks without primary requests</div></div><p class="muted">Snapshot: {esc(r['generated_at'])}. An in-progress or interrupted record is not a completed result. A submitted file is not an accepted deliverable.</p><h2>Task accounting</h2><div class="scroll"><table><thead><tr><th>Original task</th><th>Occupation</th><th>Primary execution and native files</th><th>Source or task limitations</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><h2>Models and serving identity</h2><ul>{models}</ul><details><summary>Observed provider identity</summary><ul>{providers}</ul></details><p>These are requested model routing IDs. Omitted serving-provider identities remain unknown.</p><h2>Automated grading coverage</h2><p>Compact source-anchored project rubric, not the full official GDPval score. A valid quote confirms traceability; it does not establish that the judge interpreted the evidence correctly. Consequential flags remain review candidates.</p><div class="scroll"><table><thead><tr><th>Task/run</th><th>Judge</th><th>Evidence validity</th><th>Project rubric pass</th><th>Consequential candidate</th><th>Uncertain criteria</th></tr></thead><tbody>{''.join(jrows) or '<tr><td colspan="6">No judge result records yet.</td></tr>'}</tbody></table></div><p>Agentic pilot: {esc(r['agentic_judge_status'])}.</p><h2>Human validation</h2><p>{r['human_validation']['primary_planned_case_slots']} primary task slots ({r['human_validation']['primary_ready_case_slots']} with deliverables) are separate from {r['human_validation']['additional_model_planned_case_slots']} additional-model slots ({r['human_validation']['additional_model_ready_case_slots']} with deliverables). These total {r['human_validation']['planned_case_slots']} prospective slots. The primary sample covers {r['human_validation']['prespecified_tasks']} selected tasks; the additional four-task sample is separate. Additional-model review is pending validation work, not a prerequisite for submitting the current study. {r['human_validation']['completed_reviews']} completed new reviews. All unreviewed labels remain blank. The five historical reviews are development evidence and are excluded.</p><p>{link(reviews/'index.html',out,'Review original sources and native deliverables')} · {link(reviews/'human-reviews.json',out,'Blank or preserved human review record')}</p><h2>Cost and unknown charges</h2><p><b>${cost['known_provider_cost_usd']:.5f}</b> known provider-reported cost across generation, smoke and judging. <b>{cost['unknown_charge_records']}</b> unresolved charge records reserve <b>${cost['unresolved_reserved_usd']:.5f}</b>. Authorized campaign ceiling: ${float(r['authorized_budget_usd'] or 0):.2f}. {esc(cost['interpretation'])}</p><table><thead><tr><th>Scope</th><th>Physical request records</th><th>Known cost</th><th>Unknown charges</th><th>Outstanding reserve</th></tr></thead><tbody>{costs or '<tr><td colspan="5">No API requests recorded.</td></tr>'}</tbody></table><h2>Development work kept separate</h2><p>{esc(r['development_separation'])}</p><table><thead><tr><th>Task</th><th>Model</th><th>Stage</th><th>Status</th><th>Known cost</th></tr></thead><tbody>{drows or '<tr><td colspan="5">No new development records.</td></tr>'}</tbody></table><h2>Research methods applied</h2><p>Methods are inspirations. This study does not reproduce the papers' numerical results. {link(root/'docs/evaluation_v2/grader-protocol.md',out,'Read the grading protocol')}.</p><table><thead><tr><th>Primary source</th><th>Application</th><th>Limit</th></tr></thead><tbody>{citations}</tbody></table><h2>Limits of the evidence</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in r['limitations'])}</ul><footer>{link(out/'report.json',out,'Machine-readable report')} · Input hash <code>{esc(r['task_input_sha256'])}</code><br>Build script hash <code>{esc(r['build_script_sha256'])}</code></footer></main></body></html>'''

def self_test():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        tasks=[{'task_id':f'task-{i:02d}','prompt':'Original task '+str(i),'occupation':'Occupation '+str(i//5),'references':[]} for i in range(15)]
        (root/'data/evaluation_v2').mkdir(parents=True);(root/'data/evaluation_v2/tasks.jsonl').write_text('\n'.join(json.dumps(t) for t in tasks))
        write(root/'config/evaluation_v2_run.json',{'primary_model':'test/model','primary_judge':'test/primary_judge','authorized_available_budget_usd':14.66})
        write(root/'config/evaluation_v2_grader.json',{'human_validation':{'selected_task_ids':[t['task_id'] for t in tasks[:9]]}})
        empty=build(root);assert empty['planned_tasks']==15 and empty['primary_summary']['attempted_tasks']==0
        assert empty['human_validation']['planned_case_slots']==9 and empty['human_validation']['completed_reviews']==0
        folder=root/'output/evaluation_v2/runs/task-00__test_model__smoke';write(folder/'task.json',tasks[0]);write(folder/'result.json',{'task_id':'task-00','model':'test/model','stage':'smoke','status':'ended_without_submission'})
        write(root/'output/evaluation_v2/calls/a/reservation.json',{'id':'a','label':folder.name+':turn1','scope':'solver_smoke','model':'test/model','actual_cost_usd':None,'reserved_usd':.1})
        smoke=build(root);assert smoke['primary_summary']['attempted_tasks']==0 and len(smoke['development_runs'])==1
        assert smoke['cost']['unknown_charge_records']==1 and smoke['cost']['known_provider_cost_usd']==0 and smoke['cost']['unresolved_reserved_usd']==.1
        review_text=(root/'reviews/evaluation_v2/index.html').read_text();assert 'test/model' not in review_text and 'consequential_error_candidate' not in review_text
        key_before=read(root/'output/evaluation_v2/review-private-key.json');build(root);assert read(root/'output/evaluation_v2/review-private-key.json')==key_before
        primary=root/'output/evaluation_v2/runs/task-00__test_model__primary';native=primary/'workspace/submitted/model_named_answer.txt';native.parent.mkdir(parents=True);native.write_text('Unchanged professional deliverable')
        write(primary/'task.json',tasks[0]);write(primary/'result.json',{'task_id':'task-00','model':'test/model','stage':'primary','status':'submitted','submission':[{'filename':native.name,'path':str(native),'kind':'txt','previews':[]}]})
        write(root/'output/evaluation_v2/calls/b/reservation.json',{'id':'b','label':primary.name+':turn1','scope':'solver_primary','model':'test/model','actual_cost_usd':.025,'reserved_usd':.1})
        ready=build(root);assert ready['primary_summary']['attempted_tasks']==1 and ready['primary_summary']['submitted_tasks']==1
        hpath=root/'reviews/evaluation_v2/human-reviews.json';reviews=read(hpath);case=next(c for c in reviews['cases'] if c['status']=='ready_for_review')
        assert Path(case['artifacts'][0]['path']).name=='deliverable-01.txt' and Path(case['artifacts'][0]['path']).read_bytes()==native.read_bytes()
        case['review'].update(task_or_source_defect='no',accept_without_substantive_correction='uncertain',consequential_error='uncertain',reviewer='Fixture reviewer',completed_at='2026-11-04T00:00:00Z')
        write(hpath,reviews);preserved=build(root);assert preserved['human_validation']['completed_reviews']==1 and preserved['human_validation']['acceptance_counts']=={'uncertain':1}
        recovery=root/'output/evaluation_v2/runs/task-00__test_model__recovery';write(recovery/'task.json',tasks[0]);write(recovery/'result.json',{'task_id':'task-00','model':'test/model','stage':'supplemental','recovery_of':primary.name,'recovery_stage':'recovery','status':'submitted','submission':[{'path':str(native),'kind':'txt','previews':[]}]})
        write(root/'config/evaluation_v2_budget_amendment.json',{'authorized_total_usd':30,'reason':'Fixture authorization amendment'})
        write(root/'output/evaluation_v2/calibration_analysis.json',{'analysis_status':'post_hoc','cases':[{'case_id':'HISTORICAL-FIXTURE','raw_whole_response_status':'invalid_judgment','criteria':[]}],'per_judge':{},'limitations':['Historical cases only']})
        amended=build(root);assert amended['authorized_budget_usd']==30 and amended['budget_correction']['original_operative_ceiling_usd']==14.66 and amended['budget_correction']['current_wallet_balance_usd'] is None
        assert len(amended['recovery_runs'])==1 and len(amended['supplemental_runs'])==0 and amended['primary_summary']['submitted_tasks']==1
        assert amended['calibration_diagnostic']['historical_cases'][0]['whole_response_status']=='invalid_judgment'
        assert 'HISTORICAL-FIXTURE' not in (root/'reviews/evaluation_v2/index.html').read_text()
        write(root/'config/evaluation_v2_model_extension.json',{'tasks':[{'task_id':'task-01','name':'Attempted spreadsheet task','occupation':'Occupation 0','formats':['xlsx']},{'task_id':'task-02','name':'Unattempted presentation task','occupation':'Occupation 1','formats':['pptx']}],'models':['test/extra']})
        repair=root/'output/evaluation_v2/runs/task-01__test_model__adapter_repair';write(repair/'task.json',tasks[1]);write(repair/'result.json',{'task_id':'task-01','model':'test/model','stage':'adapter_repair','status':'submitted','submission':[{'path':str(native),'kind':'txt','previews':[]}]})
        scoped=build(root)
        assert scoped['human_validation']['primary_planned_case_slots']==9 and scoped['human_validation']['additional_model_planned_case_slots']==2
        assert len(read(root/'reviews/evaluation_v2/primary-human-reviews.json')['cases'])==9
        assert 'test/extra' not in (root/'reviews/evaluation_v2/supplemental.html').read_text()
        assert scoped['primary_summary']['submitted_tasks']==1 and scoped['all_cohort_native_coverage']['distinct_original_tasks_with_any_submitted_native_output']==2
        assert len(scoped['adapter_repair_runs'])==1 and all(x['stage']!='adapter_repair' for x in scoped['development_runs'])
        grade_entries=[{'task_id':t['task_id'],'solver_model':'test/model','stage':'primary','judge_model':'test/primary_judge','effective_status':'graded'} for t in tasks]
        grade_entries.append({'task_id':'task-00','solver_model':'test/model','stage':'primary','judge_model':'test/secondary_judge','effective_status':'budget_limited'})
        write(root/'output/evaluation_v2/grade-resolution-index.json',{'entries':grade_entries})
        judged=build(root);assert sum(judged['effective_primary_grade_status_counts'].values())==15 and judged['effective_primary_grade_status_counts']=={'graded':15}
        assert judged['effective_secondary_grade_status_counts']=={'test/secondary_judge':{'budget_limited':1}}
        duplicated=effective_primary_grades(grade_entries+[grade_entries[0]],'test/model','test/primary_judge',{t['task_id'] for t in tasks})
        assert sum(duplicated['status_counts'].values())<=15 and duplicated['status_counts']['duplicate_primary_grade_records']==1
        original=root/'output/evaluation_v2/runs/task-01__test_extra__supplemental';write(original/'task.json',tasks[1]);write(original/'result.json',{'task_id':'task-01','model':'test/extra','stage':'supplemental','status':'budget_limited'})
        write(root/'output/evaluation_v2/calls/d/reservation.json',{'id':'d','label':original.name+':turn1','scope':'solver_supplemental','model':'test/extra','actual_cost_usd':0,'reserved_usd':.1})
        continued=root/'output/evaluation_v2/runs'/f'{original.name}__budget_continuation';write(continued/'task.json',tasks[1]);write(continued/'result.json',{'task_id':'task-01','model':'test/extra','stage':'supplemental','recovery_stage':'recovery','recovery_of':original.name,'continuation_of':original.name,'original_supplemental_run':original.name,'continuation_kind':'budget_continuation','status':'submitted','inherited_known_cost_usd':.025,'inherited_unresolved_reserved_usd':.1,'calls':['c'],'inherited_calls':['b'],'known_cost_usd':.01,'submission':[{'path':str(native),'kind':'txt','previews':[]}]})
        write(root/'output/evaluation_v2/calls/c/reservation.json',{'id':'c','label':continued.name+':turn1','scope':'solver_continuation','model':'test/extra','actual_cost_usd':.01,'reserved_usd':.1})
        continuation_report=build(root);cell=next(c for c in continuation_report['supplemental_planned_cells'] if c['task_id']=='task-01')
        assert cell['status']=='budget_limited' and not cell['native_produced'] and cell['continuation_native_available'] and len(cell['separate_continuations'])==1
        assert continuation_report['cost']['known_provider_cost_usd']==.035 and continuation_report['primary_summary']['submitted_tasks']==1
        assert continuation_report['human_validation']['additional_model_ready_case_slots']==0
        actual=continuation_report['supplemental_plan_summary'];assert actual['attempted_cells']==1 and actual['unattempted_cells']==1 and actual['actual_attempted_required_formats']==['xlsx'] and actual['actual_attempted_occupations']==['Occupation 0'] and actual['planned_required_formats']==['pptx','xlsx']
        return {'status':'passed','checks':['empty primary study retains 15 tasks','smoke excluded from primary denominator','9 blank prespecified review slots','unknown charges are reserved, not reported as paid','review page omits model and judge metadata','randomization persists across builds','submitted native copy preserves bytes with neutral filename','existing human answers survive rebuild without inferred acceptance','recovery stays separate from original denominator and review slot','amended authorization is distinct from original ceiling and current wallet','post-hoc invalid calibration statuses preserved outside review queue','additional reviews limited to planned extension cells on a separate page','adapter repair separated from primary and development counts','primary grading fixes solver and judge identities and cannot exceed 15 task slots','secondary judgments counted separately; duplicate primary records flagged without inflating tasks','supplemental continuations preserve original stopped slots and separate native availability','inherited continuation costs are not double-counted; continuation labels do not replace primary or additional original review slots','actual additional-model formats and occupations exclude unattempted planned tasks']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default=str(ROOT));parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:print(json.dumps(self_test(),indent=2))
    else:
        result=build(Path(args.root));print(json.dumps({'report':str(Path(args.root)/'output/evaluation_v2/report.html'),'planned_tasks':result['planned_tasks'],'primary_summary':result['primary_summary'],'known_cost_usd':result['cost']['known_provider_cost_usd'],'unresolved_charge_records':result['cost']['unknown_charge_records'],'primary_review_slots':result['human_validation']['primary_planned_case_slots'],'additional_model_review_slots':result['human_validation']['additional_model_planned_case_slots']},indent=2))
