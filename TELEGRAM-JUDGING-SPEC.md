# Telegram Judging Flow — Spec

## Overview

A Python module `src/debateflow/telegram_judging.py` that OpenClaw's Telegram bot calls to manage the debate annotation flow. This is NOT a standalone bot — it's a library that OpenClaw invokes.

## Flow

When a user sends `/debate` or "another debate" on Telegram:

1. **Pick next debate**: Scan `output/debates/` for JSON files, check `output/annotations/` to find unannotated ones. Pick the next one.
2. **Send resolution**: Return the debate resolution as a text message.
3. **Synthesize audio**: Use `voice.py` to generate TTS for all 4 turns, stitch into a single OGG/OPUS voice note with ~2s pauses between turns.
   - Voice settings for liveliness: stability=0.3, style_exaggeration=0.6
4. **Send voice note**: The stitched audio as a Telegram voice note.
5. **Scoring flow** (via inline buttons):
   - 5 dimensions: clash, burden_of_proof, rebuttal, extension, adaptation
   - 2 sides per dimension: AFF and NEG
   - Each gets: Weak (1) / OK (2) / Strong (3) buttons
   - Callback format: `score:{debate_id}:{dimension}:{side}:{value}`
6. **Winner pick**: Affirmative / Negative buttons → `winner:{debate_id}:{side}`
7. **Justification**: Ask for text justification (or Skip button)
8. **Save**: Write annotation to `output/annotations/{debate_id}_SP.json`
9. **Next**: Offer "Next debate?" button

## Module Interface

```python
class TelegramJudgingSession:
    """Manages state for one annotation session."""
    
    def __init__(self, debates_dir: str = "output/debates", 
                 annotations_dir: str = "output/annotations",
                 annotator_id: str = "SP"):
        ...
    
    def get_next_debate(self) -> dict | None:
        """Return next unannotated debate dict, or None if all done."""
        ...
    
    def prepare_audio(self, debate: dict) -> str:
        """Synthesize and stitch audio. Returns path to OGG file."""
        ...
    
    def get_scoring_prompts(self, debate_id: str) -> list[dict]:
        """Return list of scoring prompt dicts with dimension, side, and button configs."""
        ...
    
    def record_score(self, debate_id: str, dimension: str, side: str, value: int):
        """Record a single dimension score."""
        ...
    
    def record_winner(self, debate_id: str, side: str):
        """Record winner selection."""
        ...
    
    def record_justification(self, debate_id: str, text: str):
        """Record text justification."""
        ...
    
    def save_annotation(self, debate_id: str) -> str:
        """Save completed annotation to JSON. Returns file path."""
        ...
```

## Important Rules

- **Never reveal weakness_type or is_control** fields from the debate JSON when presenting to the annotator — this would bias the evaluation.
- Audio output must be OGG/OPUS format for Telegram voice notes.
- Use `voice.py` functions for TTS — don't duplicate that logic.

## File Structure

```
src/debateflow/telegram_judging.py   # Main module
output/annotations/{debate_id}_SP.json  # Saved annotations
```

## Annotation JSON Format

```json
{
  "debate_id": "0003dc00",
  "annotator": "SP",
  "timestamp": "2026-02-23T15:30:00Z",
  "scores": {
    "clash": {"AFF": 2, "NEG": 3},
    "burden_of_proof": {"AFF": 2, "NEG": 2},
    "rebuttal": {"AFF": 1, "NEG": 2},
    "extension": {"AFF": 2, "NEG": 3},
    "adaptation": {"AFF": 2, "NEG": 2}
  },
  "winner": "NEG",
  "justification": "NEG had stronger clash and extension..."
}
```
