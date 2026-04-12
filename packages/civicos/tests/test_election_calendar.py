"""
Tests for deterministic election cycle resolver and deadline generator.

Validates cycle computation for federal and state offices, CA election
deadlines, contest determination from district assignments, and
multi-state election config portability.
"""

import pytest
from datetime import date

from civicos._internal.elections.cycles import (
    OfficeType,
    first_tuesday_after_first_monday,
    ca_primary_date,
    general_election_date,
    get_next_election_date,
    get_next_primary_date,
    get_election_cycle,
    get_contests_for_jurisdiction,
)
from civicos._internal.elections.deadlines import generate_ca_deadlines


# ========== Date Computation ==========


class TestFirstTuesdayAfterFirstMonday:
    def test_november_2026(self):
        assert first_tuesday_after_first_monday(2026, 11) == date(2026, 11, 3)

    def test_november_2028(self):
        assert first_tuesday_after_first_monday(2028, 11) == date(2028, 11, 7)

    def test_june_2026(self):
        assert first_tuesday_after_first_monday(2026, 6) == date(2026, 6, 2)

    def test_june_2028(self):
        assert first_tuesday_after_first_monday(2028, 6) == date(2028, 6, 6)

    def test_november_2024(self):
        # Known: Nov 5, 2024
        assert first_tuesday_after_first_monday(2024, 11) == date(2024, 11, 5)

    def test_november_2030(self):
        assert first_tuesday_after_first_monday(2030, 11) == date(2030, 11, 5)


class TestPrimaryAndGeneralDates:
    def test_ca_primary_2026(self):
        assert ca_primary_date(2026) == date(2026, 6, 2)

    def test_general_2026(self):
        assert general_election_date(2026) == date(2026, 11, 3)


# ========== US House ==========


class TestUSHouseCycle:
    def test_next_from_2026(self):
        result = get_next_election_date("us_house", district=2, as_of=date(2026, 3, 28))
        assert result == date(2026, 11, 3)

    def test_next_from_after_2026_general(self):
        result = get_next_election_date("us_house", district=2, as_of=date(2026, 11, 4))
        assert result == date(2028, 11, 7)

    def test_all_districts_same_year(self):
        d2 = get_next_election_date("us_house", district=2, as_of=date(2026, 1, 1))
        d5 = get_next_election_date("us_house", district=5, as_of=date(2026, 1, 1))
        d50 = get_next_election_date("us_house", district=50, as_of=date(2026, 1, 1))
        assert d2 == d5 == d50 == date(2026, 11, 3)


# ========== US Senate ==========


class TestUSSenateCycle:
    def test_class_1_padilla(self):
        # Class I (Padilla) was elected 2024, next 2030
        result = get_next_election_date(
            "us_senate", senate_class="class_1", as_of=date(2026, 3, 28)
        )
        assert result == date(2030, 11, 5)

    def test_class_3_schiff(self):
        # Class III (Schiff) was elected 2022, next 2028
        result = get_next_election_date(
            "us_senate", senate_class="class_3", as_of=date(2026, 3, 28)
        )
        assert result == date(2028, 11, 7)

    def test_no_class_returns_soonest(self):
        # Without class info, should return whichever CA senate seat is next
        result = get_next_election_date("us_senate", as_of=date(2026, 3, 28))
        assert result == date(2028, 11, 7)  # Class 3 is sooner


# ========== CA Governor ==========


class TestCAGovernorCycle:
    def test_2026(self):
        result = get_next_election_date("state_governor", as_of=date(2026, 3, 28))
        assert result == date(2026, 11, 3)

    def test_after_2026(self):
        result = get_next_election_date("state_governor", as_of=date(2027, 1, 1))
        assert result == date(2030, 11, 5)

    def test_executive_same_as_governor(self):
        gov = get_next_election_date("state_governor", as_of=date(2026, 3, 28))
        exec_ = get_next_election_date("state_executive", as_of=date(2026, 3, 28))
        assert gov == exec_


# ========== CA Assembly ==========


class TestCAAssemblyCycle:
    def test_every_two_years(self):
        result = get_next_election_date("state_assembly", district=12, as_of=date(2026, 1, 1))
        assert result == date(2026, 11, 3)

    def test_all_seats_same(self):
        d1 = get_next_election_date("state_assembly", district=1, as_of=date(2026, 1, 1))
        d80 = get_next_election_date("state_assembly", district=80, as_of=date(2026, 1, 1))
        assert d1 == d80


# ========== CA State Senate ==========


class TestCAStateSenate:
    def test_even_district_2026(self):
        # Even districts (2,4,6...) up in 2026, 2030...
        result = get_next_election_date("state_senate", district=2, as_of=date(2026, 3, 28))
        assert result == date(2026, 11, 3)

    def test_odd_district_2028(self):
        # Odd districts (1,3,5...) up in 2028, 2032...
        result = get_next_election_date("state_senate", district=3, as_of=date(2026, 3, 28))
        assert result == date(2028, 11, 7)

    def test_even_district_after_2026(self):
        result = get_next_election_date("state_senate", district=2, as_of=date(2027, 1, 1))
        assert result == date(2030, 11, 5)

    def test_odd_district_after_2028(self):
        result = get_next_election_date("state_senate", district=1, as_of=date(2029, 1, 1))
        assert result == date(2032, 11, 2)

    def test_district_required(self):
        with pytest.raises(ValueError, match="district required"):
            get_next_election_date("state_senate", as_of=date(2026, 1, 1))


# ========== Primary Dates ==========


class TestPrimaryResolver:
    def test_primary_before_it_passes(self):
        result = get_next_primary_date("us_house", district=2, as_of=date(2026, 3, 28))
        assert result == date(2026, 6, 2)

    def test_primary_after_it_passes(self):
        # After June 2 primary, should return None (general is next)
        result = get_next_primary_date("us_house", district=2, as_of=date(2026, 6, 3))
        assert result is None

    def test_primary_for_next_cycle(self):
        result = get_next_primary_date("us_house", district=2, as_of=date(2027, 1, 1))
        assert result == date(2028, 6, 6)


# ========== Election Cycle Info ==========


class TestElectionCycle:
    def test_us_house_cycle(self):
        cycle = get_election_cycle("us_house", district=2, as_of=date(2026, 3, 28))
        assert cycle.term_years == 2
        assert cycle.next_general == date(2026, 11, 3)
        assert cycle.next_primary == date(2026, 6, 2)
        assert len(cycle.upcoming_generals) == 5  # 2026,2028,2030,2032,2034
        assert cycle.office_type == "us_house"

    def test_us_senate_cycle(self):
        cycle = get_election_cycle(
            "us_senate", senate_class="class_3", as_of=date(2026, 3, 28)
        )
        assert cycle.term_years == 6
        assert cycle.next_general == date(2028, 11, 7)
        assert cycle.office_type == "us_senate"

    def test_state_senate_4yr(self):
        cycle = get_election_cycle("state_senate", district=2, as_of=date(2026, 3, 28))
        assert cycle.term_years == 4
        assert cycle.office_type == "state_senate"

    def test_state_governor_cycle(self):
        cycle = get_election_cycle("state_governor", as_of=date(2026, 3, 28))
        assert cycle.term_years == 4
        assert cycle.next_general == date(2026, 11, 3)
        assert cycle.office_type == "state_governor"

    def test_state_assembly_cycle(self):
        cycle = get_election_cycle("state_assembly", district=12, as_of=date(2026, 3, 28))
        assert cycle.term_years == 2
        assert cycle.next_general == date(2026, 11, 3)

    def test_upcoming_generals_are_sorted(self):
        cycle = get_election_cycle("us_house", district=2, as_of=date(2026, 3, 28))
        generals = cycle.upcoming_generals
        assert generals == sorted(generals)

    def test_upcoming_generals_within_horizon(self):
        cycle = get_election_cycle("us_house", district=2, as_of=date(2026, 3, 28))
        for gen in cycle.upcoming_generals:
            assert gen.year <= 2026 + 8  # default horizon_years=8


# ========== Contest Determination ==========


class TestContestsForJurisdiction:
    def test_san_rafael_2026(self):
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
        contests = get_contests_for_jurisdiction(districts, 2026)
        titles = [c["title"] for c in contests]

        assert "US House District 2" in titles
        assert "State Assembly District 12" in titles
        assert "State Senate District 2" in titles
        assert "Governor" in titles
        assert "Attorney General" in titles
        assert "Controller" in titles
        assert "Treasurer" in titles
        assert "Lieutenant Governor" in titles
        assert len(contests) == 8

    def test_contest_fields_for_house(self):
        """Validate all fields on a US House contest dict."""
        districts = {"us-rep": [2]}
        contests = get_contests_for_jurisdiction(districts, 2026)
        house = next(c for c in contests if "US House" in c["title"])
        assert house["office_type"] == "us_house"
        assert house["contest_type"] == "federal_house"
        assert house["district"] == 2
        assert house["title"] == "US House District 2"

    def test_contest_fields_for_assembly(self):
        """Validate all fields on a state assembly contest dict."""
        districts = {"state-assembly": [12]}
        contests = get_contests_for_jurisdiction(districts, 2026)
        asm = next(c for c in contests if "Assembly" in c["title"])
        assert asm["office_type"] == "state_assembly"
        assert asm["contest_type"] == "state_legislature"
        assert asm["district"] == 12

    def test_contest_fields_for_state_senate(self):
        """Validate all fields on a state senate contest dict."""
        districts = {"state-senate": [2]}
        contests = get_contests_for_jurisdiction(districts, 2026)
        sen = next(c for c in contests if "State Senate" in c["title"])
        assert sen["office_type"] == "state_senate"
        assert sen["contest_type"] == "state_legislature"
        assert sen["district"] == 2

    def test_contest_fields_for_governor(self):
        """Validate governor contest dict fields."""
        districts = {}
        contests = get_contests_for_jurisdiction(districts, 2026)
        gov = next(c for c in contests if c["title"] == "Governor")
        assert gov["office_type"] == "state_governor"
        assert gov["contest_type"] == "state_governor"
        assert gov["district"] is None

    def test_contest_fields_for_statewide_executive(self):
        """Non-Governor statewide offices get state_executive type."""
        districts = {}
        contests = get_contests_for_jurisdiction(districts, 2026)
        ag = next(c for c in contests if c["title"] == "Attorney General")
        assert ag["office_type"] == "state_executive"
        assert ag["contest_type"] == "state_executive"
        assert ag["district"] is None

    def test_us_senate_contest_fields(self):
        """Validate US Senate contest dict fields including senate_class."""
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
        # 2028: Class 3 (Schiff) is up
        contests = get_contests_for_jurisdiction(districts, 2028)
        senate = [c for c in contests if c.get("office_type") == "us_senate"]
        assert len(senate) == 1  # Only Class 3 (Schiff) is up in 2028
        s = senate[0]
        assert s["contest_type"] == "federal_senate"
        assert s["district"] is None
        assert s["senate_class"] == "class_3"
        assert "US Senate" in s["title"]

    def test_empty_districts_still_gets_statewide(self):
        """Even with no districts, statewide offices appear in governor years."""
        contests = get_contests_for_jurisdiction({}, 2026)
        titles = [c["title"] for c in contests]
        assert "Governor" in titles
        assert len(contests) == 5  # Governor + 4 statewide executives

    def test_missing_district_key_skipped(self):
        """Keys not in the districts dict are skipped, not errored."""
        districts = {"us-rep": [2]}  # no assembly or senate
        contests = get_contests_for_jurisdiction(districts, 2026)
        titles = [c["title"] for c in contests]
        assert "US House District 2" in titles
        assert not any("Assembly" in t for t in titles)
        assert not any("State Senate" in t for t in titles)

    def test_odd_senate_district_not_in_2026(self):
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [3]}
        contests = get_contests_for_jurisdiction(districts, 2026)
        titles = [c["title"] for c in contests]
        assert "State Senate District 3" not in titles

    def test_2028_includes_odd_senate(self):
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [3]}
        contests = get_contests_for_jurisdiction(districts, 2028)
        titles = [c["title"] for c in contests]
        assert "State Senate District 3" in titles
        # Senate Class 3 (Schiff) is up in 2028
        assert any("US Senate" in t for t in titles)

    def test_no_governor_in_2028(self):
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [3]}
        contests = get_contests_for_jurisdiction(districts, 2028)
        titles = [c["title"] for c in contests]
        assert "Governor" not in titles


# ========== Deadline Generator ==========


class TestCADeadlines:
    def test_june_2_primary_deadlines(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2), as_of=date(2026, 3, 28))
        types = [d.deadline_type for d in deadlines]

        assert "voter_registration" in types
        assert "vbm_ballots_mailed" in types
        assert "early_voting_start" in types
        assert "election_day" in types
        assert "conditional_registration" in types
        assert len(deadlines) == 5

    def test_registration_15_days_before(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2))
        reg = next(d for d in deadlines if d.deadline_type == "voter_registration")
        assert reg.deadline_date == date(2026, 5, 18)

    def test_vbm_29_days_before(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2))
        vbm = next(d for d in deadlines if d.deadline_type == "vbm_ballots_mailed")
        assert vbm.deadline_date == date(2026, 5, 4)

    def test_early_voting_10_days_before(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2))
        early = next(d for d in deadlines if d.deadline_type == "early_voting_start")
        assert early.deadline_date == date(2026, 5, 23)

    def test_is_passed_flag(self):
        # As of March 28, no deadlines for June 2 should be passed
        deadlines = generate_ca_deadlines(date(2026, 6, 2), as_of=date(2026, 3, 28))
        assert all(not d.is_passed for d in deadlines)

        # As of May 20, registration should be passed
        deadlines = generate_ca_deadlines(date(2026, 6, 2), as_of=date(2026, 5, 20))
        reg = next(d for d in deadlines if d.deadline_type == "voter_registration")
        assert reg.is_passed

    def test_sorted_by_date(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2))
        dates = [d.deadline_date for d in deadlines]
        assert dates == sorted(dates)

    def test_november_general_deadlines(self):
        deadlines = generate_ca_deadlines(date(2026, 11, 3))
        reg = next(d for d in deadlines if d.deadline_type == "voter_registration")
        assert reg.deadline_date == date(2026, 10, 19)


# ========== Election.to_dict() Ballot Measure Serialization ==========


class TestElectionToDict:
    """Verify to_dict() includes all ballot measure content fields."""

    def _make_election_with_measure(self):
        from civicos._internal.elections import (
            Election, Contest, ContestType, BallotMeasure, ElectionType,
        )
        bm = BallotMeasure(
            id="measure-1",
            title="Proposition 36",
            description="Drug and theft penalties",
            measure_type="initiative",
            full_text="Section 1. This act shall be known as...",
            full_text_url="https://example.com/prop36",
            fiscal_impact="Tens of millions of dollars annually",
            arguments_for=["Restores accountability"],
            arguments_against=["Costs taxpayers millions"],
            passed=True,
            yes_votes=5000,
            no_votes=3000,
            yes_percentage=62.5,
            no_percentage=37.5,
        )
        contest = Contest(
            id="contest-1",
            title="Proposition 36",
            contest_type=ContestType.STATE_PROPOSITION,
            ballot_measure=bm,
        )
        election = Election(
            id="election-1",
            jurisdiction_id="city-san-rafael",
            name="2024 General",
            election_date=date(2024, 11, 5),
            election_type=ElectionType.GENERAL,
            contests=[contest],
        )
        return election

    def test_to_dict_includes_ballot_measure(self):
        election = self._make_election_with_measure()
        d = election.to_dict()
        bm = d["contests"][0]["ballot_measure"]
        assert bm is not None
        assert bm["id"] == "measure-1"
        assert bm["title"] == "Proposition 36"

    def test_to_dict_includes_content_fields(self):
        election = self._make_election_with_measure()
        d = election.to_dict()
        bm = d["contests"][0]["ballot_measure"]
        assert bm["full_text"] == "Section 1. This act shall be known as..."
        assert bm["full_text_url"] == "https://example.com/prop36"
        assert bm["fiscal_impact"] == "Tens of millions of dollars annually"
        assert bm["measure_type"] == "initiative"

    def test_to_dict_includes_arguments(self):
        election = self._make_election_with_measure()
        d = election.to_dict()
        bm = d["contests"][0]["ballot_measure"]
        assert bm["arguments_for"] == ["Restores accountability"]
        assert bm["arguments_against"] == ["Costs taxpayers millions"]

    def test_to_dict_includes_vote_tallies(self):
        election = self._make_election_with_measure()
        d = election.to_dict()
        bm = d["contests"][0]["ballot_measure"]
        assert bm["passed"] is True
        assert bm["yes_votes"] == 5000
        assert bm["no_votes"] == 3000
        assert bm["yes_percentage"] == 62.5
        assert bm["no_percentage"] == 37.5

    def test_to_dict_null_measure(self):
        from civicos._internal.elections import (
            Election, Contest, ContestType, ElectionType,
        )
        contest = Contest(
            id="contest-2",
            title="Mayor",
            contest_type=ContestType.LOCAL_MAYOR,
        )
        election = Election(
            id="election-1",
            jurisdiction_id="city-san-rafael",
            name="2024 General",
            election_date=date(2024, 11, 5),
            election_type=ElectionType.GENERAL,
            contests=[contest],
        )
        d = election.to_dict()
        assert d["contests"][0]["ballot_measure"] is None


# ========== Multi-State Config ==========


class TestStateElectionConfig:
    """StateElectionConfig registry and lookup."""

    def test_ca_config_exists(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("CA")
        assert config.state_code == "CA"
        assert config.primary_month == 6

    def test_tx_config_exists(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("TX")
        assert config.state_code == "TX"
        assert config.primary_month == 3

    def test_supported_states(self):
        from civicos._internal.elections.state_config import supported_states
        states = supported_states()
        assert "CA" in states
        assert "TX" in states
        assert "FL" in states
        assert "NY" in states
        assert "PA" in states
        assert "IL" in states

    def test_unsupported_state_raises(self):
        from civicos._internal.elections.state_config import get_state_config
        with pytest.raises(KeyError):
            get_state_config("ZZ")

    def test_case_insensitive(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("ca")
        assert config.state_code == "CA"

    def test_ca_deadline_offsets(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("CA")
        assert config.registration_deadline_days == 15
        assert config.early_voting_start_days == 10
        assert config.vbm_mailing_days == 29
        assert config.conditional_registration is True

    def test_tx_deadline_offsets(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("TX")
        assert config.registration_deadline_days == 30
        assert config.early_voting_start_days == 17
        assert config.vbm_mailing_days == 0
        assert config.conditional_registration is False

    def test_ca_statewide_offices(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("CA")
        assert "Governor" in config.statewide_offices
        assert "Controller" in config.statewide_offices
        assert len(config.statewide_offices) == 5

    def test_tx_statewide_offices(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("TX")
        assert "Governor" in config.statewide_offices
        assert "Comptroller" in config.statewide_offices
        assert "Railroad Commissioner" in config.statewide_offices
        assert len(config.statewide_offices) == 7

    def test_configs_are_frozen(self):
        from civicos._internal.elections.state_config import get_state_config
        config = get_state_config("CA")
        with pytest.raises(AttributeError):
            config.primary_month = 3


# ========== Multi-State Cycle Resolution ==========


class TestTexasCycles:
    """Texas election cycles use TX config, not CA defaults."""

    def test_tx_governor_2026(self):
        gen = get_next_election_date("state_governor", as_of=date(2025, 1, 1), state="TX")
        assert gen == general_election_date(2026)

    def test_tx_primary_is_march(self):
        from civicos._internal.elections.cycles import state_primary_date
        primary = state_primary_date(2026, "TX")
        assert primary.month == 3  # March, not June

    def test_tx_house_district(self):
        gen = get_next_election_date("state_assembly", district=45, as_of=date(2025, 1, 1), state="TX")
        assert gen.year == 2026

    def test_tx_senate_stagger(self):
        even = get_next_election_date("state_senate", district=2, as_of=date(2025, 1, 1), state="TX")
        odd = get_next_election_date("state_senate", district=3, as_of=date(2025, 1, 1), state="TX")
        assert even.year == 2026
        assert odd.year == 2028

    def test_tx_us_senate_classes(self):
        # Cruz is Class I (2024), Cornyn is Class II (2026)
        cruz = get_next_election_date("us_senate", senate_class="class_1", as_of=date(2025, 1, 1), state="TX")
        cornyn = get_next_election_date("us_senate", senate_class="class_2", as_of=date(2025, 1, 1), state="TX")
        assert cruz.year == 2030  # 2024 + 6
        assert cornyn.year == 2026


class TestTexasContests:
    """Texas contest generation uses TX statewide offices."""

    def test_tx_2026_has_governor(self):
        contests = get_contests_for_jurisdiction(
            districts={"us-rep": [21], "state-assembly": [45], "state-senate": [14]},
            election_year=2026,
            state="TX",
        )
        titles = [c["title"] for c in contests]
        assert "Governor" in titles

    def test_tx_2026_has_comptroller(self):
        contests = get_contests_for_jurisdiction(
            districts={"us-rep": [21]},
            election_year=2026,
            state="TX",
        )
        titles = [c["title"] for c in contests]
        assert "Comptroller" in titles
        assert "Controller" not in titles  # That's CA

    def test_tx_lower_chamber_title(self):
        contests = get_contests_for_jurisdiction(
            districts={"state-assembly": [45]},
            election_year=2026,
            state="TX",
        )
        titles = [c["title"] for c in contests]
        assert "State House District 45" in titles
        assert "State Assembly District 45" not in titles


# ========== Multi-State Deadlines ==========


class TestMultiStateDeadlines:
    """Deadline generation respects per-state config."""

    def test_tx_no_vbm(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="TX")
        types = [d.deadline_type for d in deadlines]
        assert "vbm_ballots_mailed" not in types  # TX has no universal VBM

    def test_tx_registration_30_days(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="TX")
        reg = next(d for d in deadlines if d.deadline_type == "voter_registration")
        assert reg.deadline_date == date(2026, 10, 4)  # 30 days before

    def test_tx_early_voting_17_days(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="TX")
        early = next(d for d in deadlines if d.deadline_type == "early_voting_start")
        assert early.deadline_date == date(2026, 10, 17)  # 17 days before

    def test_tx_no_conditional_registration(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="TX")
        types = [d.deadline_type for d in deadlines]
        assert "conditional_registration" not in types

    def test_ca_wrapper_still_works(self):
        deadlines = generate_ca_deadlines(date(2026, 6, 2))
        types = [d.deadline_type for d in deadlines]
        assert "vbm_ballots_mailed" in types
        assert "conditional_registration" in types

    def test_pa_no_early_voting(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="PA")
        types = [d.deadline_type for d in deadlines]
        assert "early_voting_start" not in types  # PA has no in-person early voting

    def test_il_has_conditional_registration(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="IL")
        types = [d.deadline_type for d in deadlines]
        assert "conditional_registration" in types  # IL has grace period registration

    def test_election_day_has_state_times(self):
        from civicos._internal.elections.deadlines import generate_deadlines
        deadlines = generate_deadlines(date(2026, 11, 3), state_code="NY")
        eday = next(d for d in deadlines if d.deadline_type == "election_day")
        assert "6:00 AM" in eday.description  # NY opens at 6 AM
        assert "9:00 PM" in eday.description  # NY closes at 9 PM


# ========== Mutation Kill Targets ==========
# Tests targeting surviving mutants from mutmut baseline (77% → 80%)


class TestDefaultStateParameter:
    """Kill mutants that change state='CA' default to 'XXCAXX' or 'ca'."""

    def test_us_house_uses_ca_default(self):
        # No state= arg — should use CA default and return a valid CA election date
        result = get_next_election_date("us_house", district=2, as_of=date(2026, 3, 28))
        assert result == date(2026, 11, 3)  # CA general election

    def test_state_governor_default_is_ca(self):
        # Governor with default state should return CA governor cycle (2026 base)
        result = get_next_election_date("state_governor", as_of=date(2025, 1, 1))
        assert result == date(2026, 11, 3)  # CA governor 2026

    def test_state_assembly_default_is_ca(self):
        result = get_next_election_date("state_assembly", district=12, as_of=date(2025, 1, 1))
        assert result == date(2026, 11, 3)


class TestElectionDayBoundary:
    """Kill mutants that change `< as_of` to `<= as_of` (boundary condition)."""

    def test_us_house_on_election_day_returns_that_day(self):
        # as_of = election day itself — should still return THIS election, not skip to next
        election_day = date(2026, 11, 3)
        result = get_next_election_date("us_house", district=2, as_of=election_day)
        assert result == election_day  # Not 2028

    def test_us_house_day_after_election_returns_next(self):
        day_after = date(2026, 11, 4)
        result = get_next_election_date("us_house", district=2, as_of=day_after)
        assert result == date(2028, 11, 7)

    def test_governor_on_election_day_returns_that_day(self):
        election_day = date(2026, 11, 3)
        result = get_next_election_date("state_governor", as_of=election_day)
        assert result == election_day

    def test_governor_day_after_returns_next_cycle(self):
        day_after = date(2026, 11, 4)
        result = get_next_election_date("state_governor", as_of=day_after)
        assert result == date(2030, 11, 5)

    def test_assembly_on_election_day(self):
        election_day = date(2026, 11, 3)
        result = get_next_election_date("state_assembly", district=12, as_of=election_day)
        assert result == election_day

    def test_senate_on_election_day(self):
        election_day = date(2028, 11, 7)
        result = get_next_election_date(
            "us_senate", senate_class="class_3", as_of=election_day
        )
        assert result == election_day


class TestGovernorFallbackPath:
    """Kill mutants that replace gen = general_election_date(...) with None."""

    def test_governor_after_election_returns_valid_date(self):
        # After 2026 election, next governor race is 2030
        result = get_next_election_date("state_governor", as_of=date(2027, 6, 15))
        assert result == date(2030, 11, 5)
        assert isinstance(result, date)  # Not None

    def test_executive_after_election_returns_valid_date(self):
        result = get_next_election_date("state_executive", as_of=date(2027, 6, 15))
        assert result == date(2030, 11, 5)
        assert isinstance(result, date)


class TestPrimaryDateBoundary:
    """Kill mutants in get_next_primary_date and state_primary_date."""

    def test_ca_primary_default_state(self):
        from civicos._internal.elections.cycles import get_next_primary_date
        result = get_next_primary_date("us_house", district=2, as_of=date(2026, 1, 1))
        assert result == date(2026, 6, 2)  # CA primary

    def test_primary_on_primary_day(self):
        from civicos._internal.elections.cycles import get_next_primary_date
        result = get_next_primary_date("us_house", district=2, as_of=date(2026, 6, 2))
        assert result == date(2026, 6, 2)  # Should return today's primary

    def test_primary_day_after_returns_none_within_cycle(self):
        from civicos._internal.elections.cycles import get_next_primary_date
        # After the primary passes in the same cycle, returns None (no more primaries this cycle)
        result = get_next_primary_date("us_house", district=2, as_of=date(2026, 6, 3))
        assert result is None


class TestElectionCycleBoundary:
    """Kill mutants in get_election_cycle."""

    def test_cycle_on_election_day(self):
        from civicos._internal.elections.cycles import get_election_cycle
        cycle = get_election_cycle("us_house", as_of=date(2026, 11, 3))
        assert cycle.next_general == date(2026, 11, 3)

    def test_cycle_day_after_election(self):
        from civicos._internal.elections.cycles import get_election_cycle
        cycle = get_election_cycle("us_house", as_of=date(2026, 11, 4))
        assert cycle.next_general == date(2028, 11, 7)

    def test_cycle_default_state_is_ca(self):
        from civicos._internal.elections.cycles import get_election_cycle
        cycle = get_election_cycle("state_governor", as_of=date(2025, 6, 1))
        # CA governor base year is 2026 — should reflect CA cycle
        assert cycle.next_general == date(2026, 11, 3)

    def test_cycle_includes_primary(self):
        from civicos._internal.elections.cycles import get_election_cycle
        cycle = get_election_cycle("us_house", as_of=date(2026, 1, 1))
        assert cycle.next_primary == date(2026, 6, 2)


class TestContestsBoundaryAndDefaults:
    """Kill mutants in get_contests_for_jurisdiction."""

    def test_contests_default_state_is_ca(self):
        from civicos._internal.elections.cycles import get_contests_for_jurisdiction
        districts = {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
        contests = get_contests_for_jurisdiction(districts, 2026, as_of=date(2026, 1, 1))
        # Should include CA-specific offices (governor in 2026 cycle)
        office_types = [c["office_type"] for c in contests]
        assert "state_governor" in office_types
        assert "us_house" in office_types

    def test_contests_include_house_with_correct_fields(self):
        from civicos._internal.elections.cycles import get_contests_for_jurisdiction
        districts = {"us-rep": [2]}
        contests = get_contests_for_jurisdiction(districts, 2026, as_of=date(2026, 6, 1))
        house = next(c for c in contests if c["office_type"] == "us_house")
        assert house["district"] == 2
        assert house["contest_type"] == "federal_house"
        assert house["title"] == "US House District 2"
