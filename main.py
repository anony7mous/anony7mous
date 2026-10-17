from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from setup_parser import SetupParser, KNOWN_PATTERNS
from scanner import scan_pairs, DEFAULT_PAIRS
from pattern_engine import DETECTORS

app = FastAPI(title="Forex Setup Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before shipping to prod
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
    ranked by how far along the pattern is (near_complete/complete first)
    and by confidence.
    """
    if not description and not image:
        raise HTTPException(400, "Provide a text description, an image, or both.")

    parser = SetupParser()

    if image is not None:
        image_bytes = await image.read()
        parsed = parser.parse_image(
            image_bytes,
            media_type=image.content_type or "image/png",
            extra_text=description,
        )
    else:
        parsed = parser.parse_text(description)

    pattern_key = parsed.get("pattern")
    if pattern_key not in DETECTORS:
        raise HTTPException(422, f"Could not map input to a known pattern. Model said: {parsed}")

    pair_list = [p.strip() for p in pairs.split(",")] if pairs else None
    results = await scan_pairs(pattern_key, pairs=pair_list, min_score=min_score)

    return {
        "interpreted_pattern": pattern_key,
        "interpretation_confidence": parsed.get("confidence"),
        "interpretation_notes": parsed.get("notes"),
        "matches": results,
        "count": len(results),
    }
