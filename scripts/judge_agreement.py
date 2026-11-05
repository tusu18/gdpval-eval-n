"""Descriptive agreement diagnostics, not a test of judge correctness.

Callers must first enforce their own evidence, task-validity and missing-label
gates. This module never coerces uncertain or absent labels into yes/no.
"""
from collections import Counter


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def agreement_diagnostics(pairs, labels=('yes', 'no'), positive_label='yes'):
    """Return all contingency cells and margins for exact categorical pairs.

    Cohen's kappa is withheld when no comparison is available, there is only
    one pair, or either rater has no observed label variation. The latter is
    distinct from the mathematically undefined case where expected agreement
    is one. A small-sample warning is descriptive, not a minimum sample-size
    guarantee. No independence, confidence interval or accuracy is inferred.
    """
    labels = tuple(labels)
    if len(labels) < 2 or len(set(labels)) != len(labels):
        raise ValueError('At least two distinct declared labels are required')
    if positive_label is not None and (len(labels) != 2 or positive_label not in labels):
        raise ValueError('Positive agreement requires two labels and a declared positive label')
    pairs = list(pairs)
    if any(len(pair) != 2 or any(value not in labels for value in pair) for pair in pairs):
        raise ValueError('Undeclared, missing or uncertain labels must be gated explicitly')
    cells = Counter(tuple(pair) for pair in pairs)
    left = {label: sum(n for (a, _), n in cells.items() if a == label) for label in labels}
    right = {label: sum(n for (_, b), n in cells.items() if b == label) for label in labels}
    n = len(pairs)
    agree = sum(cells[label, label] for label in labels)
    expected_numerator = sum(left[label] * right[label] for label in labels)
    denominator = n * n - expected_numerator
    warnings = []
    if 0 < n < 20:
        warnings.append('very_small_sample')
    if n and any(max(margin.values()) / n >= 0.9 for margin in (left, right)):
        warnings.append('dominant_label_margin')
    if not n:
        kappa = {'value': None, 'status': 'no_pairs'}
    elif not denominator:
        kappa = {'value': None, 'status': 'degenerate_marginals'}
    elif n < 2:
        kappa = {'value': None, 'status': 'insufficient_pairs'}
    elif any(sum(count > 0 for count in margin.values()) < 2 for margin in (left, right)):
        # With a constant rater, a finite kappa of zero is uninformative about
        # discrimination. Preserve the complete table instead of reporting it.
        kappa = {'value': None, 'status': 'suppressed_single_label_margin'}
    else:
        kappa = {'value': (agree * n - expected_numerator) / denominator,
                 'status': 'descriptive_only'}
    kappa['warnings'] = warnings
    kappa['expected_agreement'] = ratio(expected_numerator, n * n)
    kappa['small_sample_note'] = 'The n<20 flag is a reporting caution, not a threshold that establishes validity or independent sampling.'
    result = {
        'comparable': n, 'label_order': list(labels),
        'full_matrix': [{'left': a, 'right': b, 'count': cells[a, b]} for a in labels for b in labels],
        'label_frequencies': {'left': left, 'right': right},
        'observed_agreement': ratio(agree, n), 'cohen_kappa': kappa,
        'scope': 'Descriptive agreement conditional on caller-defined eligibility. Agreement and kappa do not establish correctness; related cases are not independent observations.'}
    if positive_label is not None:
        negative_label = next(label for label in labels if label != positive_label)
        result.update(positive_label=positive_label, negative_label=negative_label,
                      positive_agreement=ratio(2 * cells[positive_label, positive_label], left[positive_label] + right[positive_label]),
                      negative_agreement=ratio(2 * cells[negative_label, negative_label], left[negative_label] + right[negative_label]))
    return result
