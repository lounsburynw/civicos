"""
Tests for municipal funding program Pydantic schemas.

Tests construction, validation, defaults, required fields, nested models,
serialization, and boundary conditions for all schema classes.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from civicos_extraction.research.municipal.schemas import (
    BallotMeasure,
    ContactInfo,
    FeeScheduleEntry,
    FundingProgram,
    IncomeLimit,
    IncomeLimits,
    MunicipalFundingPrograms,
    RecentFundingAward,
)


class TestContactInfo:
    """ContactInfo: all-optional model for department contacts."""

    def test_empty_construction(self):
        """All fields are optional — empty construction yields all None."""
        contact = ContactInfo()
        assert contact.name is None
        assert contact.phone is None
        assert contact.email is None
        assert contact.address is None
        assert contact.website is None
        assert contact.hours is None

    def test_full_construction(self):
        """All fields populated should be accessible."""
        contact = ContactInfo(
            name="Planning Dept",
            phone="415-555-0100",
            email="planning@city.gov",
            address="1400 5th Ave",
            website="https://city.gov/planning",
            hours="Mon-Fri 9am-5pm",
        )
        assert contact.name == "Planning Dept"
        assert contact.phone == "415-555-0100"
        assert contact.email == "planning@city.gov"
        assert contact.address == "1400 5th Ave"
        assert contact.website == "https://city.gov/planning"
        assert contact.hours == "Mon-Fri 9am-5pm"

    def test_partial_construction(self):
        """Subset of fields populated, rest default to None."""
        contact = ContactInfo(name="Housing Authority", email="housing@city.gov")
        assert contact.name == "Housing Authority"
        assert contact.email == "housing@city.gov"
        assert contact.phone is None
        assert contact.address is None

    def test_serialization_round_trip(self):
        """model_dump → ContactInfo reconstruction preserves values."""
        original = ContactInfo(name="Clerk", phone="415-555-0200")
        data = original.model_dump()
        restored = ContactInfo(**data)
        assert restored.name == "Clerk"
        assert restored.phone == "415-555-0200"
        assert restored.website is None


class TestFeeScheduleEntry:
    """FeeScheduleEntry: required amount/unit, optional effective_date."""

    def test_required_fields(self):
        """amount and unit are required."""
        entry = FeeScheduleEntry(amount=150.0, unit="per unit")
        assert entry.amount == 150.0
        assert entry.unit == "per unit"
        assert entry.effective_date is None

    def test_missing_amount_raises(self):
        """Omitting required 'amount' raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FeeScheduleEntry(unit="per sqft")
        assert "amount" in str(exc_info.value)

    def test_missing_unit_raises(self):
        """Omitting required 'unit' raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FeeScheduleEntry(amount=50.0)
        assert "unit" in str(exc_info.value)

    def test_with_effective_date(self):
        """effective_date stores string date."""
        entry = FeeScheduleEntry(amount=200.0, unit="per parcel", effective_date="2025-07-01")
        assert entry.effective_date == "2025-07-01"

    def test_zero_amount(self):
        """Zero is a valid fee amount."""
        entry = FeeScheduleEntry(amount=0.0, unit="flat fee")
        assert entry.amount == 0.0

    def test_negative_amount(self):
        """Negative amounts are accepted (no validator restricts them)."""
        entry = FeeScheduleEntry(amount=-10.0, unit="rebate")
        assert entry.amount == -10.0

    def test_fractional_amount(self):
        """Fractional cent amounts are preserved."""
        entry = FeeScheduleEntry(amount=0.005, unit="per sqft")
        assert entry.amount == 0.005


class TestFundingProgram:
    """FundingProgram: complex model with required/optional/default fields."""

    def _minimal_program(self, **overrides):
        """Create a FundingProgram with only required fields."""
        defaults = {
            "program_name": "CDBG",
            "administering_agency": "Housing Authority",
            "description": "Community Development Block Grant",
        }
        defaults.update(overrides)
        return FundingProgram(**defaults)

    def test_minimal_construction(self):
        """Only required fields — all defaults applied."""
        prog = self._minimal_program()
        assert prog.program_name == "CDBG"
        assert prog.administering_agency == "Housing Authority"
        assert prog.description == "Community Development Block Grant"

    def test_list_defaults_are_empty(self):
        """List fields default to empty lists, not None."""
        prog = self._minimal_program()
        assert prog.eligible_activities == []
        assert prog.resident_input_opportunities == []
        assert prog.governing_resolutions == []
        assert prog.keywords == []

    def test_dict_defaults_are_empty(self):
        """Dict fields default to empty dicts."""
        prog = self._minimal_program()
        assert prog.eligibility_requirements == {}

    def test_boolean_defaults(self):
        """local_compliance_required defaults True, annual_reporting defaults False."""
        prog = self._minimal_program()
        assert prog.local_compliance_required is True
        assert prog.annual_reporting is False

    def test_optional_fields_default_none(self):
        """Optional scalar fields default to None."""
        prog = self._minimal_program()
        assert prog.annual_funding_available is None
        assert prog.fee_schedule is None
        assert prog.official_url is None
        assert prog.governing_ordinance is None
        assert prog.contact is None

    def test_leverage_point_defaults_empty_string(self):
        """leverage_point defaults to empty string, not None."""
        prog = self._minimal_program()
        assert prog.leverage_point == ""

    def test_missing_required_raises(self):
        """Missing required field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            FundingProgram(
                program_name="CDBG",
                # missing administering_agency
                description="Grant",
            )
        assert "administering_agency" in str(exc_info.value)

    def test_nested_fee_schedule(self):
        """fee_schedule accepts dict of FeeScheduleEntry."""
        prog = self._minimal_program(
            fee_schedule={
                "fy25": FeeScheduleEntry(amount=100.0, unit="per unit", effective_date="2025-07-01"),
                "fy26": FeeScheduleEntry(amount=110.0, unit="per unit"),
            }
        )
        assert prog.fee_schedule["fy25"].amount == 100.0
        assert prog.fee_schedule["fy25"].effective_date == "2025-07-01"
        assert prog.fee_schedule["fy26"].amount == 110.0
        assert prog.fee_schedule["fy26"].effective_date is None

    def test_nested_contact(self):
        """contact accepts a ContactInfo instance."""
        prog = self._minimal_program(
            contact=ContactInfo(name="John Doe", phone="415-555-0300")
        )
        assert prog.contact.name == "John Doe"
        assert prog.contact.phone == "415-555-0300"

    def test_populated_lists(self):
        """List fields accept populated values."""
        prog = self._minimal_program(
            eligible_activities=["rehabilitation", "new construction"],
            keywords=["housing", "affordable"],
            governing_resolutions=["Res 2025-01"],
            resident_input_opportunities=["public hearing", "written comment"],
        )
        assert prog.eligible_activities == ["rehabilitation", "new construction"]
        assert prog.keywords == ["housing", "affordable"]
        assert prog.governing_resolutions == ["Res 2025-01"]
        assert prog.resident_input_opportunities == ["public hearing", "written comment"]

    def test_override_boolean_defaults(self):
        """Boolean defaults can be overridden."""
        prog = self._minimal_program(
            local_compliance_required=False,
            annual_reporting=True,
        )
        assert prog.local_compliance_required is False
        assert prog.annual_reporting is True

    def test_default_factory_independence(self):
        """Each instance gets independent default lists/dicts."""
        prog1 = self._minimal_program()
        prog2 = self._minimal_program()
        prog1.eligible_activities.append("demolition")
        assert prog2.eligible_activities == []
        assert prog1.eligible_activities == ["demolition"]


class TestBallotMeasure:
    """BallotMeasure: local ballot measure with required/optional fields."""

    def _minimal_measure(self, **overrides):
        defaults = {
            "measure_name": "Measure P",
            "title": "Affordable Housing Bond",
            "description": "Authorizes $50M in bonds for affordable housing",
            "status": "passed",
        }
        defaults.update(overrides)
        return BallotMeasure(**defaults)

    def test_minimal_construction(self):
        """Required fields set, optionals default to None/empty."""
        m = self._minimal_measure()
        assert m.measure_name == "Measure P"
        assert m.title == "Affordable Housing Bond"
        assert m.status == "passed"
        assert m.election_date is None
        assert m.annual_revenue is None
        assert m.duration_years is None
        assert m.tax_rate is None
        assert m.exemptions == []
        assert m.official_url is None

    def test_full_construction(self):
        """All fields populated."""
        m = self._minimal_measure(
            election_date="2024-11-05",
            annual_revenue=5_000_000.0,
            duration_years=30,
            tax_rate="$0.05 per $1,000 assessed value",
            exemptions=["senior citizens", "disabled veterans"],
            official_url="https://city.gov/measure-p",
        )
        assert m.election_date == "2024-11-05"
        assert m.annual_revenue == 5_000_000.0
        assert m.duration_years == 30
        assert m.tax_rate == "$0.05 per $1,000 assessed value"
        assert m.exemptions == ["senior citizens", "disabled veterans"]
        assert m.official_url == "https://city.gov/measure-p"

    def test_missing_status_raises(self):
        """status is required."""
        with pytest.raises(ValidationError) as exc_info:
            BallotMeasure(
                measure_name="Measure Q",
                title="Parks Bond",
                description="Fund parks",
            )
        assert "status" in str(exc_info.value)

    def test_missing_measure_name_raises(self):
        """measure_name is required."""
        with pytest.raises(ValidationError) as exc_info:
            BallotMeasure(
                title="Parks Bond",
                description="Fund parks",
                status="pending",
            )
        assert "measure_name" in str(exc_info.value)

    def test_exemptions_default_independent(self):
        """Each instance gets its own exemptions list."""
        m1 = self._minimal_measure()
        m2 = self._minimal_measure()
        m1.exemptions.append("low-income")
        assert m2.exemptions == []


class TestRecentFundingAward:
    """RecentFundingAward: project/award with optional amount."""

    def test_minimal_construction(self):
        """Required fields only."""
        award = RecentFundingAward(
            project_name="Downtown Revitalization",
            description="Streetscape improvements on 4th Street",
            status="awarded",
        )
        assert award.project_name == "Downtown Revitalization"
        assert award.description == "Streetscape improvements on 4th Street"
        assert award.status == "awarded"
        assert award.amount is None

    def test_with_amount(self):
        """amount field stores numeric value."""
        award = RecentFundingAward(
            project_name="Bike Lane Project",
            description="Protected bike lanes on 2nd Street",
            status="in development",
            amount=2_500_000.0,
        )
        assert award.amount == 2_500_000.0

    def test_missing_status_raises(self):
        """status is required."""
        with pytest.raises(ValidationError) as exc_info:
            RecentFundingAward(
                project_name="Test",
                description="Test project",
            )
        assert "status" in str(exc_info.value)

    def test_zero_amount(self):
        """Zero is a valid funding amount."""
        award = RecentFundingAward(
            project_name="Volunteer Program",
            description="No-cost volunteer coordination",
            status="active",
            amount=0.0,
        )
        assert award.amount == 0.0


class TestIncomeLimit:
    """IncomeLimit: all four fields are required ints."""

    def test_construction(self):
        """All four household size limits stored correctly."""
        limit = IncomeLimit(
            one_person=30_000,
            two_person=34_300,
            three_person=38_600,
            four_person=42_850,
        )
        assert limit.one_person == 30_000
        assert limit.two_person == 34_300
        assert limit.three_person == 38_600
        assert limit.four_person == 42_850

    def test_missing_field_raises(self):
        """All four fields are required."""
        with pytest.raises(ValidationError) as exc_info:
            IncomeLimit(
                one_person=30_000,
                two_person=34_300,
                # missing three_person and four_person
            )
        errors_str = str(exc_info.value)
        assert "three_person" in errors_str
        assert "four_person" in errors_str

    def test_integer_coercion_from_float(self):
        """Pydantic coerces float to int when possible."""
        limit = IncomeLimit(
            one_person=30000,
            two_person=34300,
            three_person=38600,
            four_person=42850,
        )
        assert limit.four_person == 42850
        assert isinstance(limit.four_person, int)


class TestIncomeLimits:
    """IncomeLimits: nested model with three IncomeLimit tiers."""

    def _sample_limits(self):
        return IncomeLimits(
            area="San Francisco HMFA",
            median_family_income_4person=149_600,
            extremely_low_30_ami=IncomeLimit(
                one_person=31_450, two_person=35_950,
                three_person=40_450, four_person=44_900,
            ),
            very_low_50_ami=IncomeLimit(
                one_person=52_400, two_person=59_900,
                three_person=67_350, four_person=74_800,
            ),
            low_80_ami=IncomeLimit(
                one_person=83_900, two_person=95_850,
                three_person=107_800, four_person=119_700,
            ),
            effective_date="2025-06-15",
        )

    def test_full_construction(self):
        """All required fields populated."""
        limits = self._sample_limits()
        assert limits.area == "San Francisco HMFA"
        assert limits.median_family_income_4person == 149_600
        assert limits.effective_date == "2025-06-15"
        assert limits.note is None

    def test_nested_income_limits_values(self):
        """Nested IncomeLimit values are accessible."""
        limits = self._sample_limits()
        assert limits.extremely_low_30_ami.one_person == 31_450
        assert limits.very_low_50_ami.four_person == 74_800
        assert limits.low_80_ami.two_person == 95_850

    def test_with_note(self):
        """Optional note field."""
        limits = self._sample_limits()
        limits_with_note = limits.model_copy(update={"note": "FY2025 limits"})
        assert limits_with_note.note == "FY2025 limits"

    def test_missing_area_raises(self):
        """area is required."""
        with pytest.raises(ValidationError) as exc_info:
            IncomeLimits(
                median_family_income_4person=100_000,
                extremely_low_30_ami=IncomeLimit(
                    one_person=1, two_person=2, three_person=3, four_person=4,
                ),
                very_low_50_ami=IncomeLimit(
                    one_person=1, two_person=2, three_person=3, four_person=4,
                ),
                low_80_ami=IncomeLimit(
                    one_person=1, two_person=2, three_person=3, four_person=4,
                ),
                effective_date="2025-01-01",
            )
        assert "area" in str(exc_info.value)

    def test_missing_nested_tier_raises(self):
        """Missing a required IncomeLimit tier raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IncomeLimits(
                area="Test Area",
                median_family_income_4person=100_000,
                extremely_low_30_ami=IncomeLimit(
                    one_person=1, two_person=2, three_person=3, four_person=4,
                ),
                # missing very_low_50_ami
                low_80_ami=IncomeLimit(
                    one_person=1, two_person=2, three_person=3, four_person=4,
                ),
                effective_date="2025-01-01",
            )
        assert "very_low_50_ami" in str(exc_info.value)


class TestMunicipalFundingPrograms:
    """MunicipalFundingPrograms: top-level container with nested collections."""

    def _minimal_programs(self, **overrides):
        defaults = {
            "jurisdiction": "city-san-rafael",
            "topic": "housing",
        }
        defaults.update(overrides)
        return MunicipalFundingPrograms(**defaults)

    def test_minimal_construction(self):
        """Required fields only — defaults applied."""
        mfp = self._minimal_programs()
        assert mfp.jurisdiction == "city-san-rafael"
        assert mfp.topic == "housing"
        assert mfp.jurisdiction_type == "municipal"
        assert mfp.verification_status == "DRAFT - NOT VERIFIED"

    def test_default_collections_are_empty(self):
        """All dict/list collection defaults are empty."""
        mfp = self._minimal_programs()
        assert mfp.programs == {}
        assert mfp.ballot_measures == {}
        assert mfp.recent_funding_awards == {}
        assert mfp.contact_information == {}
        assert mfp.data_sources == []
        assert mfp.source_citations == []

    def test_income_limits_default_none(self):
        """income_limits defaults to None."""
        mfp = self._minimal_programs()
        assert mfp.income_limits is None

    def test_last_updated_is_recent_datetime(self):
        """last_updated auto-populates to approximately now."""
        before = datetime.now()
        mfp = self._minimal_programs()
        after = datetime.now()
        assert before <= mfp.last_updated <= after

    def test_explicit_last_updated(self):
        """Explicit last_updated overrides default_factory."""
        fixed_time = datetime(2025, 6, 15, 12, 0, 0)
        mfp = self._minimal_programs(last_updated=fixed_time)
        assert mfp.last_updated == fixed_time
        assert mfp.last_updated.year == 2025
        assert mfp.last_updated.month == 6

    def test_missing_jurisdiction_raises(self):
        """jurisdiction is required."""
        with pytest.raises(ValidationError) as exc_info:
            MunicipalFundingPrograms(topic="housing")
        assert "jurisdiction" in str(exc_info.value)

    def test_missing_topic_raises(self):
        """topic is required."""
        with pytest.raises(ValidationError) as exc_info:
            MunicipalFundingPrograms(jurisdiction="city-test")
        assert "topic" in str(exc_info.value)

    def test_override_jurisdiction_type(self):
        """jurisdiction_type can be overridden from default."""
        mfp = self._minimal_programs(jurisdiction_type="county")
        assert mfp.jurisdiction_type == "county"

    def test_override_verification_status(self):
        """verification_status can be overridden from default."""
        mfp = self._minimal_programs(verification_status="VERIFIED")
        assert mfp.verification_status == "VERIFIED"

    def test_nested_programs_dict(self):
        """programs dict accepts FundingProgram instances."""
        prog = FundingProgram(
            program_name="CDBG",
            administering_agency="HUD",
            description="Community development",
        )
        mfp = self._minimal_programs(programs={"cdbg": prog})
        assert "cdbg" in mfp.programs
        assert mfp.programs["cdbg"].program_name == "CDBG"
        assert mfp.programs["cdbg"].administering_agency == "HUD"

    def test_nested_ballot_measures_dict(self):
        """ballot_measures dict accepts BallotMeasure instances."""
        measure = BallotMeasure(
            measure_name="Measure A",
            title="Parks Bond",
            description="Parks funding",
            status="passed",
        )
        mfp = self._minimal_programs(ballot_measures={"measure-a": measure})
        assert mfp.ballot_measures["measure-a"].measure_name == "Measure A"
        assert mfp.ballot_measures["measure-a"].status == "passed"

    def test_nested_funding_awards_dict(self):
        """recent_funding_awards dict accepts RecentFundingAward instances."""
        award = RecentFundingAward(
            project_name="Bridge Repair",
            description="Structural repair",
            status="awarded",
            amount=1_000_000.0,
        )
        mfp = self._minimal_programs(recent_funding_awards={"bridge": award})
        assert mfp.recent_funding_awards["bridge"].amount == 1_000_000.0

    def test_nested_contact_information_dict(self):
        """contact_information dict accepts ContactInfo instances."""
        contact = ContactInfo(name="Planning", phone="415-555-0100")
        mfp = self._minimal_programs(contact_information={"planning": contact})
        assert mfp.contact_information["planning"].name == "Planning"

    def test_nested_income_limits(self):
        """income_limits accepts IncomeLimits instance."""
        il = IncomeLimits(
            area="Marin County",
            median_family_income_4person=149_600,
            extremely_low_30_ami=IncomeLimit(
                one_person=31_000, two_person=35_000,
                three_person=40_000, four_person=44_000,
            ),
            very_low_50_ami=IncomeLimit(
                one_person=52_000, two_person=59_000,
                three_person=67_000, four_person=74_000,
            ),
            low_80_ami=IncomeLimit(
                one_person=83_000, two_person=95_000,
                three_person=107_000, four_person=119_000,
            ),
            effective_date="2025-06-15",
        )
        mfp = self._minimal_programs(income_limits=il)
        assert mfp.income_limits.area == "Marin County"
        assert mfp.income_limits.extremely_low_30_ami.one_person == 31_000

    def test_json_serialization_datetime(self):
        """datetime fields serialize to ISO format via model_dump(mode='json')."""
        fixed_time = datetime(2025, 6, 15, 12, 0, 0)
        mfp = self._minimal_programs(last_updated=fixed_time)
        data = mfp.model_dump(mode="json")
        assert data["last_updated"] == "2025-06-15T12:00:00"

    def test_json_serialization_tz_aware_datetime(self):
        """Timezone-aware datetime serializes with tz offset."""
        fixed_time = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        mfp = self._minimal_programs(last_updated=fixed_time)
        data = mfp.model_dump(mode="json")
        # Pydantic v2 serializes UTC as Z suffix
        assert data["last_updated"] in (
            "2025-06-15T12:00:00Z",
            "2025-06-15T12:00:00+00:00",
        )

    def test_default_factory_independence_programs(self):
        """Each instance gets independent programs dict."""
        mfp1 = self._minimal_programs()
        mfp2 = self._minimal_programs()
        mfp1.programs["test"] = FundingProgram(
            program_name="Test",
            administering_agency="Agency",
            description="Desc",
        )
        assert mfp2.programs == {}

    def test_default_factory_independence_data_sources(self):
        """Each instance gets independent data_sources list."""
        mfp1 = self._minimal_programs()
        mfp2 = self._minimal_programs()
        mfp1.data_sources.append("perplexity")
        assert mfp2.data_sources == []

    def test_full_round_trip(self):
        """Full construction → dump → reconstruction preserves all data."""
        prog = FundingProgram(
            program_name="HOME",
            administering_agency="HCD",
            description="HOME Investment Partnerships",
            annual_funding_available=500_000.0,
            local_compliance_required=True,
            annual_reporting=True,
            keywords=["housing", "federal"],
        )
        measure = BallotMeasure(
            measure_name="Measure P",
            title="Housing Bond",
            description="Bond for housing",
            status="passed",
            annual_revenue=5_000_000.0,
        )
        fixed_time = datetime(2025, 6, 15, 12, 0, 0)
        mfp = MunicipalFundingPrograms(
            jurisdiction="city-san-rafael",
            topic="housing",
            last_updated=fixed_time,
            data_sources=["perplexity", "city website"],
            verification_status="VERIFIED",
            programs={"home": prog},
            ballot_measures={"measure-p": measure},
        )
        data = mfp.model_dump()
        restored = MunicipalFundingPrograms(**data)

        assert restored.jurisdiction == "city-san-rafael"
        assert restored.topic == "housing"
        assert restored.verification_status == "VERIFIED"
        assert restored.data_sources == ["perplexity", "city website"]
        assert restored.programs["home"].program_name == "HOME"
        assert restored.programs["home"].annual_funding_available == 500_000.0
        assert restored.programs["home"].annual_reporting is True
        assert restored.ballot_measures["measure-p"].annual_revenue == 5_000_000.0
        assert restored.ballot_measures["measure-p"].status == "passed"
