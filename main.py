from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from setup_parser import SetupParser, KNOWN_PATTERNS, VisionUnavailable
from scanner import scan_pairs, DEFAULT_PAIRS
from pattern_engine import DETECTORS

app = FastAPI(title="Forex Setup Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend URL before sharing publicly
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "known_patterns": KNOWN_PATTERNS, "default_pairs": DEFAULT_PAIRS}


@app.post("/scan")
async def scan(
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    pairs: Optional[str] = Form(None),   # comma separated, optional override
    min_score: float = Form(40.0),
):
    """
    Accepts a text description and/or a chart image describing the setup.
    Returns the pairs/timeframes currently forming or near that setup,
    ranked by how far along the pattern is and by confidence.
    """
    if not description and not image:
        raise HTTPException(400, "Provide a text description, an image, or both.")

    try:
        parser = SetupParser()
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    try:
        if image is not None:
            image_bytes = await image.read()
            try:
                parsed = parser.parse_image(
                    image_bytes,
                    media_type=image.content_type or "image/png",
                    extra_text=description,
                )
            except VisionUnavailable:
                if description:
                    parsed = parser.parse_text(description)
                else:
                    raise HTTPException(
                        400,
                        "Image analysis isn't enabled. Describe the setup in text instead.",
                    )
        else:
            parsed = parser.parse_text(description)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"The AI model request failed: {e}")

    pattern_key = parsed.get("pattern")
    if pattern_key not in DETECTORS:
        raise HTTPException(
            422,
            f"Could not map your input to a known pattern. Try naming one, e.g. "
            f"'double bottom' or 'bull flag'. Model said: {parsed.get('notes')}",
        )

    pair_list = [p.strip() for p in pairs.split(",")] if pairs else None
    try:
        results = await scan_pairs(pattern_key, pairs=pair_list, min_score=min_score)
    except Exception as e:
        raise HTTPException(502, f"Market data fetch failed: {e}")

    return {
        "interpreted_pattern": pattern_key,
        "interpretation_confidence": parsed.get("confidence"),
        "interpretation_notes": parsed.get("notes"),
        "matches": results,
        "count": len(results),
    }
