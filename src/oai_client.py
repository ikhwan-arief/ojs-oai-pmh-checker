from __future__ import annotations

import time
from urllib.parse import urljoin

import requests

from src.models import OAIResponse
from src.security import safe_join_query, validate_public_url


DEFAULT_USER_AGENT = (
    "OJS-OAI-PMH-Checker/1.0 "
    "(+https://github.com/ikhwan-arief/ojs-oai-pmh-checker)"
)

BLOCKED_CONTENT_TYPE_PARTS = (
    "application/pdf",
    "application/zip",
    "application/x-zip",
    "image/",
    "audio/",
    "video/",
)


class OAIClient:
    def __init__(self, timeout: int, max_bytes: int, user_agent: str = DEFAULT_USER_AGENT):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.request_log: list[OAIResponse] = []

    def request_oai(self, endpoint: str, params: dict[str, str | int | None]) -> OAIResponse:
        validate_public_url(endpoint)
        request_url = safe_join_query(endpoint, params)
        response = self._request_with_safe_redirects(endpoint, request_url)
        self.request_log.append(response)
        return response

    def identify(self, endpoint: str) -> OAIResponse:
        return self.request_oai(endpoint, {"verb": "Identify"})

    def list_metadata_formats(self, endpoint: str) -> OAIResponse:
        return self.request_oai(endpoint, {"verb": "ListMetadataFormats"})

    def list_records_page(
        self,
        endpoint: str,
        metadata_prefix: str,
        resumption_token: str = "",
    ) -> OAIResponse:
        if resumption_token:
            return self.request_oai(endpoint, {"verb": "ListRecords", "resumptionToken": resumption_token})
        return self.request_oai(endpoint, {"verb": "ListRecords", "metadataPrefix": metadata_prefix})

    def list_records(
        self,
        endpoint: str,
        metadata_prefix: str,
        max_records: int,
        follow_tokens: bool,
        max_token_pages: int,
    ) -> list[OAIResponse]:
        from src.parser import get_resumption_token, parse_oai_xml, parse_records

        responses: list[OAIResponse] = []
        seen_tokens: set[str] = set()
        token = ""
        pages = 0
        record_count = 0

        while True:
            response = self.list_records_page(endpoint, metadata_prefix, token)
            responses.append(response)
            pages += 1
            if not response.ok:
                break
            try:
                root = parse_oai_xml(response.content)
                token = get_resumption_token(root)
                record_count += len(parse_records(root))
            except Exception:
                break
            if not follow_tokens or not token:
                break
            if token in seen_tokens:
                responses[-1].error_type = "resumption_token_loop"
                responses[-1].error_message = "resumptionToken berulang terus."
                break
            seen_tokens.add(token)
            if pages >= max_token_pages or record_count >= max_records:
                break

        return responses

    def _request_with_safe_redirects(self, endpoint: str, request_url: str) -> OAIResponse:
        current_url = request_url
        started_at = time.monotonic()
        headers = {"User-Agent": self.user_agent, "Accept": "application/xml,text/xml,*/*;q=0.8"}

        try:
            for redirect_count in range(6):
                validate_public_url(current_url)
                response = requests.get(
                    current_url,
                    headers=headers,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=False,
                )

                if response.is_redirect or response.is_permanent_redirect:
                    if redirect_count >= 5:
                        return self._error_response(
                            request_url,
                            endpoint,
                            started_at,
                            "too_many_redirects",
                            "Redirect terlalu banyak. Ada kemungkinan konfigurasi URL atau HTTPS bermasalah.",
                            http_status=response.status_code,
                            final_url=current_url,
                            content_type=response.headers.get("Content-Type", ""),
                        )
                    location = response.headers.get("Location", "")
                    if not location:
                        return self._error_response(
                            request_url,
                            endpoint,
                            started_at,
                            "redirect_without_location",
                            "Server mengirim redirect tanpa alamat tujuan.",
                            http_status=response.status_code,
                            final_url=current_url,
                            content_type=response.headers.get("Content-Type", ""),
                        )
                    current_url = urljoin(current_url, location)
                    continue

                return self._read_response(request_url, endpoint, current_url, response, started_at)

            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "too_many_redirects",
                "Redirect terlalu banyak. Ada kemungkinan konfigurasi URL atau HTTPS bermasalah.",
                final_url=current_url,
            )
        except requests.exceptions.Timeout:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "timeout",
                "Request timeout. Server terlalu lama merespons.",
                final_url=current_url,
            )
        except requests.exceptions.SSLError:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "ssl_error",
                "SSL error. Sertifikat HTTPS bermasalah.",
                final_url=current_url,
            )
        except requests.exceptions.ConnectionError:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "connection_error",
                "Koneksi gagal. Server tidak dapat dihubungi.",
                final_url=current_url,
            )
        except ValueError as exc:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "url_validation_error",
                f"URL tidak aman atau tidak valid. {exc}",
                final_url=current_url,
            )
        except requests.RequestException as exc:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "request_error",
                _sanitize_error(str(exc)),
                final_url=current_url,
            )

    def _read_response(
        self,
        request_url: str,
        endpoint: str,
        current_url: str,
        response: requests.Response,
        started_at: float,
    ) -> OAIResponse:
        content_type = response.headers.get("Content-Type", "")
        content_length = response.headers.get("Content-Length")
        if _is_blocked_content_type(content_type):
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "blocked_content_type",
                "Respons tampak seperti file besar atau bukan XML OAI-PMH.",
                http_status=response.status_code,
                final_url=current_url,
                content_type=content_type,
            )
        if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
            return self._error_response(
                request_url,
                endpoint,
                started_at,
                "response_too_large",
                "Ukuran respons terlalu besar untuk diperiksa dengan aman.",
                http_status=response.status_code,
                final_url=current_url,
                content_type=content_type,
            )

        chunks: list[bytes] = []
        bytes_read = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            bytes_read += len(chunk)
            if bytes_read > self.max_bytes:
                return self._error_response(
                    request_url,
                    endpoint,
                    started_at,
                    "response_too_large",
                    "Ukuran respons terlalu besar untuk diperiksa dengan aman.",
                    http_status=response.status_code,
                    final_url=current_url,
                    content_type=content_type,
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        error_type, error_message = _http_error_message(response.status_code, content, content_type)
        ok = 200 <= response.status_code < 300 and not error_type
        return OAIResponse(
            request_url=request_url,
            endpoint_url=endpoint,
            ok=ok,
            http_status=response.status_code,
            content=content,
            content_type=content_type,
            response_time_seconds=round(time.monotonic() - started_at, 3),
            final_url=current_url,
            error_type=error_type,
            error_message=error_message,
            xml_snippet=_snippet(content),
        )

    def _error_response(
        self,
        request_url: str,
        endpoint: str,
        started_at: float,
        error_type: str,
        error_message: str,
        http_status: int | None = None,
        final_url: str = "",
        content_type: str = "",
    ) -> OAIResponse:
        return OAIResponse(
            request_url=request_url,
            endpoint_url=endpoint,
            ok=False,
            http_status=http_status,
            content_type=content_type,
            response_time_seconds=round(time.monotonic() - started_at, 3),
            final_url=final_url,
            error_type=error_type,
            error_message=error_message,
        )


def _is_blocked_content_type(content_type: str) -> bool:
    lower = content_type.lower()
    return any(part in lower for part in BLOCKED_CONTENT_TYPE_PARTS)


def _http_error_message(status_code: int, content: bytes, content_type: str) -> tuple[str, str]:
    if status_code == 403:
        return "http_403", "Server menolak akses ke endpoint OAI-PMH."
    if status_code >= 500:
        return "http_500", "Server mengalami error saat memproses endpoint OAI-PMH."
    if status_code >= 400:
        return "http_error", f"HTTP error {status_code}."
    if not content:
        return "empty_content", "Content kosong."
    lower_type = content_type.lower()
    trimmed = content[:300].lstrip().lower()
    if "html" in lower_type or trimmed.startswith(b"<!doctype html") or trimmed.startswith(b"<html"):
        return "html_response", "Respons HTML, bukan XML."
    return "", ""


def _sanitize_error(message: str) -> str:
    return " ".join(message.split())[:500]


def _snippet(content: bytes) -> str:
    return content[:3000].decode("utf-8", errors="replace")
