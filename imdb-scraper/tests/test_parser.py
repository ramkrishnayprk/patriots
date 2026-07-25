import json

import pytest

from imdb_scraper.parser import ParseError, parse_title_page
from imdb_scraper.urls import load_seed_urls, normalize_title_url


HTML = """
<!doctype html>
<html>
  <head>
    <link rel="canonical" href="https://www.imdb.com/title/tt1234567/">
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": "Example Film",
        "alternateName": "Original Example",
        "description": "A compact test overview.",
        "datePublished": "2026-05-10",
        "duration": "PT2H4M",
        "genre": ["Drama", "Mystery"],
        "keywords": "secret,investigation",
        "director": [{"@type": "Person", "name": "Ada Director"}],
        "creator": [{"@type": "Person", "name": "Will Writer"}],
        "actor": [
          {"@type": "Person", "name": "Alex Actor"},
          {"@type": "Person", "name": "Sam Star"}
        ],
        "aggregateRating": {
          "@type": "AggregateRating",
          "ratingValue": "8.2",
          "ratingCount": "12,345",
          "bestRating": "10",
          "worstRating": "1"
        }
      }
    </script>
  </head>
  <body></body>
</html>
"""


def test_parse_title_page_extracts_normalized_metadata():
    record = parse_title_page(
        HTML,
        "https://www.imdb.com/title/tt1234567/",
    )

    assert record["imdb_id"] == "tt1234567"
    assert record["title"] == "Example Film"
    assert record["runtime_minutes"] == 124
    assert record["genres"] == ["Drama", "Mystery"]
    assert record["directors"] == ["Ada Director"]
    assert record["actors"] == ["Alex Actor", "Sam Star"]
    assert record["rating"] == 8.2
    assert record["rating_count"] == 12345
    assert len(record["raw_sha256"]) == 64


def test_parse_title_page_requires_movie_json_ld():
    with pytest.raises(ParseError):
        parse_title_page(
            "<html><head></head><body></body></html>",
            "https://www.imdb.com/title/tt1234567/",
        )


def test_seed_loader_rejects_non_title_urls_and_deduplicates(tmp_path):
    path = tmp_path / "seeds.txt"
    path.write_text(
        "# comment\n"
        "https://www.imdb.com/title/tt1234567/\n"
        "https://imdb.com/title/tt1234567\n",
        encoding="utf-8",
    )

    assert load_seed_urls(path, 25) == [
        ("https://www.imdb.com/title/tt1234567/", "tt1234567")
    ]
    with pytest.raises(ValueError):
        normalize_title_url("https://example.com/title/tt1234567/")


def test_json_fixture_is_valid():
    script = HTML.split('<script type="application/ld+json">', 1)[1].split(
        "</script>", 1
    )[0]
    assert json.loads(script)["@type"] == "Movie"
