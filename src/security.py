from __future__ import annotations

import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
ALLOWED_SCHEMES = {"http", "https"}


class URLValidationError(ValueError):
    """Raised when a user-supplied URL is unsafe or invalid."""


def normalize_url(input_url: str) -> str:
    cleaned = (input_url or "").strip()
    if not cleaned:
        raise URLValidationError("URL wajib diisi.")

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError("Hanya URL dengan skema http atau https yang diizinkan.")
    if not parsed.hostname:
        raise URLValidationError("URL harus memiliki hostname.")

    normalized = parsed._replace(fragment="")
    return urlunparse(normalized)


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError("URL tidak aman atau tidak valid.")
    if not parsed.hostname:
        raise URLValidationError("URL harus memiliki hostname.")
    if is_private_or_local_hostname(parsed.hostname):
        raise URLValidationError("URL lokal atau private IP tidak diizinkan.")


def is_private_or_local_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower().rstrip(".")
    if normalized in BLOCKED_HOSTNAMES:
        return True

    try:
        return _is_blocked_ip(ipaddress.ip_address(normalized))
    except ValueError:
        pass

    try:
        resolved = socket.getaddrinfo(normalized, None)
    except socket.gaierror:
        return False

    for result in resolved:
        ip_text = result[4][0]
        try:
            if _is_blocked_ip(ipaddress.ip_address(ip_text)):
                return True
        except ValueError:
            continue
    return False


def safe_join_query(url: str, params: dict[str, str | int | None]) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            continue
        existing[str(key)] = str(value)
    query = urlencode(existing)
    return urlunparse(parsed._replace(query=query))


def _is_blocked_ip(ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_multicast
        or ip_address.is_reserved
        or ip_address.is_unspecified
    )
