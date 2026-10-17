from __future__ import annotations

import asyncio
import os
from dataclasses import asdict

from data_provider import get_default_provider, DataProviderError
from pattern_engine import DETECTORS, PatternMatch

DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "USD/CHF", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
    "AUD/JPY", "EUR/AUD",
]

TIMEFRAMES = ["1h", "4h", "1day"]


async def scan_pairs(pattern_key: str, pairs: list[str] | None = None,
                      timeframes: list[str] | None = None,
                      min_score: float = 40.0) -> list[dict]:
    if pattern_key not in DETECTORS:
        raise ValueError(f"Unknown pattern '{pattern_key}'. Known: {list(DETECTORS)}")

    pairs = pairs or os.environ.get("SCAN_PAIRS", "").split(",") or DEFAULT_PAIRS
    pairs = [p.strip() for p in pairs if p.strip()] or DEFAULT_PAIRS
    timeframes = timeframes or TIMEFRAMES
    provider = get_default_provider()
    detector = DETECTORS[pattern_key]

    async def scan_one(pair: str, tf: str) -> dict | None:
        try:
            df = await provider.get_candles(pair, interval=tf, output_size=200)
        except DataProviderError:
            return None
        if len(df) < 30:
            return None
        match: PatternMatch = detector(df)
        if match.score < min_score:
            return None
        result = asdict(match)
        result["pair"] = pair
        result["timeframe"] = tf
        result["last_close"] = float(df["close"].iloc[-1])
        return result

    tasks = [scan_one(pair, tf) for pair in pairs for tf in timeframes]
    results = await asyncio.gather(*tasks)
    hits = [r for r in results if r is not None]

    # rank: completed/near-complete setups with strong scores first
    stage_rank = {"complete": 2, "near_complete": 1, "forming": 0}
    hits.sort(key=lambda r: (stage_rank[r["stage"]], r["score"]), reverse=True)
    return hits
