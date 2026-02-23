# DebateFlow Voice Component: Spoken Debate Playback

- **Author:** Šimon Podhajský
- **Status:** Mostly implemented
- **Depends on:** DebateFlow core benchmark (SPEC.md)

---

## 1. Motivation

Competitive debates are oral events. Listening to arguments is closer to the real judging experience than reading transcripts. Adding speech to DebateFlow is a quality-of-life improvement: evaluators can listen to debates while scoring, making the evaluation frontend feel more natural.

This is not an evaluation dimension — delivery quality is not scored. The voice layer simply makes the existing text debates audible.

---

## 2. TTS Pipeline

### Architecture

```
debate.json → TTS (ElevenLabs) → per-turn audio (on-demand, cached to disk)
```

Audio is synthesized **on demand** via the annotation server (`/api/tts`), cached to `output/audio/{debate_id}/`. No batch pre-generation needed — the frontend requests TTS as the user clicks play.

### Voice Assignment

- **Affirmative** and **Negative** get distinct voices within each debate (different timbre)
- Same voice across all turns for a given side (consistency within a debate)
- **Voice pairings rotate across debates** — pool of 6 voices, deterministic pairing via hash of `debate_id`
- Voice pairing recorded in response metadata

### Provider: ElevenLabs

- Model: `eleven_multilingual_v2`
- Output: `mp3_22050_32`
- API key via `DF_ELEVENLABS_API_KEY` env var

**Current voice pool (6 voices):**
- George, Liam, Charlotte, Lily, Will, Laura
- All distinct ElevenLabs pre-made voices
- 15 possible pairings from `combinations(6, 2)`

**Cost estimate:** ~$0.03–0.10/min. At ~4 min per debate, a 100-debate set costs $3–10.

---

## 3. Audio Format

- **Format:** MP3
- **Sample rate:** 22.05kHz
- **Bitrate:** 32kbps
- **Naming:** `{debate_id}_turn_{n}_{side}.mp3`
- **Storage:** `output/audio/{debate_id}/`

---

## 4. Frontend Integration (✅ Implemented)

The annotation frontend (`annotate.html`) includes:

- **Play/pause per turn** — button on each turn card
- **Play All** — sequential playback through all 4 turns, auto-advancing
- **Visual indicator** — turn card highlighted (blue border) while playing, yellow while loading/synthesizing
- **Speed control** — 1x / 1.25x / 1.5x dropdown
- **Status text** — shows "Synthesizing Aff Opening..." / "Playing Neg Closing" etc.
- **Caching** — TTS results cached server-side; second play is instant

---

## 5. Implementation Status

| Component | Status | File |
|-----------|--------|------|
| ElevenLabs API wrapper | ✅ Done | `voice.py` |
| Voice pool + deterministic pairing | ✅ Done | `voice.py` |
| On-demand TTS endpoint | ✅ Done | `server.py` (`/api/tts`) |
| Frontend audio player | ✅ Done | `static/annotate.html` |
| Disk caching | ✅ Done | `server.py` |
| Batch pre-synthesis CLI (`synthesize`) | ❌ Not yet | — |
| Full-debate stitched audio | ❌ Not yet | — |
| Data schema extension (`DebateAudio`) | ❌ Not yet | `models.py` |

### Remaining work

1. **Batch synthesis CLI** — `uv run python cli.py synthesize` to pre-generate all audio (useful for offline use or dataset publication)
2. **Full-debate stitched audio** — concatenate per-turn MP3s with 2s silence gaps into `{debate_id}_full.mp3`
3. **Schema extension** — add optional `audio: DebateAudio | None` to the `Debate` model so audio metadata persists in the debate JSON

These are nice-to-haves — the on-demand server approach already works for annotation sessions.

---

*Last updated: 2026-02-23*
