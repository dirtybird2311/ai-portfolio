"""
COUNCIL PORTFOLIO  —  what portfolio the council dossier would have produced, built in a sandbox.

    python -m pipeline.council_plan 2026-11-01 --snapshot 485dbbd~1     (Actions > Council portfolio)

For one rebuild it runs the portfolio manager twice, once on the standard verdicts and once on "council" verdicts
(the live judges' average with the council judge standing in for the live Sonnet judge), each a single PM pass with
the code rules and sizing, no critic round. Nothing real changes: no plan, holdings, trades or ledger rows. The two
target portfolios are saved under runs/<date>/rebuild/council/ and added to the shadow books
(pipeline/shadowbooks.py), which track both from the rebuild's trade-date open against SPY.

The rebuild runs this itself after each plan (when the council judge scored the stocks). --snapshot reads the
holdings and macro files as they stood at a past commit, so a past rebuild is replayed with the book it had then.
"""
import io
import json
import math
import subprocess
import sys

import pandas as pd

from . import config, shadowbooks
from .team import label
from .util import read_json, state_path, write_json, write_text

COUNCIL_ID = config.COUNCIL_JUDGE["id"]
STANDARD_LABEL = "Standard dossier (PM once, no critic)"
COUNCIL_LABEL = "Council dossier (PM once, no critic)"


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def council_verdicts(team_res, council_p):
    """A copy of the team results whose verdicts use the council judge in place of the live Sonnet judge.
    council_p: {ticker: council judge probability}. Stocks without one keep the standard verdict."""
    out = json.loads(json.dumps(team_res))
    changed = 0
    for t, s in out["stocks"].items():
        v = s.get("verdict") or {}
        cp = council_p.get(t)
        live = v.get("live_judges") or []
        probs = {j: (v.get("judges") or {}).get(j, {}).get("probability") for j in live}
        if cp is None or "sonnet" not in probs:
            continue
        probs["sonnet"] = cp
        ok = [p for p in probs.values() if p is not None]
        if not ok:
            continue
        p = 1 / (1 + math.exp(-sum(_logit(x) for x in ok) / len(ok)))
        edge = round((p - v.get("base_p", 0.5)) * 100, 1)
        v.update(probability=round(p, 4), edge_pts=edge, conviction=label(edge), council_variant=True)
        changed += 1
    out["council_variant"] = {"replaced": "sonnet", "by": COUNCIL_ID, "stocks": changed}
    return out


def council_probs(team_res, date):
    """The council judge's probabilities: from the verdicts (live runs) or the decision ledger (replays)."""
    p = {t: ((s.get("verdict") or {}).get("judges") or {}).get(COUNCIL_ID, {}).get("probability")
         for t, s in team_res["stocks"].items()}
    p = {t: v for t, v in p.items() if v is not None}
    if p:
        return p
    led = state_path("decision_ledger.csv")
    if not led.exists():
        return {}
    d = pd.read_csv(led)
    d = d[(d["date"] == date) & (d["judge"] == COUNCIL_ID) & d["p"].notna()]
    return dict(zip(d["ticker"], d["p"].astype(float)))


def _at(commit, name, default=None):
    """A state file as it stood at a past commit (None: the current one)."""
    if not commit:
        p = state_path(name)
        if not p.exists():
            return default
        return pd.read_csv(p) if name.endswith(".csv") else read_json(p, default)
    try:
        txt = subprocess.run(["git", "show", f"{commit}:state/{name}"], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return default
    return pd.read_csv(io.StringIO(txt)) if name.endswith(".csv") else json.loads(txt)


def context(book, team_res, macro, prices, signals, drawdown, digest):
    """The PM inputs the rebuild builds from the book (same code path as pipeline.rebuild.main)."""
    from .book import positions_df
    from .pm import holding_info
    pos0 = positions_df(book, prices)
    holdings_view = [{"ticker": p["ticker"], "account": p["account"], "value": round(p["value"], 2),
                      "gain_%": round(p["gain"] / p["cost_basis"] * 100, 1), "bought": p["buy_date"],
                      "thesis": p.get("thesis"), "exit_condition": p.get("exit_condition"),
                      "conviction_then": p.get("conviction")} for _, p in pos0.iterrows()] if len(pos0) else []
    info = holding_info(holdings_view, team_res, signals or {}, team_res.get("date"))
    if (digest or {}).get("view_date") != (macro or {}).get("date"):
        digest = {}
    return holdings_view, (drawdown or {}).get("level", 0), info, digest or {}


def build_both(session, team_res, council_res, book, macro, bench, holdings_view, dd, universe, digest, info):
    from .rebuild import plan_stage
    std = plan_stage(session, team_res, book, macro, bench, holdings_view, dd, universe, digest=digest, info=info)
    cou = plan_stage(session, council_res, book, macro, bench, holdings_view, dd, universe, digest=digest, info=info)
    return std, cou


def compare_md(date, trade_date, std, cou, real_target):
    names = sorted(set(std["weights"]) | set(cou["weights"]) | set(real_target or {}),
                   key=lambda t: -max(std["weights"].get(t, 0), cou["weights"].get(t, 0)))
    rows = [f"| {t} | {(real_target or {}).get(t, 0):.1f}% | {std['weights'].get(t, 0):.1f}% | {cou['weights'].get(t, 0):.1f}% |"
            for t in names]
    only_c = sorted(set(cou["weights"]) - set(std["weights"]))
    only_s = sorted(set(std["weights"]) - set(cou["weights"]))
    return "\n".join([
        f"# Council portfolio — rebuild {date} (trade date {trade_date})\n",
        "Sandbox only: nothing here was traded. Both columns are one PM pass with the code rules and sizing and no "
        "critic round, so they can differ a little from the real plan.\n",
        f"Council only: {', '.join(only_c) or 'none'}. Standard only: {', '.join(only_s) or 'none'}.\n",
        "| Ticker | Real plan | Standard (sandbox) | Council (sandbox) |", "|---|---|---|---|", *rows,
        f"\n**Standard PM summary:** {std['pick'].get('summary', '')}\n",
        f"**Council PM summary:** {cou['pick'].get('summary', '')}\n"])


def save(folder, date, trade_date, std, cou, real_target):
    out = folder / "council"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "standard_plan.json", std)
    write_json(out / "council_plan.json", cou)
    write_text(out / "comparison.md", compare_md(date, trade_date, std, cou, real_target))
    shadowbooks.add_segment("standard", trade_date, std["weights"], label=STANDARD_LABEL, note=f"rebuild {date}")
    shadowbooks.add_segment("council", trade_date, cou["weights"], label=COUNCIL_LABEL, note=f"rebuild {date}")
    print(f"    council portfolio saved ({out / 'comparison.md'}); shadow books updated from {trade_date}")


def run(session, date, snapshot=None):
    """Replay for a past rebuild (its team results and plan are in runs/<date>/rebuild/)."""
    from .book import load_book
    from .rebuild import market_prices
    folder = config.RUNS_DIR / date / "rebuild"
    team_res = read_json(folder / "team" / "team_results.json")
    plan = read_json(folder / "plan.json") or {}
    if not team_res:
        raise SystemExit(f"no team results for {date}")
    cp = council_probs(team_res, date)
    if not cp:
        raise SystemExit(f"no council judge scores for {date}: run Actions > Replay a judge (council) first")
    council_res = council_verdicts(team_res, cp)
    if snapshot:
        book = _at(snapshot, "holdings.json")
        for p in book["positions"]:
            p.setdefault("lots", [{"date": p.get("buy_date"), "shares": p["shares"], "cost": p["cost_basis"]}])
    else:
        book = load_book()
    macro = config.with_current_ranges(_at(snapshot, "macro_view.json"))
    bench = _at(snapshot, "bench.csv").set_index("ticker")
    universe = set(team_res["stocks"]) | {p["ticker"] for p in book["positions"]}
    prices, _ = market_prices(sorted({p["ticker"] for p in book["positions"]})) if book["positions"] else ({}, None)
    holdings_view, dd, info, digest = context(book, team_res, macro, prices, _at(snapshot, "holding_signals.json", {}),
                                              _at(snapshot, "drawdown.json", {}), _at(snapshot, "macro_check.json", {}))
    print(f"Council portfolio for the {date} rebuild: {council_res['council_variant']['stocks']} verdicts use the council judge")
    std, cou = build_both(session, team_res, council_res, book, macro, bench, holdings_view, dd, universe, digest, info)
    save(folder, date, plan.get("trade_date") or date, std, cou, plan.get("target"))
    return {"standard": std["weights"], "council": cou["weights"]}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--snapshot")
    a = ap.parse_args()
    from .runner import run_stage
    run_stage("council_plan", lambda s, f: run(s, a.date, a.snapshot))


if __name__ == "__main__":
    sys.exit(main())
