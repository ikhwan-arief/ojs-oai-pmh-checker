from __future__ import annotations

from urllib.parse import urlparse

from src.models import AuditResult, HarvestIssue


def generate_recommendations(audit_result: AuditResult) -> list[HarvestIssue]:
    issues: list[HarvestIssue] = []
    for detector in (
        detect_endpoint_issues,
        detect_server_security_issues,
        detect_metadata_format_issues,
        detect_list_records_issues,
        detect_metadata_quality_issues,
    ):
        issues.extend(detector(audit_result))
    return _dedupe_and_sort(issues)


def detect_endpoint_issues(audit_result: AuditResult) -> list[HarvestIssue]:
    issues: list[HarvestIssue] = []
    if not audit_result.selected_endpoint:
        evidence = [f"{attempt.endpoint_url}: {attempt.reason}" for attempt in audit_result.endpoint_attempts]
        if audit_result.raw_errors:
            evidence.extend(audit_result.raw_errors)
        issues.append(
            _issue(
                "endpoint_not_found",
                "Endpoint",
                "Critical",
                "Endpoint OAI-PMH tidak menghasilkan Identify yang valid.",
                evidence,
                [
                    "OAI belum aktif.",
                    "Path jurnal salah.",
                    "Konfigurasi pretty URL atau routing OJS bermasalah.",
                    "Website bukan OJS atau memakai konfigurasi custom.",
                ],
                "Harvester tidak punya alamat valid untuk menarik metadata.",
                [
                    "Pastikan URL yang dimasukkan adalah URL jurnal, bukan URL portal induk.",
                    "Pastikan jurnal sudah memiliki issue dan artikel yang dipublikasikan.",
                    "Kirim contoh URL jurnal dan hasil error ke tim IT.",
                ],
                [
                    "Periksa konfigurasi OAI pada OJS.",
                    "Periksa config.inc.php.",
                    "Pastikan routing /oai dapat diakses publik.",
                    "Periksa rewrite URL, base_url, canonical URL, log PHP, dan log web server.",
                ],
                ["Buka /oai?verb=Identify.", "Pastikan HTTP 200 dan respons XML mengandung Identify."],
                "Pengelola Jurnal dan Tim IT",
                "P1",
            )
        )

    for response in audit_result.request_log:
        if response.error_type in {"html_response", "blocked_content_type"}:
            issues.append(
                _issue(
                    "non_xml_response",
                    "Respons",
                    "Critical",
                    "Endpoint mengembalikan HTML atau konten non-XML.",
                    [_response_evidence(response)],
                    [
                        "Endpoint salah.",
                        "Redirect ke halaman utama.",
                        "Routing OAI tidak aktif.",
                        "Server menyisipkan halaman proteksi.",
                    ],
                    "Harvester gagal parse metadata karena respons bukan XML OAI-PMH.",
                    [
                        "Pastikan URL yang digunakan bukan halaman artikel, about, archive, atau login.",
                        "Gunakan endpoint yang direkomendasikan aplikasi.",
                    ],
                    [
                        "Periksa redirect.",
                        "Periksa konfigurasi base_url.",
                        "Periksa aturan rewrite.",
                        "Pastikan endpoint OAI menghasilkan XML, bukan HTML.",
                    ],
                    ["Respons harus dimulai dengan XML OAI-PMH dan dapat diparse."],
                    "Tim IT atau Admin Server",
                    "P1",
                )
            )
        if response.error_type == "xml_parse_error":
            issues.append(_xml_invalid_issue([_response_evidence(response), *audit_result.raw_errors]))

    if audit_result.repository_info and audit_result.repository_info.base_url and audit_result.selected_endpoint:
        endpoint_host = urlparse(audit_result.selected_endpoint).hostname or ""
        base_host = urlparse(audit_result.repository_info.base_url).hostname or ""
        if endpoint_host and base_host and endpoint_host.lower() != base_host.lower():
            issues.append(
                _issue(
                    "identity_mismatch",
                    "Repository Identity",
                    "Medium",
                    "Identify valid tetapi baseURL berbeda dari endpoint yang diuji.",
                    [
                        f"Endpoint: {audit_result.selected_endpoint}",
                        f"baseURL: {audit_result.repository_info.base_url}",
                    ],
                    [
                        "Migrasi domain.",
                        "Konfigurasi base_url belum diperbarui.",
                        "repository_id tidak sesuai.",
                    ],
                    "Harvester bisa menyimpan sumber yang salah atau gagal deduplikasi.",
                    ["Pastikan domain resmi jurnal sudah benar.", "Laporkan inkonsistensi domain kepada tim IT."],
                    ["Periksa base_url.", "Periksa repository_id.", "Periksa redirect domain lama ke domain baru."],
                    ["Identify harus menampilkan baseURL yang konsisten dengan endpoint aktif."],
                    "Tim IT atau Admin Server",
                    "P2",
                )
            )
    return issues


def detect_metadata_format_issues(audit_result: AuditResult) -> list[HarvestIssue]:
    if not audit_result.selected_endpoint:
        return []
    if not any(fmt.metadata_prefix == "oai_dc" for fmt in audit_result.metadata_formats):
        return [
            _issue(
                "oai_dc_missing",
                "Metadata Format",
                "High",
                "ListMetadataFormats tidak menampilkan metadataPrefix oai_dc.",
                [f"Format ditemukan: {', '.join(fmt.metadata_prefix for fmt in audit_result.metadata_formats) or '-'}"],
                ["Metadata format tidak aktif.", "Plugin metadata bermasalah.", "OJS atau plugin tidak lengkap."],
                "Banyak harvester dasar tidak bisa menarik data.",
                ["Laporkan bahwa Dublin Core tidak tersedia."],
                [
                    "Periksa plugin metadata OAI.",
                    "Periksa instalasi dan konfigurasi OJS.",
                    "Pastikan format oai_dc aktif.",
                ],
                ["ListMetadataFormats harus menampilkan metadataPrefix oai_dc."],
                "Tim IT atau Admin Server",
                "P1",
            )
        ]
    return []


def detect_list_records_issues(audit_result: AuditResult) -> list[HarvestIssue]:
    issues: list[HarvestIssue] = []
    if audit_result.no_records_match:
        issues.append(
            _issue(
                "no_records_match",
                "ListRecords",
                "High",
                "OAI-PMH aktif, tetapi tidak ada record yang cocok untuk metadataPrefix ini.",
                [f"metadataPrefix: {audit_result.metadata_prefix}"],
                [
                    "Belum ada artikel yang published.",
                    "Issue belum published.",
                    "Artikel masih scheduled atau unpublished.",
                    "metadataPrefix salah.",
                    "Filter tanggal harvester tidak cocok.",
                    "Datestamp tidak sesuai.",
                ],
                "Harvester tidak menemukan publikasi.",
                [
                    "Pastikan issue sudah dipublikasikan.",
                    "Pastikan artikel sudah berstatus published.",
                    "Periksa tanggal publikasi artikel.",
                    "Periksa kelengkapan metadata artikel.",
                ],
                [
                    "Periksa apakah OAI membaca data artikel published.",
                    "Periksa database jika artikel published tidak muncul di OAI.",
                    "Periksa cache OJS.",
                ],
                ["ListRecords&metadataPrefix=oai_dc harus menampilkan minimal satu record."],
                "Pengelola Jurnal dan Tim IT",
                "P2",
            )
        )
    if audit_result.list_records_response and audit_result.list_records_response.error_type == "oai_error":
        issues.append(
            _issue(
                "list_records_failed",
                "ListRecords",
                "High",
                "ListRecords gagal diproses oleh endpoint OAI-PMH.",
                [_response_evidence(audit_result.list_records_response)],
                ["metadataPrefix tidak valid.", "Query OAI bermasalah.", "Plugin OAI gagal memproses daftar record."],
                "Harvester gagal mengambil daftar publikasi.",
                ["Coba metadataPrefix yang tersedia dari tab Metadata Format."],
                ["Periksa log OJS dan plugin OAI untuk request ListRecords."],
                ["ListRecords harus menghasilkan XML valid berisi record atau noRecordsMatch."],
                "Pengelola Jurnal dan Tim IT",
                "P2",
            )
        )
    if audit_result.token_error:
        issues.append(
            _issue(
                "resumption_token_problem",
                "Resumption Token",
                "High",
                audit_result.token_error,
                [audit_result.token_error],
                [
                    "Bug OJS atau plugin.",
                    "Cache bermasalah.",
                    "Session atau token handling bermasalah.",
                    "Konfigurasi oai_max_records tidak stabil.",
                ],
                "Harvester hanya menarik sebagian publikasi.",
                [
                    "Cocokkan jumlah artikel yang tampil di OJS dengan jumlah record OAI.",
                    "Laporkan perbedaan jumlah record kepada tim IT.",
                ],
                [
                    "Periksa bug versi OJS.",
                    "Periksa cache.",
                    "Periksa konfigurasi oai_max_records.",
                    "Pertimbangkan update OJS jika versi lama bermasalah.",
                ],
                ["Harvest dengan resumptionToken harus berlanjut sampai token habis."],
                "Tim IT atau Admin Server",
                "P2",
            )
        )
    if audit_result.token_truncated:
        issues.append(
            _issue(
                "records_truncated",
                "Resumption Token",
                "Low",
                "Record ditampilkan sebagian karena batas aplikasi.",
                ["Batas max record atau halaman token tercapai."],
                ["Jumlah record lebih banyak daripada batas pemeriksaan aplikasi."],
                "Harvester penuh mungkin masih bisa melanjutkan jika resumptionToken sehat.",
                ["Gunakan batas record lebih tinggi jika perlu audit lebih banyak publikasi."],
                ["Pastikan resumptionToken stabil untuk harvest penuh."],
                ["Harvest harus selesai sampai resumptionToken kosong."],
                "Pengelola Jurnal dan Tim IT",
                "P3",
            )
        )
    return issues


def detect_metadata_quality_issues(audit_result: AuditResult) -> list[HarvestIssue]:
    issues: list[HarvestIssue] = []
    diagnostic = audit_result.diagnostic_result
    if not audit_result.records:
        return issues

    if diagnostic.completeness_percent < 80:
        issues.append(
            _issue(
                "metadata_incomplete",
                "Kualitas Metadata",
                "Medium",
                "Banyak metadata utama kosong.",
                [f"Kelengkapan metadata: {diagnostic.completeness_percent}%"],
                [
                    "Metadata artikel tidak lengkap di OJS.",
                    "Proses copyediting/layout tidak mengisi field dengan benar.",
                    "Data lama hasil migrasi tidak lengkap.",
                ],
                "Portal indeks bisa menampilkan artikel secara salah atau tidak lengkap.",
                [
                    "Lengkapi metadata artikel satu per satu.",
                    "Prioritaskan title, author, affiliation, abstract, keyword, date, DOI, pages, language.",
                    "Periksa issue terbaru dan dua issue terakhir lebih dahulu.",
                ],
                [
                    "Jika data lama hasil migrasi kosong massal, bantu ekspor dan audit database.",
                    "Hindari update langsung database tanpa backup.",
                ],
                ["Jalankan ulang ListRecords dan pastikan field utama terisi."],
                "Pengelola Jurnal",
                "P3",
            )
        )
    if diagnostic.duplicate_identifiers:
        issues.append(
            _issue(
                "duplicate_identifier",
                "Kualitas Metadata",
                "High",
                "Ada OAI identifier sama pada lebih dari satu record.",
                diagnostic.duplicate_identifiers,
                ["Migrasi data bermasalah.", "Konfigurasi repository_id berubah.", "Data artikel duplikat."],
                "Harvester bisa menimpa, mengabaikan, atau salah menduplikasi record.",
                ["Periksa apakah ada artikel ganda.", "Periksa histori migrasi atau perubahan domain."],
                [
                    "Periksa repository_id.",
                    "Periksa struktur identifier OAI.",
                    "Periksa database untuk duplikasi submission atau publication.",
                ],
                ["Semua OAI identifier harus unik."],
                "Pengelola Jurnal dan Tim IT",
                "P2",
            )
        )
    if diagnostic.deleted_records:
        issues.append(
            _issue(
                "deleted_records",
                "Kualitas Metadata",
                "Medium",
                "Banyak header record memiliki status deleted.",
                [f"Record deleted: {diagnostic.deleted_records}"],
                ["Artikel pernah dihapus.", "Data lama atau hasil migrasi.", "Penghapusan tidak sengaja."],
                "Harvester bisa menghapus atau mengabaikan record tersebut.",
                [
                    "Periksa apakah artikel memang ditarik, dihapus, atau dipindahkan.",
                    "Jangan menghapus artikel published tanpa kebijakan editorial yang jelas.",
                ],
                ["Periksa apakah status deleted berasal dari data valid atau error migrasi."],
                ["Record artikel aktif tidak boleh berstatus deleted."],
                "Pengelola Jurnal dan Tim IT",
                "P2",
            )
        )
    if any("date bukan format tanggal yang wajar" in item["problems"] for item in diagnostic.problem_records):
        issues.append(
            _issue(
                "unreasonable_dates",
                "Kualitas Metadata",
                "Medium",
                "Datestamp atau date tidak wajar.",
                ["Sebagian record memiliki tanggal kosong atau tidak wajar."],
                [
                    "Tanggal publikasi tidak diisi.",
                    "Migrasi data mengubah tanggal.",
                    "Timezone atau format tanggal bermasalah.",
                ],
                "Harvester incremental bisa melewatkan artikel baru.",
                ["Periksa tanggal publikasi artikel dan issue.", "Pastikan artikel baru punya tanggal publikasi benar."],
                ["Periksa date_published, last_modified, datestamp OAI, dan timezone server."],
                ["ListRecords dengan parameter from harus menampilkan artikel baru sesuai tanggal."],
                "Pengelola Jurnal dan Tim IT",
                "P2",
            )
        )
    return issues


def detect_server_security_issues(audit_result: AuditResult) -> list[HarvestIssue]:
    issues: list[HarvestIssue] = []
    responses = audit_result.request_log
    for response in responses:
        if response.error_type == "http_403":
            issues.append(
                _issue(
                    "http_403_forbidden",
                    "Server",
                    "Critical",
                    "Endpoint mengembalikan 403 Forbidden.",
                    [_response_evidence(response)],
                    [
                        "Firewall, WAF, Cloudflare, ModSecurity, atau rate limit memblokir request.",
                        "User-Agent tertentu diblokir.",
                        "Akses ke /oai dibatasi.",
                    ],
                    "Harvester ditolak server.",
                    [
                        "Laporkan ke tim IT bahwa endpoint OAI ditolak publik.",
                        "Berikan URL endpoint dan waktu pengecekan.",
                    ],
                    [
                        "Periksa firewall, WAF, ModSecurity, Cloudflare, atau security plugin.",
                        "Izinkan akses publik ke endpoint OAI.",
                        "Pastikan request GET ke /oai tidak diblokir.",
                        "Pertimbangkan whitelist harvester resmi jika tersedia.",
                    ],
                    ["Request /oai?verb=Identify harus menghasilkan HTTP 200 dan XML valid."],
                    "Tim IT atau Admin Server",
                    "P1",
                )
            )
        if response.error_type == "http_500":
            issues.append(
                _issue(
                    "http_500_server_error",
                    "Server",
                    "Critical",
                    "Endpoint mengembalikan 500 Internal Server Error.",
                    [_response_evidence(response)],
                    [
                        "Error PHP.",
                        "Plugin OJS bermasalah.",
                        "Database error.",
                        "Konfigurasi OJS rusak.",
                        "Versi PHP tidak sesuai.",
                    ],
                    "Harvester gagal total.",
                    ["Jangan hanya mengulang harvest.", "Laporkan sebagai error server kepada tim IT."],
                    [
                        "Periksa error_log PHP.",
                        "Periksa log web server.",
                        "Periksa kompatibilitas versi OJS, PHP, dan plugin.",
                        "Nonaktifkan plugin bermasalah jika terbukti menyebabkan error.",
                        "Periksa permission folder cache dan files.",
                    ],
                    ["Identify, ListMetadataFormats, dan ListRecords harus bisa diakses tanpa error 500."],
                    "Tim IT atau Admin Server",
                    "P1",
                )
            )
        if response.error_type == "timeout":
            issues.append(
                _issue(
                    "timeout_or_slow",
                    "Server",
                    "High",
                    "ListRecords timeout atau server sangat lambat.",
                    [_response_evidence(response)],
                    [
                        "Terlalu banyak record dalam satu response.",
                        "oai_max_records terlalu besar.",
                        "Server lambat.",
                        "Query database lambat.",
                        "Resource hosting terbatas.",
                    ],
                    "Harvester gagal atau hanya menarik sebagian data.",
                    [
                        "Laporkan endpoint lambat kepada tim IT.",
                        "Jangan mengubah metadata secara massal saat server berat.",
                    ],
                    [
                        "Turunkan oai_max_records.",
                        "Periksa performa database.",
                        "Periksa cache OJS.",
                        "Periksa memory_limit dan max_execution_time.",
                        "Periksa beban server.",
                    ],
                    [
                        "ListRecords harus merespons dalam waktu wajar.",
                        "resumptionToken harus muncul jika data dibagi beberapa halaman.",
                    ],
                    "Tim IT atau Admin Server",
                    "P2",
                )
            )
        if response.error_type == "ssl_error":
            issues.append(
                _issue(
                    "ssl_problem",
                    "Server",
                    "Critical",
                    "SSL atau HTTPS bermasalah.",
                    [_response_evidence(response)],
                    ["Sertifikat kedaluwarsa.", "Chain certificate tidak lengkap.", "Redirect HTTPS salah."],
                    "Harvester gagal koneksi.",
                    ["Laporkan error sertifikat kepada tim IT."],
                    ["Perbarui SSL certificate.", "Periksa chain certificate.", "Periksa redirect HTTP ke HTTPS."],
                    ["Endpoint bisa diakses via HTTPS tanpa warning sertifikat."],
                    "Tim IT atau Admin Server",
                    "P1",
                )
            )
    return issues


def _xml_invalid_issue(evidence: list[str]) -> HarvestIssue:
    return _issue(
        "invalid_xml",
        "Respons",
        "Critical",
        "Respons XML tidak valid.",
        evidence,
        [
            "Warning atau notice PHP tampil di output.",
            "Metadata artikel mengandung karakter ilegal XML.",
            "Encoding tidak UTF-8.",
            "Plugin atau tema menyisipkan output tambahan.",
        ],
        "Harvester gagal membaca record.",
        [
            "Periksa metadata artikel terbaru, terutama judul, abstrak, keyword, dan nama penulis.",
            "Hindari karakter hasil copy-paste yang rusak.",
            "Perbaiki metadata yang mengandung simbol aneh.",
        ],
        [
            "Matikan display_errors di production.",
            "Simpan error ke log, bukan ke output.",
            "Periksa encoding database dan output.",
            "Periksa plugin yang menyisipkan output.",
        ],
        ["XML harus valid saat diuji dengan parser XML."],
        "Pengelola Jurnal dan Tim IT",
        "P1",
    )


def _issue(
    issue_id: str,
    category: str,
    severity: str,
    symptom: str,
    technical_evidence: list[str],
    probable_causes: list[str],
    impact_for_harvester: str,
    action_for_journal_manager: list[str],
    action_for_it_admin: list[str],
    validation_steps: list[str],
    owner: str,
    priority: str,
) -> HarvestIssue:
    return HarvestIssue(
        issue_id=issue_id,
        category=category,
        severity=severity,
        symptom=symptom,
        technical_evidence=technical_evidence,
        probable_causes=probable_causes,
        impact_for_harvester=impact_for_harvester,
        action_for_journal_manager=action_for_journal_manager,
        action_for_it_admin=action_for_it_admin,
        validation_steps=validation_steps,
        owner=owner,
        priority=priority,
    )


def _response_evidence(response) -> str:
    status = response.http_status if response.http_status is not None else "-"
    return f"{response.request_url} | HTTP {status} | {response.error_type or response.oai_error_code}: {response.error_message or response.oai_error_message}"


def _dedupe_and_sort(issues: list[HarvestIssue]) -> list[HarvestIssue]:
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    unique: dict[str, HarvestIssue] = {}
    for issue in issues:
        unique.setdefault(issue.issue_id, issue)
    return sorted(
        unique.values(),
        key=lambda issue: (
            priority_order.get(issue.priority.split(":", 1)[0], 9),
            severity_order.get(issue.severity, 9),
            issue.issue_id,
        ),
    )
