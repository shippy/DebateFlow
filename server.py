"""Starlette HTTP server — serves annotation UI and on-demand TTS."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from voice import (
    DEFAULT_VOICE_POOL,
    get_client,
    pick_voice_pair,
    synthesize_turn,
)

OUTPUT_DIR = Path("output")
AUDIO_DIR = OUTPUT_DIR / "audio"


async def homepage(request: Request) -> Response:
    return FileResponse("annotate.html")


async def list_debates(request: Request) -> Response:
    """Return list of debate JSON filenames available on disk."""
    debates_dir = OUTPUT_DIR / "debates"
    if not debates_dir.exists():
        return JSONResponse([])
    files = sorted(p.name for p in debates_dir.glob("*.json"))
    return JSONResponse(files)


async def tts_endpoint(request: Request) -> Response:
    """On-demand TTS: synthesize a single turn, cache to disk.

    Accepts JSON: {debate_id, turn_index, speaker, text}
    Returns JSON: {url} pointing to the cached MP3.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    debate_id: str = body.get("debate_id", "")
    turn_index: int = body.get("turn_index", 0)
    speaker: str = body.get("speaker", "")
    text: str = body.get("text", "")

    if not all([debate_id, speaker, text]):
        return JSONResponse({"error": "Missing required fields"}, status_code=400)

    # Determine filename and cache path
    filename = f"{debate_id}_turn_{turn_index}_{speaker}.mp3"
    debate_audio_dir = AUDIO_DIR / debate_id
    cache_path = debate_audio_dir / filename
    url = f"/output/audio/{debate_id}/{filename}"

    # Return cached version if it exists
    if cache_path.exists():
        return JSONResponse({"url": url, "cached": True})

    # Synthesize via ElevenLabs
    aff_voice, neg_voice = pick_voice_pair(debate_id)
    voice = aff_voice if speaker == "aff" else neg_voice
    voice_id: str = voice["voice_id"]

    try:
        client = get_client()
        audio_bytes = synthesize_turn(client, text, voice_id)
    except Exception as e:
        return JSONResponse({"error": f"TTS failed: {e}"}, status_code=502)

    # Write to disk cache
    debate_audio_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(audio_bytes)

    return JSONResponse({"url": url, "cached": False})


async def voices_endpoint(request: Request) -> Response:
    """Return available voice pool (for debugging)."""
    return JSONResponse(DEFAULT_VOICE_POOL)


# Ensure output directory exists for static file serving
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

routes: list[Route | Mount] = [
    Route("/", homepage),
    Route("/api/debates", list_debates),
    Route("/api/tts", tts_endpoint, methods=["POST"]),
    Route("/api/voices", voices_endpoint),
    Mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output"),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    ),
]

app = Starlette(routes=routes, middleware=middleware)
