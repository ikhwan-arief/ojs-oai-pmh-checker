import pytest

from src.security import URLValidationError, normalize_url, safe_join_query, validate_public_url


def test_normalize_url_adds_https_and_removes_fragment() -> None:
    assert normalize_url(" jurnal.example.ac.id/index.php/jurnal#about ") == (
        "https://jurnal.example.ac.id/index.php/jurnal"
    )


def test_localhost_url_is_rejected() -> None:
    with pytest.raises(URLValidationError):
        validate_public_url("https://localhost/oai")


def test_private_ip_url_is_rejected() -> None:
    with pytest.raises(URLValidationError):
        validate_public_url("https://192.168.1.10/oai")


def test_non_http_scheme_is_rejected() -> None:
    with pytest.raises(URLValidationError):
        normalize_url("file:///etc/passwd")


def test_safe_join_query_replaces_existing_verb() -> None:
    url = safe_join_query("https://example.org/oai?verb=Identify", {"verb": "ListRecords", "metadataPrefix": "oai_dc"})

    assert url == "https://example.org/oai?verb=ListRecords&metadataPrefix=oai_dc"
