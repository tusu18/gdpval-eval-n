"""Freeze a balanced public-GDPval selection; no inference or downloads."""
import csv
import hashlib
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
REVISION='11e7900cdcac61bc4daf59e65feb238acda98fbf'
OCCUPATIONS=[
 'Buyers and Purchasing Agents',
 'Project Management Specialists',
 'Shipping, Receiving, and Inventory Clerks',
 'Accountants and Auditors',
 'Administrative Services Managers',
 'Financial Managers',
 'Order Clerks',
 'General and Operations Managers',
]
RATIONALES={
 OCCUPATIONS[0]:'Supplier comparisons, numerical tradeoffs, sourcing and approval conditions.',
 OCCUPATIONS[1]:'Schedules, costs, risk, dependencies and change control across deliverables.',
 OCCUPATIONS[2]:'Inventory joins, shipment decisions, operating instructions and exceptions.',
 OCCUPATIONS[3]:'Accounting classification, arithmetic, timing and financial reconciliation.',
 OCCUPATIONS[4]:'Staffing, service procedures, planning rules and cross-document consistency.',
 OCCUPATIONS[5]:'Financial models, contractual compensation and business decision support.',
 OCCUPATIONS[6]:'Order and invoice reconciliation, units, dates, conditional rules and spreadsheet functionality.',
 OCCUPATIONS[7]:'Operational forms, capacity planning, role boundaries, escalation and usable instructions.',
}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def main():
    target=ROOT/'data/evaluation_v4';target.mkdir(parents=True,exist_ok=True)
    if (target/'selection-freeze.json').exists():
        frozen=json.loads((target/'selection-freeze.json').read_text())
        for name,expected in frozen['files'].items():
            if digest(ROOT/name)!=expected:raise ValueError('Frozen selection changed')
        print('Existing 40-task selection freeze verified; no work rerun.')
        return
    catalog=ROOT/'data/evaluation_v3/candidate-source.jsonl'
    rows=[json.loads(line) for line in catalog.read_text().split('\n') if line.strip()]
    selected=sorted((r for r in rows if r['occupation'] in OCCUPATIONS),key=lambda r:(OCCUPATIONS.index(r['occupation']),r['task_id']))
    assert len({r['task_id'] for r in selected})==40
    assert Counter(r['occupation'] for r in selected)==Counter({o:5 for o in OCCUPATIONS})
    prior=json.loads((ROOT/'output/evaluation_v2/report.json').read_text())
    core={r['task_id'] for r in prior['primary_solver_native_grade_coverage']['rows']}
    extra=json.loads((ROOT/'output/evaluation_v3/report.json').read_text())
    extension={r['task_id'] for r in extra['tasks'] if r['native_submitted']}
    assert len(core)==15 and len(extension)==5 and not core&extension
    roster=[];source_members=defaultdict(list)
    solver=[]
    for row in selected:
        record={k:row[k] for k in ('task_id','occupation','sector','prompt','reference_files')}
        record['reference_urls']=[f'https://huggingface.co/datasets/openai/gdpval/resolve/{REVISION}/{quote(p,safe="/")}' for p in row['reference_files']]
        solver.append(record)
        status='existing_v2_native_output' if row['task_id'] in core else ('existing_v3_native_output' if row['task_id'] in extension else 'not_run')
        roster.append({'task_id':row['task_id'],'occupation':row['occupation'],'sector':row['sector'],'status':status,'reference_count':len(row['reference_files']),'prompt_sha256':hashlib.sha256(row['prompt'].encode()).hexdigest()})
        for source in row['reference_files']:source_members[source].append(row['task_id'])
    (target/'tasks.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=True)+'\n' for r in solver))
    with (target/'task-roster.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(roster[0]));writer.writeheader();writer.writerows(roster)
    save(target/'task-roster.json',roster)
    counts=[{'occupation':o,'selected':5,'existing_outputs':sum(r['occupation']==o and r['status']!='not_run' for r in roster),'remaining':sum(r['occupation']==o and r['status']=='not_run' for r in roster),'selection_rationale':RATIONALES[o]} for o in OCCUPATIONS]
    manifest={'schema':'gdpval-balanced-selection-v4-1','created_at_utc':datetime.now(timezone.utc).isoformat(),'user_facing_date':datetime.now(ZoneInfo('America/New_York')).date().isoformat(),'dataset':'openai/gdpval','revision':REVISION,'catalog_sha256':digest(catalog),'original_parquet_sha256':digest(ROOT/'research/train-00000-of-00001.parquet'),'source_catalog_tasks':len(rows),'selected_unique_original_tasks':40,'selected_occupations':8,'per_occupation':5,'sectors':sorted({r['sector'] for r in selected}),'existing_unique_tasks_with_outputs':20,'new_tasks_requiring_execution':20,'new_model_runs_in_this_selection_step':0,'new_api_spend_usd':0,'occupations':counts,'selection_rule':'Retain all six already-represented occupations, add two occupations after prompt-level screening of four candidates, and include ALL five original public tasks in each selected occupation. No individual task sampled or dropped by model outcome.','selection_type':'Purposive, staged occupation selection with complete coverage of public tasks within each chosen occupation. Not random or economy-representative.','outcome_exposure':'The prior20 task outcomes informed the exploratory research direction. The additional20 task IDs are fixed before their solver outputs. Do not describe the complete40 as an untouched preregistered confirmation.','no_synthetic_padding':True,'repeats_and_controlled_input_edits_are_additional_unique_tasks':False,'solver_field_allowlist':list(solver[0]),'source_file_records':sum(len(r['reference_files']) for r in selected),'unique_source_paths':len(source_members),'shared_exact_reference_paths':{p:ids for p,ids in source_members.items() if len(set(ids))>1},'independence_caveat':'Unique task IDs do not prove independent business episodes. Audit shared sources, templates and business-case lineage before uncertainty estimates. Related Aurisic accounting tasks may share business context.','execution_caveat':'A balanced task roster does not make existing v2 OpenRouter and v3 in-app runs comparable. Preserve cohorts. Uniform comparisons require matched model, harness, source policy, resource limits and grading.','preflight_status':'Selection only. New sources not yet downloaded/validated by this step. Some retained tasks require external research; source contradictions and missing files remain to be audited.','next_execution_gate':'Expose and test required native features (including real pivots, filters, charts, dropdowns and appropriate document images/print controls), establish external evidence policy, preflight references, freeze new-task rubrics and an execution protocol before scoring.'}
    save(target/'selection.json',manifest)
    paths=[target/'tasks.jsonl',target/'task-roster.csv',target/'task-roster.json',target/'selection.json',ROOT/'docs/evaluation_v4/selection-method.txt',ROOT/'docs/evaluation_v4/candidate-screening.json',Path(__file__).resolve()]
    save(target/'selection-freeze.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Selection only, not a run/grader protocol freeze','files':{str(p.relative_to(ROOT)):digest(p) for p in paths}})
    print(json.dumps({'selected':40,'occupations':8,'existing_outputs':20,'remaining':20,'source_file_records':manifest['source_file_records'],'sectors':len(manifest['sectors']),'new_model_runs':0}))

if __name__=='__main__':main()
