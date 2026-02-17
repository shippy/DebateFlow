"""JSONL compilation and dataset statistics."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.table import Table

from models import Debate

console = Console()


def compute_stats(debates: list[Debate]) -> dict:
    """Compute summary statistics for a list of debates."""
    weakness_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    control_count = 0

    for d in debates:
        category_counts[d.metadata.category.value] += 1
        if d.metadata.is_control:
            control_count += 1
            weakness_counts["control"] += 1
        else:
            assert d.metadata.constraint.type is not None
            assert d.metadata.constraint.target_side is not None
            weakness_counts[d.metadata.constraint.type.value] += 1
            side_counts[d.metadata.constraint.target_side.value] += 1

    return {
        "total": len(debates),
        "control": control_count,
        "constrained": len(debates) - control_count,
        "weakness_counts": dict(sorted(weakness_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "side_counts": dict(sorted(side_counts.items())),
    }


def compile_to_jsonl(
    input_dir: Path,
    output_path: Path,
) -> int:
    """Read all debate JSONs from input_dir, validate, write one-per-line JSONL.

    Returns count of debates written.
    """
    files = sorted(input_dir.glob("*.json"))
    if not files:
        console.print(f"[red]No JSON files found in {input_dir}[/red]")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w") as out:
        for f in files:
            debate = Debate.model_validate_json(f.read_text())
            out.write(debate.model_dump_json() + "\n")
            count += 1

    console.print(f"[green]Compiled {count} debates to {output_path}[/green]")
    return count


def show_stats(input_dir: Path) -> None:
    """Print dataset statistics from individual debate JSON files."""
    files = sorted(input_dir.glob("*.json"))
    if not files:
        console.print(f"[red]No JSON files found in {input_dir}[/red]")
        return

    debates = [Debate.model_validate_json(f.read_text()) for f in files]
    stats = compute_stats(debates)

    console.print(f"\n[bold]Dataset: {stats['total']} debates[/bold]\n")

    # Weakness distribution
    table = Table(title="Weakness Distribution")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")
    for wt, count in sorted(stats["weakness_counts"].items()):
        table.add_row(wt, str(count))
    console.print(table)

    # Category distribution
    table = Table(title="Category Distribution")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    for cat, count in sorted(stats["category_counts"].items()):
        table.add_row(cat, str(count))
    console.print(table)

    # Constrained side distribution
    if stats["side_counts"]:
        table = Table(title="Constrained Side Distribution")
        table.add_column("Side", style="cyan")
        table.add_column("Count", justify="right")
        for side, count in sorted(stats["side_counts"].items()):
            table.add_row(side, str(count))
        console.print(table)

    console.print(f"\nControl: {stats['control']} | Constrained: {stats['constrained']}")
