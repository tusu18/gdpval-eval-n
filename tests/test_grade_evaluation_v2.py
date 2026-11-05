"""Integration invariants: no live network calls or credentials."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import grade_evaluation_v2 as runner
import evaluation_v2_grading as grading


class GradeOrchestrationTest(unittest.TestCase):
    def packet(self):
        return grading.build_packet({"task_id": "t", "prompt": "Original"}, [],
            [{"id": "A01.docx", "text": "Document", "full_text_available": True}],
            [{"id": "R1", "criterion": "Original criterion"}],
            {"observations": [{"id": f"v{i}", "artifact_id": "A01.docx", "image_supplied": False} for i in range(18)]},
            source_coverage_confirmed=True)

    def test_all_images_scheduled_without_claiming_batch_full_coverage(self):
        images = [{"id": f"v{i}", "available": True} for i in range(18)]
        batches = runner.image_batches(self.packet(), images)
        self.assertEqual([len(g) for _, g in batches], [16, 2])
        supplied = {x["id"] for _, group in batches for x in group}
        self.assertEqual(supplied, {f"v{i}" for i in range(18)})
        self.assertTrue(all(not p["inspection"]["visual_coverage"]["all_output_views_supplied_in_this_call"] for p, _ in batches))

    def test_missing_image_remains_visible(self):
        batches = runner.image_batches(self.packet(), [{"id": "v0", "available": False}])
        self.assertEqual(batches[0][0]["inspection"]["visual_coverage"]["missing_views"], ["v0"])

    def test_invalid_batch_cannot_be_aggregated_into_pass(self):
        summary = runner.combine_summaries([
            {"status": "automated_assessment_not_human_acceptance", "project_rubric_pass": True, "consequential_error_candidate": False},
            {"status": "invalid_judgment", "project_rubric_pass": None, "consequential_error_candidate": None}], 2)
        self.assertIsNone(summary["project_rubric_pass"])
        self.assertIsNone(summary["consequential_error_candidate"])

    def test_preparation_does_not_call_a_client(self):
        class NoCall:
            def call(self, *args, **kwargs):
                raise AssertionError("Preparation dispatched a paid call")
        with tempfile.TemporaryDirectory() as folder:
            result = runner.grade_packet(NoCall(), self.packet(), [], folder, "judge", identity={"task_id": "t"}, scope="test", execute=False)
            self.assertEqual(result["status"], "prepared_not_executed")
            self.assertTrue((Path(folder) / "packet-01.json").exists())
            self.assertFalse((Path(folder) / "result.json").exists())

    def test_interrupted_call_is_not_automatically_reissued(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "in_progress.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "interrupted"):
                runner.grade_packet(None, self.packet(), [], folder, "judge", identity={}, scope="test", execute=False)


if __name__ == "__main__":
    unittest.main()
