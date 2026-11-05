"""Reconcile cumulative API spend and protect historical evidence. No API calls."""
from decimal import Decimal
import json
from pathlib import Path
from build_evidence_upgrade import ROOT, DEST, digest, validate
from run_repair_probe import CampaignBudget

LEDGERS = ('output/paired_v1/ledger.json', 'output/paired_v1/judge_ledger.json',
           'output/repair_probe_01/ledger.json')


def budget_status(root=ROOT):
    totals = []; exposure = Decimal(0); actual = Decimal(0); pending = 0
    for rel in LEDGERS:
        rows = json.loads((root / rel).read_text())  # Missing ledger is an error, not zero spend.
        value = sum((Decimal(str(x['charged_or_reserved'])) for x in rows), Decimal(0))
        paid = sum((Decimal(str(x.get('actual_cost_usd', 0))) for x in rows), Decimal(0))
        if value < 0 or paid < 0 or not value.is_finite() or not paid.is_finite():
            raise ValueError('invalid_ledger_total')
        pending += sum(x['status'] not in ('actual', 'provider_rejected_before_dispatch') for x in rows)
        totals.append({'path': rel, 'sha256': digest((root / rel).read_bytes()),
                       'charged_or_reserved_usd': float(value), 'actual_usd': float(paid)})
        exposure += value; actual += paid
    if exposure > Decimal(25):
        raise ValueError('campaign_cap_exceeded')
    return {'campaign_cap_usd': 25, 'charged_or_reserved_usd': float(exposure),
            'actual_usd': float(actual), 'remaining_cap_usd': float(Decimal(25)-exposure),
            'unresolved_reservations': pending, 'new_api_spend_usd': 0,
            'human_review_and_correction_cost': None, 'ledger_totals': totals,
            'scope': 'Recorded campaign allowance, not OpenRouter balance. Human labor is separate and unmeasured.'}


def future_stage_budget(base, stage_cap, root=ROOT):
    """Reuse the campaign reservation guard with ALL three historical ledgers.

    Callers must also hold run_repair_probe.campaign_lock, enforce provider price
    ceilings and pass engineering/review readiness before any future dispatch.
    No executor is enabled by constructing this object.
    """
    budget_status(root)
    return CampaignBudget(Path(base), campaign=25, stage=stage_cap,
                          legacy_paths=[root / p for p in LEDGERS])


def main():
    prior = json.loads((ROOT / 'output/evidence_upgrade_01/prior_evidence_hashes.json').read_text())
    changed = [p for p, h in prior.items() if not (ROOT / p).exists() or digest((ROOT / p).read_bytes()) != h]
    rubrics = {r['id']: r for r in json.loads((DEST / 'grader/rubrics.json').read_text())}
    maps = json.loads((DEST / 'grader/evidence_maps.json').read_text())
    manifest = json.loads((DEST / 'manifest.json').read_text())
    release_errors = []
    if digest((DEST / 'grader/evidence_maps.json').read_bytes()) != manifest['private_map_sha256']:
        release_errors.append('map_hash_changed')
    for f in manifest['files']:
        if digest((ROOT / f['path']).read_bytes()) != f['sha256']:
            release_errors.append('candidate_hash_changed:' + f['path'])
        if digest((ROOT / f['parent_path']).read_bytes()) != f['parent_sha256']:
            release_errors.append('parent_hash_changed:' + f['parent_path'])
    checks = []
    for m in maps:
        task = json.loads((DEST / 'solver' / (m['instance_id'] + '.json')).read_text())
        checks.append({'instance_id': m['instance_id'], 'errors': validate(task, m, rubrics[m['family_id']])})
    result = {'date': '2026-11-03', 'status': 'engineering_checks_pass' if not changed and not release_errors and not any(c['errors'] for c in checks) else 'failed',
              'historical_files_checked': len(prior), 'historical_files_changed': changed,
              'release_integrity_errors': release_errors,
              'task_checks': checks, 'budget': budget_status(),
              'paid_run_ready': False, 'model_selection_ready': False, 'training_ready': False,
              'remaining_work': ['Independent task/evidence-map review and source-rights attestations.',
                                 'Native file create/render/recalculate/inspect/revise loop under matched solver tools.',
                                 'Human review of constructed challenges and full model deliverables; measure judge misses and false accepts.',
                                 'Freeze a matched protocol on additional distinct families before repeats; reserve generation and judging costs together.',
                                 'Set customer error/acceptance thresholds and measure review/correction minutes before model selection.'],
              'human_record': {'completed_full_output_reviews': 0, 'issue_only_material_correction_labels': 2,
                               'partially_reviewed_case': 'C-7424ebd2', 'usability': 'uncertain', 'consequential_error': 'uncertain',
                               'expertise_and_independence': 'unspecified'}}
    dest = ROOT / 'output/evidence_upgrade_01/status.json'
    dest.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'protected_files': len(prior),
                      'task_instances': len(checks), 'budget': result['budget']['charged_or_reserved_usd'],
                      'remaining': result['budget']['remaining_cap_usd']}))
    if result['status'] != 'engineering_checks_pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
