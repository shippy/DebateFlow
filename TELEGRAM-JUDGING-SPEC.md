# DebateFlow Telegram Judging Interface

- **Author:** Šimon Podhajský
- **Status:** Design spec
- **Depends on:** DebateFlow voice pipeline (VOICE-SPEC.md), OpenClaw Telegram channel

---

## 1. Overview

A conversational judging flow via Telegram, powered by OpenClaw. The assistant sends a debate as a voice note, then walks the annotator through per-side rubric scoring using inline buttons. Designed for low-friction, on-the-go annotation.

**Flow summary:**
1. Resolution (text)
2. Full debate (single voice note, ~3–5 min)
3. 10 scoring messages with inline buttons (5 dimensions × 2 sides)
4. Winner selection (inline buttons)
5. Optional justification (text reply or skip)
6. Confirmation + score summary

**Time to complete:** ~30 seconds of tapping after listening.

---

## 2. Message Sequence

### Message 1: Resolution

```
🎙️ Debate #a3f2 (12 of 50)

Resolution: "This house would ban private car ownership in city centers"

Listen to the full debate below, then I'll walk you through scoring.
```

### Message 2: Voice Note

Single stitched audio file with all 4 turns:
- Turn 1: Aff Opening (Voice A)
- [2s silence]
- Turn 2: Neg Response (Voice B)
- [2s silence]
- Turn 3: Aff Rebuttal (Voice A)
- [2s silence]
- Turn 4: Neg Closing (Voice B)

Sent as a Telegram voice message (OGG/OPUS format, `asVoice: true`).

After the voice note, a prompt:

```
Ready to score? Tap below when you've listened.

[Score This Debate]
```

This avoids flooding the chat with scoring messages before the annotator has listened.

### Messages 3–12: Dimension Scoring

Sent one at a time, each with three inline buttons. Next message sent on button tap.

**Order:** Grouped by dimension, AFF then NEG within each.

```
📊 1/5 — Clash Engagement

Did the AFFIRMATIVE address the opponent's arguments or talk past them?

[Weak ❌]  [OK ➖]  [Strong ✅]
```

On tap → button row updates to show selection → next message sent:

```
📊 1/5 — Clash Engagement

Did the NEGATIVE address the opponent's arguments or talk past them?

[Weak ❌]  [OK ➖]  [Strong ✅]
```

Then (example for an empirical debate):

```
📊 2/5 — Burden Fulfillment

Did each side adequately support their core claims and meet their argumentative obligations?

For this empirical debate:
Did AFF provide sufficient evidence that the claim is true?

[Weak ❌]  [OK ➖]  [Strong ✅]
```

Continuing:
- 3/5 — Rebuttal Quality (AFF, NEG)
- 4/5 — Argument Extension (AFF, NEG)
- 5/5 — Strategic Adaptation (AFF, NEG)

**Dimension definitions (sent with each message):**

> **Note:** Burden Fulfillment prompts vary by debate category (policy, values, empirical). All other dimensions use the same prompts regardless of category.

| # | Dimension | AFF prompt | NEG prompt |
|---|-----------|-----------|-----------|
| 1 | Clash Engagement | Did the AFF address the opponent's arguments or talk past them? | Did the NEG address the opponent's arguments or talk past them? |
| 2 | Burden Fulfillment | *(category-specific — see below)* | *(category-specific — see below)* |
| 3 | Rebuttal Quality | How specific and deep were the AFF's refutations? | How specific and deep were the NEG's refutations? |
| 4 | Argument Extension | Did the AFF's arguments develop across turns or just repeat? | Did the NEG's arguments develop across turns or just repeat? |
| 5 | Strategic Adaptation | Did the AFF adjust their approach based on the NEG's moves? | Did the NEG adjust their approach based on the AFF's moves? |

**Burden Fulfillment — category-specific prompts:**

Base definition: *"Did each side adequately support their core claims and meet their argumentative obligations?"*

| Category | AFF prompt | NEG prompt |
|----------|-----------|-----------|
| policy | Did AFF demonstrate a need for change and show the proposal solves it? | Did NEG defend the status quo or show the proposal causes more harm? |
| values | Did AFF show that the value or principle they champion should take precedence? | Did NEG show the competing value takes priority or that AFF's framing is flawed? |
| empirical | Did AFF provide sufficient evidence that the claim is true? | Did NEG provide sufficient evidence that the claim is false or unsupported? |

### Message 13: Winner

```
🏆 Who won this debate?

[Affirmative]  [Negative]
```

### Message 14: Justification

```
✍️ Brief justification? (Reply with text, or tap Skip)

[Skip]
```

If the annotator replies with text → captured as `winner_justification`.
If they tap Skip → field left empty.

### Message 15: Confirmation

```
✅ Debate #a3f2 annotated!

  Clash:      AFF Strong · NEG OK
  Burden:     AFF OK · NEG Weak
  Rebuttal:   AFF Strong · NEG Strong
  Extension:  AFF OK · NEG OK
  Adaptation: AFF Strong · NEG Weak
  Winner:     Affirmative

[Next Debate]  [Done for Now]
```

---

## 3. Callback Data Format

Each inline button encodes the full action:

```
score:{debate_id}:{dimension}:{side}:{value}
```

Examples:
- `score:a3f2:clash:aff:1` → Clash Engagement, AFF, Weak
- `score:a3f2:burden:neg:3` → Burden Fulfillment, NEG, Strong
- `winner:a3f2:aff` → Winner is Affirmative
- `action:a3f2:skip` → Skip justification
- `action:a3f2:next` → Next debate
- `action:a3f2:done` → Done for now

The agent receives these as `callback_data: <value>` messages from OpenClaw.

---

## 4. OpenClaw Integration

### Telegram channel config

Requires inline buttons enabled:

```json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "...",
      capabilities: {
        inlineButtons: "dm"  // or "all" / "allowlist"
      }
    }
  }
}
```

### Sending messages with buttons

Via OpenClaw `message` tool:

```json5
{
  action: "send",
  channel: "telegram",
  to: "<user_id>",
  message: "📊 1/5 — Clash Engagement\n\nDid the AFFIRMATIVE address the opponent's arguments?",
  buttons: [
    [
      { text: "Weak ❌", callback_data: "score:a3f2:clash:aff:1" },
      { text: "OK ➖", callback_data: "score:a3f2:clash:aff:2" },
      { text: "Strong ✅", callback_data: "score:a3f2:clash:aff:3" }
    ]
  ]
}
```

### Sending voice notes

```json5
{
  action: "send",
  channel: "telegram",
  to: "<user_id>",
  media: "/path/to/debate_full.ogg",
  asVoice: true
}
```

### Receiving callbacks

OpenClaw delivers callback clicks as agent messages:

```
callback_data: score:a3f2:clash:aff:3
```

The agent parses this, updates state, and sends the next scoring message.

---

## 5. Session State

Stored in `output/annotations/telegram_state.json`:

```json
{
  "annotator_id": "SP",
  "telegram_user_id": "123456789",
  "current_debate_id": "a3f2c1b9",
  "current_step": "score:burden:neg",
  "scores": {
    "clash_engagement": { "aff": 3, "neg": null },
    "burden_fulfillment": { "aff": 2, "neg": null }
  },
  "winner": null,
  "justification": null,
  "queue": ["b7e1d2a3", "c9f0e4b5"],
  "completed": ["d1a2b3c4"]
}
```

### Resumption

If interrupted, `/debate` resumes from current step. The agent checks state file and picks up where it left off.

---

## 6. Audio Pipeline

### Stitching (new — not yet implemented)

```python
from pydub import AudioSegment

def stitch_debate(debate_id: str, turns: list[Path]) -> Path:
    """Stitch per-turn MP3s into one OGG voice note."""
    silence = AudioSegment.silent(duration=2000)
    combined = AudioSegment.empty()
    for i, turn_path in enumerate(turns):
        segment = AudioSegment.from_mp3(turn_path)
        combined += segment
        if i < len(turns) - 1:
            combined += silence
    out = AUDIO_DIR / debate_id / f"{debate_id}_full.ogg"
    out.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(out), format="ogg", codec="opus")
    return out
```

### Generation flow

1. For each turn: call `synthesize_turn()` (existing `voice.py`), cache MP3
2. Stitch all 4 turns with 2s silence → export as OGG/OPUS
3. Send via OpenClaw `message` tool with `asVoice: true`

---

## 7. Entry Points

### Command: `/debate`

- No args: pick next unannotated debate, start scoring flow
- `/debate 5`: queue 5 debates for sequential annotation
- `/debate a3f2`: annotate specific debate by ID
- `/debate status`: show progress (X of Y annotated)

### Cron: Debate of the Day

```json5
{
  schedule: { kind: "cron", expr: "0 8 * * *", tz: "Europe/Prague" },
  payload: {
    kind: "agentTurn",
    message: "Send the next unannotated debate to Telegram for judging. Use the DebateFlow Telegram judging flow."
  },
  sessionTarget: "isolated",
  delivery: { mode: "announce", channel: "telegram" }
}
```

---

## 8. Annotation Output

Same schema as web frontend annotations:

```json
{
  "debate_id": "a3f2c1b9",
  "annotator_id": "SP",
  "source": "telegram",
  "winner": "aff",
  "winner_justification": "Neg dropped the economic argument entirely in closing",
  "dimension_scores": [
    { "dimension": "clash_engagement", "aff_score": 3, "neg_score": 2 },
    { "dimension": "burden_fulfillment", "aff_score": 2, "neg_score": 1 },
    { "dimension": "rebuttal_quality", "aff_score": 3, "neg_score": 3 },
    { "dimension": "argument_extension", "aff_score": 2, "neg_score": 2 },
    { "dimension": "strategic_adaptation", "aff_score": 3, "neg_score": 1 }
  ],
  "annotated_at": "2026-02-23T15:30:00Z",
  "annotation_version": "0.1.0",
  "audio_listened": true
}
```

Saved to `output/annotations/{debate_id}_{annotator_id}.json`.

---

## 9. Implementation Plan

### Prerequisites
- [ ] Telegram bot configured in OpenClaw with `inlineButtons: "dm"`
- [ ] ElevenLabs API key (`DF_ELEVENLABS_API_KEY`)
- [ ] `pydub` + `ffmpeg` for audio stitching
- [ ] Generated debates in `output/debates/`

### Phase 1: Audio stitching
- [ ] `stitch_debate()` in voice pipeline (MP3 → stitched OGG/OPUS)
- [ ] Test: generate + stitch one debate, verify playback

### Phase 2: Agent-side scoring flow
- [ ] State management (JSON file, read/write from agent)
- [ ] `/debate` command → load debate → send resolution + voice note
- [ ] Callback parser → score storage → next message dispatch
- [ ] Justification handling (text reply vs. skip)
- [ ] Confirmation message with summary

### Phase 3: Polish
- [ ] Queue management (`/debate N`, `/debate status`)
- [ ] Resumption logic
- [ ] Debate-of-the-day cron
- [ ] Inter-annotator agreement tracking (if multi-annotator)

---

## 10. Open Questions

1. **Telegram bot setup.** Šimon needs a Telegram bot token + OpenClaw Telegram channel configured. Is this already set up?
2. **Corrections.** Current spec is forward-only (no going back). Add a `/redo` command to re-annotate the last debate?
3. **Transcript fallback.** Should the text transcript also be available on demand (e.g., `/transcript` command during scoring)? Could help for tricky debates where re-listening is too slow.

---

*Last updated: 2026-02-23*
