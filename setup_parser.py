"""
Turns pasted text and/or a chart screenshot into one of the pattern keys
pattern_engine.DETECTORS knows how to scan for. Uses OpenRouter, which exposes
an OpenAI-compatible API, so any model on openrouter.ai works.
"""
from __future__ import annotations

import base64
import json
import os
import re
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


class SetupParser:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your environment variables.")
        # `or` (not a default arg) so a blank env value still falls back correctly
        self.text_model = os.environ.get("OPENROUTER_TEXT_MODEL") or "openrouter/auto"
        self.vision_model = os.environ.get("OPENROUTER_VISION_MODEL") or self.text_model

    def _chat(self, model: str, user_content) -> dict:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                # high limit: reasoning models spend tokens "thinking" before answering
                "max_tokens": 1500,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        text = (message.get("content") or "").strip()
        return self._extract_json(text)

    def parse_text(self, description: str) -> dict:
        return self._chat(self.text_model, description)

    def parse_image(self, image_bytes: bytes, media_type: str = "image/png",
                    extra_text: str | None = None) -> dict:
        b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            {"type": "text", "text": extra_text or "Identify the chart pattern shown."},
        ]
        return self._chat(self.vision_model, content)

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
        # Fallback: look for a known pattern name anywhere in the reply
        lowered = text.lower()
        for p in KNOWN_PATTERNS:
            if p in lowered:
                return {"pattern": p, "confidence": 0.4,
                        "notes": "Pattern name found in free-text reply"}
        return {"pattern": None, "confidence": 0,
                "notes": f"Could not parse model output: {text[:200]}"}
