import json

from app.scraper.storage import RunStorage


def test_checkpoint_writes_all_artifacts(tmp_path):
    storage = RunStorage(tmp_path, "test-run")
    storage.save_raw_html("https://degrees.ucumberlands.edu/", "<html>ok</html>")
    storage.save_checkpoint(
        programs=[{"id": "program-1", "title": "Program"}],
        chunks=[{"id": "chunk-1", "text": "Content"}],
        failed_urls=[],
        discovered_urls={"https://degrees.ucumberlands.edu/"},
    )

    assert len(list(storage.raw_html_dir.glob("*.html"))) == 1
    assert json.loads(storage.programs_file.read_text())[0]["id"] == "program-1"
    assert storage.documents_file.read_text().count("\n") == 1
    assert storage.chunks_file.read_text().count("\n") == 1
