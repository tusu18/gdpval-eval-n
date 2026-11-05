from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_evaluation_v2_recovery_pilot import recovery_candidates
from run_evaluation_v2 import write


class RecoveryPilotBindingTests(unittest.TestCase):
    def test_first_submitted_attempt_is_selected_without_quality_or_grade(self):
        with tempfile.TemporaryDirectory() as root:
            for suffix, status in [("", "failed"), ("2", "failed"), ("3", "submitted"), ("4", "submitted"), ("3_extra", "submitted")]:
                write(Path(root) / "runs" / ("T__solver_model__recovery" + suffix) / "result.json",
                      {"task_id": "T", "model": "solver/model", "status": status, "recovery_stage": "recovery"})
            rows = recovery_candidates({"task_id": "T"}, {"solver_model": "solver/model"}, root)
            self.assertEqual([p.name for p in rows], ["T__solver_model__recovery3", "T__solver_model__recovery4"])

    def test_different_task_or_non_recovery_is_ineligible(self):
        with tempfile.TemporaryDirectory() as root:
            write(Path(root) / "runs/T__solver_model__recovery/result.json", {"task_id": "other", "model": "solver/model", "status": "submitted", "recovery_stage": "recovery"})
            write(Path(root) / "runs/T__solver_model__recovery2/result.json", {"task_id": "T", "model": "solver/model", "status": "submitted", "stage": "primary"})
            self.assertEqual(recovery_candidates({"task_id": "T"}, {"solver_model": "solver/model"}, root), [])


if __name__ == "__main__":
    unittest.main()
