from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import re
from xml.etree.ElementTree import ParseError

from src.endpoint_discovery import discover_oai_endpoints
from src.models import (
    AppSettings,
    AuditResult,
    DiagnosticResult,
    EndpointAttempt,
    HarvestIssue,
    OAIRecord,
)
from src.oai_client import OAIClient
from src.parser import (
    get_oai_error,
    get_resumption_token,
    has_identify,
    is_oai_pmh_root,
    parse_identify,
    parse_metadata_formats,
    parse_oai_xml,
    parse_records,
)
from src.security import normalize_url, validate_public_url


def audit_url(input_url: str, settings: AppSettings) -> AuditResult:
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        normalized_url = normalize_url(input_url)
        validate_public_url(normalized_url)
    except ValueError as exc:
        audit = AuditResult(input_url=input_url, checked_at=checked_at)
        audit.raw_errors.append(f"URL tidak aman atau tidak valid. {exc}")
        from src.recommendations import generate_recommendations

        audit.issues = generate_recommendations(audit)
        audit.harvestability_score = compute_harvestability_score(audit)
        audit.harvestability_status = classify_harvestability(audit.harvestability_score, audit.issues)
        return audit

    audit = AuditResult(
        input_url=input_url,
        normalized_url=normalized_url,
        metadata_prefix=settings.metadata_prefix,
        checked_at=checked_at,
    )

    endpoints = discover_oai_endpoints(normalized_url) if settings.auto_discover else [normalized_url]
    client = OAIClient(timeout=settings.timeout, max_bytes=settings.max_bytes)

    for endpoint in endpoints:
        response = client.identify(endpoint)
        attempt = _attempt_from_response(endpoint, response)
        audit.request_log.append(response)
        if response.ok:
            try:
                root = parse_oai_xml(response.content)
                error = get_oai_error(root)
                if not is_oai_pmh_root(root):
                    attempt.status = "Gagal"
                    attempt.reason = "Root XML bukan OAI-PMH."
                elif not has_identify(root):
                    attempt.status = "Gagal"
                    attempt.reason = "Respons OAI-PMH tidak mengandung Identify."
                elif error:
                    attempt.status = "Gagal"
                    attempt.reason = f"Endpoint OAI mengembalikan error {error[0]}: {error[1]}"
                    response.oai_error_code, response.oai_error_message = error
                else:
                    attempt.status = "Valid"
                    attempt.reason = "Identify valid."
                    attempt.selected = True
                    audit.selected_endpoint = endpoint
                    audit.identify_response = response
                    audit.repository_info = parse_identify(root)
                    audit.endpoint_attempts.append(attempt)
                    break
            except ParseError as exc:
                response.error_type = "xml_parse_error"
                response.error_message = "Respons XML tidak valid. Harvester kemungkinan gagal membaca data."
                audit.raw_errors.append(_sanitize_error(str(exc)))
                attempt.status = "Gagal"
                attempt.reason = response.error_message
            except Exception as exc:
                response.error_type = "xml_parse_error"
                response.error_message = "Respons XML tidak valid. Harvester kemungkinan gagal membaca data."
                audit.raw_errors.append(_sanitize_error(str(exc)))
                attempt.status = "Gagal"
                attempt.reason = response.error_message
        audit.endpoint_attempts.append(attempt)

    if audit.selected_endpoint:
        _check_metadata_formats(audit, client)
        _check_list_records(audit, client, settings)

    audit.diagnostic_result = diagnose_records(audit.records)
    from src.recommendations import generate_recommendations

    audit.issues = generate_recommendations(audit)
    audit.harvestability_score = compute_harvestability_score(audit)
    audit.harvestability_status = classify_harvestability(audit.harvestability_score, audit.issues)
    return audit


def diagnose_records(records: list[OAIRecord]) -> DiagnosticResult:
    result = DiagnosticResult(total_records=len(records))
    result.deleted_records = sum(1 for record in records if record.deleted)
    result.active_records = result.total_records - result.deleted_records
    result.with_title = sum(1 for record in records if record.title)
    result.with_creator = sum(1 for record in records if record.creators)
    result.with_datestamp = sum(1 for record in records if record.datestamp)
    result.with_date = sum(1 for record in records if record.date)
    result.with_identifier = sum(1 for record in records if record.identifier)
    result.with_description = sum(1 for record in records if record.description)
    result.with_publisher = sum(1 for record in records if record.publisher)
    result.with_language = sum(1 for record in records if record.language)

    identifiers = [record.identifier for record in records if record.identifier]
    counts = Counter(identifiers)
    result.duplicate_identifiers = sorted(identifier for identifier, count in counts.items() if count > 1)

    completeness_fields = (
        "title",
        "creators",
        "datestamp",
        "date",
        "identifier",
        "description",
        "publisher",
        "language",
    )
    possible_fields = max(1, result.total_records * len(completeness_fields))
    filled_fields = sum(1 for record in records for field in completeness_fields if getattr(record, field))
    result.completeness_percent = round((filled_fields / possible_fields) * 100, 1) if records else 0.0

    for record in records:
        problems = _record_problems(record, result.duplicate_identifiers)
        if problems:
            result.problem_records.append(
                {
                    "identifier": record.identifier,
                    "title": record.title,
                    "datestamp": record.datestamp,
                    "problems": "; ".join(problems),
                }
            )

    if result.total_records and result.completeness_percent >= 80 and not result.duplicate_identifiers:
        result.status = "Baik"
    elif result.total_records:
        result.status = "Perlu perhatian"
    else:
        result.status = "Perlu perhatian"
    return result


def compute_harvestability_score(audit_result: AuditResult) -> int:
    score = 0
    if audit_result.identify_response and audit_result.identify_response.ok and audit_result.selected_endpoint:
        score += 25
    if any(fmt.metadata_prefix == "oai_dc" for fmt in audit_result.metadata_formats):
        score += 15
    if audit_result.list_records_succeeded:
        score += 25
    if audit_result.records:
        score += 15
    if audit_result.diagnostic_result.completeness_percent >= 80:
        score += 10
    if not audit_result.token_error:
        score += 5
    if not any(issue.severity == "Critical" for issue in audit_result.issues):
        score += 5
    return min(100, score)


def classify_harvestability(score: int, issues: list[HarvestIssue]) -> str:
    if any(issue.severity == "Critical" for issue in issues) and score < 65:
        return "Kemungkinan besar gagal di-harvest"
    if score >= 85:
        return "Siap di-harvest"
    if score >= 65:
        return "Bisa di-harvest, tetapi perlu perbaikan"
    if score >= 40:
        return "Berisiko gagal atau hanya tertarik sebagian"
    return "Kemungkinan besar gagal di-harvest"


def _check_metadata_formats(audit: AuditResult, client: OAIClient) -> None:
    response = client.list_metadata_formats(audit.selected_endpoint)
    audit.metadata_formats_response = response
    audit.request_log.append(response)
    if not response.ok:
        return
    try:
        root = parse_oai_xml(response.content)
        error = get_oai_error(root)
        if error:
            response.oai_error_code, response.oai_error_message = error
            response.ok = False
            response.error_type = "oai_error"
            response.error_message = f"OAI error {error[0]}: {error[1]}"
            return
        audit.metadata_formats = parse_metadata_formats(root)
    except Exception as exc:
        response.ok = False
        response.error_type = "xml_parse_error"
        response.error_message = "Respons XML tidak valid. Harvester kemungkinan gagal membaca data."
        audit.raw_errors.append(_sanitize_error(str(exc)))


def _check_list_records(audit: AuditResult, client: OAIClient, settings: AppSettings) -> None:
    responses = client.list_records(
        audit.selected_endpoint,
        settings.metadata_prefix,
        settings.max_records,
        settings.follow_resumption_token,
        settings.max_token_pages,
    )
    all_records: list[OAIRecord] = []
    seen_tokens: set[str] = set()

    for response in responses:
        audit.request_log.append(response)
        audit.list_records_response = response
        if response.error_type == "resumption_token_loop":
            audit.token_error = response.error_message
            break
        if not response.ok:
            continue
        try:
            root = parse_oai_xml(response.content)
            error = get_oai_error(root)
            if error:
                response.oai_error_code, response.oai_error_message = error
                if error[0] == "noRecordsMatch":
                    audit.no_records_match = True
                    audit.list_records_succeeded = True
                else:
                    response.ok = False
                    response.error_type = "oai_error"
                    response.error_message = f"OAI error {error[0]}: {error[1]}"
                continue
            page_records = parse_records(root)
            all_records.extend(page_records)
            audit.list_records_succeeded = True
            token = get_resumption_token(root)
            if token:
                if token in seen_tokens:
                    audit.token_error = "resumptionToken berulang terus."
                    break
                seen_tokens.add(token)
            if len(all_records) >= settings.max_records:
                audit.token_truncated = bool(token)
                break
        except Exception as exc:
            response.ok = False
            response.error_type = "xml_parse_error"
            response.error_message = "Respons XML tidak valid. Harvester kemungkinan gagal membaca data."
            audit.raw_errors.append(_sanitize_error(str(exc)))

    if len(responses) >= settings.max_token_pages and responses:
        try:
            root = parse_oai_xml(responses[-1].content)
            audit.token_truncated = bool(get_resumption_token(root))
        except Exception:
            pass
    audit.records = all_records[: settings.max_records]


def _attempt_from_response(endpoint: str, response) -> EndpointAttempt:
    status = "Gagal"
    reason = response.error_message or "Identify tidak valid."
    if response.ok:
        status = "Diuji"
        reason = "HTTP 200, menunggu validasi XML Identify."
    return EndpointAttempt(
        endpoint_url=endpoint,
        status=status,
        reason=reason,
        http_status=response.http_status,
        response_time_seconds=response.response_time_seconds,
        content_type=response.content_type,
        error_type=response.error_type,
        final_url=response.final_url,
        request_url=response.request_url,
    )


def _record_problems(record: OAIRecord, duplicate_identifiers: list[str]) -> list[str]:
    problems: list[str] = []
    if not record.title:
        problems.append("tanpa title")
    elif len(record.title.strip()) < 5:
        problems.append("title terlalu pendek")
    if not record.creators:
        problems.append("tanpa creator")
    elif len(record.creators.strip()) < 3:
        problems.append("creator terlalu pendek")
    if not record.date:
        problems.append("tanpa date")
    elif not _date_looks_reasonable(record.date):
        problems.append("date bukan format tanggal yang wajar")
    if not record.description:
        problems.append("tanpa description")
    if not record.datestamp:
        problems.append("datestamp kosong")
    if record.deleted:
        problems.append("status deleted")
    if record.identifier in duplicate_identifiers:
        problems.append("identifier duplikat")
    if record.language and not _language_looks_reasonable(record.language):
        problems.append("language tidak jelas")
    if record.relation and "doi" in record.relation.lower() and not _relation_has_valid_doi(record.relation):
        problems.append("DOI atau relation tampak tidak valid")
    return problems


def _date_looks_reasonable(value: str) -> bool:
    years = [int(match) for match in re.findall(r"\b(18\d{2}|19\d{2}|20\d{2}|2100)\b", value)]
    return bool(years)


def _language_looks_reasonable(value: str) -> bool:
    parts = [part.strip().lower() for part in re.split(r"[;|,]", value) if part.strip()]
    return all(re.fullmatch(r"[a-z]{2,3}(-[a-z]{2})?", part) for part in parts)


def _relation_has_valid_doi(value: str) -> bool:
    return bool(re.search(r"10\.\d{4,9}/\S+", value))


def _sanitize_error(message: str) -> str:
    return " ".join(message.split())[:500]
