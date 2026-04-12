"""
Tests for CA Voter Guide ballot measure content extraction.

Validates:
1. LAO proposition analysis parsing
2. VIG proposition page parsing
3. Client proposition content merging
4. Storage enrichment pipeline

Run: pytest packages/civicos-extraction/tests/test_ca_voter_guide.py -v --override-ini="addopts="
"""

from unittest.mock import patch, MagicMock

import pytest

from civicos_extraction.clients.ca_voter_guide import (
    CAVoterGuideClient,
    enrich_ballot_measure_content,
    parse_lao_proposition,
    parse_vig_proposition,
    _extract_text_blocks,
    _extract_section,
)


# ==================== Sample HTML ====================

SAMPLE_LAO_HTML = """
<html><body>
<h1>Proposition 36</h1>
<p>Allows Felony Charges and Increases Sentences for Certain Drug and Theft Crimes</p>

<h2>Summary</h2>
<p>This measure changes penalties for certain theft and drug crimes.
Currently, theft of items worth $950 or less is generally a misdemeanor.
This measure makes such thefts a felony if the person has two or more prior convictions.</p>

<h2>Fiscal Impact</h2>
<p>Increased state criminal justice costs, likely ranging from several tens of millions
of dollars to the low hundreds of millions of dollars annually. Increased local criminal
justice costs of tens of millions of dollars annually.</p>

<h2>Background</h2>
<p>In 2014, voters approved Proposition 47, which reduced penalties for certain crimes.</p>
</body></html>
"""

SAMPLE_VIG_HTML = """
<html><body>
<h1>Proposition 36</h1>

<h2>Text of the Proposed Law</h2>
<p>SECTION 1. This act shall be known as the Homelessness, Drug Addiction,
and Theft Reduction Act.</p>
<p>SEC. 2. Section 459.5 of the Penal Code is amended to read:</p>
<p>(a) Notwithstanding Section 459, shoplifting is defined as entering a commercial
establishment with intent to commit larceny while that establishment is open during
regular business hours.</p>

<h2>Fiscal Impact</h2>
<p>Net increase in state and local government costs in the tens of millions to low
hundreds of millions of dollars annually for increased incarceration and supervision
of criminal offenders.</p>

<h2>Argument in Favor of Proposition 36</h2>
<p>Proposition 36 is supported by law enforcement, retailers, and community groups.
It will restore accountability for repeat offenders while providing treatment pathways.</p>

<h2>Argument Against Proposition 36</h2>
<p>Proposition 36 will cost taxpayers hundreds of millions annually for more prison cells
instead of investing in treatment and prevention programs that actually reduce crime.</p>

<h2>Rebuttal to Argument Against</h2>
<p>The opponents ignore that this measure includes treatment requirements.</p>
</body></html>
"""


# ==================== Unit Tests: HTML Parsing ====================


class TestExtractTextBlocks:
    def test_strips_tags(self):
        blocks = _extract_text_blocks("<p>Hello <b>world</b></p>")
        assert any("Hello world" in b for b in blocks)

    def test_strips_scripts(self):
        blocks = _extract_text_blocks("<script>var x = 1;</script><p>Content</p>")
        assert any("Content" in b for b in blocks)
        assert not any("var x" in b for b in blocks)

    def test_preserves_paragraphs(self):
        blocks = _extract_text_blocks("<p>First</p><p>Second</p>")
        assert "First" in blocks
        assert "Second" in blocks

    def test_decodes_entities(self):
        blocks = _extract_text_blocks("<p>A &amp; B</p>")
        assert any("A & B" in b for b in blocks)


class TestExtractSection:
    def test_extracts_between_patterns(self):
        lines = ["Intro", "Summary", "This is the summary.", "Fiscal Impact", "Money stuff."]
        result = _extract_section(lines, r"^Summary$", [r"^Fiscal"])
        assert result == "This is the summary."

    def test_empty_when_no_start(self):
        lines = ["No match here", "Nothing relevant"]
        result = _extract_section(lines, r"^Summary$", [r"^Fiscal"])
        assert result == ""


# ==================== Unit Tests: LAO Parsing ====================


class TestParseLAOProposition:
    def test_extracts_fiscal_impact(self):
        result = parse_lao_proposition(SAMPLE_LAO_HTML, 36)
        assert result.get("fiscal_impact")
        assert "tens of millions" in result["fiscal_impact"]

    def test_extracts_summary(self):
        result = parse_lao_proposition(SAMPLE_LAO_HTML, 36)
        assert result.get("summary")
        assert "theft" in result["summary"].lower() or "penalties" in result["summary"].lower()

    def test_returns_empty_on_empty_html(self):
        result = parse_lao_proposition("", 36)
        assert result == {}

    def test_source_is_lao(self):
        result = parse_lao_proposition(SAMPLE_LAO_HTML, 36)
        assert result.get("source") == "lao"


# ==================== Unit Tests: VIG Parsing ====================


class TestParseVIGProposition:
    def test_extracts_full_text(self):
        result = parse_vig_proposition(SAMPLE_VIG_HTML, 36)
        assert result.get("full_text")
        assert "Homelessness" in result["full_text"] or "larceny" in result["full_text"]

    def test_extracts_fiscal_impact(self):
        result = parse_vig_proposition(SAMPLE_VIG_HTML, 36)
        assert result.get("fiscal_impact")
        assert "millions" in result["fiscal_impact"]

    def test_extracts_arguments_for(self):
        result = parse_vig_proposition(SAMPLE_VIG_HTML, 36)
        assert result.get("arguments_for")
        assert len(result["arguments_for"]) == 1
        assert "accountability" in result["arguments_for"][0]

    def test_extracts_arguments_against(self):
        result = parse_vig_proposition(SAMPLE_VIG_HTML, 36)
        assert result.get("arguments_against")
        assert len(result["arguments_against"]) == 1
        assert "taxpayers" in result["arguments_against"][0]

    def test_returns_empty_on_empty_html(self):
        result = parse_vig_proposition("", 36)
        assert result == {}

    def test_source_is_vig(self):
        result = parse_vig_proposition(SAMPLE_VIG_HTML, 36)
        assert result.get("source") == "ca_vig"


# ==================== Unit Tests: Client ====================


class TestCAVoterGuideClient:
    def test_initialization(self):
        client = CAVoterGuideClient(election_year=2024)
        assert client.election_year == 2024
        assert client.election_type == "general"
        assert client.platform_name == "ca_voter_guide"
        assert client.source_id == "ca_voter_guide-2024-general"

    def test_validate_valid(self):
        client = CAVoterGuideClient(election_year=2024)
        result = client.validate()
        assert result.is_valid

    def test_validate_bad_year(self):
        client = CAVoterGuideClient(election_year=1990)
        result = client.validate()
        assert not result.is_valid

    def test_validate_bad_type(self):
        client = CAVoterGuideClient(election_year=2024, election_type="invalid")
        result = client.validate()
        assert not result.is_valid

    @patch.object(CAVoterGuideClient, "_fetch")
    def test_get_lao_analysis(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_LAO_HTML
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        result = client.get_lao_analysis(36)
        assert "tens of millions" in result["fiscal_impact"]
        assert result["source"] == "lao"

    @patch.object(CAVoterGuideClient, "_fetch")
    def test_get_vig_content(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_VIG_HTML
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        result = client.get_vig_content(36)
        assert "Homelessness" in result["full_text"] or "larceny" in result["full_text"]
        assert len(result["arguments_for"]) == 1
        assert "accountability" in result["arguments_for"][0]

    @patch.object(CAVoterGuideClient, "_fetch")
    def test_get_proposition_content_merges_sources(self, mock_fetch):
        """LAO + VIG content should merge, LAO fiscal_impact taking precedence."""
        mock_fetch.side_effect = [SAMPLE_LAO_HTML, SAMPLE_VIG_HTML]
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        result = client.get_proposition_content(36)

        assert result["prop_number"] == 36
        assert result["election_year"] == 2024
        assert "tens of millions" in result["fiscal_impact"]  # from LAO
        assert "Homelessness" in result["full_text"] or "larceny" in result["full_text"]  # from VIG
        assert len(result["arguments_for"]) == 1  # from VIG
        assert len(result["arguments_against"]) == 1  # from VIG
        assert "proposition-36" in result["full_text_url"]
        assert "lao" in result["sources"]
        assert "ca_vig" in result["sources"]

    @patch.object(CAVoterGuideClient, "_fetch")
    def test_get_proposition_content_lao_only(self, mock_fetch):
        """When VIG is 403'd, should still get fiscal_impact from LAO."""
        mock_fetch.side_effect = [SAMPLE_LAO_HTML, None]
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        result = client.get_proposition_content(36)

        assert "tens of millions" in result["fiscal_impact"]
        assert result["full_text"] is None
        assert "lao" in result["sources"]
        assert "ca_vig" not in result["sources"]


# ==================== Unit Tests: Storage Enrichment ====================


class TestEnrichBallotMeasureContent:
    def _make_storage(self, contests):
        storage = MagicMock()
        storage.get_election_contests.return_value = contests
        return storage

    @patch.object(CAVoterGuideClient, "get_proposition_content")
    def test_enriches_state_proposition(self, mock_content):
        mock_content.return_value = {
            "fiscal_impact": "Millions of dollars",
            "full_text": "Section 1. This act...",
            "arguments_for": ["Good for safety"],
            "arguments_against": ["Costs too much"],
            "full_text_url": "https://example.com/prop36",
        }

        contests = [{
            "id": "test-contest-1",
            "title": "Proposition 36",
            "contest_type": "state_proposition",
            "raw_data": {
                "mapped_ballot_measure": {
                    "title": "Proposition 36",
                    "description": "Drug and theft penalties",
                    "passed": True,
                    "yes_votes": 1000,
                    "no_votes": 500,
                    "full_text": None,
                    "fiscal_impact": None,
                    "arguments_for": [],
                    "arguments_against": [],
                    "source": "civera_election_stats",
                },
            },
        }]

        storage = self._make_storage(contests)
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        stats = enrich_ballot_measure_content(client, storage, "city-san-rafael", "election-1")

        assert stats["enriched"] == 1
        assert stats["skipped"] == 0
        assert stats["failed"] == 0
        storage.store_election_contests.assert_called_once()

    def test_skips_non_proposition_contests(self):
        contests = [{
            "id": "test-1",
            "title": "Mayor",
            "contest_type": "local_mayor",
            "raw_data": {},
        }]

        storage = self._make_storage(contests)
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        stats = enrich_ballot_measure_content(client, storage, "city-san-rafael", "election-1")

        assert stats["enriched"] == 0

    def test_skips_already_enriched(self):
        contests = [{
            "id": "test-1",
            "title": "Proposition 36",
            "contest_type": "state_proposition",
            "raw_data": {
                "mapped_ballot_measure": {
                    "full_text": "Already has text",
                    "fiscal_impact": "Already has impact",
                },
            },
        }]

        storage = self._make_storage(contests)
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        stats = enrich_ballot_measure_content(client, storage, "city-san-rafael", "election-1")

        assert stats["skipped"] == 1
        assert stats["enriched"] == 0

    def test_skips_non_numbered_measures(self):
        """Local measures without proposition numbers should be skipped."""
        contests = [{
            "id": "test-1",
            "title": "Measure A: Sales Tax",
            "contest_type": "state_proposition",
            "raw_data": {"mapped_ballot_measure": {}},
        }]

        storage = self._make_storage(contests)
        client = CAVoterGuideClient(election_year=2024, request_delay=0)
        stats = enrich_ballot_measure_content(client, storage, "city-san-rafael", "election-1")

        assert stats["skipped"] == 1
