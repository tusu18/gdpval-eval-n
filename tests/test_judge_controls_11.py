import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_judge_controls_11 import build, inspect, materialize_request, materials, source_families


PHASE = {'jobs': [{'study': 'sensitivity', 'model': 'fixed/test-judge'}],
         'variants': {'v1_reword': 'Equivalent grading instructions used only as a test fixture.'},
         'max_tokens': 16000, 'reasoning_effort': 'high', 'response_format': {'type': 'json_object'}}


class JudgeControlsTests(unittest.TestCase):
    def setUp(self):
        self.packets, self.keys, self.config, self.manifest, self.scorecard = materials(copy.deepcopy(PHASE))
        self.by_id = {p['id']: p for p in self.packets}

    def family(self, fid):
        return {k['member']: self.by_id[k['id']] for k in self.keys if k['family_id'] == fid}

    def body(self, packet):
        return [u['text'] for u in packet['artifacts'][0]['units'] if u['locator'].endswith(':body')]

    def test_same_sources_and_only_action_mutated(self):
        for f in source_families():
            group = self.family(f['id'])
            self.assertEqual(len(group), 4)
            for packet in group.values():
                self.assertEqual(packet['source_documents'], group['supported']['source_documents'])
                self.assertEqual(packet['criteria'], group['supported']['criteria'])
                self.assertGreater(len(packet['artifacts'][0]['text'].split()), 400)
            original = group['supported']['artifacts'][0]['text']
            mutated = group['contradicted_action']['artifacts'][0]['text']
            self.assertEqual(original.replace(f['mutate_from'], f['mutate_to']), mutated)
            self.assertIn(f['counterevidence'], mutated)

    def test_cosmetic_control_preserves_every_body_paragraph(self):
        for fid in ('continuity_window', 'approval_authority'):
            group = self.family(fid)
            self.assertEqual(self.body(group['contradicted_action']), self.body(group['cosmetic_control']))
            self.assertNotEqual(group['contradicted_action']['artifacts'][0]['text'], group['cosmetic_control']['artifacts'][0]['text'])

    def test_conditional_plans_preserve_useful_authorized_work(self):
        group = self.family('approval_authority')
        conditional = group['conditional_plan']['artifacts'][0]['text']
        self.assertIn('Continue authorized CR-205 work independently.', conditional)
        self.assertIn('Pre-stage the version-7 release package without sending it.', conditional)
        continuity = self.family('continuity_window')['conditional_plan']['artifacts'][0]['text']
        self.assertIn('No quantity is assumed available by stating these conditions.', continuity)
        self.assertIn('3,960 units', continuity)
        self.assertIn('5,160 units', continuity)
        self.assertEqual(99 * 40, 3960)
        self.assertEqual(129 * 40, 5160)

    def test_author_labels_do_not_enter_judge_packets(self):
        for packet in self.packets:
            serialized = json.dumps(packet)
            for secret in ('expected_content_acceptable', 'expected_consequential_error', 'family_id', 'contradicted_action', 'author_intended_construction'):
                self.assertNotIn(secret, serialized)
            self.assertEqual(packet['human_validation'], 'pending')
        self.assertEqual(sum(k['expected_consequential_error'] for k in self.keys), 4)
        self.assertTrue(all(k['human_validated'] is False for k in self.keys))

    def test_identical_repeat_settings_and_posthoc_dependency(self):
        order = {j: i for i, j in enumerate(self.config['planned_execution_order'])}
        self.assertEqual(len(order), 40)
        self.assertFalse(self.config['execution_enabled'])
        for packet in self.packets:
            jobs = [j for j in self.config['jobs'] if j['case_id'] == packet['id']]
            self.assertEqual(len(jobs), 5)
            repeats = [j for j in jobs if j['arm'] == 'original']
            self.assertEqual([j['repeat'] for j in repeats], [1, 2, 3])
            self.assertEqual(len({(j['packet'], j['model'], j['prompt_key']) for j in repeats}), 1)
            review = next(j for j in jobs if j['arm'] == 'self_review')
            self.assertEqual(review['depends_on'], [packet['id'] + '__original_r1'])
            self.assertLess(order[review['depends_on'][0]], order[review['id']])
        self.assertIn('saved initial judgment', self.config['prompts']['self_review'])

    def test_no_results_or_native_comparison_are_invented(self):
        self.assertEqual(self.manifest['executed_requests'], 0)
        self.assertEqual(self.manifest['human_validated_cases'], 0)
        self.assertIsNone(self.manifest['reported_api_cost_usd'])
        self.assertIsNone(self.manifest['runtime_seconds'])
        self.assertTrue(all(v['value'] is None for v in self.scorecard['metrics'].values()))
        self.assertEqual(self.config['native_inspection_arm']['status'], 'not_prepared_not_run')

    def test_materialized_repeats_identical_and_reword_changes_system_only(self):
        packet = self.packets[0]
        jobs = [j for j in self.config['jobs'] if j['case_id'] == packet['id']]
        originals = [materialize_request(self.config, j, packet) for j in jobs if j['arm'] == 'original']
        self.assertEqual(originals[0], originals[1])
        self.assertEqual(originals[1], originals[2])
        reword = materialize_request(self.config, next(j for j in jobs if j['arm'] == 'reword'), packet)
        self.assertNotEqual(reword['messages'][0], originals[0]['messages'][0])
        self.assertEqual(reword['messages'][1], originals[0]['messages'][1])
        self.assertEqual({k: v for k, v in reword.items() if k != 'messages'},
                         {k: v for k, v in originals[0].items() if k != 'messages'})
        user = json.loads(reword['messages'][1]['content'])['packet']
        self.assertNotIn('judge_instructions', user)
        self.assertEqual(user['source_documents'], packet['source_documents'])
        self.assertEqual(user['artifacts'], packet['artifacts'])

    def test_materialized_self_review_requires_matching_saved_response(self):
        packet = self.packets[0]
        job = next(j for j in self.config['jobs'] if j['case_id'] == packet['id'] and j['arm'] == 'self_review')
        record = {'id': packet['id'] + '__original_r1', 'case_id': packet['id'], 'packet': job['packet'],
                  'model': job['model'], 'status': 'received', 'judgment': {'criteria': [], 'task_defect': {'status': 'uncertain'}}}
        with self.assertRaisesRegex(ValueError, 'Saved original_r1 response'):
            materialize_request(self.config, job, packet)
        result = materialize_request(self.config, job, packet, record)
        payload = json.loads(result['messages'][1]['content'])
        self.assertEqual(payload['initial_judgment'], record['judgment'])
        self.assertEqual(payload['packet']['artifacts'], packet['artifacts'])
        self.assertNotIn('judge_instructions', payload['packet'])
        record['id'] += '_other'
        with self.assertRaisesRegex(ValueError, 'identity does not match'):
            materialize_request(self.config, job, packet, record)

    def test_materializer_rejects_edited_task_or_output_under_same_case_id(self):
        packet = self.packets[0]
        job = next(j for j in self.config['jobs'] if j['case_id'] == packet['id'] and j['arm'] == 'original')
        changed_task = copy.deepcopy(packet)
        changed_task['source_documents']['request'] += ' Changed request.'
        with self.assertRaisesRegex(ValueError, 'configured input hash'):
            materialize_request(self.config, job, changed_task)
        changed_output = copy.deepcopy(packet)
        changed_output['artifacts'][0]['units'][1]['text'] += ' Changed output.'
        with self.assertRaisesRegex(ValueError, 'configured input hash'):
            materialize_request(self.config, job, changed_output)

    def test_materializer_rejects_changed_job_model_prompt_or_packet_path(self):
        packet = self.packets[0]
        job = next(j for j in self.config['jobs'] if j['case_id'] == packet['id'] and j['arm'] == 'original')
        for field, value in [('model', 'other/judge'), ('prompt_key', 'reword'), ('packet', 'other-packet.json')]:
            modified = copy.deepcopy(job); modified[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'exact proposed configuration'):
                    materialize_request(self.config, modified, packet)

    def test_saved_bundle_is_self_contained_and_repeat_build_is_safe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build(root, copy.deepcopy(PHASE))
            result = inspect(root)
            self.assertEqual(result['packet_hashes_verified'], 8)
            self.assertEqual(result['author_evidence_quotes_verified'], 24)
            self.assertEqual(result['planned_requests'], 40)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            build(root, copy.deepcopy(PHASE))
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            for packet in self.packets:
                page = root / 'reviews/judge_controls_11' / (packet['id'] + '.html')
                text = page.read_text()
                self.assertIn('Complete sources', text)
                self.assertIn('Complete output', text)
                self.assertNotIn('expected_content_acceptable', text)
                self.assertNotIn('contradicted_action', text)
                self.assertNotIn('src=', text)

    def test_inspector_rejects_tampered_packet_and_builder_will_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); build(root, copy.deepcopy(PHASE))
            path = next((root / 'data/judge_controls_11/packets').glob('*.json'))
            path.write_text(path.read_text() + ' ')
            with self.assertRaisesRegex(ValueError, 'Packet hash changed'):
                inspect(root)
            with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
                build(root, copy.deepcopy(PHASE))

    def test_inspector_rejects_fabricated_measured_result(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); build(root, copy.deepcopy(PHASE))
            path = root / 'data/judge_controls_11/unrun_scorecard.json'
            score = json.loads(path.read_text()); score['metrics']['errors_recovered']['value'] = 0
            path.write_text(json.dumps(score))
            with self.assertRaisesRegex(ValueError, 'measured result'):
                inspect(root)


if __name__ == '__main__':
    unittest.main()
