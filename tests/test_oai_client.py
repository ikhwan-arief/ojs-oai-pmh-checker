from src.models import OAIResponse
from src.oai_client import OAIClient


NAMESPACED_RECORDS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<oai:OAI-PMH xmlns:oai="http://www.openarchives.org/OAI/2.0/"
             xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
  <oai:ListRecords>
    <oai:record>
      <oai:header>
        <oai:identifier>oai:test:1</oai:identifier>
        <oai:datestamp>2026-01-01</oai:datestamp>
      </oai:header>
      <oai:metadata>
        <oai_dc:dc><dc:title>One</dc:title></oai_dc:dc>
      </oai:metadata>
    </oai:record>
    <oai:record>
      <oai:header>
        <oai:identifier>oai:test:2</oai:identifier>
        <oai:datestamp>2026-01-02</oai:datestamp>
      </oai:header>
      <oai:metadata>
        <oai_dc:dc><dc:title>Two</dc:title></oai_dc:dc>
      </oai:metadata>
    </oai:record>
    <oai:resumptionToken>next-page</oai:resumptionToken>
  </oai:ListRecords>
</oai:OAI-PMH>
"""


class FakeOAIClient(OAIClient):
    def __init__(self) -> None:
        super().__init__(timeout=5, max_bytes=5_000_000)
        self.calls = 0

    def list_records_page(
        self,
        endpoint: str,
        metadata_prefix: str,
        resumption_token: str = "",
    ) -> OAIResponse:
        self.calls += 1
        return OAIResponse(
            request_url=f"{endpoint}?page={self.calls}",
            endpoint_url=endpoint,
            ok=True,
            http_status=200,
            content=NAMESPACED_RECORDS_XML,
            content_type="text/xml",
        )


def test_list_records_counts_namespaced_records_when_enforcing_max_records() -> None:
    client = FakeOAIClient()

    responses = client.list_records(
        "https://example.org/oai",
        metadata_prefix="oai_dc",
        max_records=1,
        follow_tokens=True,
        max_token_pages=5,
    )

    assert len(responses) == 1
    assert client.calls == 1
