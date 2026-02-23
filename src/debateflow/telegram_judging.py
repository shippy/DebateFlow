"""Telegram judging flow for DebateFlow annotations."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydub import AudioSegment

from .voice import synthesize_debate

logger = logging.getLogger(__name__)

Side = Literal["AFF", "NEG"]
Dimension = Literal["clash", "burden_of_proof", "rebuttal", "extension", "adaptation"]


class TelegramJudgingSession:
    """Manages state for one annotation session."""

    def __init__(
        self,
        debates_dir: str = "output/debates",
        annotations_dir: str = "output/annotations",
        annotator_id: str = "SP",
    ):
        self.debates_dir = Path(debates_dir)
        self.annotations_dir = Path(annotations_dir)
        self.annotator_id = annotator_id
        self.annotations_dir.mkdir(parents=True, exist_ok=True)

        # Current annotation state
        self.current_debate_id: str | None = None
        self.scores: dict[Dimension, dict[Side, int]] = {}
        self.winner: Side | None = None
        self.justification: str = ""

    def get_next_debate(self) -> dict | None:
        """Return next unannotated debate dict, or None if all done."""
        debate_files = sorted(self.debates_dir.glob("*.json"))
        existing_annotations = {
            f.stem.replace(f"_{self.annotator_id}", "")
            for f in self.annotations_dir.glob(f"*_{self.annotator_id}.json")
        }

        for debate_file in debate_files:
            debate_id = debate_file.stem
            if debate_id not in existing_annotations:
                with open(debate_file) as f:
                    debate = json.load(f)
                self.current_debate_id = debate_id
                self._reset_state()
                return debate

        return None

    def prepare_audio(self, debate: dict) -> str:
        """Synthesize and stitch audio. Returns path to OGG file."""
        debate_id = debate["debate_id"]
        output_dir = Path("output/audio")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate MP3 audio for all turns
        audio_paths = synthesize_debate(
            debate=debate,
            output_dir=str(output_dir),
            stability=0.3,
            style_exaggeration=0.6,
        )

        # Load all turn audio files
        segments = []
        pause = AudioSegment.silent(duration=2000)  # 2 seconds

        for i in range(1, 5):  # 4 turns
            turn_key = f"turn_{i}"
            if turn_key not in audio_paths:
                raise ValueError(f"Missing audio for {turn_key}")

            turn_audio = AudioSegment.from_mp3(audio_paths[turn_key])
            segments.append(turn_audio)
            if i < 4:  # Add pause between turns
                segments.append(pause)

        # Stitch together
        full_debate = segments[0]
        for seg in segments[1:]:
            full_debate += seg

        # Export as OGG (Opus codec for Telegram voice notes)
        ogg_path = output_dir / f"{debate_id}_full.ogg"
        full_debate.export(str(ogg_path), format="ogg", codec="libopus")

        return str(ogg_path)

    def get_scoring_prompts(self, debate_id: str) -> list[dict]:
        """Return list of scoring prompt dicts with dimension, side, and button configs."""
        dimensions: list[Dimension] = [
            "clash",
            "burden_of_proof",
            "rebuttal",
            "extension",
            "adaptation",
        ]
        sides: list[Side] = ["AFF", "NEG"]

        prompts = []
        for dimension in dimensions:
            for side in sides:
                prompts.append(
                    {
                        "dimension": dimension,
                        "side": side,
                        "text": f"Score {dimension.replace('_', ' ').title()} - {side}:",
                        "buttons": [
                            {
                                "text": "Weak (1)",
                                "callback_data": f"score:{debate_id}:{dimension}:{side}:1",
                            },
                            {
                                "text": "OK (2)",
                                "callback_data": f"score:{debate_id}:{dimension}:{side}:2",
                            },
                            {
                                "text": "Strong (3)",
                                "callback_data": f"score:{debate_id}:{dimension}:{side}:3",
                            },
                        ],
                    }
                )

        return prompts

    def record_score(self, debate_id: str, dimension: Dimension, side: Side, value: int):
        """Record a single dimension score."""
        if debate_id != self.current_debate_id:
            raise ValueError(f"Score for wrong debate: {debate_id} != {self.current_debate_id}")

        if dimension not in self.scores:
            self.scores[dimension] = {}

        self.scores[dimension][side] = value
        logger.info(f"Recorded score: {dimension}/{side} = {value}")

    def record_winner(self, debate_id: str, side: Side):
        """Record winner selection."""
        if debate_id != self.current_debate_id:
            raise ValueError(f"Winner for wrong debate: {debate_id} != {self.current_debate_id}")

        self.winner = side
        logger.info(f"Recorded winner: {side}")

    def record_justification(self, debate_id: str, text: str):
        """Record text justification."""
        if debate_id != self.current_debate_id:
            raise ValueError(f"Justification for wrong debate: {debate_id} != {self.current_debate_id}")

        self.justification = text
        logger.info(f"Recorded justification: {len(text)} chars")

    def save_annotation(self, debate_id: str) -> str:
        """Save completed annotation to JSON. Returns file path."""
        if debate_id != self.current_debate_id:
            raise ValueError(f"Save for wrong debate: {debate_id} != {self.current_debate_id}")

        if not self.winner:
            raise ValueError("Cannot save annotation without winner selection")

        annotation = {
            "debate_id": debate_id,
            "annotator": self.annotator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scores": {
                dim: {"AFF": self.scores[dim].get("AFF", 0), "NEG": self.scores[dim].get("NEG", 0)}
                for dim in self.scores
            },
            "winner": self.winner,
            "justification": self.justification,
        }

        output_path = self.annotations_dir / f"{debate_id}_{self.annotator_id}.json"
        with open(output_path, "w") as f:
            json.dump(annotation, f, indent=2)

        logger.info(f"Saved annotation: {output_path}")
        return str(output_path)

    def _reset_state(self):
        """Reset annotation state for new debate."""
        self.scores = {}
        self.winner = None
        self.justification = ""
