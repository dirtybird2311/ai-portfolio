"""
DECISION LEDGER + GRADING  —  how the system learns whether it is any good (see EVALUATION.md).

Recording
  state/decision_ledger.csv   one row per stock per judge for EVERY stock judged (rejections too):
                              each judge's probability, plus "panel" (live average) and "base_rate"
                              (the free statistics alone) rows. Replayed judges (Opus, ablated twins)
                              are added later by pipeline/replay.py with the original decision date.
                              Stamped with code version, settings hash and prompt hash.
  state/catalyst_ledger.csv   dated catalysts with their expected direction
  state/process_errors.csv    counts of mechanical mistakes, fed back into the next run's prompts
  state/sell_ledger.csv       every holding at each rebuild: sold (and why) or kept
  state/critic_ledger.csv     every planned buy with the critic's verdict
  state/macro_ledger.csv      each full macro run: per-sector probability, base rate, tilt, and the
                              simple momentum rule's call (the free opponent)

Grading (weekly tracking job)
  state/grades.csv            each judged stock's return 2, 4 and 13 weeks later minus its
                              EQUAL-WEIGHTED sector ("resid"; the sector-ETF version is kept as
                              "resid_etf"); beat = resid > 0
  state/catalyst_grades.csv   did the stock move the expected way around each catalyst?
  state/macro_grades.csv      each sector ETF vs SPY 4 and 8 weeks after each macro run

Evaluation (monthly email): per-judge and per-combination IC and Brier skill, panel vs base rate,
calibration, bought vs passed over, sold vs kept, critic flags, catalysts, pruning tests, the macro
agent vs its momentum-rule opponent, the pre-registered verdicts, and replay reminders.
"""
import itertools
import math
import re
from datetime import date

import numpy as np
import pandas as pd

from . import config
from .util import append_csv, now_et, read_json, state_path, write_json

HORIZONS = {"2w": 10, "4w": 20, "13w": 65}        # trading days
MACRO_HORIZONS = {"4w": 20, "8w": 40}
REBUILD_SPACING = 10                               # trading days between rebuilds (for overlap correction)
MIN_NAMES_PER_DATE = 5                             # an IC needs at least this many graded stocks that day
CAT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}): (.*) \(impact: (\w+); source: (\w+)\)$")
PSEUDO = ("panel", "panel_sharp", "base_rate")


def _read(name, **kw):
    p = state_path(name)
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


def _ledger():
    return _read("decision_ledger.csv", dtype={"date": str})


# ==================================================================== recording
def record_judgments(results, judged):
    d = results["date"]
    v = results.get("versions") or {}
    rows, cats = [], []
    for t, s in results["stocks"].items():
        if t not in judged:
            continue
        verdict = s["verdict"]
        common = {"date": d, "ticker": t, "sector": s.get("sector"), "sector_etf": config.SECTORS.get(s.get("sector"), "SPY"),
                  "incumbent": bool(s.get("incumbent")), "composite": round(float(s.get("composite", 0)), 4),
                  "news_score": (s.get("news") or {}).get("score"), "price": s.get("price"),
                  "base_p": verdict.get("base_p"), "panel_p": verdict.get("probability"),
                  "edge_pts": verdict.get("edge_pts"), "spread": verdict.get("spread"),
                  "disagreement": bool(verdict.get("disagreement")),
                  "base_group": (s.get("base_rate") or {}).get("group"),
                  "dominant_factor": (s.get("sensitivity") or {}).get("_dominant"),
                  "code_version": v.get("code_version"), "config_hash": v.get("config_hash"),
                  "prompt_hash": v.get("prompt_hash"), "replay": False}
        for jid, j in (verdict.get("judges") or {}).items():
            rows.append(dict(common, judge=jid, model=j.get("model"), live=bool(j.get("live")), p=j.get("probability"),
                             exception=bool(j.get("exception")), winner=j.get("winner"),
                             primary_driver=j.get("primary_driver")))
        rows.append(dict(common, judge="panel", model="live average (log-odds)", live=True, p=verdict.get("probability"),
                         winner=verdict.get("winner"), primary_driver=verdict.get("primary_driver")))
        rows.append(dict(common, judge="base_rate", model="history (free)", live=False, p=verdict.get("base_p")))
        if verdict.get("probability_sharp") is not None:
            rows.append(dict(common, judge="panel_sharp", model="live average, sharpened x1.5 (shadow)", live=False,
                             p=verdict.get("probability_sharp")))
        for item in s.get("dossier") or []:
            if item.get("kind") != "catalyst":
                continue
            m = CAT_RE.match(item.get("text", ""))
            if m and m.group(3) in ("positive", "negative"):
                cats.append({"made_on": d, "ticker": t, "sector_etf": common["sector_etf"], "event_date": m.group(1),
                             "event": m.group(2)[:200], "impact": m.group(3), "source_class": m.group(4)})
    append_csv(state_path("decision_ledger.csv"), rows)
    if cats:
        old = _read("catalyst_ledger.csv", dtype=str)
        seen = set(zip(old.ticker, old.event_date, old.event)) if len(old) else set()
        append_csv(state_path("catalyst_ledger.csv"), [c for c in cats if (c["ticker"], c["event_date"], c["event"]) not in seen])
    return len(rows)


def record_signals(results):
    """Shadow signals (config.SHADOW_SIGNALS) as pseudo-judge rows 'sig_<name>': the score -2..+2 becomes
    p = 0.5 + 0.1 x score, so the look-back's rank correlations grade it like any shadow judge. Never live."""
    d, rows = results["date"], []
    ver = results.get("versions") or {}
    for t, s in results["stocks"].items():
        v = s.get("verdict") or {}
        for name, sig in (s.get("shadow_signals") or {}).items():
            if not isinstance(sig, dict) or sig.get("score") is None:
                continue
            rows.append({"date": d, "ticker": t, "sector": s.get("sector"), "sector_etf": config.SECTORS.get(s.get("sector"), "SPY"),
                         "incumbent": bool(s.get("incumbent")), "composite": round(float(s.get("composite", 0)), 4),
                         "price": s.get("price"), "base_p": v.get("base_p"), "panel_p": v.get("probability"),
                         "edge_pts": v.get("edge_pts"), "code_version": ver.get("code_version"),
                         "config_hash": ver.get("config_hash"), "prompt_hash": ver.get("prompt_hash"),
                         "replay": False, "judge": f"sig_{name}",
                         "model": f"shadow signal ({config.MODELS['shadow_signals']})", "live": False,
                         "p": round(0.5 + 0.1 * float(sig["score"]), 3)})
    led = _ledger()
    have = set(zip(led.date, led.ticker, led.judge)) if len(led) else set()
    rows = [r for r in rows if (r["date"], r["ticker"], r["judge"]) not in have]
    append_csv(state_path("decision_ledger.csv"), rows)
    return len(rows)


def record_replay(rows):
    """Rows from pipeline/replay.py: {date, ticker, judge, model, p, ...} for past decision dates."""
    led = _ledger()
    have = set(zip(led.date, led.ticker, led.judge)) if len(led) else set()
    new = [dict(r, replay=True, live=False) for r in rows if (r["date"], r["ticker"], r["judge"]) not in have]
    append_csv(state_path("decision_ledger.csv"), new)
    return len(new)


def record_labels(rows):
    """Headline labels from the live labeler and the background labelers (same headlines)."""
    append_csv(state_path("label_ledger.csv"), rows)


def record_process_errors(results, session=None):
    """Tally the mechanical mistakes of this run so the next run's prompts can warn about them."""
    st = results["stocks"]
    fresh = {t: s for t, s in st.items() if not s["verdict"].get("reused_from")}
    judges = [j for s in fresh.values() for j in (s["verdict"].get("judges") or {}).values()]
    counts = {
        "invalid_citations": sum(len(s["verdict"].get("invalid_citations") or []) for s in fresh.values()),
        "judge_replies_unusable": sum(1 for j in judges if j.get("probability") is None),
        "uncited_adjustments": sum(int(j.get("dropped_adjustments") or 0) for j in judges),
        "panel_failed": sum(1 for s in fresh.values() if s["verdict"].get("panel_failed")),
        "judge_disagreements": sum(1 for s in fresh.values() if s["verdict"].get("disagreement")),
        "missing_exit_condition": sum(1 for s in fresh.values()
                                      if str(s["verdict"].get("exit_condition", "")).startswith("not provided")),
        "model_fallbacks": sum(1 for u in (session.usage if session else []) if u.get("fallback")),
    }
    append_csv(state_path("process_errors.csv"),
               [{"date": results["date"], "category": k, "count": v, "stocks": len(fresh)} for k, v in counts.items()])
    return counts


def record_sells(team_date, rows):
    """rows: [{ticker, account, action: sold|kept, reason, edge_pts, probability}] for every holding."""
    append_csv(state_path("sell_ledger.csv"), [dict(r, date=team_date) for r in rows])


def record_critic(team_date, trades):
    append_csv(state_path("critic_ledger.csv"), [
        {"date": team_date, "ticker": t["ticker"], "account": t["account"], "action": t["action"],
         "critic": t.get("critic", "PASS"), "status": t.get("status")} for t in trades if t["ticker"] != "SPY"])


def record_macro(day, sectors):
    """sectors: {sector: {etf, base_p, p, disagreement_pts, tilt, momentum_rank, momentum_p}}"""
    append_csv(state_path("macro_ledger.csv"), [dict(v, date=day, sector=s) for s, v in sectors.items()])


FEEDBACK_TEXT = {
    "invalid_citations": "{n} debate claims cited nothing or cited dossier ids that don't exist. Cite only listed D-ids; "
                         "a claim without a valid citation is ignored.",
    "judge_replies_unusable": "{n} judge replies had no usable JSON. End with exactly one ```json block in the requested shape.",
    "uncited_adjustments": "{n} probability adjustments had no valid dossier citation and were removed. Cite D-ids for every adjustment.",
    "missing_exit_condition": "{n} verdicts had no exit condition. Always give a specific, observable exit condition.",
}


def error_feedback():
    """Short process note for the next run's prompts, built from the last run's error tally.
    Mechanical fixes only; lessons about judgment need your approval (see EVALUATION.md)."""
    df = _read("process_errors.csv", dtype={"date": str})
    if df.empty:
        return ""
    last = df[df.date == df.date.max()]
    lines = [FEEDBACK_TEXT[r.category].format(n=int(r["count"])) for _, r in last.iterrows()
             if r.category in FEEDBACK_TEXT and int(r["count"]) > 0]
    return ("PROCESS NOTES FROM THE LAST RUN (avoid repeating these):\n- " + "\n- ".join(lines) + "\n\n") if lines else ""


# ==================================================================== grading
def _graded_keys():
    g = _read("grades.csv", dtype={"date": str})
    return set(zip(g.date, g.ticker, g.horizon)) if len(g) else set()


def _catalyst_done():
    g = _read("catalyst_grades.csv", dtype=str)
    return set(zip(g.ticker, g.event_date, g.event)) if len(g) else set()


def pending():
    """True when something is still waiting to be graded (tracking then downloads the universe)."""
    led = _ledger()
    if led.empty:
        return False
    graded = _graded_keys()
    return any((r.date, r.ticker, h) not in graded
               for r in led[["date", "ticker"]].drop_duplicates().itertuples() for h in HORIZONS)


def tickers_needed():
    """Tickers (and ETFs) needed to grade what's ungraded. The equal-weighted sector benchmark also
    needs every bench stock, which tracking adds when pending() is true."""
    led = _ledger()
    out = {"SPY"} | set(config.SECTORS.values())
    if len(led):
        graded = _graded_keys()
        for r in led[["date", "ticker"]].drop_duplicates().itertuples():
            if any((r.date, r.ticker, h) not in graded for h in HORIZONS):
                out.add(r.ticker)
    cats = _read("catalyst_ledger.csv", dtype=str)
    done = _catalyst_done()
    for r in cats.itertuples() if len(cats) else []:
        if (r.ticker, r.event_date, r.event) not in done:
            out.add(r.ticker)
    lab = _read("label_ledger.csv", dtype={"date": str})
    if len(lab):
        g = _read("label_grades.csv", dtype={"date": str})
        seen = set(zip(g.date, g.ticker)) if len(g) else set()
        out |= {r.ticker for r in lab[["date", "ticker"]].drop_duplicates().itertuples() if (r.date, r.ticker) not in seen}
    return out


def _ret(px, t, i, j):
    if t not in px or j >= len(px.index) or i < 0:
        return None
    a, b = px[t].iloc[i], px[t].iloc[j]
    if pd.isna(a) or pd.isna(b) or a <= 0:
        return None
    return float(b / a - 1)


def grade(px, sector_of=None):
    """Grade every (decision date, stock) whose horizon has passed, against the equal-weighted sector
    built from `px` (all bench stocks), with the sector ETF as a secondary benchmark. The clock starts
    at the close of the first trading day AFTER the decision (no peeking)."""
    from .history import ew_sector_index
    led = _ledger()
    if led.empty or "SPY" not in px:
        return 0
    sector_of = sector_of or {}
    ew = ew_sector_index(px, sector_of) if sector_of else pd.DataFrame(index=px.index)
    graded = _graded_keys()
    rows = []
    for r in led[["date", "ticker", "sector", "sector_etf"]].drop_duplicates(["date", "ticker"]).itertuples():
        i = px.index.searchsorted(pd.Timestamp(r.date) + pd.Timedelta(days=1))
        for h, n in HORIZONS.items():
            if (r.date, r.ticker, h) in graded:
                continue
            j = i + n
            if j >= len(px.index):
                continue
            ret, spy = _ret(px, r.ticker, i, j), _ret(px, "SPY", i, j)
            if ret is None or spy is None:
                continue
            etf = _ret(px, r.sector_etf, i, j)
            etf = spy if etf is None else etf
            ews = _ret(ew, r.sector, i, j) if r.sector in ew else None
            bench = ews if ews is not None else etf
            rows.append({"date": r.date, "ticker": r.ticker, "horizon": h, "start": px.index[i].date().isoformat(),
                         "end": px.index[j].date().isoformat(), "ret": round(ret, 5), "spy": round(spy, 5),
                         "sector_ew": round(bench, 5), "sector_etf": round(etf, 5), "excess_spy": round(ret - spy, 5),
                         "resid": round(ret - bench, 5), "resid_etf": round(ret - etf, 5), "beat": int(ret > bench),
                         "benchmark": "equal-weighted sector" if ews is not None else "sector ETF (fallback)"})
    append_csv(state_path("grades.csv"), rows)
    # catalysts: did the stock beat its sector from the close before the event to 2 trading days after?
    crow, done = [], _catalyst_done()
    cats = _read("catalyst_ledger.csv", dtype=str)
    for c in cats.itertuples() if len(cats) else []:
        if (c.ticker, c.event_date, c.event) in done:
            continue
        k = px.index.searchsorted(pd.Timestamp(c.event_date))
        i, j = k - 1, k + 2
        if j >= len(px.index) or i < 0:
            continue
        ret, sec = _ret(px, c.ticker, i, j), _ret(px, c.sector_etf, i, j)
        if ret is None:
            continue
        resid = ret - (sec if sec is not None else (_ret(px, "SPY", i, j) or 0.0))
        crow.append({"ticker": c.ticker, "event_date": c.event_date, "event": c.event, "made_on": c.made_on,
                     "impact": c.impact, "resid": round(resid, 5), "hit": (resid > 0) == (c.impact == "positive")})
    append_csv(state_path("catalyst_grades.csv"), crow)
    grade_macro(px)
    grade_labels(px, sector_of)
    return len(rows)


def grade_labels(px, sector_of=None):
    """Was a YES/NO headline label right? Stock vs its sector ETF from the close before the headline
    date to 2 trading days after. UNKNOWN labels aren't graded."""
    lab = _read("label_ledger.csv", dtype={"date": str})
    if lab.empty or "SPY" not in px:
        return 0
    lab = lab[lab.label.isin(["YES", "NO"])]
    done = _read("label_grades.csv", dtype={"date": str})
    seen = set(zip(done.date, done.ticker)) if len(done) else set()
    moves = {}
    for r in lab[["date", "ticker"]].drop_duplicates().itertuples():
        if (r.date, r.ticker) in seen:
            continue
        k = px.index.searchsorted(pd.Timestamp(r.date))
        i, j = k - 1, k + 2
        if i < 0 or j >= len(px.index):
            continue
        ret = _ret(px, r.ticker, i, j)
        etf = config.SECTORS.get((sector_of or {}).get(r.ticker), "SPY")
        b = _ret(px, etf, i, j)
        b = _ret(px, "SPY", i, j) if b is None else b
        if ret is not None and b is not None:
            moves[(r.date, r.ticker)] = ret - b
    rows = [{"date": d, "ticker": t, "move": round(m, 5)} for (d, t), m in moves.items()]
    append_csv(state_path("label_grades.csv"), rows)
    return len(rows)


def evaluate_labels():
    """Hit rate of each labeler on graded YES/NO calls, and on the headlines where the labelers disagreed."""
    lab = _read("label_ledger.csv", dtype={"date": str})
    g = _read("label_grades.csv", dtype={"date": str})
    if lab.empty or g.empty:
        return {}
    m = lab[lab.label.isin(["YES", "NO"])].merge(g, on=["date", "ticker"])
    if m.empty:
        return {}
    m["hit"] = ((m.label == "YES") & (m.move > 0)) | ((m.label == "NO") & (m.move < 0))
    out = {}
    for model, x in m.groupby("model"):
        out[model] = {"calls": int(len(x)), "hit_rate_%": round(float(x.hit.mean() * 100), 1),
                      "live": bool(x.live.astype(str).eq("True").any())}
    return out


def grade_macro(px):
    m = _read("macro_ledger.csv", dtype={"date": str})
    if m.empty or "SPY" not in px:
        return 0
    g = _read("macro_grades.csv", dtype={"date": str})
    done = set(zip(g.date, g.sector, g.horizon)) if len(g) else set()
    rows = []
    for r in m.itertuples():
        i = px.index.searchsorted(pd.Timestamp(r.date) + pd.Timedelta(days=1))
        for h, n in MACRO_HORIZONS.items():
            if (r.date, r.sector, h) in done or i + n >= len(px.index):
                continue
            a, spy = _ret(px, r.etf, i, i + n), _ret(px, "SPY", i, i + n)
            if a is None or spy is None:
                continue
            rows.append({"date": r.date, "sector": r.sector, "horizon": h, "excess": round(a - spy, 5), "beat": int(a > spy)})
    append_csv(state_path("macro_grades.csv"), rows)
    return len(rows)


# ==================================================================== statistics
def _spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _ic_series(df, col, target="resid", min_names=MIN_NAMES_PER_DATE):
    out = {}
    for d, g in df.dropna(subset=[col, target]).groupby("date"):
        if len(g) >= min_names:
            ic = _spearman(g[col], g[target])
            if ic is not None:
                out[d] = ic
    return pd.Series(out, dtype=float)


def _overlap(horizon, spacing=REBUILD_SPACING, table=HORIZONS):
    return max(1, math.ceil(table[horizon] / spacing))


def _summ(s, horizon, spacing=REBUILD_SPACING, table=HORIZONS):
    """Mean of a per-date series with a t-stat corrected for overlapping horizons."""
    n = len(s)
    if n == 0:
        return {"dates": 0, "mean_ic": None, "t": None}
    n_eff = max(1.0, n / _overlap(horizon, spacing, table))
    sd = float(s.std(ddof=1)) if n > 1 else float("nan")
    t = float(s.mean() / (sd / math.sqrt(n_eff))) if n > 1 and sd > 0 else None
    return {"dates": n, "mean_ic": round(float(s.mean()), 3), "t": round(t, 2) if t is not None else None,
            "hit_%": round(float((s > 0).mean() * 100)), "effective_n": round(n_eff, 1)}


def _paired(df, a, b, horizon, spacing=REBUILD_SPACING, table=HORIZONS):
    """Brier(a) - Brier(b) per forecast, averaged per date, then over dates (positive = b is better).
    Returns improvement, t (overlap-corrected), n forecasts, and the 95% upper bound."""
    d = df.dropna(subset=[a, b, "beat"])
    if d.empty:
        return {"n": 0, "improvement": None, "t": None, "upper95": None}
    diff = (d[a] - d.beat) ** 2 - (d[b] - d.beat) ** 2
    per = diff.groupby(d.date).mean()
    n_eff = max(1.0, len(per) / _overlap(horizon, spacing, table))
    mean = float(per.mean())
    sd = float(per.std(ddof=1)) if len(per) > 1 else float("nan")
    se = sd / math.sqrt(n_eff) if len(per) > 1 and sd > 0 else None
    return {"n": int(len(d)), "dates": int(len(per)), "improvement": round(mean, 5),
            "t": round(mean / se, 2) if se else None, "upper95": round(mean + 1.96 * se, 5) if se else None,
            "lower95": round(mean - 1.96 * se, 5) if se else None}


def brier(df, col):
    d = df.dropna(subset=[col, "beat"])
    return round(float(((d[col] - d.beat) ** 2).mean()), 5) if len(d) else None


BUCKETS = [(0, .40), (.40, .45), (.45, .50), (.50, .55), (.55, .60), (.60, 1.01)]


def calibration(df, col):
    out = []
    d = df.dropna(subset=[col, "beat"])
    for lo, hi in BUCKETS:
        g = d[(d[col] >= lo) & (d[col] < hi)]
        if len(g):
            out.append({"bucket": f"{lo * 100:.0f}-{min(hi, 1) * 100:.0f}%", "avg_forecast_%": round(float(g[col].mean() * 100), 1),
                        "actual_%": round(float(g.beat.mean() * 100), 1), "n": int(len(g))})
    return out


# ==================================================================== evaluation
def evaluate(today=None):
    led = _ledger()
    grades = _read("grades.csv", dtype={"date": str})
    out = {"horizons": list(HORIZONS), "judges": {}, "brier": {}, "combos": {}, "selection": {}, "calibration": {},
           "warnings": replay_warnings(today)}
    if led.empty or grades.empty:
        out["status"] = "no graded decisions yet"
        out["macro"] = evaluate_macro(today)
        return out
    if "beat" not in grades:
        grades["beat"] = (grades.resid > 0).astype(int)
    wide = led.pivot_table(index=["date", "ticker"], columns="judge", values="p", aggfunc="first")
    judges = [c for c in wide.columns if c not in PSEUDO]
    live_ids = set(led[(led.live.astype(str) == "True") & ~led.judge.isin(PSEUDO)].judge)
    table = read_json(state_path("base_rates.json")) or {}
    flat = table.get("overall", 0.5)
    for h in HORIZONS:
        g = grades[grades.horizon == h].set_index(["date", "ticker"])[["resid", "beat"]]
        df = wide.join(g, how="inner").reset_index()
        if df.empty:
            continue
        df["flat"] = flat
        cols = [c for c in ["panel", "panel_sharp", "base_rate"] + judges if c in df]
        out["judges"][h] = {j: _summ(_ic_series(df, j), h) for j in cols}
        out["brier"][h] = {"scores": {j: brier(df, j) for j in cols + ["flat"]},
                           "panel_vs_base": _paired(df, "base_rate", "panel", h) if "panel" in df and "base_rate" in df else None,
                           "panel_vs_flat": _paired(df, "flat", "panel", h) if "panel" in df else None,
                           "base_vs_flat": _paired(df, "flat", "base_rate", h) if "base_rate" in df else None,
                           "sharp_vs_panel": _paired(df, "panel", "panel_sharp", h) if "panel_sharp" in df and "panel" in df else None}
        combos = {}
        live_j = [j for j in judges if j in live_ids]
        for k in range(2, len(judges) + 1):
            for c in itertools.combinations(judges, k):
                sub = df.dropna(subset=list(c)).copy()
                sub["combo"] = sub[list(c)].mean(axis=1)
                s = _summ(_ic_series(sub, "combo"), h)
                if s["dates"]:
                    combos["+".join(c)] = s
        best = sorted(combos.items(), key=lambda kv: -(kv[1]["mean_ic"] or -9))[:8]
        out["combos"][h] = {"best": dict(best), "live_panel": combos.get("+".join(live_j)), "tested": len(combos)}
        if "panel" in df:
            out["calibration"][h] = calibration(df, "panel")
        if h == "4w":
            out["pruning"] = pruning(df, h)
    out["selection"] = _selection(grades)
    out["sells"] = _sells(grades)
    out["critic"] = _critic(grades)
    cg = _read("catalyst_grades.csv", dtype=str)
    if len(cg):
        out["catalysts"] = {"graded": len(cg), "hit_rate_%": round(float((cg.hit == "True").mean() * 100), 1)}
    pe = _read("process_errors.csv", dtype={"date": str})
    if len(pe):
        last = pe[pe.date == pe.date.max()]
        out["process_errors"] = {"date": pe.date.max(), **{r.category: int(r["count"]) for _, r in last.iterrows()}}
    out["first_decision"] = led[~led.replay.astype(str).eq("True")].date.min() if "replay" in led else led.date.min()
    out["rebuilds_judged"] = int(led.date.nunique())
    out["macro"] = evaluate_macro(today)
    out["labelers"] = evaluate_labels()
    out["rule"] = decision_rule(out, today)
    return out


def _selection(grades):
    vh = _read("verdict_history.csv", dtype={"date": str, "team_date": str})
    out = {}
    if vh.empty or "team_date" not in vh:
        return out
    sel = vh.dropna(subset=["team_date"]).rename(columns={"team_date": "tdate"})
    for h in HORIZONS:
        g = grades[grades.horizon == h]
        m = sel.merge(g, left_on=["tdate", "ticker"], right_on=["date", "ticker"])
        if len(m):
            ins = m[m.in_portfolio.astype(str) == "True"].resid
            outs = m[m.in_portfolio.astype(str) != "True"].resid
            out[h] = {"selected_avg_resid_%": round(float(ins.mean() * 100), 2) if len(ins) else None,
                      "rejected_avg_resid_%": round(float(outs.mean() * 100), 2) if len(outs) else None,
                      "n_selected": len(ins), "n_rejected": len(outs)}
    return out


def _sells(grades):
    """Sold holdings vs kept holdings over the 4 weeks after each rebuild. If the sold ones keep
    doing better, the selling is hurting."""
    s = _read("sell_ledger.csv", dtype={"date": str})
    if s.empty:
        return {}
    g = grades[grades.horizon == "4w"]
    m = s.merge(g, on=["date", "ticker"])
    if m.empty:
        return {}
    sold, kept = m[m.action == "sold"].resid, m[m.action == "kept"].resid
    return {"sold_avg_resid_%": round(float(sold.mean() * 100), 2) if len(sold) else None,
            "kept_avg_resid_%": round(float(kept.mean() * 100), 2) if len(kept) else None,
            "n_sold": len(sold), "n_kept": len(kept)}


def _critic(grades):
    c = _read("critic_ledger.csv", dtype={"date": str})
    if c.empty:
        return {}
    g = grades[grades.horizon == "4w"]
    m = c[c.action == "BUY"].merge(g, on=["date", "ticker"])
    if m.empty:
        return {}
    ok, flagged = m[m.critic == "PASS"].resid, m[m.critic != "PASS"].resid
    return {"approved_avg_resid_%": round(float(ok.mean() * 100), 2) if len(ok) else None,
            "flagged_avg_resid_%": round(float(flagged.mean() * 100), 2) if len(flagged) else None,
            "n_approved": len(ok), "n_flagged": len(flagged)}


def pruning(df, h):
    """Twin tests: a replayed copy of a live judge with one dossier section removed. Benefit of the
    section = Brier(twin without it) - Brier(live judge with it); removable when, over enough
    paired forecasts, even the upper 95% bound of that benefit is below the pre-registered minimum."""
    R = config.EVAL_RULE
    out = {}
    for col in df.columns:
        if not str(col).startswith("twin_"):
            continue
        base_judge = str(col).split("__", 1)[1] if "__" in str(col) else "sonnet"
        if base_judge not in df:
            continue
        s = _paired(df, col, base_judge, h)      # positive = the live judge (with the section) is better
        verdict = "collecting"
        if s["n"] >= R["prune_min_pairs"] and s["upper95"] is not None:
            verdict = ("REMOVABLE (needs your approval)" if s["upper95"] < R["prune_max_benefit"]
                       else "keep: it helps" if (s["lower95"] or 0) > 0 else "keep: not yet clear")
        out[str(col)] = dict(s, verdict=verdict)
    return out


def evaluate_macro(today=None):
    m = _read("macro_ledger.csv", dtype={"date": str})
    g = _read("macro_grades.csv", dtype={"date": str})
    if m.empty or g.empty:
        return {"status": "no graded macro runs yet"}
    out = {}
    for h in MACRO_HORIZONS:
        d = m.merge(g[g.horizon == h], on=["date", "sector"])
        if d.empty:
            continue
        spacing = 20                     # monthly runs
        ic = lambda col: _summ(_ic_series(d, col, "excess", 5), h, spacing, MACRO_HORIZONS)
        out[h] = {"macro_ic": ic("p"), "momentum_rule_ic": ic("momentum_p"), "base_ic": ic("base_p"),
                  "brier": {c: brier(d, c) for c in ("p", "base_p", "momentum_p")},
                  "macro_vs_base": _paired(d, "base_p", "p", h, spacing, MACRO_HORIZONS),
                  "macro_vs_momentum": _paired(d, "momentum_p", "p", h, spacing, MACRO_HORIZONS)}
    out["first_run"] = m.date.min()
    out["rule"] = macro_rule(out, today)
    return out


def macro_rule(mev, today=None):
    """Pre-registered: after 12 months, if the macro view beats neither the momentum rule (sector IC)
    nor the no-macro portfolio, sector ranges revert to neutral and the paid monthly run stops."""
    today = today or now_et().date()
    first = mev.get("first_run")
    if not first:
        return {"verdict": "collecting"}
    months = (today - date.fromisoformat(first)).days / 30.44
    need = config.EVAL_RULE["macro_review_months"]
    if months < need:
        return {"verdict": "collecting", "why": f"{months:.1f} of {need} months"}
    h = (mev.get("4w") or {})
    beats_mom = (h.get("macro_ic") or {}).get("mean_ic") is not None and \
        (h["macro_ic"]["mean_ic"] or 0) > ((h.get("momentum_rule_ic") or {}).get("mean_ic") or 0)
    perf = (read_json(state_path("performance.json"), {}) or {}).get("metrics", {})
    ai = (perf.get("AI as recommended") or {}).get("since_inception_%")
    nm = (perf.get("No-macro (top-rated, no PM)") or {}).get("since_inception_%")
    beats_nomacro = ai is not None and nm is not None and ai > nm
    if beats_mom or beats_nomacro:
        return {"verdict": "keep", "why": f"beats {'the momentum rule' if beats_mom else ''}"
                                         f"{' and ' if beats_mom and beats_nomacro else ''}{'the no-macro portfolio' if beats_nomacro else ''}"}
    return {"verdict": "REVERT TO NEUTRAL (needs your approval)",
            "why": "after 12 months the macro view beats neither the momentum rule nor the no-macro portfolio; "
                   "set MACRO_MODE=neutral in GitHub variables to stop the paid run"}


def replay_warnings(today=None):
    """Replays must happen before a model is retired. Retirement dates are entered in config.REPLAY."""
    today = today or now_et().date()
    out = []
    for name, r in config.REPLAY.items():
        if r.get("retires"):
            days = (date.fromisoformat(r["retires"]) - today).days
            if days <= 90:
                out.append(f"{r['model']} retires {r['retires']} ({days} days): run `python -m pipeline.replay {name}` before then")
    return out


# ==================================================================== pre-registered decision rule
def decision_rule(ev, today=None):
    """Written down BEFORE seeing results (EVALUATION.md). Primary test: live panel 4-week IC at the
    scheduled looks. Second test: the panel must beat the free base rate on Brier score, otherwise any
    edge belongs to the statistics, not the AI."""
    R = config.EVAL_RULE
    today = today or now_et().date()
    first = ev.get("first_decision")
    if not first:
        return {"verdict": "waiting", "why": "no decisions recorded yet"}
    months = (today - date.fromisoformat(first)).days / 30.44
    looks = [m for m in R["looks_months"] if months >= m]
    stat = ((ev.get("judges") or {}).get(R["horizon"]) or {}).get("panel") or {}
    pvb = ((ev.get("brier") or {}).get(R["horizon"]) or {}).get("panel_vs_base") or {}
    brier_ok = pvb.get("n", 0) >= R["brier_min_forecasts"] and (pvb.get("t") or 0) >= 2 and (pvb.get("improvement") or 0) > 0
    res = {"look": len(looks), "months": round(months, 1), "stat": stat, "panel_vs_base": pvb,
           "promotion_candidates": _promotions(ev)}
    if not looks:
        res.update(verdict="collecting", why=f"{months:.1f} months of decisions; first scheduled look at "
                                             f"{R['looks_months'][0]} months")
        return res
    k = len(looks)
    bound = R["t_boundaries"][k - 1]
    t, ic, n = stat.get("t"), stat.get("mean_ic"), stat.get("dates", 0)
    res["boundary_t"] = bound
    if n < R["min_dates"] or t is None:
        res.update(verdict="collecting", why=f"only {n} graded rebuilds at the {R['horizon']} horizon (need {R['min_dates']})")
    elif t >= bound and brier_ok:
        res.update(verdict="EDGE CONFIRMED",
                   why=f"live panel {R['horizon']} IC {ic:+.3f}, t = {t:.2f} >= {bound} at look {k}, and the panel beats the "
                       f"base rate (Brier improvement t = {pvb.get('t')}). Scaling up can be considered, in the steps in EVALUATION.md.")
    elif t >= bound:
        res.update(verdict="STATISTICS ONLY",
                   why=f"ranking skill is real (t = {t:.2f}) but the judges don't yet beat the free base rate on their own "
                       f"(Brier test: n {pvb.get('n', 0)}, t {pvb.get('t')}). Don't pay for scale on this evidence.")
    elif k >= R["futility_from_look"] and ic is not None and ic <= R["futility_ic"]:
        res.update(verdict="NO EDGE (futility)",
                   why=f"live panel {R['horizon']} IC {ic:+.3f} <= {R['futility_ic']} at look {k}. Do not scale; redesign or stop.")
    elif k == len(R["looks_months"]):
        res.update(verdict="NOT PROVEN", why=f"final look: t = {t:.2f} < {bound}. Do not scale on this evidence.")
    else:
        res.update(verdict="continue", why=f"t = {t:.2f} (needs {bound} at this look); keep running unchanged.")
    return res


def _promotions(ev):
    R = config.EVAL_RULE
    js = ((ev.get("judges") or {}).get(R["promote_horizon"]) or {})
    base = (js.get("panel") or {}).get("mean_ic")
    out = []
    for jid, s in js.items():
        if jid in PSEUDO or str(jid).startswith("twin_") or s.get("mean_ic") is None or base is None:
            continue
        if s["dates"] >= R["promote_min_dates"] and (s.get("t") or 0) >= R["promote_t"] and s["mean_ic"] > base + R["promote_margin"]:
            out.append(f"{jid}: IC {s['mean_ic']:+.3f} vs panel {base:+.3f} over {s['dates']} rebuilds (t {s['t']})")
    return out


# ==================================================================== rendering
def _fmt(s):
    if not s or s.get("mean_ic") is None:
        return "n/a"
    return f"{s['mean_ic']:+.3f} (t {s['t'] if s.get('t') is not None else 'n/a'}, {s['dates']} dates)"


def _pv(p):
    if not p or p.get("improvement") is None:
        return f"n/a ({(p or {}).get('n', 0)} forecasts)"
    return f"{p['improvement']:+.4f} (t {p.get('t')}, {p['n']} forecasts)"


def render_md(ev):
    L = ["## Judge report card"]
    for w in ev.get("warnings") or []:
        L.append(f"**Replay reminder:** {w}")
    if ev.get("status"):
        L.append(ev["status"])
        L += _render_macro(ev.get("macro") or {})
        return "\n".join(L)
    rule = ev.get("rule", {})
    L += [f"{ev.get('rebuilds_judged')} rebuilds judged since {ev.get('first_decision')}.",
          f"**Decision rule:** {rule.get('verdict')} — {rule.get('why')}"]
    for p in rule.get("promotion_candidates") or []:
        L.append(f"- Shadow judge worth promoting (needs your approval): {p}")
    L += ["", "IC = rank correlation between a forecast and the stock's return beyond its equal-weighted sector. "
              "0 = no skill; +0.05 sustained is good; t >= 2 means unlikely to be luck. base_rate = the free statistics alone.", "",
          "| Judge | " + " | ".join(ev["horizons"]) + " |", "|---" * (len(ev["horizons"]) + 1) + "|"]
    names = sorted({j for h in ev["judges"].values() for j in h}, key=lambda x: (x not in PSEUDO, x))
    for j in names:
        L.append(f"| {j} | " + " | ".join(_fmt((ev["judges"].get(h) or {}).get(j)) for h in ev["horizons"]) + " |")
    b4 = (ev.get("brier") or {}).get("4w")
    if b4:
        L += ["", "**Brier score, 4 weeks** (lower is better): " + ", ".join(f"{k} {v}" for k, v in b4["scores"].items() if v is not None),
              f"- Panel vs base rate (the key test: do the paid judges add anything?): {_pv(b4.get('panel_vs_base'))}",
              f"- Base rate vs a flat guess: {_pv(b4.get('base_vs_flat'))}"]
    if (ev.get("calibration") or {}).get("4w"):
        L += ["", "**Calibration, 4 weeks** (forecast vs what happened): " + "; ".join(
            f"{c['bucket']}: said {c['avg_forecast_%']}%, happened {c['actual_%']}% (n {c['n']})" for c in ev["calibration"]["4w"])]
    for h, c in ev.get("combos", {}).items():
        if c.get("tested"):
            L += ["", f"**Best judge combinations, {h}** ({c['tested']} tested, so the best will look lucky). "
                      f"Live panel: {_fmt(c.get('live_panel'))}"]
            L += [f"- {k}: {_fmt(v)}" for k, v in list(c["best"].items())[:4]]
    if ev.get("selection"):
        L += ["", "**Bought vs passed over** (avg return beyond sector):"]
        L += [f"- {h}: bought {s['selected_avg_resid_%']}% (n {s['n_selected']}) vs passed {s['rejected_avg_resid_%']}% "
              f"(n {s['n_rejected']})" for h, s in ev["selection"].items()]
    if ev.get("sells"):
        s = ev["sells"]
        L.append(f"**Sold vs kept, 4 weeks after:** sold {s['sold_avg_resid_%']}% (n {s['n_sold']}) vs kept "
                 f"{s['kept_avg_resid_%']}% (n {s['n_kept']})")
    if ev.get("critic"):
        c = ev["critic"]
        L.append(f"**Critic:** approved buys {c['approved_avg_resid_%']}% (n {c['n_approved']}) vs flagged/held "
                 f"{c['flagged_avg_resid_%']}% (n {c['n_flagged']}), 4 weeks")
    for k, v in (ev.get("pruning") or {}).items():
        L.append(f"**Pruning test {k}:** {v['verdict']} — benefit {_pv(v)}")
    if ev.get("catalysts"):
        L.append(f"**Catalysts:** {ev['catalysts']['hit_rate_%']}% moved the expected way ({ev['catalysts']['graded']} graded)")
    if ev.get("labelers"):
        L.append("**Headline labelers** (right direction over the next 2 trading days vs sector): " + "; ".join(
            f"{k}{' (live)' if v['live'] else ''} {v['hit_rate_%']}% of {v['calls']}" for k, v in ev["labelers"].items()))
    if ev.get("process_errors"):
        pe = {k: v for k, v in ev["process_errors"].items() if k != "date"}
        L.append(f"**Process errors, last run ({ev['process_errors']['date']}):** " + ", ".join(f"{k} {v}" for k, v in pe.items()))
    L += _render_macro(ev.get("macro") or {})
    return "\n".join(L)


def _render_macro(m):
    if not m or m.get("status"):
        return ["", f"**Macro agent:** {(m or {}).get('status', 'no data')}"]
    L = ["", "**Macro agent vs the momentum rule** (sector ranking skill, IC):"]
    for h in MACRO_HORIZONS:
        x = m.get(h)
        if x:
            L.append(f"- {h}: macro {_fmt(x['macro_ic'])}; momentum rule {_fmt(x['momentum_rule_ic'])}; "
                     f"macro vs base rate (Brier) {_pv(x['macro_vs_base'])}")
    r = m.get("rule") or {}
    L.append(f"- 12-month macro rule: {r.get('verdict')} {('— ' + r['why']) if r.get('why') else ''}")
    return L


def render_html(ev):
    """The report card as simple email HTML (tables stay tables)."""
    import html
    out, in_tbl = [], False
    for line in render_md(ev).splitlines():
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            if not in_tbl:
                out.append("<table border='1' cellpadding='4' style='border-collapse:collapse'>")
                in_tbl = True
            out.append("<tr>" + "".join(f"<td>{html.escape(c.strip())}</td>" for c in line.strip("|").split("|")) + "</tr>")
            continue
        if in_tbl:
            out.append("</table>")
            in_tbl = False
        text = html.escape(line.lstrip("#- ").replace("**", ""))
        if line.startswith("## "):
            out.append(f"<h3>{text}</h3>")
        elif line.strip():
            out.append(f"<p>{text}</p>")
    if in_tbl:
        out.append("</table>")
    return "".join(out)


def save(ev):
    write_json(state_path("evaluation.json"), ev)


