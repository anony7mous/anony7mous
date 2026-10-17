"""
Rule-based technical pattern detectors.

Each detector takes an OHLC DataFrame (oldest->newest) and returns a
PatternMatch: a 0-100 confidence score plus a lifecycle stage:

  "forming"      -> early structure visible, needs more development
  "near_complete"-> structure is there, price is at the decision point
                    (neckline / trendline / resistance) but hasn't broken yet
  "complete"     -> the breakout/confirmation has already happened

This is intentionally rule-based (not ML) so it's transparent, fast, and
doesn't need training data. Swap in a model later without changing the
scanner's interface.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.signal import argrelextrema


@dataclass
class PatternMatch:
    pattern: str
    score: float           # 0-100 confidence this pair matches the pattern
    stage: str             # forming | near_complete | complete
    detail: str = ""
    levels: dict = field(default_factory=dict)  # e.g. {"neckline": 1.0855}


def _swings(df: pd.DataFrame, order: int = 5):
    """Return indices of local swing highs and lows using a rolling window."""
    highs = argrelextrema(df["high"].values, np.greater_equal, order=order)[0]
    lows = argrelextrema(df["low"].values, np.less_equal, order=order)[0]
    # de-duplicate adjacent flat runs
    highs = sorted(set(highs))
    lows = sorted(set(lows))
    return highs, lows


def _pct_diff(a: float, b: float) -> float:
    return abs(a - b) / ((a + b) / 2) * 100


def detect_double_top(df: pd.DataFrame, tolerance_pct: float = 0.15) -> PatternMatch:
    highs, lows = _swings(df, order=4)
    if len(highs) < 2 or len(lows) < 1:
        return PatternMatch("double_top", 0, "forming", "Not enough swing structure yet")

    h1, h2 = highs[-2], highs[-1]
    p1, p2 = df["high"].iloc[h1], df["high"].iloc[h2]
    diff = _pct_diff(p1, p2)

    trough_between = [l for l in lows if h1 < l < h2]
    if not trough_between:
        return PatternMatch("double_top", 20, "forming", "Second peak not confirmed yet")
    neckline = df["low"].iloc[trough_between[-1]]

    last_close = df["close"].iloc[-1]
    score = max(0, 100 - diff * 40)  # peaks within tolerance score higher
    if diff > tolerance_pct * 6:
        score *= 0.4

    if last_close < neckline:
        stage = "complete"
        detail = f"Neckline broken at {neckline:.5f}, breakdown confirmed"
    elif last_close < neckline * 1.002:
        stage = "near_complete"
        detail = f"Price testing neckline at {neckline:.5f}"
    else:
        stage = "forming" if h2 < len(df) - 3 else "near_complete"
        detail = f"Two peaks near {p2:.5f}, watching neckline {neckline:.5f}"

    return PatternMatch("double_top", round(score, 1), stage, detail, {"neckline": neckline})


def detect_double_bottom(df: pd.DataFrame, tolerance_pct: float = 0.15) -> PatternMatch:
    highs, lows = _swings(df, order=4)
    if len(lows) < 2 or len(highs) < 1:
        return PatternMatch("double_bottom", 0, "forming", "Not enough swing structure yet")

    l1, l2 = lows[-2], lows[-1]
    p1, p2 = df["low"].iloc[l1], df["low"].iloc[l2]
    diff = _pct_diff(p1, p2)

    peak_between = [h for h in highs if l1 < h < l2]
    if not peak_between:
        return PatternMatch("double_bottom", 20, "forming", "Second trough not confirmed yet")
    neckline = df["high"].iloc[peak_between[-1]]

    last_close = df["close"].iloc[-1]
    score = max(0, 100 - diff * 40)
    if diff > tolerance_pct * 6:
        score *= 0.4

    if last_close > neckline:
        stage = "complete"
        detail = f"Neckline broken at {neckline:.5f}, breakout confirmed"
    elif last_close > neckline * 0.998:
        stage = "near_complete"
        detail = f"Price testing neckline at {neckline:.5f}"
    else:
        stage = "forming" if l2 < len(df) - 3 else "near_complete"
        detail = f"Two troughs near {p2:.5f}, watching neckline {neckline:.5f}"

    return PatternMatch("double_bottom", round(score, 1), stage, detail, {"neckline": neckline})


def detect_head_and_shoulders(df: pd.DataFrame) -> PatternMatch:
    highs, lows = _swings(df, order=4)
    if len(highs) < 3 or len(lows) < 2:
        return PatternMatch("head_and_shoulders", 0, "forming", "Need three peaks to qualify")

    s1, h, s2 = highs[-3], highs[-2], highs[-1]
    ls, hp, rs = df["high"].iloc[s1], df["high"].iloc[h], df["high"].iloc[s2]

    if not (hp > ls and hp > rs):
        return PatternMatch("head_and_shoulders", 15, "forming", "Middle peak isn't the highest yet")

    shoulder_symmetry = 100 - _pct_diff(ls, rs) * 10
    neck_lows = [l for l in lows if s1 < l < s2]
    if len(neck_lows) < 2:
        return PatternMatch("head_and_shoulders", 30, "forming", "Neckline not fully defined")
    neckline = (df["low"].iloc[neck_lows[0]] + df["low"].iloc[neck_lows[-1]]) / 2

    last_close = df["close"].iloc[-1]
    score = max(0, min(100, shoulder_symmetry))

    if last_close < neckline:
        stage = "complete"
        detail = f"Neckline broken at {neckline:.5f}"
    elif last_close < neckline * 1.002:
        stage = "near_complete"
        detail = f"Right shoulder formed, testing neckline {neckline:.5f}"
    else:
        stage = "near_complete" if s2 >= len(df) - 6 else "forming"
        detail = f"Head at {hp:.5f}, right shoulder forming near {rs:.5f}"

    return PatternMatch("head_and_shoulders", round(score, 1), stage, detail, {"neckline": neckline})


def _trendline_slope(points_x, points_y) -> tuple[float, float]:
    """Least squares fit -> (slope, intercept)."""
    x = np.array(points_x, dtype=float)
    y = np.array(points_y, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    return slope, intercept


def detect_triangle(df: pd.DataFrame, lookback: int = 60) -> PatternMatch:
    window = df.iloc[-lookback:] if len(df) > lookback else df
    highs, lows = _swings(window, order=3)
    if len(highs) < 2 or len(lows) < 2:
        return PatternMatch("triangle", 0, "forming", "Not enough swings in lookback window")

    hs, ht = _trendline_slope(highs, window["high"].iloc[highs])
    ls, lt = _trendline_slope(lows, window["low"].iloc[lows])

    price_range = window["high"].max() - window["low"].min()
    flat_thresh = price_range * 0.0006  # near-zero slope threshold, scaled to pair volatility

    if abs(hs) < flat_thresh and ls > flat_thresh:
        kind, detail = "ascending_triangle", "Flat resistance, rising support"
    elif hs < -flat_thresh and abs(ls) < flat_thresh:
        kind, detail = "descending_triangle", "Falling resistance, flat support"
    elif hs < -flat_thresh and ls > flat_thresh:
        kind, detail = "symmetrical_triangle", "Converging trendlines"
    else:
        return PatternMatch("triangle", 10, "forming", "Trendlines not converging cleanly")

    last_idx = len(window) - 1
    resistance_now = hs * last_idx + ht
    support_now = ls * last_idx + lt
    channel_width_now = resistance_now - support_now
    channel_width_start = (hs * highs[0] + ht) - (ls * lows[0] + lt)
    compression = 1 - (channel_width_now / channel_width_start) if channel_width_start else 0
    score = max(0, min(100, compression * 100))

    last_close = window["close"].iloc[-1]
    if last_close > resistance_now:
        stage, detail = "complete", f"{detail} — broke above resistance {resistance_now:.5f}"
    elif last_close < support_now:
        stage, detail = "complete", f"{detail} — broke below support {support_now:.5f}"
    elif channel_width_now < channel_width_start * 0.35:
        stage, detail = "near_complete", f"{detail} — apex close, width tightening"
    else:
        stage, detail = "forming", detail

    return PatternMatch(kind, round(score, 1), stage, detail,
                         {"resistance": round(resistance_now, 5), "support": round(support_now, 5)})


def detect_flag(df: pd.DataFrame, pole_lookback: int = 20, flag_lookback: int = 12) -> PatternMatch:
    """Bull/bear flag: a sharp directional 'pole' move followed by a tight
    channel consolidating against that direction."""
    if len(df) < pole_lookback + flag_lookback:
        return PatternMatch("flag", 0, "forming", "Not enough candles for pole + flag")

    pole = df.iloc[-(pole_lookback + flag_lookback):-flag_lookback]
    flag = df.iloc[-flag_lookback:]

    pole_move = pole["close"].iloc[-1] - pole["close"].iloc[0]
    pole_range = pole["high"].max() - pole["low"].min()
    if pole_range == 0:
        return PatternMatch("flag", 0, "forming", "No directional move detected")
    pole_strength = abs(pole_move) / pole_range  # closer to 1 = clean directional pole

    direction = "bull" if pole_move > 0 else "bear"

    flag_highs, flag_lows = _swings(flag, order=2)
    flag_range = flag["high"].max() - flag["low"].min()
    tightness = 1 - min(1, flag_range / pole_range)  # tighter flag vs pole = higher score

    # flag should drift mildly against the pole direction (or sideways)
    flag_slope, _ = _trendline_slope(range(len(flag)), flag["close"])
    against_trend = (flag_slope < 0) if direction == "bull" else (flag_slope > 0)

    score = pole_strength * 45 + tightness * 45 + (10 if against_trend else 0)
    score = max(0, min(100, score))

    last_close = df["close"].iloc[-1]
    flag_high, flag_low = flag["high"].max(), flag["low"].min()

    if direction == "bull":
        if last_close > flag_high:
            stage, detail = "complete", f"Bull flag broke out above {flag_high:.5f}"
        elif last_close > flag_high * 0.998:
            stage, detail = "near_complete", f"Price pressing flag top {flag_high:.5f}"
        else:
            stage, detail = "forming", f"Bull pole then consolidation, channel top {flag_high:.5f}"
    else:
        if last_close < flag_low:
            stage, detail = "complete", f"Bear flag broke down below {flag_low:.5f}"
        elif last_close < flag_low * 1.002:
            stage, detail = "near_complete", f"Price pressing flag bottom {flag_low:.5f}"
        else:
            stage, detail = "forming", f"Bear pole then consolidation, channel bottom {flag_low:.5f}"

    return PatternMatch(f"{direction}_flag", round(score, 1), stage, detail,
                         {"flag_high": round(flag_high, 5), "flag_low": round(flag_low, 5)})


def detect_support_resistance_breakout(df: pd.DataFrame, lookback: int = 80, touches_needed: int = 3,
                                        tolerance_pct: float = 0.12) -> PatternMatch:
    window = df.iloc[-lookback:] if len(df) > lookback else df
    highs, lows = _swings(window, order=3)

    def cluster_level(idxs, series):
        if len(idxs) < touches_needed:
            return None, 0
        vals = series.iloc[idxs].values
        vals_sorted = np.sort(vals)
        best_level, best_count = None, 0
        for v in vals_sorted:
            close_vals = vals[np.abs(vals - v) / v * 100 < tolerance_pct]
            if len(close_vals) > best_count:
                best_count = len(close_vals)
                best_level = float(np.mean(close_vals))
        return best_level, best_count

    res_level, res_touches = cluster_level(highs, window["high"])
    sup_level, sup_touches = cluster_level(lows, window["low"])

    last_close = df["close"].iloc[-1]
    candidates = []
    if res_level and res_touches >= touches_needed:
        dist_pct = (res_level - last_close) / res_level * 100
        score = min(100, res_touches * 22)
        if last_close > res_level:
            stage, detail = "complete", f"Broke above resistance {res_level:.5f} ({res_touches} touches)"
        elif dist_pct < 0.15:
            stage, detail = "near_complete", f"Testing resistance {res_level:.5f} ({res_touches} touches)"
        else:
            stage, detail = "forming", f"Approaching resistance {res_level:.5f} ({res_touches} touches)"
        candidates.append(PatternMatch("resistance_breakout", round(score, 1), stage, detail,
                                        {"resistance": res_level}))

    if sup_level and sup_touches >= touches_needed:
        dist_pct = (last_close - sup_level) / sup_level * 100
        score = min(100, sup_touches * 22)
        if last_close < sup_level:
            stage, detail = "complete", f"Broke below support {sup_level:.5f} ({sup_touches} touches)"
        elif dist_pct < 0.15:
            stage, detail = "near_complete", f"Testing support {sup_level:.5f} ({sup_touches} touches)"
        else:
            stage, detail = "forming", f"Approaching support {sup_level:.5f} ({sup_touches} touches)"
        candidates.append(PatternMatch("support_breakdown", round(score, 1), stage, detail,
                                        {"support": sup_level}))

    if not candidates:
        return PatternMatch("support_resistance", 0, "forming", "No well-tested level found yet")
    return max(candidates, key=lambda c: c.score)


# Registry so the scanner / setup parser can look detectors up by name
DETECTORS = {
    "double_top": detect_double_top,
    "double_bottom": detect_double_bottom,
    "head_and_shoulders": detect_head_and_shoulders,
    "triangle": detect_triangle,
    "ascending_triangle": detect_triangle,
    "descending_triangle": detect_triangle,
    "symmetrical_triangle": detect_triangle,
    "flag": detect_flag,
    "bull_flag": detect_flag,
    "bear_flag": detect_flag,
    "support_resistance": detect_support_resistance_breakout,
    "resistance_breakout": detect_support_resistance_breakout,
    "support_breakdown": detect_support_resistance_breakout,
}
