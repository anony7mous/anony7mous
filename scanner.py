from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict

import pandas as pd

from data_provider import get_default_provider
from pattern_engine import DETECTORS, PatternMatch

DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "USD/CHF", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
    "AUD/JPY", "EUR/AUD",
]

# One timeframe by default keeps a scan to 12 data requests.
# Free data plans limit requests per minute, so scanning many
# timeframes at once can trigger rate-limit errors.
DEFAULT_TIMEFRAMES = ["4h"]

CACHE_TTL_SECONDS = 600
_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
_semaphore = asyncio.Semaphore(3)  # at most 3 data requests at once


async def _get_candles(provider, pair: str, tf: str) -> pd.DataFrame:
    key = (pair, tf)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    async with _semaphore:
        df = await provider.get_candles(pair, interval=tf, output_size=200)
    _cache[key] = (time.time(), df)
    return df


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
