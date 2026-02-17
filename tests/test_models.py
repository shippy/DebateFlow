"""Tests for DebateFlow data models — serialization roundtrips."""

import json

from models import (
    ConstraintInfo,
    Debate,
    DebateCategory,
    DebateMetadata,
    ModelConfig,
    Side,
    Turn,
    WeaknessType,
)


def _make_debate(*, is_control: bool = False, weakness: WeaknessType | None = None) -> Debate:
    """Helper to build a valid Debate instance."""
    constraint = ConstraintInfo(
        type=None if is_control else weakness or WeaknessType.WEAK_EVIDENCE,
        target_side=None if is_control else Side.NEG,
    )
    model_cfg = ModelConfig(
        provider="anthropic",
        model_name="claude-sonnet-4-20250514",
        temperature=0.7,
    )
    metadata = DebateMetadata(
        resolution="This house would ban private car ownership in city centers",
        category=DebateCategory.POLICY,
        aff_model=model_cfg,
        neg_model=model_cfg,
        constraint=constraint,
        is_control=is_control,
    )
    turns = [
        Turn(speaker=Side.AFF, role="opening", text="Aff opening speech."),
        Turn(speaker=Side.NEG, role="response", text="Neg response speech."),
        Turn(speaker=Side.AFF, role="rebuttal", text="Aff rebuttal speech."),
        Turn(speaker=Side.NEG, role="closing", text="Neg closing speech."),
    ]
    return Debate(metadata=metadata, turns=turns)


def test_constrained_debate_roundtrip():
    debate = _make_debate(weakness=WeaknessType.LOGICAL_GAPS)
    json_str = debate.model_dump_json()
    restored = Debate.model_validate_json(json_str)
    assert restored.metadata.debate_id == debate.metadata.debate_id
    assert restored.metadata.constraint.type == WeaknessType.LOGICAL_GAPS
    assert restored.metadata.constraint.target_side == Side.NEG
    assert not restored.metadata.is_control
    assert len(restored.turns) == 4


def test_control_debate_roundtrip():
    debate = _make_debate(is_control=True)
    json_str = debate.model_dump_json()
    restored = Debate.model_validate_json(json_str)
    assert restored.metadata.is_control
    assert restored.metadata.constraint.type is None
    assert restored.metadata.constraint.target_side is None


def test_json_dict_roundtrip():
    debate = _make_debate()
    d = debate.model_dump(mode="json")
    json_str = json.dumps(d)
    restored = Debate.model_validate_json(json_str)
    assert restored == debate


def test_all_weakness_types():
    for wt in WeaknessType:
        debate = _make_debate(weakness=wt)
        assert debate.metadata.constraint.type == wt


def test_all_categories():
    for cat in DebateCategory:
        model_cfg = ModelConfig(provider="openai", model_name="gpt-4o")
        metadata = DebateMetadata(
            resolution="Test resolution",
            category=cat,
            aff_model=model_cfg,
            neg_model=model_cfg,
            constraint=ConstraintInfo(),
            is_control=True,
        )
        assert metadata.category == cat


def test_metadata_defaults():
    model_cfg = ModelConfig(provider="anthropic", model_name="claude-sonnet-4-20250514")
    metadata = DebateMetadata(
        resolution="Test",
        category=DebateCategory.POLICY,
        aff_model=model_cfg,
        neg_model=model_cfg,
        constraint=ConstraintInfo(),
        is_control=True,
    )
    assert len(metadata.debate_id) == 8
    assert metadata.generator_version == "0.1.0"
    assert metadata.generated_at is not None
