from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from grade_evaluation_v2_cross_family import candidate, BoundedSecondaryClient
from run_evaluation_v2 import write, BudgetStop


class CrossFamilySelectionTests(unittest.TestCase):
    def test_primary_wins_over_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "runs"
            write(base / "T__openai_sol__primary/result.json", {"status": "submitted"})
            write(base / "T__openai_sol__recovery/result.json", {"task_id": "T", "model": "openai/sol", "status": "submitted", "recovery_stage": "recovery"})
            self.assertEqual(candidate("T", "openai/sol", root).parent.name, "T__openai_sol__primary")

    def test_gemini_failed_first_pass_is_not_replaced_by_repeat(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "runs"
            write(base / "T__google_gemini__supplemental/result.json", {"status": "infrastructure_failure"})
            write(base / "T__google_gemini__supplemental_r2/result.json", {"status": "submitted"})
            self.assertIsNone(candidate("T", "google/gemini", root))

    def test_first_completed_recovery_including_explicit_adapter(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "runs"
            for stage, date in [("adapter_repair", "2026-11-05T02:00Z"), ("recovery", "2026-11-05T03:00Z")]:
                write(base / ("T__openai_sol__" + stage) / "result.json", {"task_id": "T", "model": "openai/sol", "status": "submitted", "stage": stage, "recovery_stage": "recovery" if stage == "recovery" else None, "completed_at": date})
            self.assertEqual(candidate("T", "openai/sol", root).parent.name, "T__openai_sol__adapter_repair")

    def test_phase_cap_blocks_before_underlying_call(self):
        with tempfile.TemporaryDirectory() as root:
            class Fake:
                cfg = {}
                models = {"judge": {"pricing": {"prompt": 0.000001, "completion": 0.000001}}}
                def reservation(self, body): return 4
                def call(self, *args, **kwargs): raise AssertionError("Must not dispatch")
            fake = Fake(); fake.root = Path(root)
            client = BoundedSecondaryClient(fake, {"budget": {"maximum_new_api_requests": 16, "per_phase_maximum_additional_commitment_usd": 3}})
            with self.assertRaises(BudgetStop): client.call({"model": "judge"})


if __name__ == "__main__":
    unittest.main()
