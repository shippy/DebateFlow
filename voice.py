"""ElevenLabs TTS wrapper — voice selection and synthesis."""

from __future__ import annotations

import hashlib
import os
from itertools import combinations

from elevenlabs import ElevenLabs


def get_api_key() -> str:
    """Read ElevenLabs API key from DF_ELEVENLABS_API_KEY env var."""
    key = os.environ.get("DF_ELEVENLABS_API_KEY")
    if not key:
        raise ValueError("Set DF_ELEVENLABS_API_KEY in your .env file or environment")
    return key


def get_client() -> ElevenLabs:
    """Return an ElevenLabs client configured with the DF_ API key."""
    return ElevenLabs(api_key=get_api_key())


# Pre-made ElevenLabs voices — varied timbre for distinguishable debate pairings.
DEFAULT_VOICE_POOL: list[dict[str, str]] = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam"},
    {"voice_id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte"},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily"},
    {"voice_id": "bIHbv24MWmeRgasZH58o", "name": "Will"},
    {"voice_id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura"},
]


def _all_distinct_pairs(pool: list[dict[str, str]]) -> list[tuple[dict[str, str], dict[str, str]]]:
    """Generate all ordered distinct pairs from the voice pool."""
    return list(combinations(pool, 2))


def pick_voice_pair(debate_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """Deterministic voice pair based on hash of debate_id.

    Returns (aff_voice, neg_voice) — always distinct voices.
    """
    pairs = _all_distinct_pairs(DEFAULT_VOICE_POOL)
    h = int(hashlib.sha256(debate_id.encode()).hexdigest(), 16)
    idx = h % len(pairs)
    return pairs[idx]


def synthesize_turn(client: ElevenLabs, text: str, voice_id: str) -> bytes:
    """Synthesize text to MP3 bytes via ElevenLabs.

    Returns raw MP3 audio bytes.
    """
    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_22050_32",
    )
    # The SDK returns an iterator of bytes chunks
    chunks = []
    for chunk in audio_iter:
        chunks.append(chunk)
    return b"".join(chunks)
