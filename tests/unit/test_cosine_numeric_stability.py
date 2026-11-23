"""Finite embedding magnitudes must not corrupt similarity scores or ranking."""

import math
import unittest

from knowledge.documents.models import AccessLevel, Chunk
from knowledge.embeddings.base import cosine
from knowledge.vectorstores.base import InMemoryVectorStore, RetrievalFilter


class CosineNumericStabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_large_vectors_have_finite_correct_scores(self):
        self.assertAlmostEqual(cosine([3e300, 4e300], [0.0, 5e300]), 0.8)
        self.assertAlmostEqual(cosine([1e308] * 4, [1e308] * 4), 1.0)
        self.assertAlmostEqual(cosine([1e308] * 4, [-1e308] * 4), -1.0)

    def test_tiny_and_mixed_magnitudes_keep_the_same_direction_score(self):
        for first, second in ((1e-300, 1e-300), (1e300, 1e-300), (1e-300, 1e300)):
            with self.subTest(first=first, second=second):
                self.assertAlmostEqual(cosine([3 * first, 4 * first], [0.0, 5 * second]), 0.8)

    def test_non_finite_coordinates_are_rejected_in_either_vector(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            for first, second in (([value, 1.0], [0.0, 0.0]), ([0.0, 0.0], [value, 1.0])):
                with (
                    self.subTest(value=value, first=first),
                    self.assertRaisesRegex(ValueError, "finite"),
                ):
                    cosine(first, second)

    def test_ordinary_zero_and_dimension_cases_keep_expected_behavior(self):
        self.assertAlmostEqual(cosine([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertEqual(cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(cosine([0.0, 0.0], [1.0, 0.0]), 0.0)
        self.assertEqual(cosine([], []), 0.0)
        with self.assertRaises(ValueError):
            cosine([0.0], [0.0, 0.0])

    async def test_search_ranks_large_finite_vectors_by_similarity(self):
        def chunk(identifier):
            return Chunk(
                chunk_id=identifier,
                tenant_id="fixture",
                document_id=identifier,
                document_key=identifier,
                version=1,
                title="Fictional vector fixture",
                chunk_index=0,
                content="Fictional vector fixture text",
                access_level=AccessLevel.PUBLIC,
            )

        store = InMemoryVectorStore()
        await store.upsert(
            [chunk("a-orthogonal"), chunk("z-matching")],
            [[0.0, 1e300], [1e300, 0.0]],
        )

        hits = await store.search([1e300, 0.0], k=2, filters=RetrievalFilter(tenant_id="fixture"))

        self.assertEqual([hit.chunk.chunk_id for hit in hits], ["z-matching", "a-orthogonal"])
        self.assertTrue(all(math.isfinite(hit.score) for hit in hits))
        self.assertAlmostEqual(hits[0].score, 1.0)
        self.assertEqual(hits[1].score, 0.0)
