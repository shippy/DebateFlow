"""HuggingFace Hub publication — compile + push_to_hub."""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from compile import compile_to_jsonl
from dataset_card import generate_card, load_debates_from_jsonl

console = Console()

JSONL_PATH = Path("output/debateflow.jsonl")


def _get_hf_token() -> str:
    """Read HuggingFace token from DF_HF_TOKEN env var."""
    token = os.environ.get("DF_HF_TOKEN")
    if not token:
        raise ValueError("Set DF_HF_TOKEN in your .env file or environment")
    return token


def publish(repo_id: str, input_dir: Path, dry_run: bool = False, private: bool = True) -> None:
    """Compile debates to JSONL, generate dataset card, and push to HuggingFace Hub.

    Args:
        repo_id: HuggingFace repo ID (e.g. "spodhajsky/debateflow")
        input_dir: Directory containing individual debate JSON files
        dry_run: If True, generate card + JSONL locally without pushing
    """
    # 1. Compile debates to JSONL
    count = compile_to_jsonl(input_dir, JSONL_PATH)
    if count == 0:
        console.print("[red]No debates to publish.[/red]")
        return

    # 2. Load compiled debates
    debates = load_debates_from_jsonl(JSONL_PATH)

    # 3. Generate dataset card
    card_content = generate_card(debates)
    card_path = Path("output/README.md")
    card_path.write_text(card_content)
    console.print(f"[green]Generated dataset card at {card_path}[/green]")

    if dry_run:
        console.print(f"\n[yellow]Dry run — not pushing to {repo_id}[/yellow]")
        console.print(f"  JSONL: {JSONL_PATH}")
        console.print(f"  Card:  {card_path}")
        return

    # 4. Push to Hub
    from datasets import Dataset
    from huggingface_hub import HfApi

    token = _get_hf_token()
    console.print(f"\n[bold]Pushing to {repo_id}...[/bold]")

    dataset = Dataset.from_json(str(JSONL_PATH))
    dataset.push_to_hub(repo_id, private=private, token=token)

    # Upload the dataset card
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(card_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
    )

    console.print(f"[green]Published to https://huggingface.co/datasets/{repo_id}[/green]")
