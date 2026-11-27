"""
LOOK-BACK  —  run:  python -m pipeline.lookback            (numbers + a written read by a model)
                    python -m pipeline.lookback --no-llm   (numbers only, free)

Read-only. Never changes a pick, a weight or a setting. For every rebuild it takes the judged shortlist (about 80
names), measures each name from the trade-date close to the latest close, and asks what separated the names that
did well from the ones that did not: which of our inputs (judge probabilities, the base rate, the composite
score, the five signal families, the sector) lined up with what actually happened, and which picked and
passed-over names were the biggest hits and misses, with the judges' stated driver beside each.

Output: reports/lookback/lookback-<date>.md and reports/lookback/latest.md. The file is a record to read later,
not an instruction: with 9 to 14 trading days behind it, patterns are leads to test, never findings.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .util import now_et, state_path

OUT = "reports/lookback"
SIGNALS = ["m", "e", "q", "v", "l"]            # momentum, estimates, quality, value, low-vol style families
JUDGE_COLS = ["panel_p", "base_p", "edge_pts", "composite", "news_score"]


def _load(name, default):
    p = state_path(name)
    return json.loads(Path(p).read_text()) if Path(p).exists() else default


def rank_ic(x, y):
    """Spearman rank correlation of two aligned series (nan when fewer than 8 pairs or no spread)."""
    d = pd.concat([pd.Series(x, dtype=float), pd.Series(y, dtype=float)], axis=1).dropna()
    if len(d) < 8 or d.iloc[:, 0].nunique() < 2 or d.iloc[:, 1].nunique() < 2:
        return float("nan")
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank()))


def ic_band(n):
    """Rough 95% band for a rank correlation of pure noise with n names."""
    return 1.96 / np.sqrt(max(n - 1, 1))


def build_frame(rebuild, ledger, features, verdicts, close):
    """One row per shortlisted name: what we thought at the rebuild, and what the stock did since."""
    td = pd.Timestamp(rebuild["trade_date"])
    names = list(rebuild.get("sectors", {}))
    px = close.reindex(columns=names).dropna(how="all", axis=1)
    px = px.loc[px.index >= td]
    if len(px) < 2:
        return None
    ret = (px.iloc[-1] / px.iloc[0] - 1).dropna() * 100
    df = pd.DataFrame({"ret": ret})
    df["sector"] = [rebuild["sectors"].get(t) for t in df.index]
    df["picked"] = [t in rebuild.get("target", {}) for t in df.index]
    df["weight"] = [rebuild.get("target", {}).get(t, 0.0) for t in df.index]
    day = ledger[ledger["date"] == rebuild.get("team_date", rebuild["date"])]
    panel = day[day["judge"] == "panel"].drop_duplicates("ticker").set_index("ticker")
    for c in JUDGE_COLS:
        df[c] = panel[c] if c in panel else np.nan
    df["winner"] = panel["winner"] if "winner" in panel else None
    df["driver"] = panel["primary_driver"] if "primary_driver" in panel else None
    df["factor"] = panel["dominant_factor"] if "dominant_factor" in panel else None
    live = day[(day["judge"] != "panel") & day["p"].notna()]      # live and shadow judges (shadows: p_<id> too)
    for j, g in live.groupby("judge"):
        if j in ("base_rate", "panel_sharp"):
            continue
        df[f"p_{j}"] = g.drop_duplicates("ticker").set_index("ticker")["p"]
    feats = (features or {}).get("stocks", {})
    for s in SIGNALS:
        df[s] = [feats.get(t, {}).get(s) for t in df.index]
    df["thesis"] = [(verdicts.get(t, {}).get("verdict") or {}).get("thesis") for t in df.index]
    df["key_risk"] = [(verdicts.get(t, {}).get("verdict") or {}).get("key_risk") for t in df.index]
    df.index.name = "ticker"
    return df.assign(trade_date=rebuild["trade_date"], last=str(px.index[-1].date()), days=len(px) - 1)


def scoreboard(frames):
    """Rank IC of every input against the return since the rebuild, per rebuild and averaged."""
    cols = JUDGE_COLS + SIGNALS
    judges = sorted({c for f in frames for c in f.columns if c.startswith("p_")})
    rows = []
    for c in cols + judges:
        per = []
        for f in frames:
            per.append(rank_ic(f[c], f["ret"]) if c in f else float("nan"))
        n = [int(f[c].notna().sum()) if c in f else 0 for f in frames]
        ok = [v for v in per if v == v]
        rows.append({"input": c, "per_rebuild": per, "n": n, "mean": float(np.mean(ok)) if ok else float("nan"),
                     "band": ic_band(int(np.mean([x for x in n if x]) if any(n) else 0))})
    return rows


def summary_row(f):
    p, s, o = f[f.picked], f, f[~f.picked]
    return {"trade_date": f.trade_date.iloc[0], "last": f["last"].iloc[0], "days": int(f.days.iloc[0]),
            "n_picks": int(len(p)), "picks": float(p.ret.mean()) if len(p) else float("nan"),
            "shortlist": float(s.ret.mean()), "passed_over": float(o.ret.mean()) if len(o) else float("nan"),
            "pick_hit": float((p.ret > s.ret.median()).mean()) if len(p) else float("nan")}


def movers(f, k=6):
    cols = ["ret", "picked", "weight", "sector", "panel_p", "edge_pts", "winner", "driver"]
    cols = [c for c in cols if c in f]
    return f.sort_values("ret", ascending=False)[cols].head(k), f.sort_values("ret")[cols].head(k)


def sector_view(f):
    g = f.groupby("sector").agg(n=("ret", "size"), avg=("ret", "mean"), picks=("picked", "sum"))
    return g.sort_values("avg", ascending=False)


# ==================================================================== text
def _f(v, d=1, pct=False):
    return "n/a" if v is None or v != v else f"{v:+.{d}f}{'%' if pct else ''}"


def _table(df, floatfmt=None):
    cols = list(df.columns)
    out = ["| " + " | ".join(["name"] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for idx, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append("" if v is None else f"{v:.2f}" if isinstance(v, (float, np.floating)) and v == v else
                         "" if isinstance(v, float) else "yes" if v is True else "no" if v is False else str(v))
        out.append("| " + " | ".join([str(idx)] + cells) + " |")
    return "\n".join(out)


def evidence_text(frames, summaries, board):
    """The compact fact sheet the model reads (and that is printed in the file)."""
    L = []
    for f, s in zip(frames, summaries):
        L.append(f"Rebuild traded {s['trade_date']}, measured to {s['last']} ({s['days']} trading days). "
                 f"Picks ({s['n_picks']}) {_f(s['picks'], 2, True)}, shortlist {_f(s['shortlist'], 2, True)}, "
                 f"passed over {_f(s['passed_over'], 2, True)}, picks beating the shortlist median: "
                 f"{s['pick_hit'] * 100:.0f}%.")
        top, bot = movers(f)
        for label, m in (("Best", top), ("Worst", bot)):
            for t, r in m.iterrows():
                th = f.loc[t, "thesis"] if "thesis" in f and isinstance(f.loc[t, "thesis"], str) else ""
                L.append(f"  {label} {t} {r['ret']:+.1f}% {'PICKED' if r['picked'] else 'passed over'} "
                         f"sector={r['sector']} panel_p={_f(r.get('panel_p'), 3)} edge={_f(r.get('edge_pts'), 1)}pts "
                         f"judges said {r.get('winner')} on '{r.get('driver')}'" + (f" | thesis: {th[:220]}" if th else ""))
    L.append("Rank correlation with the return since the rebuild (0 = no relationship; about +/-"
             f"{board[0]['band']:.2f} is what pure luck gives with ~80 names):")
    for b in board:
        L.append(f"  {b['input']}: mean {_f(b['mean'], 2)}  per rebuild " + ", ".join(_f(v, 2) for v in b["per_rebuild"]))
    return "\n".join(L)


SYSTEM = """You are the look-back analyst for a small stock-picking pipeline. You are shown, for each rebuild, how the
judged shortlist performed since the trade date, which names were picked or passed over, what the judges said, and
how well each input ranked the names. Write a short, plain, honest read for the person who runs it.
Rules: use only numbers in the evidence; the samples are 9 to 14 trading days, so call every pattern a hypothesis,
never a finding or a cause; say plainly when the evidence is within what luck gives; do not recommend changing
live settings, only what to test or log next. Structure, in markdown, with these headings and nothing else:
## What separated winners from losers
## Where the judges' reasoning held up or missed
## Hypotheses to test (each with how we would test it)
## What not to conclude yet
Keep it under 450 words."""


def ask_model(evidence, session=None):
    from . import llm
    session = session or llm.Session("lookback", budget=0.6)
    r = session.ask("lookback", SYSTEM, evidence, model=config.SONNET_55, max_tokens=5000)
    return r.text.strip(), float(getattr(session, "spent", 0.0))


def render(frames, summaries, board, read, today, cost=None):
    L = [f"# Look-back: what worked on the shortlist and why\n",
         f"Built {today}. Read-only record; it changes no pick, weight or setting. Windows are short, so treat every "
         "pattern as a lead to test, not a finding.\n",
         "## How each rebuild did\n",
         "| Traded | Measured to | Days | Picks | Picks % | Shortlist % | Passed over % | Picks above shortlist median |",
         "|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        L.append(f"| {s['trade_date']} | {s['last']} | {s['days']} | {s['n_picks']} | {_f(s['picks'], 2)} | "
                 f"{_f(s['shortlist'], 2)} | {_f(s['passed_over'], 2)} | {s['pick_hit'] * 100:.0f}% |")
    L += ["", "## Which inputs lined up with what happened\n",
          f"Rank correlation with the return since each rebuild. About ±{board[0]['band']:.2f} is noise at this sample "
          "size, so values inside that band say nothing yet. `panel_p` is the judges' averaged probability, `base_p` "
          "the base rate before the judges, `edge_pts` the gap between them (the judges' added view), `composite` the "
          "screen score, and `m e q v l` the five signal families.\n",
          "| Input | " + " | ".join(s["trade_date"] for s in summaries) + " | Mean |", "|---|" + "---|" * (len(summaries) + 1)]
    for b in board:
        L.append(f"| {b['input']} | " + " | ".join(_f(v, 2) for v in b["per_rebuild"]) + f" | {_f(b['mean'], 2)} |")
    for f, s in zip(frames, summaries):
        top, bot = movers(f)
        L += ["", f"## Rebuild traded {s['trade_date']}: biggest hits and misses\n", "Best performers on the shortlist:\n",
              _table(top.round(2)), "", "Worst performers on the shortlist:\n", _table(bot.round(2)), "",
              "By sector:\n", _table(sector_view(f).round(2))]
    L += ["", "## Written read\n", read or "_Skipped (numbers only)._"]
    if cost:
        L.append(f"\n_Model cost for this read: ${cost:.3f}._")
    return "\n".join(L) + "\n"


def build(loader, ledger=None, rebuilds=None, features=None, verdicts=None, session=None, use_llm=True, today=None):
    import pandas as pd
    rebuilds = rebuilds if rebuilds is not None else _load("rebuild_history.json", [])
    if ledger is None:
        p = Path(state_path("decision_ledger.csv"))
        ledger = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["date", "ticker", "judge", "live", "p"])
    features = features if features is not None else _load("current_features.json", {})
    verdicts = verdicts if verdicts is not None else _load("team_results.json", {}).get("stocks", {})
    if not rebuilds:
        return None
    start = min(pd.Timestamp(r["trade_date"]) for r in rebuilds) - pd.Timedelta(days=3)
    tickers = sorted({t for r in rebuilds for t in r.get("sectors", {})})
    close = loader(tickers, start)
    if close is None or getattr(close, "empty", True):
        return None
    close.index = pd.to_datetime(close.index).tz_localize(None) if getattr(close.index, "tz", None) else pd.to_datetime(close.index)
    frames = [f for f in (build_frame(r, ledger, features, verdicts, close) for r in rebuilds) if f is not None]
    if not frames:
        return None
    summaries = [summary_row(f) for f in frames]
    board = scoreboard(frames)
    read, cost = None, None
    if use_llm:
        try:
            read, cost = ask_model(evidence_text(frames, summaries, board), session)
        except Exception as e:                       # the numbers still go out if the model is unavailable
            read = f"_The written read is unavailable this time ({str(e)[:120]}). The numbers above stand on their own._"
    return render(frames, summaries, board, read, today or now_et().date().isoformat(), cost)


def main(argv):
    from .report import yahoo_closes
    md = build(yahoo_closes, use_llm="--no-llm" not in argv)
    if md is None:
        print("Look-back skipped: no rebuilds, or no prices available.")
        return 0
    root = Path(state_path("x")).parent.parent / OUT
    root.mkdir(parents=True, exist_ok=True)
    stamp = now_et().date().isoformat()
    (root / f"lookback-{stamp}.md").write_text(md)
    (root / "latest.md").write_text(md)
    print(f"Wrote {root / 'latest.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
