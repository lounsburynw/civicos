"""
Tests for deriving elected officials from election contest winners.

Validates the derive_officials_from_contests() function against
realistic contest data matching Civera and CA SOS formats.
"""

import pytest
from unittest.mock import Mock

from unittest.mock import patch

from civicos._internal.elections.derive import (
    derive_officials_from_contests,
    _extract_winners,
    _contest_to_seat,
    _extract_district_number,
    _generate_name_variations,
    _winner_to_official,
    _resolve_official_jurisdiction,
)


def _make_contest(
    contest_id: str,
    title: str,
    contest_type: str,
    candidates: list,
    district_name: str | None = None,
    election_id: str = "election-1",
    division_name: str | None = None,
    division_type: str | None = None,
) -> dict:
    """Build a contest dict matching DB storage format."""
    raw_data: dict = {
        "mapped_candidates": candidates,
    }
    if division_name:
        raw_data["division"] = {
            "displayName": division_name,
            "divisionType": {"name": division_type or "City"},
        }
    return {
        "id": contest_id,
        "election_id": election_id,
        "title": title,
        "contest_type": contest_type,
        "district_name": district_name,
        "raw_data": raw_data,
    }


def _make_candidate(
    name: str,
    is_winner: bool = False,
    party: str | None = None,
    votes: int | None = None,
    source: str = "civera_election_stats",
) -> dict:
    """Build a candidate dict matching extraction output."""
    slug = name.lower().replace(" ", "-")
    return {
        "id": f"cand-{slug}",
        "name": name,
        "party": party,
        "votes_received": votes,
        "vote_percentage": None,
        "is_winner": is_winner,
        "source": source,
    }


class TestExtractWinners:
    """Test winner extraction from contest raw_data."""

    def test_extracts_winner_from_mapped_candidates(self):
        contest = _make_contest(
            "c1", "Mayor", "local_mayor",
            [
                _make_candidate("Alice Winner", is_winner=True, votes=1000),
                _make_candidate("Bob Loser", is_winner=False, votes=500),
            ],
        )
        winners = _extract_winners(contest)
        assert len(winners) == 1
        assert winners[0]["name"] == "Alice Winner"

    def test_no_winners(self):
        contest = _make_contest(
            "c1", "Mayor", "local_mayor",
            [_make_candidate("Alice", is_winner=False)],
        )
        assert _extract_winners(contest) == []

    def test_empty_candidates(self):
        contest = _make_contest("c1", "Mayor", "local_mayor", [])
        assert _extract_winners(contest) == []

    def test_no_raw_data(self):
        contest = {"id": "c1", "contest_type": "local_mayor", "raw_data": None}
        assert _extract_winners(contest) == []

    def test_raw_data_as_json_string(self):
        import json
        contest = {
            "id": "c1",
            "contest_type": "local_mayor",
            "raw_data": json.dumps({
                "mapped_candidates": [
                    {"name": "Jane", "is_winner": True, "id": "cand-1"},
                ],
            }),
        }
        winners = _extract_winners(contest)
        assert len(winners) == 1
        assert winners[0]["name"] == "Jane"

    def test_fallback_to_candidates_key(self):
        """Some formats may store candidates under 'candidates' instead of 'mapped_candidates'."""
        contest = {
            "id": "c1",
            "contest_type": "federal_house",
            "raw_data": {
                "candidates": [
                    {"name": "Rep. Smith", "is_winner": True, "id": "cand-1"},
                ],
            },
        }
        winners = _extract_winners(contest)
        assert len(winners) == 1
        assert winners[0]["name"] == "Rep. Smith"


class TestContestToSeat:
    """Test mapping contest type + title to normalized seat names."""

    def test_federal_house(self):
        contest = {"contest_type": "federal_house", "title": "U.S. House of Representatives District 2"}
        assert _contest_to_seat(contest) == "US House District 2"

    def test_federal_senate(self):
        contest = {"contest_type": "federal_senate", "title": "United States Senator"}
        assert _contest_to_seat(contest) == "US Senate"

    def test_state_assembly(self):
        contest = {"contest_type": "state_legislature", "title": "Member of the State Assembly, District 12"}
        assert _contest_to_seat(contest) == "State Assembly District 12"

    def test_state_senate(self):
        contest = {"contest_type": "state_legislature", "title": "State Senator, District 2"}
        assert _contest_to_seat(contest) == "State Senate District 2"

    def test_governor(self):
        contest = {"contest_type": "state_governor", "title": "Governor"}
        assert _contest_to_seat(contest) == "Governor"

    def test_mayor(self):
        contest = {"contest_type": "local_mayor", "title": "Mayor"}
        assert _contest_to_seat(contest) == "Mayor"

    def test_city_council_with_district(self):
        contest = {"contest_type": "local_council", "title": "City Council District 3"}
        assert _contest_to_seat(contest) == "City Council District 3"

    def test_city_council_no_district(self):
        contest = {"contest_type": "local_council", "title": "City Council Member"}
        assert _contest_to_seat(contest) == "City Council"

    def test_county_supervisor(self):
        contest = {"contest_type": "local_council", "title": "County Supervisor District 1"}
        assert _contest_to_seat(contest) == "County Supervisor District 1"

    def test_school_board(self):
        contest = {"contest_type": "local_school_board", "title": "San Rafael School Board"}
        assert _contest_to_seat(contest) == "School Board - San Rafael School Board"

    def test_president(self):
        contest = {"contest_type": "federal_president", "title": "President of the United States"}
        assert _contest_to_seat(contest) == "US President"

    def test_ballot_measure_returns_none(self):
        contest = {"contest_type": "state_proposition", "title": "Proposition 1"}
        assert _contest_to_seat(contest) is None

    def test_local_measure_returns_none(self):
        contest = {"contest_type": "local_measure", "title": "Measure A"}
        assert _contest_to_seat(contest) is None


class TestExtractDistrictNumber:
    """Test district number extraction from titles."""

    def test_standard_district(self):
        assert _extract_district_number("District 2") == "2"

    def test_district_in_context(self):
        assert _extract_district_number("US House of Representatives District 12") == "12"

    def test_hd_pattern(self):
        assert _extract_district_number("Arkansas HD 70") == "70"

    def test_sd_pattern(self):
        assert _extract_district_number("State SD 35") == "35"

    def test_no_district(self):
        assert _extract_district_number("Mayor") is None

    def test_comma_separated(self):
        assert _extract_district_number("Member of the State Assembly, District 12") == "12"


class TestGenerateNameVariations:
    """Test name variation generation for fuzzy matching."""

    def test_full_name(self):
        variations = _generate_name_variations("Jared Huffman")
        assert "Jared Huffman" in variations
        assert "J. Huffman" in variations
        assert "Huffman" in variations
        assert "Huffman, Jared" in variations

    def test_single_name(self):
        variations = _generate_name_variations("Prince")
        assert variations == ["Prince"]

    def test_three_part_name(self):
        variations = _generate_name_variations("Mary Jane Watson")
        assert "Mary Jane Watson" in variations
        assert "M. Watson" in variations
        assert "Watson" in variations


class TestWinnerToOfficial:
    """Test conversion of winner + contest to official dict."""

    def test_basic_conversion(self):
        winner = _make_candidate("Jared Huffman", is_winner=True, party="Dem", votes=23772)
        contest = {"contest_type": "federal_house", "title": "US House District 2"}
        official = _winner_to_official(winner, contest, "city-san-rafael", "2024-11-05")

        assert official["name"] == "Jared Huffman"
        assert official["seat"] == "US House District 2"
        assert official["jurisdiction_id"] == "city-san-rafael"
        assert official["term_start"] == "2024-11-05"
        assert official["term_end"] is None
        assert official["candidate_id"] == "cand-jared-huffman"
        assert "Jared Huffman" in official["name_variations"]
        assert official["id"] == "official-city-san-rafael-us-house-district-2"


SAN_RAFAEL_PARENTS = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
MILL_VALLEY_PARENTS = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}


class TestDeriveOfficialsFromContests:
    """Integration tests for the full derivation pipeline."""

    @pytest.fixture(autouse=True)
    def patch_parents(self):
        """Patch parent jurisdiction loading so tests don't depend on YAML file paths."""
        def mock_load(jid):
            if jid == "city-san-rafael":
                return SAN_RAFAEL_PARENTS
            if jid == "city-mill-valley":
                return MILL_VALLEY_PARENTS
            return {}
        with patch("civicos._internal.elections.derive._load_parent_jurisdictions", side_effect=mock_load):
            yield

    @pytest.fixture
    def mock_storage(self):
        storage = Mock()
        return storage

    def test_derives_officials_from_single_election(self, mock_storage):
        mock_storage.get_elections.return_value = [
            {"id": "election-2024", "election_date": "2024-11-05"},
        ]
        mock_storage.get_election_contests.return_value = [
            _make_contest(
                "c1", "U.S. House of Representatives District 2", "federal_house",
                [
                    _make_candidate("Jared Huffman", is_winner=True, party="Dem", votes=23772),
                    _make_candidate("Chris Coulombe", is_winner=False, party="Rep", votes=21456),
                ],
            ),
            _make_contest(
                "c2", "County Supervisor District 1", "local_council",
                [
                    _make_candidate("Damon Connolly", is_winner=True, votes=15000),
                    _make_candidate("Opponent", is_winner=False, votes=8000),
                ],
            ),
        ]
        mock_storage.store_elected_officials.return_value = 1

        result = derive_officials_from_contests(mock_storage, "city-san-rafael")

        assert result == 2
        # Officials go to different jurisdictions: federal + county
        assert mock_storage.store_elected_officials.call_count == 2

        # Collect all stored officials across calls
        all_calls = mock_storage.store_elected_officials.call_args_list
        stored = {}
        for call in all_calls:
            jid = call[0][0]
            stored[jid] = call[0][1]

        assert "country-united-states" in stored
        assert stored["country-united-states"][0]["name"] == "Jared Huffman"
        assert "county-marin" in stored
        assert stored["county-marin"][0]["name"] == "Damon Connolly"

    def test_most_recent_winner_per_seat(self, mock_storage):
        """When multiple elections have the same seat, keep only the most recent winner."""
        mock_storage.get_elections.return_value = [
            {"id": "election-2024", "election_date": "2024-11-05"},
            {"id": "election-2020", "election_date": "2020-11-03"},
        ]

        def side_effect(election_id, **kwargs):
            if election_id == "election-2024":
                return [
                    _make_contest(
                        "c1", "U.S. House of Representatives District 2", "federal_house",
                        [_make_candidate("New Rep", is_winner=True, votes=25000)],
                    ),
                ]
            elif election_id == "election-2020":
                return [
                    _make_contest(
                        "c2", "U.S. House of Representatives District 2", "federal_house",
                        [_make_candidate("Old Rep", is_winner=True, votes=20000)],
                    ),
                ]
            return []

        mock_storage.get_election_contests.side_effect = side_effect
        mock_storage.store_elected_officials.return_value = 1

        derive_officials_from_contests(mock_storage, "city-san-rafael")

        # Federal officials stored under country-united-states
        call_args = mock_storage.store_elected_officials.call_args
        assert call_args[0][0] == "country-united-states"
        officials = call_args[0][1]
        assert len(officials) == 1
        assert officials[0]["name"] == "New Rep"
        assert officials[0]["term_start"] == "2024-11-05"

    def test_skips_ballot_measures(self, mock_storage):
        mock_storage.get_elections.return_value = [
            {"id": "e1", "election_date": "2024-11-05"},
        ]
        mock_storage.get_election_contests.return_value = [
            _make_contest(
                "c1", "Proposition 1", "state_proposition",
                [_make_candidate("Yes", is_winner=True, votes=1000000)],
            ),
            _make_contest(
                "c2", "Measure A", "local_measure",
                [_make_candidate("Yes", is_winner=True, votes=5000)],
            ),
        ]

        result = derive_officials_from_contests(mock_storage, "city-san-rafael")
        assert result == 0
        mock_storage.store_elected_officials.assert_not_called()

    def test_no_elections(self, mock_storage):
        mock_storage.get_elections.return_value = []
        result = derive_officials_from_contests(mock_storage, "city-san-rafael")
        assert result == 0

    def test_multi_level_derivation(self, mock_storage):
        """Test deriving officials across federal, state, and local levels."""
        mock_storage.get_elections.return_value = [
            {"id": "e1", "election_date": "2024-11-05"},
        ]
        mock_storage.get_election_contests.return_value = [
            _make_contest(
                "c1", "U.S. House of Representatives District 2", "federal_house",
                [_make_candidate("Jared Huffman", is_winner=True, party="Dem")],
            ),
            _make_contest(
                "c2", "United States Senator", "federal_senate",
                [_make_candidate("Alex Padilla", is_winner=True, party="Dem")],
            ),
            _make_contest(
                "c3", "Member of the State Assembly, District 12", "state_legislature",
                [_make_candidate("Damon Connolly", is_winner=True, party="Dem")],
            ),
            _make_contest(
                "c4", "State Senator, District 2", "state_legislature",
                [_make_candidate("Mike McGuire", is_winner=True, party="Dem")],
            ),
            _make_contest(
                "c5", "Mayor", "local_mayor",
                [_make_candidate("Kate Colin", is_winner=True)],
            ),
        ]
        mock_storage.store_elected_officials.return_value = 1

        result = derive_officials_from_contests(mock_storage, "city-san-rafael")

        assert result == 3  # 3 jurisdictions × 1 return each

        # Collect all stored officials across jurisdiction-grouped calls
        all_calls = mock_storage.store_elected_officials.call_args_list
        stored = {}
        for call in all_calls:
            jid = call[0][0]
            stored[jid] = call[0][1]

        # Federal officials at country level
        assert "country-united-states" in stored
        federal_names = {o["name"] for o in stored["country-united-states"]}
        assert federal_names == {"Jared Huffman", "Alex Padilla"}

        # State officials at state level
        assert "state-california" in stored
        state_names = {o["name"] for o in stored["state-california"]}
        assert state_names == {"Damon Connolly", "Mike McGuire"}

        # Local officials at city level
        assert "city-san-rafael" in stored
        local_names = {o["name"] for o in stored["city-san-rafael"]}
        assert local_names == {"Kate Colin"}

    def test_candidate_id_links_to_contest(self, mock_storage):
        """Verify candidate_id in official links back to contest candidate."""
        mock_storage.get_elections.return_value = [
            {"id": "e1", "election_date": "2024-11-05"},
        ]
        mock_storage.get_election_contests.return_value = [
            _make_contest(
                "c1", "Mayor", "local_mayor",
                [_make_candidate("Kate Colin", is_winner=True, votes=10000)],
            ),
        ]
        mock_storage.store_elected_officials.return_value = 1

        derive_officials_from_contests(mock_storage, "city-san-rafael")

        officials = mock_storage.store_elected_officials.call_args[0][1]
        assert officials[0]["candidate_id"] == "cand-kate-colin"

    def test_skips_contests_from_other_cities(self, mock_storage):
        """Contests whose division names a different city are skipped."""
        mock_storage.get_elections.return_value = [
            {"id": "e1", "election_date": "2024-11-05"},
        ]
        mock_storage.get_election_contests.return_value = [
            # This mayor contest belongs to San Rafael, not Mill Valley
            _make_contest(
                "c1", "Mayor", "local_mayor",
                [_make_candidate("Kate Colin", is_winner=True)],
                division_name="City of San Rafael",
                division_type="City",
            ),
            # This is Mill Valley's own council contest
            _make_contest(
                "c2", "City Council", "local_council",
                [_make_candidate("Mill Valley Councilmember", is_winner=True)],
                division_name="City of Mill Valley",
                division_type="City",
            ),
        ]
        mock_storage.store_elected_officials.return_value = 1

        derive_officials_from_contests(mock_storage, "city-mill-valley")

        # Only Mill Valley's own council member should be stored
        call_args = mock_storage.store_elected_officials.call_args
        assert call_args[0][0] == "city-mill-valley"
        officials = call_args[0][1]
        assert len(officials) == 1
        assert officials[0]["name"] == "Mill Valley Councilmember"

    def test_resolve_jurisdiction_federal(self):
        """Federal contests resolve to country-united-states."""
        parents = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
        contest = _make_contest("c1", "US Senator", "federal_senate", [])
        result = _resolve_official_jurisdiction("federal_senate", contest, "city-san-rafael", parents)
        assert result == "country-united-states"

    def test_resolve_jurisdiction_state(self):
        """State contests resolve to state parent."""
        parents = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
        contest = _make_contest("c1", "Governor", "state_governor", [])
        result = _resolve_official_jurisdiction("state_governor", contest, "city-san-rafael", parents)
        assert result == "state-california"

    def test_resolve_jurisdiction_county_supervisor(self):
        """County supervisor contests resolve to county parent."""
        parents = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
        contest = _make_contest("c1", "County Supervisor District 1", "local_council", [])
        result = _resolve_official_jurisdiction("local_council", contest, "city-san-rafael", parents)
        assert result == "county-marin"

    def test_resolve_jurisdiction_local_mayor(self):
        """Mayor contests stay at city level."""
        parents = {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
        contest = _make_contest("c1", "Mayor", "local_mayor", [])
        result = _resolve_official_jurisdiction("local_mayor", contest, "city-san-rafael", parents)
        assert result == "city-san-rafael"
