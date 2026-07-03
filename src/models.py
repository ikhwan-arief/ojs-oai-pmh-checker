from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EndpointAttempt:
    endpoint_url: str
    status: str
    reason: str = ""
    http_status: int | None = None
    response_time_seconds: float | None = None
    content_type: str = ""
    selected: bool = False
    error_type: str = ""
    final_url: str = ""
    request_url: str = ""


@dataclass
class OAIResponse:
    request_url: str
    endpoint_url: str
    ok: bool
    http_status: int | None = None
    content: bytes = b""
    content_type: str = ""
    response_time_seconds: float | None = None
    final_url: str = ""
    error_type: str = ""
    error_message: str = ""
    oai_error_code: str = ""
    oai_error_message: str = ""
    xml_snippet: str = ""


@dataclass
class RepositoryInfo:
    repository_name: str = ""
    base_url: str = ""
    protocol_version: str = ""
    admin_emails: list[str] = field(default_factory=list)
    earliest_datestamp: str = ""
    deleted_record: str = ""
    granularity: str = ""


@dataclass
class MetadataFormat:
    metadata_prefix: str = ""
    schema: str = ""
    metadata_namespace: str = ""


@dataclass
class OAIRecord:
    identifier: str = ""
    datestamp: str = ""
    set_specs: list[str] = field(default_factory=list)
    title: str = ""
    creators: str = ""
    subjects: str = ""
    description: str = ""
    publisher: str = ""
    date: str = ""
    type: str = ""
    format: str = ""
    source: str = ""
    language: str = ""
    relation: str = ""
    coverage: str = ""
    rights: str = ""
    deleted: bool = False


@dataclass
class DiagnosticResult:
    total_records: int = 0
    active_records: int = 0
    deleted_records: int = 0
    with_title: int = 0
    with_creator: int = 0
    with_datestamp: int = 0
    with_date: int = 0
    with_identifier: int = 0
    with_description: int = 0
    with_publisher: int = 0
    with_language: int = 0
    completeness_percent: float = 0.0
    problem_records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_identifiers: list[str] = field(default_factory=list)
    status: str = "Bermasalah"


@dataclass
class HarvestIssue:
    issue_id: str
    category: str
    severity: str
    symptom: str
    technical_evidence: list[str] = field(default_factory=list)
    probable_causes: list[str] = field(default_factory=list)
    impact_for_harvester: str = ""
    action_for_journal_manager: list[str] = field(default_factory=list)
    action_for_it_admin: list[str] = field(default_factory=list)
    validation_steps: list[str] = field(default_factory=list)
    owner: str = "Pengelola Jurnal dan Tim IT"
    priority: str = "P3"


@dataclass
class AppSettings:
    max_records: int = 50
    timeout: int = 15
    metadata_prefix: str = "oai_dc"
    auto_discover: bool = True
    follow_resumption_token: bool = True
    max_token_pages: int = 5
    show_technical_detail: bool = False
    max_bytes: int = 5_000_000


@dataclass
class AuditResult:
    input_url: str
    normalized_url: str = ""
    selected_endpoint: str = ""
    metadata_prefix: str = "oai_dc"
    endpoint_attempts: list[EndpointAttempt] = field(default_factory=list)
    identify_response: OAIResponse | None = None
    metadata_formats_response: OAIResponse | None = None
    list_records_response: OAIResponse | None = None
    repository_info: RepositoryInfo | None = None
    metadata_formats: list[MetadataFormat] = field(default_factory=list)
    records: list[OAIRecord] = field(default_factory=list)
    diagnostic_result: DiagnosticResult = field(default_factory=DiagnosticResult)
    issues: list[HarvestIssue] = field(default_factory=list)
    harvestability_score: int = 0
    harvestability_status: str = "Kemungkinan besar gagal di-harvest"
    checked_at: str = ""
    request_log: list[OAIResponse] = field(default_factory=list)
    raw_errors: list[str] = field(default_factory=list)
    no_records_match: bool = False
    list_records_succeeded: bool = False
    token_truncated: bool = False
    token_error: str = ""
