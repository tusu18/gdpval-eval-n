"""Build the focused assignment handoff from saved evidence; no model calls.

Human outcomes come from assignment_evidence, never from model judgments.
Historical studies stay immutable. The website is the primary submission view;
the one-page PDF is a compact leave-behind, not an independent scored study.
"""
import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/assignment_final/submission'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def esc(value):
    return html.escape(str(value))


def copy(root, relative, dest):
    source = root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def review_plan_text(e):
    """A small review plan is a scope limit, never a validation threshold."""
    plan = e.get('review_plan')
    if not plan:
        return ''
    target = plan['target_case_count']
    complete = plan['completed_case_count']
    remaining = plan['remaining_case_count']
    if e.get('readiness',{}).get('human_review_complete'):
        return (f'Completed qualitative audit: {complete} selected outputs from two purchasing source families, '
                'reviewed by one project owner. Selection was post-hoc and purposive; the reviewer knew the study hypothesis. '
                'These case counts do not estimate population acceptance, model reliability or grader accuracy. '
                'Earlier issue-only judgments remain separate from the completed full-output reviews.')
    return (f'Fixed review set: {target} outputs from two purchasing source families; '
            f'{complete} complete content reviews and {remaining} remaining. '
            'This is a post-hoc qualitative case study, not a statistically validated sample. '
            'Keep accepted, rejected and uncertain judgments; do not replace cases to obtain failures. '
            'The earlier issue-only judgments do not count as full reviews.')


def human_status(e):
    h = e['human']
    count = h['completed_count']
    readiness = e.get('readiness', {})
    # Completion of some records is never silently promoted to completion of
    # the assignment or to qualified independent expert validation.
    status = 'Manual analysis pending' if count == 0 else 'Human review in progress'
    if readiness.get('human_review_complete') is True:
        status = 'Human review complete'
    if count:
        noun = 'output has a complete human content-review record' if count == 1 else 'outputs have complete human content-review records'
        detail = f"{count} distinct {noun}. Reviewer-specific judgments, uncertainty and comparable denominators are in the evidence record."
        detail += ' These are extracted-text judgments; native-file usability and page-length compliance remain unverified by the reviewer. This selected sample cannot establish grader accuracy.'
    else:
        detail = 'No complete full-output human reviews are recorded. Two earlier issue-only judgments remain separate; the taxonomy and automated grades are provisional.'
    return status, detail


def reviewed_counts(e):
    endpoints=e['human'].get('outcomes',{}).get('historical',{}).get('endpoints',{})
    acceptable=endpoints.get('content_acceptable',{}).get('counts',{})
    errors=endpoints.get('consequential_error',{}).get('counts',{})
    return {'reviewed':e['human']['completed_count'],'acceptable':acceptable.get('yes',0),
            'correction':acceptable.get('no',0),'consequential':errors.get('yes',0),
            'uncertain':acceptable.get('uncertain',0)}


def reviewed_result_text(e):
    c=reviewed_counts(e)
    return (f"The reviewer accepted {c['acceptable']} of {c['reviewed']} selected outputs without substantive correction "
            f"and marked {c['correction']} as requiring correction. {c['consequential']} received a consequential-error label. "
            "These are counts within the reviewed case set, not population rates.")


def reviewed_judge_text(e):
    cases=e['human'].get('calibration',{}).get('case_level_comparisons',[])
    eligible=[c for c in cases if all(c['endpoints'][k].get('comparable') for k in ('content_acceptable','consequential_error'))]
    agreements=sum(all(c['endpoints'][k]['human_label']==c['endpoints'][k]['judge_label'] for k in ('content_acceptable','consequential_error')) for c in eligible)
    missed=[c['review_id'] for c in eligible if c['endpoints']['consequential_error']['human_label']=='yes' and c['endpoints']['consequential_error']['judge_label']=='no']
    false_accepts=[c['review_id'] for c in eligible if c['endpoints']['content_acceptable']['human_label']=='no' and c['endpoints']['content_acceptable']['judge_label']=='yes']
    both=sorted(set(missed)&set(false_accepts))
    detail=(f" {', '.join(both)} was both a false accept and a missed consequential error relative to the human review." if both else '')
    return (f"The original judge is comparable on {len(eligible)} reviewed outputs; {agreements} agree with the human on both outcomes."
            +detail+f" {len(cases)-len(eligible)} reviewed outputs lack an eligible original-judge comparison; missing judgments are not backfilled. "
            "This is a diagnostic disagreement record, not a validated accuracy or sensitivity estimate.")


def illustrative_transcript_review_text(e):
    reviewed={row['review_id'] for row in e['human'].get('calibration',{}).get('case_level_comparisons',[])}
    if 'C-5304f72e' in reviewed:
        return ('Case 1 (C-5304f72e) now has a complete extracted-text content review and a documented tooling-release finding. '
                'Its earlier buffer-stock issue-only judgment remains separate history. Cases 2 and 3 remain unreviewed candidates. '
                'Native-file appearance and page compliance are not established by the content review.')
    return ('Only case 1 has the earlier issue-specific owner judgment; its whole-output content review is not recorded here. '
            'Cases 2 and 3 remain unreviewed candidates.')


def submission_trace_index(root,e):
    """Annotate the handoff copy while preserving the frozen historical index."""
    relative='output/anthropic_defense/trace_index.json'
    source=root/relative
    index=read(source)
    current={row['review_id']:row for row in e['human'].get('calibration',{}).get('case_level_comparisons',[])}
    findings={row['review_id']:row for row in e['human'].get('taxonomy',{}).get('examples',[])}
    index['source_provenance']={'path':relative,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'transformation':'Submission annotations incorporate current content reviews; the source index and raw-run hashes remain unchanged.'}
    index['current_evidence_snapshot']=e['updated_at']
    for case in index['cases']:
        row=current.get(case['review_id'])
        if row is None:
            continue
        case['historical_review_annotation']={key:case.get(key) for key in ('judgment_status','whole_output_human_reviewed')}
        labels={key:value['human_label'] for key,value in row['endpoints'].items()}
        case['whole_output_human_reviewed']=True
        case['whole_output_review_scope']='Complete extracted text; native-file appearance and page compliance remain unverified.'
        case['judgment_status']=('Complete extracted-text content review is recorded in current evidence. '
            f"Content acceptable: {labels.get('content_acceptable')}; consequential error: {labels.get('consequential_error')}. "
            'The earlier issue-only annotation is retained as history; native-file appearance and page compliance remain unverified.')
        finding=findings.get(case['review_id'],{})
        case['current_content_review']={'evaluation_defect':row.get('evaluation_defect'),**labels,
            'category':finding.get('category'),'minimum_repair':finding.get('minimum_repair'),
            'evidence_scope_notes':finding.get('evidence_scope_notes',[]),
            'native_visual_review_status':'not_established_by_content_review'}
    return index


def selected_fact_check_context(root,e):
    """Trace the selected-case headline to its original run-level checks."""
    ids=(e.get('review_plan') or {}).get('case_ids',[])
    mapping={row['review_id']:row for row in read(root/'output/submission_audit/private_review_key.json')}
    scores={row['run_id']:row for row in read(root/'output/paired_v1/scores.json')}
    rows=[]
    for cid in ids:
        score=scores[mapping[cid]['run_id']]
        rows.append({'review_id':cid,'run_id':score['run_id'],'parseable':score['status']=='completed',
                     'narrow_fact_pass':score['decision_pass'] is True,'known_task_defect':bool(score['known_task_defect'])})
    return {'selected':len(rows),'parseable':sum(x['parseable'] for x in rows),
            'passed':sum(x['narrow_fact_pass'] for x in rows),'cases':rows,
            'scope':'Original targeted fact checks only; not full output acceptance or professional correctness.'}


def evaluation_record_html(record):
    """Expose the original experiment without merging later native extensions."""
    inventory=[];changes=[]
    for task in record['selection']:
        coverage='Included in the five-output human case study' if task['human_case_study_included'] else 'Automated study only'
        inventory.append('<tr><td><strong>'+esc(task['task_name'])+'</strong><br><code>'+esc(task['family_id'])+'</code><br><span class="small">'+esc(coverage)+'</span></td><td>'+esc(task['source_task_id'])+'</td><td>'+esc(task['occupation'])+'</td><td>'+esc(task['deliverable'])+'</td><td>'+esc(task['why_selected'])+'</td></tr>')
        v=task['variant_changes']
        inputs=' / '.join('<a href="code/'+esc(path)+'">'+esc(path.rsplit('__',1)[-1].removesuffix('.json'))+'</a>' for path in task['solver_inputs'])
        changes.append('<tr><td>'+esc(task['task_name'])+'<br><span class="small">Changed location: '+esc(v['location'])+'</span><br>'+inputs+'</td><td>'+esc(v['baseline'])+'</td><td>'+esc(v['recovery'])+'</td><td>'+esc(v['conflict'])+'</td><td><strong>Operative:</strong> '+esc(v['operative_record'])+'<br><strong>Unapproved draft:</strong> '+esc(v['unapproved_draft'])+'</td></tr>')
    def field_rows(values):
        rows=[]
        for key,value in values.items():
            rendered=', '.join(str(x) for x in value) if isinstance(value,list) else str(value)
            rows.append('<tr><th>'+esc(key.replace('_',' '))+'</th><td>'+esc(rendered)+'</td></tr>')
        return ''.join(rows)
    result='<details><summary>Exact task inventory, modifications, run settings and grading</summary>'
    result+='<p>This record describes the original 60-attempt experiment. The five-output human case study and later native-file extension retain their separate scopes.</p>'
    result+='<div class="tablewrap"><table><thead><tr><th>Task family</th><th>GDPval source task ID</th><th>Occupation</th><th>Study deliverable</th><th>Selection reason</th></tr></thead><tbody>'+''.join(inventory)+'</tbody></table></div>'
    result+='<p><strong>Selection limits:</strong></p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in record['selection_limits'])+'</ul>'
    result+='<p><strong>Common changes to the original inputs:</strong></p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in record['common_input_changes'])+'</ul>'
    result+='<div class="tablewrap"><table><thead><tr><th>Modified location and solver packets</th><th>Baseline wording</th><th>Recovery wording</th><th>Conflict wording</th><th>Workspace records</th></tr></thead><tbody>'+''.join(changes)+'</tbody></table></div>'
    result+='<p><strong>Saved protocol and implementation provenance:</strong> protocol and per-run input hashes match. Exact historical runner bytes have not been recovered; retained implementation details are qualified below.</p><div class="tablewrap"><table><tbody>'+field_rows(record['method'])+'</tbody></table></div>'
    result+='<p><strong>How the outcomes were graded:</strong></p><div class="tablewrap"><table><tbody>'+field_rows(record['grading'])+'</tbody></table></div>'
    result+='<p><a href="supporting/evaluation-record.json">Complete evaluation record, 60 attempt traces and source hashes</a> / <a href="code/data/paired_v1/selection_audit.json">Original selection audit</a> / <a href="code/config/paired_protocol.v1.json">Frozen protocol</a>.</p></details>'
    return result


def data_opportunity_html(record):
    rows=[]
    for opportunity in record['data_opportunities']:
        rows.append('<tr><td><strong>'+esc(opportunity['category'])+'</strong><p>'+esc(opportunity['observed_failure'])+'</p></td><td>'+esc(opportunity['capability_hypothesis'])+'</td><td>'+esc(opportunity['proposed_data'])+'</td><td>'+esc(opportunity['future_test'])+'<p class="small">'+esc(opportunity['status'])+'</p></td></tr>')
    return '<section><h2>From a reviewed failure to a testable data proposal</h2><p>These are capability hypotheses and proposed interventions, not demonstrated training improvements. The fresh-family test must measure useful authorized action as well as errors.</p><div class="tablewrap"><table><thead><tr><th>Observed in reviewed outputs</th><th>Capability hypothesis</th><th>Proposed data</th><th>Fresh held-out test</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p><strong>Repair these before attributing a gap to data:</strong></p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in record['non_training_fixes_first'])+'</ul></section>'


def evaluation_record_pitch(record):
    if not record:return ''
    tasks='\n'.join(f"- {x['task_name']} ({x['occupation']}): {x['deliverable']}. Source task ID: {x['source_task_id']}." for x in record['selection'])
    methods=record['method']
    mappings='\n\n'.join(f"{x['category']}\nCapability hypothesis: {x['capability_hypothesis']}\nProposed data: {x['proposed_data']}\nFresh held-out test: {x['future_test']}\nStatus: {x['status']}" for x in record['data_opportunities'])
    return f"""\nEXACT EVALUATION RECORD AND DATA-TEST MAP
{tasks}

Design: {methods['design']}
Models: {', '.join(methods['models'])}. Reasoning effort: {methods['reasoning_effort']}; maximum {methods['max_completion_tokens_per_call']} completion tokens per call and {methods['max_calls_per_run']} calls per run. Temperature: {methods['temperature']} Seed: {methods['generation_seed']}
Tools: {', '.join(methods['tools'])}; {methods['tool_access']}. {methods['output_workflow']}
Code provenance: {methods['code_provenance']}
All variants already expose the approved and unapproved records. Recovery replaces a bounded fact with a workspace pointer; conflict substitutes the draft value and adds draft-derived notes. The exact replacements, source IDs, grader layers, attempt costs and raw-file links are in supporting/evaluation-record.json and the website's expanded inventory.

{mappings}
"""


def prepare_strengthening_supplement(root, out):
    """Keep new offline diagnostics separate from the human headline."""
    from build_strengthening_13 import build as build_supplement, render_html
    from audit_lossless_quotes_13 import build as build_lossless, render_html as render_lossless
    result=build_supplement(root);lossless=build_lossless(root)
    folder=root/'output/strengthening_13';folder.mkdir(parents=True,exist_ok=True)
    write(folder/'evidence-reconciliation.json',result)
    write(folder/'lossless-audit.json',lossless)
    (folder/'lossless-audit.html').write_text(render_lossless(lossless))
    inspection_path=folder/'inspection-summary.json'
    inspection=read(inspection_path) if inspection_path.is_file() else None
    (folder/'index.html').write_text(render_html(result,lossless,inspection,packaged=False))
    target=out/'supporting/strengthening-13';target.mkdir(parents=True,exist_ok=True)
    for name in ('evidence-reconciliation.json','lossless-audit.json','lossless-audit.html','inspection-summary.json'):
        if (folder/name).is_file():shutil.copyfile(folder/name,target/name)
    (target/'index.html').write_text(render_html(result,lossless,inspection,packaged=True))
    a=lossless['original_attempts'];q=result['queue_audit']
    panel=f'''<details><summary>New supporting checks: preserve quoted evidence and reconcile automated flags</summary><p>The raw primary robustness result remains {a['raw_primary_scorable']}/{a['attempts']} attempts meeting evidence checks. The historical secondary parser made {a['frozen_secondary_scorable']} scorable while discarding {a['frozen_discarded_value_segments']} quoted value segments. A strict lossless method makes {a['lossless_secondary_scorable']} scorable and discards {a['lossless_discarded_value_segments']}. This is an offline measurement-interface repair, not an accuracy or reasoning improvement.</p><p>Of {q['automated_candidates']} archived automatic flags, {q['completed_content_reviews_in_queue']} have human content reviews: three documented content findings and one content-accepted output whose page flag remains separate. {q['unreviewed_candidates']} candidates remain unreviewed. The original five-case finding counts are unchanged.</p><p>The four-artifact inspection pilot has a separate status record and new human reviews. Local smoke checks do not constitute a live judge experiment; incomplete reviews remain pending.</p><p><a href="supporting/strengthening-13/index.html">Evidence supplement, inspection readiness and metric definitions</a></p></details>'''
    defense=f'''\nSUPPORTING DIAGNOSTICS — WHAT CHANGED AND WHAT DID NOT
The offline quote audit preserves raw primary results: {a['raw_primary_scorable']}/{a['attempts']} original attempts meet raw checks. Historical first-segment normalization makes {a['frozen_secondary_scorable']} scorable while discarding {a['frozen_discarded_value_segments']} value segments; strict lossless validation makes {a['lossless_secondary_scorable']} scorable and discards none. Later recoveries are reported separately. This is an evidence-interface repair, not better model reasoning or human accuracy.
The archived queue of 35 flags overlaps four completed human content reviews. Three have documented content findings; one is content-accepted with an unadjudicated native-page flag. 31 remain unreviewed. Automated flags never become human-confirmed failures by counting them.
The next four-artifact inspection pilot compares extraction, fixed inspection evidence and adaptive inspection. Human control reviews and execution readiness remain separate from the completed original five-case review. A dry run is not a model result. The older 40-request schedule is deferred; no automatic combined campaign is proposed. See supporting/strengthening-13/index.html for exact current readiness and metrics.
'''
    return panel,defense


def human_html(e):
    """Render measured human counts; zero comparable observations means unknown."""
    h=e['human'];metrics=h.get('calibration',{}).get('metrics',{})
    case_rows=[]
    for case in h.get('calibration',{}).get('case_level_comparisons',[]):
        for key,label in [('content_acceptable','Content acceptable'),('consequential_error','Consequential error')]:
            endpoint=case['endpoints'][key]
            exclusions=endpoint.get('exclusions') or []
            eligibility='Comparable' if endpoint.get('comparable') else 'Excluded: '+', '.join(exclusions)
            case_rows.append('<tr><td>'+esc(case['review_id'])+'</td><td>'+esc(label)+'</td><td>'+esc(endpoint.get('human_label'))+'</td><td>'+esc(endpoint.get('judge_label') if endpoint.get('judge_label') is not None else 'Unavailable / invalid')+'</td><td>'+esc(eligibility)+'</td></tr>')
    html_='<p>Only completed human records are shown. A missing or invalid judge label is not replaced with another judge or a later run.</p>'
    html_+='<div class="tablewrap"><table><thead><tr><th>Reviewed case</th><th>Judgment</th><th>Human</th><th>Original judge</th><th>Comparison eligibility</th></tr></thead><tbody>'+''.join(case_rows)+'</tbody></table></div>' if case_rows else '<p>No case-level comparisons are available.</p>'
    rows=[]
    for key,label in [('content_acceptable','Acceptance judgments'),('consequential_error','Consequential-error judgments')]:
        m=metrics.get(key,{})
        a=m.get('agreement',{});n=m.get('comparable',0)
        agreement=f"{a.get('numerator',0)}/{a.get('denominator',0)}" if a.get('denominator') else 'Unmeasured'
        rows.append(f'<tr><td>{label}</td><td>{n}</td><td>{agreement}</td><td>{m.get("families",0)}</td></tr>')
    aggregate='<div class="tablewrap"><table><thead><tr><th>Human-judge comparison</th><th>Comparable cases</th><th>Agreement count</th><th>Source families</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    tax=h.get('taxonomy',{});counts=tax.get('counts',{})
    html_+=f'<p>{tax.get("manually_categorized_count",0)} imported cases have evidence-backed manual primary labels. These labels can include no issue or insufficient evidence; classified does not mean confirmed failure. Historical and native-extension cohorts remain separate in the evidence record.</p>'
    finding_families={item['family_id'] for item in tax.get('examples',[])}
    if tax.get('examples'):
        family_word='family' if len(finding_families)==1 else 'families'
        html_+=f'<p>These {len(tax["examples"])} classified outputs come from {len(finding_families)} source {family_word}. Multiple outputs from the same family are related observations, not independent demonstrations across occupations.</p>'
    if counts:
        labels={item['category']:item.get('category_label') or item['category'].replace('_',' ') for item in tax.get('examples',[])}
        html_+='<ul>'+''.join(f'<li>{esc(labels.get(k,k.replace("_"," ")))}: {v}</li>' for k,v in sorted(counts.items()))+'</ul>'
    for finding in tax.get('examples',[]):
        label=finding.get('category_label') or finding['category'].replace('_',' ')
        html_+=f'<article class="card"><div class="label">Recorded applicant finding / {esc(finding["review_id"])}</div><h3>{esc(label)}</h3><p><strong>Reviewer definition:</strong> {esc(finding.get("category_definition") or "Not separately supplied")}</p><p><strong>Severity:</strong> {esc(finding.get("severity") or "Not supplied")}</p>'
        html_+='<p><strong>Source and output evidence:</strong></p><pre>'+esc(finding['output_evidence'])+'</pre><p><strong>Reviewer reasoning:</strong></p><pre>'+esc(finding['source_and_consequence'])+'</pre>'
        html_+='<p><strong>Accepted minimum correction:</strong> '+esc(finding.get('minimum_repair') or 'Not yet supplied or confirmed')+'</p>'
        if finding.get('quantitative_illustration'):
            html_+=quantitative_illustration_html(finding['quantitative_illustration'])
        for note in finding.get('evidence_scope_notes',[]):
            html_+='<p class="small">'+esc(note)+'</p>'
        html_+='<p class="small">'+esc(finding.get('scope','Reviewer finding; not independent expert validation or a demonstrated repair effect.'))+'</p></article>'
    html_+='<p>These are descriptive case comparisons, not validated grader accuracy, sensitivity, population acceptance or occupational error rates. Source validity, uncertainty, invalid judge evidence and reviewer disagreement can reduce the comparable denominator. No reviewer disagreement is averaged into a gold label.</p>'
    html_+='<details><summary>Technical appendix: aggregate counts and agreement diagnostics</summary>'+aggregate
    for key,label in [('content_acceptable','Human / judge acceptance'),('consequential_error','Human / judge consequential-error flags')]:
        diagnostic=metrics.get(key,{}).get('agreement_diagnostics')
        if diagnostic:
            html_+=agreement_html(label,diagnostic,'Human','Judge')
    html_+='</details>'
    return html_


def quantitative_illustration_html(q):
    """Keep a conditional calculation adjacent to all its saved assumptions."""
    low,high=q['conditional_uncovered_sets']
    html_=f'<div class="notice"><p><strong>{esc(q["label"])}:</strong> {low:,}-{high:,} sets uncovered under the conditions below.</p>'
    html_+='<p><strong>Conditions:</strong></p><ul>'+''.join('<li>'+esc(c)+'</li>' for c in q['conditions'])+'</ul>'
    html_+='<div class="tablewrap"><table><thead><tr><th>Conditional quantity</th><th>Sets</th></tr></thead><tbody>'
    for label,key in [('Production during all first 21 days','production_first21days_sets'),('Demand consumed during first 21 days','consumption_first21days_sets'),('Buffer remaining at day 21','buffer_at_day21_sets')]:
        html_+=f'<tr><td>{esc(label)}</td><td>{q[key]:,}</td></tr>'
    gap_low,gap_high=q['gap_demand_sets']
    html_+=f'<tr><td>Demand during the output-stated post-day-21 gap</td><td>{gap_low:,}-{gap_high:,}</td></tr><tr><td>Conditional demand without coverage</td><td>{low:,}-{high:,}</td></tr></tbody></table></div>'
    for key in ('stock_sensitivity','build_ahead_sensitivity','scope'):
        html_+='<p>'+esc(q[key])+'</p>'
    return html_+'</div>'


def manual_finding_brief(e):
    """One illustrative saved finding, with the reviewer's explicit condition."""
    examples=e['human'].get('taxonomy',{}).get('examples',[])
    if not examples:return ''
    # Prefer a saved explicit reviewer definition for the short illustration;
    # every classified output remains separately visible on the website.
    finding=next((item for item in examples if item.get('category_definition')),examples[0])
    families=len({item['family_id'] for item in examples})
    family_word='family' if families==1 else 'families'
    output_word='output' if len(examples)==1 else 'outputs'
    label=finding.get('category_label') or finding['category'].replace('_',' ')
    notes=finding.get('evidence_scope_notes',[])
    scope=notes[0] if notes else finding.get('scope','Reviewer finding, not independent expert validation.')
    return (f"{len(examples)} classified {output_word} across {families} source {family_word}; related outputs are not independent task families. "
            f"Illustrative full-output finding, {finding['review_id']}: {label}. "
            f"Reviewer definition: {finding.get('category_definition') or 'See the source/output evidence'}. "
            f"Severity: {finding.get('severity') or 'Not supplied'}. "
            f"Scope: {scope} "
            f"Accepted correction: {(finding.get('minimum_repair') or 'Not yet confirmed').rstrip('.')}. "
            "This correction has not been tested in a repair run.")


def earlier_issue_scope(e):
    """Do not silently promote an earlier issue-only label to the primary finding."""
    completed=set((e.get('review_plan') or {}).get('completed_case_ids',[]))
    examples=e['human'].get('taxonomy',{}).get('examples',[])
    tooling=any(x['review_id']=='C-5304f72e' and x['category']=='tooling_release_not_gated_on_bridge_supply' for x in examples)
    continuity=('The continuity document now has a full review with tooling-release gating as its primary finding; the earlier buffer-stock judgment remains separate. '
                if tooling else 'The complete-document continuity review remains separate from the earlier buffer-stock issue-only judgment. ')
    approval=('The approval document\'s full review is reported separately. ' if 'C-4f3f9946' in completed else 'The approval document is still pending. ')
    return continuity+approval


def ratio_text(value):
    """Unknown denominators remain unmeasured, never a reassuring zero rate."""
    if not value or not value.get('denominator'):
        return 'Unmeasured'
    return f"{value['numerator']}/{value['denominator']}"


def agreement_html(title, diagnostic, left_name='First judge', right_name='Second judge'):
    """Show every contingency cell and prevalence alongside descriptive kappa."""
    cells=diagnostic.get('full_matrix',[])
    labels=diagnostic.get('label_order') or list(dict.fromkeys([c['left'] for c in cells]+[c['right'] for c in cells]))
    counts={(c['left'],c['right']):c['count'] for c in cells}
    matrix=''.join('<tr><th>'+esc(left)+'</th>'+''.join(f'<td>{counts.get((left,right),0)}</td>' for right in labels)+'</tr>' for left in labels)
    frequencies=diagnostic.get('label_frequencies',{})
    freq='; '.join(esc(name)+': '+', '.join(esc(label)+' '+str(frequencies.get(side,{}).get(label,0)) for label in labels) for side,name in [('left',left_name),('right',right_name)])
    kappa=diagnostic.get('cohen_kappa',{});value=kappa.get('value')
    kappa_text=f'{value:.3f}' if value is not None else ('Undefined' if kappa.get('status')=='degenerate_marginals' else 'Not reported')
    warnings=kappa.get('warnings',[])
    caution='; '.join(str(x).replace('_',' ') for x in warnings)
    status=str(kappa.get('status','not_available')).replace('_',' ')
    binary=''
    if 'positive_agreement' in diagnostic:
        positive=diagnostic.get('positive_label','yes');negative=diagnostic.get('negative_label','no')
        binary=f" Label-specific agreement ({esc(positive)}): {ratio_text(diagnostic['positive_agreement'])}; ({esc(negative)}): {ratio_text(diagnostic['negative_agreement'])}."
    return f'''<article class="card"><h3>{esc(title)}</h3><p class="small">Rows: {esc(left_name)}. Columns: {esc(right_name)}. All cells, including zero counts, are shown.</p><div class="tablewrap"><table><thead><tr><th>Label</th>{''.join('<th>'+esc(x)+'</th>' for x in labels)}</tr></thead><tbody>{matrix}</tbody></table></div><p>{freq}.</p><p>Observed agreement: {ratio_text(diagnostic.get('observed_agreement'))}. Cohen's kappa: {kappa_text} ({esc(status)}).{binary}</p><p class="small">{esc(caution)}. These are descriptive agreement diagnostics, not accuracy or independent human validation. Repeated outputs and variants may share source families.</p></article>'''


def measurement_html(e, root):
    """Separate observed agreement from proposed interventions and human truth."""
    historical=e.get('historical',{}).get('model_grading',{}).get('measurement_diagnostics',{})
    cards=[]
    for key,label in [('content_acceptable','Historical acceptance judgments'),('critical_error','Historical consequential-error judgments')]:
        entry=historical.get('endpoints',{}).get(key)
        if entry:
            cards.append(agreement_html(label+' - original descriptive cohort',entry,'Primary judge','Secondary judge'))
            if entry.get('task_validity_filtered'):
                cards.append(agreement_html(label+' - known task-defect pairs excluded',entry['task_validity_filtered'],'Primary judge','Secondary judge'))
    r=e['grader_robustness']
    family_comparison=r['family']['historical']
    reword_comparisons=[r['sensitivity']['comparisons'][v] for v in ('v1_reword','v2_reword','v3_reword') if v in r['sensitivity']['comparisons']]
    reword_n=sum(c.get('comparable',0) for c in reword_comparisons)
    reword_changed=sum(c.get('changed',0) for c in reword_comparisons)
    changed=family_comparison.get('changed',0);comparable=family_comparison.get('comparable',0)
    comparisons=[('Different judge families, historical outputs',r['family']['historical'])]
    comparisons += [(v.replace('_',' '),c) for v,c in r['sensitivity']['comparisons'].items()]
    comparisons.append(('Selected injection controls',r['injection']['comparison']))
    for label,entry in comparisons:
        if entry.get('agreement_diagnostics'):
            cards.append(agreement_html(label,entry['agreement_diagnostics'],'Original judge','Comparison judge'))
    controls=root/'config/judge_controls_11.proposed.json'
    extra=''
    if controls.exists():
        extra='''<p><strong>Prepared, NOT RUN:</strong> eight complete authored memos from two professional-document families. Each family includes a supported decision, a contradictory action beside a correct rule, a harmless wording/style change that preserves that error, and a useful conditional plan. The proposed 40-request single-judge comparison includes three original-prompt attempts, one rewording and one separate self-review per memo; zero requests have run. Author expectations remain separate from judge inputs and require human review.</p><p>Measure recovered errors, new false alarms, invalid and uncertain judgments, and added time/cost separately. Self-review adds a second inference step as well as reflection instructions, so any improvement would not isolate reflection from extra compute. A rendered/native-file comparison has not been prepared or run in this extension. No ensemble weights or accuracy gains have been estimated.</p><p><a href="measurement-controls/index.html">Blinded controlled cases for review</a> / <a href="code/config/judge_controls_11.proposed.json">Proposed comparison protocol</a>.</p>'''
    literature=''
    if (root/'output/measurement_update_11/literature-review.html').exists():
        literature='<p><a href="supporting/literature-review.html">Paper verification and project application</a>. Literature motivates controls; its published results are not project evidence.</p>'
    return f'''<section><h2>Test the judge as a measurement tool</h2><p>Stable decisions do not establish correct decisions. The {reword_changed}/{reword_n} eligible rewording comparisons reuse outputs and lack repeated-original-prompt controls. Their baseline labels are visible below. The {comparable} eligible cross-judge cases contain {changed} disagreements; eligible cases must not all be called disputed outputs. No human-calibrated accuracy estimate follows.</p><details><summary>Full confusion matrices, label frequencies and agreement diagnostics</summary><p>The historical tables reproduce the original v3 judge cohort and separately exclude its known task-defect pairs. They do not retroactively acquire the later quote-evidence validation. Positive/negative agreement uses twice the shared cell over the sum of both judges' corresponding label counts.</p>'''+''.join(cards)+'''</details>'''+extra+literature+'''</section>'''


def comparison_fraction(comparison):
    n=comparison['comparable']
    return f"{comparison['changed']}/{n}" if n else 'unmeasured (0 comparable)'


def robustness_brief(e):
    """Only raw-valid comparisons enter claims; normalized scores stay secondary."""
    r=e['grader_robustness'];done=r['completion'];raw=r['raw']
    comparisons=r['sensitivity']['comparisons']
    reword={'comparable':sum(comparisons[v]['comparable'] for v in ('v1_reword','v2_reword','v3_reword')),
            'changed':sum(comparisons[v]['changed'] for v in ('v1_reword','v2_reword','v3_reword'))}
    recovery=r.get('recovery',{})
    recovery_note=(f" {recovery['additional_requests']} later recovery calls are separate from primary comparisons." if recovery.get('additional_requests') else '')
    return (f"Grader robustness (original attempts): {done['received']}/{done['planned']} responses; {raw['format_valid']}/{done['received']} passed raw evidence-format checks. "
            f"Verdicts changed in {comparison_fraction(reword)} eligible rewording comparisons, "
            f"{comparison_fraction(comparisons['v4_bias_aware'])} bias-aware comparisons, and "
            f"{comparison_fraction(r['injection']['comparison'])} selected injection comparisons. "
            f"Different judge families disagreed on {comparison_fraction(r['family']['historical'])} eligible historical cases. "
            "Rewording comparisons lack repeated-original-prompt controls. These are dependent diagnostic comparisons, not grader accuracy."+recovery_note)


def recovery_html(r):
    recovery=r.get('recovery',{})
    if not recovery.get('additional_requests'):
        return ''
    additional=recovery['additional_raw'];final=recovery['final_logical_raw']
    return f'''<details><summary>Later recovery supplement - original failures preserved</summary><p>Five previously failed jobs were retried before this measurement update. The {recovery['additional_requests']} additional requests returned {additional['received']} responses; {additional['raw_scorable']} passed raw evidence checks and {additional['received']-additional['raw_scorable']} did not. There are {recovery['all_physical_requests']} physical requests in total and {recovery['final_logical_requests']} logical jobs; the final available responses include {final['raw_scorable']} raw-scorable judgments.</p><p>These recoveries do not replace the original-attempt comparisons above. The five original error records and original ledger were recovered from the previously sealed archive, with hashes preserved. The recovery calls add ${recovery['reported_additional_cost_usd']:.7f}; cost includes them once. The work in this measurement update made no paid calls.</p><p><a href="code/output/judge_robustness_10/first_attempts/manifest.json">Original-attempt provenance and recovery record hashes</a>. The source archive hash is recorded; an independent copy of that earlier archive is retained in the project history.</p></details>'''


def robustness_html(e):
    r=e['grader_robustness'];done=r['completion'];raw=r['raw']
    descriptions={
      'v1_reword':'Rewording 1', 'v2_reword':'Rewording 2',
      'v3_reword':'Rewording 3', 'v4_bias_aware':'Added failure-pattern guidance'}
    rows=[]
    for variant,label in descriptions.items():
        comparison=r['sensitivity']['comparisons'][variant]
        scope='Meaning-preserving instruction rewording' if variant!='v4_bias_aware' else 'Different guidance; not a meaning-preserving rewording'
        rows.append(f'<tr><td>{label}</td><td>{comparison["comparable"]}</td><td>{esc(comparison_fraction(comparison))}</td><td>{scope}</td></tr>')
    family=r['family']['historical'];injection=r['injection']['comparison']
    rows.append(f'<tr><td>Different judge family, same historical packet</td><td>{family["comparable"]}</td><td>{esc(comparison_fraction(family))}</td><td>Agreement is not validity; human-reference coverage is limited to the separately reported completed reviews.</td></tr>')
    rows.append(f'<tr><td>Injected artifact instructions</td><td>{injection["comparable"]}</td><td>{esc(comparison_fraction(injection))}</td><td>Eight planned perturbations of four selected constructed packets.</td></tr>')
    fixtures=[]
    for model,label in [('gemini_original','Original Gemini judge'),('sol_v0','GPT judge, same instructions')]:
        fixture=r['family']['constructed'][model];groups=fixture['groups'];critical=fixture['critical_error_checks']
        total=sum(g['binary_comparable'] for g in groups.values());matches=sum(g['matches_author_expectation'] for g in groups.values())
        unknown=sum(g['unknown_invalid_or_unreceived'] for g in groups.values())
        matched=f'{matches}/{total}' if total else 'Unmeasured'
        detected=f"{critical['detected']}/{critical['binary_comparable']}" if critical['binary_comparable'] else 'Unmeasured'
        fixtures.append(f'<tr><td>{label}</td><td>{matched}</td><td>{unknown}</td><td>{detected}</td></tr>')
    norm=r['normalization']['new_batch'];old_norm=r['normalization']['original_historical']
    return f'''<section><h2>Grader robustness: what changed the verdict?</h2>
<p>Original-attempt analysis: {done['finished']}/{done['planned']} planned attempts finished; {done['received']} returned responses, {done['execution_errors']} ended in execution errors. {raw['format_valid']}/{done['received']} responses passed raw evidence-format checks. An invalid or missing response is not a pass, fail or evidence of robustness. Later recovery attempts remain separate below.</p>
<div class="tablewrap"><table><thead><tr><th>Comparison with the original Gemini judge</th><th>Comparable pairs</th><th>Changed verdicts / comparable pairs</th><th>Scope</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>Primary comparisons require valid raw source/output evidence on both sides. Uncertain remains a separate verdict; missing baselines are excluded and listed. Rewording observations share the same 20 historical outputs, and injected variants share four constructed parents. These counts are not independent task samples or a human accuracy estimate.</p>
<p>The bias-aware version adds an explicit failure pattern, so its changes cannot be pooled with meaning-preserving rewordings. A cross-family difference does not identify which judge is right. Author-intended constructed labels remain diagnostic expectations.</p>
<details><summary>Constructed controls across judge families</summary><div class="tablewrap"><table><thead><tr><th>Judge</th><th>Matches author expectation / resolved controls</th><th>Unknown, invalid or unreceived controls</th><th>Planted critical errors detected / comparable</th></tr></thead><tbody>{''.join(fixtures)}</tbody></table></div><p>Nine constructed families supply 36 correlated control variants. Expectations were written by the author, not independently certified by experts. The eight intended critical errors are a diagnostic subset, not a sensitivity estimate on workplace outputs.</p></details>
<details><summary>Secondary locator normalization and full exclusions</summary><p>The frozen normalizer makes {norm['raw_invalid_becoming_secondary_scorable']}/{norm['raw_invalid']} new raw-invalid responses and {old_norm['raw_invalid_becoming_secondary_scorable']}/{old_norm['raw_invalid']} original historical raw-invalid responses scorable under its secondary rule. It removes locator prefixes and retains one matching quote fragment; {norm['cases_with_discarded_quote_segments']} new responses lose quote segments. That can discard context. This is not a semantic repair and never replaces raw primary judgments or human calibration.</p><p><a href="supporting/grader-robustness-audit.json">Complete audited metrics, normalization diagnostics, exclusions and source hashes</a></p></details>{recovery_html(r)}</section>'''


def pitch_text(e, evaluation_record=None):
    cost=e['cost']['reported_cumulative_usd'];unresolved=e['cost']['unresolved_charge_records']
    return f'''TURING FIELD ENGINEER TAKE-HOME — TWO LAB PITCHES

ANTHROPIC — CAN THE ACTION BE TRUSTED?
I propose a small private evaluation pack for agents making workplace release decisions. It tests whether an agent carries approval rules and resource constraints through the entire work product, including exception paths and action tables.

The starting evidence is a narrow GDPval-derived investigation. All 53 parseable outputs passed the designed fact checks; seven attempts had no parseable final. Five selected human reviews accepted two outputs and confirmed three corrections previously flagged by the primary GPT judge: two tooling-release plans without an explicit bridge-supply gate, and one provisional-price instruction omitting Finance.

The grading itself needs investigation. The GPT judge accepted 24/25 GPT outputs and 12/28 Claude outputs. A later Gemini judge accepted one output the human rejected. These are distinct judge observations, not a validated model ranking or proof of self-preference.

Commission five fresh purchasing families with permissioned sources, complete deliverables, independent domain review and evidence-grounded judgments. Include authorized proceed cases as well as justified holds. The acceptance test is whether the grader detects consequential errors without inventing problems or blocking valid work. We will report misses, false alarms, uncertain judgments and review cost case by case before expanding the collection.

OPENAI — TURN A DOCUMENTED FAILURE INTO TESTABLE SUPERVISION
I propose five fresh purchasing task families that connect each important constraint to the action it should control. Each family includes source files, realistic information gaps, acceptable native deliverables, criterion-level evidence and expert correction or preference pairs.

The current investigation identifies two useful targets: carrying resource dependencies through a schedule and applying mandatory approvals consistently to exceptions. Fact extraction alone did not expose these problems: all 53 completed historical outputs passed narrow checks. Human review confirmed three specific corrections among five selected outputs, all previously flagged by the primary judge.

The first intervention will hold the model and task conditions fixed and compare a baseline with explicit dependency and approval checks plus reliable file inspection. If prompt or tool repairs solve the failures, we deliver that improvement. If verified failures persist, collect successful trajectories and preferences on separate training families, then test transfer on untouched evaluation families.

The purchase gate combines useful completion, consequential errors and total review-and-correction cost per accepted deliverable. This pilot establishes whether further data collection is worth funding; it does not promise an unmeasured training gain.

15-MINUTE PRESENTATION
First 2minutes: state the null fact-check result, judge asymmetry and two source/output exhibits.
Next 4minutes: explain the human-confirmed corrections and how counterevidence changes their scope.
Next 3minutes: present the audience-specific five-family offer and acceptance criteria.
Remaining 6minutes: inspect raw evidence and discuss the questions below.

HARD QUESTIONS — EVIDENCE-BOUND ANSWERS

1. What is the main result?
The designed critical-fact probe found no wrong targeted fields among 53 parseable outputs; seven of 60 attempts produced no parseable final. Document-level grading was asymmetric, and five selected human reviews confirmed three substantive corrections. This shifts the follow-up toward action consistency and grader validity, without establishing a model ranking.

2. Did humans find failures that your model judge missed?
The primary GPT judge had already flagged all three retained issues before human review. The reviewer confirmed and refined those findings. The later Gemini calibration judge missed one of them; that is a different judge and phase. Narrow fact checks, content judges and human acceptance must not be merged.

3. Is the 24/25 versus 12/28 gap self-preference?
Not established. It is a descriptive association between generator family and the GPT judge's acceptance decisions. Output quality, style, length, task conditions and selection can also explain the association. The secondary Claude judge accepted 7/7 GPT and 4/5 Claude outputs in its selected subset; it does not show simple reciprocal vendor favoritism. The next test needs the same outputs crossed with multiple judges and independent human judgments.

4. Why only five human reviews?
This is a purposive, hypothesis-aware qualitative case study, not a prevalence sample. It retained two accepted outputs and three rejected outputs across two source families. It supports examples and correction hypotheses. It does not measure occupational reliability or independent expert agreement.

5. Are the tooling findings certain production failures?
No. The source does not establish one tool set, duplicate capacity or available molded stock. The reviewer identifies a missing dependency gate under the single-tool scenario. The correction is to verify coverage and the final molding run before release, then align the dates. No production halt was observed.

6. Finance is required in the next paragraph. Why reject that output?
The operative provisional-release clause names only Program and Purchase. The following paragraph and tier rules are counterevidence, but do not clearly reconcile that conflicting action instruction. The reviewer requires the release route to explicitly retain all three approvals and a defined cap. No actual bypass or spending loss was observed.

7. Show three confirmed examples of the top category.
There are only two confirmed tooling findings, C-9d21debd and C-5304f72e, from the same source family. The third confirmed finding is the separate approval case C-4f3f9946. Archived unreviewed examples do not increase the confirmed count.

8. Were these unchanged GDPval tasks?
No. Five public tasks were adapted into baseline, recovery-pointer and conflicting-draft versions. Every version included approved and unapproved workspace records. The solver returned JSON artifact specifications; a local renderer created the files afterward. The exact tasks, substitutions, tools and settings are in supporting/evaluation-record.json.

9. Are 24 automatic flags proven harness defects?
No. Twelve contract flags, eleven page-overflow flags and one serialization flag are delivery or evaluation concerns. Their causes and repair effects are not established. Three of the eleven potentially substantive candidates received completed human content reviews and documented findings. The 35-flag appendix is automated triage.

10. Is the grader validated?
No general accuracy claim is supported. The original Gemini comparison is eligible for three reviewed outputs: two agree on both outcomes, and one is a false accept and missed consequential error relative to the human. Quote checks establish traceability, not entailment. Rewording stability can coexist with consistent error.

11. Why would more data help rather than a better prompt or tools?
That remains the hypothesis. First clarify task contracts, provide reliable native-file inspection and test explicit dependency/approval checks. Training is justified only if confirmed failures persist and improvements transfer to untouched families. A resolved setup issue changes the proposed product; it is not retroactively a data success.

12. How is contamination handled?
Private gold and rubrics were outside solver access; no training ran. Public pretraining exposure is unknown. Fresh collection requires permissions and complete source/template-lineage separation across development, training and evaluation. Local hashes document provenance; they do not prove novelty.

13. What did the work cost?
Original evaluation and judging cost $4.391054. All recorded stages total ${cost:.4f}, with {unresolved} unresolved charge records. These are provider-reported charges, not a reconciled invoice. Human labor and repair cost are unknown, so total cost per accepted deliverable is not estimable.

14. What is reproducible?
The package reproduces recorded counts offline and includes the saved inputs, outputs and costs. All 60 task/protocol hashes match. The retained runner differs from the runtime-recorded script hash, so exact historical execution equivalence is not established. Later native-file work and inspection dry runs are separate engineering evidence.

15. What would invalidate the proposal?
Independent task review removes the alleged error; reviewers cannot agree on the intended outcome; the source rights cannot be secured; prompt/tool repairs resolve the gap; or a data intervention fails on untouched families. Each result changes what should be built or purchased.
''' + evaluation_record_pitch(evaluation_record)


def judge_gap_html(gap):
    rows=[]
    for model,label in [('openai/gpt-6.1-sol','GPT-6.1 Sol outputs'),('anthropic/claude-sonnet-5.5','Claude Sonnet 5.5 outputs')]:
        row=gap['primary_by_generator'][model]
        rows.append(f"<tr><td>{label}</td><td>{row['accepted']}/{row['judged']}</td><td>{row['critical_error']}/{row['judged']}</td></tr>")
    sensitivity=gap['sensitivity_exclusion']
    pair=sensitivity['matched_by_generator']
    # The source record contains the exact paired members and all exclusions.
    return '<section id="judge-gap"><h2>The primary judge treated the generators differently</h2><p>The primary GPT judge made the following content decisions. These are automated labels, not human-validated model-quality estimates.</p><table><thead><tr><th>Generator</th><th>Accepted by GPT judge</th><th>Critical-error label</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><p>Excluding all change-control attempts and EV-conflict attempts leaves '+str(sensitivity['remaining_judged'])+' judged outputs and '+str(sensitivity['complete_matched_pairs'])+' complete matched pairs. On those pairs, the GPT judge accepts 21/21 GPT outputs and 10/21 Claude outputs. Eleven pairs disagree, all in the same direction. This association survives that exclusion but does not identify self-preference: output quality, style, length and other generation differences remain possible explanations.</p><p>The secondary Claude judge accepts 7/7 GPT and 4/5 Claude outputs in its selected subset. It does not show simple reciprocal vendor favoritism. All three retained human findings were previously flagged by the primary GPT judge; the later Gemini miss is a separate judge and phase.</p><p><a href="supporting/judge-gap.json">Run-level counts, matched pairs, prior flags and source hashes</a></p></section>'


def concise_landing(e, gap):
    c=reviewed_counts(e);cost=e['cost'];g=gap['primary_by_generator']['openai/gpt-6.1-sol'];a=gap['primary_by_generator']['anthropic/claude-sonnet-5.5']
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Turing | Correct facts, conflicting actions</title><style>{CSS}</style></head><body><main>
<header><span>Turing / Field Engineer take-home</span><span>Professional-work evaluation</span></header>
<section class="hero"><div class="label">Findings and dataset proposal</div><h1>Correct facts.<br>Conflicting actions.</h1><p class="lead">The targeted fact probe found no errors among 53 parseable outputs. Five selected human reviews nevertheless confirmed three substantive corrections already flagged by the primary judge.</p><p><b>The offer:</b> commission five fresh purchasing task families that test whether approval rules and resource dependencies survive throughout a complete work product.</p><div class="links"><a class="button" href="one-page.pdf">One-page brief</a><a class="button secondary" href="evidence.html">Evidence and methods</a><a class="button secondary" href="pitches-and-defense.txt">Lab pitches</a></div></section>
<section><h2>What ran—and what it found</h2><p>Five adapted GDPval tasks covered supplier continuity, sourcing approvals, EV localization, change control and shipping. Two models × three variants × two repeats produced <b>60 attempts</b>. Models returned JSON specifications; the harness rendered the files.</p><p><b>Null result:</b> 53/53 parseable outputs passed the designed fact checks; seven attempts had no parseable final. This probe did not separate the models on its targeted facts.</p><table><thead><tr><th>Generator</th><th>Accepted by GPT judge</th><th>Critical-error labels</th></tr></thead><tbody><tr><td>GPT-6.1 Sol</td><td>{g['accepted']}/{g['judged']}</td><td>{g['critical_error']}/{g['judged']}</td></tr><tr><td>Claude Sonnet 5.5</td><td>{a['accepted']}/{a['judged']}</td><td>{a['critical_error']}/{a['judged']}</td></tr></tbody></table><p>This sharp judge asymmetry deserves investigation; it does not establish self-preference or a model winner. <a href="evidence.html#judge-gap">Inspect the matched comparison</a>.</p></section>
<section><h2>Three confirmed corrections</h2><p><b>Two tooling plans:</b> require an explicit gate between final supplier production, verified supply coverage and tool transfer.</p><p><b>One approval workflow:</b> require Finance on the provisional-release path, despite correct approval rules elsewhere.</p><p>The reviewer accepted {c['acceptable']}/{c['reviewed']} selected outputs and required correction in {c['correction']}. The primary GPT judge had flagged all three issues; human review confirmed and refined them. A later Gemini judge missed one. <a href="evidence.html#evidence">See sources, counterevidence and corrections</a>.</p></section>
<section><h2>What to commission next</h2><p>Permissioned sources, realistic workflow variants, native deliverables, independent domain review and evidence-grounded correction pairs. Test prompt/tool repairs first; measure accepted work, consequential errors, unnecessary holds and review cost. Use separate training families only if verified failures persist.</p></section>
<aside class="notice"><b>Scope:</b> five selected, hypothesis-aware content reviews across two purchasing families; reviewer expertise and independence unestablished. The tooling scenario assumes a shared tool. Tasks were adapted, native inspection was absent in the original run, and some task contracts were confounded. No observed business harm or training gain is claimed.</aside>
<footer><p><b>Cost:</b> $4.391054 original evaluation and judging; ${cost['reported_cumulative_usd']:.2f} across recorded stages, with {cost['unresolved_charge_records']} unresolved charge records. Human labor is unmeasured.</p><p><a href="code/START_HERE.txt">Code and offline reproduction</a> · <a href="supporting/strengthening-13/index.html">Additional measurement checks and unrun inspection pilot</a></p></footer></main></body></html>'''


def build_pdf(e, taxonomy, dest, selected_checks=None, judge_gap=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle, Spacer
    from pypdf import PdfReader
    ink=colors.HexColor('#172b32');teal=colors.HexColor('#196755')
    styles={
      'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=30,leading=33,textColor=ink,spaceAfter=18),
      'head':ParagraphStyle('head',fontName='Helvetica-Bold',fontSize=11,leading=14,textColor=teal,spaceBefore=13,spaceAfter=5),
      'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10.5,leading=14,textColor=ink,spaceAfter=9),
      'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.5,leading=11,textColor=ink,spaceAfter=7)}
    p=lambda text,kind='body':Paragraph(text,styles[kind])
    cost=e['cost'];c=reviewed_counts(e)
    if judge_gap is None:raise ValueError('A verified judge-gap record is required for the brief.')
    gap=judge_gap
    g=gap['primary_by_generator']['openai/gpt-6.1-sol'];a=gap['primary_by_generator']['anthropic/claude-sonnet-5.5']
    flow=[p('TURING / FIELD ENGINEER TAKE-HOME','small'),p('Correct facts.<br/>Conflicting actions.','title'),
      p('Five adapted GDPval tasks across purchasing, project management and shipping; two models, three variants, two repeats: <b>60 attempts</b>. Models returned JSON specifications rendered locally into files.'),
      p('<b>Null result:</b> 53/53 parseable outputs passed targeted fact checks; seven attempts had no parseable final.'),
      p('A judge asymmetry to investigate','head')]
    table=Table([[p('<b>Generator</b>','small'),p('<b>GPT judge accepts</b>','small'),p('<b>Critical labels</b>','small')],
        [p('GPT-6.1 Sol','small'),p(f"{g['accepted']}/{g['judged']}",'small'),p(f"{g['critical_error']}/{g['judged']}",'small')],
        [p('Claude Sonnet 5.5','small'),p(f"{a['accepted']}/{a['judged']}",'small'),p(f"{a['critical_error']}/{a['judged']}",'small')]],colWidths=[201,154,144])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eee8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),3),('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#d5ddd7'))]))
    flow += [table,Spacer(1,8),p('This association could reflect output quality, style or judge bias. It is not a validated model ranking.','small'),
      p('What manual review confirmed','head'),
      p(f"The reviewer accepted {c['acceptable']}/{c['reviewed']} selected outputs and confirmed three corrections already flagged by the GPT judge: <b>two missing tooling-release gates</b> and <b>one provisional-release clause omitting Finance</b>. Correct rules elsewhere did not resolve the action instructions. A later Gemini judge missed one finding."),
      p('Commission a focused data pilot','head'),
      p('Five fresh, permissioned purchasing families: authoritative sources, workflow variants, native deliverables, independent review and correction pairs. Test prompt/tool repairs first. Measure acceptance, consequential errors, unnecessary holds and review cost; train on separate families only if failures persist.'),
      p('<b>Scope:</b> purposive, hypothesis-aware content review across two families; expertise and independence unestablished. The tooling scenario assumes a shared tool. Original native inspection was absent; some tasks were confounded. No observed harm or training gain.','small'),
      p(f"<b>Cost:</b> $4.391054 original evaluation/judging; ${cost['reported_cumulative_usd']:.2f} across recorded stages, {cost['unresolved_charge_records']} unresolved charge records. Human labor unmeasured.",'small')]
    def footer(canvas,doc):
        canvas.setFont('Helvetica',7.5);canvas.setFillColor(ink)
        canvas.drawString(48,25,'Evidence, exact task modifications, distinct pitches and offline reproduction: open index.html.')
    SimpleDocTemplate(str(dest),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=40,title='Turing — correct facts, conflicting actions',author='Turing take-home submission').build(flow,onFirstPage=footer,onLaterPages=footer)
    pages=len(PdfReader(dest).pages)
    if pages!=1:raise ValueError(f'Leave-behind must be one page; got {pages}.')


CSS = '''*{box-sizing:border-box}body{margin:0;color:#182d34;background:#f5f2e9;font:17px/1.55 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:28px 28px 70px}header{display:flex;justify-content:space-between;gap:12px;color:#536267;font-size:12px;text-transform:uppercase;letter-spacing:.08em}h1{font:normal clamp(38px,6vw,64px)/1.05 Georgia,serif;letter-spacing:-.035em;max-width:850px;margin:18px 0}h2{font:normal 31px/1.2 Georgia,serif;margin:38px 0 14px}h3{font-size:19px;margin:0 0 9px}p{margin:0 0 14px}a{color:#196755;text-underline-offset:3px}.hero{padding:28px 0;border-bottom:1px solid #d5d8cb}.lead{font-size:20px;max-width:850px}.label{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#196755;font-weight:700}.notice{border-left:4px solid #aa572b;background:#fff8e9;padding:12px 16px;font-size:14px}.links{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.button{display:inline-block;background:#196755;border:1px solid #196755;color:white;text-decoration:none;padding:10px 16px;border-radius:4px;font-size:14px;font-weight:600}.secondary{background:transparent;color:#196755}.stats{display:grid;grid-template-columns:repeat(4,1fr);margin:24px 0 8px}.stat{border-left:1px solid #cfd6ca;padding:0 18px}.stat:first-child{border-left:0;padding-left:0}.stat strong{font-size:30px;font-weight:500;display:block}.stat span,.small{font-size:13px;color:#536267}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:#fffdf7;border:1px solid #d5d8cb;padding:22px}blockquote{border-left:3px solid #aa572b;margin:16px 0;padding-left:14px;font:20px/1.4 Georgia,serif}.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;background:#fffdf7;font-size:14px}th,td{text-align:left;padding:11px 13px;border-bottom:1px solid #ddd;vertical-align:top}th{font-size:12px;text-transform:uppercase;color:#536267}details{padding:15px 0;border-bottom:1px solid #d5d8cb}summary{font-weight:650;cursor:pointer}pre{white-space:pre-wrap;font-size:12px;background:#eef0e7;padding:15px;max-height:450px;overflow:auto}footer{margin-top:35px;padding-top:20px;border-top:1px solid #d5d8cb;font-size:12px;color:#536267}a:focus-visible,summary:focus-visible{outline:3px solid #d09335;outline-offset:3px}@media(max-width:700px){main{padding:22px 18px 45px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr;row-gap:20px}.stat:nth-child(3){border-left:0;padding-left:0}table{min-width:560px}header{flex-direction:column}}'''


def build(root=ROOT):
    out=root/'output/assignment_final/submission';out.mkdir(parents=True,exist_ok=True)
    evidence_path=root/'output/assignment_final/evidence.json'
    if not evidence_path.exists():
        raise FileNotFoundError('Build assignment_evidence.py first; do not fabricate a substitute evidence record.')
    e=read(evidence_path);taxonomy=read(root/'output/submission_audit/taxonomy.json')
    from build_judge_gap_14 import build as build_judge_gap
    judge_gap=build_judge_gap(root)
    write(root/'output/strengthening_14/judge-gap.json',judge_gap)
    write(out/'supporting/judge-gap.json',judge_gap)
    from build_evaluation_record import build as build_evaluation_record
    evaluation_record=build_evaluation_record(root)
    write(root/'output/assignment_final/evaluation-record.json',evaluation_record)
    write(out/'supporting/evaluation-record.json',evaluation_record)
    strengthening_panel,strengthening_defense=prepare_strengthening_supplement(root,out)
    if not e.get('grader_robustness',{}).get('completion',{}).get('complete'):
        raise ValueError('Finish and audit the grader-robustness batch before replacing the final submission.')
    status, hline=human_status(e);count=e['human']['completed_count'];cost=e['cost']
    plan=e.get('review_plan',{})
    review_scope=review_plan_text(e)
    planned=plan.get('target_case_count',count)
    reviewed=plan.get('completed_case_count',count)
    remaining=plan.get('remaining_case_count',0)
    write(out/'evidence.json',e)
    if plan:
        write(out/'supporting/review-plan.json',plan)
        for case in plan['case_ids']:
            copy(root,f'reviews/calibration_ready_01/files/{case}/review-packet.pdf',out/f'review-cases/{case}.pdf')
    sources=[('output/paired_v1/summary.json','supporting/historical-results.json'),
             ('output/submission_audit/taxonomy.json','supporting/provisional-taxonomy.json'),
             ('output/grader_checks_05/quote_format_summary.json','supporting/grader-format.json'),
             ('output/judge_robustness_10/audited_summary.json','supporting/grader-robustness-audit.json'),
             ('output/submission_ready/historical-purchasing-review.pdf','supporting/issue-review.pdf')]
    for source,target in sources:copy(root,source,out/target)
    write(out/'cases/trace-index.json',submission_trace_index(root,e))
    for name in ('literature-review.json','literature-review.html'):
        source=root/'output/measurement_update_11'/name
        if source.is_file():copy(root,source.relative_to(root),out/'supporting'/name)
    controls=root/'reviews/judge_controls_11'
    if controls.is_dir():
        target=out/'measurement-controls'
        if target.exists():shutil.rmtree(target)
        shutil.copytree(controls,target)
    for number in (1,2,3):
        for name in ('deliverable-1.docx','deliverable-1.pdf','observable-transcript.json','observable-transcript.txt'):
            copy(root,f'output/anthropic_defense/case-{number}/{name}',out/f'cases/case-{number}/{name}')
    rows=''.join(f"<tr><td>{esc(c['name'])}</td><td>{c['candidate_count']}</td><td>{esc(c['severity'])}</td><td>{esc(c['data_fix'])}</td></tr>" for c in taxonomy['categories'])
    human_results=human_html(e)
    selected_checks=selected_fact_check_context(root,e)
    result_counts=reviewed_counts(e)
    finding_by_category={x['category']:x for x in e['human']['taxonomy'].get('examples',[])}
    category_counts=e['human']['taxonomy'].get('counts',{})
    tooling_count=category_counts.get('tooling_release_not_gated_on_bridge_supply',0)
    approval_count=category_counts.get('provisional_release_omits_required_finance_approval',0)
    tooling_correction=finding_by_category.get('tooling_release_not_gated_on_bridge_supply',{}).get('minimum_repair') or 'Not yet confirmed'
    approval_correction=finding_by_category.get('provisional_release_omits_required_finance_approval',{}).get('minimum_repair') or 'Not yet confirmed'
    selected_lead=(f"All {selected_checks['selected']} selected outputs passed the narrow fact checks." if selected_checks['selected'] and selected_checks['passed']==selected_checks['selected'] else f"{selected_checks['passed']}/{selected_checks['selected']} selected outputs passed the narrow fact checks.")
    write(out/'supporting/selected-fact-checks.json',selected_checks)
    review_links=' / '.join(f'<a href="review-cases/{esc(case)}.pdf">{esc(case)}</a>' for case in plan.get('case_ids',[]))
    content=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Turing | Evidence-to-action diagnostic</title><style>{CSS}</style></head><body><main>
<header><span>Turing / Field Engineer take-home</span><span>Evidence snapshot: {esc(e['updated_at'][:10])}</span></header><p><a href="index.html">Return to the two-minute overview</a></p>
<section class="hero"><div class="label">Completed five-case purchasing audit</div><h1>{count} reviews. {result_counts['correction']} outputs required correction.</h1>
<p class="lead">{esc(selected_lead)} The human reviewer accepted {result_counts['acceptable']} and required substantive correction in {result_counts['correction']}. The gap is whether the final release decision respects the source facts and dependencies.</p>
<p><strong>Dataset ask:</strong> a proposed private GDPval-style task pack with authoritative reference files, complete professional deliverables, dependency and approval checks, and expert evidence rationales. Test useful completion and consequential errors before using the results as training signals.</p>
<div class="links"><a class="button" href="one-page.pdf">One-page findings</a><a class="button secondary" href="#evidence">Inspect the findings</a><a class="button secondary" href="code/START_HERE.txt">Code + reproduction</a></div>
<div class="stats"><div class="stat"><strong>{count}</strong><span>reviewed outputs</span></div><div class="stat"><strong>{result_counts['acceptable']}</strong><span>acceptable without substantive correction</span></div><div class="stat"><strong>{result_counts['correction']}</strong><span>require substantive correction</span></div><div class="stat"><strong>2</strong><span>purchasing source families</span></div></div>
<p class="notice"><strong>{esc(status)}.</strong> {esc(review_scope)} Qualifications and independence are unspecified; native-file/page compliance remains unverified. </p>
<p class="small"><a href="supporting/selected-fact-checks.json">Selected-case fact-check trace</a>. Three consequential-error judgments apply to these reviewed outputs; no population error rate, model ranking, validated grader or training benefit follows.</p></section>
<section id="evidence"><h2>Two user-confirmed categories and accepted corrections</h2><div class="grid">
<article class="card"><div class="label">{tooling_count} outputs / one supplier-exit source family</div><h3>Tooling release not gated on bridge supply</h3><p>The plans schedule transfer while LPI bridge supply is still proposed, without tying the tool release to the final molding run and verified coverage. The reviewer marks both outputs unusable without correction and consequential.</p><p><strong>Scope:</strong> the source does not establish one tooling set, absence of duplicates or available molded stock. The interruption scenario is conditional; no line stoppage was observed. These two related outputs are not independent task families.</p><p><strong>Accepted correction:</strong> {esc(tooling_correction)}</p></article>
<article class="card"><div class="label">{approval_count} output / sourcing-approvals family</div><h3>Provisional release omits required Finance approval</h3><p>The provisional-price exception names Program Manager and Purchase while the approved source requires Finance as well. The reviewer identifies a potential routing and commitment risk.</p><p><strong>Counterevidence:</strong> the immediately following paragraph and every tier repeat the three-way rule. No platform implementation, approval bypass or expenditure was observed. An undefined cap is an unresolved control, not proof of unlimited exposure.</p><p><strong>Accepted correction:</strong> {esc(approval_correction)}</p></article>
</div><p class="small">The reviewer supplied a separate formal severity description for one tooling case. Other formal severity grades remain unspecified; their actual rejection and consequential-error labels are shown in the case records. Accepted corrections have not been implemented and tested as interventions.</p><p><strong>Grader check:</strong> {esc(reviewed_judge_text(e))}</p></section>
<details><summary>History: two earlier issue-only judgments</summary><div class="grid"><article class="card"><div class="label">Supplier continuity</div><h3>Unknown stock becomes assured coverage</h3><p><strong>Source:</strong> supply stops in 21 days; replacement takes months; opening stock is unknown.</p><blockquote>"Absent an agreement, buffer stock and air freight cover the gap."</blockquote><p><strong>Why it matters:</strong> an action plan could rely on coverage that has not been established. The same output warns of interruption; that counterevidence belongs in the judgment.</p><p class="small">Earlier owner label: this specific issue requires material correction. {esc(earlier_issue_scope(e))}</p></article><article class="card"><div class="label">Approval authority</div><h3>An exception omits a required approver</h3><p><strong>Source:</strong> the approved price-change rule requires Finance, Program and Purchase.</p><blockquote>"This must be recorded and approved by the Program Manager and Purchase."</blockquote><p><strong>Why it matters:</strong> a provisional-release instruction can bypass Finance. The output then repeats the three-way rule and leaves the cap for CPO decision; review those qualifications too.</p><p class="small">Earlier owner label: this specific issue requires material correction. It does not establish whole-output rejection or a model-wide honesty rate.</p></article></div><p class="small"><a href="supporting/issue-review.pdf">Sources and issue excerpts</a>. Selection occurred after outputs and earlier issue labels were available. The final report retains rejected or uncertain findings and withdraws any unsupported claim; it does not keep adding cases until errors appear.</p></details>
<section><h2>Wider historical run: automated context</h2><p>Five public GDPval source families: three purchasing, one project-management and one shipping task. We chose inspectable costs, approval rules, dependencies and file deliverables. Two models (GPT-6.1 Sol and Claude Sonnet 5.5), three information versions and two repeats produced 60 attempts. Repeats and variants are not independent professional tasks. This broader execution coverage is separate from the two-family human case study.</p>
{evaluation_record_html(evaluation_record)}
{judge_gap_html(judge_gap)}
<div class="tablewrap"><table><thead><tr><th>Observed result</th><th>Interpretation</th></tr></thead><tbody><tr><td>53/60 targeted fact-check passes</td><td>All 53 parseable outputs passed the narrow critical-fact check; seven attempts had no parseable output. This is not full deliverable acceptance.</td></tr><tr><td>18/35 bounded prose documents exceeded the page limit</td><td>A delivery constraint under the fixed renderer, not an honesty failure. Models could not inspect and revise native files in this historical setup.</td></tr><tr><td>12/12 shipment workbooks passed value checks</td><td>Calculation checks for this selected family, not proof of general spreadsheet competence.</td></tr><tr><td>53 primary model reviews; 12 secondary reviews</td><td>Acceptance agreement 8/12. Critical-error agreement 10/12, all shared negatives. No expert correctness follows from model agreement.</td></tr></tbody></table></div>
<p class="small">Four EV conflict runs have a cost-basis defect; a separate scope ambiguity affects 12 change-control attempts. They remain visible in the evidence. <a href="supporting/historical-results.json">Historical results and original descriptive family-level intervals</a>.</p></section>
<section><h2>Completed review records and supporting evidence</h2><p>{esc(reviewed_result_text(e))} Each retained finding has source/output evidence, a confirmed category and an accepted correction. The primary GPT judge had already flagged all three issues; the human review confirmed and refined them. Formal severity, qualifications, independence and time remain unspecified where not supplied.</p><p><a href="supporting/review-plan.json">Completed fixed review plan</a>. The five cases were retained regardless of verdict; the original 20- and 35-case queues are not further review requirements.</p><p class="small">Complete source/output packets, in review order: {review_links}.</p>
<details><summary>Imported human judgments and descriptive grader comparisons ({count} complete records)</summary><p>These are calculated from actual review exports, with uncertainty, defects, provenance and disagreements preserved. Only cases with valid existing judge evidence enter comparisons. The selected set is not a representative calibration sample; agreement counts cannot validate the grader.</p>{human_results}<p><a href="evidence.json">Full confusion counts, exclusions, evidence and provenance</a></p></details>
<details><summary>Automated appendix: 35 flagged attempts, not confirmed failures</summary><p>Seven rule-assigned triage categories remain archived for reproducibility. Their counts, severity labels and proposed data opportunities are automated suggestions, not applicant-confirmed findings. They do not create an additional human-review requirement. A task defect may coexist with a business error.</p><div class="tablewrap"><table><thead><tr><th>Automated candidate category</th><th>Flag count</th><th>Proposed severity</th><th>Unverified data hypothesis</th></tr></thead><tbody>{rows}</tbody></table></div><p class="small">Counts repeat five source families. The contract, serialization and overflow categories do not establish that 24 cases would be fixed by changing the harness. <a href="supporting/provisional-taxonomy.json">Definitions and example run IDs</a>.</p></details></section>
<section><h2>Can the grader support the claim?</h2><p>The original Gemini batch received 55/56 responses. All 36 constructed responses passed exact-evidence validation; only 11/19 historical-output responses passed, with eight invalid quotation records. Constructed success therefore does not establish reliable judging on real deliverables.</p><p>Measure false accepts, missed consequential errors and false alarms against actual human reviews. Keep invalid judge responses and uncertain human labels visible. Quote matching establishes traceability, not whether the conclusion follows.</p><p class="small"><a href="supporting/grader-format.json">Raw evidence-validation diagnostic</a>. A different judge family adds diversity, not ground truth. Individual human-positive cases and judge disagreements are shown in the completed-case table. They are diagnostic examples, not a general sensitivity estimate; reviewer assumptions remain attached to each finding.</p></section>
{robustness_html(e)}
{measurement_html(e,root)}
<section><h2>Different buying decisions for each lab</h2><div class="grid"><article class="card"><div class="label">Anthropic</div><h3>Preserve uncertainty through the action</h3><p>Test whether the final deliverable respects source authority and resource constraints. Include cross-file contradictions, correct proceed cases and justified holds, so excessive refusal cannot win.</p><p><strong>Proposed offer:</strong> a private diagnostic task pack with expert evidence, followed by a separately planned human validation of its grader. This case study supplies inspectable examples, not a reliable automated honesty score.</p></article><article class="card"><div class="label">OpenAI</div><h3>Identify useful supervision after repairs</h3><p>First repair task contracts, source access, tools and prompt guidance. Persistent human-confirmed errors become candidates for verified trajectories and expert preferences on separate training families.</p><p><strong>Proposed offer:</strong> a testable supervision hypothesis with untouched-family evaluation. No measured training improvement or uniquely data-addressable failure is claimed.</p></article></div><p><a href="pitches-and-defense.txt">Two distinct spoken pitches, 15-minute agenda and hard questions</a>.</p></section>
{data_opportunity_html(evaluation_record)}
{strengthening_panel}
<section><h2>The proposed dataset and purchase metric</h2><p>Start with five freshly authored development families to measure authoring and review effort. The proposed collection is 30 families with three versions each: 10 development and 20 untouched evaluation families. Deliver permission records, source files, allowed tools, expert native gold outputs, acceptable alternatives, evidence maps and preference rationales. The collection is not yet produced.</p><p>Any later SFT/RL collection uses separate source/template lineages. Test prompt and tool repairs before training, then assess transfer to untouched families. Public pretraining exposure cannot be ruled out; current inspected tasks cannot become a fresh test set.</p><p><strong>Buying decision:</strong> agree consequential-error and useful-completion gates first, then compare total generation, retry, judging, tool and human review/correction cost per accepted deliverable. That unit cost is currently unknown.</p></section>
<details><summary>Separate engineering extension: native files and foreground misinformation</summary><p>Native DOCX/XLSX creation, rendering, inspection and revision were built and mechanically checked. A later fixed-Claude study used five families, three public derivatives and two constructed scenarios. Ten attempts finished; five submitted files; three stopped on provider/transport errors and two on response-token limits. Only one family has both outputs.</p><p>Both conditions already contain approved and unapproved records. The contrast changes correct foreground information into misleading foreground information; it does not isolate the presence of conflict. Search is lexical, clarification scripted and workspace structures strongly cued. The extension supplies engineering diagnostics, not a repair-effect estimate or model ranking.</p></details>
<details><summary>Three complete illustrative transcripts</summary><p>All three are from one supplier-continuity source family and were selected for diagnosis. {esc(illustrative_transcript_review_text(e))} They are outside the frozen calibration queue and must not be presented as three independent confirmed errors.</p><ol>'''
    for number in (1,2,3):
        content += f'<li>Case {number}: <a href="cases/case-{number}/observable-transcript.txt">sources and complete observable transcript</a> / <a href="cases/case-{number}/deliverable-1.pdf">full output PDF</a> / <a href="cases/case-{number}/deliverable-1.docx">native file</a>.</li>'
    content+=f'''</ol><p><a href="cases/trace-index.json">Selection record and original-run hashes</a>. Provider-internal reasoning and account metadata are excluded.</p></details>
<details><summary>Data origin, seeds and coding-agent contribution</summary><p>The original study adapts public GDPval tasks. Transformations and later fictional facts were authored locally, not sampled from a teacher API. Seeds shuffle run order only. Private maps and labels stay outside solver access. No training ran, and source redistribution/commercial permissions remain unresolved.</p><p>The coding agent implemented tools, checks, orchestration, scoring and packaging; it drafted the taxonomy and pitches. It cannot supply the applicant's manual review, domain qualifications, rights clearance or lab endorsement.</p></details>
<section><h2>Cost and reproduction</h2><p>Original evaluation and judging: <strong>$4.391054</strong>. Recorded historical, native and grader stages: <strong>${cost['reported_cumulative_usd']:.4f}</strong> provider-reported, with <strong>{cost['unresolved_charge_records']}</strong> unresolved charge records. Robustness and its separately reported recovery requests contribute <strong>${cost['grader_robustness_usd']:.4f}</strong>. Primary comparisons preserve the original attempts; later recovery charges are included once in cost. Human labor is unmeasured.</p><p class="small">These are not live account totals or a reconciled invoice. The paid robustness requests are included; rebuilding the report and reproducing saved observations make no API calls. Grader robustness does not establish human calibration.</p><div class="links"><a class="button" href="code/START_HERE.txt">Offline reproduction instructions</a><a class="button secondary" href="code/reproduce_assignment.py">Reproduction code</a><a class="button secondary" href="evidence.json">Evidence record</a></div></section>
<footer>Supporting evidence preserves original inputs, failed attempts, counterevidence and unresolved measurements. The overview, one-page brief and lab pitches state the proposed next experiment; this archive supports inspection and offline reproduction.</footer></main></body></html>'''
    (out/'evidence.html').write_text(content)
    (out/'index.html').write_text(concise_landing(e,judge_gap))
    (out/'pitches-and-defense.txt').write_text(pitch_text(e,evaluation_record)+strengthening_defense)
    build_pdf(e,taxonomy,out/'one-page.pdf',selected_checks,judge_gap)
    write(out/'build-record.json',{'source_evidence_sha256':hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        'human_review_records':count,'pdf_pages':1,'new_api_calls':0,'visual_qa':'pending render inspection',
        'history_modified':False,'scope':'Focused assignment; human analysis status follows imported evidence.'})
    print(json.dumps({'website':str(out/'index.html'),'pdf':str(out/'one-page.pdf'),'human_records':count,'new_api_calls':0}))
    return out


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    build(parser.parse_args().root)
