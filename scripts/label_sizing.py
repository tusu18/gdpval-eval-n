"""How many located labels a buyer needs to show a trained critic beats the untrained judges measured here.

Inputs are this study's own numbers (results.json): the error prevalence in the random sample, the located-error
recall of the judges (site_src/judge_locate_v31.json via results_v31), and the timed minutes per full-output label.
Output: the size of a sealed test set, not of a training set; no training was run, so training volume is not estimated.

Test: one-sided exact binomial, H0 recall <= baseline, alpha 0.05, power 0.80, against a fixed baseline. The baseline is
itself estimated from 7 cases, so the table is a planning figure, not a guarantee.
"""
import math

ALPHA, POWER, SECOND_READER_SHARE = 0.05, 0.80, 0.20


def _binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def errors_needed(p0, p1, alpha=ALPHA, power=POWER, n_max=2000):
    """Smallest n (errors in the sealed test) whose exact one-sided test of recall > p0 has the given power at recall p1."""
    for n in range(1, n_max + 1):
        k = next((k for k in range(n + 1) if _binom_sf(k, n, p0) <= alpha), None)  # critical count
        if k is not None and _binom_sf(k, n, p1) >= power:
            return n, k
    return None, None


def sizing(prevalence, prevalence_ci, minutes, baselines, targets):
    lo, hi = min(minutes), max(minutes)
    rows = []
    for name, (k0, n0) in baselines.items():
        p0 = k0 / n0
        for p1 in targets[name]:
            n, k = errors_needed(p0, p1)
            reads = math.ceil(n / prevalence)
            reads_range = [math.ceil(n / prevalence_ci[1]), math.ceil(n / prevalence_ci[0])]
            hours = [round(reads * m * (1 + SECOND_READER_SHARE) / 60, 1) for m in (lo, hi)]
            rows.append({'baseline': name, 'baseline_recall': [k0, n0], 'target_recall': p1, 'errors_needed': n, 'critical_count': k,
                         'outputs_to_read': reads, 'outputs_to_read_range': reads_range, 'reviewer_hours': hours})
    return {'alpha': ALPHA, 'power': POWER, 'second_reader_share': SECOND_READER_SHARE, 'minutes_per_label': [lo, hi],
            'prevalence': round(prevalence, 3), 'prevalence_ci': prevalence_ci, 'rows': rows}
