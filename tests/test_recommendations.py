from src.models import AuditResult, DiagnosticResult, OAIRecord, OAIResponse
from src.recommendations import generate_recommendations


def test_http_403_generates_it_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="")
    audit.request_log.append(
        OAIResponse(
            request_url="https://example.org/oai?verb=Identify",
            endpoint_url="https://example.org/oai",
            ok=False,
            http_status=403,
            error_type="http_403",
            error_message="Server menolak akses ke endpoint OAI-PMH.",
        )
    )

    issue_ids = {issue.issue_id for issue in generate_recommendations(audit)}

    assert "http_403_forbidden" in issue_ids


def test_http_500_generates_log_server_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="")
    audit.request_log.append(
        OAIResponse(
            request_url="https://example.org/oai?verb=Identify",
            endpoint_url="https://example.org/oai",
            ok=False,
            http_status=500,
            error_type="http_500",
            error_message="Server mengalami error saat memproses endpoint OAI-PMH.",
        )
    )

    issues = generate_recommendations(audit)

    assert any("Periksa error_log PHP." in issue.action_for_it_admin for issue in issues)


def test_xml_parse_error_generates_php_warning_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="")
    audit.raw_errors.append("not well-formed")
    audit.request_log.append(
        OAIResponse(
            request_url="https://example.org/oai?verb=Identify",
            endpoint_url="https://example.org/oai",
            ok=False,
            http_status=200,
            error_type="xml_parse_error",
            error_message="Respons XML tidak valid.",
        )
    )

    issues = generate_recommendations(audit)

    assert any("Matikan display_errors di production." in issue.action_for_it_admin for issue in issues)


def test_list_records_empty_generates_published_article_recommendation() -> None:
    audit = AuditResult(
        input_url="https://example.org",
        selected_endpoint="https://example.org/oai",
        no_records_match=True,
        metadata_prefix="oai_dc",
    )

    issues = generate_recommendations(audit)

    assert any("Pastikan artikel sudah berstatus published." in issue.action_for_journal_manager for issue in issues)


def test_metadata_empty_generates_journal_manager_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="https://example.org/oai")
    audit.records = [OAIRecord(identifier="oai:test:1")]
    audit.diagnostic_result = DiagnosticResult(total_records=1, completeness_percent=10)

    issues = generate_recommendations(audit)

    assert any(issue.issue_id == "metadata_incomplete" for issue in issues)


def test_duplicate_identifier_generates_migration_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="https://example.org/oai")
    audit.records = [OAIRecord(identifier="oai:test:1"), OAIRecord(identifier="oai:test:1")]
    audit.diagnostic_result = DiagnosticResult(
        total_records=2,
        completeness_percent=90,
        duplicate_identifiers=["oai:test:1"],
    )

    issues = generate_recommendations(audit)

    assert any(issue.issue_id == "duplicate_identifier" for issue in issues)


def test_timeout_generates_oai_max_records_recommendation() -> None:
    audit = AuditResult(input_url="https://example.org", selected_endpoint="https://example.org/oai")
    audit.request_log.append(
        OAIResponse(
            request_url="https://example.org/oai?verb=ListRecords&metadataPrefix=oai_dc",
            endpoint_url="https://example.org/oai",
            ok=False,
            error_type="timeout",
            error_message="Request timeout. Server terlalu lama merespons.",
        )
    )

    issues = generate_recommendations(audit)

    assert any("Turunkan oai_max_records." in issue.action_for_it_admin for issue in issues)
