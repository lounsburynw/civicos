"""
Pydantic schemas for municipal funding program data.

These schemas define the structure of municipal funding data,
ensuring consistent output across different research providers
and municipalities.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    """Contact information for a department or program."""

    name: Optional[str] = Field(None, description="Contact name or title")
    phone: Optional[str] = Field(None, description="Phone number")
    email: Optional[str] = Field(None, description="Email address")
    address: Optional[str] = Field(None, description="Physical address")
    website: Optional[str] = Field(None, description="Website URL")
    hours: Optional[str] = Field(None, description="Office hours")


class FeeScheduleEntry(BaseModel):
    """A fee schedule entry with amount and effective date."""

    amount: float = Field(..., description="Fee amount")
    unit: str = Field(..., description="Unit (per unit, per sqft, etc.)")
    effective_date: Optional[str] = Field(None, description="Effective date")


class FundingProgram(BaseModel):
    """A municipal funding program."""

    program_name: str = Field(..., description="Official program name")
    administering_agency: str = Field(..., description="City department or agency")
    description: str = Field(..., description="Program description")

    eligible_activities: list[str] = Field(
        default_factory=list,
        description="Activities the program can fund",
    )

    eligibility_requirements: dict[str, str] = Field(
        default_factory=dict,
        description="Requirements to access the program",
    )

    annual_funding_available: Optional[float] = Field(
        None, description="Annual funding amount if known"
    )

    fee_schedule: Optional[dict[str, FeeScheduleEntry]] = Field(
        None, description="Fee schedule entries by fiscal year or type"
    )

    local_compliance_required: bool = Field(
        True, description="Whether local compliance is required"
    )

    annual_reporting: bool = Field(
        False, description="Whether annual reporting is required"
    )

    resident_input_opportunities: list[str] = Field(
        default_factory=list,
        description="Ways residents can provide input",
    )

    leverage_point: str = Field(
        "", description="How residents can leverage this program"
    )

    official_url: Optional[str] = Field(None, description="Official program URL")

    governing_ordinance: Optional[str] = Field(
        None, description="Municipal code section or ordinance"
    )

    governing_resolutions: list[str] = Field(
        default_factory=list,
        description="Related city council resolutions",
    )

    contact: Optional[ContactInfo] = Field(None, description="Contact information")

    keywords: list[str] = Field(
        default_factory=list,
        description="Search keywords for this program",
    )


class BallotMeasure(BaseModel):
    """A local ballot measure."""

    measure_name: str = Field(..., description="Measure identifier (e.g., 'Measure P')")
    title: str = Field(..., description="Full title of the measure")
    description: str = Field(..., description="What the measure does")
    election_date: Optional[str] = Field(None, description="Election date")
    status: str = Field(..., description="passed, failed, pending")
    annual_revenue: Optional[float] = Field(None, description="Annual revenue if passed")
    duration_years: Optional[int] = Field(None, description="Duration in years")
    tax_rate: Optional[str] = Field(None, description="Tax rate description")
    exemptions: list[str] = Field(default_factory=list, description="Available exemptions")
    official_url: Optional[str] = Field(None, description="Official information URL")


class RecentFundingAward(BaseModel):
    """A recent funding award or project."""

    project_name: str = Field(..., description="Project or award name")
    description: str = Field(..., description="Description of what was funded")
    amount: Optional[float] = Field(None, description="Funding amount")
    status: str = Field(..., description="Status (awarded, in development, etc.)")


class IncomeLimit(BaseModel):
    """Income limit by household size."""

    one_person: int
    two_person: int
    three_person: int
    four_person: int


class IncomeLimits(BaseModel):
    """Area income limits for housing programs."""

    area: str = Field(..., description="HUD area name")
    median_family_income_4person: int = Field(..., description="Median family income for 4-person household")
    extremely_low_30_ami: IncomeLimit
    very_low_50_ami: IncomeLimit
    low_80_ami: IncomeLimit
    effective_date: str
    note: Optional[str] = None


class MunicipalFundingPrograms(BaseModel):
    """Complete municipal funding programs data."""

    jurisdiction: str = Field(..., description="Jurisdiction ID (e.g., 'city-san-rafael')")
    jurisdiction_type: str = Field("municipal", description="Type of jurisdiction")
    topic: str = Field(..., description="Topic area (housing, transportation, etc.)")

    last_updated: datetime = Field(default_factory=datetime.now)

    data_sources: list[str] = Field(
        default_factory=list,
        description="Sources used to compile this data",
    )

    verification_status: str = Field(
        "DRAFT - NOT VERIFIED",
        description="Verification status of the data",
    )

    source_citations: list[str] = Field(
        default_factory=list,
        description="URLs cited as sources",
    )

    programs: dict[str, FundingProgram] = Field(
        default_factory=dict,
        description="Funding programs by ID",
    )

    ballot_measures: dict[str, BallotMeasure] = Field(
        default_factory=dict,
        description="Related ballot measures by ID",
    )

    recent_funding_awards: dict[str, RecentFundingAward] = Field(
        default_factory=dict,
        description="Recent funding awards",
    )

    income_limits: Optional[IncomeLimits] = Field(
        None, description="Area income limits"
    )

    contact_information: dict[str, ContactInfo] = Field(
        default_factory=dict,
        description="Department contact information",
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
