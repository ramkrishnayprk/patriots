from app.retrieval.conversation import resolve_conversational_reference


def _history(*titles):
    return [
        {"role": "user", "content": "Tell me about a movie"},
        {
            "role": "assistant",
            "content": "Here is the answer.",
            "sources": [
                {
                    "title": title,
                    "url": f"https://www.imdb.com/title/{index}/",
                }
                for index, title in enumerate(titles, start=1)
            ],
        },
    ]


def test_resolves_bare_followup_from_recent_single_movie_source():
    rewrite = resolve_conversational_reference(
        "Explain more",
        _history("Laggam Time"),
    )

    assert rewrite is not None
    assert rewrite.rewritten_query == "Tell me more about Laggam Time"
    assert rewrite.referenced_title == "Laggam Time"


def test_resolves_pronoun_and_field_followups_without_an_llm():
    pronoun = resolve_conversational_reference(
        "Who directed it?",
        _history("Laggam Time"),
    )
    field = resolve_conversational_reference(
        "What about its runtime?",
        _history("Laggam Time"),
    )

    assert pronoun is not None
    assert pronoun.rewritten_query == "Who directed Laggam Time?"
    assert field is not None
    assert field.rewritten_query == "What is the runtime of Laggam Time?"


def test_does_not_guess_when_recent_response_has_multiple_movies():
    rewrite = resolve_conversational_reference(
        "Explain more about the movie",
        _history("Movie One", "Movie Two"),
    )

    assert rewrite is None


def test_standalone_query_is_not_rewritten():
    rewrite = resolve_conversational_reference(
        "What are the top action movies?",
        _history("Laggam Time"),
    )

    assert rewrite is None
