"""Pydantic schema for what the extractor produces."""

from pydantic import BaseModel, Field, field_validator


class ExtractedDecision(BaseModel):
    """One decision extracted from one artifact."""

    claim: str = Field(
        ...,
        description="The decision in one sentence: 'chose X over Y because Z'.",
    )
    rationale: str | None = Field(
        None,
        description="Fuller reasoning if the artifact provides it.",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Files, modules, libraries, or concepts the decision touches.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extractor's self-reported confidence, 0.0-1.0.",
    )

    @field_validator("claim")
    @classmethod
    def _claim_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim must be non-empty")
        return v.strip()


class ExtractionResult(BaseModel):
    """Wraps the list of decisions for a single artifact.

    Wrapping in an object (rather than returning a bare list) gives us
    room to add fields later — e.g. an 'artifact_summary' without a
    breaking schema change.
    """

    decisions: list[ExtractedDecision] = Field(default_factory=list)