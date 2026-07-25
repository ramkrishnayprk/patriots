from app.scraper.url_utils import is_allowed_crawl_url, is_program_url, normalize_url, safe_filename

BASE_URL = "https://degrees.ucumberlands.edu/"
DOMAIN = "degrees.ucumberlands.edu"


def test_normalize_url_removes_tracking_and_fragment():
    result = normalize_url(
        "/programs/data-science?utm_source=test&level=graduate#overview",
        base_url=BASE_URL,
        allowed_domain=DOMAIN,
    )

    assert result == "https://degrees.ucumberlands.edu/programs/data-science/?level=graduate"
    assert is_program_url(result)


def test_url_policy_rejects_external_and_non_content_urls():
    assert (
        normalize_url("https://example.com/program", base_url=BASE_URL, allowed_domain=DOMAIN)
        is None
    )
    assert not is_allowed_crawl_url(
        "https://degrees.ucumberlands.edu/wp-admin/", allowed_domain=DOMAIN
    )
    assert not is_allowed_crawl_url(
        "https://degrees.ucumberlands.edu/image.webp", allowed_domain=DOMAIN
    )


def test_safe_filename_is_stable():
    first = safe_filename("https://degrees.ucumberlands.edu/programs/data-science/")
    second = safe_filename("https://degrees.ucumberlands.edu/programs/data-science/")

    assert first == second
    assert first.endswith(".html")
