from __future__ import annotations

from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from src.models import MetadataFormat, OAIRecord, RepositoryInfo


OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"


def parse_oai_xml(xml_bytes: bytes) -> Element:
    return ElementTree.fromstring(xml_bytes)


def parse_identify(root: Element) -> RepositoryInfo:
    identify = _first_descendant(root, "Identify")
    if identify is None:
        return RepositoryInfo()

    return RepositoryInfo(
        repository_name=_first_text(identify, "repositoryName"),
        base_url=_first_text(identify, "baseURL"),
        protocol_version=_first_text(identify, "protocolVersion"),
        admin_emails=_all_text(identify, "adminEmail"),
        earliest_datestamp=_first_text(identify, "earliestDatestamp"),
        deleted_record=_first_text(identify, "deletedRecord"),
        granularity=_first_text(identify, "granularity"),
    )


def parse_metadata_formats(root: Element) -> list[MetadataFormat]:
    formats: list[MetadataFormat] = []
    for element in _descendants(root, "metadataFormat"):
        formats.append(
            MetadataFormat(
                metadata_prefix=_first_text(element, "metadataPrefix"),
                schema=_first_text(element, "schema"),
                metadata_namespace=_first_text(element, "metadataNamespace"),
            )
        )
    return formats


def parse_records(root: Element) -> list[OAIRecord]:
    records: list[OAIRecord] = []
    list_records = _first_descendant(root, "ListRecords")
    if list_records is None:
        return records

    for record_element in _children(list_records, "record"):
        header = _first_child(record_element, "header")
        metadata = _first_child(record_element, "metadata")
        deleted = header is not None and header.attrib.get("status", "").lower() == "deleted"
        set_specs = _all_text(header, "setSpec") if header is not None else []

        records.append(
            OAIRecord(
                identifier=_first_text(header, "identifier") if header is not None else "",
                datestamp=_first_text(header, "datestamp") if header is not None else "",
                set_specs=set_specs,
                title=_join_dc(metadata, "title", " | "),
                creators=_join_dc(metadata, "creator", "; "),
                subjects=_join_dc(metadata, "subject", "; "),
                description=_join_dc(metadata, "description", " | "),
                publisher=_join_dc(metadata, "publisher", " | "),
                date=_join_dc(metadata, "date", " | "),
                type=_join_dc(metadata, "type", " | "),
                format=_join_dc(metadata, "format", " | "),
                source=_join_dc(metadata, "source", " | "),
                language=_join_dc(metadata, "language", " | "),
                relation=_join_dc(metadata, "relation", " | "),
                coverage=_join_dc(metadata, "coverage", " | "),
                rights=_join_dc(metadata, "rights", " | "),
                deleted=deleted,
            )
        )
    return records


def extract_dc_values(metadata_element: Element | None, tag_name: str) -> list[str]:
    if metadata_element is None:
        return []
    values: list[str] = []
    for element in metadata_element.iter():
        if _local_name(element.tag) != tag_name:
            continue
        text = _clean_text(element.text)
        if text:
            values.append(text)
    return values


def get_oai_error(root: Element) -> tuple[str, str] | None:
    error_element = _first_descendant(root, "error")
    if error_element is None:
        return None
    return error_element.attrib.get("code", ""), _clean_text(error_element.text)


def get_resumption_token(root: Element) -> str:
    token = _first_descendant(root, "resumptionToken")
    if token is None:
        return ""
    return _clean_text(token.text)


def is_oai_pmh_root(root: Element) -> bool:
    return _local_name(root.tag) == "OAI-PMH"


def has_identify(root: Element) -> bool:
    return _first_descendant(root, "Identify") is not None


def _join_dc(metadata: Element | None, tag_name: str, separator: str) -> str:
    return separator.join(extract_dc_values(metadata, tag_name))


def _first_text(element: Element | None, tag_name: str) -> str:
    found = _first_child(element, tag_name) if element is not None else None
    return _clean_text(found.text) if found is not None else ""


def _all_text(element: Element | None, tag_name: str) -> list[str]:
    if element is None:
        return []
    return [_clean_text(child.text) for child in _children(element, tag_name) if _clean_text(child.text)]


def _first_descendant(element: Element, tag_name: str) -> Element | None:
    for child in element.iter():
        if _local_name(child.tag) == tag_name:
            return child
    return None


def _descendants(element: Element, tag_name: str) -> list[Element]:
    return [child for child in element.iter() if _local_name(child.tag) == tag_name]


def _first_child(element: Element | None, tag_name: str) -> Element | None:
    if element is None:
        return None
    for child in element:
        if _local_name(child.tag) == tag_name:
            return child
    return None


def _children(element: Element | None, tag_name: str) -> list[Element]:
    if element is None:
        return []
    return [child for child in element if _local_name(child.tag) == tag_name]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _clean_text(text: str | None) -> str:
    return " ".join((text or "").split())
