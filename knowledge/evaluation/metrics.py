"""Retrieval evaluation: recall@k and MRR over labelled query sets."""

from __future__ import annotations

from dataclasses import dataclass

from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import RetrievalFilter


@dataclass(frozen=True, slots=True)
class EvalCase:
    query: str
    relevant_document_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class EvalReport:
    cases: int
    recall_at_k: float
    mrr: float


async def evaluate_retrieval(
    retriever: Retriever, cases: list[EvalCase], filters: RetrievalFilter, *, k: int = 4
) -> EvalReport:
    if not cases:
        return EvalReport(0, 0.0, 0.0)
    hits_total = 0
    reciprocal_sum = 0.0
    for case in cases:
        result = await retriever.retrieve(case.query, filters, k=k)
        keys = [h.chunk.document_key for h in result.hits]
        if case.relevant_document_keys.intersection(keys):
            hits_total += 1
        for rank, key in enumerate(keys, start=1):
            if key in case.relevant_document_keys:
                reciprocal_sum += 1.0 / rank
                break
    return EvalReport(len(cases), hits_total / len(cases), reciprocal_sum / len(cases))
