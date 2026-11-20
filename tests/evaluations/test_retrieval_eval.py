"""Retrieval evaluation on the fictional demo corpus (regression guard, not a quality claim).

The hashing embedder is lexical only; thresholds here are deliberately modest and
should be raised once a real embedding model is configured.
"""

from __future__ import annotations

from knowledge.documents.models import AccessLevel
from knowledge.evaluation.metrics import EvalCase, evaluate_retrieval
from knowledge.vectorstores.base import RetrievalFilter
from tests.factories import TENANT
from workflows.runtime import PlatformRuntime

CASES = [
    EvalCase("Demo Creek Heights payment plan", frozenset({"demo-creek-heights-payment-plan"})),
    EvalCase(
        "how do I reserve a unit and sign the sales agreement", frozenset({"faq-buying-process"})
    ),
    EvalCase("can I schedule viewings of the show homes", frozenset({"faq-buying-process"})),
]


async def test_demo_corpus_retrieval_quality(runtime: PlatformRuntime) -> None:
    report = await evaluate_retrieval(
        runtime.retriever,
        CASES,
        RetrievalFilter(tenant_id=TENANT, access_levels={AccessLevel.PUBLIC}),
        k=2,
    )
    assert report.cases == 3
    assert report.recall_at_k == 1.0
    assert report.mrr >= 0.8
