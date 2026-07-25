from app.scraper.chunking import create_chunks
from app.scraper.extractor import (
    extract_internal_links,
    extract_program_page,
)

BASE_URL = "https://degrees.ucumberlands.edu/"
PROGRAM_URL = "https://degrees.ucumberlands.edu/programs/data-science/"
DOMAIN = "degrees.ucumberlands.edu"

HTML = """
<!doctype html>
<html>
  <head>
    <title>Data Science | UC</title>
    <meta name="description" content="Prepare for a data science career.">
    <link rel="canonical" href="/programs/data-science/">
  </head>
  <body>
    <nav><a href="/programs/ignored-nav/">Navigation</a></nav>
    <main>
      <h1>Data Science, M.S.</h1>
      <p>Complete 30 Credit Hours through a 100% online program.</p>
      <h2>Program Outcomes</h2>
      <p>Build statistical, analytical, and machine learning expertise.</p>
      <a href="/programs/artificial-intelligence/?utm_source=test">Related</a>
      <a href="https://example.com/external">External</a>
    </main>
    <script>ignored()</script>
  </body>
</html>
"""


def test_program_extraction_and_chunking():
    document = extract_program_page(
        HTML,
        PROGRAM_URL,
        base_url=BASE_URL,
        allowed_domain=DOMAIN,
    )
    chunks = create_chunks(document, chunk_size=300, chunk_overlap=50)

    assert document["title"] == "Data Science, M.S."
    assert document["quick_facts"]["credit_hours"] == "30"
    assert document["quick_facts"]["delivery_format"] == "Online"
    assert "ignored()" not in document["text"]
    assert chunks
    assert all(chunk["document_id"] == document["id"] for chunk in chunks)


def test_internal_link_extraction_stays_on_allowed_domain():
    links = extract_internal_links(
        HTML,
        PROGRAM_URL,
        base_url=BASE_URL,
        allowed_domain=DOMAIN,
    )

    assert "https://degrees.ucumberlands.edu/programs/artificial-intelligence/" in links
    assert all("example.com" not in link for link in links)
