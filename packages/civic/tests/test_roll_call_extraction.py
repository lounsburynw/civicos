"""
Tests for roll call extraction from meeting minutes.

Tests the extraction of AYES/NOES/ABSENT vote patterns and
motion attribution from city council minutes text.
"""

import pytest

from civic._internal.meetings.decision import (
    extract_roll_call,
    extract_motion_attribution,
    extract_vote_tally,
    normalize_vote_names,
    VoteTally,
    _parse_names,
    _strip_title,
)


class TestExtractRollCall:
    """Test roll call extraction from minutes text."""

    def test_basic_roll_call_pattern(self):
        """Test standard AYES/NOES/ABSENT pattern."""
        text = """
        AYES: Councilmembers: Bushey, Hill, Kertz & Mayor Kate
        NOES: Councilmembers: None
        ABSENT: Councilmembers: Llorens Gulati
        """
        result = extract_roll_call(text)

        assert result["ayes"] == ["Bushey", "Hill", "Kertz", "Kate"]
        assert result["noes"] == []
        assert result["absent"] == ["Llorens Gulati"]

    def test_roll_call_with_all_noes(self):
        """Test pattern where everyone votes no."""
        text = """
        AYES: Councilmembers: None
        NOES: Councilmembers: Bushey, Hill, Kertz, Kate
        ABSENT: None
        """
        result = extract_roll_call(text)

        assert result["ayes"] == []
        assert result["noes"] == ["Bushey", "Hill", "Kertz", "Kate"]
        assert result["absent"] == []

    def test_roll_call_split_vote(self):
        """Test split vote with some ayes and noes."""
        text = """
        AYES: Councilmembers: Bushey, Hill
        NOES: Councilmembers: Kertz, Kate
        ABSENT: Councilmembers: Llorens Gulati
        """
        result = extract_roll_call(text)

        assert result["ayes"] == ["Bushey", "Hill"]
        assert result["noes"] == ["Kertz", "Kate"]
        assert result["absent"] == ["Llorens Gulati"]

    def test_roll_call_with_and_connector(self):
        """Test names connected with 'and' instead of '&'."""
        text = """
        AYES: Councilmembers: Bushey, Hill and Kertz
        NOES: None
        ABSENT: None
        """
        result = extract_roll_call(text)

        assert result["ayes"] == ["Bushey", "Hill", "Kertz"]

    def test_roll_call_single_line(self):
        """Test roll call all on one line."""
        text = "AYES: Bushey, Hill, Kertz NOES: None ABSENT: Llorens Gulati"
        result = extract_roll_call(text)

        assert result["ayes"] == ["Bushey", "Hill", "Kertz"]
        assert result["noes"] == []
        assert result["absent"] == ["Llorens Gulati"]

    def test_roll_call_without_councilmembers_prefix(self):
        """Test roll call without 'Councilmembers:' prefix."""
        text = """
        AYES: Bushey, Hill, Kertz, Kate
        NOES: None
        ABSENT: Llorens Gulati
        """
        result = extract_roll_call(text)

        assert result["ayes"] == ["Bushey", "Hill", "Kertz", "Kate"]

    def test_real_october_6_pattern(self):
        """Test actual pattern from Oct 6, 2025 San Rafael minutes."""
        text = """
        AYES:  Councilmembers:  Bushey , Hill, Kertz & Mayor Kate
        NOES:  Councilmembers:  None
        ABSENT:   Councilmembers:  Llorens Gulati
        """
        result = extract_roll_call(text)

        assert "Bushey" in result["ayes"]
        assert "Hill" in result["ayes"]
        assert "Kertz" in result["ayes"]
        assert "Kate" in result["ayes"]
        assert result["noes"] == []
        assert "Llorens Gulati" in result["absent"]


class TestParseNames:
    """Test name parsing from vote lists."""

    def test_parse_comma_separated(self):
        """Test comma-separated names."""
        result = _parse_names("Smith, Jones, Brown")
        assert result == ["Smith", "Jones", "Brown"]

    def test_parse_ampersand_separated(self):
        """Test names with & connector."""
        result = _parse_names("Smith, Jones & Brown")
        assert result == ["Smith", "Jones", "Brown"]

    def test_parse_with_titles(self):
        """Test names with title prefixes."""
        result = _parse_names("Mayor Smith, Councilmember Jones, Vice Mayor Brown")
        assert result == ["Smith", "Jones", "Brown"]

    def test_parse_none_value(self):
        """Test 'None' returns empty list."""
        assert _parse_names("None") == []
        assert _parse_names("none") == []
        assert _parse_names("None.") == []

    def test_parse_empty(self):
        """Test empty string returns empty list."""
        assert _parse_names("") == []
        assert _parse_names("   ") == []

    def test_parse_multi_word_name(self):
        """Test names with multiple words (e.g., 'Llorens Gulati')."""
        result = _parse_names("Councilmember Llorens Gulati")
        assert result == ["Llorens Gulati"]


class TestStripTitle:
    """Test title stripping from names."""

    def test_strip_mayor(self):
        """Test stripping Mayor prefix."""
        assert _strip_title("Mayor Kate") == "Kate"
        assert _strip_title("mayor Kate") == "Kate"

    def test_strip_vice_mayor(self):
        """Test stripping Vice Mayor prefix."""
        assert _strip_title("Vice Mayor Bushey") == "Bushey"
        assert _strip_title("vice mayor Bushey") == "Bushey"

    def test_strip_councilmember(self):
        """Test stripping Councilmember prefix."""
        assert _strip_title("Councilmember Kertz") == "Kertz"
        assert _strip_title("councilmember Kertz") == "Kertz"
        assert _strip_title("Council member Kertz") == "Kertz"
        assert _strip_title("Council Member Kertz") == "Kertz"

    def test_strip_cm_abbreviation(self):
        """Test stripping CM abbreviation."""
        assert _strip_title("CM Kertz") == "Kertz"

    def test_no_title_unchanged(self):
        """Test name without title is unchanged."""
        assert _strip_title("Kertz") == "Kertz"
        assert _strip_title("Llorens Gulati") == "Llorens Gulati"


class TestExtractMotionAttribution:
    """Test motion/second attribution extraction."""

    def test_basic_motion_pattern(self):
        """Test standard motion pattern."""
        text = "Vice Mayor Bushey moved, and Councilmember Kertz seconded to approve"
        motion_by, second_by = extract_motion_attribution(text)

        assert motion_by == "Bushey"
        assert second_by == "Kertz"

    def test_motion_without_comma(self):
        """Test motion pattern without comma."""
        text = "Councilmember Hill moved and Councilmember Kertz seconded"
        motion_by, second_by = extract_motion_attribution(text)

        assert motion_by == "Hill"
        assert second_by == "Kertz"

    def test_mayor_motion(self):
        """Test mayor making motion."""
        text = "Mayor Kate moved and Vice Mayor Bushey seconded"
        motion_by, second_by = extract_motion_attribution(text)

        assert motion_by == "Kate"
        assert second_by == "Bushey"

    def test_no_motion_found(self):
        """Test text without motion pattern."""
        text = "The council discussed the item at length."
        motion_by, second_by = extract_motion_attribution(text)

        assert motion_by is None
        assert second_by is None


class TestExtractVoteTally:
    """Test complete vote tally extraction."""

    def test_complete_vote_extraction(self):
        """Test extracting full vote with motion and roll call."""
        text = """
        Vice Mayor Bushey moved, and Councilmember Kertz seconded to approve.

        AYES: Councilmembers: Bushey, Hill, Kertz & Mayor Kate
        NOES: Councilmembers: None
        ABSENT: Councilmembers: Llorens Gulati
        """
        tally = extract_vote_tally(text)

        assert tally.ayes == ["Bushey", "Hill", "Kertz", "Kate"]
        assert tally.noes == []
        assert tally.absent == ["Llorens Gulati"]
        assert tally.motion_by == "Bushey"
        assert tally.second_by == "Kertz"

    def test_vote_tally_properties(self):
        """Test VoteTally computed properties."""
        text = """
        AYES: Bushey, Hill, Kertz, Kate
        NOES: None
        ABSENT: Llorens Gulati
        """
        tally = extract_vote_tally(text)

        assert tally.passed is True
        assert tally.unanimous is True
        assert tally.vote_count == "4-0"

    def test_vote_tally_to_vote_results(self):
        """Test converting VoteTally to vote_results dict format."""
        tally = VoteTally(
            ayes=["Bushey", "Hill", "Kertz", "Kate"],
            noes=["Jones"],
            absent=["Llorens Gulati"],
        )

        result = tally.to_vote_results()

        assert result["Bushey"] == "yes"
        assert result["Hill"] == "yes"
        assert result["Kertz"] == "yes"
        assert result["Kate"] == "yes"
        assert result["Jones"] == "no"
        assert result["Llorens Gulati"] == "absent"


class TestNormalizeVoteNames:
    """Test normalization of vote names to official records."""

    def test_normalize_with_variations(self):
        """Test matching extracted names to officials via variations."""
        tally = VoteTally(
            ayes=["Bushey", "Kate"],
            noes=[],
            absent=["Llorens Gulati"],
        )

        officials = [
            {
                "name": "Maribeth Bushey",
                "name_variations": ["Councilmember Bushey", "M. Bushey", "Bushey"],
            },
            {
                "name": "Kate Colin",
                "name_variations": ["Mayor Kate", "K. Colin", "Kate"],
            },
            {
                "name": "Rachel Llorens Gulati",
                "name_variations": ["Councilmember Llorens Gulati", "Llorens Gulati"],
            },
        ]

        result = normalize_vote_names(tally, officials)

        assert result["Maribeth Bushey"] == "yes"
        assert result["Kate Colin"] == "yes"
        assert result["Rachel Llorens Gulati"] == "absent"

    def test_normalize_partial_match(self):
        """Test partial name matching when exact match fails."""
        tally = VoteTally(
            ayes=["Hill"],
            noes=[],
            absent=[],
        )

        officials = [
            {
                "name": "Eli Hill",
                "name_variations": ["Councilmember Hill"],
            },
        ]

        result = normalize_vote_names(tally, officials)

        assert result["Eli Hill"] == "yes"

    def test_normalize_unmatched_preserved(self):
        """Test unmatched names are preserved as-is."""
        tally = VoteTally(
            ayes=["UnknownPerson"],
            noes=[],
            absent=[],
        )

        officials = [
            {"name": "Some Official", "name_variations": []},
        ]

        result = normalize_vote_names(tally, officials)

        # Unmatched names kept with original spelling
        assert result["UnknownPerson"] == "yes"


class TestRealMinutesPatterns:
    """Test extraction with real patterns from San Rafael minutes."""

    def test_oct6_consent_calendar_vote(self):
        """Test real vote pattern from Oct 6 consent calendar."""
        text = """
        Vice Mayor Bushey moved and Councilmember Kertz seconded to approve the
        remainder of the Consent Calendar.

        AYES:  Councilmembers:  Bushey , Hill, Kertz & Mayor Kate
        NOES:  Councilmembers:  None
        ABSENT:   Councilmembers:  Llorens Gulati
        """
        tally = extract_vote_tally(text)

        assert len(tally.ayes) == 4
        assert "Bushey" in tally.ayes
        assert tally.motion_by == "Bushey"
        assert tally.second_by == "Kertz"
        assert tally.passed is True
        assert tally.unanimous is True

    def test_oct6_item_5b_vote(self):
        """Test real vote pattern from Oct 6 item 5.b."""
        text = """
        Vice Mayor Bushey moved and Councilmember Hill seconded to approve item 5.b.

        AYES:  Councilmembers:  Bushey , Hill, Kertz & Mayor Kate
        NOES:  Councilmembers:  None
        ABSENT:   Councilmembers:  Llorens Gulati

        Adopted Resolution 15464
        """
        tally = extract_vote_tally(text)

        assert len(tally.ayes) == 4
        assert tally.motion_by == "Bushey"
        assert tally.second_by == "Hill"

    def test_board_appointment_vote(self):
        """Test vote pattern from board appointment."""
        text = """
        Vice Mayor Bushey moved, and Councilmember Kertz seconded to reappoint
        Alexander Vahdat and to appoint Michael Polk to the Board of Library
        Trustees to the end of October 2029.

        AYES:  Councilmembers:  Bushey, Hill, Kertz & Mayor Kate
        NOES:  Councilmembers:  None
        ABSENT:   Councilmembers:  Llorens Gulati
        """
        tally = extract_vote_tally(text)

        assert len(tally.ayes) == 4
        assert tally.motion_by == "Bushey"
        assert tally.second_by == "Kertz"
