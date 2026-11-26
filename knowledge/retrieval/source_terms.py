"""Conservative English wording normalization for supplied-source matching only.

These rules select passages; they never rewrite a source or generate an answer.
The hashing embedder and its stored vectors retain their existing tokenizer.
"""

from knowledge.embeddings.base import tokenize_unicode

_FORMS = (
    "garden gardens",
    "visit visits",
    "payment payments",
    "plan plans",
    "installment installments instalment instalments",
    "deposit deposits",
    "viewing viewings",
    "booking bookings",
    "document documents",
    "fee fees",
    "bedroom bedrooms",
    "apartment apartments",
    "villa villas",
    "enquiry enquiries inquiry inquiries",
    "cancelled canceled",
)
_CANONICAL = {word: group.split()[0] for group in _FORMS for word in group.split()}
_QUESTION_PREFIXES = sorted(
    {
        tuple(tokenize_unicode(phrase))
        for phrase in (
            "Could you please tell me about",
            "Would you please tell me about",
            "Could you tell me about",
            "Would you tell me about",
            "Please tell me about",
            "Tell me about",
            "Could you please explain",
            "Would you please explain",
            "Could you explain",
            "Would you explain",
            "Please explain",
            "Explain",
            "Please",
        )
    },
    key=lambda words: (-len(words), words),
)


def passage_terms(text: str) -> set[str]:
    return {_CANONICAL.get(word, word) for word in tokenize_unicode(text)}


def question_terms(text: str) -> set[str]:
    words = tokenize_unicode(text)
    for prefix in _QUESTION_PREFIXES:
        if tuple(words[: len(prefix)]) == prefix:
            words = words[len(prefix) :]
            break
    return {_CANONICAL.get(word, word) for word in words}
