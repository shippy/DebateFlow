"""Typer CLI entry point for DebateFlow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml
from dotenv import load_dotenv

from models import DebateCategory, ModelConfig

load_dotenv()

app = typer.Typer(help="DebateFlow — synthetic debate generation pipeline")

OUTPUT_DIR = Path("output/debates")
JSONL_PATH = Path("output/debateflow.jsonl")
RESOLUTIONS_PATH = Path("resolutions.yaml")


def _load_resolutions() -> tuple[list[dict], dict]:
    """Load resolutions and defaults from YAML."""
    with RESOLUTIONS_PATH.open() as f:
        data = yaml.safe_load(f)
    return data["resolutions"], data["defaults"]


@app.command()
def generate(
    n: Annotated[int, typer.Option("-n", help="Number of debates to generate")] = 1,
    aff_provider: Annotated[Optional[str], typer.Option(help="Aff LLM provider")] = None,
    aff_model: Annotated[Optional[str], typer.Option(help="Aff model name")] = None,
    neg_provider: Annotated[Optional[str], typer.Option(help="Neg LLM provider")] = None,
    neg_model: Annotated[Optional[str], typer.Option(help="Neg model name")] = None,
    control_ratio: Annotated[float, typer.Option(help="Fraction of control debates")] = 0.2,
    category: Annotated[Optional[str], typer.Option(help="Filter by category: policy|values|empirical")] = None,
    resolution: Annotated[Optional[str], typer.Option("-r", help="Use a specific resolution")] = None,
) -> None:
    """Generate synthetic debates."""
    from generator import generate_batch

    resolutions, defaults = _load_resolutions()

    aff_config = ModelConfig(
        provider=aff_provider or defaults["aff"]["provider"],
        model_name=aff_model or defaults["aff"]["model_name"],
        temperature=defaults["aff"].get("temperature", 0.7),
    )
    neg_config = ModelConfig(
        provider=neg_provider or defaults["neg"]["provider"],
        model_name=neg_model or defaults["neg"]["model_name"],
        temperature=defaults["neg"].get("temperature", 0.7),
    )

    cat_filter = DebateCategory(category) if category else None

    written = generate_batch(
        resolutions=resolutions,
        aff_config=aff_config,
        neg_config=neg_config,
        n=n,
        output_dir=OUTPUT_DIR,
        control_ratio=control_ratio,
        category_filter=cat_filter,
        resolution_override=resolution,
    )

    typer.echo(f"\nGenerated {len(written)} debate(s) in {OUTPUT_DIR}/")


@app.command()
def compile() -> None:
    """Compile individual debate JSONs into a single JSONL file."""
    from compile import compile_to_jsonl

    compile_to_jsonl(OUTPUT_DIR, JSONL_PATH)


@app.command()
def stats() -> None:
    """Show dataset statistics."""
    from compile import show_stats

    show_stats(OUTPUT_DIR)


@app.command()
def publish(
    repo: Annotated[str, typer.Option(help="HuggingFace repo ID (e.g. user/debateflow)")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Generate card + JSONL without pushing")] = False,
) -> None:
    """Compile dataset and publish to HuggingFace Hub."""
    from publish import publish as do_publish

    do_publish(repo_id=repo, input_dir=OUTPUT_DIR, dry_run=dry_run)


if __name__ == "__main__":
    app()
