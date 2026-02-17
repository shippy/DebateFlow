"""Pydantic data models for DebateFlow synthetic debate generation."""

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
