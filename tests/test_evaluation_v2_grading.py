import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("evaluation_v2_grading", Path(__file__).resolve().parents[1] / "scripts/evaluation_v2_grading.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GraderEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.packet = g.build_packet(
            {"task_id": "t", "prompt": "Require Finance approval before release."}, [],
            [{"id": "memo.docx", "text": "Finance approval is required. Release before approval.", "full_text_available": True,
              "units": [{"locator": "p1", "text": "Finance approval is required."}, {"locator": "p2", "text": "Release before approval."}]}],
            [{"id": "R1", "criterion": "All release instructions require approval.", "consequential": True}],
            source_coverage_confirmed=True)
        self.judgment = {"task_defect": {"status": "no", "reason": "Source rule explicit."}, "criteria": [{
            "id": "R1", "status": "fail", "rationale": "Release instruction bypasses the rule.", "evidence_kind": "quoted",
            "evidence": [{"source_id": "original_request", "source_quote": "Require Finance approval before release.", "artifact_id": "memo.docx", "output_quote": "Release before approval."}],
            "inspected_artifact_ids": ["memo.docx"], "inspection_ids": [], "assumptions": "none", "counterevidence": "Earlier paragraph states the rule.", "consequence": "Unauthorized release risk.", "minimum_correction": "Gate release on approval.", "rule_stated": "yes", "rule_honored": "no", "operative_sections_inspected": ["p1", "p2"], "severity": "consequential", "coverage_status": "complete", "coverage_limitations": "none"}]}

    def test_failure_is_candidate_not_human_acceptance(self):
        result = g.summarize_judgment(self.packet, self.judgment)
        self.assertTrue(result["consequential_error_candidate"])
        self.assertFalse(result["project_rubric_pass"])
        self.assertIsNone(result["human_accepted"])

    def test_matching_prefix_does_not_validate_fabricated_remainder(self):
        self.judgment["criteria"][0]["evidence"][0]["output_quote"] = "Release before approval. Finance already signed."
        self.assertIn("R1:unverifiable_output_quote", g.validate_judgment(self.packet, self.judgment))

    def test_locator_is_not_quoted_artifact_text(self):
        self.judgment["criteria"][0]["evidence"][0]["output_quote"] = "p2"
        self.assertIn("R1:unverifiable_output_quote", g.validate_judgment(self.packet, self.judgment))

    def test_duplicate_criteria_cannot_imply_coverage(self):
        self.judgment["criteria"].append(copy.deepcopy(self.judgment["criteria"][0]))
        self.assertIn("missing_duplicate_or_unknown_criteria", g.validate_judgment(self.packet, self.judgment))

    def test_incomplete_source_pass_stays_unknown(self):
        self.packet["coverage"]["full_sources"] = False
        self.judgment["criteria"][0]["status"] = "pass"
        self.judgment["criteria"][0]["severity"] = "none"
        self.judgment["criteria"][0]["rule_honored"] = "yes"
        result = g.summarize_judgment(self.packet, self.judgment)
        self.assertIsNone(result["project_rubric_pass"])
        self.assertIsNone(result["consequential_error_candidate"])

    def test_absence_requires_complete_artifact_inspection(self):
        row = self.judgment["criteria"][0]
        row.update(evidence_kind="absence", inspected_artifact_ids=[])
        row["evidence"][0]["output_quote"] = ""
        self.assertIn("R1:incomplete_absence_check", g.validate_judgment(self.packet, self.judgment))

    def test_filename_without_supplied_image_cannot_validate_visual_claim(self):
        row = self.judgment["criteria"][0]
        row.update(evidence_kind="visual", inspection_ids=["page1"])
        row["evidence"][0]["output_quote"] = ""
        self.packet["inspection"]["observations"] = [{"id": "page1", "artifact_id": "memo.docx", "image_supplied": False}]
        self.assertIn("R1:unverifiable_visual_observation", g.validate_judgment(self.packet, self.judgment))

    def test_strict_parser_rejects_explanatory_prefix(self):
        with self.assertRaises(ValueError):
            g.parse_judgment('Here is the answer: {"criteria": []}')

    def test_minor_failure_does_not_become_consequential_from_criterion_flag(self):
        self.judgment["criteria"][0]["severity"] = "minor"
        result = g.summarize_judgment(self.packet, self.judgment)
        self.assertFalse(result["project_rubric_pass"])
        self.assertFalse(result["consequential_error_candidate"])

    def test_correct_quote_without_operative_coverage_is_invalid(self):
        self.judgment["criteria"][0]["operative_sections_inspected"] = []
        self.assertIn("R1:missing_operative_coverage", g.validate_judgment(self.packet, self.judgment))

    def test_rule_honoring_cannot_be_no_on_a_pass(self):
        self.judgment["criteria"][0].update(status="pass", severity="none")
        self.assertIn("R1:pass_conflicts_with_coverage_or_honoring", g.validate_judgment(self.packet, self.judgment))

    def test_packet_strips_author_metadata(self):
        packet = g.build_packet({"prompt": "Original", "model": "secret"}, [], [{"id": "a", "text": "t", "model": "secret", "human_label": "yes"}], [{"id": "r", "criterion": "Read"}])
        self.assertNotIn("model", packet)
        self.assertNotIn("human_label", packet["artifacts"][0])


if __name__ == "__main__":
    unittest.main()
