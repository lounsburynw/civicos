"""Provenance data models."""

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class KeyProvenance(BaseModel):
    """
    Provenance record for a public key.

    Tracks trust signals: key age, voice history, jurisdictions touched.
    MVP scope - no vouching or physical attestation yet.
    """

    public_key: str = Field(description="Public key (hex-encoded)")
    created_at: datetime = Field(description="When the key was first seen")
    total_voices: int = Field(default=0, description="Total voices cast by this key")
    entities_touched: int = Field(
        default=0, description="Unique entities this key has voiced on"
    )
    first_voice_at: Optional[datetime] = Field(
        default=None, description="When the first voice was cast"
    )
    last_voice_at: Optional[datetime] = Field(
        default=None, description="When the most recent voice was cast"
    )
    jurisdictions: list[str] = Field(
        default_factory=list, description="Jurisdictions this key has participated in"
    )

    @computed_field
    @property
    def age_days(self) -> int:
        """Days since key creation."""
        delta = datetime.utcnow() - self.created_at
        return delta.days

    @computed_field
    @property
    def is_new_key(self) -> bool:
        """Key is less than 7 days old."""
        return self.age_days < 7

    @computed_field
    @property
    def is_active(self) -> bool:
        """Has voiced in the last 30 days."""
        if not self.last_voice_at:
            return False
        return (datetime.utcnow() - self.last_voice_at) < timedelta(days=30)


class ProvenanceSummary(BaseModel):
    """Summary of provenance quality for display."""

    total_voices: int
    high_quality_voices: int = Field(description="Keys older than 30 days")
    new_key_voices: int = Field(description="Keys less than 7 days old")
    attested_voices: int = Field(default=0, description="Future: physically attested")

    @computed_field
    @property
    def quality_ratio(self) -> float:
        """Ratio of high-quality voices to total."""
        if self.total_voices == 0:
            return 0.0
        return self.high_quality_voices / self.total_voices
