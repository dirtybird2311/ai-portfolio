"""
ALTERNATIVE SIGNALS: short interest (FINRA) and "Lazy Prices" (10-K text changes, SEC)
run:  python -m pipeline.altdata --minutes 300        (Actions > Backfill 10-K similarity; the weekly run
                                                       also advances it ~40 minutes at a time)

Short interest  FINRA's free twice-monthly file (cdn.finra.org) of every stock's short position.
                Signal: days to cover (shares short / average daily volume); heavily shorted stocks tend
                to lag (Asquith, Pathak & Ritter 2005; Hong et al. 2016). Exchange-listed stocks are in
                the file since June 2021, so history can test about 5 years. A file is treated as public
                10 days after its settlement date (FINRA publishes ~7 business days later).

Lazy Prices     How much a company's annual report (10-K) wording changed from the year before: cosine
                similarity of word counts. Firms that change a lot tend to lag, and the market is slow
                to notice (Cohen, Malloy & Nguyen 2020). Similarities are saved in
                state/lazy_prices.json by filing date, so history is point-in-time.

Both are candidate signals: zero weight until history clears their bar.
"""
import argparse
import csv
import io
import math
import re
import time
from bisect import bisect_right
from collections import Counter
from datetime import date, timedelta

import requests

from .util import now_et, read_json, state_path, write_json

# ==================================================================== short interest (FINRA)
FINRA_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{d:%Y%m%d}.csv"
SHORT_START = date(2021, 6, 1)          # exchange-listed stocks are in FINRA's file from June 2021
PUBLISH_LAG_DAYS = 10


def norm_symbol(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def settlement_candidates(start, end):
    """FINRA settlement dates: around the 15th and the last business day of each month. Returns
    [[candidate dates, most likely first]] per half-month."""
    out = []
    d = date(start.year, start.month, 1)
    while d <= end:
        mid = [date(d.year, d.month, x) for x in (15, 14, 13, 12, 16)]
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        last = [nxt - timedelta(days=k) for k in range(1, 6)]
        out += [[x for x in mid if start <= x <= end], [x for x in last if start <= x <= end]]
        d = nxt
    return [c for c in out if c]


def parse_short_file(text):
    """{SYMBOL: days to cover}. Handles pipe- or comma-separated files and FINRA's column names."""
    if not text:
        return {}
    first = text.split("\n", 1)[0]
    delim = "|" if first.count("|") > first.count(",") else ","
    rows = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = {c.lower(): c for c in (rows.fieldnames or [])}
    pick = lambda *names: next((cols[n.lower()] for n in names if n.lower() in cols), None)
    sym = pick("symbolCode", "issueSymbolIdentifier", "symbol")
    dtc = pick("daysToCoverQuantity", "daysToCoverNumber", "daysToCover")
    short = pick("currentShortPositionQuantity", "currentShortShareNumber", "currentShortPosition")
    adv = pick("averageDailyVolumeQuantity", "averageShortShareNumber", "averageDailyVolume")
    out = {}
    num = lambda x: float(str(x).replace(",", "")) if x not in (None, "") else None
    for r in rows:
        try:
            s = norm_symbol(r[sym]) if sym else None
            v = num(r.get(dtc)) if dtc else None
            if v is None and short and adv and num(r.get(adv)):
                v = num(r.get(short)) / num(r.get(adv))
        except (ValueError, TypeError, KeyError):
            continue
        if s and v is not None and v >= 0:
            out[s] = round(v, 3)
    return out


def fetch_short(d, get=requests.get):
    try:
        r = get(FINRA_URL.format(d=d), timeout=60, headers={"User-Agent": "Mozilla/5.0 (personal research)"})
    except Exception:
        return None
    if r.status_code != 200 or not r.text or len(r.text) < 1000:
        return None
    parsed = parse_short_file(r.text)
    return parsed or None


def refresh_short_history(hist, get=requests.get, today=None, sleep=0.3):
    """hist: {"files": {settlement date: {SYMBOL: days to cover}}, "missing": [dates tried, not found]}.
    Downloads each half-month's file once (trying the likely settlement dates)."""
    today = today or now_et().date()
    files, missing = hist.setdefault("files", {}), set(hist.setdefault("missing", []))
    added = 0
    for cands in settlement_candidates(SHORT_START, today - timedelta(days=7)):
        if any(c.isoformat() in files for c in cands):
            continue
        recent = (today - cands[0]).days < 45             # recent misses may just not be published yet
        for c in cands:
            if c.isoformat() in missing and not recent:
                continue
            got = fetch_short(c, get)
            time.sleep(sleep)
            if got:
                files[c.isoformat()] = got
                added += 1
                break
            if not recent:
                missing.add(c.isoformat())
    hist["missing"] = sorted(missing)
    return added


def short_at(hist, d):
    """{SYMBOL: days to cover} as the public knew it on date d (settlement + publishing lag)."""
    files = hist.get("files") or {}
    ds = sorted(files)
    cut = (date.fromisoformat(d[:10]) - timedelta(days=PUBLISH_LAG_DAYS)).isoformat()
    k = bisect_right(ds, cut)
    if not k or (date.fromisoformat(cut) - date.fromisoformat(ds[k - 1])).days > 45:
        return {}
    return files[ds[k - 1]]


def latest_short(get=requests.get, today=None):
    """Newest published file: (settlement date, {SYMBOL: days to cover}), or (None, {})."""
    today = today or now_et().date()
    for d in sorted({x for c in settlement_candidates(today - timedelta(days=40), today - timedelta(days=5))
                     for x in c}, reverse=True):
        got = fetch_short(d, get)
        if got:
            return d.isoformat(), got
    return None, {}


# ==================================================================== Lazy Prices (10-K similarity)
LAZY_FILE = "lazy_prices.json"
LAZY_START = "2014-01-01"               # 10-Ks from here: similarities from ~2015, 10+ years to test
LAZY_MINUTES_WEEKLY = 40
WORD = re.compile(r"[a-z]{3,}")


def word_counts(text):
    return Counter(WORD.findall((text or "").lower()))


def cosine(a, b):
    if not a or not b:
        return None
    small, big = (a, b) if len(a) < len(b) else (b, a)
    dot = sum(v * big.get(k, 0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return round(dot / (na * nb), 5) if na and nb else None


def ten_k_filings(sec, cik, since=LAZY_START):
    """Oldest-first [{filed, accession, doc}] of original 10-Ks (not amendments) since `since`."""
    sub = sec.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json") or {}
    pages = [(sub.get("filings") or {}).get("recent") or {}]
    for f in (sub.get("filings") or {}).get("files") or []:
        if f.get("filingTo", "9999") >= since:
            pages.append(sec.get(f"https://data.sec.gov/submissions/{f['name']}") or {})
    out = {}
    for r in pages:
        for i, form in enumerate(r.get("form", [])):
            if form == "10-K" and r["filingDate"][i] >= since:
                out[r["accessionNumber"][i]] = {"filed": r["filingDate"][i], "accession": r["accessionNumber"][i],
                                                "doc": r["primaryDocument"][i]}
    return sorted(out.values(), key=lambda x: x["filed"])


def update_company(sec, cik, entry):
    """Adds similarities for any 10-K not yet compared with the one before it. entry: {"sims": [[filed,
    sim]], "last": filed of the newest 10-K handled}. Returns the number of documents read."""
    filings = ten_k_filings(sec, cik)
    last = entry.get("last") or ""
    todo = [k for k in range(1, len(filings)) if filings[k]["filed"] > last]
    prev_counts, prev_k, reads = None, None, 0
    for k in todo:
        if prev_k != k - 1:
            p = filings[k - 1]
            prev_counts = word_counts(sec.document_text(cik, p["accession"], p["doc"]))
            reads += 1
        f = filings[k]
        counts = word_counts(sec.document_text(cik, f["accession"], f["doc"]))
        reads += 1
        sim = cosine(prev_counts, counts)
        if sim is not None:
            entry.setdefault("sims", []).append([f["filed"], sim])
        prev_counts, prev_k = counts, k
    if filings:
        entry["last"] = filings[-1]["filed"]
    entry["checked"] = now_et().date().isoformat()
    return reads


def update_lazy(sec, companies, minutes=LAZY_MINUTES_WEEKLY, refresh_days=30):
    """companies: [(ticker, cik)]. Works through companies not checked in `refresh_days`, oldest first,
    until the time budget runs out; saves as it goes. Marks the backfill complete once every company
    has been read at least once."""
    st = read_json(state_path(LAZY_FILE), {}) or {}
    data = st.setdefault("companies", {})
    today = now_et().date()
    stale = lambda t: not data.get(t, {}).get("checked") or \
        (today - date.fromisoformat(data[t]["checked"])).days >= refresh_days
    order = sorted([c for c in companies if stale(c[0])], key=lambda c: data.get(c[0], {}).get("checked", ""))
    end, n, reads = time.time() + minutes * 60, 0, 0
    for t, cik in order:
        if time.time() >= end:
            break
        try:
            reads += update_company(sec, cik, data.setdefault(t, {}))
        except Exception as e:
            print(f"    ! 10-K text {t}: {str(e)[:80]}")
            data.setdefault(t, {})["checked"] = today.isoformat()
        n += 1
        if n % 25 == 0:
            write_json(state_path(LAZY_FILE), st)
    st["complete"] = all(data.get(t, {}).get("checked") for t, _ in companies)
    st["updated"] = today.isoformat()
    write_json(state_path(LAZY_FILE), st)
    left = sum(stale(t) for t, _ in companies)
    print(f"    10-K similarity: {n} companies checked ({reads} reports read); {left} still to do"
          + ("" if st["complete"] else " (backfill in progress: not tested until complete)"))
    return st


def lazy_history(st=None):
    """{ticker: [(filed, similarity)]} oldest first; {} until the backfill is complete."""
    st = st if st is not None else (read_json(state_path(LAZY_FILE), {}) or {})
    if not st.get("complete"):
        return {}
    return {t: sorted((f, s) for f, s in e.get("sims", [])) for t, e in (st.get("companies") or {}).items() if e.get("sims")}


def lazy_at(hist, t, d, max_age_days=450):
    rows = hist.get(t) or []
    k = bisect_right([x[0] for x in rows], d)
    if not k or (date.fromisoformat(d[:10]) - date.fromisoformat(rows[k - 1][0])).days > max_age_days:
        return None
    return rows[k - 1][1]


def latest_lazy(max_age_days=450):
    """{ticker: similarity of its latest 10-K to the one before}, for the screen (any company done so far)."""
    st = read_json(state_path(LAZY_FILE), {}) or {}
    today = now_et().date().isoformat()
    out = {}
    for t, e in (st.get("companies") or {}).items():
        v = lazy_at({t: sorted(e.get("sims") or [])}, t, today, max_age_days)
        if v is not None:
            out[t] = v
    return out


# ==================================================================== job (backfill)
def main(minutes=300):
    import pandas as pd
    from .sec import SEC
    bp = state_path("bench.csv")
    if not bp.exists():
        print("No bench yet (the screen hasn't run): nothing to do.")
        return {"status": "no bench"}
    bench = pd.read_csv(bp).dropna(subset=["cik"])
    st = update_lazy(SEC(), [(r.ticker, int(r.cik)) for r in bench.itertuples()], minutes=minutes)
    return {"status": "complete" if st.get("complete") else "partial"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300)
    a = ap.parse_args()
    main(a.minutes)
