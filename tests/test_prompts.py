"""Tests for prompt construction and weakness injection."""

from debateflow.models import Side, WeaknessType
from debateflow.prompts import (
    TURN_INSTRUCTIONS,
    WEAKNESS_TEMPLATES,
    build_system_prompt,
    build_user_prompt,
)


def test_base_prompt_contains_side():
    prompt = build_system_prompt(Side.AFF, weakness=None, target_side=None, role="opening")
    assert "FAVOR" in prompt
    prompt = build_system_prompt(Side.NEG, weakness=None, target_side=None, role="opening")
    assert "AGAINST" in prompt


def test_no_weakness_on_unconstrained_side():
    prompt = build_system_prompt(
        Side.AFF,
        weakness=WeaknessType.WEAK_EVIDENCE,
        target_side=Side.NEG,  # NEG is constrained, not AFF
        role="opening",
    )
    assert "CONSTRAINT" not in prompt


def test_weakness_injected_on_constrained_side():
    for wt in WeaknessType:
        # Use a role where all weaknesses apply
        role = "response" if wt == WeaknessType.ARGUMENT_DROPPING else "opening"
        prompt = build_system_prompt(
            Side.NEG,
            weakness=wt,
            target_side=Side.NEG,
            role=role,
        )
        assert "CONSTRAINT" in prompt, f"Missing constraint for {wt}"


def test_argument_dropping_skipped_only_for_opening():
    # Opening — should NOT get argument_dropping (no opponent args yet)
    prompt = build_system_prompt(
        Side.AFF,
        weakness=WeaknessType.ARGUMENT_DROPPING,
        target_side=Side.AFF,
        role="opening",
    )
    assert "CONSTRAINT" not in prompt

    # Rebuttal — SHOULD get it (Aff rebuttal follows opponent speeches)
    prompt = build_system_prompt(
        Side.AFF,
        weakness=WeaknessType.ARGUMENT_DROPPING,
        target_side=Side.AFF,
        role="rebuttal",
    )
    assert "CONSTRAINT" in prompt

    # Response — SHOULD get it
    prompt = build_system_prompt(
        Side.NEG,
        weakness=WeaknessType.ARGUMENT_DROPPING,
        target_side=Side.NEG,
        role="response",
    )
    assert "CONSTRAINT" in prompt

    # Closing — SHOULD get it
    prompt = build_system_prompt(
        Side.NEG,
        weakness=WeaknessType.ARGUMENT_DROPPING,
        target_side=Side.NEG,
        role="closing",
    )
    assert "CONSTRAINT" in prompt


def test_user_prompt_includes_resolution():
    prompt = build_user_prompt("Ban cars", "opening", [])
    assert "Ban cars" in prompt
    assert "opening" in prompt.lower() or "Opening" in prompt


def test_user_prompt_includes_history():
    history = [
        {"speaker": "aff", "role": "opening", "text": "Cars are bad."},
    ]
    prompt = build_user_prompt("Ban cars", "response", history)
    assert "Cars are bad." in prompt
    assert "Debate so far" in prompt


def test_user_prompt_no_history_for_opening():
    prompt = build_user_prompt("Ban cars", "opening", [])
    assert "Debate so far" not in prompt


def test_all_turn_roles_have_instructions():
    for role in ("opening", "response", "rebuttal", "closing"):
        assert role in TURN_INSTRUCTIONS


def test_all_weakness_types_have_templates():
    for wt in WeaknessType:
        assert wt in WEAKNESS_TEMPLATES
