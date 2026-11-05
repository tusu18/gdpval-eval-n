"""Reconcile saved phase-10 quote formats without rewriting judge evidence.

Raw primary results and the frozen first-segment normalizer remain historical
facts. This separate offline diagnostic accepts a locator-prefixed quotation
only when every complete native-unit value matches its named artifact/locator.
It preserves all values in separate evidence objects with verified locators.
Traceability is not entailment, human accuracy, or an improved model verdict.
"""
import argparse
from collections import Counter
import copy
import hashlib
import html
import json
from pathlib import Path

from analyze_judge_robustness_10 import normalized_copy, separate_first_attempts
from evidence_grader import score_judgment

ROOT = Path(__file__).resolve().parents[1]
AUTO = 'automated_assessment_not_human_acceptance'


def read(path):
    return json.loads(Path(path).read_text())


def _decode_complete_quote(quote, units):
    """Consume every character of exact locator/value records, or reject all.

    Unit values can contain newlines or tabs. Only record separators are
    removed; values are never stripped, truncated or selected by substring.
    Empty values and duplicate locator definitions are intentionally rejected.
    """
    by_locator = {}
    for unit in units:
        locator, value = unit.get('locator'), unit.get('text')
        if not isinstance(locator, str) or not isinstance(value, str):
            return None, 'malformed_artifact_unit'
        if locator in by_locator:
            return None, 'duplicate_artifact_locator'
        by_locator[locator] = value
    cursor = 0
    decoded = []
    while cursor < len(quote):
        tab = quote.find('\t', cursor)
        if tab < 0:
            return None, 'missing_locator_separator'
        locator = quote[cursor:tab]
        if locator not in by_locator:
            return None, 'unknown_locator_in_named_artifact'
        value = by_locator[locator]
        if not value.strip():
            return None, 'empty_native_value'
        start = tab + 1
        if not quote.startswith(value, start):
            return None, 'native_value_mismatch'
        cursor = start + len(value)
        decoded.append({'locator': locator, 'value': value})
        if cursor == len(quote):
            break
        if quote.startswith('\r\n', cursor):
            cursor += 2
        elif quote[cursor:cursor+1] == '\n':
            cursor += 1
        else:
            return None, 'unconsumed_quote_content'
        # A trailing record separator is harmless formatting; internal blank
        # records remain invalid rather than silently dropping their content.
    return decoded if decoded else None, None if decoded else 'empty_quote'


def lossless_normalize(packet, judgment):
    """Return a separate normalized copy, transformations and rejected edits.

    No status, rationale, source quote, or business value is generated. The
    whole original quote is retained in each transformation for audit. Invalid
    candidates remain unchanged and therefore remain subject to raw checks.
    """
    result = copy.deepcopy(judgment)
    transformations, rejected = [], []
    if not isinstance(result, dict) or not isinstance(result.get('criteria'), list):
        return result, transformations, rejected
    artifacts = {}
    duplicate_ids = set()
    for artifact in packet.get('artifacts', []):
        if artifact.get('id') in artifacts:
            duplicate_ids.add(artifact.get('id'))
        artifacts[artifact.get('id')] = artifact
    for criterion_index, criterion in enumerate(result['criteria']):
        if not isinstance(criterion, dict) or criterion.get('evidence_kind') != 'quoted':
            continue
        evidence = criterion.get('evidence')
        if not isinstance(evidence, list):
            continue
        revised = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                revised.append(item)
                continue
            quote, artifact_id = item.get('output_quote'), item.get('artifact_id')
            artifact = artifacts.get(artifact_id) if isinstance(artifact_id, str) else None
            if not isinstance(quote, str) or '\t' not in quote:
                revised.append(item)
                continue
            location = {'criterion': criterion.get('id'), 'criterion_index': criterion_index, 'evidence_index': index,
                        'artifact_id': artifact_id}
            if artifact is None or artifact_id in duplicate_ids:
                rejected.append({**location, 'reason': 'unknown_or_duplicate_artifact_id'})
                revised.append(item)
                continue
            units = artifact.get('units', [])
            # A raw literal quote already traceable to a native unit needs no
            # repair, including a literal quote containing tabs or newlines.
            if quote and any(isinstance(u.get('text'), str) and quote in u['text'] for u in units):
                revised.append(item)
                continue
            decoded, reason = _decode_complete_quote(quote, units)
            if decoded is None:
                rejected.append({**location, 'reason': reason})
                revised.append(item)
                continue
            if 'verified_output_locator' in item:
                rejected.append({**location, 'reason': 'preexisting_normalizer_metadata'})
                revised.append(item)
                continue
            for unit in decoded:
                revised.append({**item, 'output_quote': unit['value'],
                                'verified_output_locator': unit['locator']})
            transformations.append({**location, 'original_quote': quote,
                'verified_units': decoded,
                'values_before': len(decoded), 'values_after': len(decoded),
                'discarded_value_segments': 0,
                'rule': 'Every complete native-unit value matches its named artifact and locator; all values and locators retained.'})
        criterion['evidence'] = revised
    return result, transformations, rejected


def safe_assess(packet, judgment):
    try:
        return score_judgment(packet, judgment)
    except (KeyError, TypeError, ValueError, IndexError):
        return {'status': 'invalid_grader_evidence',
                'errors': ['malformed_judgment_or_packet'],
                'content_acceptable': None, 'consequential_error': None}


def score_lossless_judgment(packet, judgment):
    """Apply the existing checks plus fail-closed empty-quote/identity guards.

    This secondary checker does not alter any primary historical judgment.
    Duplicate artifact IDs cannot establish which file supplies the evidence.
    """
    result = safe_assess(packet, judgment)
    errors = list(result.get('errors', []))
    artifact_ids = [a.get('id') for a in packet.get('artifacts', [])]
    artifacts = {a['id']: a for a in packet.get('artifacts', []) if isinstance(a.get('id'), str)}
    if len(artifact_ids) != len(set(str(a) for a in artifact_ids)):
        errors.append('duplicate_artifact_id')
    if isinstance(judgment, dict) and isinstance(judgment.get('criteria'), list):
        for row in judgment['criteria']:
            if not isinstance(row, dict):
                continue
            evidence = row.get('evidence')
            if not isinstance(evidence, list):
                continue
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                quote = item.get('output_quote')
                if (row.get('status') != 'uncertain' and row.get('evidence_kind') == 'quoted'
                        and isinstance(quote, str) and not quote.strip()):
                    errors.append(str(row.get('id'))+':empty_output_quote')
                # Caller-provided metadata is a claim, never a trust signal.
                # Verify it even for an uncertain row or a raw literal quote
                # that did not need normalization.
                if 'verified_output_locator' in item:
                    locator = item['verified_output_locator']
                    aid = item.get('artifact_id')
                    artifact = artifacts.get(aid) if isinstance(aid, str) else None
                    units = artifact.get('units', []) if artifact else []
                    matches = [u for u in units if u.get('locator') == locator] if isinstance(locator, str) else []
                    if (row.get('evidence_kind') != 'quoted' or not isinstance(quote, str)
                            or not quote.strip() or len(matches) != 1 or matches[0].get('text') != quote):
                        errors.append(str(row.get('id'))+':unverifiable_verified_output_locator')
    if errors:
        return {'status': 'invalid_grader_evidence', 'errors': sorted(set(errors)),
                'content_acceptable': None, 'consequential_error': None, 'human_accepted': None}
    return result


def preserved_judgment_fields(original, normalized, transformations):
    """Reconstruct the only permitted edit from the recorded transformations."""
    expected = copy.deepcopy(original)
    if not transformations:
        return expected == normalized
    by_position = {(t['criterion_index'], t['evidence_index']):t for t in transformations}
    for ci, criterion in enumerate(expected.get('criteria', [])):
        if not isinstance(criterion, dict) or not isinstance(criterion.get('evidence'), list):
            continue
        evidence = []
        for ei, item in enumerate(criterion['evidence']):
            transformation = by_position.get((ci, ei))
            if transformation is None:
                evidence.append(item)
                continue
            if item.get('output_quote') != transformation['original_quote']:
                return False
            for unit in transformation['verified_units']:
                evidence.append({**item, 'output_quote': unit['value'], 'verified_output_locator':unit['locator']})
        criterion['evidence'] = evidence
    return expected == normalized


def audit_record(record, packet, cohort):
    row = {'id': record['id'], 'cohort': cohort, 'response_status': record.get('status'),
           'raw_primary_eligible': False, 'raw_primary_status': record.get('status'),
           'frozen_secondary_scorable': False, 'lossless_secondary_scorable': False,
           'frozen_discarded_value_segments': 0, 'lossless_discarded_value_segments': 0,
           'lossless_transformations': [], 'lossless_rejected_candidates': []}
    if record.get('status') != 'received':
        return row
    original = record.get('judgment')
    raw = safe_assess(packet, original)
    stored = record.get('assessment') or {}
    frozen, old_changes = normalized_copy(packet, original)
    frozen_assessment = safe_assess(packet, frozen)
    lossless, transformations, rejected = lossless_normalize(packet, original)
    lossless_assessment = score_lossless_judgment(packet, lossless)
    status_matches = raw['status'] == stored.get('status')
    row.update({
        'raw_primary_status': raw['status'],
        'raw_stored_status_matches': status_matches,
        'raw_primary_eligible': raw['status'] == AUTO and status_matches,
        'raw_assessment': raw, 'frozen_secondary_assessment': frozen_assessment,
        'lossless_secondary_assessment': lossless_assessment,
        'frozen_secondary_scorable': frozen_assessment['status'] == AUTO,
        'lossless_secondary_scorable': lossless_assessment['status'] == AUTO,
        'frozen_changes': old_changes,
        'frozen_discarded_value_segments': sum(x['discarded_nonempty_segments'] for x in old_changes),
        'lossless_transformations': transformations, 'lossless_rejected_candidates': rejected,
        'criterion_statuses_unchanged': preserved_judgment_fields(original, lossless, transformations),
        'all_non_output_quote_fields_preserved': preserved_judgment_fields(original, lossless, transformations),
        'lossless_value_preservation_verified': all(
            x['values_before'] == x['values_after'] and x['discarded_value_segments'] == 0
            for x in transformations),
    })
    # The exact candidate copy is kept separately from every historical record.
    if transformations:
        row['lossless_secondary_judgment'] = lossless
    return row


def summarize(rows):
    received = [r for r in rows if r['response_status'] == 'received']
    raw_invalid = [r for r in received if r['raw_primary_status'] == 'invalid_grader_evidence']
    changed = [r for r in received if r['lossless_transformations']]
    return {
        'attempts': len(rows), 'responses': len(received),
        'execution_or_other_failures': len(rows)-len(received),
        'raw_primary_scorable': sum(r['raw_primary_eligible'] for r in rows),
        'raw_invalid_responses': len(raw_invalid),
        'frozen_secondary_scorable': sum(r['frozen_secondary_scorable'] for r in rows),
        'lossless_secondary_scorable': sum(r['lossless_secondary_scorable'] for r in rows),
        'raw_invalid_to_lossless_scorable': sum(r['lossless_secondary_scorable'] for r in raw_invalid),
        'raw_invalid_to_frozen_scorable': sum(r['frozen_secondary_scorable'] for r in raw_invalid),
        'frozen_only_scorable_case_ids': [r['id'] for r in rows if r['frozen_secondary_scorable'] and not r['lossless_secondary_scorable']],
        'lossless_only_scorable_case_ids': [r['id'] for r in rows if r['lossless_secondary_scorable'] and not r['frozen_secondary_scorable']],
        'lossless_changed_case_ids': [r['id'] for r in changed],
        'lossless_transformations': sum(len(r['lossless_transformations']) for r in rows),
        'lossless_verified_value_segments': sum(x['values_after'] for r in rows for x in r['lossless_transformations']),
        'lossless_discarded_value_segments': sum(r['lossless_discarded_value_segments'] for r in rows),
        'frozen_cases_with_discarded_segments': sum(r['frozen_discarded_value_segments'] > 0 for r in rows),
        'frozen_discarded_value_segments': sum(r['frozen_discarded_value_segments'] for r in rows),
        'lossless_rejection_reasons': dict(Counter(x['reason'] for r in rows for x in r['lossless_rejected_candidates'])),
        'stored_status_mismatches': sum(not r['raw_stored_status_matches'] for r in received),
        'all_transformed_values_preserved': all(r['lossless_value_preservation_verified'] for r in received),
        'all_criterion_statuses_unchanged': all(r['criterion_statuses_unchanged'] for r in received),
    }


def build(root=ROOT):
    root = Path(root)
    sources = set()
    def load(relative):
        path = root/relative
        sources.add(path.relative_to(root).as_posix())
        return read(path)
    config = load('config/judge_robustness_10.json')
    jobs = {j['id']: j for j in config['jobs']}
    if len(jobs) != len(config['jobs']):
        raise ValueError('Duplicate configured request ID')
    current = {}
    for path in sorted((root/'output/judge_robustness_10/runs').glob('*.json')):
        record = load(path.relative_to(root))
        if record['id'] in current:
            raise ValueError('Duplicate saved request ID')
        current[record['id']] = record
    if set(current) != set(jobs):
        raise ValueError('Missing or unconfigured phase-10 record')
    ledger = load('output/judge_robustness_10/ledger.json')
    original, _, _, recovery_ids, provenance = separate_first_attempts(root, current, ledger, set(jobs), load)
    packets = {}
    rows = []
    for cohort, ids, records in [('original_attempts', sorted(jobs), original),
                                  ('later_recovery_attempts', recovery_ids, current)]:
        for rid in ids:
            job, record = jobs[rid], records[rid]
            if any(record.get(k) != job.get(k) for k in ('id','study','variant','model','packet','base_id')):
                raise ValueError('Configured request identity mismatch: '+rid)
            if job['packet'] not in packets:
                packets[job['packet']] = load(job['packet'])
            row = audit_record(record, packets[job['packet']], cohort)
            row['packet_path'] = job['packet']
            row['record_path'] = (f'output/judge_robustness_10/first_attempts/{rid}.json'
                if cohort == 'original_attempts' and rid in recovery_ids
                else f'output/judge_robustness_10/runs/{rid}.json')
            rows.append(row)
    source_hashes = {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(sources)}
    return {
        'schema': 'lossless-quote-reconciliation-v1',
        'status': 'completed_offline_secondary_diagnostic',
        'primary_results_replaced': False, 'human_labels_created': 0, 'new_model_requests': 0,
        'new_api_cost_usd': 0,
        'normalization_rule': 'Preserve raw literal quotes. Otherwise require every complete locator/value record to match the named artifact exactly, consume the entire quotation, and retain all values in separate evidence objects with verified locators. Unknown, wrong, partial, ambiguous or empty values remain unaltered.',
        'comparison_scope': 'Raw primary, historical frozen first-segment secondary, and new strict lossless secondary interface checks. These are evaluations of saved response formats, not new judge verdicts or accuracy estimates.',
        'original_attempts': summarize([r for r in rows if r['cohort'] == 'original_attempts']),
        'later_recovery_attempts': summarize([r for r in rows if r['cohort'] == 'later_recovery_attempts']),
        'first_attempt_provenance': provenance,
        'limitations': [
            'Exact matching establishes quotation traceability, not whether the evidence entails the verdict or whether the task/rubric is valid.',
            'No new human validation, model improvement, semantic correction, verdict change or population accuracy is claimed.',
            'Strict lossless normalization can retain fewer scorable responses than a permissive first-segment rule. Unrecognized formats remain invalid rather than partially accepted.',
            'Repeated requests and task families are dependent; original and later recovery attempts are reported separately.',
            'No historical raw record, ledger, primary grade, human label or frozen audit is overwritten.'],
        'rows': rows, 'source_hashes': source_hashes,
    }


def render_html(result):
    esc = html.escape
    cols = [('attempts','Attempts'), ('responses','Responses'), ('raw_primary_scorable','Raw primary scorable'),
            ('frozen_secondary_scorable','Frozen secondary scorable'), ('lossless_secondary_scorable','Lossless secondary scorable'),
            ('frozen_discarded_value_segments','Frozen discarded segments'), ('lossless_discarded_value_segments','Lossless discarded segments')]
    summary = ''.join('<tr><th>'+esc(label)+'</th>'+''.join('<td>'+str(result[k][key])+'</td>' for k in ('original_attempts','later_recovery_attempts'))+'</tr>' for key,label in cols)
    cases = ''.join('<tr><td>'+esc(r['cohort'])+'</td><td>'+esc(r['id'])+'</td><td>'+esc(r['raw_primary_status'])+'</td><td>'+str(r['frozen_secondary_scorable'])+'</td><td>'+str(r['lossless_secondary_scorable'])+'</td><td>'+str(r['frozen_discarded_value_segments'])+'</td></tr>' for r in result['rows'])
    return '<!doctype html><meta charset="utf-8"><title>Lossless quote reconciliation</title><style>body{font:16px/1.5 system-ui;margin:40px auto;max-width:1100px;color:#18323b}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #ccd6d8;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}details{margin:24px 0}.note{background:#edf5f0;padding:18px}</style><h1>Quote evidence preserved, historical results retained</h1><p class="note">This is a completed offline interface audit. No model calls or human labels were created. Raw primary results remain unchanged; secondary scorable counts are not judge accuracy.</p><p>'+esc(result['normalization_rule'])+'</p><table><tr><th>Check</th><th>Original attempts</th><th>Later recoveries</th></tr>'+summary+'</table><p>Every strict lossless transformation retains all verified values and locators. The historical first-segment method can discard quoted context. Passing either interface check does not establish that the quoted evidence supports the conclusion.</p><details><summary>Every saved attempt</summary><table><tr><th>Cohort</th><th>Request</th><th>Raw status</th><th>Frozen scorable</th><th>Lossless scorable</th><th>Frozen segments discarded</th></tr>'+cases+'</table></details><p><a href="lossless-audit.json">Detailed evidence, affected IDs, retained values and source hashes</a></p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in result['limitations'])+'</ul>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = build(args.root)
    folder = args.root/'output/strengthening_13'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'lossless-audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    (folder/'lossless-audit.html').write_text(render_html(result))
    keys=('attempts','responses','raw_primary_scorable','frozen_secondary_scorable',
          'lossless_secondary_scorable','lossless_discarded_value_segments')
    print(json.dumps({'status':result['status'], 'new_model_requests':0,
        **{cohort:{k:result[cohort][k] for k in keys} for cohort in ('original_attempts','later_recovery_attempts')}}))


if __name__ == '__main__':
    main()
