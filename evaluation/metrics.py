"""Pure ranking metrics for synthetic fixtures, independent from model inference.

Unanswerable cases have no graded-relevant reference and return None instead of
being counted as perfect/failed semantic rankings. Evaluate abstention separately.
"""
import math
from collections.abc import Mapping


def _inputs(ranked_ids, relevance, k):
    if type(k) is not int or k < 1:
        raise ValueError('k must be a positive integer')
    if not isinstance(ranked_ids, (list, tuple)) or any(not isinstance(x, str) for x in ranked_ids):
        raise ValueError('Rankings must be a sequence of IDs')
    if len(set(ranked_ids)) != len(ranked_ids):
        raise ValueError('Duplicate IDs would inflate ranking metrics')
    if not isinstance(relevance, Mapping) or any(not isinstance(key, str) or
            type(grade) is not int or not 0 <= grade <= 3 for key, grade in relevance.items()):
        raise ValueError('Relevance grades must be integers from zero to three')


def ndcg_at_k(ranked_ids, relevance, k=3):
    """Exponential-gain nDCG; None when the ideal reference gain is zero."""
    _inputs(ranked_ids, relevance, k)
    ideal = sorted(relevance.values(), reverse=True)[:k]
    ideal_gain = math.fsum((2 ** grade - 1) / math.log2(rank + 2)
                           for rank, grade in enumerate(ideal))
    if ideal_gain == 0:
        return None
    gain = math.fsum((2 ** relevance.get(offer_id, 0) - 1) / math.log2(rank + 2)
                    for rank, offer_id in enumerate(ranked_ids[:k]))
    return gain / ideal_gain


def reciprocal_rank_at_k(ranked_ids, relevance, k=3):
    """Reciprocal rank of the first grade >= 2 result, through k."""
    _inputs(ranked_ids, relevance, k)
    if not any(grade >= 2 for grade in relevance.values()):
        return None
    return next((1 / rank for rank, offer_id in enumerate(ranked_ids[:k], 1)
                 if relevance.get(offer_id, 0) >= 2), 0.0)


def top1_relevant(ranked_ids, relevance):
    _inputs(ranked_ids, relevance, 1)
    if not any(grade >= 2 for grade in relevance.values()):
        return None
    return float(bool(ranked_ids) and relevance.get(ranked_ids[0], 0) >= 2)


def recall_at_k(ranked_ids, relevance, k=3):
    """Fraction of all grade >= 2 references retrieved in the first k."""
    _inputs(ranked_ids, relevance, k)
    relevant = {offer_id for offer_id, grade in relevance.items() if grade >= 2}
    if not relevant:
        return None
    return len(relevant.intersection(ranked_ids[:k])) / len(relevant)


def ranking_metrics(ranked_ids, relevance, k=3):
    """Per-query values; callers average only non-None entries and report n."""
    return {
        f'ndcg@{k}': ndcg_at_k(ranked_ids, relevance, k),
        f'mrr@{k}': reciprocal_rank_at_k(ranked_ids, relevance, k),
        'top1Relevant': top1_relevant(ranked_ids, relevance),
        f'recall@{k}': recall_at_k(ranked_ids, relevance, k),
    }


def quantile(samples, probability):
    """Linear (R-7) quantile: index=(n-1)*p; interpolate adjacent observations.

    Returns None for no observations. Timing observations must be finite and
    nonnegative. Repeated observations are retained; no outlier is discarded.
    """
    if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError('Quantile probability must be between zero and one')
    values = list(samples)
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        raise ValueError('Timing observations must be finite and nonnegative')
    if not values:
        return None
    values.sort()
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)
