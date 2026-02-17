"""Pydantic data models for DebateFlow synthetic debate generation and annotation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DebateCategory(str, Enum):
    """Resolution topic category."""

    POLICY = "policy"
    VALUES = "values"
    EMPIRICAL = "empirical"


class WeaknessType(str, Enum):
    """Injected weakness type for constrained debates."""

    WEAK_EVIDENCE = "weak_evidence"
    ARGUMENT_DROPPING = "argument_dropping"
    LOGICAL_GAPS = "logical_gaps"
    BURDEN_OF_PROOF = "burden_of_proof"


class Side(str, Enum):
    """Debate side."""

    AFF = "aff"
    NEG = "neg"


TurnRole = Literal["opening", "response", "rebuttal", "closing"]


class Turn(BaseModel):
    """A single speech in a debate."""

    speaker: Side
    role: TurnRole
    text: str


class ModelConfig(BaseModel):
    """LLM configuration for a debate side."""

    provider: str  # "anthropic" | "openai"
    model_name: str  # e.g. "claude-sonnet-4-20250514"
    temperature: float = 0.7


class ConstraintInfo(BaseModel):
    """Describes the injected weakness (or lack thereof for controls)."""

    type: WeaknessType | None = None
    target_side: Side | None = None


class DebateMetadata(BaseModel):
    """Full metadata for a generated debate."""

    debate_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    resolution: str
    category: DebateCategory
    aff_model: ModelConfig
    neg_model: ModelConfig
    constraint: ConstraintInfo
    is_control: bool
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generator_version: str = "0.1.0"


class Debate(BaseModel):
    """A complete 4-turn debate with metadata."""

    metadata: DebateMetadata
    turns: list[Turn]

    @field_validator("turns")
    @classmethod
    def exactly_four_turns(cls, v: list[Turn]) -> list[Turn]:
        if len(v) != 4:
            raise ValueError(f"Debate must have exactly 4 turns, got {len(v)}")
        return v


ANNOTATION_DIMENSIONS = [
    "clash_engagement",
    "burden_fulfillment",
    "rebuttal_quality",
    "argument_extension",
    "strategic_adaptation",
]


class DimensionScore(BaseModel):
    """Score for a single rubric dimension, per side."""

    dimension: str
    aff_score: int = Field(ge=1, le=3)
    neg_score: int = Field(ge=1, le=3)

    @field_validator("dimension")
    @classmethod
    def valid_dimension(cls, v: str) -> str:
        if v not in ANNOTATION_DIMENSIONS:
            raise ValueError(
                f"Unknown dimension '{v}', must be one of {ANNOTATION_DIMENSIONS}"
            )
        return v


class Annotation(BaseModel):
    """Human annotation for a single debate."""

    debate_id: str
    annotator_id: str
    winner: Side
    winner_justification: str
    dimension_scores: list[DimensionScore]
    annotated_at: datetime
    annotation_version: str = "0.1.0"

    @field_validator("dimension_scores")
    @classmethod
    def exactly_five_dimensions(
        cls, v: list[DimensionScore],
    ) -> list[DimensionScore]:
        if len(v) != 5:
            raise ValueError(
                f"Must have exactly 5 dimension scores, got {len(v)}"
            )
        names = [ds.dimension for ds in v]
        if sorted(names) != sorted(ANNOTATION_DIMENSIONS):
            raise ValueError(
                f"Dimensions must be exactly {ANNOTATION_DIMENSIONS}, got {names}"
            )
        return v
