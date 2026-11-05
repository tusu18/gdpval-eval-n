"""Validate frozen contracts and bounded quote provenance, never judge accuracy.

Raw assessments are immutable inputs. Quote failures remain explicit flags and do
not delete a criterion or whole assessment. This module makes no model calls.
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evaluation_v4'
VERDICTS = {'pass', 'fail', 'uncertain', 'not_assessed'}
CHECKS = {'pass', 'fail', 'uncertain', 'not_applicable'}
CLASSES = {'substantive_business_error', 'presentation_defect', 'missing_deliverable',
           'source_issue', 'infrastructure_or_tool_issue', 'unresolved_interpretation', 'none'}
COVERAGE = {'text': {'complete', 'partial', 'unavailable'},
            'formulas': {'complete', 'partial', 'unavailable', 'not_applicable'},
            'visual': {'complete', 'partial', 'unavailable'},
            'behavior': {'executed', 'not_executed', 'not_applicable'}}


def norm(value):
    return re.sub(r'\s+', ' ', str(value)).strip()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def resolved(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def evidence_index(packet):
    """Index neutral S/A/E IDs and filenames; preserve ambiguous aliases."""
    index, issues, views = {}, [], set()
    index['original_prompt'] = [{'id': 'original_prompt', 'text': packet.get('original_prompt', ''),
                                 'units': [], 'kind': 'source'}]
    for kind, group in (('source', packet.get('sources', [])), ('artifact', packet.get('artifacts', []))):
        for item in group:
            try:
                ex = json.loads(resolved(item['extraction']).read_text())
                units = ex.get('units', [])
                record = {'id': item['id'], 'text': '\n'.join(str(u.get('text', '')) for u in units),
                          'units': units, 'kind': kind}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                issues.append(f"Extraction unavailable for {item.get('id')}: {type(exc).__name__}")
                record = {'id': item.get('id'), 'text': None, 'units': [], 'kind': kind}
            path = item.get('path', '')
            aliases = {item.get('id'), item.get('original_name'), item.get('submitted_filename'),
                       path, Path(path).name, item.get('url')}
            for alias in aliases - {None, ''}:
                index.setdefault(str(alias), []).append(record)
            views.update(v['id'] for v in item.get('views', []) if isinstance(v, dict) and 'id' in v)
    return index, issues, views


def check_quote(evidence, field, criterion_id, index):
    quote = evidence.get('quote', evidence.get('supporting_quote'))
    ref = evidence.get('source') or evidence.get('artifact') or evidence.get('file')
    locator = evidence.get('locator') or evidence.get('section_or_range')
    result = {'criterion_id': criterion_id, 'field': field, 'reference': ref,
              'locator': locator, 'quote': quote, 'status': 'requires_manual_verification',
              'match_variant': None, 'locator_verified': False,
              'view_id': evidence.get('view_id'), 'view_ids': evidence.get('view_ids')}
    records = index.get(str(ref), index.get(Path(str(ref)).name, []))
    records = {r['id']: r for r in records}
    if len(records) != 1:
        result['flag'] = 'unknown_or_ambiguous_reference'
        return result
    record = next(iter(records.values()))
    text = record['text']
    if text is None:
        result['flag'] = 'extraction_unavailable'
        return result
    units = [u for u in record['units'] if norm(u.get('locator', '')) == norm(locator)]
    scope = '\n'.join(str(u.get('text', '')) for u in units) if units else None
    if record['id'] == 'original_prompt' and isinstance(locator, str):
        span = re.search(r'characters?\s+(\d+)\s*:\s*(\d+)', locator)
        if span:
            a, b = map(int, span.groups())
            if 0 <= a <= b <= len(text):
                scope = text[a:b]
    variants = [('raw', quote), ('whitespace_only', norm(quote))]
    # Strip only an explicitly cited, existing locator prefix; never punctuation,
    # numbers, qualifiers or arbitrary bracketed text from the substantive quote.
    if scope is not None and nonempty(locator):
        for prefix in (f'[{locator}] ', f'{locator}: ', f'{locator} | '):
            if quote.startswith(prefix):
                variants.append(('explicit_locator_prefix_removed', quote[len(prefix):]))
    for variant, candidate in variants:
        if not candidate:
            continue
        haystack = text if variant == 'raw' else norm(text)
        needle = candidate if variant == 'raw' else norm(candidate)
        if needle in haystack:
            result.update(status='text_verified', match_variant=variant,
                          locator_verified=scope is not None and norm(candidate) in norm(scope))
            if not result['locator_verified']:
                result['flag'] = 'text_matches_but_locator_requires_manual_verification'
            return result
    result['flag'] = 'quote_not_found_in_available_extraction'
    return result


def validate(packet, judgment, frozen_hash=None, frozen_task=None):
    problems, quotes = [], []
    if not isinstance(judgment, dict):
        return {'task_id': packet.get('task_id'), 'contract_valid': False,
                'contract_problems': ['Judgment must be an object'], 'quotes': [], 'quote_counts': {},
                'criteria_counts': {}, 'accuracy_or_human_acceptance_validated': False}
    index, packet_issues, available_views = evidence_index(packet)
    expected_rubric = frozen_task if frozen_task is not None else packet.get('rubric', {})
    rubric_criteria = expected_rubric.get('criteria', [])
    expected = {c['criterion_id']: c for c in rubric_criteria}
    required = ('task_id', 'rubric_sha256', 'reviewer_requested_model', 'artifacts_inspected',
                'rendered_views_inspected', 'criteria', 'confirmed_failures', 'unresolved_questions',
                'suggested_first_human_question', 'overall', 'decision', 'human_acceptance')
    problems += [f'Missing top-level field: {key}' for key in required if key not in judgment]
    if judgment.get('task_id') != packet.get('task_id'):
        problems.append('Task ID mismatch')
    target_hash = frozen_hash or packet.get('rubric_sha256')
    if judgment.get('rubric_sha256') != target_hash or packet.get('rubric_sha256') != target_hash:
        problems.append('Rubric hash mismatch')
    if frozen_task is not None and packet.get('rubric') != frozen_task:
        problems.append('Packet rubric differs from frozen task rubric')
    if not nonempty(judgment.get('reviewer_requested_model')):
        problems.append('reviewer_requested_model must be a nonempty string')
    if not isinstance(judgment.get('suggested_first_human_question'), str):
        problems.append('suggested_first_human_question must be a string')
    if judgment.get('human_acceptance') is not None:
        problems.append('human_acceptance must remain null')
    for key in ('artifacts_inspected', 'rendered_views_inspected', 'confirmed_failures', 'unresolved_questions'):
        if not isinstance(judgment.get(key), list):
            problems.append(f'{key} must be an array')
    criteria = judgment.get('criteria', [])
    if not isinstance(criteria, list):
        problems.append('criteria must be an array')
        criteria = []
    if any(not isinstance(c, dict) for c in criteria):
        problems.append('Every criterion must be an object')
    criteria = [c for c in criteria if isinstance(c, dict)]
    ids = [str(c.get('criterion_id')) for c in criteria]
    if Counter(ids) != Counter(expected.keys()):
        problems.append('Missing, duplicate, or unexpected criterion IDs')
    for c in criteria:
        cid = str(c.get('criterion_id')); prefix = cid + ': '
        verdict = c.get('verdict'); severity = c.get('severity'); failure_class = c.get('failure_class')
        if verdict not in VERDICTS:
            problems.append(prefix + 'invalid verdict')
        if 'severity' not in c or (severity is not None and (type(severity) is not int or not 1 <= severity <= 5)):
            problems.append(prefix + 'severity must be null or integer 1–5')
        if failure_class not in CLASSES:
            problems.append(prefix + 'invalid failure_class')
        if verdict == 'fail' and (type(severity) is not int or not 1 <= severity <= 5 or failure_class == 'none'):
            problems.append(prefix + 'fail requires severity 1–5 and a non-none failure class')
        if verdict == 'pass' and (severity is not None or failure_class != 'none'):
            problems.append(prefix + 'pass requires null severity and failure_class none')
        applicable = expected.get(cid, {}).get('stated_and_honored_separately', False)
        for key in ('stated_check', 'honored_check'):
            if key in c and c[key] not in CHECKS:
                problems.append(prefix + key + ' invalid enum')
            if applicable and c.get(key) not in CHECKS - {'not_applicable'}:
                problems.append(prefix + key + ' required for stated/honored criterion')
            if applicable and verdict == 'pass' and c.get(key) != 'pass':
                problems.append(prefix + key + ' must pass for overall criterion pass')
        if not nonempty(c.get('reason')):
            problems.append(prefix + 'reason must be nonempty')
        if not nonempty(c.get('counterevidence_search')):
            problems.append(prefix + 'counterevidence_search must identify inspected scope')
        if 'human_review_question' not in c or (c['human_review_question'] is not None and not isinstance(c['human_review_question'], str)):
            problems.append(prefix + 'human_review_question must be a string or null')
        coverage = c.get('coverage')
        if not isinstance(coverage, dict):
            problems.append(prefix + 'coverage must be an object')
        else:
            for key, choices in COVERAGE.items():
                if coverage.get(key) not in choices:
                    problems.append(prefix + 'invalid/missing coverage.' + key)
        for field in ('source_evidence', 'output_evidence', 'counterevidence', 'operative_sections_inspected', 'calculation_evidence'):
            evidence_list = c.get(field)
            if not isinstance(evidence_list, list):
                problems.append(prefix + field + ' must be an array'); continue
            for evidence in evidence_list:
                if not isinstance(evidence, dict):
                    problems.append(prefix + field + ' entries must be objects'); continue
                if field == 'calculation_evidence':
                    for key in ('inputs', 'method', 'expected', 'observed', 'tolerance'):
                        if key not in evidence:
                            problems.append(prefix + 'calculation_evidence missing ' + key)
                    continue
                keys = {'source_evidence': ('source', 'locator', 'quote'),
                        'output_evidence': ('artifact', 'locator', 'quote'),
                        'counterevidence': ('artifact', 'locator', 'quote', 'effect'),
                        'operative_sections_inspected': ('artifact', 'section_or_range')}[field]
                for key in keys:
                    if not nonempty(evidence.get(key)):
                        problems.append(prefix + field + ' missing/non-string ' + key)
                if field == 'operative_sections_inspected' and not isinstance(evidence.get('view_ids'), list):
                    problems.append(prefix + 'operative_sections_inspected.view_ids must be an array')
                quote = evidence.get('quote', evidence.get('supporting_quote'))
                if nonempty(quote):
                    quotes.append(check_quote(evidence, field, cid, index))
                view_ids = evidence.get('view_ids', [])
                if not isinstance(view_ids, list):
                    view_ids = []
                if evidence.get('view_id'):
                    view_ids = view_ids + [evidence['view_id']]
                if any(not isinstance(v, str) or v not in available_views for v in view_ids):
                    packet_issues.append(prefix + 'view reference requires verification against packet or separate test evidence')
        if verdict == 'fail':
            if not c.get('source_evidence'):
                problems.append(prefix + 'fail needs source/prompt evidence of the violated requirement')
            if not c.get('output_evidence') and not c.get('operative_sections_inspected'):
                problems.append(prefix + 'fail needs output evidence or inspected scope for an absence claim')
    verdicts = [c.get('verdict') for c in criteria]
    overall = ('project_rubric_fail' if 'fail' in verdicts else
               'project_rubric_uncertain' if not criteria or any(v != 'pass' for v in verdicts) else
               'project_rubric_pass')
    decision = {'project_rubric_fail': 'requires_revision', 'project_rubric_uncertain': 'unresolved',
                'project_rubric_pass': 'no_confirmed_issue'}[overall]
    if judgment.get('overall') != overall:
        problems.append('Overall does not follow frozen aggregation')
    if judgment.get('decision') != decision:
        problems.append('Decision does not follow frozen aggregation')
    return {'task_id': packet.get('task_id'), 'contract_problems': problems, 'contract_valid': not problems,
            'criteria_counts': dict(Counter(str(v) for v in verdicts)), 'quotes': quotes,
            'quote_counts': dict(Counter(q['status'] for q in quotes)),
            'provenance_flags': packet_issues + [q for q in quotes if q.get('flag')],
            'accuracy_or_human_acceptance_validated': False}


def main():
    rubric_path = ROOT / 'data/evaluation_v4/project-rubrics.json'
    rubric_bytes = rubric_path.read_bytes()
    rubric_hash = hashlib.sha256(rubric_bytes).hexdigest()
    frozen = {t['task_id']: t for t in json.loads(rubric_bytes)['tasks']}
    results = []
    for path in sorted((OUT / 'assessments').glob('*.json')):
        if path.stem == 'validation':
            continue
        packet_path = OUT / 'judge-packets' / path.stem / 'packet.json'
        try:
            packet = json.loads(packet_path.read_text())
            judgment = json.loads(path.read_text())
            if path.stem not in frozen:
                raise ValueError('No frozen rubric for assessment filename')
            result = validate(packet, judgment, rubric_hash, frozen[path.stem])
            if packet.get('task_id') != path.stem:
                result['contract_problems'].append('Assessment filename/task mismatch')
                result['contract_valid'] = False
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result = {'task_id': path.stem, 'contract_valid': False,
                      'contract_problems': [f'Assessment or packet could not be validated: {type(exc).__name__}: {exc}'],
                      'criteria_counts': {}, 'quotes': [], 'quote_counts': {},
                      'accuracy_or_human_acceptance_validated': False}
        result['assessment_path'] = str(path.relative_to(ROOT))
        result['assessment_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        results.append(result)
    dest = OUT / 'assessments/validation.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'validator_schema': 'v4-contract-provenance-2', 'rubric_sha256': rubric_hash,
                               'checks': results, 'interpretation': 'Mechanical contract and quote checks only. Raw judgments remain unchanged. Every unmatched quote and unverified locator remains a flag; no criterion is dropped. Text match does not establish correct interpretation, native behavior, visual coverage, accuracy or human acceptance.'}, indent=2) + '\n')
    print(json.dumps([{key: r[key] for key in ('task_id', 'contract_valid', 'criteria_counts', 'quote_counts')} for r in results]))


if __name__ == '__main__':
    main()
