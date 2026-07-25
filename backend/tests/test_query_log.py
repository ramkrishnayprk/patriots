from app.feedback.query_log import QueryLogStore


def test_query_log_appends_lists_and_filters_entries(tmp_path):
    store = QueryLogStore(tmp_path / "query_logs" / "queries.jsonl")

    answered = store.append(
        {
            "query": "Show me details of Laggam Time",
            "decision": "answered",
            "triage_bucket": "answered",
        }
    )
    refused = store.append(
        {
            "query": "Unknown movie",
            "decision": "refused",
            "triage_bucket": "needs_review",
        }
    )

    assert [item["id"] for item in store.list_recent()] == [
        refused["id"],
        answered["id"],
    ]
    assert store.list_recent(decision="refused") == [refused]
    assert store.list_recent(triage_bucket="answered") == [answered]


def test_query_log_ignores_malformed_lines(tmp_path):
    path = tmp_path / "queries.jsonl"
    path.write_text('{"query":"valid","decision":"answered"}\nnot-json\n', encoding="utf-8")

    assert QueryLogStore(path).list_recent() == [
        {"query": "valid", "decision": "answered"}
    ]
