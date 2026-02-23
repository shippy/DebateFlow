"""Typer CLI entry point for DebateFlow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml
from dotenv import load_dotenv

from models import DebateCategory, ModelConfig, WeaknessType

load_dotenv()

app = typer.Typer(help="DebateFlow — synthetic debate generation pipeline")

OUTPUT_DIR = Path("output/debates")
ANNOTATIONS_DIR = Path("output/annotations")
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
    weakness: Annotated[Optional[str], typer.Option(help="Force weakness type: weak_evidence|argument_dropping|logical_gaps|burden_of_proof")] = None,
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
    weakness_override = WeaknessType(weakness) if weakness else None

    written = generate_batch(
        resolutions=resolutions,
        aff_config=aff_config,
        neg_config=neg_config,
        n=n,
        output_dir=OUTPUT_DIR,
        control_ratio=control_ratio,
        category_filter=cat_filter,
        resolution_override=resolution,
        weakness_override=weakness_override,
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
    repo: Annotated[Optional[str], typer.Option(help="HuggingFace repo ID (e.g. user/debateflow)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Generate card + JSONL without pushing")] = False,
    public: Annotated[bool, typer.Option("--public", help="Make the dataset public (default: private)")] = False,
) -> None:
    """Compile dataset and publish to HuggingFace Hub."""
    import os

    from publish import publish as do_publish

    repo_id = repo or os.environ.get("DF_HF_REPO")
    if not repo_id:
        typer.echo("Error: provide --repo or set DF_HF_REPO in .env", err=True)
        raise typer.Exit(1)

    do_publish(repo_id=repo_id, input_dir=OUTPUT_DIR, dry_run=dry_run, private=not public)


@app.command()
def annotate_status() -> None:
    """Show annotation progress — which debates are annotated, by whom."""
    from agreement import load_annotations
    from models import Debate

    # Load debates
    debate_ids: dict[str, str] = {}
    if OUTPUT_DIR.exists():
        for p in sorted(OUTPUT_DIR.glob("*.json")):
            d = Debate.model_validate_json(p.read_text())
            debate_ids[d.metadata.debate_id] = d.metadata.resolution

    # Load annotations
    annotations = load_annotations(ANNOTATIONS_DIR)
    annotated: dict[str, list[str]] = {}
    for ann in annotations:
        annotated.setdefault(ann.debate_id, []).append(ann.annotator_id)

    typer.echo(f"Debates: {len(debate_ids)}  |  Annotations: {len(annotations)}")
    typer.echo("")

    if not debate_ids:
        typer.echo("No debates found in output/debates/")
        return

    for did, res in debate_ids.items():
        short_res = res[:60] + ("..." if len(res) > 60 else "")
        annotators = annotated.get(did, [])
        if annotators:
            who = ", ".join(sorted(annotators))
            typer.echo(f"  [{did}] {short_res}  — annotated by: {who}")
        else:
            typer.echo(f"  [{did}] {short_res}  — not annotated")

    n_annotated = sum(1 for did in debate_ids if did in annotated)
    typer.echo(f"\nCoverage: {n_annotated}/{len(debate_ids)} debates annotated")


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port to listen on")] = 5733,
) -> None:
    """Start the annotation server with on-demand TTS."""
    import uvicorn

    typer.echo(f"Starting DebateFlow server on http://localhost:{port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")


@app.command()
def annotate_agreement() -> None:
    """Compute inter-annotator agreement (requires 2+ annotators on same debates)."""
    from agreement import compute_agreement, load_annotations

    annotations = load_annotations(ANNOTATIONS_DIR)
    if not annotations:
        typer.echo("No annotations found in output/annotations/")
        raise typer.Exit(1)

    result = compute_agreement(annotations)

    if result["paired_debates"] == 0:
        typer.echo("No debates with 2 annotators found. Need overlapping annotations.")
        raise typer.Exit(1)

    typer.echo(f"Paired debates: {result['paired_debates']}")
    typer.echo(f"Winner kappa:   {result['winner_kappa']:.3f}")
    typer.echo("")
    typer.echo("Per-dimension kappa (aff / neg):")
    dim_agreement: dict[str, dict[str, float]] = result["dimension_agreement"]  # type: ignore[assignment]
    for dim, scores in dim_agreement.items():
        typer.echo(f"  {dim:25s}  {scores['aff_kappa']:.3f} / {scores['neg_kappa']:.3f}")


if __name__ == "__main__":
    app()
