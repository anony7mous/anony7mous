from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from setup_parser import SetupParser, KNOWN_PATTERNS, VisionUnavailable
from scanner import scan_pairs, DEFAULT_PAIRS, DEFAULT_TIMEFRAMES
from pattern_engine import DETECTORS
from data_provider import get_default_provider

app = FastAPI(title="Forex Setup Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend URL before sharing publicly
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "known_patterns": KNOWN_PATTERNS,
        "default_pairs": DEFAULT_PAIRS,
        "default_timeframes": DEFAULT_TIMEFRAMES,
    }


@app.get("/test-data")
async def test_data(pair: str = "EUR/USD", interval: str = "1h"):
    """Quick check that the market data key and provider work."""
    try:
        provider = get_default_provider()
        df = await provider.get_candles(pair, interval=interval, output_size=50)
        return {
            "ok": True,
            "pair": pair,
            "candles": len(df),
            "last_close": float(df["close"].iloc[-1]),
            "last_time": str(df.index[-1]),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/scan")
async def scan(
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    pairs: Optional[str] = Form(None),        # comma separated, e.g. "EUR/USD,GBP/USD"
    timeframes: Optional[str] = Form(None),   # comma separated, e.g. "1h,4h"
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
        if image is not None and image.filename:
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
            if not description:
                raise HTTPException(400, "Provide a text description or an image.")
            parsed = parser.parse_text(description)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"The AI model request failed: {e}")

    pattern_key = parsed.get("pattern")
    if pattern_key not in DETECTORS:
        raise HTTPException(
            422,
            "Could not map your input to a known pattern. Try naming one, e.g. "
            f"'double bottom' or 'bull flag'. Model said: {parsed.get('notes')}",
        )

    pair_list = [p.strip() for p in pairs.split(",") if p.strip()] if pairs else None
    tf_list = [t.strip() for t in timeframes.split(",") if t.strip()] if timeframes else None

    try:
        result = await scan_pairs(pattern_key, pairs=pair_list, timeframes=tf_list,
                                  min_score=min_score)
    except Exception as e:
        raise HTTPException(502, f"Market data fetch failed: {e}")

    return {
        "interpreted_pattern": pattern_key,
        "interpretation_confidence": parsed.get("confidence"),
        "interpretation_notes": parsed.get("notes"),
        "scanned": result["scanned"],
        "failed": result["failed"],
        "errors": result["errors"],
        "count": len(result["hits"]),
        "matches": result["hits"],
    }
