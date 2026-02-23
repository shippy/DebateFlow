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

from .models import Annotation

from .voice import (
    DEFAULT_VOICE_POOL,
    pick_voice_pair,
    synthesize_turn,
)

_PACKAGE_DIR = Path(__file__).parent
OUTPUT_DIR = Path("output")
AUDIO_DIR = OUTPUT_DIR / "audio"


async def homepage(request: Request) -> Response:
    return FileResponse(_PACKAGE_DIR / "static" / "annotate.html")


async def review_page(request: Request) -> Response:
    return FileResponse(_PACKAGE_DIR / "static" / "review.html")


async def list_annotations(request: Request) -> Response:
    """Return mapping of debate_id → [annotator_ids] from saved annotations."""
    annotations_dir = OUTPUT_DIR / "annotations"
    if not annotations_dir.exists():
        return JSONResponse({})

    result: dict[str, list[str]] = {}
    for p in sorted(annotations_dir.glob("*.json")):
        parts = p.stem.rsplit("_", 1)
        if len(parts) == 2:
            debate_id, annotator_id = parts
            result.setdefault(debate_id, []).append(annotator_id)
    return JSONResponse(result)


async def save_annotation(request: Request) -> Response:
    """Validate and save an annotation JSON file."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    try:
        annotation = Annotation.model_validate(body)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=422)

    annotations_dir = OUTPUT_DIR / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{annotation.debate_id}_{annotation.annotator_id}.json"
    (annotations_dir / filename).write_text(
        annotation.model_dump_json(indent=2)
    )
    return JSONResponse({"saved": filename})


async def list_debates(request: Request) -> Response:
    """Return list of debate JSON filenames available on disk.

    When ``?annotator=X`` is provided, debates already annotated by that
    annotator (i.e. a matching file in ``output/annotations/``) are excluded.
    """
    debates_dir = OUTPUT_DIR / "debates"
    if not debates_dir.exists():
        return JSONResponse([])

    annotator = request.query_params.get("annotator", "").strip()
    if annotator:
        annotations_dir = OUTPUT_DIR / "annotations"
        annotated_ids: set[str] = set()
        if annotations_dir.exists():
            for p in annotations_dir.glob(f"*_{annotator}.json"):
                annotated_ids.add(p.stem.removesuffix(f"_{annotator}"))
        files = sorted(
            p.name
            for p in debates_dir.glob("*.json")
            if p.stem not in annotated_ids
        )
    else:
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

    # Synthesize via TTS (ElevenLabs preferred, OpenAI fallback)
    aff_voice, neg_voice = pick_voice_pair(debate_id)
    voice = aff_voice if speaker == "aff" else neg_voice

    try:
        audio_bytes = synthesize_turn(text, voice)
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
    Route("/review", review_page),
    Route("/api/debates", list_debates),
    Route("/api/annotations", list_annotations, methods=["GET"]),
    Route("/api/annotations", save_annotation, methods=["PUT"]),
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
