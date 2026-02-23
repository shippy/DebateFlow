"""System prompts, turn instructions, and weakness injection templates."""

from __future__ import annotations

from .models import Side, WeaknessType

# ---------------------------------------------------------------------------
# Base system prompts (one per side)
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPTS: dict[Side, str] = {
    Side.AFF: (
        "You are the AFFIRMATIVE debater. You argue IN FAVOR of the resolution "
        "— you believe it is true and should be adopted. "
        "Present clear, well-structured arguments. Do not include meta-commentary "
        "about the debate itself — speak as if delivering a speech in a live round. "
        "Each speech should be 200–400 words."
    ),
    Side.NEG: (
        "You are the NEGATIVE debater. You argue AGAINST the resolution "
        "— you believe it is false or should be rejected. "
        "Present clear, well-structured arguments. Do not include meta-commentary "
        "about the debate itself — speak as if delivering a speech in a live round. "
        "Each speech should be 200–400 words."
    ),
}

# ---------------------------------------------------------------------------
# Per-role turn instructions (appended to user prompt)
# ---------------------------------------------------------------------------

TURN_INSTRUCTIONS: dict[str, str] = {
    "opening": (
        "This is your opening constructive speech as the {side_name}. Present your "
        "strongest arguments and establish the framework for the debate. Define key "
        "terms if necessary and lay out the criteria by which the resolution should "
        "be evaluated."
    ),
    "response": (
        "This is your response speech as the {side_name}. You must directly engage "
        "with your opponent's opening arguments — refute their key claims and present "
        "your own counter-arguments. Do not simply repeat your own position; show why "
        "the opponent's case fails."
    ),
    "rebuttal": (
        "This is your rebuttal speech as the {side_name}. Defend your arguments "
        "against the opponent's attacks, expose weaknesses in the opponent's case, "
        "and extend your strongest points with additional reasoning or evidence."
    ),
    "closing": (
        "This is your closing speech as the {side_name}. Summarize the key clashes "
        "in the debate and explain why the {side_name} has won each one. Weigh the "
        "most important arguments and give the judge clear reasons to vote for the "
        "{side_name}."
    ),
}

# ---------------------------------------------------------------------------
# Weakness injection templates (appended to system prompt on constrained turns)
# ---------------------------------------------------------------------------

WEAKNESS_TEMPLATES: dict[WeaknessType, str] = {
    WeaknessType.WEAK_EVIDENCE: (
        "IMPORTANT CONSTRAINT: In this speech, rely primarily on anecdotal evidence, "
        "vague references to unnamed authorities ('experts say', 'studies show'), and "
        "hedging language. Your argument structure should remain coherent and your "
        "rhetoric confident, but the underlying evidence should be noticeably weak "
        "upon close inspection. Do not flag or acknowledge the weakness of your evidence."
    ),
    WeaknessType.ARGUMENT_DROPPING: (
        "IMPORTANT CONSTRAINT: In this speech, ignore one or two of your opponent's "
        "key arguments entirely. Do not acknowledge that you are skipping them — simply "
        "do not address them. Focus on other points instead. Your speech should still "
        "sound complete and confident, but an attentive observer should notice that "
        "significant opposing arguments went unanswered."
    ),
    WeaknessType.LOGICAL_GAPS: (
        "IMPORTANT CONSTRAINT: In this speech, include one or two logical fallacies "
        "such as hasty generalization, false dichotomy, or non-sequitur. The surface "
        "rhetoric should remain confident and polished, but the logical connections "
        "between your premises and conclusions should contain noticeable gaps upon "
        "careful analysis. Do not label or call attention to the fallacies."
    ),
    WeaknessType.BURDEN_OF_PROOF: (
        "IMPORTANT CONSTRAINT: In this speech, make key assertions without adequate "
        "support and shift the burden of proof to your opponent. Use phrases like "
        "'unless they can show otherwise' or 'it is obvious that' without providing "
        "sufficient justification. Your tone should be confident, but your core claims "
        "should lack the evidential foundation they require. Do not acknowledge this gap."
    ),
    WeaknessType.SIDE_CONCESSION: (
        "IMPORTANT CONSTRAINT: In this speech, gradually drift toward agreeing with "
        "your opponent's position. Start by acknowledging their strongest points, then "
        "subtly adopt their framing and reasoning. By the end of your speech, your "
        "conclusion should effectively support the opponent's side rather than your own "
        "— but present this as if you believe you are still arguing your assigned "
        "position. Do not explicitly announce that you are switching sides."
    ),
}


def build_system_prompt(
    side: Side,
    weakness: WeaknessType | None,
    target_side: Side | None,
    role: str,
) -> str:
    """Build the full system prompt for a given turn.

    Weakness injection is applied only when:
    - This side is the constrained side
    - For argument_dropping: only on turns that follow an opponent speech (not opening)
    """
    prompt = BASE_SYSTEM_PROMPTS[side]

    if weakness and target_side == side:
        # argument_dropping and side_concession only apply after opponent has spoken
        if weakness in (WeaknessType.ARGUMENT_DROPPING, WeaknessType.SIDE_CONCESSION) and role == "opening":
            return prompt
        prompt += "\n\n" + WEAKNESS_TEMPLATES[weakness]

    return prompt


_SIDE_LABELS: dict[Side, tuple[str, str]] = {
    Side.AFF: ("AFFIRMATIVE", "IN FAVOR OF"),
    Side.NEG: ("NEGATIVE", "AGAINST"),
}


def build_user_prompt(
    resolution: str,
    role: str,
    previous_turns: list[dict[str, str]],
    *,
    side: Side,
) -> str:
    """Build the user prompt with resolution, role instructions, and debate history.

    previous_turns: list of dicts with 'speaker', 'role', 'text' keys.
    """
    side_name, stance = _SIDE_LABELS[side]

    parts: list[str] = [f"Resolution: {resolution}"]

    parts.append(
        f"You are the {side_name}. You argue {stance} the resolution."
    )

    if previous_turns:
        parts.append("\n--- Debate so far ---")
        for turn in previous_turns:
            label = f"[{turn['speaker'].upper()} — {turn['role']}]"
            parts.append(f"{label}\n{turn['text']}")
        parts.append("--- End of debate so far ---\n")

    parts.append(TURN_INSTRUCTIONS[role].format(side_name=side_name))

    return "\n\n".join(parts)
