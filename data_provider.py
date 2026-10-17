"""
Data provider layer for forex OHLC candles.

Default implementation targets Twelve Data (https://twelvedata.com) which has a
free tier that covers forex majors/minors at 1min-1day intervals — good enough
to prototype a scanner. Swap in OANDA or Polygon by implementing the same
`get_candles` interface and pointing scanner.py at your class instead.
"""
from __future__ import annotations

import os
import httpx
import pandas as pd
from typing import Literal

Interval = Literal["15min", "1h", "4h", "1day"]

TWELVE_DATA_BASE = "https://api.twelvedata.com"


class DataProviderError(Exception):
    pass


class TwelveDataProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("TWELVE_DATA_API_KEY")
        if not self.api_key:
            raise DataProviderError(
                "TWELVE_DATA_API_KEY is not set. Sign up free at twelvedata.com "
                "and add the key to your .env file."
            )

    async def get_candles(
        self, pair: str, interval: Interval = "4h", output_size: int = 200
    ) -> pd.DataFrame:
        """
        Returns a DataFrame indexed by datetime with columns:
        open, high, low, close (float). Most recent candle is last row.
        """
        params = {
            "symbol": pair,
            "interval": interval,
            "outputsize": output_size,
            "apikey": self.api_key,
            "order": "ASC",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{TWELVE_DATA_BASE}/time_series", params=params)
            data = resp.json()

        if data.get("status") == "error" or "values" not in data:
            raise DataProviderError(
                f"Failed to fetch {pair} @ {interval}: {data.get('message', data)}"
            )

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        return df[["open", "high", "low", "close"]]


def get_default_provider() -> TwelveDataProvider:
    return TwelveDataProvider()
