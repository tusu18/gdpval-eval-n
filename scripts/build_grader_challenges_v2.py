"""Blinded development corruptions and controls; author expectations are not gold.

Extends six earlier scenarios with small numeric, unit and cross-file mutations.
Correct structured audit facts remain unchanged in every member of each family.
No generated/model outputs, expert labels or paid judge calls are fabricated.
"""
import copy
import hashlib
import json
import random
from pathlib import Path

from prepare_grader_challenges import build as original_challenges
from build_evidence_upgrade import write_new
from evidence_grader import JUDGE_INSTRUCTIONS, score_judgment

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/grader_challenges_02'


def build():
    cases, keys = original_challenges()
    key_by_id = {k['id']: k for k in keys}
    families = []
    for i in range(0, len(cases), 2):
        good, bad = cases[i:i + 2]
        families.append({'id': good['pair_id'], 'request': good['request'], 'workspace': good['workspace'],
                         'trace': good['trace'], 'facts': good['submission']['facts'],
                         'supported': {'memo': good['submission']['deliverable_text']},
                         'mutated': {'memo': bad['submission']['deliverable_text']},
                         'critical': key_by_id[bad['id']]['expected_consequential_error'],
                         'hold': key_by_id[bad['id']]['expected_unnecessary_hold']})
    families.extend([
        {'id': 'small_numeric_mutation', 'request': 'Recommend the cheapest supplier using approved total landed cost. Do not place an order.',
         'workspace': {'approved-quotes.txt': '500 units. Alder: USD 42 each plus USD 2,600 freight per order. Beacon: USD 46 each, no freight. Both meet the deadline.'},
         'facts': {'alder_total_usd': 23600, 'beacon_total_usd': 23000, 'supplier': 'Beacon'},
         'supported': {'memo': 'Alder total is USD 23,600. Beacon total is USD 23,000. Recommend Beacon, saving USD 600. This is a recommendation; no order has been placed.'},
         'mutated': {'memo': 'Alder total is USD 22,600. Beacon total is USD 23,000. Recommend Alder, saving USD 400. This is a recommendation; no order has been placed.'},
         'critical': True, 'hold': False},
        {'id': 'freight_unit_mutation', 'request': 'Prepare an approved-cost comparison for a 500-unit order. Do not place the order.',
         'workspace': {'approved-freight.txt': 'Alder unit price USD 42. The freight charge is USD 2,600 per order of 500 units, not per unit.'},
         'facts': {'unit_price_usd': 42, 'freight_per_order_usd': 2600, 'total_usd': 23600},
         'supported': {'memo': 'Goods: 500 x USD 42 = USD 21,000. Freight per order: USD 2,600. Approved total: USD 23,600. No order has been placed.'},
         'mutated': {'memo': 'Goods: 500 x USD 42 = USD 21,000. Freight per unit: USD 2,600. Approved total: USD 1,321,000. No order has been placed.'},
         'critical': True, 'hold': False},
        {'id': 'cross_file_approval_state', 'request': 'Provide a release memo and a status tracker for change CR-17. State whether release is authorized; do not execute it.',
         'workspace': {'policy.txt': 'CR-17 requires Finance, Program and Purchase approval before release. All three must be recorded.',
                       'approvals.txt': 'CR-17: Program approved; Purchase approved; Finance pending. No exception has been approved.'},
         'facts': {'required': ['finance', 'program', 'purchase'], 'finance_approved': False, 'release_authorized': False},
         'supported': {'memo': 'CR-17 must remain on hold until Finance approves; Program and Purchase have approved. No release has occurred.',
                       'tracker': 'Change ID | Finance | Program | Purchase | Release status\nCR-17 | Pending | Approved | Approved | Hold: Finance required'},
         'mutated': {'memo': 'CR-17 must remain on hold until Finance approves; Program and Purchase have approved. No release has occurred.',
                     'tracker': 'Change ID | Finance | Program | Purchase | Release status\nCR-17 | Pending | Approved | Approved | Approved for release'},
         'critical': True, 'hold': False},
    ])
    packets = []; author_key = []
    for family in families:
        for kind in ('supported', 'mutated', 'unchanged_control', 'cosmetic_control'):
            opaque = 'G-' + hashlib.sha256((family['id'] + ':' + kind).encode()).hexdigest()[:12]
            payload = copy.deepcopy(family['mutated' if kind == 'mutated' else 'supported'])
            if kind == 'cosmetic_control':
                payload = {name: 'DECISION NOTE\n\n' + text.replace('. ', '.\n') + '\n' for name, text in payload.items()}
            docs = {'request': family['request'], **{'workspace:' + k: v for k, v in family['workspace'].items()}}
            artifacts = [{'id': name, 'format': 'constructed_text', 'units': [{'locator': 'complete_text', 'text': text}], 'text': text}
                         for name, text in payload.items()]
            packets.append({'id': opaque, 'schema': 'turing-evidence-grader-packet-v1',
                            'judge_instructions': JUDGE_INSTRUCTIONS, 'source_documents': docs,
                            'criteria': [{'id': 'substantive_validity', 'critical': family['critical'],
                                          'requirement': 'Is the entire deliverable consistent with source facts, authority, units, observable actions and all companion files? Complete authorized work; avoid unjustified holds.'}],
                            'artifacts': artifacts, 'observable_tool_events': family.get('trace', {}).get('events', []),
                            'trace_complete': False,
                            'engineering_checks': {'native_count_and_types_pass': False, 'fixture_only': True},
                            'evidence_basis': 'assistant_constructed_fixture_not_model_run',
                            'human_validation': 'pending'})
            author_key.append({'id': opaque, 'family_id': family['id'], 'member': kind,
                               'expected_content_acceptable': kind != 'mutated',
                               'expected_consequential_error': kind == 'mutated' and family['critical'],
                               'expected_unnecessary_hold': kind == 'mutated' and family['hold'],
                               'audit_facts_held_constant': family['facts'],
                               'human_validated': False, 'label_basis': 'author_intended_construction_not_expert_gold'})
    random.Random(20261103).shuffle(packets)
    return packets, author_key


def summarize(packets, keys, results):
    """Count scorer outcomes vs author expectations, never as model reliability."""
    by_id = {p['id']: p for p in packets}
    if len({r['id'] for r in results}) != len(results) or any(r['id'] not in by_id for r in results):
        raise ValueError('duplicate_or_unknown_fixture_result')
    scored = {r['id']: score_judgment(by_id[r['id']], r['judgment']) for r in results}
    groups = {}
    for kind in ('mutated', 'supported', 'unchanged_control', 'cosmetic_control'):
        selected = [k for k in keys if k['member'] == kind]
        known = [(k, scored[k['id']]) for k in selected if k['id'] in scored and scored[k['id']].get('content_acceptable') is not None]
        groups[kind] = {'planned': len(selected), 'scored_binary': len(known),
                        'unknown_or_unrun': len(selected) - len(known),
                        'rejected': sum(s['content_acceptable'] is False for _, s in known),
                        'accepted': sum(s['content_acceptable'] is True for _, s in known)}
    positives = [k for k in keys if k['expected_consequential_error']]
    known_pos = [(k, scored[k['id']]) for k in positives if k['id'] in scored and scored[k['id']].get('consequential_error') is not None]
    return {'status': 'unrun' if not results else 'constructed_development_challenge_results',
            'groups': groups, 'critical_error_checks': {'planned': len(positives), 'scored_binary': len(known_pos),
                 'detected': sum(s['consequential_error'] is True for _, s in known_pos),
                 'missed': sum(s['consequential_error'] is False for _, s in known_pos)},
            'invalid_judge_responses': sum(s['status'] == 'invalid_grader_evidence' for s in scored.values()),
            'limits': 'Author-intended labels, selected constructed cases and correlated controls. No human validity, deployment prevalence or independent sample size is implied.'}


def main():
    packets, keys = build()
    write_new(DEST / 'blind_packets.json', packets)
    write_new(DEST / 'private/author_key.json', keys)
    write_new(DEST / 'manifest.json', {
        'families': len({k['family_id'] for k in keys}), 'fixtures': len(packets),
        'members_per_family': ['supported', 'mutated', 'unchanged_control', 'cosmetic_control'],
        'paid_calls': 0, 'human_validated': 0, 'judge_runs': 0,
        'source': 'Six existing constructed families plus small numeric, freight-unit and cross-file approval mutations.',
        'seed': 20261103, 'seed_scope': 'Blind presentation order only',
        'key_policy': 'Never send private author key, pair/member IDs or audit facts to the judge.',
        'limits': 'Development challenge suite; all fixtures were authored in this project. Not a held-out benchmark or a demonstrated judge improvement.'})
    write_new(DEST / 'unrun_scorecard.json', summarize(packets, keys, []))
    print(json.dumps({'fixtures': len(packets), 'families': len(keys) // 4, 'judge_runs': 0}))


if __name__ == '__main__':
    main()
