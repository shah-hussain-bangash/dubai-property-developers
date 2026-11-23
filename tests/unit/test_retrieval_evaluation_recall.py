"""Document recall measures the relevant fraction rather than a binary hit rate."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from knowledge.evaluation.metrics import EvalCase, evaluate_retrieval
from knowledge.vectorstores.base import RetrievalFilter


def fixture_result(*keys):
    return SimpleNamespace(
        hits=[SimpleNamespace(chunk=SimpleNamespace(document_key=key)) for key in keys]
    )


class RetrievalEvaluationRecallTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_document_coverage_is_not_reported_as_full_recall(self):
        retriever = SimpleNamespace(
            retrieve=AsyncMock(return_value=fixture_result("fixture-other", "fixture-a"))
        )
        filters = RetrievalFilter(tenant_id="fixture")
        case = EvalCase("fixture-query", frozenset({"fixture-a", "fixture-b"}))

        report = await evaluate_retrieval(retriever, [case], filters, k=2)

        self.assertEqual(report.cases, 1)
        self.assertEqual(report.recall_at_k, 0.5)
        self.assertEqual(report.mrr, 0.5)
        retriever.retrieve.assert_awaited_once_with("fixture-query", filters, k=2)

    async def test_duplicate_chunks_count_as_one_relevant_document(self):
        retriever = SimpleNamespace(
            retrieve=AsyncMock(return_value=fixture_result("fixture-a", "fixture-a"))
        )

        report = await evaluate_retrieval(
            retriever,
            [EvalCase("fixture-query", frozenset({"fixture-a", "fixture-b"}))],
            RetrievalFilter(tenant_id="fixture"),
        )

        self.assertEqual(report.recall_at_k, 0.5)
        self.assertEqual(report.mrr, 1.0)

    async def test_recall_is_averaged_per_query_with_different_relevant_set_sizes(self):
        responses = [fixture_result("fixture-a"), fixture_result("fixture-e")]
        retriever = SimpleNamespace(retrieve=AsyncMock(side_effect=responses))
        cases = [
            EvalCase(
                "fixture-first", frozenset({"fixture-a", "fixture-b", "fixture-c", "fixture-d"})
            ),
            EvalCase("fixture-second", frozenset({"fixture-e"})),
        ]

        report = await evaluate_retrieval(retriever, cases, RetrievalFilter(tenant_id="fixture"))

        self.assertEqual(report.cases, 2)
        self.assertEqual(report.recall_at_k, 0.625)
        self.assertEqual(report.mrr, 1.0)

    async def test_no_matches_and_empty_relevant_sets_contribute_zero(self):
        retriever = SimpleNamespace(
            retrieve=AsyncMock(side_effect=[fixture_result(), fixture_result("fixture-other")])
        )
        cases = [
            EvalCase("fixture-missing", frozenset({"fixture-a"})),
            EvalCase("fixture-unlabelled", frozenset()),
        ]

        report = await evaluate_retrieval(retriever, cases, RetrievalFilter(tenant_id="fixture"))

        self.assertEqual(report.cases, 2)
        self.assertEqual(report.recall_at_k, 0.0)
        self.assertEqual(report.mrr, 0.0)

    async def test_empty_case_list_returns_zero_without_retrieving(self):
        retriever = SimpleNamespace(retrieve=AsyncMock())

        report = await evaluate_retrieval(retriever, [], RetrievalFilter(tenant_id="fixture"))

        self.assertEqual(report.cases, 0)
        self.assertEqual(report.recall_at_k, 0.0)
        self.assertEqual(report.mrr, 0.0)
        retriever.retrieve.assert_not_awaited()
