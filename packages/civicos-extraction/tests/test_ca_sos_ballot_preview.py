"""
Tests for CA SOS Ballot Preview client (certified candidate PDF parser).

Tests PDF text parsing, candidate extraction, storage mapping, and
contest generation from CA Secretary of State certified candidate list PDFs.
"""

import pytest

from civicos_extraction.clients.ca_sos_ballot_preview import (
    KNOWN_PARTIES,
    RACE_CONFIGS,
    _parse_candidates_from_text,
    _parse_district_from_page,
    _slugify,
    _split_candidate_text,
    ca_sos_preview_candidate_to_storage,
    ca_sos_preview_to_contest,
    ca_sos_preview_to_election,
    parse_candidate_pdf,
)


# ==================== Sample PDF Text ====================

# Simulates text extracted from a congressional district PDF page
SAMPLE_CONGRESS_PAGE = """Gregory Burgess
No Party Preference
327 Irwin St
San Rafael, CA 94901
WEBSITE: www.vote-roar.com
E-MAIL: gregoryburgess79@gmail.com
Elder Caregiver
Jared Huffman
Democratic
PO Box 664
Petaluma, CA 94953
WEBSITE: www.jaredhuffman.com
U.S. Representative
TO ALL CANDIDATES FOR THE OFFICE HEREINAFTER INDICATED
   This notice complies with provisions of the Elections Code requiring the Secretary of State to notify each candidate
for voter-nominated office of the name, address, and, if applicable, ballot designation and party preference of each
person having filed for the same office. A Certified List of Candidates will be available on March 26, 2026.
Shirley N. Weber, Ph.D.
Secretary of State
March 24, 2026
CANDIDATES FOR JUNE 2, 2026, PRIMARY ELECTION
United States Representative District 2
Notice to Candidates
June 2, 2026, Primary Election
Page 1
United States Representative District 2"""

SAMPLE_CONGRESS_PAGE_2 = """Robin Littau
Republican
PO Box 12345
Ukiah, CA 95482
(707) 555-1234 (Business)
WEBSITE: www.littauforcongress.com
E-MAIL: robin@littauforcongress.com
Enterprise Elementary School Board Member
Notice to Candidates
June 2, 2026, Primary Election
Page 2
United States Representative District 2"""

SAMPLE_SENATE_PAGE = """Damon Connolly
Democratic
1888 Las Gallinas Ave
San Rafael, CA 94903
(415) 250-6127 (Business)
WEBSITE: www.damonconnolly.com
E-MAIL: damon@damonconnolly.com
California State Assemblymember
Tief Gibbs
Republican
904 Vallejo Ave
Novato, CA 94945
(510) 734-6763 (Business)
WEBSITE: www.tief4casenate.com
E-MAIL: tief@sbcglobal.net
Small Businesswoman
Notice to Candidates
June 2, 2026, Primary Election
Page 1
State Senate District 2"""

SAMPLE_GOVERNOR_PAGE = """Jane Smith
Democratic
123 Main St
Sacramento, CA 95814
WEBSITE: www.janeforgovernor.com
Business Executive
John Doe
Republican
456 Oak Ave
Los Angeles, CA 90001
(213) 555-9876 (Business)
Retired Judge
Notice to Candidates
June 2, 2026, Primary Election
Page 1
Governor"""

SAMPLE_INCUMBENT_PAGE = """Heather Hadwick*
Republican
PO Box 693
Alturas, CA 96101
(530) 223-6300 (Business)
WEBSITE: www.votehadwick.com
E-MAIL: hhadwick@hotmail.com
Farmer/Assemblywoman
Darin Hale
Republican
1457 Fair Oaks Dr
Anderson, CA 96007
E-MAIL: haleassemblydistrictone2026@outlook.com
Councilmember
Notice to Candidates
June 2, 2026, Primary Election
Page 1
State Assembly Member District 1
*Incumbent"""


# ==================== Text Splitting ====================


class TestSplitCandidateText:
    """Removing footer/notice text from page text."""

    def test_removes_notice_section(self):
        result = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        assert "TO ALL CANDIDATES" not in result
        assert "Gregory Burgess" in result
        assert "Jared Huffman" in result

    def test_removes_footer(self):
        result = _split_candidate_text(SAMPLE_CONGRESS_PAGE_2)
        assert "Notice to Candidates" not in result
        assert "Robin Littau" in result

    def test_preserves_candidate_data(self):
        result = _split_candidate_text(SAMPLE_SENATE_PAGE)
        assert "Damon Connolly" in result
        assert "Tief Gibbs" in result
        assert "Small Businesswoman" in result


# ==================== District Parsing ====================


class TestParseDistrict:
    """District number extraction from page footer text."""

    def test_congress_district(self):
        assert _parse_district_from_page(SAMPLE_CONGRESS_PAGE, "congress") == 2

    def test_senate_district(self):
        assert _parse_district_from_page(SAMPLE_SENATE_PAGE, "state-senate") == 2

    def test_assembly_district(self):
        assert _parse_district_from_page(SAMPLE_INCUMBENT_PAGE, "assembly") == 1

    def test_statewide_returns_none(self):
        assert _parse_district_from_page(SAMPLE_GOVERNOR_PAGE, "governor") is None

    def test_wrong_race_returns_none(self):
        # Looking for senate district in a congress page
        assert _parse_district_from_page(SAMPLE_CONGRESS_PAGE, "state-senate") is None


# ==================== Candidate Parsing ====================


class TestParseCandidates:
    """Candidate entry extraction from cleaned PDF text."""

    def test_basic_parsing(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert len(candidates) == 2
        assert candidates[0]["name"] == "Gregory Burgess"
        assert candidates[1]["name"] == "Jared Huffman"

    def test_party_extraction(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert candidates[0]["party"] == "No Party Preference"
        assert candidates[1]["party"] == "Democratic"

    def test_ballot_designation(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert candidates[0]["ballot_designation"] == "Elder Caregiver"
        assert candidates[1]["ballot_designation"] == "U.S. Representative"

    def test_website_extraction(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert candidates[0]["website"] == "www.vote-roar.com"
        assert candidates[1]["website"] == "www.jaredhuffman.com"

    def test_email_extraction(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert candidates[0]["email"] == "gregoryburgess79@gmail.com"
        assert candidates[1]["email"] is None

    def test_phone_extraction(self):
        text = _split_candidate_text(SAMPLE_CONGRESS_PAGE_2)
        candidates = _parse_candidates_from_text(text)
        assert len(candidates) == 1
        assert candidates[0]["phone"] == "(707) 555-1234 (Business)"

    def test_incumbent_marker(self):
        text = _split_candidate_text(SAMPLE_INCUMBENT_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert len(candidates) == 2
        assert candidates[0]["name"] == "Heather Hadwick"
        assert candidates[0]["incumbent"] is True
        assert candidates[1]["name"] == "Darin Hale"
        assert candidates[1]["incumbent"] is False

    def test_multi_page_combined(self):
        """Combining text from two pages of the same district."""
        text1 = _split_candidate_text(SAMPLE_CONGRESS_PAGE)
        text2 = _split_candidate_text(SAMPLE_CONGRESS_PAGE_2)
        combined = text1 + "\n" + text2
        candidates = _parse_candidates_from_text(combined)
        assert len(candidates) == 3
        names = [c["name"] for c in candidates]
        assert "Gregory Burgess" in names
        assert "Jared Huffman" in names
        assert "Robin Littau" in names

    def test_senate_candidates(self):
        text = _split_candidate_text(SAMPLE_SENATE_PAGE)
        candidates = _parse_candidates_from_text(text)
        assert len(candidates) == 2
        assert candidates[0]["name"] == "Damon Connolly"
        assert candidates[0]["party"] == "Democratic"
        assert candidates[1]["name"] == "Tief Gibbs"
        assert candidates[1]["party"] == "Republican"

    def test_all_known_parties_recognized(self):
        """All known party names should be in the KNOWN_PARTIES set."""
        expected = {
            "Democratic", "Republican", "No Party Preference",
            "American Independent", "Green", "Libertarian",
            "Peace and Freedom",
        }
        assert KNOWN_PARTIES == expected


# ==================== Storage Mappers ====================


class TestStorageMappers:
    """Storage format mapping for candidates, contests, elections."""

    def test_candidate_to_storage(self):
        candidate = {
            "name": "Jared Huffman",
            "party": "Democratic",
            "incumbent": False,
            "ballot_designation": "U.S. Representative",
            "website": "www.jaredhuffman.com",
            "email": None,
            "phone": None,
        }
        result = ca_sos_preview_candidate_to_storage(candidate, "congress", 2)
        assert result["id"] == "ca-sos-preview-congress-2-jared-huffman"
        assert result["name"] == "Jared Huffman"
        assert result["party"] == "Democratic"
        assert result["incumbent"] is False
        assert result["ballot_designation"] == "U.S. Representative"
        assert result["source"] == "ca_sos_ballot_preview"
        assert result["votes_received"] is None
        assert result["is_winner"] is False

    def test_candidate_to_storage_statewide(self):
        candidate = {
            "name": "Jane Smith",
            "party": "Democratic",
            "incumbent": False,
            "ballot_designation": "Business Executive",
        }
        result = ca_sos_preview_candidate_to_storage(candidate, "governor", None)
        assert result["id"] == "ca-sos-preview-governor-jane-smith"

    def test_contest_to_storage(self):
        candidates = [
            {"name": "A", "party": "Democratic", "incumbent": False, "ballot_designation": "X"},
            {"name": "B", "party": "Republican", "incumbent": True, "ballot_designation": "Y"},
        ]
        result = ca_sos_preview_to_contest("congress", 2, candidates, "2026-primary")
        assert result["id"] == "ca-sos-preview-2026-primary-congress-2"
        assert result["title"] == "US House District 2"
        assert result["contest_type"] == "federal_house"
        assert result["number_elected"] == 1
        assert len(result["candidates"]) == 2
        assert result["ballot_measure"] is None
        assert result["raw_data"]["race_slug"] == "congress"
        assert result["raw_data"]["district"] == 2

    def test_contest_statewide(self):
        candidates = [{"name": "X", "party": "Democratic", "incumbent": False}]
        result = ca_sos_preview_to_contest("governor", None, candidates, "2026-primary")
        assert result["id"] == "ca-sos-preview-2026-primary-governor"
        assert result["title"] == "Governor"
        assert result["contest_type"] == "state_governor"
        assert result["district_name"] is None

    def test_election_to_storage(self):
        result = ca_sos_preview_to_election("2026-primary", "2026-06-02", "primary")
        assert result["id"] == "ca-sos-preview-2026-primary"
        assert result["name"] == "California Primary Election"
        assert result["election_date"] == "2026-06-02"
        assert result["election_type"] == "primary"
        assert result["source"] == "ca_sos_ballot_preview"
        assert "2026-primary" in result["source_url"]


# ==================== Race Config ====================


class TestRaceConfigs:
    """RACE_CONFIGS completeness and correctness."""

    def test_all_expected_races_present(self):
        expected = {
            "congress", "state-senate", "assembly", "governor",
            "lt-governor", "controller", "treasurer", "attorney-general",
        }
        assert set(RACE_CONFIGS.keys()) == expected

    def test_district_races_have_pattern(self):
        for slug in ["congress", "state-senate", "assembly"]:
            config = RACE_CONFIGS[slug]
            assert "district_pattern" in config
            assert not config.get("statewide", False)

    def test_statewide_races_marked(self):
        for slug in ["governor", "lt-governor", "controller", "treasurer", "attorney-general"]:
            config = RACE_CONFIGS[slug]
            assert config.get("statewide") is True

    def test_all_have_contest_type(self):
        for slug, config in RACE_CONFIGS.items():
            assert "contest_type" in config, f"{slug} missing contest_type"
            assert "title_template" in config, f"{slug} missing title_template"


# ==================== Slugify ====================


class TestSlugify:
    """URL-friendly slug generation."""

    def test_simple(self):
        assert _slugify("Jared Huffman") == "jared-huffman"

    def test_special_chars(self):
        assert _slugify("James Athans Jr.") == "james-athans-jr"

    def test_quotes(self):
        assert _slugify('Nicholas "Nick" Schultz') == "nicholas-nick-schultz"
