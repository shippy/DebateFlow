# DebateFlow Voice Component: Spoken Debate Playback

- **Author:** Šimon Podhajský
- **Status:** Design spec
- **Depends on:** DebateFlow core benchmark (SPEC.md)

---

## 1. Motivation

Competitive debates are oral events. Listening to arguments is closer to the real judging experience than reading transcripts. Adding speech to DebateFlow is a quality-of-life improvement: evaluators can listen to debates while scoring, making the evaluation frontend feel more natural.

This is not an evaluation dimension — delivery quality is not scored. The voice layer simply makes the existing text debates audible.

---

## 2. TTS Pipeline

### Architecture

```
debate.json → TTS (ElevenLabs) → per-turn audio → stitched full debate
```

Each debate produces:
- Four per-turn audio files (`{debate_id}_turn_{n}_{side}.mp3`)
- One stitched full-debate file with ~2s pauses between turns (`{debate_id}_full.mp3`)
- Audio metadata added to the debate JSON

### Voice Assignment

- **Affirmative** and **Negative** get distinct voices within each debate (different timbre)
- Same voice across all turns for a given side (consistency within a debate)
- **Voice pairings rotate across debates** — maintain a pool of 4–6 voices and cycle through pairings so consecutive debates sound different
- Voice pairing recorded in metadata for reproducibility

### Provider: ElevenLabs

ElevenLabs as the primary (and initially only) TTS provider:
- High-quality, natural-sounding speech
- Large voice library for building a diverse pool
- Voice selection via `voice_id`
- API: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`

**Voice pool (starter):**
- Curate 4–6 voices with varied timbre, pitch, and character
- Mix genders and vocal qualities for variety
- Avoid extreme accents — neutral, clear delivery appropriate for debate
- Pairings should always be clearly distinguishable (no two similar-sounding voices in the same debate)

**Cost estimate:** ~$0.03–0.10/min. At ~4 min per debate, a 100-debate set costs $3–10.

---

## 3. Audio Format

- **Format:** MP3
- **Sample rate:** 24kHz (ElevenLabs default)
- **Inter-turn pause:** 2 seconds of silence
- **Naming:** `{debate_id}_turn_{n}_{side}.mp3`, `{debate_id}_full.mp3`
- **Storage:** `output/audio/{debate_id}/`

---

## 4. Data Schema Extension

```python
class VoiceConfig(BaseModel):
    voice_id: str              # ElevenLabs voice ID
    voice_name: str            # Human-readable name
    model_id: str = "eleven_multilingual_v2"

class TurnAudio(BaseModel):
    file: str                  # Relative path to audio file
    duration_seconds: float

class DebateAudio(BaseModel):
    aff_voice: VoiceConfig
    neg_voice: VoiceConfig
    turns: list[TurnAudio]     # Parallel to Debate.turns
    full_file: str             # Stitched full-debate audio
    full_duration_seconds: float
    generated_at: datetime
```

The `Debate` model gains an optional `audio: DebateAudio | None` field.

---

## 5. Frontend Integration

Add to the existing evaluation frontend:

- **Play/pause per turn** — click a turn to hear it
- **Play full debate** — sequential playback of all turns
- **Visual indicator** — highlight which turn is currently playing
- **Speed control** — 1x / 1.25x / 1.5x playback

The transcript remains visible and scrollable during playback. No audio-only mode — this is a reading aid, not a separate evaluation condition.

---

## 6. Implementation

### New files
- `voice.py` — ElevenLabs API wrapper, voice selection
- `synthesize.py` — Generate audio from debate JSON, stitch with pydub/ffmpeg

### CLI command
```bash
# Synthesize audio for all debates
uv run python cli.py synthesize

# Synthesize a specific debate
uv run python cli.py synthesize --debate-id abc12345

# List available ElevenLabs voices
uv run python cli.py voices
```

### Dependencies
```
elevenlabs>=1.0.0
pydub>=0.25.0       # Audio stitching
```

### Implementation order
1. ElevenLabs API wrapper + voice listing
2. Per-turn synthesis
3. Stitching (pydub + 2s silence insertion)
4. Metadata generation + schema update
5. Frontend audio player

---

*Last updated: 2026-02-23*
