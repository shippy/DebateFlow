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

    def get_scoring_prompts(self, debate_id: str, category: str = "policy") -> list[dict]:
        """Return list of scoring prompt dicts with dimension, side, and button configs.

        Args:
            debate_id: The debate identifier.
            category: Debate category — "policy", "values", or "empirical".
                Controls the burden fulfillment guidance text.
        """
        dimension_defs: list[dict] = [
            {
                "key": "clash",
                "label": "Clash Engagement",
                "number": 1,
                "definition": "Did each side address the opponent's arguments or talk past them?",
                "prompts": {
                    "AFF": "Did the AFF address the opponent's arguments or talk past them?",
                    "NEG": "Did the NEG address the opponent's arguments or talk past them?",
                },
                "anchors": {
                    1: "Talked past the opponent entirely",
                    2: "Addressed the opponent's general thrust",
                    3: "Engaged with multiple specific arguments",
                },
            },
            {
                "key": "burden_of_proof",
                "label": "Burden Fulfillment",
                "number": 2,
                "definition": "Did each side adequately support their core claims and meet their argumentative obligations?",
                "prompts": {
                    "AFF": {
                        "policy": "Did AFF demonstrate a need for change and show the proposal solves it?",
                        "values": "Did AFF show that the value or principle they champion should take precedence?",
                        "empirical": "Did AFF provide sufficient evidence that the claim is true?",
                    },
                    "NEG": {
                        "policy": "Did NEG defend the status quo or show the proposal causes more harm?",
                        "values": "Did NEG show the competing value takes priority or that AFF's framing is flawed?",
                        "empirical": "Did NEG provide sufficient evidence that the claim is false or unsupported?",
                    },
                },
                "anchors": {
                    1: "Side-specific obligations unaddressed",
                    2: "Attempted their burden but left notable gaps",
                    3: "Each element of their burden clearly covered",
                },
            },
            {
                "key": "rebuttal",
                "label": "Rebuttal Quality",
                "number": 3,
                "definition": "Specificity and depth of refutations — targeting weak premises vs. asserting disagreement.",
                "prompts": {
                    "AFF": "How specific and deep were the AFF's refutations?",
                    "NEG": "How specific and deep were the NEG's refutations?",
                },
                "anchors": {
                    1: "Mere contradiction (\"that's wrong\")",
                    2: "Challenged conclusions but not underlying reasoning",
                    3: "Identified and attacked a specific weak premise",
                },
            },
            {
                "key": "extension",
                "label": "Argument Extension",
                "number": 4,
                "definition": "Did arguments develop across turns, or merely repeat the opening?",
                "prompts": {
                    "AFF": "Did the AFF's arguments develop across turns or just repeat?",
                    "NEG": "Did the NEG's arguments develop across turns or just repeat?",
                },
                "anchors": {
                    1: "Repeated opening arguments verbatim",
                    2: "Some new framing but no substantive new material",
                    3: "Added new evidence or reasoning that advanced the case",
                },
            },
            {
                "key": "adaptation",
                "label": "Strategic Adaptation",
                "number": 5,
                "definition": "Did speakers adjust their approach based on the opponent's actual moves?",
                "prompts": {
                    "AFF": "Did the AFF adjust their approach based on the NEG's moves?",
                    "NEG": "Did the NEG adjust their approach based on the AFF's moves?",
                },
                "anchors": {
                    1: "Could have been written without hearing the opponent",
                    2: "Some responsiveness but core approach unchanged",
                    3: "Clearly shifted priorities based on how the debate unfolded",
                },
            },
        ]

        sides: list[Side] = ["AFF", "NEG"]
        prompts = []

        for dim in dimension_defs:
            for side in sides:
                # Build the prompt text
                side_prompt = dim["prompts"][side]
                anchors = dim.get("anchors", {})
                anchor_lines = (
                    f"\n\n\u274c {anchors.get(1, '')}\n"
                    f"\u2796 {anchors.get(2, '')}\n"
                    f"\u2705 {anchors.get(3, '')}"
                    if anchors
                    else ""
                )

                if isinstance(side_prompt, dict):
                    # Category-specific (burden fulfillment)
                    side_prompt = side_prompt.get(category, side_prompt.get("policy", ""))
                    text = (
                        f"\U0001f4ca {dim['number']}/5 \u2014 {dim['label']}\n\n"
                        f"{dim['definition']}\n\n"
                        f"For this {category} debate:\n"
                        f"{side_prompt}"
                        f"{anchor_lines}"
                    )
                else:
                    text = (
                        f"\U0001f4ca {dim['number']}/5 \u2014 {dim['label']}\n\n"
                        f"{side_prompt}"
                        f"{anchor_lines}"
                    )

                prompts.append(
                    {
                        "dimension": dim["key"],
                        "side": side,
                        "text": text,
                        "buttons": [
                            {
                                "text": "Weak \u274c",
                                "callback_data": f"score:{debate_id}:{dim['key']}:{side}:1",
                            },
                            {
                                "text": "OK \u2796",
                                "callback_data": f"score:{debate_id}:{dim['key']}:{side}:2",
                            },
                            {
                                "text": "Strong \u2705",
                                "callback_data": f"score:{debate_id}:{dim['key']}:{side}:3",
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
