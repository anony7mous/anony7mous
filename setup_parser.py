"""
Turns pasted text and/or a chart screenshot into one of the pattern keys
pattern_engine.DETECTORS knows how to scan for. Uses OpenRouter, which exposes
an OpenAI-compatible API, so any model on openrouter.ai works.

Resilience: OPENROUTER_TEXT_MODEL can hold several model IDs separated by
commas. They are tried in order. If all fail, a keyword matcher takes over
so common setups still work without any AI.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

KNOWN_PATTERNS = [
    "double_top", "double_bottom", "head_and_shoulders",
    "ascending_triangle", "descending_triangle", "symmetrical_triangle",
    "bull_flag", "bear_flag",
    "resistance_breakout", "support_breakdown",
]

_SYSTEM = f"""You are a technical-analysis pattern classifier for a forex chart
scanner. Map the user's input to exactly one pattern from this fixed list:
{", ".join(KNOWN_PATTERNS)}

Respond with ONLY minified JSON, no prose, no markdown fences, in this shape:
{{"pattern": "<one of the list>", "confidence": 0-1, "notes": "<short note on distinguishing shape details>"}}
If nothing matches reasonably, pick the closest one and lower confidence."""


class VisionUnavailable(Exception):
    """Raised when an image is uploaded but no vision model is configured."""
    pass


def keyword_match(text: str) -> dict:
    """AI-free fallback: map common trading phrases to a pattern."""
    t = (text or "").lower()
    rules = [
        (["head and shoulders", "head & shoulders", "h&s"], "head_and_shoulders"),
        (["double bottom", "w pattern", "w-pattern", "twin bottom"], "double_bottom"),
        (["double top", "m pattern", "m-pattern", "twin top"], "double_top"),
        (["ascending triangle"], "ascending_triangle"),
        (["descending triangle"], "descending_triangle"),
        (["symmetrical triangle", "symmetric triangle", "triangle", "wedge"], "symmetrical_triangle"),
        (["bear flag", "bearish flag", "bearish pennant", "bear pennant"], "bear_flag"),
        (["bull flag", "bullish flag", "bullish pennant", "bull pennant", "flag", "pennant"], "bull_flag"),
        (["breakdown", "break below", "support break"], "support_breakdown"),
        (["breakout", "break above", "resistance break", "break out"], "resistance_breakout"),
    ]
    for words, pattern in rules:
        if any(w in t for w in words):
            return {"pattern": pattern, "confidence": 0.5,
                    "notes": "Matched by keywords (AI model unavailable)"}
    return {"pattern": None, "confidence": 0,
            "notes": "Could not recognise a pattern name in the description"}


class SetupParser:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your environment variables.")
        raw = os.environ.get("OPENROUTER_TEXT_MODEL") or "openrouter/auto"
        self.text_models = [m.strip() for m in raw.split(",") if m.strip()]
        # Blank or missing means image analysis is switched off
        self.vision_model = os.environ.get("OPENROUTER_VISION_MODEL") or None

    def _call(self, model: str, user_content, retries: int = 2) -> dict:
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = httpx.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model,
                        # high limit: reasoning models spend tokens "thinking" first
                        "max_tokens": 1500,
                        "messages": [
                            {"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": user_content},
                        ],
                    },
                    timeout=90,
                )
                # Temporary errors: wait and retry
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"{model} returned {resp.status_code}"
                    time.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                message = resp.json()["choices"][0]["message"]
                text = (message.get("content") or "").strip()
                return self._extract_json(text)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = f"{model} network error: {e}"
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(last_error or f"{model} failed")

    def parse_text(self, description: str) -> dict:
        errors = []
        for model in self.text_models:
            try:
                result = self._call(model, description)
                if result.get("pattern"):
                    return result
                errors.append(f"{model}: unreadable answer")
            except Exception as e:
                errors.append(str(e))
        # Every model failed, so use the keyword fallback
        result = keyword_match(description)
        if result["pattern"] is None:
            result["notes"] += f" | AI errors: {'; '.join(errors)[:300]}"
        return result

    def parse_image(self, image_bytes: bytes, media_type: str = "image/png",
                    extra_text: str | None = None) -> dict:
        if not self.vision_model:
            raise VisionUnavailable("No vision model configured")
        b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            {"type": "text", "text": extra_text or "Identify the chart pattern shown."},
        ]
        try:
            return self._call(self.vision_model, content)
        except Exception:
            # Vision model failed, so fall back to the typed description if there is one
            if extra_text:
                return keyword_match(extra_text)
            raise

    @staticmethod
    def _extract_json(text: str) -> dict:
        # Models sometimes wrap JSON in prose or code fences, so grab the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if data.get("pattern") in KNOWN_PATTERNS:
                    return data
            except json.JSONDecodeError:
                pass
        lowered = text.lower()
        for p in KNOWN_PATTERNS:
            if p in lowered:
                return {"pattern": p, "confidence": 0.4,
                        "notes": "Pattern name found in free-text reply"}
        return {"pattern": None, "confidence": 0,
                "notes": f"Could not parse model output: {text[:200]}"}
