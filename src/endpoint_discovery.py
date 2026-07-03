from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.security import normalize_url


KNOWN_OJS_PAGE_PARTS = {
    "about",
    "issue",
    "article",
    "archives",
    "announcement",
    "login",
    "user",
    "search",
}


def discover_oai_endpoints(input_url: str) -> list[str]:
    normalized_url = normalize_url(input_url)
    parsed = urlparse(normalized_url)
    candidates: list[str] = []

    if _looks_like_oai_endpoint(normalized_url):
        candidates.append(normalized_url)

    journal_root_path = strip_known_ojs_page_paths(parsed.path)
    journal_root_path = _strip_trailing_index(journal_root_path)
    if journal_root_path and journal_root_path != "/":
        candidates.append(_with_path(parsed, _append_oai(journal_root_path)))

    legacy_url = _legacy_ojs_url(parsed, journal_root_path)
    if legacy_url:
        candidates.append(legacy_url)

    if parsed.path.rstrip("/"):
        candidates.append(_with_path(parsed, _append_oai(parsed.path)))
        candidates.append(_with_path(parsed, _append_oai(parsed.path.rstrip("/"))))

    candidates.append(_with_path(parsed, "/oai"))
    return dedupe_preserve_order(candidates)


def strip_known_ojs_page_paths(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"

    lowered = [part.lower() for part in parts]
    for marker in KNOWN_OJS_PAGE_PARTS:
        if marker in lowered:
            index = lowered.index(marker)
            return "/" + "/".join(parts[:index])

    return "/" + "/".join(parts)


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.rstrip("/") if "?" not in item else item
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _looks_like_oai_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return "/oai" in parsed.path.lower() or query.get("page") == "oai" or "verb" in query


def _append_oai(path: str) -> str:
    clean = path.rstrip("/")
    if clean.lower().endswith("/oai"):
        return clean
    return f"{clean}/oai" if clean else "/oai"


def _with_path(parsed, path: str) -> str:
    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def _strip_trailing_index(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if parts and parts[-1].lower() == "index":
        parts = parts[:-1]
    return "/" + "/".join(parts) if parts else "/"


def _legacy_ojs_url(parsed, journal_root_path: str) -> str:
    parts = [part for part in journal_root_path.split("/") if part]
    if "index.php" in parts:
        index_position = parts.index("index.php")
        if len(parts) > index_position + 1:
            journal = parts[index_position + 1]
            query = urlencode({"journal": journal, "page": "oai"})
            return urlunparse(parsed._replace(path="/index.php", params="", query=query, fragment=""))
    if parts:
        journal = parts[-1]
        query = urlencode({"journal": journal, "page": "oai"})
        return urlunparse(parsed._replace(path="/index.php", params="", query=query, fragment=""))
    return ""
