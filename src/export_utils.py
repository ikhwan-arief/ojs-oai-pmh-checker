from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any

import pandas as pd

from src.models import AuditResult, HarvestIssue, OAIRecord


def records_to_dataframe(records: list[OAIRecord]) -> pd.DataFrame:
    rows = []
    for index, record in enumerate(records, start=1):
        rows.append(
            {
                "No": index,
                "OAI Identifier": record.identifier,
                "Datestamp": record.datestamp,
                "Judul": record.title,
                "Penulis": record.creators,
                "Tanggal": record.date,
                "Publisher": record.publisher,
                "Bahasa": record.language,
                "Tipe": record.type,
                "Source": record.source,
                "Rights": record.rights,
                "SetSpec": "; ".join(record.set_specs),
            }
        )
    return pd.DataFrame(rows)


def issues_to_dataframe(issues: list[HarvestIssue]) -> pd.DataFrame:
    rows = []
    for issue in issues:
        rows.append(
            {
                "Prioritas": issue.priority,
                "Tingkat masalah": issue.severity,
                "Gejala": issue.symptom,
                "Dugaan penyebab": _join(issue.probable_causes),
                "Dampak bagi harvester": issue.impact_for_harvester,
                "Action untuk pengelola jurnal": _join(issue.action_for_journal_manager),
                "Action untuk tim IT": _join(issue.action_for_it_admin),
                "Cara validasi setelah perbaikan": _join(issue.validation_steps),
                "Penanggung jawab": issue.owner,
            }
        )
    return pd.DataFrame(rows)


def audit_to_json(audit_result: AuditResult) -> str:
    return json.dumps(_to_plain(audit_result), ensure_ascii=False, indent=2)


def records_to_csv_bytes(records: list[OAIRecord]) -> bytes:
    return _dataframe_to_csv_bytes(records_to_dataframe(records))


def issues_to_csv_bytes(issues: list[HarvestIssue]) -> bytes:
    return _dataframe_to_csv_bytes(issues_to_dataframe(issues))


def summary_to_markdown(audit_result: AuditResult) -> str:
    repository_name = audit_result.repository_info.repository_name if audit_result.repository_info else ""
    issue_counts = _issue_counts(audit_result.issues)
    return "\n".join(
        [
            "# Ringkasan Audit OAI-PMH",
            "",
            f"- URL input: {audit_result.input_url}",
            f"- URL normalisasi: {audit_result.normalized_url}",
            f"- Endpoint terpilih: {audit_result.selected_endpoint or '-'}",
            f"- Repository: {repository_name or '-'}",
            f"- Metadata prefix: {audit_result.metadata_prefix}",
            f"- Status: {audit_result.harvestability_status}",
            f"- Harvestability score: {audit_result.harvestability_score}/100",
            f"- Jumlah record: {len(audit_result.records)}",
            f"- Critical: {issue_counts['Critical']}",
            f"- High: {issue_counts['High']}",
            f"- Medium: {issue_counts['Medium']}",
            f"- Low: {issue_counts['Low']}",
            f"- Waktu pemeriksaan: {audit_result.checked_at}",
            "",
            "## Rekomendasi Utama",
            "",
            *[f"- [{issue.priority}] {issue.symptom}" for issue in audit_result.issues[:10]],
        ]
    )


def summary_to_txt(audit_result: AuditResult) -> str:
    markdown = summary_to_markdown(audit_result)
    return markdown.replace("# ", "").replace("## ", "")


def _dataframe_to_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return ("\ufeff" + dataframe.to_csv(index=False)).encode("utf-8")


def _join(items: list[str]) -> str:
    return "\n".join(items)


def _issue_counts(issues: list[HarvestIssue]) -> dict[str, int]:
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value
