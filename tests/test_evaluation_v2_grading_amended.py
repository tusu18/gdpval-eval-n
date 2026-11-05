from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dispatch_evaluation_v2_grading_amended import select_destination, grade_directory, plan, resolution_index
from run_evaluation_v2 import write, digest


class AmendedGradingDispatchTest(unittest.TestCase):
    def test_zero_request_guard_stop_gets_separate_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = grade_directory("run", "judge/model", folder) / "result.json"
            write(path, {"status": "budget_limited", "calls": [], "batches": [], "unresolved_calls": 0})
            before = digest(path)
            result = select_destination("run", "judge/model", folder)
            self.assertEqual(result["action"], "continue_zero_request_budget_stop")
            self.assertIn("grades_continuations", result["destination"])
            self.assertEqual(digest(path), before)

    def test_invalid_judgment_is_never_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            write(grade_directory("run", "judge/model", folder) / "result.json", {"status": "invalid_judgment", "calls": ["call"]})
            self.assertEqual(select_destination("run", "judge/model", folder)["action"], "preserve_existing")

    def test_ledger_request_blocks_automatic_zero_call_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            original = grade_directory("run", "judge/model", folder)
            write(original / "result.json", {"status": "budget_limited", "calls": [], "batches": []})
            write(Path(folder) / "calls/c1/reservation.json", {"label": "grade:" + original.name + ":batch1"})
            self.assertEqual(select_destination("run", "judge/model", folder)["action"], "checkpoint_review_required")

    def test_non_submitted_original_is_recorded_without_judging(self):
        with tempfile.TemporaryDirectory() as folder:
            write(Path(folder) / "runs/run/result.json", {"task_id": "T", "stage": "primary", "status": "ended_without_submission", "model": "solver"})
            result = plan("judge", root=folder)
            self.assertEqual(result[0]["action"], "record_no_submission")

    def test_filtered_resolution_preserves_previous_cohort_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = {"task_id": "T1", "solver_run_id": "oldrun", "judge_model": "judge", "stage": "primary", "human_acceptance": None}
            write(Path(folder) / "grade-resolution-index.json", {"entries": [prior]})
            write(Path(folder) / "runs/newrun/result.json", {"task_id": "T2", "stage": "primary", "status": "ended_without_submission", "model": "solver"})
            rows = plan("judge", root=folder)
            index = resolution_index(rows, root=folder)
            self.assertEqual({e["task_id"] for e in index["entries"]}, {"T1", "T2"})


if __name__ == "__main__":
    unittest.main()
