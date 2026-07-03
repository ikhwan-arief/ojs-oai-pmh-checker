from src.endpoint_discovery import dedupe_preserve_order, discover_oai_endpoints, strip_known_ojs_page_paths


def test_root_journal_url_generates_domain_oai_candidate() -> None:
    candidates = discover_oai_endpoints("https://jurnal.example.ac.id")

    assert "https://jurnal.example.ac.id/oai" in candidates


def test_index_php_journal_generates_journal_oai_candidate() -> None:
    candidates = discover_oai_endpoints("https://jurnal.example.ac.id/index.php/jurnal")

    assert candidates[0] == "https://jurnal.example.ac.id/index.php/jurnal/oai"
    assert "https://jurnal.example.ac.id/index.php?journal=jurnal&page=oai" in candidates


def test_article_page_generates_root_journal_oai_candidate() -> None:
    candidates = discover_oai_endpoints("https://jurnal.example.ac.id/index.php/jurnal/article/view/123")

    assert candidates[0] == "https://jurnal.example.ac.id/index.php/jurnal/oai"


def test_strip_known_ojs_page_paths() -> None:
    assert strip_known_ojs_page_paths("/index.php/jurnal/archives") == "/index.php/jurnal"
    assert strip_known_ojs_page_paths("/index.php/jurnal/about") == "/index.php/jurnal"


def test_dedupe_preserve_order_removes_duplicate_candidates() -> None:
    result = dedupe_preserve_order(["https://example.org/oai", "https://example.org/oai/", "https://example.org/oai"])

    assert result == ["https://example.org/oai"]
