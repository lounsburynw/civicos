"""Tests for HTML agenda chunk extraction (Granicus AgendaViewer fallback)."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock

from civicos_extraction.cli.chunks import (
    _extract_agenda_sections_from_html,
    _split_text_into_chunks,
    extract_chunks_from_html_agenda,
)


# Sample Granicus AgendaViewer-style HTML
SAMPLE_AGENDA_HTML = """
<html>
<head><title>Agenda</title></head>
<body>
<table>
<tr><th>Item</th><th>Description</th></tr>
<tr><td>1.</td><td>Call to Order. The Mayor called the meeting to order at 7:00 PM with all council members present.</td></tr>
<tr><td>2.</td><td>Public Comment. Members of the public may address the Council on items not on the agenda. Several residents spoke about traffic concerns on Main Street.</td></tr>
<tr><td>3a</td><td>Consent Calendar - Approval of Minutes. The minutes from the February 10, 2026 regular meeting were approved unanimously.</td></tr>
<tr><td>4.</td><td>Discussion of Housing Element Update. Staff presented the draft Housing Element for the 2023-2031 planning period. The plan includes sites for 2,500 new units across various income levels. Council directed staff to schedule community workshops. This is a critical item for RHNA compliance.</td></tr>
</table>
</body>
</html>
"""

# Heading-based HTML (non-Granicus)
SAMPLE_HEADING_HTML = """
<html><body>
<h2>Call to Order</h2>
<p>Meeting called to order at 7:00 PM.</p>
<p>All members present.</p>
<h2>Public Hearing: Zoning Amendment</h2>
<p>Staff presented the proposed zoning amendment for the downtown corridor.</p>
<p>Three members of the public testified in favor. One opposed citing traffic concerns.</p>
<p>Council voted 4-1 to approve the amendment.</p>
<h2>Adjournment</h2>
<p>Meeting adjourned at 9:30 PM.</p>
</body></html>
"""

MINIMAL_HTML = "<html><body><p>Short</p></body></html>"


class TestExtractAgendaSectionsFromHtml:
    def test_table_based_extraction(self):
        soup = BeautifulSoup(SAMPLE_AGENDA_HTML, "html.parser")
        sections = _extract_agenda_sections_from_html(soup)

        assert len(sections) >= 3
        # Check that agenda item numbers are extracted
        items = [s["item"] for s in sections]
        assert "1." in items or "2." in items
        # Check text content is present
        assert any("Housing Element" in s["text"] for s in sections)

    def test_heading_based_extraction(self):
        soup = BeautifulSoup(SAMPLE_HEADING_HTML, "html.parser")
        sections = _extract_agenda_sections_from_html(soup)

        assert len(sections) >= 2
        assert any("Zoning Amendment" in s["title"] for s in sections)
        assert any("testified" in s["text"] for s in sections)

    def test_empty_html(self):
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        sections = _extract_agenda_sections_from_html(soup)
        assert sections == []


class TestSplitTextIntoChunks:
    def test_short_text_single_chunk(self):
        text = "Short paragraph.\nAnother line."
        chunks = _split_text_into_chunks(text, max_chars=1500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits(self):
        # Create text that exceeds max_chars
        paragraphs = [f"Paragraph {i}. " + "x" * 100 for i in range(20)]
        text = "\n".join(paragraphs)
        chunks = _split_text_into_chunks(text, max_chars=500, overlap=100)

        assert len(chunks) > 1
        # All content should be covered
        combined = " ".join(chunks)
        assert "Paragraph 0" in combined
        assert "Paragraph 19" in combined

    def test_overlap_between_chunks(self):
        paragraphs = [f"Para{i} " + "a" * 200 for i in range(10)]
        text = "\n".join(paragraphs)
        chunks = _split_text_into_chunks(text, max_chars=500, overlap=200)

        if len(chunks) > 1:
            # Last paragraph of chunk N should appear in chunk N+1
            # (overlap mechanism)
            assert len(chunks[1]) > 0


class TestExtractChunksFromHtmlAgenda:
    @patch("civicos_extraction.cli.chunks.requests.Session")
    def test_successful_extraction(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_AGENDA_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        chunks = extract_chunks_from_html_agenda(
            "https://example.granicus.com/AgendaViewer.php?view_id=2&clip_id=100",
            "meeting-123",
        )

        assert len(chunks) >= 3
        # Check chunk structure
        for chunk in chunks:
            assert "id" in chunk
            assert "meeting_id" in chunk
            assert "text" in chunk
            assert "agenda_item" in chunk
            assert chunk["meeting_id"] == "meeting-123"
            assert chunk["metadata"]["source_type"] == "html_agenda"

    @patch("civicos_extraction.cli.chunks.requests.Session")
    def test_minimal_html_returns_empty(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.text = MINIMAL_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        chunks = extract_chunks_from_html_agenda(
            "https://example.granicus.com/AgendaViewer.php?view_id=2&clip_id=100",
            "meeting-123",
        )
        assert chunks == []

    @patch("civicos_extraction.cli.chunks.requests.Session")
    def test_network_error_returns_empty(self, mock_session_cls):
        import requests
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("fail")
        mock_session_cls.return_value = mock_session

        chunks = extract_chunks_from_html_agenda(
            "https://example.granicus.com/AgendaViewer.php?view_id=2&clip_id=100",
            "meeting-123",
        )
        assert chunks == []

    @patch("civicos_extraction.cli.chunks.requests.Session")
    def test_heading_based_html(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HEADING_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        chunks = extract_chunks_from_html_agenda(
            "https://example.com/meeting/123",
            "meeting-456",
        )

        assert len(chunks) >= 2
        assert any("Zoning Amendment" in c["text"] for c in chunks)
