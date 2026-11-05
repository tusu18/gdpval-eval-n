"""Audit observable engineering outcomes without assigning business grades."""
from collections import Counter
from datetime import datetime, timezone
import hashlib, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/native_workflow_01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')

def summarize(out=OUT, config_path=ROOT/'config/native_workflow_01.json'):
    cfg=load(config_path); ledger=load(out/'ledger.json') if (out/'ledger.json').exists() else []
    records=[load(p) for p in sorted((out/'runs').glob('*.json'))]
    rows=[]
    for r in records:
        folder=out/'workspaces'/r['run_id']; state=load(folder/'state.json')
        files=[]
        for entry in r.get('submission',[]):
            f=state['files'][entry['filename']]; views=len(f['previews']);bounds=None
            if f['kind']=='docx':
                if r['family_id'] in ('supplier_exit','sourcing_approvals'): bounds=[2,3]
                elif r['family_id']=='original_supplier_landed_cost':bounds=[1,1]
            formula_errors=[]
            if f['kind']=='xlsx':formula_errors=load(Path(f['metadata'])).get('formula_scan',[])
            files.append({'filename':entry['filename'],'kind':f['kind'],'revision':entry['revision'],
                'sha256':entry['sha256'],'submitted_hash_verified':sha(folder/'submitted'/entry['filename'])==entry['sha256'],
                'rendered_pages_or_sheet_views':views,'page_bounds':bounds,
                'page_requirement_met':bounds[0]<=views<=bounds[1] if bounds else None,
                'native_inspected':f['inspected'],'every_current_view_exposed':sorted(f['viewed_pages'])==list(range(1,views+1)),
                'formula_error_scan':formula_errors})
        costs=[x for x in ledger if x['run_id']==r['run_id']]
        errors=[{'tool':e['tool'],'error':e['reply']['error']} for e in r['tool_events'] if 'error' in e['reply']]
        last=r['calls'][-1].get('finish_reason') if r['calls'] else None
        attribution=('submitted_business_quality_unreviewed' if r['status']=='submitted' else
            'response_token_limit' if last=='length' else
            'transport_or_provider_failure' if any(x in r.get('error','').lower() for x in ('urlopen','openrouter http','ssl','broken pipe','timed out','connection reset','curl transport','epipe','und_err_socket','fetch failed','econnreset','socket hang up','upload connection closed')) else
            'request_size_limit' if r.get('error')=='request_size_limit' else
            'tool_call_limit' if r.get('error')=='tool_call_limit' else r['status'])
        rows.append({'run_id':r['run_id'],'model':r['model'],'family_id':r['family_id'],'status':r['status'],
            'mechanical_attribution':attribution,'last_finish_reason':last,
            'error':re.sub(r'"user_id"\s*:\s*"[^"]+"','"user_id":"[REDACTED]"',r.get('error','')) or None,
            'model_responses':len(r['calls']),'tool_calls':len(r['tool_events']),'tool_errors':errors,
            'authored_native_file_count':len(state['files']),
            'authored_native_hashes_verified':all(Path(f['path']).is_file() and sha(Path(f['path']))==f['sha256'] for f in state['files'].values()),
            'write_attempts':sum(e['tool'] in ('write_document','write_workbook') for e in r['tool_events']),
            'elapsed_seconds':r.get('elapsed_seconds'),
            'reported_api_cost_usd':sum(x['actual_cost_usd'] or 0 for x in costs),
            'unresolved_cost_records':sum(x['status']!='actual' for x in costs),
            'submitted_files':files,'raw_record':str((out/'runs'/(r['run_id']+'.json')).relative_to(ROOT))})
    by_model=[]
    for mid in [m['id'] for m in cfg['models']]:
        group=[r for r in rows if r['model']==mid];files=[f for r in group for f in r['submitted_files']]
        by_model.append({'model':mid,'planned':sum(j['model']==mid for j in cfg['jobs']),'started':len(group),'finished':sum(r['status']!='running' for r in group),
            'submitted':sum(r['status']=='submitted' for r in group),'status_counts':dict(Counter(r['mechanical_attribution'] for r in group)),
            'bounded_documents':sum(f['page_requirement_met'] is not None for f in files),
            'bounded_documents_within_limit':sum(f['page_requirement_met'] is True for f in files),
            'reported_api_cost_usd':sum(r['reported_api_cost_usd'] for r in group),
            'unresolved_cost_records':sum(r['unresolved_cost_records'] for r in group),
            'human_acceptance':None,'consequential_errors':None})
    frozen_ok=all(sha(ROOT/p)==h for p,h in cfg['input_hashes'].items())
    if cfg['id']=='native-transport-02':
        frozen_ok=frozen_ok and sha(ROOT/'scripts/run_native_transport_recovery.py')==cfg['script_sha256'] and sha(ROOT/'config/native_workflow_01.json')==cfg['parent_config_sha256']
    snapshot=load(ROOT/'output/evidence_upgrade_01/prior_evidence_hashes.json')
    # The protected snapshot may wrap paths under a descriptive key.
    hashes=snapshot.get('files',snapshot) if isinstance(snapshot,dict) else snapshot
    if isinstance(hashes,list): protected_ok=all(sha(ROOT/x['path'])==x['sha256'] for x in hashes)
    else: protected_ok=all(sha(ROOT/p)==h for p,h in hashes.items())
    transport_events=[json.loads(line) for line in (out/'transport_events.jsonl').read_text().splitlines()] if (out/'transport_events.jsonl').exists() else []
    extra_unresolved=sum(e.get('extra_unresolved_charge_record') is True for e in transport_events)
    cost=sum(x['actual_cost_usd'] or 0 for x in ledger);unresolved=sum(x['status']!='actual' for x in ledger)+extra_unresolved
    prior=cfg['prior_api_spend']
    if cfg['id']=='native-transport-02':prior+=sum(x['actual_cost_usd'] or 0 for x in load(OUT/'ledger.json'))
    result={'schema':'native-development-audit-v1','stage':cfg['id'],'as_of':datetime.now(timezone.utc).isoformat(),
        'planned_attempts':len(cfg['jobs']),'started_attempts':len(rows),'finished_attempts':sum(r['status']!='running' for r in rows),
        'submitted_attempts':sum(r['status']=='submitted' for r in rows),
        'attempts_with_authored_native_files':sum(r['authored_native_file_count']>0 for r in rows),
        'complete':len(rows)==len(cfg['jobs']) and all(r['status']!='running' for r in rows),
        'execution_finished':(out/'run_summary.json').exists() and all(r['status']!='running' for r in rows),
        'source_families':len({j['family_id'] for j in cfg['jobs']}),
        'conditions':sorted({j['instance_id'].rsplit('__',1)[-1] for j in cfg['jobs']}),'repeats_per_model_family':1,
        'frozen_inputs_unchanged':frozen_ok,'protected_historical_records_unchanged':protected_ok,
        'cost':{'reported_new_usd':cost,'reported_prior_usd':prior,
            'reported_cumulative_usd':cost+prior,'unresolved_records':unresolved,'extra_unresolved_retry_charge_records':extra_unresolved,
            'billing_reconciled':unresolved==0,'spending_authorization':cfg['authorization'],
            'review_and_correction_labor_usd':None,'total_cost_per_accepted_deliverable':None},
        'by_model':by_model,'runs':rows,
        'limits':[
            'Engineering submission is not human acceptance or absence of consequential errors.',
            'Inspected development families; no independently validated task gold or commercial rights attestations.',
            cfg['interpretation'],
            'Common high reasoning and limits do not equalize internal compute. Model aliases may move; returned identifiers are logged.',
            'Inputs are text/table extracts. Output tools use a restricted native writer and spreadsheet engine, not arbitrary Office software.',
            'Solver prompts disclose audit-field names, which cue relevant facts. Search is local lexical matching; clarification uses recorded keyword-matched replies, not a live stakeholder.',
            'Current-revision image exposure establishes delivery to the model, not visual comprehension.',
            'Provider errors can leave charges unresolved. Reported totals are not a reconciled invoice.',
            'No human acceptance, calibrated native judge, model winner or training improvement established.'
        ]}
    write(out/'engineering_audit.json',result)
    print(json.dumps({k:result[k] for k in ('complete','finished_attempts','submitted_attempts','frozen_inputs_unchanged','protected_historical_records_unchanged','cost')}))
    return result

if __name__=='__main__':summarize()
