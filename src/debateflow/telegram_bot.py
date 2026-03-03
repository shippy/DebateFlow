"""Plain Telegram bot for DebateFlow debate annotation.

Uses python-telegram-bot (polling mode, no webhook needed).
Wraps TelegramJudgingSession for state/scoring logic.
"""

from __future__ import annotations

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    filters,
)

from .telegram_judging import TelegramJudgingSession

logger = logging.getLogger(__name__)

# Conversation states
ASK_NAME, AWAITING_READY, SCORING, WINNER, JUSTIFICATION, DONE = range(6)

SCORE_LABELS = {1: "Weak", 2: "OK", 3: "Strong"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allowed_user_ids() -> set[int] | None:
    """Parse DEBATEFLOW_ANNOTATOR_IDS env var. None means allow everyone."""
    raw = os.environ.get("DEBATEFLOW_ANNOTATOR_IDS", "")
    if not raw.strip():
        return None
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}


def _is_allowed(user_id: int) -> bool:
    allowed = _allowed_user_ids()
    return allowed is None or user_id in allowed


def _get_session(context: ContextTypes.DEFAULT_TYPE) -> TelegramJudgingSession:
    """Return (or create) the per-user judging session using stored annotator name."""
    name = context.user_data.get("annotator_name", "anonymous")
    # Always recreate — the session object doesn't need to survive restarts
    session = TelegramJudgingSession(annotator_id=name)
    context.user_data["session"] = session
    return session


async def _send_debate(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send resolution + voice note + 'Score This Debate' button.

    Shared by /debate and the 'Next Debate' callback.
    Returns the next conversation state (AWAITING_READY or END).
    """
    session: TelegramJudgingSession = context.user_data["session"]
    debate: dict = context.user_data["debate"]
    debate_id: str = context.user_data["debate_id"]

    resolution = debate["metadata"]["resolution"]

    total = len(list(session.debates_dir.glob("*.json")))
    done = len(list(session.annotations_dir.glob(f"*_{session.annotator_id}.json")))

    # Message 1: Resolution
    await message.reply_text(
        f"\U0001f399\ufe0f Debate #{debate_id} ({done + 1} of {total})\n\n"
        f'Resolution: "{resolution}"\n\n'
        "Listen to the full debate below, then I'll walk you through scoring."
    )

    # Message 2: Voice note (or transcript fallback)
    try:
        ogg_path = session.prepare_audio(debate)
        with open(ogg_path, "rb") as f:
            await message.reply_voice(voice=f)
    except Exception:
        logger.warning("Audio synthesis failed, sending transcript", exc_info=True)
        transcript = "\n\n".join(
            f"{'AFF' if t['speaker'] == 'aff' else 'NEG'} ({t['role']}):\n{t['text']}"
            for t in debate["turns"]
        )
        # Telegram message limit is 4096 chars
        await message.reply_text(
            f"\u26a0\ufe0f Audio unavailable \u2014 transcript:\n\n{transcript[:3900]}"
        )

    # "Score This Debate" button
    keyboard = [[
        InlineKeyboardButton(
            "Score This Debate",
            callback_data=f"action:{debate_id}:ready",
        )
    ]]
    await message.reply_text(
        "Ready to score? Tap below when you've listened.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return AWAITING_READY


async def _send_scoring_prompt(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send the current scoring prompt with inline buttons."""
    prompts = context.user_data["prompts"]
    idx = context.user_data["prompt_index"]
    prompt = prompts[idx]

    keyboard = [[
        InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"])
        for btn in prompt["buttons"]
    ]]

    side_label = "AFFIRMATIVE" if prompt["side"] == "AFF" else "NEGATIVE"
    await message.reply_text(
        prompt["text"] + f"\n\n\U0001f446 Rate the {side_label}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SCORING


async def _save_and_confirm(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save annotation and send confirmation summary."""
    session: TelegramJudgingSession = context.user_data["session"]
    debate_id: str = context.user_data["debate_id"]

    path = session.save_annotation(debate_id)
    logger.info("Annotation saved: %s", path)

    dim_labels = {
        "clash": "Clash",
        "burden_of_proof": "Burden",
        "rebuttal": "Rebuttal",
        "extension": "Extension",
        "adaptation": "Adaptation",
    }

    lines = []
    for dim, scores in session.scores.items():
        label = dim_labels.get(dim, dim)
        aff = SCORE_LABELS.get(scores.get("AFF", 0), "?")
        neg = SCORE_LABELS.get(scores.get("NEG", 0), "?")
        lines.append(f"  {label:12s}  AFF {aff} \u00b7 NEG {neg}")

    winner_label = "Affirmative" if session.winner == "AFF" else "Negative"

    keyboard = [[
        InlineKeyboardButton("Next Debate", callback_data=f"action:{debate_id}:next"),
        InlineKeyboardButton("Done for Now", callback_data=f"action:{debate_id}:done"),
    ]]

    await message.reply_text(
        f"\u2705 Debate #{debate_id} annotated!\n\n"
        + "\n".join(lines)
        + f"\n  Winner: {winner_label}\n",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return DONE


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /debate — load next debate and begin the flow."""
    if not _is_allowed(update.effective_user.id):
        return ConversationHandler.END

    # First interaction: ask for a pseudonym
    if "annotator_name" not in context.user_data:
        await update.message.reply_text(
            "Welcome! What name should I use for your annotations?\n"
            "(e.g. your initials — this will appear in filenames like "
            "debate_SP.json)"
        )
        return ASK_NAME

    session = _get_session(context)
    debate = session.get_next_debate()

    if debate is None:
        await update.message.reply_text("\U0001f389 All debates have been annotated!")
        return ConversationHandler.END

    debate_id = debate["metadata"]["debate_id"]
    category = debate["metadata"].get("category", "policy")

    context.user_data["debate"] = debate
    context.user_data["debate_id"] = debate_id
    context.user_data["category"] = category

    return await _send_debate(update.message, context)


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle name reply — store pseudonym and proceed to first debate."""
    name = update.message.text.strip()
    if not name or len(name) > 20:
        await update.message.reply_text("Please enter a short name (1\u201320 characters).")
        return ASK_NAME

    context.user_data["annotator_name"] = name
    await update.message.reply_text(
        f'Got it \u2014 you\'re "{name}". Loading your first debate\u2026'
    )

    session = _get_session(context)
    debate = session.get_next_debate()

    if debate is None:
        await update.message.reply_text("\U0001f389 All debates have been annotated!")
        return ConversationHandler.END

    debate_id = debate["metadata"]["debate_id"]
    category = debate["metadata"].get("category", "policy")

    context.user_data["debate"] = debate
    context.user_data["debate_id"] = debate_id
    context.user_data["category"] = category

    return await _send_debate(update.message, context)


async def ready_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Score This Debate' tap — begin scoring prompts."""
    query = update.callback_query
    await query.answer()

    session: TelegramJudgingSession = context.user_data["session"]
    debate_id = context.user_data["debate_id"]
    category = context.user_data["category"]

    prompts = session.get_scoring_prompts(debate_id, category)
    context.user_data["prompts"] = prompts
    context.user_data["prompt_index"] = 0

    return await _send_scoring_prompt(query.message, context)


async def score_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle score button tap — record and advance."""
    query = update.callback_query
    await query.answer()

    # Parse: score:{debate_id}:{dimension}:{side}:{value}
    _, debate_id, dimension, side, value = query.data.split(":")

    session: TelegramJudgingSession = context.user_data["session"]
    session.record_score(debate_id, dimension, side, int(value))

    # Advance to next prompt
    context.user_data["prompt_index"] += 1
    idx = context.user_data["prompt_index"]
    prompts = context.user_data["prompts"]

    if idx < len(prompts):
        return await _send_scoring_prompt(query.message, context)

    # All 10 scores recorded — ask for winner
    keyboard = [[
        InlineKeyboardButton("Affirmative", callback_data=f"winner:{debate_id}:AFF"),
        InlineKeyboardButton("Negative", callback_data=f"winner:{debate_id}:NEG"),
    ]]
    await query.message.reply_text(
        "\U0001f3c6 Who won this debate?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WINNER


async def winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle winner selection — ask for justification."""
    query = update.callback_query
    await query.answer()

    _, debate_id, side = query.data.split(":")

    session: TelegramJudgingSession = context.user_data["session"]
    session.record_winner(debate_id, side)

    keyboard = [[
        InlineKeyboardButton("Skip", callback_data=f"action:{debate_id}:skip"),
    ]]
    await query.message.reply_text(
        "\u270d\ufe0f Brief justification? (Reply with text, or tap Skip)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return JUSTIFICATION


async def text_justification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle free-text justification reply."""
    session: TelegramJudgingSession = context.user_data["session"]
    debate_id = context.user_data["debate_id"]
    session.record_justification(debate_id, update.message.text)
    return await _save_and_confirm(update.message, context)


async def skip_justification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip button for justification."""
    query = update.callback_query
    await query.answer()
    return await _save_and_confirm(query.message, context)


async def next_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Next Debate' button."""
    query = update.callback_query
    await query.answer()

    session: TelegramJudgingSession = context.user_data["session"]
    debate = session.get_next_debate()

    if debate is None:
        await query.message.reply_text("\U0001f389 All debates have been annotated!")
        return ConversationHandler.END

    debate_id = debate["metadata"]["debate_id"]
    category = debate["metadata"].get("category", "policy")

    context.user_data["debate"] = debate
    context.user_data["debate_id"] = debate_id
    context.user_data["category"] = category

    return await _send_debate(query.message, context)


async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Done for Now' button."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "\U0001f44b See you next time! Use /debate to resume."
    )
    return ConversationHandler.END


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — show annotation progress."""
    if not _is_allowed(update.effective_user.id):
        return

    session = _get_session(context)
    total = len(list(session.debates_dir.glob("*.json")))
    done = len(list(session.annotations_dir.glob(f"*_{session.annotator_id}.json")))

    name = context.user_data.get("annotator_name", "unknown")
    await update.message.reply_text(
        f"\U0001f4ca Annotator: {name}\n"
        f"Progress: {done}/{total} debates annotated."
    )


async def name_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /name — show or change annotator pseudonym."""
    if not _is_allowed(update.effective_user.id):
        return

    args = update.message.text.split(maxsplit=1)
    if len(args) > 1:
        new_name = args[1].strip()
        if new_name and len(new_name) <= 20:
            context.user_data["annotator_name"] = new_name
            await update.message.reply_text(
                f'Annotator name changed to "{new_name}".'
            )
            return

    current = context.user_data.get("annotator_name")
    if current:
        await update.message.reply_text(
            f'Your annotator name is "{current}".\n'
            "To change it: /name NewName"
        )
    else:
        await update.message.reply_text(
            "No name set yet. Use /name YourName to set one, "
            "or just send /debate and I'll ask."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel — abort current annotation."""
    await update.message.reply_text(
        "Annotation cancelled. Use /debate to start again."
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_application(token: str) -> Application:
    """Create and configure the Telegram bot Application."""
    persistence = PicklePersistence(filepath="output/telegram_bot_data.pickle")
    app = Application.builder().token(token).persistence(persistence).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("debate", start_debate)],
        states={
            ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_name),
            ],
            AWAITING_READY: [
                CallbackQueryHandler(ready_callback, pattern=r"^action:.*:ready$"),
            ],
            SCORING: [
                CallbackQueryHandler(score_callback, pattern=r"^score:"),
            ],
            WINNER: [
                CallbackQueryHandler(winner_callback, pattern=r"^winner:"),
            ],
            JUSTIFICATION: [
                CallbackQueryHandler(skip_justification, pattern=r"^action:.*:skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_justification),
            ],
            DONE: [
                CallbackQueryHandler(next_debate, pattern=r"^action:.*:next$"),
                CallbackQueryHandler(done_callback, pattern=r"^action:.*:done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("name", name_command))

    return app
