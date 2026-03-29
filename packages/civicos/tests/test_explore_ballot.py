"""
Tests for explore what='my_ballot' — the capstone ballot query.

Validates:
1. Response shape (elections, contests grouped by level, deadlines)
2. Contest-level grouping (federal/state/local)
3. Candidate extraction from raw_data.parsed_candidates
4. Deadline computation (next_deadline, days_until, passed flags)
5. Elections sorted by date (nearest first)

Run: pytest packages/civicos/tests/test_explore_ballot.py -v --override-ini="addopts="
"""

import asyncio

import pytest
from dotenv import load_dotenv

load_dotenv()

from civicos import CivicOS
from civicos_services.query.models import ExploreRequest
from civicos_services.query.verbs import execute_explore


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def civic():
    return CivicOS("city-san-rafael")


@pytest.fixture(scope="module")
def ballot_response(civic):
    req = ExploreRequest(jurisdiction="city-san-rafael", what="my_ballot")
    return _run(execute_explore(req, civic, "city-san-rafael"))


class TestBallotResponseShape:
    """Top-level response structure."""

    def test_has_elections_list(self, ballot_response):
        data = ballot_response.data
        assert "elections" in data
        assert isinstance(data["elections"], list)

    def test_has_total_elections(self, ballot_response):
        data = ballot_response.data
        assert "total_elections" in data
        assert data["total_elections"] == len(data["elections"])

    def test_has_jurisdiction(self, ballot_response):
        assert ballot_response.data["jurisdiction"] == "city-san-rafael"

    def test_no_error(self, ballot_response):
        assert "error" not in ballot_response.data

    def test_has_meta(self, ballot_response):
        assert ballot_response.meta is not None
        assert ballot_response.meta.query_time_ms >= 0


class TestElectionStructure:
    """Each election entry has required fields."""

    def test_election_fields(self, ballot_response):
        elections = ballot_response.data["elections"]
        assert len(elections) > 0
        for e in elections:
            assert "election_id" in e
            assert "name" in e
            assert "date" in e
            assert "type" in e
            assert "days_until" in e
            assert "contests" in e
            assert "total_contests" in e
            assert "deadlines" in e
            assert "next_deadline" in e or e["next_deadline"] is None

    def test_elections_sorted_by_date(self, ballot_response):
        dates = [e["date"] for e in ballot_response.data["elections"] if e["date"]]
        assert dates == sorted(dates)


class TestContestGrouping:
    """Contests grouped by government level."""

    def _primary(self, ballot_response):
        """Find the CA Primary with actual contests."""
        for e in ballot_response.data["elections"]:
            if e["total_contests"] > 0:
                return e
        pytest.skip("No election with contests found")

    def test_contest_levels_are_valid(self, ballot_response):
        valid_levels = {"federal", "state", "local", "judicial", "other"}
        primary = self._primary(ballot_response)
        for group in primary["contests"]:
            assert group["level"] in valid_levels

    def test_federal_before_state(self, ballot_response):
        primary = self._primary(ballot_response)
        levels = [g["level"] for g in primary["contests"]]
        if "federal" in levels and "state" in levels:
            assert levels.index("federal") < levels.index("state")

    def test_state_before_local(self, ballot_response):
        primary = self._primary(ballot_response)
        levels = [g["level"] for g in primary["contests"]]
        if "state" in levels and "local" in levels:
            assert levels.index("state") < levels.index("local")

    def test_race_fields(self, ballot_response):
        primary = self._primary(ballot_response)
        for group in primary["contests"]:
            for race in group["races"]:
                assert "id" in race
                assert "title" in race
                assert "contest_type" in race
                assert "candidates" in race
                assert isinstance(race["candidates"], list)


class TestCandidateExtraction:
    """Candidates extracted from raw_data.parsed_candidates."""

    def test_primary_has_candidates(self, ballot_response):
        """CA Primary should have at least some candidates from CA SOS."""
        for e in ballot_response.data["elections"]:
            for group in e.get("contests", []):
                for race in group["races"]:
                    if race["candidates"]:
                        # Found at least one race with candidates
                        cand = race["candidates"][0]
                        assert "name" in cand
                        assert "party" in cand
                        assert "incumbent" in cand
                        return
        pytest.skip("No candidates found in any race")

    def test_candidate_fields(self, ballot_response):
        for e in ballot_response.data["elections"]:
            for group in e.get("contests", []):
                for race in group["races"]:
                    for cand in race["candidates"]:
                        assert isinstance(cand["name"], str)
                        assert len(cand["name"]) > 0


class TestDeadlines:
    """Deadline computation and next_deadline."""

    def _election_with_deadlines(self, ballot_response):
        for e in ballot_response.data["elections"]:
            if e["deadlines"]:
                return e
        pytest.skip("No election with deadlines found")

    def test_deadline_fields(self, ballot_response):
        e = self._election_with_deadlines(ballot_response)
        for d in e["deadlines"]:
            assert "type" in d
            assert "date" in d
            assert "description" in d
            assert "passed" in d
            assert isinstance(d["passed"], bool)

    def test_next_deadline_is_future(self, ballot_response):
        e = self._election_with_deadlines(ballot_response)
        nd = e.get("next_deadline")
        if nd:
            assert nd["days_until"] >= 0
            assert "type" in nd
            assert "date" in nd

    def test_days_until_positive_for_future_elections(self, ballot_response):
        for e in ballot_response.data["elections"]:
            if e["days_until"] is not None:
                assert e["days_until"] >= 0, f"{e['name']} has negative days_until"
