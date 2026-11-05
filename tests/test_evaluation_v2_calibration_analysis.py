import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_evaluation_v2_calibration import analyze_rows, comparison_cell, summarize_cases
from evaluation_v2_grading import build_packet


class CriterionDiagnosticsTest(unittest.TestCase):
    def fixture(self):
        packet = build_packet({"prompt": "Approval required"}, [],
            [{"id": "A", "text": "Approval required", "full_text_available": True}],
            [{"id": "business", "criterion": "Apply approval"}, {"id": "layout", "criterion": "Readable layout"}], source_coverage_confirmed=True)
        row = {"id": "business", "status": "pass", "severity": "none", "rationale": "Present", "rule_stated": "yes", "rule_honored": "yes",
               "operative_sections_inspected": ["section1"], "coverage_status": "complete", "coverage_limitations": "none",
               "evidence_kind": "quoted", "evidence": [{"source_id": "original_request", "source_quote": "Approval required", "artifact_id": "A", "output_quote": "Approval required"}]}
        second = copy.deepcopy(row); second.update(id="layout", coverage_status="partial", coverage_limitations="No page images")
        judgment = {"task_defect": {"status": "no", "reason": "Clear"}, "criteria": [row, second]}
        return packet, judgment

    def test_partial_visual_pass_remains_globally_invalid(self):
        packet, judgment = self.fixture(); original = copy.deepcopy(judgment)
        result = analyze_rows(packet, judgment)
        self.assertFalse(result["whole_response_valid"])
        self.assertTrue(result["criteria"][0]["row_valid"])
        self.assertFalse(result["criteria"][1]["row_valid"])
        self.assertEqual(judgment, original)

    def test_duplicate_target_is_not_salvaged(self):
        packet, judgment = self.fixture(); judgment["criteria"].append(copy.deepcopy(judgment["criteria"][0]))
        self.assertFalse(analyze_rows(packet, judgment)["criteria"][0]["row_valid"])

    def test_uncertain_business_row_is_outside_binary_matrix(self):
        packet, judgment = self.fixture(); judgment["criteria"][0].update(status="uncertain", severity="uncertain")
        target = analyze_rows(packet, judgment)["criteria"][0]
        self.assertTrue(target["row_valid"])
        self.assertFalse(target["binary_eligible"])
        self.assertIsNone(comparison_cell(target["judge_consequential_flag"], "yes"))

    def test_confusion_cells_keep_positive_error_semantics(self):
        self.assertEqual(comparison_cell(True, "yes"), "TP")
        self.assertEqual(comparison_cell(True, "no"), "FP")
        self.assertEqual(comparison_cell(False, "yes"), "FN")
        self.assertEqual(comparison_cell(False, "no"), "TN")

    def test_incomplete_packet_cannot_supply_a_binary_negative(self):
        packet, judgment = self.fixture(); packet["coverage"]["full_sources"] = False
        target = analyze_rows(packet, judgment)["criteria"][0]
        self.assertTrue(target["row_valid"])
        self.assertFalse(target["binary_eligible"])
        self.assertIsNone(target["judge_consequential_flag"])


if __name__ == "__main__":
    unittest.main()
