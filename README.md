# Forex setup scanner

Paste a setup (text, a chart screenshot, or both) → the platform scans a list
of forex pairs across multiple timeframes and returns which ones are
currently **forming**, **near-complete**, or have just **broken out** of that
pattern.

## How it works

```
User input (text / image)
        │
        ▼
setup_parser.py ──► Claude reads the description or chart and maps it
                     to one of the known pattern types (double_top,
                     bull_flag, ascending_triangle, etc.)
        │
        ▼
scanner.py ──► for every pair × timeframe:
                 - data_provider.py fetches OHLC candles (Twelve Data)
                 - pattern_engine.py runs the matching rule-based detector
                 - keeps results above a confidence threshold
        │
        ▼
Ranked results: breakouts first, then near-complete, then forming,
sorted by confidence score
```

## Why rule-based pattern detection, not an ML classifier

Chart patterns (double tops, flags, triangles, head & shoulders, S/R
breaks) have precise geometric definitions — swing highs/lows, neckline
symmetry, trendline slope, channel width. `pattern_engine.py` implements
each one directly against the price data (via `scipy` swing-point
detection + linear regression on trendlines). This is transparent (you can
see exactly why a pair scored 78 vs 40), fast, needs no training data, and
is easy to extend — add a new function and register it in `DETECTORS`.

The one place an LLM genuinely helps is **interpreting what the user
pasted** — free text or a screenshot doesn't map cleanly onto a fixed
schema otherwise. That's the only place `setup_parser.py` calls Claude.

## What's real vs. what's a stand-in

- **Real & working:** the pattern-detection math (`pattern_engine.py`),
  the FastAPI backend (`main.py`, `scanner.py`), the Claude-based
  text/image interpreter (`setup_parser.py`).
- **Stand-in:** `frontend/demo.jsx` uses mock scan results so you can see
  and click through the UX immediately without any API keys. Swap the
  mock data for a `fetch('/scan', ...)` call once your backend is
  deployed.
- **Needs your own keys:** live forex candles require a data provider
  account (free tier is fine to start). I can't fetch live market data
  from my own sandbox — no outbound network access there — so this part
  is code you run, not something I could demo live myself.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in TWELVE_DATA_API_KEY and ANTHROPIC_API_KEY in .env
uvicorn main:app --reload
```

Get a free Twelve Data key at twelvedata.com (covers forex majors/minors
down to 1-minute bars on the free tier, rate-limited — fine for a scanner
that polls every few minutes). Swap in OANDA or Polygon by implementing
the same `get_candles()` method in `data_provider.py` if you outgrow it.

Test it:

```bash
curl -X POST http://localhost:8000/scan \
  -F "description=double bottom with a clear neckline about to break out"
```

Or with an image:

```bash
curl -X POST http://localhost:8000/scan \
  -F "image=@chart_screenshot.png" \
  -F "description=looking for this exact setup"
```

## Extending it

- **New pattern:** write a function in `pattern_engine.py` that takes an
  OHLC DataFrame and returns a `PatternMatch(pattern, score, stage,
  detail, levels)`, then add it to `DETECTORS` and `KNOWN_PATTERNS` in
  `setup_parser.py`.
- **More pairs / crypto / stocks:** `SCAN_PAIRS` in `.env`, or extend
  `data_provider.py` — the detector logic itself doesn't care what
  instrument it's fed.
- **Alerting:** wrap `scanner.scan_pairs()` in a scheduled job (cron /
  APScheduler) and push results near/at `complete` stage to a webhook,
  email, or Telegram bot — that's the natural next step once the core
  scan works.
- **Production notes:** add auth, rate-limit `/scan`, cache candle
  fetches (they don't need to be re-pulled on every request), and
  restrict CORS `allow_origins` before deploying publicly.

## Honest limitations to know going in

- Free-tier forex data APIs are usually delayed by a few minutes and
  rate-limited — fine for swing-trade setups on 1h/4h/1day charts, not
  for scalping or true tick-level scanning.
- The rule-based detectors are good at clean, textbook-shaped patterns.
  Messy or ambiguous price action will score lower even when a
  discretionary trader might still call it a match — that's inherent to
  any geometric rule set, not a bug to "fix" so much as a tradeoff to be
  aware of.
- Nothing here is trading advice or a signal service — treat scan
  results as a screening shortlist to pull up and evaluate yourself, the
  same way you'd use a screener on TradingView.
