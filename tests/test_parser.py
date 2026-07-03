from src.parser import (
    get_oai_error,
    has_identify,
    is_oai_pmh_root,
    parse_identify,
    parse_metadata_formats,
    parse_oai_xml,
    parse_records,
)


IDENTIFY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <responseDate>2026-01-01T00:00:00Z</responseDate>
  <request verb="Identify">https://jurnal.example.ac.id/oai</request>
  <Identify>
    <repositoryName>Contoh Jurnal</repositoryName>
    <baseURL>https://jurnal.example.ac.id/oai</baseURL>
    <protocolVersion>2.0</protocolVersion>
    <adminEmail>admin@example.ac.id</adminEmail>
    <earliestDatestamp>2024-01-01</earliestDatestamp>
    <deletedRecord>transient</deletedRecord>
    <granularity>YYYY-MM-DD</granularity>
  </Identify>
</OAI-PMH>
"""


FORMATS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListMetadataFormats>
    <metadataFormat>
      <metadataPrefix>oai_dc</metadataPrefix>
      <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
      <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
    </metadataFormat>
  </ListMetadataFormats>
</OAI-PMH>
"""


RECORDS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:jurnal.example.ac.id:article/1</identifier>
        <datestamp>2026-01-15</datestamp>
        <setSpec>jurnal:ART</setSpec>
      </header>
      <metadata>
        <oai_dc:dc>
          <dc:title>Judul A</dc:title>
          <dc:title>Judul B</dc:title>
          <dc:creator>Penulis Satu</dc:creator>
          <dc:creator>Penulis Dua</dc:creator>
          <dc:subject>OAI</dc:subject>
          <dc:description>Abstrak</dc:description>
          <dc:publisher>Penerbit</dc:publisher>
          <dc:date>2026-01-15</dc:date>
          <dc:type>Article</dc:type>
          <dc:format>text/html</dc:format>
          <dc:source>Jurnal Contoh</dc:source>
          <dc:language>id</dc:language>
          <dc:relation>https://doi.org/10.1234/example</dc:relation>
          <dc:coverage>Indonesia</dc:coverage>
          <dc:rights>CC BY</dc:rights>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>
"""


NO_RECORDS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <error code="noRecordsMatch">No records match</error>
</OAI-PMH>
"""


def test_identify_valid_xml_can_be_parsed() -> None:
    root = parse_oai_xml(IDENTIFY_XML)
    info = parse_identify(root)

    assert is_oai_pmh_root(root)
    assert has_identify(root)
    assert info.repository_name == "Contoh Jurnal"
    assert info.admin_emails == ["admin@example.ac.id"]


def test_list_metadata_formats_valid_xml_can_be_parsed() -> None:
    formats = parse_metadata_formats(parse_oai_xml(FORMATS_XML))

    assert formats[0].metadata_prefix == "oai_dc"
    assert formats[0].metadata_namespace == "http://www.openarchives.org/OAI/2.0/oai_dc/"


def test_list_records_oai_dc_valid_xml_can_be_parsed() -> None:
    records = parse_records(parse_oai_xml(RECORDS_XML))

    assert len(records) == 1
    assert records[0].title == "Judul A | Judul B"
    assert records[0].creators == "Penulis Satu; Penulis Dua"
    assert records[0].identifier == "oai:jurnal.example.ac.id:article/1"


def test_no_records_match_is_detected_as_oai_error() -> None:
    error = get_oai_error(parse_oai_xml(NO_RECORDS_XML))

    assert error == ("noRecordsMatch", "No records match")
