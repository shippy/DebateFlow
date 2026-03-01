# Plan: DebateFlow Telegram Bot (Plain Bot, No OpenClaw)

## Context

DebateFlow needs a Telegram interface for debate annotation. The original plan called for a second OpenClaw instance, but the annotation flow is a deterministic state machine (button taps + one text reply) — no LLM needed. A plain `python-telegram-bot` is simpler, cheaper, more secure (zero injection surface), and faster to build.

**What already exists:**
- `telegram_judging.py` (309 lines) — `TelegramJudgingSession` class with scoring prompts, callback data format, state tracking, annotation saving
- `voice.py` (187 lines) — TTS with ElevenLabs/OpenAI fallback, voice pairing, but **missing `synthesize_debate()`**
- `models.py` — Pydantic models for `Debate`, `Annotation`, `DimensionScore`
- `output/debates/` — 20+ generated debate JSONs ready to annotate
- `output/audio/` — Cached MP3 files from TTS
- `TELEGRAM-JUDGING-SPEC.md` — Full 15-message flow spec

**What's missing:**
- Actual Telegram bot code (no `python-telegram-bot` dependency yet)
- `synthesize_debate()` function in voice.py
- Deployment config for VPS

---

## Implementation Steps

### Phase 1: Implement `synthesize_debate()` in voice.py (~20 min)

**File:** `src/debateflow/voice.py`

Add function that:
- Takes a `Debate` dict and output directory
- Calls `pick_voice_pair(debate_id)` for deterministic voice assignment
- Calls `synthesize_turn()` for each of 4 turns (AFF gets voice A, NEG gets voice B)
- Saves MP3 files as `{output_dir}/{debate_id}/turn_{n}.mp3`
- Returns `dict[str, str]` mapping `turn_1`..`turn_4` to file paths

Uses existing `synthesize_turn()` and `pick_voice_pair()` — no new TTS logic needed.

### Phase 2: Write `telegram_bot.py` (~60 min)

**New file:** `src/debateflow/telegram_bot.py` (~200 lines)

Core structure using `python-telegram-bot`:
- `Application` with polling mode (outbound only, no ports needed)
- `ConversationHandler` for the state machine:
  ```
  /debate → send resolution → send voice note → "Score This Debate" button
  → 10 scoring messages (one at a time, CallbackQueryHandler)
  → winner selection → justification (text or skip) → confirmation
  → /debate for next, or done
  ```
- Wraps existing `TelegramJudgingSession` for state/scoring logic
- Wraps existing `prepare_audio()` for voice note generation
- Saves annotations via existing `save_annotation()`

**Key handlers:**
| Handler | Trigger | Action |
|---------|---------|--------|
| `CommandHandler("debate")` | `/debate`, `/debate 5`, `/debate abc123` | Load debate, send resolution + voice |
| `CallbackQueryHandler` (pattern `score:*`) | Button tap | Record score, send next prompt |
| `CallbackQueryHandler` (pattern `winner:*`) | Winner button | Record winner, ask justification |
| `CallbackQueryHandler` (pattern `action:*:skip`) | Skip button | Skip justification, save |
| `MessageHandler` (text) | Free text reply | Record as justification, save |
| `CommandHandler("status")` | `/status` | Show X of Y annotated |

**Annotator allowlist:** Only respond to whitelisted Telegram user IDs (configurable via env var or config file).

### Phase 3: Add CLI entry point (~10 min)

**File:** `src/debateflow/cli.py`

Add `debateflow bot` command (Typer) that:
- Reads `DEBATEFLOW_TELEGRAM_TOKEN` from environment
- Reads optional `DEBATEFLOW_ANNOTATOR_IDS` (comma-separated Telegram user IDs)
- Starts the bot with `app.run_polling()`

### Phase 4: Add dependency (~2 min)

```bash
cd ~/Documents/DebateFlow && uv add python-telegram-bot
```

### Phase 5: Local testing (~20 min)

1. Create a test Telegram bot via @BotFather (Šimon does this manually)
2. Set `DEBATEFLOW_TELEGRAM_TOKEN` in environment
3. Run `uv run debateflow bot`
4. Send `/debate` from Telegram → walk through full flow
5. Verify annotation JSON saved to `output/annotations/`

### Phase 6: VPS deployment (~30 min)

**Option A: systemd service (recommended)**
- Copy/sync DebateFlow project to VPS
- Create `/etc/systemd/system/debateflow-bot.service`
- `uv sync` on VPS, systemd starts the bot
- Auto-restarts on crash, starts on boot

**Option B: Docker container**
- Write minimal Dockerfile (python + uv + ffmpeg)
- Add to existing docker-compose or standalone
- More isolation but more setup

Either way: needs `ffmpeg` for audio stitching (pydub dependency), ElevenLabs API key for TTS.

**Data sync:** Syncthing folder for `output/debates/` (local → VPS) and `output/annotations/` (VPS → local). Or simpler: rsync/scp before and after annotation sessions.

---

## Files Changed/Created

| File | Action |
|------|--------|
| `src/debateflow/voice.py` | Add `synthesize_debate()` function (~30 lines) |
| `src/debateflow/telegram_bot.py` | **New** — Telegram bot (~200 lines) |
| `src/debateflow/cli.py` | Add `bot` subcommand (~15 lines) |
| `pyproject.toml` | Add `python-telegram-bot` dependency |

## Files NOT Changed

- `telegram_judging.py` — Used as-is (session state, scoring prompts, annotation saving)
- `models.py` — Used as-is (Debate, Annotation models)
- `voice.py` — Only adding the missing `synthesize_debate()` function

---

## Verification

1. **Unit**: `synthesize_debate()` returns 4 MP3 paths for a sample debate
2. **Integration**: Full `/debate` flow on Telegram → annotation JSON matches expected schema
3. **Allowlist**: Messages from non-whitelisted users are ignored
4. **Audio**: OGG voice note plays correctly in Telegram (4 turns, 2s gaps)
5. **Resumption**: Bot restart mid-annotation → `/debate` picks up or starts fresh cleanly
6. **Queue**: `/debate 3` queues 3 debates, `/status` shows progress

## Estimated Time: ~2.5 hours

- Phase 1 (synthesize_debate): 20 min
- Phase 2 (telegram_bot.py): 60 min
- Phase 3 (CLI entry point): 10 min
- Phase 4 (dependency): 2 min
- Phase 5 (local testing): 20 min
- Phase 6 (VPS deployment): 30 min
