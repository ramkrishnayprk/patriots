import json
from types import SimpleNamespace

import pytest

from app.retrieval.expansion import (
    QueryExpansionOptions,
    QueryExpansionProviderError,
    expand_weak_query,
)


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output)


def _options():
    return QueryExpansionOptions(
        api_key="test-key",
        model="test-model",
        variation_count=3,
    )


def test_expand_weak_query_returns_structured_variations_and_hyde():
    responses = FakeResponses(
        json.dumps(
            {
                "variations": [
                    "future-set science fiction films",
                    "science fiction stories about future societies",
                    "sci-fi movies depicting humanity's future",
                ],
                "hypothetical_document": (
                    "A science-fiction movie overview describing a future society."
                ),
            }
        )
    )
    client = SimpleNamespace(responses=responses)

    expanded = expand_weak_query(
        "science fiction movie about the future",
        options=_options(),
        client=client,
    )

    assert len(expanded.variations) == 3
    assert "future society" in expanded.hypothetical_document
    request = responses.calls[0]
    assert request["model"] == "test-model"
    assert request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"


def test_expand_weak_query_rejects_duplicate_or_incomplete_output():
    responses = FakeResponses(
        json.dumps(
            {
                "variations": [
                    "science fiction movie about the future",
                    "future science fiction movie",
                    "future science fiction movie",
                ],
                "hypothetical_document": "A future movie.",
            }
        )
    )

    with pytest.raises(QueryExpansionProviderError):
        expand_weak_query(
            "science fiction movie about the future",
            options=_options(),
            client=SimpleNamespace(responses=responses),
        )


def test_expand_weak_query_validates_variation_budget():
    options = QueryExpansionOptions(
        api_key="test-key",
        model="test-model",
        variation_count=2,
    )

    with pytest.raises(ValueError, match="3 or 4"):
        expand_weak_query("movie query", options=options)
