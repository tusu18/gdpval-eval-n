"""Offline numerical and cluster-dependence checks for paired judge metrics."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluation_v5_pair_metrics import paired_agreement, summarize_pairs


def task(identity, left, right, criteria=None):
    pairs = criteria if criteria is not None else [(left, right)]
    return {"task_id": identity, "left_overall": left, "right_overall": right,
            "criteria": [{"criterion_id": f"R{i}", "left": a, "right": b} for i, (a, b) in enumerate(pairs)]}


class PairMetricsTests(unittest.TestCase):
    def test_known_binary_kappa_and_positive_agreement(self):
        # Matrix [[20 both pass,10 disagreement],[10 disagreement,60 both fail]].
        result = summarize_pairs([("pass", "pass")] * 20 + [("pass", "fail")] * 10 + [("fail", "pass")] * 10 + [("fail", "fail")] * 60)
        self.assertEqual(result["matched_pairs"], 100)
        self.assertAlmostEqual(result["raw_agreement"], .8)
        self.assertAlmostEqual(result["chance_expected_agreement"], .58)
        self.assertAlmostEqual(result["cohens_kappa"], 11 / 21)
        self.assertAlmostEqual(result["fail_positive_agreement"], 6 / 7)

    def test_uncertainty_is_not_a_pass_and_excluded_from_binary(self):
        result = summarize_pairs([("fail", "fail"), ("fail", "pass"), ("pass", "fail"), ("uncertain", "fail"), ("uncertain", "uncertain")])
        self.assertEqual(result["matrix"]["uncertain"]["fail"], 1)
        self.assertEqual(result["uncertain_or_not_assessed_pairs_excluded_from_binary"], 2)
        self.assertEqual(result["decided_binary_pairs"], 3)
        self.assertEqual(result["fail_positive_agreement"], .5)
        self.assertEqual(result["raw_agreement"], .4)

    def test_empty_and_constant_labels_keep_undefined_metrics_null(self):
        empty = paired_agreement([])
        self.assertIsNone(empty["task_overall"]["raw_agreement"])
        constant = paired_agreement([task(str(i), "pass", "pass") for i in range(10)], bootstrap_samples=200)
        self.assertIsNone(constant["task_overall"]["cohens_kappa"])
        self.assertIsNone(constant["task_overall"]["fail_positive_agreement"])
        self.assertEqual(constant["intervals"]["task_raw_agreement"]["ci95"], [1.0, 1.0])
        self.assertEqual(constant["intervals"]["task_raw_agreement"]["ci_status"], "degenerate_empirical_interval")
        self.assertIsNone(constant["intervals"]["task_cohens_kappa"]["ci95"])

    def test_small_sample_retains_points_but_suppresses_default_intervals(self):
        result = paired_agreement([task("a", "pass", "pass"), task("b", "fail", "pass")])
        self.assertEqual(result["task_overall"]["raw_agreement"], .5)
        self.assertIsNone(result["intervals"]["task_raw_agreement"]["ci95"])
        self.assertEqual(result["intervals"]["task_raw_agreement"]["ci_status"], "too_few_matched_tasks")

    def test_whole_task_bootstrap_preserves_large_within_task_correlation(self):
        # One task has one agreement; the other has nine disagreements. A proper
        # two-task bootstrap can yield all-good or all-bad samples, unlike a
        # criterion-level bootstrap that would falsely narrow this interval.
        tasks = [task("good", "pass", "pass", [("pass", "pass")]),
                 task("bad", "fail", "pass", [("fail", "pass")] * 9)]
        result = paired_agreement(tasks, min_tasks_for_ci=2, bootstrap_samples=2000)
        self.assertEqual(result["criterion_micro_agreement"], .1)
        self.assertEqual(result["criterion_macro_task_agreement"], .5)
        self.assertEqual(result["intervals"]["criterion_raw_agreement"]["ci95"], [0.0, 1.0])
        self.assertEqual(result, paired_agreement(tasks, min_tasks_for_ci=2, bootstrap_samples=2000))

    def test_many_criteria_do_not_replace_number_of_independent_tasks(self):
        tasks = [task(str(i), "pass", "pass", [("pass", "pass")] * 100) for i in range(3)]
        result = paired_agreement(tasks)
        self.assertEqual(result["matched_criterion_count"], 300)
        self.assertEqual(result["task_count"], 3)
        self.assertIsNone(result["intervals"]["criterion_raw_agreement"]["ci95"])

    def test_rare_fail_bootstrap_undefined_denominators_are_visible(self):
        tasks = [task("fail", "fail", "fail")] + [task(str(i), "pass", "pass") for i in range(9)]
        result = paired_agreement(tasks)
        interval = result["intervals"]["task_fail_positive_agreement"]
        self.assertEqual(interval["estimate"], 1.0)
        self.assertGreater(interval["undefined_bootstrap_replicates"], 500)
        self.assertIsNone(interval["ci95"])
        self.assertEqual(interval["ci_status"], "insufficient_defined_bootstrap_replicates")

    def test_invalid_or_duplicate_inputs_cannot_be_silently_counted(self):
        with self.assertRaises(ValueError):
            paired_agreement([task("same", "pass", "pass"), task("same", "fail", "fail")])
        with self.assertRaises(ValueError):
            paired_agreement([task("a", None, "pass")])
        with self.assertRaises(ValueError):
            summarize_pairs([("invalid_judgment", "pass")])


if __name__ == "__main__":
    unittest.main()
