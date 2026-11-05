import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_evidence_upgrade import ROOT, DEST, repair, evidence_map, validate
from evidence_grader import extract_artifact, prepare_packet, score_judgment
from build_grader_challenges_v2 import build, summarize
from check_evidence_upgrade import budget_status, future_stage_budget
from run_repair_probe import BudgetStop


def docx(path, text):
    from xml.sax.saxutils import escape
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + escape(text) + '</w:t></w:r></w:p></w:body></w:document>')


def xlsx(path, value, formula=None):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook/>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1">' +
                   (f'<f>{formula}</f>' if formula else '') + f'<v>{value}</v></c></row></sheetData></worksheet>')


def sample_packet():
    return {'source_documents': {'policy': 'Finance approval is required before release.'},
            'criteria': [{'id': 'approval', 'critical': True}, {'id': 'presentation', 'critical': False}],
            'artifacts': [{'id': 'memo.docx', 'units': [{'text': 'Release now without Finance approval.'}]}],
            'engineering_checks': {'native_count_and_types_pass': True}}


def sample_judgment():
    return {'task_defect': {'status': 'no', 'reason': 'The rule is explicit.'}, 'criteria': [
        {'id': cid, 'status': 'fail' if cid == 'approval' else 'pass',
         'rationale': 'Constructed validator fixture, not a real judge assessment.',
         'evidence_kind': 'quoted', 'evidence': [{'source_id': 'policy', 'source_quote': 'Finance approval is required before release.',
             'artifact_id': 'memo.docx', 'output_quote': 'Release now without Finance approval.'}],
         'consequence': 'Unauthorized release.', 'minimum_correction': 'Hold until Finance approval.',
         'counterevidence': 'None in the constructed fixture.'} for cid in ['approval', 'presentation']]}


class TaskMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = json.loads((DEST / 'grader/evidence_maps.json').read_text())
        cls.rubrics = {r['id']: r for r in json.loads((DEST / 'grader/rubrics.json').read_text())}

    def task(self, instance):
        return json.loads((DEST / 'solver' / f'{instance}.json').read_text())

    def test_all_fifteen_maps_have_resolving_anchors(self):
        self.assertEqual(len(self.maps), 15)
        for m in self.maps:
            self.assertEqual(validate(self.task(m['instance_id']), m, self.rubrics[m['family_id']]), [])

    def test_source_edit_invalidates_map(self):
        m = self.maps[0]; task = self.task(m['instance_id'])
        task['workspace']['operations/record-r2.txt'] += ' Unauthorized change.'
        errors = validate(task, m, self.rubrics[m['family_id']])
        self.assertIn('task_hash_mismatch', errors)
        self.assertTrue(any(e.startswith('broken_anchor') for e in errors))

    def test_wrong_numeric_key_is_caught_against_visible_sources(self):
        task = self.task('original_supplier_landed_cost__recovery')
        m = evidence_map(task, copy.deepcopy(self.rubrics[task['family_id']]))
        m['canonical_facts']['alder_total_usd'] = 22600
        self.assertIn('landed_cost_source_oracle_disagrees', validate(task, m, self.rubrics[task['family_id']]))

    def test_wrong_numeric_criterion_cannot_hide_behind_correct_key(self):
        task = self.task('original_supplier_landed_cost__conflict')
        m = evidence_map(task, copy.deepcopy(self.rubrics[task['family_id']]))
        next(c for c in m['criteria'] if c['id'] == 'landed_cost')['expected']['savings_usd'] = 400
        self.assertIn('landed_cost_criterion_disagrees', validate(task, m, self.rubrics[task['family_id']]))

    def test_completed_blank_form_conflict_is_caught(self):
        task = self.task('change_control__recovery')
        task['prompt'] += '\nYou are producing a completed Change Request Form.'
        m = evidence_map(task, self.rubrics['change_control'])
        self.assertIn('blank_vs_completed_form_conflict', validate(task, m, self.rubrics['change_control']))

    def test_approval_before_log_is_caught_even_with_refreshed_hashes(self):
        task = self.task('original_delivery_appointment__conflict')
        task['workspace']['project/decision-register.txt'] = 'operations/record-r2.txt approved 2026-10-19.'
        m = evidence_map(task, self.rubrics[task['family_id']])
        self.assertIn('approval_predates_current_log', validate(task, m, self.rubrics[task['family_id']]))

    def test_recovery_requires_real_clarification(self):
        task = self.task('original_delivery_appointment__recovery')
        task['clarifications'][0]['keywords'] = ['unmatchable']
        m = evidence_map(task, self.rubrics[task['family_id']])
        self.assertIn('clarification_not_recoverable', validate(task, m, self.rubrics[task['family_id']]))

    def test_paired_workspace_and_contract_are_constant(self):
        for family in self.rubrics:
            ts = [self.task(family + '__' + v) for v in ('baseline', 'recovery', 'conflict')]
            for t in ts[1:]:
                for field in ('workspace', 'clarifications', 'deliverable_count', 'deliverable_format'):
                    self.assertEqual(t.get(field), ts[0].get(field))


class NativePacketTests(unittest.TestCase):
    def test_xml_in_a_zip_is_not_accepted_as_an_office_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fake.docx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('word/document.xml', '<document/>')
            with self.assertRaisesRegex(ValueError, 'missing_office_package_metadata'):
                extract_artifact(path)

    def test_reads_actual_docx_not_facts_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memo.docx'; docx(path, 'Approved total USD 22,600.')
            artifact = extract_artifact(path)
            self.assertIn('22,600', artifact['text'])
            self.assertEqual(artifact['render_validation'], 'not_performed')

    def test_formula_cache_is_not_treated_as_recalculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cost.xlsx'; xlsx(path, '22600', '500*42+2600')
            artifact = extract_artifact(path)
            self.assertEqual(artifact['formula_cells'][0]['cached_value'], '22600')
            self.assertEqual(artifact['recalculation_validation'], 'not_performed')

    def test_broken_native_file_is_evaluation_setup_evidence(self):
        task = json.loads((DEST / 'solver/original_supplier_landed_cost__baseline.json').read_text())
        m = next(x for x in json.loads((DEST / 'grader/evidence_maps.json').read_text()) if x['instance_id'] == task['instance_id'])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'memo.docx').write_text('Not a Word file')
            packet = prepare_packet(task, m, tmp)
            self.assertFalse(packet['engineering_checks']['native_count_and_types_pass'])
            self.assertEqual(len(packet['engineering_checks']['errors']), 1)


class EvidenceGradeTests(unittest.TestCase):
    def test_critical_failure_cannot_average_away(self):
        s = score_judgment(sample_packet(), sample_judgment())
        self.assertFalse(s['content_acceptable']); self.assertTrue(s['consequential_error'])
        self.assertEqual(s['criteria_passed'], 1); self.assertIsNone(s['human_accepted'])

    def test_fabricated_output_quote_invalidates_judge_not_model(self):
        j = sample_judgment(); j['criteria'][0]['evidence'][0]['output_quote'] = 'Finance approved.'
        s = score_judgment(sample_packet(), j)
        self.assertEqual(s['status'], 'invalid_grader_evidence'); self.assertIsNone(s['consequential_error'])

    def test_fabricated_source_is_rejected(self):
        j = sample_judgment(); j['criteria'][0]['evidence'][0]['source_id'] = 'invented-approval.txt'
        self.assertEqual(score_judgment(sample_packet(), j)['status'], 'invalid_grader_evidence')

    def test_missing_or_duplicate_criteria_do_not_default_to_pass(self):
        for edit in ('missing', 'duplicate'):
            j = sample_judgment()
            if edit == 'missing': j['criteria'].pop()
            else: j['criteria'].append(copy.deepcopy(j['criteria'][0]))
            self.assertEqual(score_judgment(sample_packet(), j)['status'], 'invalid_grader_evidence')

    def test_uncertainty_is_preserved(self):
        j = sample_judgment(); j['criteria'][0]['status'] = 'uncertain'
        s = score_judgment(sample_packet(), j)
        self.assertIsNone(s['content_acceptable']); self.assertIsNone(s['consequential_error'])

    def test_task_defect_blocks_model_error_attribution(self):
        j = sample_judgment(); j['task_defect'] = {'status': 'yes', 'reason': 'Conflicting source authority.'}
        s = score_judgment(sample_packet(), j)
        self.assertEqual(s['status'], 'task_defect_or_uncertainty'); self.assertIsNone(s['consequential_error'])

    def test_absence_requires_all_files_and_no_invented_quote(self):
        j = sample_judgment(); row = j['criteria'][0]; row['evidence_kind'] = 'absence'
        row['evidence'][0]['output_quote'] = ''; row['inspected_artifact_ids'] = []
        self.assertEqual(score_judgment(sample_packet(), j)['status'], 'invalid_grader_evidence')
        row['inspected_artifact_ids'] = ['memo.docx']
        self.assertEqual(score_judgment(sample_packet(), j)['status'], 'automated_assessment_not_human_acceptance')

    def test_passed_content_does_not_claim_package_or_expert_acceptance(self):
        j = sample_judgment()
        for r in j['criteria']: r['status'] = 'pass'
        s = score_judgment(sample_packet(), j)
        self.assertTrue(s['content_acceptable']); self.assertIsNone(s['package_acceptable']); self.assertIsNone(s['human_accepted'])

    def test_malformed_reason_is_a_grader_error(self):
        j = sample_judgment(); j['task_defect']['reason'] = 42
        self.assertEqual(score_judgment(sample_packet(), j)['status'], 'invalid_grader_evidence')

    def test_non_object_and_unhashable_evidence_fail_closed(self):
        self.assertEqual(score_judgment(sample_packet(), [])['status'], 'invalid_grader_evidence')
        j = sample_judgment(); j['criteria'][0]['evidence'][0]['source_id'] = ['bad']
        self.assertEqual(score_judgment(sample_packet(), j)['status'], 'invalid_grader_evidence')

    def test_no_output_is_not_counted_as_a_business_error(self):
        packet = sample_packet(); packet['artifacts'] = []
        j = sample_judgment()
        for r in j['criteria']:
            r.update(status='fail', evidence_kind='absence', inspected_artifact_ids=[])
            r['evidence'][0]['output_quote'] = ''
        s = score_judgment(packet, j)
        self.assertEqual(s['status'], 'no_usable_artifact'); self.assertIsNone(s['consequential_error'])


class ChallengeAndBudgetTests(unittest.TestCase):
    def test_constructed_suite_has_controls_and_no_human_gold(self):
        packets, keys = build()
        self.assertEqual(len(packets), 36); self.assertEqual(len({k['family_id'] for k in keys}), 9)
        self.assertFalse(any(k['human_validated'] for k in keys))
        for p in packets:
            self.assertNotIn('member', p); self.assertNotIn('audit_facts_held_constant', p)
        self.assertEqual(summarize(packets, keys, [])['groups']['mutated']['scored_binary'], 0)

    def test_cosmetic_controls_keep_substantive_content_and_keys_constant(self):
        packets, keys = build(); by_id = {p['id']: p for p in packets}
        for family in {k['family_id'] for k in keys}:
            ks = [k for k in keys if k['family_id'] == family]
            self.assertTrue(all(k['audit_facts_held_constant'] == ks[0]['audit_facts_held_constant'] for k in ks))
            good = by_id[next(k['id'] for k in ks if k['member'] == 'supported')]
            same = by_id[next(k['id'] for k in ks if k['member'] == 'unchanged_control')]
            self.assertEqual(good['artifacts'], same['artifacts'])

    def test_budget_reconciles_all_three_ledgers(self):
        status = budget_status()
        self.assertAlmostEqual(status['charged_or_reserved_usd'], 5.1661575, places=7)
        self.assertAlmostEqual(status['remaining_cap_usd'], 19.8338425, places=7)

    def test_new_stage_counts_historical_probe_and_refuses_excess(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = future_stage_budget(tmp, stage_cap=25)
            # A real provider reservation must include all historical phases.
            self.assertEqual(str(budget.legacy_cost()), '5.1661575')
            budget.rows = [{'charged_or_reserved': 19.8}]
            with self.assertRaises(BudgetStop):
                budget.reserve('must-not-dispatch', {'max_tokens': 9000})
            self.assertFalse((Path(tmp) / 'ledger.json').exists())


if __name__ == '__main__':
    unittest.main()
