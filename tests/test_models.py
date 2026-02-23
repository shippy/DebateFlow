"""Tests for DebateFlow data models — serialization roundtrips."""

import json

import pytest

from debateflow.models import (
    ANNOTATION_DIMENSIONS,
    Annotation,
    ConstraintInfo,
    Debate,
    DebateCategory,
    DebateMetadata,
    DimensionScore,
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


# --- Annotation model tests ---


def _make_annotation(
    *,
    debate_id: str = "abc12345",
    annotator_id: str = "SP",
    winner: Side = Side.AFF,
) -> Annotation:
    """Helper to build a valid Annotation instance."""
    from datetime import datetime, timezone

    return Annotation(
        debate_id=debate_id,
        annotator_id=annotator_id,
        winner=winner,
        winner_justification="Aff had stronger rebuttal and extended arguments well.",
        dimension_scores=[
            DimensionScore(dimension=dim, aff_score=2, neg_score=1)
            for dim in ANNOTATION_DIMENSIONS
        ],
        annotated_at=datetime.now(timezone.utc),
    )


def test_annotation_roundtrip():
    ann = _make_annotation()
    json_str = ann.model_dump_json()
    restored = Annotation.model_validate_json(json_str)
    assert restored.debate_id == ann.debate_id
    assert restored.annotator_id == ann.annotator_id
    assert restored.winner == Side.AFF
    assert len(restored.dimension_scores) == 5
    assert restored.annotation_version == "0.1.0"


def test_annotation_json_dict_roundtrip():
    ann = _make_annotation()
    d = ann.model_dump(mode="json")
    json_str = json.dumps(d)
    restored = Annotation.model_validate_json(json_str)
    assert restored == ann


def test_dimension_score_range():
    """Scores must be 1-3."""
    with pytest.raises(Exception):
        DimensionScore(dimension="clash_engagement", aff_score=0, neg_score=1)
    with pytest.raises(Exception):
        DimensionScore(dimension="clash_engagement", aff_score=1, neg_score=4)


def test_dimension_score_invalid_name():
    """Dimension name must be from the known list."""
    with pytest.raises(Exception):
        DimensionScore(dimension="made_up_dimension", aff_score=2, neg_score=2)


def test_annotation_wrong_number_of_dimensions():
    """Must have exactly 5 dimension scores."""
    from datetime import datetime, timezone

    with pytest.raises(Exception):
        Annotation(
            debate_id="abc12345",
            annotator_id="SP",
            winner=Side.AFF,
            winner_justification="Test",
            dimension_scores=[
                DimensionScore(dimension=dim, aff_score=2, neg_score=2)
                for dim in ANNOTATION_DIMENSIONS[:3]
            ],
            annotated_at=datetime.now(timezone.utc),
        )


def test_annotation_duplicate_dimensions():
    """Dimensions must be the correct set, no duplicates."""
    from datetime import datetime, timezone

    with pytest.raises(Exception):
        Annotation(
            debate_id="abc12345",
            annotator_id="SP",
            winner=Side.AFF,
            winner_justification="Test",
            dimension_scores=[
                DimensionScore(dimension="clash_engagement", aff_score=2, neg_score=2)
                for _ in range(5)
            ],
            annotated_at=datetime.now(timezone.utc),
        )


def test_all_annotation_dimensions():
    """All defined dimensions are valid."""
    for dim in ANNOTATION_DIMENSIONS:
        ds = DimensionScore(dimension=dim, aff_score=1, neg_score=3)
        assert ds.dimension == dim
