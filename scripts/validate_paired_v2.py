"""Independent executable arithmetic checks, not independent expert validation."""
import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from workflow_workspace import Workspace, initial_message

ROOT = Path(__file__).resolve().parents[1]

def oracle(inputs):
    if inputs['kind'] == 'landed_cost':
        a = Decimal(str(inputs['quantity']))*Decimal(str(inputs['unit_a']))+Decimal(str(inputs['freight_a']))
        b = Decimal(str(inputs['quantity']))*Decimal(str(inputs['unit_b']))+Decimal(str(inputs['freight_b']))
        return {'supplier': 'Alder' if a < b else 'Beacon', 'alder_total_usd': float(a), 'beacon_total_usd': float(b), 'savings_vs_alder_usd': float(a-b)}
    if inputs['kind'] == 'capacity':
        effort = sum(inputs['ordered_efforts'])
        return {'required_hours': effort, 'confirmed_capacity_hours': inputs['confirmed_capacity'], 'uncovered_hours': max(0,effort-inputs['confirmed_capacity']), 'launch_can_be_committed': effort <= inputs['confirmed_capacity']}
    if inputs['kind'] == 'appointment':
        deadline = datetime.fromisoformat(inputs['deadline'])
        feasible = [o for o in inputs['options'] if datetime.fromisoformat(o['arrival']) <= deadline]
        if not feasible:
            return {'service': None}
        chosen = min(feasible,key=lambda x:x['cost'])
        ground = next(x for x in inputs['options'] if x['service']=='Ground')
        return {'service': chosen['service'], 'shipping_cost_usd': chosen['cost'], 'latest_arrival_local': inputs['deadline'], 'incremental_cost_vs_ground_usd': chosen['cost']-ground['cost']}
    raise ValueError('unknown_oracle_kind')

def validate(root=ROOT):
    protocol = json.loads((root/'config/paired_v2/protocol.json').read_text())
    checks = []
    def check(name, condition, detail):
        checks.append({'check':name,'passed':bool(condition),'detail':detail})
    for rel, digest in protocol['input_hashes'].items():
        check('candidate_input_hash',sha256((root/rel).read_bytes()).hexdigest()==digest,rel)
    v1 = json.loads((root/'config/paired_protocol.v1.json').read_text())
    check('v1_frozen_inputs_unchanged',all(sha256((root/p).read_bytes()).hexdigest()==h for p,h in v1['input_hashes'].items()),'No solver inputs, source truths or v1 protocol were repaired in place.')
    rubrics = json.loads((root/'data/paired_v2/grader/rubrics.json').read_text())
    for rubric in rubrics:
        family = rubric['id']
        tasks = [json.loads((root/'data/paired_v2/solver'/f'{family}__{v}.json').read_text()) for v in ['baseline','recovery','conflict']]
        check('same_workspace_across_conditions',all(t['workspace']==tasks[0]['workspace'] and t['clarifications']==tasks[0]['clarifications'] for t in tasks),family)
        check('same_deliverable_contract',len({(t['deliverable_count'],t['deliverable_format']) for t in tasks})==1,family)
        check('no_grader_fields_in_solver',all(not any(k in t for k in ['truth','rubric','oracle_inputs']) for t in tasks),family)
        for task in tasks:
            env=Workspace(task)
            results=env.call('search_files',{'query':'approved record project'})['results']
            check('search_returns_real_paths',bool(results) and all(r['path'] in task['workspace'] for r in results),task['instance_id'])
            check('private_path_denied','error' in env.call('read_file',{'path':'../grader/rubrics.json'}),task['instance_id'])
        if rubric.get('oracle_inputs'):
            check('separate_arithmetic_oracle',oracle(rubric['oracle_inputs'])==rubric['truth'],family)
    ev=[json.loads((root/'data/paired_v2/solver'/f'ev_localization__{v}.json').read_text()) for v in ['baseline','recovery','conflict']]
    check('ev_cost_assumption_identical',len({t['attachments']['scenario-unit-cost-assumption.txt'] for t in ev})==1,'Shared fixed per-pack assumption is explicit and labeled synthetic.')
    check('ev_price_volume_phrase_removed',all('overheads for an annual projected volume' not in t['prompt'] for t in ev),'Forecast and unit cost no longer share the mutated source clause.')
    expected_ev = {'unit_savings_inr':(Decimal(10000)-Decimal(8500))*Decimal(83)-Decimal(20000)-Decimal(590)}
    ev_truth = next(r['truth'] for r in rubrics if r['id']=='ev_localization')
    check('ev_recomputed_savings',float(expected_ev['unit_savings_inr'])==ev_truth['unit_savings_inr'] and float(expected_ev['unit_savings_inr']*110000*5)==ev_truth['five_year_savings_inr'],'Independent Decimal derivation from component prices and approved forecast.')
    shipment=json.loads((root/'data/paired_v2/solver/original_delivery_appointment__recovery.json').read_text())
    msg=initial_message(shipment)
    check('clarification_not_leaked_in_initial_prompt','2026-11-06 at 16:00' not in msg and 'latest_arrival_local' in msg,'Field name is visible; its answer is not.')
    check('clarification_reachable','2026-11-06 at 16:00' in Workspace(shipment).call('ask_requester',{'question':'What is the latest receiving deadline?'})['answer'],'Scripted stakeholder confirms a fact, not a new approval.')
    return {'status':'automated_preflight_pass' if all(c['passed'] for c in checks) else 'automated_preflight_failed','checks':checks,'independent_expert_validation':False,'paid_model_runs':0,'warning':'Executable checks establish internal consistency and access controls. They do not establish workplace realism, semantic equivalence, rights clearance or expert acceptance.'}

if __name__ == '__main__':
    result=validate()
    path=ROOT/'output/paired_v2/preflight.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'} | {'checks':len(result['checks'])}))
    raise SystemExit(0 if result['status']=='automated_preflight_pass' else 1)
