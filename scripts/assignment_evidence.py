"""Rebuild the assignment evidence from saved records and genuine human exports.

Offline/stdlib only. Historical studies are immutable inputs. No inferred human
labels, automatic adjudication, model ranking, or paid calls are performed.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
try:
    from judge_agreement import agreement_diagnostics
except ModuleNotFoundError:
    from scripts.judge_agreement import agreement_diagnostics

ROOT = Path(__file__).resolve().parents[1]
BASE_INPUTS = (
 'output/paired_v1/summary.json', 'output/paired_v1/scores.json',
 'config/paired_protocol.v1.json', 'output/current_study_06/summary.json',
 'output/current_study_06/verification.json', 'output/submission_audit/taxonomy.json',
 'output/submission_audit/private_review_key.json', 'output/submission_audit/setup_audit.json',
 'output/submission_audit/review_selection.json', 'output/submission_audit/grader_diagnostics.json',
 'output/submission_audit/summary.json',
 'output/native_workflow_01/calibration_private_key.json',
 'output/grader_checks_05/summary.json', 'output/grader_checks_05/quote_format_summary.json',
 'config/judge_robustness_10.json', 'output/judge_robustness_10/ledger.json',
 'output/judge_robustness_10/audited_summary.json',
 'reviews/purchasing_calibration/case-C-7424ebd2-status.json')
FIELDS = ('content_acceptable', 'consequential_error', 'evaluation_defect')
CATEGORIES = {'contract_ambiguity', 'invalid_serialization', 'approval_bypass',
 'unsupported_continuity', 'unsupported_eligibility', 'missing_comparison',
 'page_overflow', 'no_issue', 'insufficient_evidence', 'other',
 'tooling_release_not_gated_on_bridge_supply',
 'provisional_release_omits_required_finance_approval'}
STAGES = {'initial':'native_workflow_01', 'recovery':'native_transport_02',
 'completion':'native_completion_03', 'upload_repair':'native_completion_07',
 'paired':'paired_native_08', 'backoff_probe':'native_backoff_probe_09'}

def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def ratio(n,d): return {'numerator':n,'denominator':d,'value':n/d if d else None}
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def cost_with_robustness(prior, ledger, completion):
    """Add observed phase-10 charges once; unresolved requests are never free."""
    total=0.0
    for entry in ledger:
        value=entry.get('actual_cost_usd')
        if value is not None:
            if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid recorded grader-robustness cost')
            total+=value
    unresolved=sum(entry.get('status')!='actual' or entry.get('actual_cost_usd') is None for entry in ledger)
    return {**prior,
      'previous_snapshot_usd':prior['reported_cumulative_usd'],
      'grader_robustness_usd':total,
      'grader_robustness_unresolved_charge_records':unresolved,
      'reported_cumulative_usd':prior['reported_cumulative_usd']+total,
      'unresolved_charge_records':prior['unresolved_charge_records']+unresolved,
      'scope':'Recorded historical, native and grader stages, including all phase-10 physical requests. Original first-attempt results and later transport recoveries are reported separately. Not a live account balance or reconciled invoice.',
      'grader_robustness_complete':completion.get('complete') is True,
      'excluded_later_phases':[],
      'human_labor_usd':prior.get('human_labor_usd'),
      'cost_per_accepted_deliverable':None}

def load_mapping(root):
    mapping={}
    for rel in ('output/submission_audit/private_review_key.json','output/native_workflow_01/calibration_private_key.json'):
        for item in read(root/rel):
            cid=item['review_id']
            if cid in mapping and mapping[cid]['run_id']!=item['run_id']: raise ValueError('Conflicting case identity: '+cid)
            mapping[cid]={**mapping.get(cid,{}),**item}
    return mapping

def validate_export(doc,mapping):
    if doc.get('schema')!='turing-human-review-v1': raise ValueError('Unsupported human export schema')
    if not isinstance(doc.get('rows'),list): raise ValueError('rows must be a list')
    if not isinstance(doc.get('reviewer_id'),str) or not doc['reviewer_id'].strip(): raise ValueError('Actual reviewer identifier required')
    seen=set();rows=[]
    for row in doc['rows']:
        cid=row.get('review_id')
        if cid not in mapping or cid in seen: raise ValueError('Unknown or duplicated case: '+str(cid))
        seen.add(cid)
        if row.get('human_reviewed') is not True: continue
        if any(row.get(k) not in ('yes','no','uncertain') for k in FIELDS): raise ValueError('Incomplete judgment: '+cid)
        minutes=row.get('review_minutes')
        if minutes is not None and (type(minutes) not in (int,float) or not math.isfinite(minutes) or minutes<0): raise ValueError('Invalid measured review minutes: '+cid)
        if row.get('category') and row['category'] not in CATEGORIES: raise ValueError('Unrecognized taxonomy: '+cid)
        if row['consequential_error']=='yes' and not (str(row.get('output_evidence') or '').strip() and str(row.get('source_and_consequence') or '').strip()): raise ValueError('Consequential error requires source/output/consequence evidence: '+cid)
        rows.append(row)
    return rows

def case_sources(root,record):
    run=record['run_id'];stage=STAGES.get(record.get('native_stage'),'paired_v1')
    paths=[root/'output'/stage/'runs'/(run+'.json')]
    if stage=='paired_v1':
        instance=run.split('__')[0]+'__'+run.split('__')[1]
        paths.append(root/'data/paired_v1/solver'/(instance+'.json'))
        paths += sorted((root/'output/paired_v1/artifacts'/run).glob('*'))
    else:
        raw=read(paths[0]); paths.append(root/'data/evidence_upgrade_01/solver'/(raw['instance_id']+'.json'))
        folder=root/'reviews/calibration_ready_01/files'/record['review_id']
        paths += sorted(p for p in folder.iterdir() if p.is_file())
    if any(not p.is_file() for p in paths): raise ValueError('Missing case source: '+record['review_id'])
    return {p.relative_to(root).as_posix():sha(p) for p in paths if p.is_file()}

def import_review(path,root=ROOT):
    root=Path(root); path=Path(path); doc=read(path); mapping=load_mapping(root)
    rows=validate_export(doc,mapping); digest=sha(path)
    folder=root/'reviews/assignment_final/exports'; folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(digest+'.json'); receipt_path=folder/(digest+'.receipt.json')
    if dest.exists():
        if sha(dest)!=digest or not receipt_path.exists(): raise ValueError('Existing import is incomplete or changed')
        return dest
    receipt={'schema':'human-review-import-receipt-v1','imported_at':now(),'export_sha256':digest,
      'reviewer_id':doc['reviewer_id'],'qualification':doc.get('qualification'),
      'independent_of_author':doc.get('independent_of_author'),
      'case_source_hashes':{r['review_id']:case_sources(root,mapping[r['review_id']]) for r in rows},
      'scope':'Source bytes recorded at import. This does not prove reviewer identity, expertise, independence, or which bytes were read earlier.'}
    with dest.open('xb') as f:f.write(path.read_bytes())
    with receipt_path.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    return dest

def imported_docs(root,mapping):
    documents=[];errors=[];provenance=[]
    for path in sorted((root/'reviews/assignment_final/exports').glob('*.json')):
        if path.name.endswith('.receipt.json'):continue
        try:
            digest=sha(path); receipt=read(path.with_name(path.stem+'.receipt.json'))
            doc=read(path);rows=validate_export(doc,mapping)
            if receipt['export_sha256']!=digest:raise ValueError('Imported export bytes changed')
            if receipt['reviewer_id']!=doc['reviewer_id']:raise ValueError('Reviewer provenance mismatch')
            for row in rows:
                original=receipt['case_source_hashes'].get(row['review_id'])
                if not original or case_sources(root,mapping[row['review_id']])!=original:raise ValueError('Case source snapshot changed: '+row['review_id'])
            documents.append({'sha256':digest,'doc':doc,'rows':rows})
            provenance.append({'path':path.relative_to(root).as_posix(),'sha256':digest,'receipt_path':path.with_name(path.stem+'.receipt.json').relative_to(root).as_posix(),'receipt_sha256':sha(path.with_name(path.stem+'.receipt.json')),'reviewer_id':doc['reviewer_id'],'source_snapshots_verified':True})
        except (ValueError,KeyError,OSError,TypeError) as exc:
            errors.append({'path':path.relative_to(root).as_posix(),'reason':str(exc)})
    return documents,errors,provenance

def resolve_documents(documents):
    """Accept explicit whole-export supersession; never pick the newest by date."""
    by={x['sha256']:x for x in documents}; superseded=set();errors=[];edges={}
    for item in documents:
        doc=item['doc'];old=doc.get('supersedes_export_sha256',[])
        if isinstance(old,str):old=[old]
        if not isinstance(old,list):raise ValueError('supersedes_export_sha256 must be a hash or list')
        edges[item['sha256']]=old
        for digest in old:
            if digest not in by or by[digest]['doc']['reviewer_id']!=doc['reviewer_id']:
                errors.append({'export_sha256':item['sha256'],'reason':'Unknown or other-reviewer supersession'});continue
            superseded.add(digest)
    def visit(node,trail):
        if node in trail:raise ValueError('Cyclic review supersession')
        for prev in edges.get(node,[]):visit(prev,trail|{node})
    for node in edges:visit(node,set())
    invalid={e['export_sha256'] for e in errors}
    # An invalid successor must not deactivate any prior valid export.
    superseded={d for s,ds in edges.items() if s not in invalid for d in ds}
    observations=defaultdict(list)
    for item in documents:
        if item['sha256'] in superseded|invalid:continue
        for row in item['rows']:observations[item['doc']['reviewer_id'],row['review_id']].append((row,item))
    accepted=[];conflicts=[]
    for (reviewer,cid),values in sorted(observations.items()):
        semantic={canonical({k:v for k,v in row.items() if k not in ('updated_at','reviewed_at','saved_at','exported_at')}) for row,_ in values}
        if len(semantic)>1:
            conflicts.append({'reviewer_id':reviewer,'review_id':cid,'reason':'Conflicting exports without explicit supersession','export_sha256':[i['sha256'] for _,i in values]});continue
        row,item=values[0]
        accepted.append({'reviewer_id':reviewer,'qualification':item['doc'].get('qualification'),'independent_of_author':item['doc'].get('independent_of_author'),'row':row,'exports':sorted({i['sha256'] for _,i in values}),'reviewer_metadata_records':[{'qualification':i['doc'].get('qualification'),'independent_of_author':i['doc'].get('independent_of_author')} for _,i in values]})
    return accepted,conflicts,errors

def confusion(rows,mapping,judgments):
    result={}
    for field in ('content_acceptable','consequential_error'):
        cells=Counter();excluded=Counter();families=set()
        for row in rows:
            cid=row['review_id'];meta=mapping[cid]
            if not meta.get('calibration_queue'):continue
            if row['evaluation_defect']!='no':excluded['task_defect_or_uncertain_validity']+=1;continue
            if row[field]=='uncertain':excluded['uncertain_human_label']+=1;continue
            judgment=judgments.get(cid,{})
            if judgment.get('status')!='received':excluded['missing_judge_response']+=1;continue
            a=judgment.get('assessment',{})
            if a.get('status')!='automated_assessment_not_human_acceptance' or type(a.get(field)) is not bool:excluded['invalid_judge_evidence']+=1;continue
            cells[row[field]=='yes',a[field]]+=1;families.add(meta['family_id'])
        tp,fn,fp,tn=(cells[True,True],cells[True,False],cells[False,True],cells[False,False]);n=sum(cells.values())
        out={'comparable':n,'families':len(families),'matrix':{'human_yes_judge_yes':tp,'human_yes_judge_no':fn,'human_no_judge_yes':fp,'human_no_judge_no':tn},'agreement':ratio(tp+tn,n),'exclusions':dict(excluded)}
        pairs=[('yes' if human else 'no','yes' if judge else 'no') for (human,judge),count in cells.items() for _ in range(count)]
        out['agreement_diagnostics']=agreement_diagnostics(pairs)
        if field=='consequential_error':out.update(error_sensitivity=ratio(tp,tp+fn),missed_errors=ratio(fn,tp+fn),false_alarms=ratio(fp,fp+tn))
        else:out.update(false_accepts_among_judge_accepts=ratio(fp,tp+fp),false_rejects_among_human_accepts=ratio(fn,tp+fn))
        result[field]=out
    return result

def case_level_comparisons(rows,mapping,judgments):
    """Expose each reviewed comparison; never backfill invalid or absent grades."""
    result=[]
    for row in rows:
        cid=row['review_id'];metric=confusion([row],mapping,judgments)
        endpoints={}
        for field in ('content_acceptable','consequential_error'):
            eligible=metric[field]['comparable']==1
            excluded=list(metric[field]['exclusions'])
            if not mapping[cid].get('calibration_queue'):excluded=['not_in_original_calibration_queue']
            endpoints[field]={'human_label':row[field],
              'judge_label':('yes' if judgments[cid]['assessment'][field] else 'no') if eligible else None,
              'comparable':eligible,'exclusions':excluded}
        result.append({'review_id':cid,'family_id':mapping[cid]['family_id'],
          'evaluation_defect':row['evaluation_defect'],'endpoints':endpoints,
          'scope':'Individual original-calibration comparison only; not a population accuracy estimate. Invalid, absent and ineligible judgments are not replaced.'})
    return result

def historical_judge_diagnostics(records, scores):
    """Explain the old agreement statistic from its original saved labels.

    Historical v3 judgments did not use the later quote validator. Reproducing
    their label agreement is not retroactive evidence validation. Keep a second
    view excluding the already documented task defects without changing history.
    """
    grouped=defaultdict(dict)
    for record in records:
        kind=record.get('kind')
        if kind not in ('primary','secondary'):continue
        run_id=record.get('run_id')
        if run_id in grouped[kind]:raise ValueError('Duplicate historical judge identity: '+str(run_id))
        grouped[kind][run_id]=record
    primary,secondary=grouped['primary'],grouped['secondary']
    # The planned second-judge sample defines the pair denominator, rather than
    # counting every singly graded primary output as an absent paired result.
    candidates=sorted(secondary)
    known_defects={s['run_id'] for s in scores if s.get('known_task_defect') or s.get('family_id')=='change_control'}
    endpoints={}
    for field in ('content_acceptable','critical_error'):
        pairs=[];valid_pairs=[];included=[];valid_ids=[];excluded=Counter();defects=[]
        for run_id in candidates:
            left,right=primary.get(run_id),secondary[run_id]
            if left is None:excluded['missing_primary_record']+=1;continue
            if left.get('status')!='completed' or right.get('status')!='completed':excluded['incomplete_judge_record']+=1;continue
            a,b=left.get('judgment',{}),right.get('judgment',{})
            if type(a.get(field)) is not bool or type(b.get(field)) is not bool:excluded['non_binary_label']+=1;continue
            pair=('yes' if a[field] else 'no','yes' if b[field] else 'no')
            pairs.append(pair);included.append(run_id)
            if run_id in known_defects or a.get('evaluation_defect') is not False or b.get('evaluation_defect') is not False:
                defects.append(run_id)
            else:
                valid_pairs.append(pair);valid_ids.append(run_id)
        endpoints[field]={**agreement_diagnostics(pairs),'planned_secondary_records':len(candidates),
            'included_case_ids':included,'exclusions':dict(excluded),'known_or_judge_flagged_task_defect_case_ids':defects,
            'task_validity_filtered':{**agreement_diagnostics(valid_pairs),'included_case_ids':valid_ids,'excluded_task_defect_pairs':len(defects)},
            'scope':'Original saved binary label agreement, including documented task defects for faithful reproduction. The separate task-validity-filtered view excludes them. Historical judgments were not revalidated by the phase-10 evidence checker; neither view measures human accuracy.'}
    models={kind:sorted({r.get('judge_model') for r in grouped[kind].values() if r.get('judge_model')}) for kind in ('primary','secondary')}
    return {'raters':{'left':models['primary'],'right':models['secondary']},'endpoints':endpoints,
            'new_human_labels':0,'scope':'Original v3 annotation agreement with full margins and zero cells. Sampled, dependent task variants; no accuracy, independence, self-preference or population claim.'}

def summarize_humans(observations,mapping,judgments):
    by_case=defaultdict(list);by_reviewer=defaultdict(list)
    for item in observations:by_case[item['row']['review_id']].append(item);by_reviewer[item['reviewer_id']].append(item)
    concordant=[];disagreements=[];taxonomy=Counter();tax_exclusions=Counter();confirmed=[]
    for cid,items in sorted(by_case.items()):
        rows=[i['row'] for i in items]
        different=[k for k in FIELDS if len({r[k] for r in rows})>1]
        if different:
            disagreements.append({'review_id':cid,'fields':different,'labels':[{k:i['row'].get(k) for k in ('review_id',*FIELDS,'category')}|{'reviewer_id':i['reviewer_id']} for i in items],'adjudicated_label':None});continue
        row=rows[0];concordant.append(row)
        if not mapping[cid].get('failure_queue') or mapping[cid].get('new_native_queue'):continue
        cats={r.get('category') for r in rows}
        if len(cats)>1:tax_exclusions['category_disagreement']+=1;continue
        cat=row.get('category')
        if not cat:tax_exclusions['unassigned']+=1;continue
        if not all(str(r.get('output_evidence') or '').strip() and str(r.get('source_and_consequence') or '').strip() for r in rows):tax_exclusions['missing_taxonomy_evidence']+=1;continue
        taxonomy[cat]+=1;confirmed.append({'review_id':cid,'family_id':mapping[cid]['family_id'],'category':cat,'category_label':row.get('category_label'),'category_definition':row.get('category_definition'),'category_authorship':row.get('category_authorship'),'evidence_scope_notes':row.get('evidence_scope_notes',[]),'evaluation_defect':row['evaluation_defect'],'consequential_error':row['consequential_error'],'output_evidence':row['output_evidence'],'source_and_consequence':row['source_and_consequence'],'reviewers':[i['reviewer_id'] for i in items],'severity':row.get('severity'),'minimum_repair':row.get('minimum_repair'),'minimum_repair_authorship':row.get('minimum_repair_authorship'),'quantitative_illustration':row.get('quantitative_illustration'),'secondary_issues':row.get('secondary_issues',row.get('secondary_notes')),'human_confirmed_business_error':row['evaluation_defect']=='no' and row['consequential_error']=='yes','scope':'Reviewer classification; not automatic expert validation or evidence of a training-data fix.'})
    outcomes={}
    for cohort,predicate in [('historical',lambda m:not m.get('new_native_queue')),('paired_extension',lambda m:m.get('native_stage')=='paired'),('other_native',lambda m:m.get('new_native_queue') and m.get('native_stage')!='paired')]:
        selected=[r for r in concordant if predicate(mapping[r['review_id']])];eligible=[];excluded=Counter()
        for r in selected:
            m=mapping[r['review_id']]
            if m.get('new_native_queue') and m.get('native_output_status')!='submitted':excluded['not_a_submitted_deliverable']+=1;continue
            if m.get('historical_output_available') is False:excluded['no_output']+=1;continue
            if r['evaluation_defect']!='no':excluded['task_defect_or_uncertain_validity']+=1;continue
            eligible.append(r)
        outcomes[cohort]={'reviewed_concordant':len(selected),'eligible_valid_submissions':len(eligible),'exclusions':dict(excluded),'endpoints':{f:{'counts':dict(Counter(r[f] for r in eligible)),'yes_among_resolved':ratio(sum(r[f]=='yes' for r in eligible),sum(r[f]!='uncertain' for r in eligible))} for f in FIELDS[:2]}}
    per_reviewer=[]
    for reviewer,items in sorted(by_reviewer.items()):
        metadata=[m for i in items for m in i.get('reviewer_metadata_records',[{'qualification':i['qualification'],'independent_of_author':i['independent_of_author']}])]
        variants={k:{canonical(m[k]) for m in metadata} for k in ('qualification','independent_of_author')}
        per_reviewer.append({'reviewer_id':reviewer,**{k:json.loads(next(iter(v))) if len(v)==1 else None for k,v in variants.items()},'metadata_conflicts':{k:[json.loads(x) for x in sorted(v)] for k,v in variants.items() if len(v)>1},'completed_count':len(items),'calibration':confusion([i['row'] for i in items],mapping,judgments)})
    minutes=[i['row'].get('review_minutes') for i in observations]
    return {'completed_count':len(by_case),'review_observations':len(observations),'reviewer_count':len(by_reviewer),'concordant_case_count':len(concordant),'reviewers':per_reviewer,'calibration':{'judge':'google/gemini-4-argon','sample':'Purposive historical calibration queue enriched by earlier judge outcomes; not a prevalence sample.','metrics':confusion(concordant,mapping,judgments),'case_level_comparisons':case_level_comparisons(concordant,mapping,judgments),'disagreement_cases_excluded':len(disagreements),'invalid_responses_never_backfilled':True},'taxonomy':{'planned_candidates':sum(bool(m.get('failure_queue')) and not m.get('new_native_queue') for m in mapping.values()),'native_flagged_candidates_separate':sum(bool(m.get('failure_queue')) and bool(m.get('new_native_queue')) for m in mapping.values()),'manually_categorized_count':sum(taxonomy.values()),'human_confirmed_business_error_count':sum(x['human_confirmed_business_error'] for x in confirmed),'counts':dict(taxonomy),'examples':confirmed,'exclusions':dict(tax_exclusions),'status':'manual_counts_with_source_and_output_evidence' if taxonomy else 'no_completed_evidence_backed_manual_taxonomy','unit':'Distinct reviewed attempts; repeated variants are not independent task families. Category does not establish causal repair or expert validity.'},'outcomes':outcomes,'reviewer_disagreements':disagreements,'review_minutes':{'recorded_total':sum(m for m in minutes if m is not None) if any(m is not None for m in minutes) else None,'missing':sum(m is None for m in minutes),'scope':'One observation per reviewer and case; no imputed review labor or dollar cost.'},'exclusions':{},'pending':['Complete the applicant’s source-and-full-output review and evidence-backed failure taxonomy.','Resolve task-validity and reviewer disagreements; uncertain remains a valid recorded result.'],'no_adjudication_inferred':True}

def summarize_review_plan(root, observations, mapping):
    """Track the selected workload without turning a case count into validity."""
    path=Path(root)/'config/assignment_review_minimal_v1.json'
    if not path.exists():return None
    plan=read(path);ids=plan['case_ids']
    if len(ids)!=len(set(ids)) or len(ids)!=plan['target_case_count']:
        raise ValueError('Review plan has duplicate cases or an inconsistent target')
    if any(cid not in mapping for cid in ids):raise ValueError('Unknown review-plan case')
    anchors=plan.get('headline_issue_case_ids',[])
    if any(cid not in ids for cid in anchors):raise ValueError('Headline issue outside review plan')
    completed={i['row']['review_id'] for i in observations}
    remaining=[cid for cid in ids if cid not in completed]
    by_case=defaultdict(list)
    for item in observations:
        if item['row']['review_id'] in ids:by_case[item['row']['review_id']].append(item['row'])
    pending_findings=[];documented_findings=[];disagreements=[]
    for cid,rows in by_case.items():
        signatures={tuple(row.get(k) for k in (*FIELDS,'category')) for row in rows}
        if len(signatures)>1:disagreements.append(cid)
        requires_finding=any(row['content_acceptable']=='no' or row['consequential_error']=='yes' or row['evaluation_defect']=='yes' for row in rows)
        if not requires_finding:continue
        documented=all(all(str(row.get(k) or '').strip() for k in ('category','output_evidence','source_and_consequence','minimum_repair')) for row in rows)
        (documented_findings if documented else pending_findings).append(cid)
    review_complete=not(remaining or pending_findings or disagreements)
    return {**plan,
      'source_path':path.relative_to(root).as_posix(),'source_sha256':sha(path),
      'completed_case_ids':[cid for cid in ids if cid in completed],
      'completed_case_count':len(ids)-len(remaining),
      'remaining_case_ids':remaining,'remaining_case_count':len(remaining),
      'remaining_core_endpoint_answers':3*len(remaining),
      'core_answer_count_scope':'Three endpoints per incomplete full record; partial-case answers may reduce the actual remaining questions. Issue evidence follow-ups are separate.',
      'source_family_count':len({mapping[cid]['family_id'] for cid in ids}),
      'full_content_reviews_complete':not remaining,
      'documented_finding_case_ids':sorted(documented_findings),
      'pending_finding_case_ids':sorted(pending_findings),
      'unresolved_disagreement_case_ids':sorted(disagreements),
      'human_review_complete':review_complete,
      'headline_issue_disposition':('Current full-output findings have recorded human judgments, evidence, categories and accepted corrections. They form the final claim basis; earlier issue-only judgments remain separate history.' if review_complete else 'Explicit applicant confirmation, revision or withdrawal still required for each retained headline claim; no disposition inferred from a case count.'),
      'assignment_complete_inferred':False,'grader_validated':False}


def build(root=ROOT):
    root=Path(root); old=read(root/'output/paired_v1/summary.json');scores=read(root/'output/paired_v1/scores.json');proto=read(root/'config/paired_protocol.v1.json');current=read(root/'output/current_study_06/summary.json');mapping=load_mapping(root)
    scoreby={r['run_id']:r for r in scores}
    for m in mapping.values():
        if m['run_id'] in scoreby:m['historical_output_available']=scoreby[m['run_id']]['status']=='completed'
    judgments={}
    for p in sorted((root/'output/grader_checks_05/runs').glob('*.json')):
        j=read(p)
        if j.get('cohort')=='historical_calibration':judgments[j['id']]=j
    docs,errors,provenance=imported_docs(root,mapping);observations,duplicates,sup_errors=resolve_documents(docs)
    human=summarize_humans(observations,mapping,judgments)
    review_plan=summarize_review_plan(root,observations,mapping)
    human['exclusions']={'invalid_imports':errors,'ambiguous_reviewer_exports':duplicates,'invalid_supersession':sup_errors};human['import_provenance']=provenance
    human['prior_partial_review']=read(root/'reviews/purchasing_calibration/case-C-7424ebd2-status.json')
    human['prior_issue_only_judgments']={'count':read(root/'output/submission_audit/summary.json')['existing_user_issue_labels'],'labels':['Supplier continuity: material correction required','Approval exception: material correction required'],'scope':'Two project-owner issue-only labels. Not whole-output rejection, expert validation, or a prevalence estimate.'}
    historical={'runs':len(scores),'families':len({r['family_id'] for r in scores}),'occupations':proto['occupations'],'models':proto['models'],'variants_per_family':3,'repeats_per_model_variant':proto['trials_per_system'],'source':'Five public GDPval gold task families, adapted into baseline/recovery/conflict versions; not a standard GDPval leaderboard reproduction.','slice_rationale':'Three purchasing tasks, one project-management task and one shipping task, chosen for inspectable decisions and file deliverables. Purposive and narrow.','parseable_outputs':sum(r['status']=='completed' for r in scores),'structured_passes':sum(r['decision_pass'] for r in scores),'explicit_wrong_targeted_values':sum(r['explicit_wrong'] for r in scores),'missing_outputs':sum(r['status']!='completed' for r in scores),'native_file_scope':'Solver returned a structured JSON artifact specification; local renderer created DOCX/XLSX afterward. Solver could not inspect or revise native files.','artifact_summary':old['artifact_summary'],'model_grading':old['review'],'api_reported_usd':old['total_api_reported_cost_usd'],'documented_defects':[{'family':'ev_localization','affected_attempts':sum(r['known_task_defect'] for r in scores),'description':'Conflict mutation coupled volume and cost basis; excluded post hoc from clean conflict comparison, retained in raw logs.'},{'family':'change_control','affected_attempts':12,'description':'Two-file output contract conflicts with reference request for an Excel tracker; attribution unresolved.'}],'candidate_taxonomy':read(root/'output/submission_audit/taxonomy.json'),'interpretation':'Targeted facts can pass while broader usability/content questions remain. Automated provisional acceptance is not human acceptance.'}
    historical_review_paths=sorted((root/'output/paired_v1/judgments_v3').glob('*.json'))
    historical['model_grading']['measurement_diagnostics']=historical_judge_diagnostics([read(p) for p in historical_review_paths],scores)
    extension={'finished':current['paired_finished_attempts'],'submitted':current['paired_submitted_attempts'],'families':current['paired_families'],'complete_pairs':current['pairs_with_both_submitted'],'mechanical_outcomes':current['paired_mechanical_outcome_counts'],'fixed_model':current['fixed_model'],'contrast':current['actual_pair_contrast'],'source_mix':'Three GDPval derivatives and two constructed fictional families; inspected development data.','engineering_scope':'Native-file mechanics were built and exercised. First live pass failed mainly on provider errors. End-to-end reliability and business acceptance are not established.','human_outcomes':human['outcomes']['paired_extension'],'paired_acceptance_difference':None,'limitations':'Only one complete submitted pair; no model ranking or conflict-effect estimate.'}
    # Keep any usable paired observations visible without estimating a population effect.
    byrun={mapping[i['row']['review_id']]['run_id']:i['row'] for i in observations if mapping[i['row']['review_id']].get('native_stage')=='paired'}
    extension['reviewed_pair_observations']=[]
    disputed={d['review_id'] for d in human['reviewer_disagreements']}
    paired_differences=[]
    for pair in current['pairs']:
        members={}
        for condition,m in pair['members'].items():
            row=byrun.get(m['run_id']);cid=row['review_id'] if row else None
            members[condition]={'submitted':m['native_submitted'],'review_id':cid,'human_label':None if cid in disputed else row,'reviewer_disagreement':cid in disputed}
        labels=[m['human_label'] for m in members.values()]
        eligible=(len(members)==2 and all(m['submitted'] and m['human_label'] and m['human_label']['evaluation_defect']=='no' and m['human_label']['content_acceptable']!='uncertain' for m in members.values()))
        delta=None
        if eligible:
            delta=int(members['conflict']['human_label']['content_acceptable']=='yes')-int(members['baseline']['human_label']['content_acceptable']=='yes')
            paired_differences.append({'family_id':pair['family_id'],'difference':delta})
        extension['reviewed_pair_observations'].append({'family_id':pair['family_id'],'members':members,'acceptance_difference':delta})
    extension['human_comparable_pairs']=len(paired_differences)
    extension['paired_acceptance_difference']={'descriptive_mean':sum(x['difference'] for x in paired_differences)/len(paired_differences),'families':len(paired_differences),'family_differences':paired_differences,'scope':'Descriptive complete-case difference only; selected development families and missing submissions prevent a population/causal claim.'} if paired_differences else None
    imports_ok=not(errors or duplicates or sup_errors)
    ready={'manual_review_started':human['completed_count']>0,'manual_taxonomy_available':human['taxonomy']['manually_categorized_count']>0,'human_judge_comparisons_available':any(m['comparable'] for m in human['calibration']['metrics'].values()),'human_review_complete':False,'assignment_complete':False,'release_status':'Human review pending' if not human['completed_count'] else 'Human reviews imported; manual adjudication and submission review required','imports_valid':imports_ok,'completion_judgment':'Applicant signoff required; no automatic 20/35-label quota or training/freshness gate is imposed.','model_selection_ready':False,'training_ready':False,'remaining_assignment_work':['Applicant hand review and confirmed failure taxonomy','Interpret grader agreement and disagreements with the actual denominators','Final applicant review and live pitch/submission'],'optional_research_expansion':['Independent domain validation','Fresh permissioned families','Training intervention on separate families']}
    source_paths=list(BASE_INPUTS)+[p.relative_to(root).as_posix() for p in sorted((root/'output/grader_checks_05/runs').glob('*.json')) if read(p).get('cohort')=='historical_calibration']
    source_paths += [p.relative_to(root).as_posix() for p in historical_review_paths]
    if review_plan:
        source_paths.append(review_plan['source_path'])
        ready['human_review_complete']=imports_ok and review_plan['human_review_complete']
        if ready['human_review_complete']:
            ready['release_status']='Fixed five-case human review complete; external submission and live presentation not performed'
            ready['completion_judgment']='The selected content reviews and finding documentation are complete. No additional review quota applies; completion does not validate the grader or imply external submission.'
            ready['remaining_assignment_work']=['Submit the prepared deliverables','Present the two lab pitches live']
            human['pending']=[]
        else:
            ready['remaining_assignment_work']=[
              f"Finish the fixed {review_plan['target_case_count']}-case qualitative purchasing review ({review_plan['remaining_case_count']} full records remain); retain uncertainty and rejected flags",
              'Complete evidence-backed finding documentation or report unresolved disagreement; no35-case taxonomy completion required',
              'Submit the prepared deliverables and present the two lab pitches live']
    robustness=read(root/'output/judge_robustness_10/audited_summary.json')
    cost=cost_with_robustness(current['cost'],read(root/'output/judge_robustness_10/ledger.json'),robustness['completion'])
    cost['grader_robustness_first_attempt_usd']=robustness['cost']['first_attempt']['reported_api_cost_usd']
    cost['grader_robustness_recovery_usd']=robustness['cost']['additional_recovery']['reported_api_cost_usd']
    cost['grader_robustness_first_attempt_requests']=robustness['completion']['planned']
    cost['grader_robustness_recovery_requests']=robustness['recovery']['additional_requests']
    cost['grader_robustness_physical_requests']=robustness['recovery']['all_physical_requests']
    ready['grader_robustness_execution_complete']=robustness['completion'].get('complete') is True
    return {'schema':'assignment-evidence-v1','updated_at':now(),'historical':historical,'extension':extension,'human':human,'review_plan':review_plan,'cost':cost,'readiness':ready,'grader_checks':{'summary':read(root/'output/grader_checks_05/summary.json'),'quote_validation':read(root/'output/grader_checks_05/quote_format_summary.json')},'grader_robustness':robustness,'sources':[{'path':rel,'sha256':sha(root/rel)} for rel in source_paths],'scope':'Offline analysis of saved project records. No new API calls or invented human judgments. Source hashes establish file integrity, not scientific validity.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--import-review',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    if args.import_review:print('Imported human export:',import_review(args.import_review,args.root))
    result=build(args.root);dest=args.output or args.root/'output/assignment_final/evidence.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'output':str(dest),'human_completed':result['human']['completed_count'],'manual_taxonomy':result['human']['taxonomy']['manually_categorized_count'],'imports_valid':result['readiness']['imports_valid']}))
if __name__=='__main__':main()
