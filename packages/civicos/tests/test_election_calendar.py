"""
Tests for deterministic election cycle resolver and deadline generator.

Validates cycle computation for federal and state offices, CA election
deadlines, and contest determination from district assignments.
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
        assert len(cycle.upcoming_generals) >= 3

    def test_us_senate_cycle(self):
        cycle = get_election_cycle(
            "us_senate", senate_class="class_3", as_of=date(2026, 3, 28)
        )
        assert cycle.term_years == 6
        assert cycle.next_general == date(2028, 11, 7)

    def test_state_senate_4yr(self):
        cycle = get_election_cycle("state_senate", district=2, as_of=date(2026, 3, 28))
        assert cycle.term_years == 4


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
