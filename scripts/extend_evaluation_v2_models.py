"""Prepare or dispatch a fixed matched-task supplemental model extension.

No paid request without --execute. Original solver code, prompts, references and
model settings are unchanged. All costs use the existing global ledger.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from io import BytesIO
from pathlib import Path

from dispatch_evaluation_v2_remaining import amended_client
from run_evaluation_v2 import Client, ROOT, OUT, canonical, digest, freeze, now, read, solve, write

CONFIG = ROOT / 'config/evaluation_v2_model_extension.json'
EVIDENCE = ROOT / 'docs/evaluation_v2/extension-image-budget-evidence.json'
SMALL_IMAGE_MODELS = {'openai/gpt-6-astra', 'openai/gpt-5.6-sol'}


def verified_small_image(item):
    """Decode before using the named-model pixel bound; no request mutation."""
    from PIL import Image
    url = item.get('image_url')
    if isinstance(url, dict):
        url = url.get('url')
    if not isinstance(url, str) or not url.startswith('data:image/'):
        return False
    try:
        header, encoded = url.split(',', 1)
        if header not in {'data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64', 'data:image/gif;base64'}:
            return False
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(raw)) as image:
            width, height = image.size
            bounded = (1 <= width <= 1024 and 1 <= height <= 1024 and getattr(image, 'n_frames', 1) == 1)
            image.verify()
        return bounded
    except Exception:
        return False


class ExtensionClient(Client):
    def __init__(self, key_file):
        # Preserve the same credential checks, config amendment and root ledger.
        base = amended_client(key_file)
        self.__dict__.update(base.__dict__)

    def reservation_detail(self, body):
        pricing = self.models[body['model']]['pricing']
        image_tokens = 0
        verified = fallback = 0
        def text_only(value):
            nonlocal image_tokens, verified, fallback
            if isinstance(value, dict):
                if value.get('type') in ('input_image', 'image_url'):
                    if body['model'] in SMALL_IMAGE_MODELS and verified_small_image(value):
                        image_tokens += 4096
                        verified += 1
                    else:
                        image_tokens += 40000
                        fallback += 1
                    return {'image_omitted_from_text_token_bound': True}
                return {key: text_only(item) for key, item in value.items()}
            if isinstance(value, list):
                return [text_only(item) for item in value]
            return value
        clean = text_only(body)
        tokens = len(canonical(clean).encode()) + 2048 + image_tokens
        ip = max(float(pricing.get(key, 0)) for key in ('prompt', 'input_cache_write', 'input_cache_write_1h'))
        op = float(pricing['completion'])
        for tier in pricing.get('overrides', []):
            if tokens >= tier.get('min_prompt_tokens', math.inf):
                ip = max(ip, float(tier.get('prompt', 0)), float(tier.get('input_cache_write', 0)))
                op = max(op, float(tier.get('completion', 0)))
        maximum = body.get('max_output_tokens', body.get('max_tokens'))
        amount = round((tokens * ip + maximum * op + (verified + fallback) * float(pricing.get('image', 0))) * 1.05 + .002, 8)
        return {'reserved_usd': amount, 'input_token_bound': tokens,
                'verified_small_images': verified, 'fallback_images': fallback,
                'method': 'extension-image-bound-v1', 'evidence_sha256': digest(EVIDENCE)}

    def reservation(self, body):
        if body['model'] not in SMALL_IMAGE_MODELS:
            return super().reservation(body)
        return self.reservation_detail(body)['reserved_usd']


def tasks_and_models():
    cfg = read(CONFIG)
    tasks = {t['task_id']: t for t in map(json.loads, (ROOT / 'data/evaluation_v2/effective-inputs.jsonl').read_text().splitlines())}
    models = {m['id']: m for m in read(ROOT / 'data/evaluation_v2/model-catalog.json')['models']}
    for selected in cfg['tasks']:
        task = tasks[selected['task_id']]
        if task['occupation'] != selected['occupation'] or task['prompt'] != task['original_prompt']:
            raise ValueError('Selected task differs from the frozen original contract')
        if set(selected['formats']) != set(task['contract']['required_formats']):
            raise ValueError('Selected task formats changed')
    if len(tasks) != 15 or len(cfg['tasks']) != 4 or len(cfg['models']) != 4:
        raise ValueError('Expected the original 15-task primary and fixed 4x4 extension')
    for model in cfg['models']:
        if model not in models:
            raise ValueError('Requested model absent from frozen catalog: ' + model)
    return cfg, tasks, models


def run_name(task_id, model, stage):
    return task_id + '__' + model.replace('/', '_') + '__' + stage


def planned_cells(cfg, stage):
    return [{'task_id': task['task_id'], 'name': task['name'], 'model': model, 'stage': stage,
             'run_id': run_name(task['task_id'], model, stage)} for task in cfg['tasks'] for model in cfg['models']]


def cell_status(cell):
    folder = OUT / 'runs' / cell['run_id']
    result_path = folder / 'result.json'
    if result_path.is_file():
        result = read(result_path)
        return {**cell, 'status': result['status'], 'physical_requests': len(result.get('calls', [])),
                'known_cost_usd': result.get('known_cost_usd', 0), 'unresolved_reserved_usd': result.get('unresolved_reserved_usd', 0),
                'result_path': str(result_path), 'result_sha256': digest(result_path)}
    return {**cell, 'status': 'interrupted_requires_checkpoint_review' if folder.exists() else 'not_started', 'physical_requests': 0}


def physical_attempt_complete(cell):
    row = cell_status(cell)
    ids = read(row['result_path']).get('calls', []) if row.get('result_path') else []
    # Count actual dispatch records, not a budget stop or a prepared directory.
    dispatched = any((OUT / 'calls' / ident / 'response.json').is_file() for ident in ids)
    return bool(dispatched and row['status'] not in {'running', 'interrupted_requires_checkpoint_review'})


def grade_attempt_complete(cell, judge):
    path = OUT / 'grades' / (cell['run_id'] + '__' + judge.replace('/', '_')) / 'result.json'
    index = OUT / 'grade-resolution-index.json'
    if index.is_file():
        for entry in read(index).get('entries', []):
            if entry.get('solver_run_id') == cell['run_id'] and entry.get('judge_model') == judge:
                resolved = entry.get('effective_result_path')
                if not resolved:
                    return False
                resolved = Path(resolved).resolve()
                if not resolved.is_relative_to(OUT.resolve()) or not resolved.is_file() or digest(resolved) != entry.get('effective_result_sha256'):
                    return False
                original_path = Path(entry['original_result_path']).resolve()
                if not original_path.is_relative_to(OUT.resolve()) or digest(original_path) != entry.get('original_result_sha256'):
                    return False
                path = resolved
                break
    if not path.is_file():
        return False
    grade = read(path)
    # Invalid judgments remain invalid but do count as completed grading attempts.
    return grade.get('status') in {'graded', 'invalid_judgment', 'no_submission'}


def phase_gates(cfg, tasks, second=False):
    base = read(ROOT / 'config/evaluation_v2_run.json')
    primary = [{'task_id': task_id, 'model': base['primary_model'], 'stage': 'primary',
                'run_id': run_name(task_id, base['primary_model'], 'primary')} for task_id in tasks]
    missing_primary = [c['task_id'] for c in primary if not physical_attempt_complete(c)]
    missing_grades = [c['run_id'] for c in primary if not grade_attempt_complete(c, base['primary_judge'])]
    first = planned_cells(cfg, 'supplemental')
    missing_first = [c['run_id'] for c in first if not physical_attempt_complete(c)] if second else []
    missing_first_grades = [c['run_id'] for c in first if not grade_attempt_complete(c, base['primary_judge'])] if second else []
    shipping = OUT / 'runs' / '76418a2c-a3c0-4894-b89d-2493369135d9__openai_gpt-6.1-sol__adapter_repair' / 'result.json'
    shipping_ready = shipping.is_file() and read(shipping)['status'] == 'submitted'
    return {'ready': shipping_ready and not any((missing_primary, missing_grades, missing_first, missing_first_grades)),
            'primary_physically_attempted': 15 - len(missing_primary), 'primary_grading_attempts_recorded': 15 - len(missing_grades),
            'shipping_compatibility_repair_submitted': shipping_ready,
            'missing_primary_attempts': missing_primary, 'missing_primary_grades': missing_grades,
            'missing_first_pass_attempts': missing_first, 'missing_first_pass_grades': missing_first_grades}


def completed_baseline(task_id, model):
    primary = OUT / 'runs' / run_name(task_id, model, 'primary') / 'result.json'
    recoveries = [p for p in (OUT / 'runs').glob(run_name(task_id, model, 'recovery') + '*/result.json') if read(p)['status'] == 'submitted']
    recovery = max(recoveries, key=lambda p: len(read(p).get('recovery_chain', []))) if recoveries else None
    repair = OUT / 'runs' / run_name(task_id, model, 'adapter_repair') / 'result.json'
    basis = 'same_task_completed_run_known_cost'
    if primary.exists() and read(primary)['status'] == 'submitted':
        paths = [primary]
    elif repair.exists() and read(repair)['status'] == 'submitted':
        paths = [repair]
        basis = 'same_task_completed_adapter_repair_cost_prior_failed_primary_excluded_from_forecast_only'
    elif recovery:
        chain = read(recovery).get('recovery_chain')
        paths = [Path(x['result_path']) for x in chain] + [recovery] if chain else [primary, recovery]
    else:
        smoke = OUT / 'runs' / run_name(task_id, model, 'smoke') / 'result.json'
        paths = [smoke] if smoke.exists() and read(smoke)['status'] == 'submitted' else []
    if not paths:
        return None
    return {'basis': basis,
            'known_cost_usd': sum(read(p).get('known_cost_usd', 0) for p in paths),
            'additional_unresolved_reserved_usd': sum(read(p).get('unresolved_reserved_usd', 0) for p in paths),
            'records': [{'path': str(p), 'sha256': digest(p)} for p in paths]}


def cost_forecast(cfg, models):
    sol = 'openai/gpt-6.1-sol'
    baselines = {t['task_id']: completed_baseline(t['task_id'], sol) for t in cfg['tasks']}
    measured = [x for x in baselines.values() if x]
    fallback = max(measured, key=lambda x: x['known_cost_usd']) if measured else None
    for ident, basis in baselines.items():
        if basis is None and fallback:
            baselines[ident] = {**fallback, 'basis': 'imputed_from_largest_available_matched_completed_Sol_cost',
                               'limitation': 'This task has no completed measured Sol baseline yet.'}
    rows = []
    for model in cfg['models']:
        ratio = max(float(models[model]['pricing'][p]) / float(models[sol]['pricing'][p]) for p in ('prompt', 'completion'))
        low = sum(x['known_cost_usd'] for x in baselines.values()) * ratio if all(baselines.values()) else None
        rows.append({'model': model, 'first_pass_runs': 4, 'catalog_price_ratio_to_Sol': ratio,
                     'rough_known_cost_scaled_usd': round(low, 4) if low is not None else None,
                     'rough_twofold_planning_usd': round(low * 2, 4) if low is not None else None})
    return {'task_baselines': baselines, 'by_model': rows,
            'first_pass_rough_low_usd': round(sum(x['rough_known_cost_scaled_usd'] for x in rows), 4) if fallback else None,
            'first_pass_rough_twofold_usd': round(sum(x['rough_twofold_planning_usd'] for x in rows), 4) if fallback else None,
            'limitation': 'Price-ratio forecast only; token counts, tool turns, cache behavior and success vary. Unknown charges stay reserved separately. The 2x figure is not an upper bound; per-call reservation remains authoritative.'}


def runtime_access(cfg):
    result = {}
    for model in cfg['models']:
        route = 'responses' if model.startswith('openai/') else 'chat/completions'
        successful = []
        for path in (OUT / 'calls').glob('*/reservation.json'):
            row = read(path)
            if row.get('model') == model and row.get('route') == route and row.get('status') == 'response_recorded' and row.get('scope', '').startswith('solver'):
                request = read(path.parent / 'request.json')
                if request.get('tools'):
                    successful.append(row['id'])
        result[model] = {'catalog_listed': True, 'expected_route': route, 'native_solver_route_responded': bool(successful),
                         'successful_solver_call_ids': successful,
                         'interpretation': 'A successful response proves this route was reachable for that request; it does not guarantee task completion or future access.'}
    return result


def freeze_extension():
    freeze()
    from evaluation_v2_compat_workspace import freeze_compatibility
    compatibility_freeze = freeze_compatibility()
    paths = [Path(__file__).resolve(), CONFIG, EVIDENCE, ROOT / 'scripts/dispatch_evaluation_v2_remaining.py',
             ROOT / 'config/evaluation_v2_budget_amendment.json', ROOT / 'data/evaluation_v2/model-catalog.json',
             ROOT / 'data/evaluation_v2/effective-inputs.jsonl', OUT / 'freeze.json', compatibility_freeze,
             ROOT / 'scripts/evaluation_v2_compat_workspace.py', ROOT / 'scripts/evaluation_v2_compat_engine.mjs',
             ROOT / 'config/evaluation_v2_shipping_compatibility.json']
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    path = OUT / 'extension' / 'freeze.json'
    if path.exists():
        if read(path)['files'] != hashes:
            raise RuntimeError('Extension inputs changed after freeze; create an explicit new version')
    else:
        write(path, {'created_at': now(), 'files': hashes, 'request_bytes_changed': False,
                     'budget_method': 'extension-image-bound-v1', 'existing_unknown_reservations_changed': False})
    return path


def repeat_release(path, client, forecast):
    if not path:
        raise ValueError('Second pass requires --repeat-release with funded grading and bounded-check evidence')
    release = read(path)
    status = release.get('bounded_judge_checks_status')
    if status not in {'completed', 'funded'}:
        raise ValueError('Bounded judge checks must be completed or funded before repeats')
    fields = ('remaining_grading_reserve_usd', 'remaining_bounded_judge_checks_reserve_usd', 'contingency_reserve_usd')
    amounts = [release.get(key) for key in fields]
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in amounts):
        raise ValueError('Repeat release must record nonnegative remaining dollar reserves')
    if status == 'funded' and release['remaining_bounded_judge_checks_reserve_usd'] <= 0:
        raise ValueError('Funded, uncompleted judge checks require a positive reserve')
    if release['remaining_grading_reserve_usd'] <= 0:
        raise ValueError('Second-pass grading requires a positive remaining reserve')
    evidence = release.get('evidence_files', {})
    if not evidence or any(digest(ROOT / name) != value for name, value in evidence.items()):
        raise ValueError('Repeat release requires matching budget/check evidence file hashes')
    hold = sum(amounts)
    proposed_ceiling = client.cfg['authorized_available_budget_usd'] - hold
    projected = forecast['first_pass_rough_twofold_usd']
    if projected is None or client.totals()['committed_usd'] + projected > proposed_ceiling:
        raise ValueError('Second-pass rough forecast plus protected reserves does not fit the authorized total')
    client.cfg['authorized_available_budget_usd'] = proposed_ceiling
    client.cfg['solver_ceiling_usd'] = min(client.cfg['solver_ceiling_usd'], proposed_ceiling)
    return {'path': str(Path(path).resolve()), 'sha256': digest(path), 'protected_remaining_usd': hold,
            'effective_global_ceiling_usd': proposed_ceiling}


def self_test():
    from PIL import Image
    cfg, tasks, models = tasks_and_models()
    client = object.__new__(ExtensionClient)
    client.models = models
    def image(width, height):
        data = BytesIO(); Image.new('RGB', (width, height)).save(data, format='PNG')
        return {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode(), 'detail': 'low'}
    small, large = image(1024, 1024), image(1025, 1)
    assert verified_small_image(small) and not verified_small_image(large)
    assert not verified_small_image({'type': 'input_image', 'image_url': 'https://example.com/image.png'})
    assert not verified_small_image({'type': 'input_image', 'image_url': 'data:image/png;base64,bad!'})
    for model in models:
        body = {'model': model, 'input': [{'role': 'user', 'content': [small]}], 'max_output_tokens': 16384}
        before = canonical(body)
        original = Client.reservation(client, body)
        revised = client.reservation(body)
        assert canonical(body) == before
        assert (revised < original) if model in SMALL_IMAGE_MODELS else (revised == original)
    body = {'model': 'openai/gpt-6-astra', 'input': [large], 'max_output_tokens': 16384}
    assert client.reservation(body) == Client.reservation(client, body)
    assert len(planned_cells(cfg, 'supplemental')) == 16
    assert len({x['task_id'] for x in planned_cells(cfg, 'supplemental')}) == 4
    assert len({x['occupation'] for x in cfg['tasks']}) == 3
    assert {fmt for x in cfg['tasks'] for fmt in x['formats']} == {'xlsx', 'pptx', 'pdf', 'docx'}
    # Force the long-context tier using text, independent of image accounting.
    body = {'model': 'openai/gpt-6-astra', 'input': ['x' * 280000, small], 'max_output_tokens': 16384}
    detail = client.reservation_detail(body)
    assert detail['input_token_bound'] > 272000 and detail['reserved_usd'] > detail['input_token_bound'] * .000025
    return {'offline_self_test': 'passed', 'paid_calls': 0,
            'checks': ['four original tasks, three occupations, four formats', '16 unique first-pass cells',
                       'verified image dimension guard', 'invalid/large/external fallback', 'other model reservation unchanged',
                       'pricing tiers retained', 'request bytes unchanged']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--key-file')
    parser.add_argument('--phase', choices=['first', 'second'], default='first')
    parser.add_argument('--repeat-release')
    parser.add_argument('--acknowledge-stopped-run', action='append', default=[],
                        help='Explicitly retain a named prior blocked result and continue to unattempted cells; never retries that result')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        if args.execute:
            parser.error('--self-test cannot dispatch calls')
        print(json.dumps(self_test())); return
    cfg, tasks, models = tasks_and_models()
    stage = cfg['first_pass' if args.phase == 'first' else 'optional_second_pass']['stage']
    cells = planned_cells(cfg, stage)
    gates = phase_gates(cfg, tasks, second=args.phase == 'second')
    forecast = cost_forecast(cfg, models)
    plan = {'created_at': now(), 'phase': args.phase, 'stage': stage, 'planned_runs': len(cells),
            'tasks': cfg['tasks'], 'gates': gates, 'cost_forecast': forecast, 'runtime_access': runtime_access(cfg),
            'cells': [cell_status(cell) for cell in cells], 'execute_requested': args.execute}
    folder = OUT / 'extension'
    write(folder / ('plan-' + args.phase + '.json'), plan)
    table = ['Supplemental extension: 4 original tasks x 4 additional models = 16 first-pass runs.',
             'Optional second pass: 16 further runs; gated, not automatically scheduled.',
             'Model | First-pass runs | Price ratio to Sol | Rough known-cost scaling | 2x planning figure']
    for row in forecast['by_model']:
        table.append(f"{row['model']} | 4 | {row['catalog_price_ratio_to_Sol']:.2f} | {row['rough_known_cost_scaled_usd']} | {row['rough_twofold_planning_usd']}")
    table += ['', forecast['limitation'], '', f"Primary attempted: {gates['primary_physically_attempted']}/15; primary grading recorded: {gates['primary_grading_attempts_recorded']}/15.",
              'Incomplete cells remain listed in plan JSON. Wallet cash and key allowance are distinct; root verifies both before paid phases.']
    (folder / ('plan-' + args.phase + '.txt')).write_text('\n'.join(table) + '\n')
    print('\n'.join(table), flush=True)
    if not args.execute:
        return
    if not args.key_file:
        parser.error('--execute requires --key-file')
    if not gates['ready']:
        write(folder / ('blocked-' + args.phase + '.json'), {'created_at': now(), 'reason': 'Phase prerequisites incomplete', 'gates': gates})
        raise SystemExit('No paid calls: phase prerequisites are incomplete; see the plan JSON.')
    freeze_path = freeze_extension()
    from evaluation_v2_compat_workspace import install_compatibility_adapter
    install_compatibility_adapter()
    client = ExtensionClient(args.key_file)
    release = repeat_release(args.repeat_release, client, forecast) if args.phase == 'second' else None
    dispatch = {'created_at': now(), 'stage': stage, 'freeze_path': str(freeze_path), 'freeze_sha256': digest(freeze_path),
                'plan': plan, 'repeat_release': release, 'budget_before': client.totals(), 'records': [],
                'acknowledged_stopped_runs': args.acknowledge_stopped_run}
    if set(args.acknowledge_stopped_run) - {cell['run_id'] for cell in cells}:
        raise ValueError('Acknowledged run is not a planned cell in this phase')
    dest = folder / 'dispatches' / (dispatch['created_at'].replace(':', '-') + '.json')
    write(dest, dispatch)
    stops = set(cfg['execution']['stop_on'])
    for cell in cells:
        existing = cell_status(cell)
        if existing['status'] != 'not_started':
            dispatch['records'].append({**existing, 'action': 'existing_record_preserved_no_reexecution'})
            write(dest, dispatch)
            if existing['status'] in stops and cell['run_id'] not in args.acknowledge_stopped_run:
                dispatch['stopped_reason'] = 'Existing blocked cell requires separate explicit recovery or review'
                break
            continue
        result = solve(client, tasks[cell['task_id']], cell['model'], stage)
        dispatch['records'].append({**cell_status(cell), 'action': 'dispatched_once', 'budget_after': client.totals()})
        write(dest, dispatch)
        print(json.dumps({'task': cell['task_id'][:8], 'model': cell['model'], 'stage': stage,
                          'status': result['status'], 'new_known_cost_usd': result.get('known_cost_usd'), 'budget': client.totals()}), flush=True)
        if result['status'] in stops:
            dispatch['stopped_reason'] = result.get('error') or result['status']
            break
    dispatch['completed_at'] = now()
    dispatch['all_planned_cells'] = [cell_status(cell) for cell in cells]
    dispatch['budget_after'] = client.totals()
    write(dest, dispatch)


if __name__ == '__main__':
    main()
