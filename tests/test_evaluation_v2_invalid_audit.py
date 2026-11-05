from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_evaluation_v2_invalid_judgments import normalize_shape, quote_diagnostics, visual_relation, remove_known_locator_wrappers


class InvalidAuditTests(unittest.TestCase):
    def test_singleton_wrapper_preserves_every_character_and_original(self):
        text = "  Section 2;\nCells B3:B8 — inspected.  "
        original = {"criteria": [{"id": "R1", "status": "pass", "operative_sections_inspected": text, "coverage_status": "partial"}]}
        normalized, edits = normalize_shape(original)
        self.assertEqual(original["criteria"][0]["operative_sections_inspected"], text)
        self.assertEqual(normalized["criteria"][0]["operative_sections_inspected"], [text])
        self.assertEqual(normalized["criteria"][0]["coverage_status"], "partial")
        self.assertEqual(edits[0]["original_text_verbatim"], text)

    def test_missing_or_empty_coverage_is_not_invented(self):
        original = {"criteria": [{"id": "R1"}, {"id": "R2", "operative_sections_inspected": "  "}, {"id": "R3", "operative_sections_inspected": []}]}
        normalized, edits = normalize_shape(original)
        self.assertEqual(normalized, original)
        self.assertEqual(edits, [])

    def test_quote_whitespace_diagnostic_never_changes_quote(self):
        packet = {"source_documents": [{"id": "S1", "text": "A\nB"}], "artifacts": []}
        row = {"evidence": [{"source_id": "S1", "source_quote": "A B"}]}
        detail = quote_diagnostics(packet, row, "source_quote")[0]
        self.assertEqual(detail["classification"], "whitespace_only_difference_candidate_not_repaired")
        self.assertFalse(detail["automatic_quote_repair_applied"])
        self.assertEqual(row["evidence"][0]["source_quote"], "A B")

    def test_visual_list_can_span_multiple_actual_evidence_artifacts(self):
        packet = {"artifacts": [{"id": "A"}, {"id": "B"}], "inspection": {"observations": [{"id": "V1", "artifact_id": "A", "image_supplied": True}, {"id": "V2", "artifact_id": "B", "image_supplied": True}]}}
        row = {"inspection_ids": ["V1", "V2"], "evidence": [{"artifact_id": "A"}, {"artifact_id": "B"}]}
        self.assertTrue(visual_relation(packet, row)["valid"])
        packet["inspection"]["observations"][1]["image_supplied"] = False
        self.assertFalse(visual_relation(packet, row)["valid"])
        row["inspection_ids"] = ["V1"]
        self.assertFalse(visual_relation(packet, row)["valid"])
        row["inspection_ids"] = ["unknown"]
        self.assertFalse(visual_relation(packet, row)["valid"])

    def test_locator_repair_preserves_all_contiguous_content(self):
        units = [{"locator": "cell:A1", "text": "Rate"}, {"locator": "cell:A2", "text": "10%"}, {"locator": "cell:A3", "text": "Required"}]
        item = {"units": units, "text": "\n".join(u["locator"] + "\t" + u["text"] for u in units)}
        quote = "Rate\ncell:A2\t10%\ncell:A3\tRequired"
        repair = remove_known_locator_wrappers(item, quote)
        self.assertEqual(repair["normalized_quote_verbatim"], "Rate\n10%\nRequired")
        self.assertTrue(repair["whole_quote_continuity_verified"])
        self.assertEqual("".join(s["content_verbatim"] for s in repair["preserved_content_segments"]), repair["normalized_quote_verbatim"])
        self.assertIsNone(remove_known_locator_wrappers(item, quote.replace("10%", "12%")))
        self.assertIsNone(remove_known_locator_wrappers(item, "Rate\ncell:A3\tRequired"))
        self.assertIsNone(remove_known_locator_wrappers(item, quote + " invented tail"))
        self.assertIsNone(remove_known_locator_wrappers(item, "A2\t10%"))


if __name__ == "__main__":
    unittest.main()
