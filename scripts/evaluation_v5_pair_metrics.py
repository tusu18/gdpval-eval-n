"""Pure paired-judge agreement diagnostics with whole-task bootstrap intervals.

No file access, inference, human labels, or accuracy claims. Supply only genuinely
matched assessments of the same task/output/criterion semantics. Missing or
invalid judgments must remain outside the matched input, with their exclusions
reported by the caller. Uncertain verdicts are retained as a distinct class.

Input example:
    [{"task_id": "t1", "left_overall": "pass", "right_overall": "uncertain",
      "criteria": [{"criterion_id": "R1", "left": "pass", "right": "pass"}]}]

All criteria from a selected task move together in each bootstrap draw. The
criterion micro-average gives each criterion equal weight; the macro-average
gives each task with at least one matched criterion equal weight. Neither is an
acceptance rate. Intervals describe this exploratory matched sample, not a
representative population. Shared-source/task-family dependence remains possible.
"""
from __future__ import annotations

import math
import random
from collections import Counter

TASK_LABELS = ("pass", "fail", "uncertain")
CRITERION_LABELS = ("pass", "fail", "uncertain", "not_assessed")
DEFAULT_SEED = 20261105


def _safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize_pairs(pairs, labels=TASK_LABELS):
    """Agreement counts, multiclass kappa, and fail agreement among decided pairs.

    Positive agreement =2*both_fail/(2*both_fail+left_only_fail+right_only_fail).
    Its binary subset includes only pairs for which both verdicts are pass/fail;
    uncertainty and not_assessed are explicitly excluded, never treated as passes.
    """
    labels = tuple(labels)
    if not labels or len(labels) != len(set(labels)) or not {"pass", "fail"}.issubset(labels):
        raise ValueError("Unique labels must include pass and fail")
    matrix = {left: {right: 0 for right in labels} for left in labels}
    count = 0
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("Each pair must contain exactly two verdicts")
        left, right = pair
        if left not in labels or right not in labels:
            raise ValueError("Unrecognized verdict; missing values cannot become passes")
        matrix[left][right] += 1
        count += 1
    left_margins = {label: sum(matrix[label].values()) for label in labels}
    right_margins = {label: sum(matrix[left][label] for left in labels) for label in labels}
    agreements = sum(matrix[label][label] for label in labels)
    raw = _safe_ratio(agreements, count)
    expected = _safe_ratio(sum(left_margins[label] * right_margins[label] for label in labels), count * count)
    if not count:
        kappa, kappa_reason = None, "no_matched_pairs"
    elif expected == 1:
        kappa, kappa_reason = None, "chance_agreement_is_one_constant_same_class"
    else:
        kappa, kappa_reason = (raw - expected) / (1 - expected), None
    both_fail, left_only_fail = matrix["fail"]["fail"], matrix["fail"]["pass"]
    right_only_fail, both_pass = matrix["pass"]["fail"], matrix["pass"]["pass"]
    decided = both_fail + left_only_fail + right_only_fail + both_pass
    fail_denominator = 2 * both_fail + left_only_fail + right_only_fail
    excluded_cells = [{"left": left, "right": right, "count": matrix[left][right]}
                      for left in labels for right in labels
                      if (left not in ("pass", "fail") or right not in ("pass", "fail")) and matrix[left][right]]
    return {
        "labels": list(labels), "matched_pairs": count, "matrix": matrix,
        "matrix_orientation": "rows=left judge; columns=right judge",
        "left_margins": left_margins, "right_margins": right_margins,
        "agreement_count": agreements, "disagreement_count": count - agreements,
        "raw_agreement": raw, "chance_expected_agreement": expected,
        "cohens_kappa": kappa, "kappa_undefined_reason": kappa_reason,
        "fail_positive_agreement": _safe_ratio(2 * both_fail, fail_denominator),
        "fail_positive_agreement_denominator": fail_denominator,
        "fail_positive_agreement_undefined_reason": "no_fail_in_decided_pairs" if not fail_denominator else None,
        "decided_binary_pairs": decided,
        "decided_binary_matrix": {"both_fail": both_fail, "left_fail_right_pass": left_only_fail,
                                  "left_pass_right_fail": right_only_fail, "both_pass": both_pass},
        "uncertain_or_not_assessed_pairs_excluded_from_binary": count - decided,
        "binary_exclusion_cells": excluded_cells,
        "positive_agreement_interpretation": "Agreement on a fail verdict among jointly decided pass/fail pairs; not sensitivity, accuracy, or human-confirmed error detection.",
    }


def _normalize_tasks(tasks):
    if not isinstance(tasks, (list, tuple)):
        raise ValueError("tasks must be a sequence")
    result, identifiers = [], set()
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str) or not task["task_id"]:
            raise ValueError("Every task needs a nonempty task_id")
        if task["task_id"] in identifiers:
            raise ValueError("Duplicate task IDs would violate whole-task independence accounting")
        identifiers.add(task["task_id"])
        left, right = task.get("left_overall"), task.get("right_overall")
        if left not in TASK_LABELS or right not in TASK_LABELS:
            raise ValueError("Task overalls must explicitly be pass, fail, or uncertain")
        criteria = task.get("criteria", [])
        if not isinstance(criteria, (list, tuple)):
            raise ValueError("criteria must be a sequence")
        pairs, criterion_ids = [], set()
        for criterion in criteria:
            if not isinstance(criterion, dict):
                raise ValueError("Each matched criterion must be an object")
            cid = criterion.get("criterion_id")
            if not isinstance(cid, str) or not cid or cid in criterion_ids:
                raise ValueError("Criterion IDs must be nonempty and unique within a task")
            criterion_ids.add(cid)
            pair = (criterion.get("left"), criterion.get("right"))
            if any(label not in CRITERION_LABELS for label in pair):
                raise ValueError("Criterion verdicts must be explicit recognized labels")
            pairs.append(pair)
        result.append({"task_id": task["task_id"], "overall": (left, right), "criteria": pairs})
    return result


def _quantile(values, probability):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _point_stats(tasks):
    overall = summarize_pairs([task["overall"] for task in tasks], TASK_LABELS)
    criteria = summarize_pairs([pair for task in tasks for pair in task["criteria"]], CRITERION_LABELS)
    task_criterion_means = [sum(left == right for left, right in task["criteria"]) / len(task["criteria"])
                            for task in tasks if task["criteria"]]
    macro = sum(task_criterion_means) / len(task_criterion_means) if task_criterion_means else None
    return overall, criteria, macro


def _interval(estimate, values, requested, generated, task_count, min_tasks, minimum_defined_fraction):
    defined = [v for v in values if v is not None and math.isfinite(v)]
    result = {"estimate": estimate, "ci95": None, "interval_method": "percentile bootstrap, whole tasks sampled with replacement",
              "bootstrap_replicates_requested": requested, "bootstrap_replicates_generated": generated,
              "defined_bootstrap_replicates": len(defined), "undefined_bootstrap_replicates": generated - len(defined),
              "minimum_defined_fraction_required": minimum_defined_fraction, "empirical_distribution_degenerate": None,
              "conditional_on_defined_replicates": generated > len(defined)}
    if estimate is None:
        result["ci_status"] = "undefined_point_estimate"
    elif task_count < min_tasks:
        result["ci_status"] = "too_few_matched_tasks"
    elif not generated:
        result["ci_status"] = "bootstrap_not_requested"
    elif len(defined) < math.ceil(minimum_defined_fraction * generated):
        result["ci_status"] = "insufficient_defined_bootstrap_replicates"
    elif not defined:
        result["ci_status"] = "no_defined_bootstrap_replicates"
    else:
        degenerate = min(defined) == max(defined)
        result.update(ci95=[_quantile(defined, .025), _quantile(defined, .975)],
                      empirical_distribution_degenerate=degenerate,
                      ci_status="degenerate_empirical_interval" if degenerate else "estimated")
    if result["ci_status"] == "degenerate_empirical_interval":
        result["warning"] = "No variation appeared in this empirical resampling distribution; identical endpoints do not establish certainty or population-wide agreement."
    return result


def paired_agreement(tasks, bootstrap_samples=2000, seed=DEFAULT_SEED, min_tasks_for_ci=10, minimum_defined_fraction=.8):
    """Compute paired task/criterion agreement with correctly clustered intervals.

    No case-level bootstrap is used. Criteria remain attached to their complete
    task throughout resampling, including tasks with different criterion counts.
    At least10 matched tasks are required for default intervals; smaller samples
    retain descriptive counts/point estimates. Undefined chance correction and
    zero-positive denominators remain null rather than fabricated zeros.
    """
    if type(bootstrap_samples) is not int or bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be a nonnegative integer")
    if type(seed) is not int or type(min_tasks_for_ci) is not int or min_tasks_for_ci < 2:
        raise ValueError("seed must be an integer; min_tasks_for_ci must be at least2")
    if not isinstance(minimum_defined_fraction, (int, float)) or not 0 < minimum_defined_fraction <= 1:
        raise ValueError("minimum_defined_fraction must be in(0,1]")
    normalized = _normalize_tasks(tasks)
    overall, criteria, macro = _point_stats(normalized)
    paths = ("task_raw_agreement", "task_cohens_kappa", "task_fail_positive_agreement",
             "criterion_raw_agreement", "criterion_cohens_kappa", "criterion_fail_positive_agreement", "criterion_macro_task_agreement")
    points = dict(zip(paths, (overall["raw_agreement"], overall["cohens_kappa"], overall["fail_positive_agreement"],
                             criteria["raw_agreement"], criteria["cohens_kappa"], criteria["fail_positive_agreement"], macro)))
    values = {key: [] for key in paths}
    generated = 0
    if len(normalized) >= min_tasks_for_ci:
        random_generator = random.Random(seed)
        for _ in range(bootstrap_samples):
            # A single index selects a task's overall and every matched criterion.
            sample = [normalized[random_generator.randrange(len(normalized))] for _ in normalized]
            so, sc, sm = _point_stats(sample)
            metrics = (so["raw_agreement"], so["cohens_kappa"], so["fail_positive_agreement"],
                       sc["raw_agreement"], sc["cohens_kappa"], sc["fail_positive_agreement"], sm)
            for key, value in zip(paths, metrics):
                values[key].append(value)
            generated += 1
    intervals = {key: _interval(value, values[key], bootstrap_samples, generated, len(normalized), min_tasks_for_ci, minimum_defined_fraction)
                 for key, value in points.items()}
    return {
        "schema": "evaluation-v5-paired-judge-agreement-1", "task_count": len(normalized),
        "matched_criterion_count": criteria["matched_pairs"],
        "tasks_with_matched_criteria": sum(bool(t["criteria"]) for t in normalized),
        "task_ids": [t["task_id"] for t in normalized],
        "task_overall": overall, "criterion_verdicts": criteria,
        "criterion_micro_agreement": criteria["raw_agreement"], "criterion_macro_task_agreement": macro,
        "intervals": intervals,
        "bootstrap": {"unit": "whole task", "resamples": bootstrap_samples, "seed": seed, "minimum_tasks_for_ci": min_tasks_for_ci,
                      "minimum_defined_fraction": minimum_defined_fraction, "criterion_weighting": "micro gives equal weight per criterion; macro gives equal weight per task with matched criteria"},
        "interpretation": "Agreement diagnostics only. No human gold or correctness labels are supplied; these are not accuracy, false-accept, sensitivity or expert-acceptance estimates.",
        "caveats": [
            "Purposive task selection and small samples limit generalization; the intervals do not establish representative population rates.",
            "Cohort, rubric, evidence and tool-access differences remain potential explanations for disagreement.",
            "Uncertain/uncertain counts as agreement in the multiclass matrix, not evidence of successful work.",
            "Fail-positive agreement excludes uncertain/not_assessed pairs; inspect their separate counts before interpreting it.",
            "Task resampling preserves within-task criterion dependence, but does not resolve dependence between tasks sharing sources or business families.",
            "Degenerate intervals and undefined kappa/positive-agreement denominators are reported explicitly; agreement does not prove correctness.",
        ],
    }
