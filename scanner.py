from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import asdict

import pandas as pd

from data_provider import get_default_provider
from pattern_engine import DETECTORS, PatternMatch

# 7 pairs so a full scan fits inside the free plan's 8 requests per minute.
# Pass your own `pairs` (or set SCAN_PAIRS in Render) to scan others;
# extra pairs just make the scan wait for the next minute window.
DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "USD/CAD", "USD/CHF", "EUR/JPY",
]

DEFAULT_TIMEFRAMES = ["4h"]

CACHE_TTL_SECONDS = 600
_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}

# Stay under the free plan limit of 8 requests per minute
MAX_PER_MINUTE = 7
_calls: deque[float] = deque()
_limiter_lock = asyncio.Lock()


async def _wait_for_slot() -> None:
    """Block until a request is allowed under the per-minute limit."""
    async with _limiter_lock:
        while True:
            now = time.monotonic()
            while _calls and now - _calls[0] >= 61:
                _calls.popleft()
            if len(_calls) < MAX_PER_MINUTE:
                _calls.append(now)
                return
            await asyncio.sleep(61 - (now - _calls[0]) + 0.1)


async def _get_candles(provider, pair: str, tf: str) -> pd.DataFrame:
    key = (pair, tf)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    last_error: Exception | None = None
    for attempt in range(3):
        await _wait_for_slot()
        try:
            df = await provider.get_candles(pair, interval=tf, output_size=200)
            _cache[key] = (time.time(), df)
            return df
        except Exception as e:
            last_error = e
            if "API credits" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep(20)  # rate limited: wait, then retry
                continue
            raise
    raise last_error  # type: ignore[misc]


async def scan_pairs(pattern_key: str, pairs: list[str] | None = None,
                     timeframes: list[str] | None = None,
                     min_score: float = 40.0) -> dict:
    if pattern_key not in DETECTORS:
        raise ValueError(f"Unknown pattern '{pattern_key}'. Known: {list(DETECTORS)}")

    if not pairs:
        env_pairs = [p.strip() for p in os.environ.get("SCAN_PAIRS", "").split(",") if p.strip()]
        pairs = env_pairs or DEFAULT_PAIRS
    timeframes = timeframes or DEFAULT_TIMEFRAMES

    provider = get_default_provider()
    detector = DETECTORS[pattern_key]
    errors: list[str] = []

    async def scan_one(pair: str, tf: str) -> dict | None:
        try:
            df = await _get_candles(provider, pair, tf)
        except Exception as e:
            errors.append(f"{pair} {tf}: {e}")
            return None
        if len(df) < 30:
            errors.append(f"{pair} {tf}: only {len(df)} candles returned")
            return None
        match: PatternMatch = detector(df)
        if match.score < min_score:
            return None
        result = asdict(match)
        result["pair"] = pair
        result["timeframe"] = tf
        result["last_close"] = float(df["close"].iloc[-1])
        return result

    results = await asyncio.gather(*[scan_one(p, tf) for p in pairs for tf in timeframes])
    hits = [r for r in results if r is not None]

    stage_rank = {"complete": 2, "near_complete": 1, "forming": 0}
    hits.sort(key=lambda r: (stage_rank[r["stage"]], r["score"]), reverse=True)

    total = len(pairs) * len(timeframes)
    return {
        "hits": hits,
        "scanned": total - len(errors),
        "failed": len(errors),
        "errors": errors[:5],
    }
