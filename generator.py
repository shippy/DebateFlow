"""Core 4-turn debate generation pipeline."""

from __future__ import annotations

import random
from pathlib import Path

from rich.console import Console

from models import (
    ConstraintInfo,
    Debate,
    DebateCategory,
    DebateMetadata,
    ModelConfig,
    Side,
    Turn,
    TurnRole,
    WeaknessType,
)
from prompts import build_system_prompt, build_user_prompt
from providers import make_agent

console = Console()

# Turn sequence: (speaker, role)
TURN_SEQUENCE: list[tuple[Side, TurnRole]] = [
    (Side.AFF, "opening"),
    (Side.NEG, "response"),
    (Side.AFF, "rebuttal"),
    (Side.NEG, "closing"),
]


def generate_single_debate(
    resolution: str,
    category: DebateCategory,
    aff_config: ModelConfig,
    neg_config: ModelConfig,
    constraint: ConstraintInfo,
) -> Debate:
    """Generate a single 4-turn debate.

    Turns are generated sequentially — each depends on prior turns.
    """
    is_control = constraint.type is None
    metadata = DebateMetadata(
        resolution=resolution,
        category=category,
        aff_model=aff_config,
        neg_model=neg_config,
        constraint=constraint,
        is_control=is_control,
    )

    turns: list[Turn] = []

    for speaker, role in TURN_SEQUENCE:
        config = aff_config if speaker == Side.AFF else neg_config

        system_prompt = build_system_prompt(
            side=speaker,
            weakness=constraint.type,
            target_side=constraint.target_side,
            role=role,
        )

        previous = [
            {"speaker": t.speaker.value, "role": t.role, "text": t.text}
            for t in turns
        ]
        user_prompt = build_user_prompt(resolution, role, previous)

        agent = make_agent(config, system_prompt)
        result = agent.run_sync(user_prompt)

        turns.append(Turn(speaker=speaker, role=role, text=result.output))

        side_label = speaker.value.upper()
        console.print(f"  [dim]{side_label} {role}[/dim] — {len(result.output)} chars")

    return Debate(metadata=metadata, turns=turns)


def _pick_constraint(control_ratio: float) -> ConstraintInfo:
    """Randomly pick a constraint (or control)."""
    if random.random() < control_ratio:
        return ConstraintInfo()  # control: no weakness
    return ConstraintInfo(
        type=random.choice(list(WeaknessType)),
        target_side=random.choice([Side.AFF, Side.NEG]),
    )


def generate_batch(
    resolutions: list[dict],
    aff_config: ModelConfig,
    neg_config: ModelConfig,
    n: int,
    output_dir: Path,
    control_ratio: float = 0.2,
    category_filter: DebateCategory | None = None,
    resolution_override: str | None = None,
) -> list[Path]:
    """Generate n debates and write each as JSON to output_dir.

    Returns list of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Filter resolutions if category specified
    pool = resolutions
    if category_filter:
        pool = [r for r in resolutions if r["category"] == category_filter.value]
        if not pool:
            console.print(f"[red]No resolutions found for category '{category_filter.value}'[/red]")
            return written

    for i in range(n):
        if resolution_override:
            res_text = resolution_override
            # Try to match category from pool, default to policy
            cat = DebateCategory.POLICY
            for r in resolutions:
                if r["text"] == resolution_override:
                    cat = DebateCategory(r["category"])
                    break
        else:
            chosen = random.choice(pool)
            res_text = chosen["text"]
            cat = DebateCategory(chosen["category"])

        constraint = _pick_constraint(control_ratio)
        label = "control" if constraint.type is None else constraint.type.value
        console.print(
            f"\n[bold]Debate {i + 1}/{n}[/bold]: {res_text[:60]}{'...' if len(res_text) > 60 else ''} "
            f"[{'green' if constraint.type is None else 'yellow'}]{label}[/]"
        )

        debate = generate_single_debate(res_text, cat, aff_config, neg_config, constraint)

        filename = f"{debate.metadata.debate_id}.json"
        path = output_dir / filename
        path.write_text(debate.model_dump_json(indent=2))
        written.append(path)

        console.print(f"  [dim]Wrote {filename}[/dim]")

    return written
