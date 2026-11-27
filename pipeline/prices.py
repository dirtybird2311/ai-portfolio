"""
Daily closing prices with a second source. Yahoo (yfinance) is the main source; when it is missing the newest
day for some or all tickers (it often settles late, which is why NAV rows went unsaved), the gaps are filled from
Alpaca's market-data API (IEX feed, split-adjusted) when the Alpaca keys are set.

  gaps(close, tickers)           tickers whose newest close is older than the newest day any ticker has
  expected_day(now)              the last completed US trading day, weekends aside (holidays return nothing)
  alpaca_closes(tickers, start)  DataFrame of closes, or None without keys / on any failure
  fill_gaps(close, tickers)      append Alpaca's newest bar where Yahoo lacks it; returns a printable report

IEX closes can differ from consolidated closes by a few cents. A filled value is only used for a day Yahoo does not
have yet; the backfill (python -m pipeline.navfill --all) later rewrites the row from Yahoo's settled close.
"""
import requests

import pandas as pd

from . import config
from .util import now_et

DATA_BASE = "https://data.alpaca.markets/v2/stocks/bars"


def expected_day(now=None):
    """Last completed trading day: today after 4:30 pm ET on a weekday, else the previous weekday."""
    now = now or now_et()
    d = now.date()
    if now.weekday() < 5 and (now.hour, now.minute) >= (16, 30):
        return pd.Timestamp(d)
    d = pd.Timestamp(d) - pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def _real(close):
    return [c for c in close.columns if not str(c).startswith("^")]


def gaps(close, tickers, ref=None):
    """Tickers whose newest close is older than `ref` (default: the newest day any real ticker has)."""
    cols = [t for t in tickers if t in close.columns]
    last = {t: (close[t].dropna().index[-1] if close[t].notna().any() else None) for t in cols}
    ref = ref if ref is not None else max([d for d in (close[c].dropna().index[-1] for c in _real(close)
                                                       if close[c].notna().any())] or [None])
    missing = [t for t in tickers if t not in close.columns]
    return missing + [t for t, d in last.items() if d is None or (ref is not None and d < ref)]


def alpaca_closes(tickers, start, get=requests.get):
    """Closes from Alpaca's IEX daily bars. None without keys or on any error (never raises)."""
    kid = config.secret("ALPACA_API_KEY_ID", required=False)
    sec = config.secret("ALPACA_API_SECRET_KEY", required=False)
    if not (kid and sec) or not tickers:
        return None
    h = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
    rows, token = {}, None
    try:
        for _ in range(20):
            p = {"symbols": ",".join(sorted(set(tickers))), "timeframe": "1Day", "start": str(start)[:10],
                 "adjustment": "split", "feed": "iex", "limit": 10000}
            if token:
                p["page_token"] = token
            r = get(DATA_BASE, headers=h, params=p, timeout=30)
            if getattr(r, "status_code", 200) != 200:
                return None
            j = r.json()
            for sym, bars in (j.get("bars") or {}).items():
                for b in bars:
                    rows.setdefault(sym, {})[pd.Timestamp(b["t"][:10])] = float(b["c"])
            token = j.get("next_page_token")
            if not token:
                break
    except Exception:
        return None
    return pd.DataFrame(rows).sort_index() if rows else None


def fill_gaps(close, tickers, get=requests.get, now=None):
    """Fill the newest missing closes from Alpaca (mutates `close`). Returns (report lines, tickers still short)."""
    want = pd.Timestamp(expected_day(now))
    ref = max([want] + [close[c].dropna().index[-1] for c in _real(close) if close[c].notna().any()])
    short = gaps(close, tickers, ref=ref)
    if not short:
        return [], []
    start = (ref - pd.Timedelta(days=7)).date()
    a = alpaca_closes(sorted(set(short) | {"SPY"}), start, get=get)
    if a is None:
        return [f"price gap: {', '.join(sorted(short))} have no close for {ref.date()} (no Alpaca fallback)"], short
    lines, still = [], []
    for t in short:
        if t not in a.columns:
            still.append(t)
            continue
        have = close[t].dropna().index[-1] if t in close.columns and close[t].notna().any() else None
        new = a[t].dropna()
        new = new[new.index > have] if have is not None else new
        for d, v in new.items():
            close.loc[d, t] = v
        if len(new):
            lines.append(f"{t}: Yahoo had no close after {have.date() if have is not None else 'ever'}; "
                         f"filled {len(new)} day(s) from Alpaca (IEX)")
        if t not in close.columns or close[t].dropna().index[-1] < ref:
            still.append(t)
    close.sort_index(inplace=True)
    return lines, still
