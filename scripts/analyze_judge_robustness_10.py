"""Conservative offline audit of the frozen judge-robustness experiment.

Raw quotation/coverage validation is the primary eligibility gate. A response
that cannot support its quotes is not a pass, fail, or human judgment. Stored
responses and the frozen runner are never modified. No API is called.
"""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from evidence_grader import score_judgment
from judge_agreement import agreement_diagnostics

ROOT = Path(__file__).resolve().parents[1]
AUTO = 'automated_assessment_not_human_acceptance'
VARIANTS = ('v1_reword', 'v2_reword', 'v3_reword', 'v4_bias_aware')
LOC = re.compile(r'^(?:xl/[^\t\n]*|word/document\.xml:[^\t\n]*)\t', re.M)


def read(path):
    return json.loads(Path(path).read_text())


def normalized_copy(packet, judgment):
    """Reproduce the frozen runner's secondary, first-segment normalization.

    This can shorten a multiline quotation. It is NOT a stronger semantic
    validator, and its outcomes never enter primary comparisons.
    """
    result = copy.deepcopy(judgment)
    changes = []
    if not isinstance(result, dict) or not isinstance(result.get('criteria'), list):
        return result, changes
    units = {a['id']: [u['text'] for u in a['units']] for a in packet['artifacts']}
    for criterion in result['criteria']:
        if not isinstance(criterion, dict):
            continue
        for evidence in criterion.get('evidence') or []:
            if not isinstance(evidence, dict) or not isinstance(evidence.get('output_quote'), str):
                continue
            before = evidence['output_quote']
            pieces = [s for s in LOC.sub('', before).split('\n') if s.strip()]
            texts = units.get(evidence.get('artifact_id'), [])
            if pieces and all(any(piece in text for text in texts) for piece in pieces):
                evidence['output_quote'] = pieces[0]
                if before != pieces[0]:
                    changes.append({'criterion': criterion.get('id'),
                                    'segments_before_selection': len(pieces),
                                    'discarded_nonempty_segments': max(0, len(pieces)-1),
                                    'locator_prefix_removed': LOC.sub('', before) != before})
    return result, changes


def assess_record(record, packet):
    """Return a three-state verdict only for a revalidated raw assessment."""
    if record is None:
        return {'eligible': False, 'label': None, 'reason': 'missing_response', 'received': False}
    if record.get('status') != 'received':
        return {'eligible': False, 'label': None, 'reason': record.get('status', 'unknown_record_status'), 'received': False}
    judgment = record.get('judgment')
    try:
        recomputed = score_judgment(packet, judgment)
    except (KeyError, TypeError, ValueError, IndexError):
        recomputed = {'status': 'invalid_grader_evidence', 'errors': ['malformed_judgment_or_packet']}
    stored = record.get('assessment') or {}
    # This checks the stored eligibility status and independently validates the
    # original judgment. Cached aggregate labels are never trusted as truth.
    status = recomputed['status']
    mismatch = stored.get('status') != status
    valid = status == AUTO and not mismatch and stored.get('status') == AUTO
    content = recomputed.get('content_acceptable')
    label = ('pass' if content is True else 'fail' if content is False else 'uncertain') if valid else None
    return {'eligible': valid, 'received': True, 'label': label,
            'reason': None if valid else 'stored_validation_status_mismatch' if mismatch else status,
            'assessment_status': status, 'stored_assessment_status': stored.get('status'),
            'stored_status_mismatch': mismatch,
            'format_valid': status != 'invalid_grader_evidence',
            'consequential_error': recomputed.get('consequential_error') if valid else None,
            'validation_errors': recomputed.get('errors', [])}


def comparison(pairs):
    """Compare exact pass/fail/uncertain labels; missing baselines never flip."""
    matrix = Counter(); excluded = Counter(); changes = []; compared = []; binary = []
    for case_id, left, right in pairs:
        if not left.get('eligible') or not right.get('eligible'):
            if not left.get('eligible'): excluded['baseline:' + str(left.get('reason'))] += 1
            if not right.get('eligible'): excluded['comparison:' + str(right.get('reason'))] += 1
            continue
        a, b = left['label'], right['label']
        matrix[a, b] += 1; compared.append(case_id)
        if a != b: changes.append({'case_id': case_id, 'baseline': a, 'comparison': b})
        if a in ('pass', 'fail') and b in ('pass', 'fail'): binary.append((case_id, a, b))
    exact_pairs = [(a, b) for (a, b), count in matrix.items() for _ in range(count)]
    return {'planned': len(pairs), 'comparable': len(compared), 'compared_case_ids': compared,
            'agree': sum(n for (a, b), n in matrix.items() if a == b), 'changed': len(changes),
            'changes': changes,
            'matrix': [{'baseline': a, 'comparison': b, 'count': n} for (a, b), n in sorted(matrix.items())],
            'binary_comparable': len(binary), 'binary_changed': sum(a != b for _, a, b in binary),
            'uncertain_comparisons': len(compared)-len(binary),
            'excluded_pairs': len(pairs)-len(compared), 'exclusion_reasons': dict(excluded),
            'agreement_diagnostics': agreement_diagnostics(exact_pairs, ('pass', 'fail', 'uncertain'), positive_label=None),
            'binary_agreement_diagnostics': agreement_diagnostics([(a, b) for _, a, b in binary], ('fail', 'pass'), positive_label='fail'),
            'scope': 'Paired raw-evidence-valid automated labels. Agreement is not accuracy; uncertain is not merged with pass.'}


def tally(values):
    return {'planned': len(values), 'received': sum(x.get('received', False) for x in values),
            'raw_format_valid': sum(x.get('format_valid', False) for x in values),
            'raw_scorable': sum(x.get('eligible', False) for x in values),
            'labels': dict(Counter(x['label'] for x in values if x.get('eligible'))),
            'exclusions': dict(Counter(x.get('reason') for x in values if not x.get('eligible')))}


def fixture_counts(keys, assessments):
    groups = {}
    for member in ('mutated', 'supported', 'unchanged_control', 'cosmetic_control'):
        selected = [k for k in keys if k['member'] == member]
        eligible = [(k, assessments[k['id']]) for k in selected
                    if k['id'] in assessments and assessments[k['id']].get('eligible')]
        binary = [(k, a) for k, a in eligible if a['label'] in ('pass', 'fail')]
        groups[member] = {'planned': len(selected), 'raw_scorable': len(eligible),
                          'binary_comparable': len(binary), 'accepted': sum(a['label'] == 'pass' for _, a in binary),
                          'rejected': sum(a['label'] == 'fail' for _, a in binary),
                          'matches_author_expectation': sum((a['label'] == 'pass') == k['expected_content_acceptable'] for k, a in binary),
                          'unknown_invalid_or_unreceived': len(selected)-len(binary)}
    positive = [k for k in keys if k['expected_consequential_error']]
    eligible = [(k, assessments[k['id']]) for k in positive
                if k['id'] in assessments and assessments[k['id']].get('eligible')
                and type(assessments[k['id']].get('consequential_error')) is bool]
    return {'groups': groups, 'critical_error_checks': {'planned': len(positive), 'binary_comparable': len(eligible),
            'detected': sum(a['consequential_error'] for _, a in eligible),
            'missed': sum(not a['consequential_error'] for _, a in eligible),
            'unknown_invalid_or_unreceived': len(positive)-len(eligible)},
            'scope': 'Selected, correlated constructed fixtures compared with author-intended expectations, not independently validated human gold.'}


def ledger_summary(ledger):
    def valid_amount(row):
        value = row.get('actual_cost_usd')
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    return {'reported_api_cost_usd': sum(r['actual_cost_usd'] for r in ledger if valid_amount(r)),
            'ledger_records': len(ledger),
            'unresolved_charge_records': sum(r.get('status') != 'actual' or not valid_amount(r) for r in ledger),
            'missing_or_invalid_amount_records': sum(not valid_amount(r) for r in ledger),
            'record_status_counts': dict(Counter(r.get('status') for r in ledger)),
            'scope': 'New judge_robustness_10 request ledger only. Original v0 responses reused without duplicate charges. Nonfinite, negative, Boolean or missing amounts are not treated as known charges. Not a reconciled invoice.'}


def separate_first_attempts(root, current_records, ledger, configured_ids, load=None):
    """Validate archived first attempts and isolate subsequent recovery calls.

    Original errors remain primary observations even when the latest logical-job
    file contains a successful retry. The first ledger is an immutable prefix,
    not a filtered list that silently drops failed or unresolved requests.
    """
    root=Path(root); configured_ids=set(configured_ids)
    load=load or (lambda rel: read(root/rel))
    manifest_path='output/judge_robustness_10/first_attempts/manifest.json'
    path=root/manifest_path
    if not path.exists():
        if any(r.get('previous_attempts') for r in current_records.values()) or len({r['id'] for r in ledger})!=len(ledger):
            raise ValueError('Recovery records require a validated first-attempt snapshot')
        return dict(current_records),ledger,[],[],{'mode':'original_records_no_recovery_snapshot','overlaid_ids':[]}
    manifest=load(manifest_path)
    if manifest.get('schema')!='first-attempt-archive-snapshot-v1':raise ValueError('Unknown first-attempt manifest schema')
    def checked_file(relative,digest,expected=None):
        if not isinstance(relative,str) or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Invalid first-attempt manifest path or hash')
        candidate=root/relative
        if not candidate.resolve().is_relative_to(root.resolve()) or (expected is not None and relative!=expected):
            raise ValueError('Unexpected first-attempt manifest path')
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest()!=digest:
            raise ValueError('First-attempt snapshot hash mismatch: '+relative)
        return candidate
    archive=manifest.get('source_archive');archive_hash=manifest.get('source_archive_sha256')
    if not isinstance(archive,str) or not isinstance(archive_hash,str) or not re.fullmatch('[0-9a-f]{64}',archive_hash):
        raise ValueError('Missing source-archive provenance')
    # The portable handoff contains the individually hashed snapshots, not a
    # nested copy of the prior ZIP. Validate the source ZIP as well when present.
    archive_path=root/archive
    if not archive_path.resolve().is_relative_to(root.resolve()):raise ValueError('Unexpected source-archive path')
    if archive_path.exists():checked_file(archive,archive_hash)
    ledger_meta=manifest.get('ledger',{})
    ledger_path='output/judge_robustness_10/first_attempts/ledger.json'
    checked_file(ledger_meta.get('path'),ledger_meta.get('sha256'),ledger_path)
    original_ledger=load(ledger_path)
    if ledger_meta.get('records')!=len(original_ledger):raise ValueError('First-attempt ledger size mismatch')
    if len(original_ledger)!=len(configured_ids) or {r['id'] for r in original_ledger}!=configured_ids:
        raise ValueError('First-attempt ledger does not contain exactly one row per configured request')
    if ledger[:len(original_ledger)]!=original_ledger:raise ValueError('Current ledger changed the first-attempt prefix')
    additions=ledger[len(original_ledger):]
    rows=manifest.get('records')
    if not isinstance(rows,list):raise ValueError('Missing original attempt records')
    ids=[row.get('id') for row in rows]
    if len(set(ids))!=len(ids) or not set(ids)<=configured_ids:raise ValueError('Invalid first-attempt record identities')
    if Counter(r.get('id') for r in additions)!=Counter(ids):
        raise ValueError('Recovery ledger identities do not match the archived retry set')
    previous_ids={rid for rid,r in current_records.items() if r.get('previous_attempts')}
    if previous_ids!=set(ids):raise ValueError('Unexpected recovery record outside the archived retry set')
    primary=dict(current_records)
    for row in rows:
        rid=row['id'];original_path=f'output/judge_robustness_10/first_attempts/{rid}.json'
        recovery_path=f'output/judge_robustness_10/runs/{rid}.json'
        checked_file(row.get('path'),row.get('sha256'),original_path)
        checked_file(row.get('recovery_record'),row.get('recovery_sha256'),recovery_path)
        original=load(original_path);current=current_records[rid]
        if original.get('id')!=rid or original.get('status')!='execution_error' or row.get('original_status')!='execution_error':
            raise ValueError('Archived retry predecessor is not the original execution error')
        if any(original.get(k)!=current.get(k) for k in ('id','study','variant','model','packet','base_id')):
            raise ValueError('Recovery changed configured request identity')
        previous=current.get('previous_attempts',[])
        expected={k:original.get(k) for k in ('started_at','finished_at','status','error')}
        if len(previous)!=1 or any(previous[0].get(k)!=v for k,v in expected.items()):
            raise ValueError('Recovery predecessor metadata differs from archived first attempt')
        primary[rid]=original
    provenance={'mode':'archived_first_attempts','manifest':manifest_path,
        'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'source_archive':archive,'source_archive_sha256':archive_hash,
        'overlaid_ids':sorted(ids),'original_ledger_records':len(original_ledger),
        'validation':'Snapshot and recovery-file hashes, original ledger prefix, request identities and predecessor metadata are checked. Source archive hash is additionally checked when the archive is present; the portable package uses the hashed snapshots.'}
    return primary,original_ledger,additions,sorted(ids),provenance


def build(root=ROOT):
    root = Path(root); source_paths = set()
    def load(relative):
        path = root / relative
        source_paths.add(path)
        return read(path)
    cfg = load('config/judge_robustness_10.json'); jobs = cfg['jobs']
    if len({j['id'] for j in jobs}) != len(jobs): raise ValueError('Duplicate configured job ID')
    configured = {j['id']: j for j in jobs}; records = {}
    for path in sorted((root/'output/judge_robustness_10/runs').glob('*.json')):
        item = load(path.relative_to(root)); rid = item['id']
        if rid in records: raise ValueError('Duplicate run ID')
        records[rid] = item
    unexpected = sorted(set(records)-set(configured))
    if unexpected: raise ValueError('Unconfigured run records: '+','.join(unexpected))
    ledger=load('output/judge_robustness_10/ledger.json')
    latest_records=records
    records,original_ledger,recovery_ledger,recovery_ids,first_attempt_provenance=separate_first_attempts(root,latest_records,ledger,configured,load)
    base = {}
    for path in sorted((root/'output/grader_checks_05/runs').glob('*.json')):
        item = load(path.relative_to(root)); base[item['id']] = item
    packets = {}
    def packet_for(path):
        if path not in packets: packets[path] = load(path)
        return packets[path]
    assessed = {}; normalized = {}; normalization_changes = {}; identity_errors = []
    for job in jobs:
        record = records.get(job['id']); packet = packet_for(job['packet'])
        if record and any(record.get(k) != job.get(k) for k in ('id', 'study', 'variant', 'model', 'packet', 'base_id')):
            identity_errors.append(job['id'])
            assessed[job['id']] = {'eligible': False, 'received': record.get('status') == 'received', 'label': None, 'reason': 'configured_job_identity_mismatch'}
            continue
        assessed[job['id']] = assess_record(record, packet)
        if record and record.get('status') == 'received':
            clean, changes = normalized_copy(packet, record.get('judgment'))
            secondary = score_judgment(packet, clean)
            normalized[job['id']] = secondary
            normalization_changes[job['id']] = changes
    base_assessed = {}; base_normalized = {}; base_normalization_changes = {}
    for base_id in sorted({j['base_id'] for j in jobs}):
        record = base.get(base_id)
        if record:
            packet = packet_for(record['packet'])
            base_assessed[base_id] = assess_record(record, packet)
            if record.get('status') == 'received':
                clean, changes = normalized_copy(packet, record.get('judgment'))
                base_normalized[base_id] = score_judgment(packet, clean)
                base_normalization_changes[base_id] = changes
        else: base_assessed[base_id] = assess_record(None, {})
    cal_ids = sorted({j['base_id'] for j in jobs if j['study'] == 'sensitivity'})
    comparisons = {}; variant_counts = {'v0_original': tally([base_assessed[c] for c in cal_ids])}
    for variant in VARIANTS:
        chosen = [j for j in jobs if j['study'] == 'sensitivity' and j['variant'] == variant]
        comparisons[variant] = comparison([(j['base_id'], base_assessed[j['base_id']], assessed[j['id']]) for j in chosen])
        variant_counts[variant] = tally([assessed[j['id']] for j in chosen])
    stable_cases = []
    for cid in cal_ids:
        values = [base_assessed[cid]] + [assessed[cid+'__'+v] for v in VARIANTS[:3]]
        if all(x['eligible'] and x['label'] in ('pass', 'fail') for x in values):
            stable_cases.append({'case_id': cid, 'all_same': len({x['label'] for x in values}) == 1})
    families = load('output/native_workflow_01/calibration_private_key.json')
    family_by_case = {x['review_id']: x['family_id'] for x in families}
    sensitivity = {'comparisons': comparisons, 'variant_counts': variant_counts,
                   'source_families': len({family_by_case[c] for c in cal_ids if c in family_by_case}),
                   'v0_to_v3_complete_binary_cases': len(stable_cases),
                   'v0_to_v3_same_label_cases': sum(x['all_same'] for x in stable_cases),
                   'scope': 'v1-v3 are intended meaning-preserving instruction rewordings; that intention has not been independently validated. v4 adds targeted guidance and is a separate intervention. Fixed prompt variants and repeated task families are not independent expert raters or population samples.'}
    family_jobs = [j for j in jobs if j['study'] == 'family']
    cal_jobs = [j for j in family_jobs if j.get('cohort') == 'historical_calibration']
    keys = load('data/grader_challenges_02/private/author_key.json')
    sol_constructed = {j['base_id']: assessed[j['id']] for j in family_jobs if j.get('cohort') == 'constructed'}
    family = {'historical': comparison([(j['base_id'], base_assessed[j['base_id']], assessed[j['id']]) for j in cal_jobs]),
              'constructed': {'gemini_original': fixture_counts(keys, base_assessed), 'sol_v0': fixture_counts(keys, sol_constructed)},
              'scope': 'Same source packets and v0 instructions; different judge families. Model-family diversity and agreement do not establish human validity.'}
    injection_jobs = [j for j in jobs if j['study'] == 'injection']
    injection = {'comparison': comparison([(j['id'], base_assessed[j['base_id']], assessed[j['id']]) for j in injection_jobs]),
                 'by_injection': {kind: comparison([(j['id'], base_assessed[j['base_id']], assessed[j['id']]) for j in injection_jobs if j['injection'] == kind]) for kind in sorted({j['injection'] for j in injection_jobs})},
                 'source_fixture_count': len({j['base_id'] for j in injection_jobs}),
                 'scope': 'Two appended texts on four selected constructed fixtures. A verdict change alone does not prove instruction following: the added artifact text may itself affect substantive validity. No general prompt-injection robustness or security certification follows.'}
    def normalization_stats(original, second, changes):
        received = {k: a for k, a in original.items() if a.get('received')}
        raw_invalid = {k for k, a in received.items() if a.get('assessment_status') == 'invalid_grader_evidence'}
        return {'received': len(received), 'raw_invalid': len(raw_invalid),
                'raw_invalid_becoming_secondary_scorable': sum(second.get(k, {}).get('status') == AUTO for k in raw_invalid),
                'secondary_scorable': sum(a.get('status') == AUTO for a in second.values()),
                'cases_with_quote_changes': sum(bool(x) for x in changes.values()),
                'cases_with_discarded_quote_segments': sum(any(c['discarded_nonempty_segments'] for c in x) for x in changes.values()),
                'discarded_nonempty_quote_segments': sum(c['discarded_nonempty_segments'] for x in changes.values() for c in x),
                'secondary_status_counts': dict(Counter(a.get('status') for a in second.values()))}
    normalization = {'new_batch': normalization_stats(assessed, normalized, normalization_changes),
                     'original_historical': normalization_stats({c:base_assessed[c] for c in cal_ids}, {c:base_normalized[c] for c in cal_ids if c in base_normalized}, {c:base_normalization_changes[c] for c in cal_ids if c in base_normalization_changes}),
                     'primary_scores_changed': False,
                     'scope': 'Secondary reproduction of the frozen locator normalizer. It strips location prefixes and retains only the first verified nonempty segment of a multiline quote; this can weaken evidence coverage. Its apparent format recovery is not a semantic repair, accuracy result or human calibration.'}
    statuses = Counter(r.get('status') for r in records.values())
    finished = sum(r.get('status') in ('received', 'execution_error') for r in records.values())
    completion = {'planned': len(jobs), 'started': len(records), 'finished': finished,
                  'received': statuses['received'], 'running': statuses['running'],
                  'execution_errors': statuses['execution_error'], 'unattempted_ids': sorted(set(configured)-set(records)),
                  'complete': len(records) == len(jobs) and finished == len(jobs),
                  'record_status_counts': dict(statuses), 'job_identity_errors': identity_errors,
                  'meaning': 'Complete means every configured request reached a terminal state; execution errors are preserved, not converted to responses.'}
    raw = tally([assessed[j['id']] for j in jobs])
    raw['format_valid'] = raw['raw_format_valid']
    raw['scorable'] = raw['raw_scorable']
    raw['response_status_counts'] = dict(Counter(a.get('assessment_status') for a in assessed.values() if a.get('received')))
    raw['stored_validation_status_mismatches'] = sum(a.get('stored_status_mismatch', False) for a in assessed.values())
    raw['resolved_binary'] = sum(a.get('eligible') and a.get('label') in ('pass','fail') for a in assessed.values())
    raw['validation_error_counts'] = dict(Counter(error.split(':')[-1] for a in assessed.values() for error in a.get('validation_errors', [])))
    cost = ledger_summary(ledger)
    cost['first_attempt']=ledger_summary(original_ledger)
    cost['additional_recovery']=ledger_summary(recovery_ledger)
    cost['scope']='All recorded physical requests in this phase, including separately reported recoveries. Original v0 responses reused without duplicate charges; unknown error charges remain unresolved. Not a reconciled invoice.'
    latest_assessed=dict(assessed)
    for rid in recovery_ids:
        if rid not in identity_errors:
            latest_assessed[rid]=assess_record(latest_records[rid],packet_for(configured[rid]['packet']))
    recovery={'additional_requests':len(recovery_ledger),'additional_request_ids':recovery_ids,
        'additional_raw':tally([latest_assessed[rid] for rid in recovery_ids]),
        'all_physical_requests':len(ledger),'final_logical_requests':len(latest_records),
        'final_logical_raw':tally([latest_assessed[j['id']] for j in jobs if j['id'] in latest_assessed]),
        'original_errors_preserved':len(recovery_ids),'included_in_primary_comparisons':False,
        'reported_additional_cost_usd':cost['additional_recovery']['reported_api_cost_usd'],
        'scope':'Post-hoc transport recovery of previously failed logical requests. Primary comparisons use archived first attempts; final logical-job coverage and all physical request costs are shown separately. Recovery is not a randomized intervention or evidence of improved grader accuracy.'}
    return {'schema': 'judge-robustness-audit-v1', 'updated_at': datetime.now(timezone.utc).isoformat(),
            'completion': completion, 'raw': raw, 'sensitivity': sensitivity, 'family': family,
            'injection': injection, 'normalization': normalization, 'cost': cost,
            'recovery':recovery,'first_attempt_provenance':first_attempt_provenance,
            'human_calibration': None, 'new_human_labels': 0,
            'limitations': ['All primary verdict comparisons require independently recomputed raw quote/coverage validity and the recorded automated-assessment status.',
                           'Invalid, missing, task-defective and uncertain results remain explicit; they are not silently counted as passes.',
                           'Quoted evidence can still fail to entail a judgment. No human agreement, error prevalence, model ranking or training improvement is established.',
                           'Prompt variants and constructed controls are dependent; counts describe this selected development sample.'],
            'sources': [{'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(source_paths)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); result = build(args.root)
    dest = args.output or args.root/'output/judge_robustness_10/audited_summary.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'output': str(dest), 'completion': result['completion'], 'raw': result['raw'], 'cost': result['cost']}))


if __name__ == '__main__':
    main()
