from src.diagnostics import classify_harvestability, compute_harvestability_score, diagnose_records
from src.models import AuditResult, HarvestIssue, MetadataFormat, OAIRecord, OAIResponse


def test_diagnose_records_detects_empty_metadata_duplicate_identifier_and_deleted() -> None:
    records = [
        OAIRecord(identifier="oai:test:1", title="", creators="", date="", description="", deleted=False),
        OAIRecord(identifier="oai:test:1", title="A", creators="B", date="not a date", deleted=True),
    ]

    diagnostic = diagnose_records(records)

    assert diagnostic.total_records == 2
    assert diagnostic.deleted_records == 1
    assert diagnostic.duplicate_identifiers == ["oai:test:1"]
    assert any("identifier duplikat" in item["problems"] for item in diagnostic.problem_records)
    assert any("status deleted" in item["problems"] for item in diagnostic.problem_records)


def test_compute_harvestability_score_for_healthy_audit() -> None:
    audit = AuditResult(
        input_url="https://example.org",
        selected_endpoint="https://example.org/oai",
        identify_response=OAIResponse(
            request_url="https://example.org/oai?verb=Identify",
            endpoint_url="https://example.org/oai",
            ok=True,
            http_status=200,
        ),
        metadata_formats=[MetadataFormat(metadata_prefix="oai_dc")],
        records=[OAIRecord(identifier="oai:test:1", title="Title", creators="Author")],
        list_records_succeeded=True,
    )
    audit.diagnostic_result.completeness_percent = 85

    assert compute_harvestability_score(audit) == 100


def test_classify_harvestability_with_critical_issue_low_score() -> None:
    issues = [
        HarvestIssue(
            issue_id="endpoint_not_found",
            category="Endpoint",
            severity="Critical",
            symptom="Endpoint tidak valid.",
        )
    ]

    assert classify_harvestability(30, issues) == "Kemungkinan besar gagal di-harvest"
