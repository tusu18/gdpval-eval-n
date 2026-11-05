"""Versioned model-generic exact saved-request continuation; no implicit retry.

Two explicit reasons only: replay one recorded TLS-failed logical request, or
send a budget-blocked request that has no physical dispatch. Originals remain
immutable; inherited turns, tools, workspace and unacknowledged images persist.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, shutil, tempfile, time
from pathlib import Path

from run_evaluation_v2 import ROOT, OUT, BudgetStop, canonical, digest, image_part, now, read, write, tools_responses
from extend_evaluation_v2_models import ExtensionClient, freeze_extension, tasks_and_models, planned_cells, phase_gates, grade_attempt_complete
from recover_evaluation_v2 import file_hashes, assert_hashes, replace_owned_paths
from evaluation_v2_workspace import SYSTEM, TOOLS
from evaluation_v2_verified_sonnet_budget import SonnetImageReservationMixin, EVIDENCE as SONNET_EVIDENCE

ALLOCATION = ROOT / 'config/evaluation_v2_solver_allocation_release.json'


def core_grade_gate():
    cfg, tasks, _ = tasks_and_models()
    initial = phase_gates(cfg, tasks)
    base = read(ROOT / 'config/evaluation_v2_run.json')
    selected = []
    for task_id in tasks:
        stem = task_id + '__' + base['primary_model'].replace('/', '_')
        primary = OUT / 'runs' / (stem + '__primary') / 'result.json'
        paths = [primary]
        if read(primary)['status'] != 'submitted':
            paths = [p for p in (OUT / 'runs').glob(stem + '__*/result.json')
                     if ('__recovery' in p.parent.name or p.parent.name.endswith('__adapter_repair'))
                     and read(p)['status'] == 'submitted']
        path = max(paths, key=lambda p: read(p).get('completed_at', '')) if paths else None
        complete = bool(path and read(path)['status'] == 'submitted' and
                        grade_attempt_complete({'run_id': path.parent.name}, base['primary_judge']))
        selected.append({'task_id': task_id, 'effective_run_id': path.parent.name if path else None,
                         'solver_result_sha256': digest(path) if path else None,
                         'primary_judge_attempt_complete': complete})
    return {'ready': initial['ready'] and all(x['primary_judge_attempt_complete'] for x in selected),
            'original_phase_gates': initial, 'effective_deliverables': selected,
            'interpretation': 'Completed grading attempt includes invalid judgment; this is not evidence of judge validity or human acceptance.'}


class ReleasedAllocationClient(SonnetImageReservationMixin, ExtensionClient):
    def __init__(self, key_file):
        super().__init__(key_file)
        amendment = read(ALLOCATION)
        if amendment['authorized_total_usd'] != 30 or amendment['solver_ceiling_usd'] != 30:
            raise ValueError('This version authorizes only the explicit $30 total and solver allocation')
        if not core_grade_gate()['ready']:
            raise ValueError('Core effective-deliverable grading gate is not complete')
        self.cfg['authorized_available_budget_usd'] = 30
        self.cfg['solver_ceiling_usd'] = 30


def expected_body(model, history):
    cfg = read(ROOT / 'config/evaluation_v2_run.json')
    if model.startswith('openai/'):
        body = {'model': model, 'instructions': SYSTEM, 'input': history, 'tools': tools_responses(TOOLS),
                'max_output_tokens': cfg['max_output_tokens_per_turn'], 'reasoning': {'effort': cfg['reasoning_effort']}, 'store': False}
    else:
        body = {'model': model, 'messages': history, 'tools': TOOLS,
                'max_tokens': cfg['max_output_tokens_per_turn'], 'reasoning': {'effort': cfg['reasoning_effort']}, 'usage': {'include': True}}
    pricing = next(m['pricing'] for m in read(ROOT / 'data/evaluation_v2/model-catalog.json')['models'] if m['id'] == model)
    body['provider'] = {'allow_fallbacks': False, 'require_parameters': True,
                        'max_price': {'prompt': float(pricing['prompt'])*1e6, 'completion': float(pricing['completion'])*1e6}}
    return body


def inspect(parent_name):
    if Path(parent_name).name != parent_name:
        raise ValueError('Use a run ID, not a path')
    parent = OUT / 'runs' / parent_name
    result, cp, state = [read(parent / p) for p in ('result.json', 'checkpoint.json', 'workspace/state.json')]
    cfg, tasks, models = tasks_and_models()
    chain = []
    name = parent_name
    while True:
        if name in [a['run_id'] for a in chain]:
            raise ValueError('Cyclic continuation ancestry')
        path = OUT / 'runs' / name / 'result.json';record = read(path)
        chain.append({'run_id': name, 'result_path': str(path), 'sha256': digest(path),
                      'known_cost_usd': record.get('known_cost_usd', 0),
                      'unresolved_reserved_usd': record.get('unresolved_reserved_usd', 0),
                      'failed_call_id': record.get('failed_call_id')})
        prior = record.get('recovery_of') or record.get('continuation_of')
        if not prior:
            break
        name = prior
    chain.reverse()
    if chain[0]['run_id'] not in {c['run_id'] for c in planned_cells(cfg, 'supplemental')}:
        raise ValueError('Continuation must originate in one of the frozen16 supplemental cells')
    model = result['model'];responses = model.startswith('openai/');route = 'responses' if responses else 'chat/completions'
    if cp['state'] != 'before_request' or state.get('submitted'):
        raise ValueError('Parent must be unsubmitted with a saved pre-request checkpoint')
    limit = read(ROOT / 'config/evaluation_v2_run.json')
    if not 0 <= cp['turn'] < limit['max_turns'] or result['tool_calls'] >= limit['max_tool_calls']:
        raise ValueError('Original turn/tool allowance has no remaining continuation')
    acknowledged = cp.get('inherited_calls', []) + cp['calls']
    if len(acknowledged) != len(set(acknowledged)) or len(acknowledged) != cp['turn']:
        raise ValueError('Acknowledged response count does not match cumulative turn')
    for ident in acknowledged:
        if read(OUT / 'calls' / ident / 'reservation.json')['status'] != 'response_recorded':
            raise ValueError('Inherited call is not a recorded successful response')
    local_tools = sum(len(read(p)['tool_calls']) for p in parent.glob('turn-*.json'))
    if result['tool_calls'] != result.get('inherited_tool_calls', 0) + local_tools:
        raise ValueError('Inherited plus local tool counters do not reconcile')
    if cp.get('tool_calls', result['tool_calls']) != result['tool_calls']:
        raise ValueError('Checkpoint tool counter mismatch')
    label = f"{parent_name}:turn{cp['turn']+1}"
    physical = [p.parent for p in (OUT / 'calls').glob('*/reservation.json') if read(p).get('label') == label]
    built = expected_body(model, cp['history'])
    failed = None
    if result['status'] == 'infrastructure_or_adapter_failure':
        if len(physical) != 1:
            raise ValueError('Expected one failed physical dispatch for this logical request')
        folder = physical[0];reservation = read(folder / 'reservation.json');response = read(folder / 'response.json')
        if reservation['status'] != 'failed_unknown_charge' or reservation['route'] != route:
            raise ValueError('Only separately recorded failed-unknown-charge request is eligible')
        if response.get('status') is not None or 'bad record mac' not in response.get('transport_error', '').lower():
            raise ValueError('Only the audited TLS bad-record-MAC transport failure is eligible')
        request = read(folder / 'request.json');failed = folder.name
        if hashlib.sha256(canonical(request).encode()).hexdigest() != reservation['request_sha256']:
            raise ValueError('Saved failed request hash changed')
        kind = 'transport_recovery'
    elif result['status'] == 'budget_limited':
        if physical:
            raise ValueError('Budget-blocked request already has a physical dispatch')
        request = built;reservation = None;kind = 'budget_continuation'
        if not acknowledged:
            raise ValueError('Budget continuation requires preceding acknowledged request settings')
        prior_request = read(OUT / 'calls' / acknowledged[-1] / 'request.json')
        prior_request['input' if responses else 'messages'] = cp['history']
        if canonical(prior_request) != canonical(request):
            raise ValueError('Reconstructed budget-blocked request differs from preceding frozen settings')
    else:
        raise ValueError('Only infrastructure failure or budget stop may be continued')
    if canonical(request) != canonical(built):
        raise ValueError('Saved request differs from frozen model settings/history/tools')
    request_hash = hashlib.sha256(canonical(request).encode()).hexdigest()
    if failed:
        for ancestor in chain:
            previous_failed = ancestor.get('failed_call_id')
            if previous_failed and read(OUT / 'calls' / previous_failed / 'reservation.json')['request_sha256'] == request_hash:
                raise ValueError('A prior ancestor already replayed this failed logical request')
    pending = copy.deepcopy(cp.get('pending_images', state.get('image_queue', [])))
    content = cp['history'][-1].get('content', [])
    if not isinstance(content, list):content = []
    labels = [json.loads(x['text']) for x in content if x['type'] == ('input_text' if responses else 'text')]
    encoded = [x for x in content if x['type'] == ('input_image' if responses else 'image_url')]
    if labels != [{k:v for k,v in x.items() if k != 'path'} for x in pending]:
        raise ValueError('Pending-image labels do not match saved history')
    if encoded != [image_part(x['path'], responses) for x in pending]:
        raise ValueError('Pending-image bytes differ from saved history')
    state = copy.deepcopy(state);state['image_queue'] = pending
    # A fixed suffix prevents alternate aliases replaying the same parent twice.
    target = parent_name + '__' + kind
    protected = {}
    for ancestor in chain:protected.update(file_hashes(OUT / 'runs' / ancestor['run_id']))
    if failed:protected.update(file_hashes(OUT / 'calls' / failed))
    return {'parent':parent, 'parent_name':parent_name, 'run_id':target, 'kind':kind,
            'task':read(parent/'task.json'), 'result':result, 'checkpoint':cp, 'state':state,
            'request':request, 'request_sha256':request_hash, 'reservation':reservation,
            'failed_call_id':failed, 'route':route, 'responses':responses,
            'acknowledged':acknowledged, 'chain':chain, 'protected':protected}


def offline_budget_plan(info):
    # Deliberately bypass credential constructor: read-only arithmetic, no key/API.
    client = object.__new__(ReleasedAllocationClient)
    client.root = OUT
    client.models = {m['id']:m for m in read(ROOT/'data/evaluation_v2/model-catalog.json')['models']}
    bound = client.reservation(info['request']);totals = client.totals()
    return {'first_request_reserved_usd':bound, 'current_ledger_totals':totals,
            'global_ceiling_usd':30, 'released_solver_ceiling_usd':30,
            'global_headroom_before_request_usd':30-totals['committed_usd'],
            'first_request_fits_current_headroom':totals['committed_usd']+bound<=30,
            'not_a_total_completion_cost_estimate':True,
            'unknown_charges_released_usd':0}


def prepare(info):
    extension_freeze = freeze_extension()
    config = {'schema':'evaluation-v2-generic-saved-request-continuation-v1',
              'parent_run':info['parent_name'], 'run_id':info['run_id'], 'kind':info['kind'],
              'stage':'supplemental', 'recovery_stage':'recovery',
              'model':info['request']['model'], 'route':info['route'],
              'failed_call_id':info['failed_call_id'], 'request_sha256':info['request_sha256'],
              'resume_turn_zero_based':info['checkpoint']['turn'],
              'inherited_tool_calls':info['result']['tool_calls'],
              'pending_images':len(info['state']['image_queue']),
              'physical_replays_of_failed_request':int(bool(info['failed_call_id'])),
              'budget_blocked_first_dispatch':not bool(info['failed_call_id']),
              'chain':info['chain'], 'original_turn_tool_limits_continue':True,
              'original_results_and_unknown_reserves_retained':True,
              'request_settings_changed':False, 'automatic_retries':0,
              'protected_input_hashes':info['protected']}
    path = ROOT/'config/evaluation_v2_saved_request_continuations'/(info['run_id']+'.json')
    if path.exists():
        if read(path)!=config:raise ValueError('Prepared continuation inputs changed')
    else:write(path,config)
    files=[Path(__file__).resolve(),ALLOCATION,path,Path(extension_freeze),ROOT/'scripts/extend_evaluation_v2_models.py',ROOT/'scripts/recover_evaluation_v2.py',ROOT/'scripts/evaluation_v2_verified_sonnet_budget.py',SONNET_EVIDENCE]
    hashes={str(p.relative_to(ROOT)):digest(p) for p in files}
    target=OUT/'saved-request-continuations'/info['run_id']/'freeze.json'
    record={'files':hashes,'protected_input_hashes':info['protected']}
    if target.exists():
        previous=read(target)
        if any(previous[k]!=v for k,v in record.items()):raise ValueError('Continuation freeze changed')
    else:write(target,{'created_at':now(),**record})
    assert_hashes(hashes);assert_hashes(info['protected'])
    return target


def execute(info, client, freeze_path=None):
    from evaluation_v2_compat_workspace import install_compatibility_adapter
    install_compatibility_adapter()
    from evaluation_v2_workspace import Workspace
    folder=client.root/'runs'/info['run_id']
    if (folder/'result.json').exists():return read(folder/'result.json')
    if folder.exists():raise ValueError('Continuation already started; inspect checkpoint, no implicit repeat')
    folder.mkdir(parents=True)
    write(folder/'task.json',info['task'])
    shutil.copytree(info['parent']/'workspace',folder/'workspace')
    state=replace_owned_paths(info['state'],str(info['parent']/'workspace'),str(folder/'workspace'))
    write(folder/'workspace/state.json',state)
    shutil.copyfile(info['parent']/'checkpoint.json',folder/'inherited-checkpoint.json')
    shutil.copyfile(info['parent']/'result.json',folder/'inherited-result.json')
    ws=Workspace(info['task'],folder/'workspace')
    pending=list(ws.image_queue);ws.image_queue.clear();ws._persist()
    history=copy.deepcopy(info['checkpoint']['history']);cfg=client.cfg
    result={'task_id':info['task']['task_id'],'occupation':info['task']['occupation'],
            'model':info['request']['model'],'stage':'supplemental','recovery_stage':'recovery',
            'recovery_of':info['parent_name'],'continuation_of':info['parent_name'],
            'continuation_kind':info['kind'],'failed_call_id':info['failed_call_id'],
            'failed_logical_request_sha256':info['request_sha256'] if info['failed_call_id'] else None,
            'first_continuation_request_sha256':info['request_sha256'],'run_id':info['run_id'],
            'started_at':now(),'status':'running','calls':[],
            'inherited_calls':info['acknowledged'],'inherited_model_responses':len(info['acknowledged']),
            'inherited_tool_calls':info['result']['tool_calls'],'tool_calls':info['result']['tool_calls'],
            'resume_turn_zero_based':info['checkpoint']['turn'],'artifact_paths':[], 'human_acceptance':None,
            'recovery_chain':info['chain'],'original_supplemental_run':info['chain'][0]['run_id'],
            'inherited_known_cost_usd':sum(x['known_cost_usd'] for x in info['chain']),
            'inherited_unresolved_reserved_usd':sum(x['unresolved_reserved_usd'] for x in info['chain']),
            'original_failure_retained':True,'recovery_freeze':str(freeze_path) if freeze_path else None,
            'cost_scope':'calls/known_cost_usd contain new continuation calls only; inherited totals are separate and must not be double counted.'}
    started=time.monotonic()
    try:
        for turn in range(info['checkpoint']['turn'],cfg['max_turns']):
            body=copy.deepcopy(info['request']);body['input' if info['responses'] else 'messages']=history
            if turn==info['checkpoint']['turn'] and canonical(body)!=canonical(info['request']):
                raise ValueError('First continuation request changed')
            write(folder/'checkpoint.json',{'state':'before_request','turn':turn,'history':history,
                  'calls':result['calls'],'inherited_calls':result['inherited_calls'],
                  'pending_images':pending,'tool_calls':result['tool_calls']})
            data,meta=client.call(body,info['route'],scope='solver_recovery',label=f"{info['run_id']}:turn{turn+1}")
            result['calls'].append(meta['call_id'])
            if pending:ws.acknowledge_images(pending)
            pending=[]
            if info['responses']:
                outputs=data.get('output',[]);history.extend(outputs)
                calls=[{'id':x['call_id'],'function':{'name':x['name'],'arguments':x['arguments']}} for x in outputs if x.get('type')=='function_call']
                finish=(data.get('incomplete_details') or {}).get('reason')
            else:
                choice=(data.get('choices') or [{}])[0];message=choice.get('message') or {}
                history.append({k:v for k,v in message.items() if k in ('role','content','tool_calls','reasoning_details')})
                calls=message.get('tool_calls') or [];finish=choice.get('finish_reason')
            write(folder/f'turn-{turn+1:02d}.json',{'call_id':meta['call_id'],'finish_reason':finish,
                  'tool_calls':calls,'response_id':data.get('id'),'served_provider':data.get('provider')})
            if not calls:
                result['status']='output_token_limit' if finish in ('length','max_output_tokens') else 'ended_without_submission';break
            for call in calls:
                result['tool_calls']+=1
                if result['tool_calls']>cfg['max_tool_calls']:raise RuntimeError('Original tool limit reached')
                try:reply=ws.call(call['function']['name'],json.loads(call['function']['arguments']))
                except Exception as exc:reply={'error':str(exc)[:1000]}
                text=json.dumps(reply,ensure_ascii=False)
                history.append({'type':'function_call_output','call_id':call['id'],'output':text} if info['responses'] else {'role':'tool','tool_call_id':call['id'],'content':text})
            pending=list(ws.image_queue);ws.image_queue.clear();ws._persist()
            if pending:
                content=[]
                for item in pending:
                    content.extend([{'type':'input_text' if info['responses'] else 'text','text':json.dumps({k:v for k,v in item.items() if k!='path'})},image_part(item['path'],info['responses'])])
                history.append({'role':'user','content':content})
            write(folder/'checkpoint.json',{'state':'ready_next_turn','turn':turn+1,'history':history,
                  'calls':result['calls'],'inherited_calls':result['inherited_calls'],
                  'pending_images':pending,'tool_calls':result['tool_calls']})
            if ws.submitted:
                result['status']='submitted';result['submission']=ws.submitted
                result['artifact_paths']=[x['path'] for x in ws.submitted];break
        else:result['status']='turn_limit'
    except BudgetStop as exc:result.update(status='budget_limited',error=str(exc))
    except Exception as exc:result.update(status='infrastructure_or_adapter_failure',error=str(exc)[:1500])
    records=[read(p) for p in (client.root/'calls').glob('*/reservation.json') if read(p).get('label','').startswith(info['run_id']+':')]
    result.update(calls=[x['id'] for x in records],completed_at=now(),continuation_elapsed_seconds=round(time.monotonic()-started,3),
                  known_cost_usd=sum(x.get('actual_cost_usd') or 0 for x in records),
                  unresolved_calls=sum(x.get('actual_cost_usd') is None for x in records),
                  unresolved_reserved_usd=sum(x['reserved_usd'] for x in records if x.get('actual_cost_usd') is None),workspace=str(folder/'workspace'))
    assert_hashes(info['protected']);write(folder/'result.json',result);return result


def self_test(info):
    initial_views={k:v['viewed_pages'] for k,v in info['state']['files'].items()}
    class Dummy:
        def __init__(self,root,fail):
            self.root=Path(root);self.fail=fail;self.cfg=read(ROOT/'config/evaluation_v2_run.json');self.calls=0
        def call(self,body,route,scope,label):
            self.calls+=1
            assert self.calls==1 and canonical(body)==canonical(info['request']) and route==info['route']
            assert label.endswith(':turn'+str(info['checkpoint']['turn']+1))
            current=read(self.root/'runs'/info['run_id']/'workspace/state.json')
            assert {k:v['viewed_pages'] for k,v in current['files'].items()}==initial_views
            write(self.root/'calls'/'offline'/'reservation.json',{'id':'offline','label':label,'reserved_usd':1,
                  'actual_cost_usd':None if self.fail else 0})
            if self.fail:raise RuntimeError('Offline transport failure')
            return ({'output':[]} if info['responses'] else {'choices':[{'message':{'role':'assistant','content':''},'finish_reason':'stop'}]}),{'call_id':'offline'}
    for fail in (False,True):
        with tempfile.TemporaryDirectory(prefix='v2-generic-continuation-') as tmp:
            c=Dummy(tmp,fail);r=execute(info,c)
            assert c.calls==1 and r['tool_calls']==info['result']['tool_calls']
            assert r['inherited_model_responses']==info['checkpoint']['turn']
            assert r['status']==('infrastructure_or_adapter_failure' if fail else 'ended_without_submission')
            state=read(Path(tmp)/'runs'/info['run_id']/'workspace/state.json')
            if fail:assert {k:v['viewed_pages'] for k,v in state['files'].items()}==initial_views
            else:
                for p in info['state']['image_queue']:
                    f=state['files'].get(p.get('filename'))
                    if f and f['revision']==p['revision']:assert p['page'] in f['viewed_pages']
            assert_hashes(info['protected'])
    return {'status':'passed','paid_calls':0,'run_id':info['run_id'],'route':info['route'],
            'checks':['exact first request and original turn','pending views acknowledged only after response',
                      'inherited tool/response counters preserved','original files unchanged','unknown failed charge retained']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--parent-run',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--key-file');p.add_argument('--self-test',action='store_true')
    a=p.parse_args();info=inspect(a.parent_run)
    if a.self_test:
        if a.execute:p.error('Self-test cannot dispatch')
        print(json.dumps(self_test(info)));return
    freeze_path=prepare(info);plan={'run_id':info['run_id'],'kind':info['kind'],'route':info['route'],
           'resume_turn':info['checkpoint']['turn']+1,'inherited_tool_calls':info['result']['tool_calls'],
           'pending_images':len(info['state']['image_queue']),'request_sha256':info['request_sha256'],
           'freeze_path':str(freeze_path),'gate':core_grade_gate(),'budget':offline_budget_plan(info),'execute_requested':a.execute}
    write(OUT/'saved-request-continuations'/info['run_id']/('dispatch-plan-'+now().replace(':','-')+'.json'),plan)
    if not a.execute:print(json.dumps(plan,indent=2));return
    if not a.key_file:p.error('--execute requires --key-file')
    if not plan['gate']['ready']:raise SystemExit('No paid calls: core grading allocation-release gate incomplete')
    if not plan['budget']['first_request_fits_current_headroom']:raise SystemExit('No paid calls: first exact request does not fit unchanged $30 global ceiling')
    client=ReleasedAllocationClient(a.key_file);result=execute(info,client,freeze_path)
    print(json.dumps({'run_id':result['run_id'],'status':result['status'],'new_known_cost_usd':result['known_cost_usd'],
                      'new_unresolved_reserved_usd':result['unresolved_reserved_usd'],'budget':client.totals()}),flush=True)


if __name__=='__main__':main()
