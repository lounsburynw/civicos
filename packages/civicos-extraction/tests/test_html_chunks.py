"""Tests for HTML agenda chunk extraction (Granicus AgendaViewer fallback)."""

import json
import os
import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock

from civicos_extraction.cli.chunks import (
    _extract_agenda_sections_from_html,
    _split_text_into_chunks,
    extract_chunks_from_html_agenda,
    extract_chunks_from_meeting,
    DownloadResult,
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

    def test_html_content_skips_download(self):
        """When html_content is provided, no HTTP request is made."""
        chunks = extract_chunks_from_html_agenda(
            "https://example.com/meeting/123",
            "meeting-789",
            html_content=SAMPLE_AGENDA_HTML,
        )

        assert len(chunks) >= 3
        for chunk in chunks:
            assert chunk["meeting_id"] == "meeting-789"
            assert chunk["metadata"]["source_type"] == "html_agenda"

    def test_html_content_heading_based(self):
        """html_content works with heading-based HTML too."""
        chunks = extract_chunks_from_html_agenda(
            "https://example.com/meeting/456",
            "meeting-heading",
            html_content=SAMPLE_HEADING_HTML,
        )
        assert len(chunks) >= 2
        assert any("Zoning Amendment" in c["text"] for c in chunks)

    def test_html_content_minimal_returns_empty(self):
        """html_content with too-short content returns empty."""
        chunks = extract_chunks_from_html_agenda(
            "https://example.com/meeting/123",
            "meeting-min",
            html_content=MINIMAL_HTML,
        )
        assert chunks == []


class TestExtractChunksFromMeetingHtmlFallback:
    """Test that extract_chunks_from_meeting falls back to HTML chunks correctly."""

    @patch("civicos_extraction.cli.chunks.chunks_exist_in_cloud")
    @patch("civicos_extraction.cli.chunks.download_and_validate_pdf")
    @patch("civicos_extraction.cli.chunks.extract_pdf_urls_from_meeting_page")
    def test_degenerate_case_no_pdf_links_uses_html(
        self, mock_extract_pdfs, mock_download, mock_cloud_exists, tmp_path
    ):
        """When agenda_url returns HTML and no PDF links are found, use HTML chunks."""
        mock_cloud_exists.return_value = False

        # First download returns HTML (degenerate case)
        mock_download.return_value = DownloadResult(
            content=SAMPLE_AGENDA_HTML.encode('utf-8'),
            content_type="text/html",
            is_valid_pdf=False,
            validation_warnings=["DEGENERATE CASE: Content-Type is HTML"],
        )

        # No PDF links found on page
        mock_extract_pdfs.return_value = {}

        meeting = {
            "id": "mtg-html-1",
            "meeting_date": "2026-03-01",
            "agenda_url": "https://example.com/meeting/123",
        }

        result = extract_chunks_from_meeting(
            meeting, str(tmp_path), "city-test", cloud=False
        )

        assert result.status == "success"
        assert result.chunks_count >= 3
        # Should NOT have tried to download PDF links
        assert mock_download.call_count == 1  # Only the initial download

    @patch("civicos_extraction.cli.chunks.chunks_exist_in_cloud")
    @patch("civicos_extraction.cli.chunks.download_and_validate_pdf")
    @patch("civicos_extraction.cli.chunks.extract_pdf_urls_from_meeting_page")
    def test_degenerate_case_pdf_link_also_invalid_falls_back_to_html(
        self, mock_extract_pdfs, mock_download, mock_cloud_exists, tmp_path
    ):
        """When found PDF URL also returns non-PDF, fall back to HTML chunks.

        This was the main bug: the dead-end at the second is_valid_pdf check
        returned error instead of using HTML fallback.
        """
        mock_cloud_exists.return_value = False

        # First download: HTML (degenerate case)
        html_result = DownloadResult(
            content=SAMPLE_AGENDA_HTML.encode('utf-8'),
            content_type="text/html",
            is_valid_pdf=False,
            validation_warnings=["DEGENERATE CASE: Content-Type is HTML"],
        )
        # Second download: also not a valid PDF (the "found" PDF URL is also HTML)
        bad_pdf_result = DownloadResult(
            content=b"<html><body>Not a PDF</body></html>",
            content_type="text/html",
            is_valid_pdf=False,
            validation_warnings=["DEGENERATE CASE: Content-Type is HTML"],
        )
        mock_download.side_effect = [html_result, bad_pdf_result]

        # Page scraping finds a PDF link (but it's actually broken)
        mock_extract_pdfs.return_value = {
            'agenda_packet_url': 'https://example.com/fake.pdf',
        }

        meeting = {
            "id": "mtg-html-2",
            "meeting_date": "2026-03-01",
            "agenda_url": "https://example.com/meeting/456",
        }

        result = extract_chunks_from_meeting(
            meeting, str(tmp_path), "city-test", cloud=False
        )

        # Should succeed with HTML chunks instead of returning error
        assert result.status == "success"
        assert result.chunks_count >= 3
