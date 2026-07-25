from pathlib import Path

from app.scraper.fetcher import FetchResult
from app.scraper.pipeline import crawl_site

ROBOTS = """
User-agent: *
Disallow: /wp-admin/
Crawl-delay: 0
"""

HOME_HTML = """
<!doctype html>
<html>
  <body>
    <main>
      <h1>Degrees</h1>
      <a href="/programs/data-science/">Data Science</a>
    </main>
  </body>
</html>
"""

PROGRAM_HTML = """
<!doctype html>
<html>
  <head>
    <title>Data Science, M.S.</title>
    <meta name="description" content="Prepare for a rewarding career in data science.">
    <link rel="canonical" href="/programs/data-science/">
  </head>
  <body>
    <main>
      <h1>Data Science, M.S.</h1>
      <p>Complete 30 Credit Hours in a flexible online learning environment.</p>
      <h2>Program Overview</h2>
      <p>
        Develop advanced statistical, analytical, programming, visualization,
        database, and machine learning expertise for modern organizations.
        Students complete applied projects that address practical industry
        challenges and prepare them for technical leadership opportunities.
      </p>
      <h2>Program Outcomes</h2>
      <p>
        Graduates communicate analytical findings, design reliable data
        pipelines, evaluate machine learning models, and make ethical
        evidence-based decisions.
      </p>
    </main>
  </body>
</html>
"""


def test_pipeline_crawls_extracts_chunks_and_checkpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRAPERAPI_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_PAGES", "2")
    monkeypatch.setenv("MIN_DELAY_SECONDS", "0")
    monkeypatch.setenv("MAX_DELAY_SECONDS", "0")
    monkeypatch.setenv("CHECKPOINT_INTERVAL", "1")
    monkeypatch.setattr("app.scraper.pipeline.time.sleep", lambda _seconds: None)

    def fake_fetch(_client, target_url, *, render=False):
        del render
        if target_url.endswith("/robots.txt"):
            return FetchResult(ROBOTS, "text/plain", 200)
        if target_url.endswith("/programs/data-science/"):
            return FetchResult(PROGRAM_HTML, "text/html", 200)
        return FetchResult(HOME_HTML, "text/html", 200)

    monkeypatch.setattr("app.scraper.pipeline.ScraperApiClient.fetch", fake_fetch)

    result = crawl_site(run_id="pipeline-test")

    run_dir = Path(tmp_path) / result["artifacts"]
    assert result["pages_processed"] == 2
    assert result["programs"] == 1
    assert result["chunks"] >= 1
    assert (run_dir / "programs.json").exists()
    assert (run_dir / "chunks.jsonl").read_text(encoding="utf-8").count("\n") >= 1
