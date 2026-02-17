"""Inter-annotator agreement computation for DebateFlow annotations."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from models import ANNOTATION_DIMENSIONS, Annotation


def load_annotations(annotations_dir: Path) -> list[Annotation]:
    """Load all annotation JSON files from a directory."""
    annotations: list[Annotation] = []
    if not annotations_dir.exists():
        return annotations
    for p in sorted(annotations_dir.glob("*.json")):
        annotations.append(Annotation.model_validate_json(p.read_text()))
    return annotations


def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Compute Cohen's kappa for two lists of categorical labels."""
    assert len(labels_a) == len(labels_b)
    n = len(labels_a)
    if n == 0:
        return 0.0

    categories = sorted(set(labels_a) | set(labels_b))
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    # Build confusion matrix
    matrix = [[0] * k for _ in range(k)]
    for a, b in zip(labels_a, labels_b):
        matrix[cat_to_idx[a]][cat_to_idx[b]] += 1

    # Observed agreement
    p_o = sum(matrix[i][i] for i in range(k)) / n

    # Expected agreement by chance
    p_e = sum(
        sum(matrix[i][j] for j in range(k)) * sum(matrix[j][i] for j in range(k))
        for i in range(k)
    ) / (n * n)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def compute_agreement(
    annotations: list[Annotation],
) -> dict[str, object]:
    """Compute inter-annotator agreement statistics.

    Groups annotations by debate_id and computes pairwise agreement
    for debates annotated by exactly 2 annotators.
    """
    # Group by debate_id
    by_debate: dict[str, list[Annotation]] = defaultdict(list)
    for ann in annotations:
        by_debate[ann.debate_id].append(ann)

    # Find debates with exactly 2 annotations from different annotators
    paired: list[tuple[Annotation, Annotation]] = []
    for debate_id, anns in sorted(by_debate.items()):
        if len(anns) == 2 and anns[0].annotator_id != anns[1].annotator_id:
            paired.append((anns[0], anns[1]))

    if not paired:
        return {"paired_debates": 0, "winner_kappa": None, "dimension_agreement": {}}

    # Winner agreement
    winners_a = [p[0].winner.value for p in paired]
    winners_b = [p[1].winner.value for p in paired]
    winner_kappa = _cohens_kappa(winners_a, winners_b)

    # Per-dimension agreement on 3-point scale
    dimension_agreement: dict[str, dict[str, float]] = {}
    for dim in ANNOTATION_DIMENSIONS:
        aff_a: list[str] = []
        aff_b: list[str] = []
        neg_a: list[str] = []
        neg_b: list[str] = []
        for ann_a, ann_b in paired:
            score_a = next(ds for ds in ann_a.dimension_scores if ds.dimension == dim)
            score_b = next(ds for ds in ann_b.dimension_scores if ds.dimension == dim)
            aff_a.append(str(score_a.aff_score))
            aff_b.append(str(score_b.aff_score))
            neg_a.append(str(score_a.neg_score))
            neg_b.append(str(score_b.neg_score))

        dimension_agreement[dim] = {
            "aff_kappa": _cohens_kappa(aff_a, aff_b),
            "neg_kappa": _cohens_kappa(neg_a, neg_b),
        }

    return {
        "paired_debates": len(paired),
        "winner_kappa": winner_kappa,
        "dimension_agreement": dimension_agreement,
    }
