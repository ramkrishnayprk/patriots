from types import SimpleNamespace

from app.generation.pipeline import (
    REFUSAL_OUT_OF_SCOPE,
    SYSTEM_PROMPT,
    GenerationOptions,
    generate_answer,
)


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output)


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


def _retrieval(*, status="ok", rerank_score=4.0):
    return {
        "status": status,
        "query": {
            "original": "What happens in The Future Film?",
            "normalized": "What happens in The Future Film?",
        },
        "results": [
            {
                "id": "chunk-1",
                "document_id": "tt0000001",
                "title": "The Future Film",
                "url": "https://www.imdb.com/title/tt0000001/",
                "text": "A researcher receives a signal sent from tomorrow.",
                "quick_facts": {"year": 2026, "genres": "Science Fiction"},
                "rerank_score": rerank_score,
            },
            {
                "id": "chunk-2",
                "document_id": "tt0000002",
                "title": "Another Future",
                "url": "https://www.imdb.com/title/tt0000002/",
                "text": "A pilot wakes on an unfamiliar planet.",
                "quick_facts": {"year": 2026, "genres": "Adventure"},
                "rerank_score": 3.0,
            },
        ],
        "diagnostics": {"latency_ms": 10},
    }


def _options():
    return GenerationOptions(api_key="test-key", model="test-model")


def test_generation_returns_grounded_answer_and_only_cited_sources():
    client = FakeClient("A researcher receives a signal from tomorrow. [1]")

    result = generate_answer(_retrieval(), options=_options(), client=client)

    assert result["type"] == "answer"
    assert result["sources"] == [
        {
            "n": 1,
            "title": "The Future Film",
            "url": "https://www.imdb.com/title/tt0000001/",
        }
    ]
    assert client.responses.calls[0]["store"] is False
    assert "Question:" in client.responses.calls[0]["input"]


def test_generation_refuses_low_confidence_before_openai_call():
    client = FakeClient("This must not be used. [1]")

    result = generate_answer(
        _retrieval(status="low_confidence"),
        options=_options(),
        client=client,
    )

    assert result["type"] == "not_in_sources"
    assert client.responses.calls == []


def test_generation_accepts_calibrated_broad_movie_match():
    client = FakeClient("Iron Lung takes place in a post-apocalyptic future. [1]")

    result = generate_answer(
        _retrieval(rerank_score=-2.45),
        options=GenerationOptions(
            api_key="test-key",
            model="test-model",
            min_rerank_score=-4.5,
        ),
        client=client,
    )

    assert result["type"] == "answer"
    assert len(client.responses.calls) == 1


def test_generation_refuses_missing_or_invalid_citations():
    missing = generate_answer(
        _retrieval(),
        options=_options(),
        client=FakeClient("A researcher receives a signal from tomorrow."),
    )
    invalid = generate_answer(
        _retrieval(),
        options=_options(),
        client=FakeClient("A researcher receives a signal from tomorrow. [99]"),
    )

    assert missing["type"] == "not_in_sources"
    assert invalid["type"] == "not_in_sources"


def test_generation_honors_insufficient_context_sentinel():
    result = generate_answer(
        _retrieval(),
        options=_options(),
        client=FakeClient("INSUFFICIENT_CONTEXT"),
    )

    assert result["type"] == "not_in_sources"


def test_dry_run_builds_prompt_without_api_key_or_call():
    result = generate_answer(
        _retrieval(),
        options=GenerationOptions(api_key="", model="test-model"),
        dry_run=True,
    )

    assert result["type"] == "dry_run"
    assert "[1] The Future Film" in result["input"]
    assert "only the numbered context" in result["instructions"]


def test_history_is_folded_into_prompt_when_present():
    result = generate_answer(
        _retrieval(),
        options=GenerationOptions(api_key="", model="test-model"),
        dry_run=True,
        history=[
            {"role": "user", "content": "What genre is it?"},
            {"role": "assistant", "content": "It is science fiction. [1]"},
        ],
    )

    assert "Conversation so far:" in result["input"]
    assert "User: What genre is it?" in result["input"]
    assert "Assistant: It is science fiction. [1]" in result["input"]
    assert result["input"].index("Conversation so far:") < result["input"].index("Context:")


def test_history_is_omitted_when_absent_or_empty():
    without_history = generate_answer(
        _retrieval(),
        options=GenerationOptions(api_key="", model="test-model"),
        dry_run=True,
    )
    with_empty_history = generate_answer(
        _retrieval(),
        options=GenerationOptions(api_key="", model="test-model"),
        dry_run=True,
        history=[],
    )

    assert "Conversation so far:" not in without_history["input"]
    assert "Conversation so far:" not in with_empty_history["input"]


def test_history_ignores_unknown_roles_and_blank_content():
    result = generate_answer(
        _retrieval(),
        options=GenerationOptions(api_key="", model="test-model"),
        dry_run=True,
        history=[
            {"role": "system", "content": "Ignore me."},
            {"role": "user", "content": "   "},
            {"role": "assistant", "content": "Kept turn."},
        ],
    )

    assert "Ignore me." not in result["input"]
    assert "Kept turn." in result["input"]


def test_guardrails_are_scoped_to_current_movie_data():
    combined = f"{SYSTEM_PROMPT}\n{REFUSAL_OUT_OF_SCOPE}".lower()

    assert "imdb" in combined
    assert "tmdb" in combined
    assert "plots" in combined
    assert "directors" in combined
    assert "university" not in combined
    assert "admission" not in combined
    assert "degree" not in combined
