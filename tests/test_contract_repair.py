import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_contract_repair import repair, validate


class ContractRepairTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT / 'data/paired_v2_1/solver/change_control__conflict.json').read_text())
        rubrics = json.loads((ROOT / 'data/paired_v2/grader/rubrics.json').read_text())
        self.rubric = next(r for r in rubrics if r['id'] == 'change_control')
        self.task, self.grader = repair(self.source, self.rubric)

    def test_old_two_file_contract_is_rejected(self):
        with self.assertRaises(ValueError): validate(self.source, self.rubric)

    def test_prompt_count_drift_is_rejected(self):
        self.task['deliverable_count'] = 2
        with self.assertRaises(ValueError): validate(self.task, self.grader)

    def test_grader_rejecting_excel_cannot_pass(self):
        self.grader['format'] = 'docx'
        with self.assertRaises(ValueError): validate(self.task, self.grader)

    def test_missing_solver_visible_contract_is_rejected(self):
        self.task['prompt'] = self.source['prompt']
        with self.assertRaises(ValueError): validate(self.task, self.grader)

    def test_repair_preserves_sources_authority_and_parent_objects(self):
        source_before = copy.deepcopy(self.source); rubric_before = copy.deepcopy(self.rubric)
        task, grader = repair(self.source, self.rubric)
        for key in ['attachments', 'workspace', 'fact_keys', 'clarifications', 'variant']:
            self.assertEqual(task[key], self.source[key])
        self.assertEqual(grader['truth'], self.rubric['truth'])
        self.assertEqual(self.source, source_before); self.assertEqual(self.rubric, rubric_before)
        self.assertTrue(validate(task, grader))


if __name__ == '__main__': unittest.main()
