import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit import overlap, summarize
from prepare_gdpval import solver_record, SOLVER_FIELDS
from synthetic_demo import generate, solve, validate_answer


class PreparationChecks(unittest.TestCase):
    def test_solver_does_not_receive_gold(self):
        r = dict(task_id="a", occupation="o", sector="s", prompt="p", reference_files=["reference_files/x/input.xlsx"], rubric_json="SECRET RUBRIC", deliverable_files=["SECRET GOLD"])
        safe = solver_record(r, "abc")
        self.assertEqual(set(safe), SOLVER_FIELDS)
        self.assertNotIn("SECRET", str(safe))
        self.assertIn("/abc/", safe["reference_urls"][0])

    def test_rejects_traversal(self):
        with self.assertRaises(ValueError):
            solver_record({"reference_files": ["reference_files/../../gold.xlsx"]}, "abc")

    def test_lineage_catches_paraphrase(self):
        a = {"task_id": "a", "prompt": "Calculate net stock", "seed_family_id": "family"}
        b = {"task_id": "b", "prompt": "How much inventory remains?", "seed_family_id": "family"}
        self.assertIn("seed_family_id_shared", overlap([a], [b])[0]["reasons"])

    def test_normalized_duplicates(self):
        a = {"task_id": "a", "prompt": "Total, please!"}
        b = {"task_id": "b", "prompt": "TOTAL PLEASE"}
        self.assertIn("exact_normalized_prompt", overlap([a], [b])[0]["reasons"])

    def test_mutation_rejected(self):
        r = generate("price_with_fixed_fee", 100)
        good = r["answer"]
        self.assertTrue(validate_answer(r["state"], good))
        bad = dict(good, winner="nonexistent")
        self.assertFalse(validate_answer(r["state"], bad))

    def test_ineligible_cheapest_and_tie(self):
        s = {"demand": 10, "deadline": 5, "mandatory_certification": True, "suppliers": [
            {"supplier": "A", "capacity": 100, "lead_days": 1, "certified": False, "unit_price_cents": 1, "fixed_fee_cents": 0},
            {"supplier": "C", "capacity": 10, "lead_days": 5, "certified": True, "unit_price_cents": 2, "fixed_fee_cents": 5},
            {"supplier": "B", "capacity": 10, "lead_days": 5, "certified": True, "unit_price_cents": 2, "fixed_fee_cents": 5}]}
        self.assertEqual(solve(s)["winner"], "B")
        self.assertEqual(solve(s)["total_cost_cents"], 25)
        self.assertTrue(validate_answer(s, solve(s)))

    def test_none_eligible(self):
        r = generate("certification_required", 100)
        r["state"]["demand"] = 100000
        self.assertIsNone(solve(r["state"])["winner"])

    def test_failed_task_stays_in_denominator(self):
        rows = [{"task_id": "a", "usable": True, "critical_error": False, "cost_usd": 1}, {"task_id": "b", "usable": False, "critical_error": False, "cost_usd": 2}]
        self.assertEqual(summarize(rows)["usable_rate"], .5)
        self.assertEqual(summarize(rows)["cost_per_usable_usd"], 3)

    def test_duplicate_and_nan_rejected(self):
        r = {"task_id": "a", "usable": False, "critical_error": False, "cost_usd": 1}
        with self.assertRaises(ValueError): summarize([r, r])
        with self.assertRaises(ValueError): summarize([dict(r, cost_usd=float("nan"))])


if __name__ == "__main__":
    unittest.main()
