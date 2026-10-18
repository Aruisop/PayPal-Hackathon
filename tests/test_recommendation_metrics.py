"""Independent small examples for metric definitions; no model is loaded."""
import math
import unittest

from evaluation.metrics import (ndcg_at_k, quantile, ranking_metrics,
                                recall_at_k, reciprocal_rank_at_k, top1_relevant)


class RankingMetricTests(unittest.TestCase):
    def test_ideal_order_and_reversal_use_graded_gain(self):
        labels = {'best': 3, 'good': 2, 'related': 1}
        self.assertEqual(ndcg_at_k(['best', 'good', 'related'], labels), 1)
        actual = ndcg_at_k(['related', 'good', 'best'], labels)
        expected = (1 + 3 / math.log2(3) + 7 / 2) / (7 + 3 / math.log2(3) + 1 / 2)
        self.assertAlmostEqual(actual, expected)
        self.assertLess(actual, 1)

    def test_rank_threshold_and_recall_are_distinct(self):
        labels = {'best': 3, 'good': 2, 'related': 1, 'missed': 3}
        ranking = ['related', 'best', 'good', 'missed']
        self.assertEqual(reciprocal_rank_at_k(ranking, labels), .5)
        self.assertEqual(top1_relevant(ranking, labels), 0)
        self.assertAlmostEqual(recall_at_k(ranking, labels), 2 / 3)
        self.assertEqual(reciprocal_rank_at_k(ranking, labels, k=1), 0)

    def test_empty_output_fails_answerable_query(self):
        result = ranking_metrics([], {'answer': 3})
        self.assertEqual(result, {'ndcg@3': 0, 'mrr@3': 0, 'top1Relevant': 0, 'recall@3': 0})

    def test_unanswerable_reference_is_not_fake_perfect_accuracy(self):
        for ranking in ([], ['invented-answer']):
            for labels in ({}, {'catalog-item': 0}):
                with self.subTest(ranking=ranking, labels=labels):
                    self.assertTrue(all(value is None for value in ranking_metrics(ranking, labels).values()))

    def test_weak_related_item_only_has_graded_gain(self):
        labels = {'weak': 1}
        self.assertEqual(ndcg_at_k(['weak'], labels), 1)
        self.assertIsNone(reciprocal_rank_at_k(['weak'], labels))
        self.assertIsNone(top1_relevant(['weak'], labels))
        self.assertIsNone(recall_at_k(['weak'], labels))

    def test_unknown_ids_are_irrelevant_and_duplicate_ids_are_rejected(self):
        self.assertEqual(ndcg_at_k(['unknown'], {'answer': 3}), 0)
        self.assertEqual(recall_at_k(['unknown'], {'answer': 3}), 0)
        with self.assertRaises(ValueError):
            ranking_metrics(['answer', 'answer'], {'answer': 3})

    def test_malformed_labels_and_cutoff_are_rejected(self):
        for labels in ({'a': True}, {'a': 4}, {'a': -1}, {'a': 2.0}):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                ranking_metrics(['a'], labels)
        for cutoff in (0, -1, True, 1.5):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                ndcg_at_k(['a'], {'a': 3}, cutoff)


class QuantileTests(unittest.TestCase):
    def test_linear_interpolation_and_endpoints(self):
        observations = [40, 10, 30, 20]
        self.assertEqual(quantile(observations, .5), 25)
        self.assertAlmostEqual(quantile(observations, .95), 38.5)
        self.assertEqual(quantile(observations, 0), 10)
        self.assertEqual(quantile(observations, 1), 40)
        self.assertEqual(observations, [40, 10, 30, 20])

    def test_empty_singleton_and_duplicates(self):
        self.assertIsNone(quantile([], .95))
        self.assertEqual(quantile([7], .95), 7)
        self.assertEqual(quantile([4, 4, 4, 100], .5), 4)

    def test_nonfinite_negative_or_invalid_probability_rejected(self):
        for observations in ([math.nan], [math.inf], [-1], [True], ['1']):
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                quantile(observations, .5)
        for probability in (-.1, 1.1, math.nan, math.inf, True, '0.5'):
            with self.subTest(probability=probability), self.assertRaises(ValueError):
                quantile([1, 2], probability)


if __name__ == '__main__':
    unittest.main()
