from __future__ import annotations

import pandas as pd
import streamlit as st

from src.diagnostics import audit_url
from src.export_utils import (
    audit_to_json,
    issues_to_csv_bytes,
    issues_to_dataframe,
    records_to_csv_bytes,
    records_to_dataframe,
    summary_to_markdown,
    summary_to_txt,
)
from src.models import AppSettings, AuditResult


st.set_page_config(
    page_title="Validator OAI-PMH Jurnal OJS",
    layout="wide",
)


def main() -> None:
    _render_header()
    settings = _render_sidebar()
    submitted_url = _render_form()

    if submitted_url:
        with st.spinner("Memeriksa endpoint OAI-PMH dan metadata publik..."):
            try:
                audit = audit_url(submitted_url, settings)
            except Exception as exc:
                st.error("Terjadi error saat pemeriksaan. Coba ulangi atau aktifkan detail teknis.")
                if settings.show_technical_detail:
                    st.code(" ".join(str(exc).split())[:1000])
                return
        _render_results(audit, settings)


def _render_header() -> None:
    st.title("Validator OAI-PMH Jurnal OJS")
    st.write(
        "Masukkan URL website jurnal. Aplikasi akan mencoba menemukan endpoint OAI-PMH, "
        "memeriksa validitasnya, menampilkan metadata publikasi yang tersedia, dan memberi "
        "rekomendasi jika data tidak bisa ditarik oleh harvester."
    )
    st.info("Aplikasi ini hanya membaca metadata publik dari endpoint OAI-PMH. Tidak membutuhkan login ke OJS.")


def _render_sidebar() -> AppSettings:
    with st.sidebar:
        st.header("Panduan singkat")
        st.markdown(
            """
1. Masukkan URL halaman utama jurnal, contoh:
   `https://jurnal.example.ac.id/index.php/nama-jurnal`
2. URL boleh berupa endpoint lengkap, contoh:
   `https://jurnal.example.ac.id/index.php/nama-jurnal/oai`
3. Klik tombol **Periksa OAI-PMH**.
4. Lihat status, endpoint yang ditemukan, daftar publikasi, dan rekomendasi perbaikan.
"""
        )

        st.header("Pengaturan lanjutan")
        max_records = st.number_input("Jumlah record maksimal", min_value=10, max_value=500, value=50, step=10)
        timeout = st.number_input("Timeout request (detik)", min_value=5, max_value=60, value=15, step=5)
        metadata_prefix = st.text_input("Metadata prefix", value="oai_dc")
        auto_discover = st.checkbox("Coba beberapa kandidat endpoint otomatis", value=True)
        follow_tokens = st.checkbox("Ikuti resumptionToken", value=True)
        max_token_pages = st.number_input("Jumlah halaman resumptionToken maksimal", min_value=1, max_value=20, value=5)
        show_detail = st.checkbox("Tampilkan detail teknis", value=False)

    return AppSettings(
        max_records=int(max_records),
        timeout=int(timeout),
        metadata_prefix=metadata_prefix.strip() or "oai_dc",
        auto_discover=auto_discover,
        follow_resumption_token=follow_tokens,
        max_token_pages=int(max_token_pages),
        show_technical_detail=show_detail,
    )


def _render_form() -> str:
    with st.form("oai_check_form"):
        url = st.text_input(
            "URL website jurnal atau URL OAI-PMH",
            placeholder="https://jurnal.example.ac.id/index.php/nama-jurnal",
        )
        submitted = st.form_submit_button("Periksa OAI-PMH", type="primary")
    return url if submitted else ""


def _render_results(audit: AuditResult, settings: AppSettings) -> None:
    tabs = st.tabs(
        [
            "Ringkasan",
            "Endpoint yang Diuji",
            "Informasi Repository",
            "Metadata Format",
            "Publikasi yang Bisa Ditarik Harvester",
            "Kualitas Metadata",
            "Rekomendasi Action",
            "Detail Teknis",
        ]
    )

    with tabs[0]:
        _render_summary_tab(audit)
    with tabs[1]:
        _render_endpoint_tab(audit)
    with tabs[2]:
        _render_repository_tab(audit)
    with tabs[3]:
        _render_metadata_format_tab(audit)
    with tabs[4]:
        _render_records_tab(audit)
    with tabs[5]:
        _render_quality_tab(audit)
    with tabs[6]:
        _render_recommendations_tab(audit)
    with tabs[7]:
        if settings.show_technical_detail:
            _render_technical_tab(audit)
        else:
            st.info("Aktifkan checkbox **Tampilkan detail teknis** di sidebar untuk melihat request dan error teknis.")


def _render_summary_tab(audit: AuditResult) -> None:
    st.caption("Harvestability score adalah perkiraan kesiapan endpoint untuk dipanen oleh sistem pengindeks.")
    issue_counts = _issue_counts(audit)
    last_response = audit.request_log[-1] if audit.request_log else None

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status akhir", audit.harvestability_status)
    col2.metric("Harvestability score", f"{audit.harvestability_score}/100")
    col3.metric("Record ditemukan", len(audit.records))
    col4.metric("HTTP status terakhir", last_response.http_status if last_response else "-")

    st.write(f"**Endpoint OAI-PMH terpilih:** `{audit.selected_endpoint or '-'}`")
    st.write(f"**Metadata prefix dipakai:** `{audit.metadata_prefix}`")
    st.write(f"**Waktu pemeriksaan:** `{audit.checked_at}`")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Critical", issue_counts["Critical"])
    col_b.metric("High", issue_counts["High"])
    col_c.metric("Medium", issue_counts["Medium"])
    col_d.metric("Low", issue_counts["Low"])

    _render_downloads(audit)


def _render_endpoint_tab(audit: AuditResult) -> None:
    st.caption("Endpoint OAI-PMH adalah alamat yang dibaca harvester untuk mengambil metadata.")
    rows = [
        {
            "kandidat endpoint": attempt.endpoint_url,
            "status": attempt.status,
            "alasan": attempt.reason,
            "waktu respons": attempt.response_time_seconds,
            "HTTP status": attempt.http_status,
            "dipilih": "Ya" if attempt.selected else "Tidak",
        }
        for attempt in audit.endpoint_attempts
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_repository_tab(audit: AuditResult) -> None:
    info = audit.repository_info
    if not info:
        st.warning("Informasi repository belum tersedia karena Identify tidak valid.")
        return
    st.table(
        pd.DataFrame(
            [
                ("repositoryName", info.repository_name),
                ("baseURL", info.base_url),
                ("protocolVersion", info.protocol_version),
                ("adminEmail", "; ".join(info.admin_emails)),
                ("earliestDatestamp", info.earliest_datestamp),
                ("deletedRecord", info.deleted_record),
                ("granularity", info.granularity),
            ],
            columns=["Field", "Nilai"],
        )
    )


def _render_metadata_format_tab(audit: AuditResult) -> None:
    st.caption("metadataPrefix oai_dc adalah format Dublin Core yang paling umum dipakai harvester.")
    if not audit.metadata_formats:
        st.warning("Metadata format tidak tersedia atau request ListMetadataFormats gagal.")
        return
    has_oai_dc = any(item.metadata_prefix == "oai_dc" for item in audit.metadata_formats)
    if has_oai_dc:
        st.success("Format oai_dc tersedia.")
    else:
        st.warning("Format oai_dc tidak ditemukan. Beberapa harvester dasar mungkin tidak bisa menarik data.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "metadataPrefix": item.metadata_prefix,
                    "schema": item.schema,
                    "metadataNamespace": item.metadata_namespace,
                }
                for item in audit.metadata_formats
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_records_tab(audit: AuditResult) -> None:
    st.caption("Record adalah satu entri metadata publikasi yang bisa dibaca harvester.")
    if audit.no_records_match:
        st.warning("OAI-PMH aktif, tetapi tidak ada record yang cocok untuk metadataPrefix ini.")
    dataframe = records_to_dataframe(audit.records)
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def _render_quality_tab(audit: AuditResult) -> None:
    diagnostic = audit.diagnostic_result
    total = max(1, diagnostic.total_records)
    cols = st.columns(4)
    cols[0].metric("% record dengan judul", _percent(diagnostic.with_title, total))
    cols[1].metric("% record dengan penulis", _percent(diagnostic.with_creator, total))
    cols[2].metric("% record dengan tanggal", _percent(diagnostic.with_date, total))
    cols[3].metric("% record dengan deskripsi", _percent(diagnostic.with_description, total))

    cols = st.columns(4)
    cols[0].metric("% record dengan publisher", _percent(diagnostic.with_publisher, total))
    cols[1].metric("% record dengan bahasa", _percent(diagnostic.with_language, total))
    cols[2].metric("Identifier duplikat", len(diagnostic.duplicate_identifiers))
    cols[3].metric("Record deleted", diagnostic.deleted_records)

    if diagnostic.problem_records:
        st.subheader("Record bermasalah")
        st.dataframe(pd.DataFrame(diagnostic.problem_records), use_container_width=True, hide_index=True)
    else:
        st.success("Tidak ada masalah metadata utama pada record yang ditampilkan.")


def _render_recommendations_tab(audit: AuditResult) -> None:
    st.caption(
        "Rekomendasi action membedakan pekerjaan editorial dan pekerjaan server agar masalah bisa ditangani "
        "oleh pihak yang tepat."
    )
    dataframe = issues_to_dataframe(audit.issues)
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    manager_actions = _unique_actions(issue.action_for_journal_manager for issue in audit.issues)
    it_actions = _unique_actions(issue.action_for_it_admin for issue in audit.issues)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Yang perlu dilakukan pengelola jurnal")
        if manager_actions:
            for action in manager_actions:
                st.checkbox(action, value=False, key=f"manager-{action}", disabled=True)
        else:
            st.write("Tidak ada action editorial khusus dari hasil pemeriksaan ini.")
    with col2:
        st.subheader("Yang perlu dilakukan tim IT")
        if it_actions:
            for action in it_actions:
                st.checkbox(action, value=False, key=f"it-{action}", disabled=True)
        else:
            st.write("Tidak ada action server khusus dari hasil pemeriksaan ini.")


def _render_technical_tab(audit: AuditResult) -> None:
    st.caption("resumptionToken adalah token lanjutan jika daftar record terlalu panjang.")
    rows = [
        {
            "URL request": response.request_url,
            "HTTP status": response.http_status,
            "response time": response.response_time_seconds,
            "content type": response.content_type,
            "error": response.error_message or response.oai_error_message,
        }
        for response in audit.request_log
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for index, response in enumerate(audit.request_log, start=1):
        if response.xml_snippet:
            with st.expander(f"Potongan XML request {index}"):
                st.code(response.xml_snippet[:3000], language="xml")

    if audit.raw_errors:
        st.subheader("Error tersanitasi")
        for error in audit.raw_errors:
            st.code(error)


def _render_downloads(audit: AuditResult) -> None:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.download_button(
        "Download publikasi CSV",
        records_to_csv_bytes(audit.records),
        file_name="publikasi_oai_pmh.csv",
        mime="text/csv",
    )
    col2.download_button(
        "Download audit JSON",
        audit_to_json(audit),
        file_name="audit_oai_pmh.json",
        mime="application/json",
    )
    col3.download_button(
        "Download rekomendasi CSV",
        issues_to_csv_bytes(audit.issues),
        file_name="rekomendasi_oai_pmh.csv",
        mime="text/csv",
    )
    col4.download_button(
        "Download ringkasan Markdown",
        summary_to_markdown(audit),
        file_name="ringkasan_oai_pmh.md",
        mime="text/markdown",
    )
    col5.download_button(
        "Download laporan TXT",
        summary_to_txt(audit),
        file_name="laporan_oai_pmh.txt",
        mime="text/plain",
    )


def _issue_counts(audit: AuditResult) -> dict[str, int]:
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for issue in audit.issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def _percent(value: int, total: int) -> str:
    return f"{round((value / total) * 100, 1)}%"


def _unique_actions(groups) -> list[str]:
    seen: set[str] = set()
    actions: list[str] = []
    for group in groups:
        for action in group:
            if action in seen:
                continue
            seen.add(action)
            actions.append(action)
    return actions


if __name__ == "__main__":
    main()
