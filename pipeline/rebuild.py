"""
BIWEEKLY REBUILD  —  run:  python -m pipeline.rebuild   (add --force to run in an off week)

 1. RECONCILE   read last checklist; record the trades you placed
 2. TEAM        news -> fundamentals -> catalysts -> debate -> judge   (pipeline.team)
 3. PM          Opus picks names; code enforces rules, sizes, builds trades, places accounts
 4. CHECKS      code: rule compliance, turnover, wash sales (cross-account), drawdown level
 5. CRITIC      Sonnet (a different model from the PM) reviews every trade + the portfolio;
                failed new buys go back to the PM once
 6. APPROVAL    partial: clean trades go out; flagged trades wait for you; held buy money parks
                in SPY; a sale that's held shrinks the buys it was funding
 7. DELIVER     email (trades by account, sells first, limits, wash-sale results, flags) +
                GitHub checklist issue; plan saved for next reconciliation
"""
import json
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

from . import checkpoint as cpt
from . import broker, config, integrity, ledger, team
from .checkpoint import Checkpoint
from .book import ACCOUNTS, account_values, load_book, positions_df, post_checklist, reconcile_all, wash_check
from .notify import send, subject_line
from .approvals import check_macro
from .pm import PARKING, PM_SYSTEM, _c, build_trades, clusters, factor_tilts, holding_info, render_macro, select, size
from .runner import run_stage
from .util import JSON_RULE, now_et, read_json, require_columns, state_path, version_stamp, write_json, write_text

TODAY = now_et().date()
REBUILD_WEEK_PARITY = 0           # rebuild on even ISO weeks (change to 1 to shift by a week)
MAX_TURNOVER = 0.50               # more than half the portfolio traded in one rebuild -> blocked


def next_trading_day(d):
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def trade_day(now=None):
    """The session the plan trades in: today if the plan is finished before 9 am ET on a weekday (a run that
    ends overnight still trades that morning), otherwise the next weekday."""
    now = now or now_et()
    if now.weekday() < 5 and now.hour < 9:
        return now.date()
    return next_trading_day(now.date())


# ==================================================================== prices
def market_prices(tickers):
    import yfinance as yf
    tickers = sorted(set(tickers) | {PARKING})
    data = yf.download([t.replace(".", "-") for t in tickers], period="6mo", progress=False, auto_adjust=True)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    data.columns = [c.replace("-", ".") for c in data.columns]
    require_columns(data, [PARKING], "the rebuild")
    last = {t: float(data[t].dropna().iloc[-1]) for t in data.columns if data[t].notna().any()}
    rets = data.pct_change().tail(60)
    corr = rets.corr()
    # market-adjusted returns (each stock minus beta x SPY): what's left shows hidden common bets
    spy = rets[PARKING]
    beta = rets.apply(lambda c: c.cov(spy) / spy.var() if spy.var() else 1.0)
    corr.attrs["resid"] = (rets - spy.values[:, None] * beta.values[None, :]).drop(columns=[PARKING]).corr()
    return last, corr


# ==================================================================== critic
CRITIC_SYSTEM = ("You are the risk reviewer on an investment committee and a different model from the portfolio "
                 "manager. Your job is to find problems, not to agree. For each trade: does it follow from the "
                 "committee's evidence? For sells: is the thesis really broken, or is this reacting to price noise? "
                 "Portfolio level: consistency with the macro view, hidden common bets, several holdings reporting "
                 "earnings in the same week, flip-flops (rebuying something just sold without new evidence), strong "
                 "bear arguments ignored. FAIL only for clear errors (wrong facts, a broken thesis being bought, a "
                 "rule-worthy mistake); FLAG real concerns the owner should weigh. Sector labels are the official "
                 "S&P (GICS) classification (e.g. Target, Dollar General and Walmart are Consumer Staples since 2023): "
                 "take them as given, don't flag them. Geopolitics: compare each holding's geographic exposure (where it "
                 "sells and makes things) with the macro view's key risks and the market-risk readings; FLAG a large "
                 "position concentrated in a region or supply chain the macro view names as a live risk, or several "
                 "holdings sharing the same exposure. " + JSON_RULE)
CRITIC_SHAPE = ('{"overall": "PASS|FLAG|FAIL", "summary": "...", '
                '"trades": {"<id>": {"status": "PASS|FLAG|FAIL", "issue": "...", "recommendation": "..."}}, '
                '"portfolio_issues": ["..."]}\n'
                'Be brief: a PASS trade gets {"status": "PASS"} with no text; each issue and recommendation is one '
                'sentence of at most 40 words; at most 6 portfolio issues.')


def render_review(trades, weights, team_res, macro, recent_sells, digest):
    stocks = team_res["stocks"]
    L = render_macro(macro or {}, digest)
    L += ["", "## TARGET PORTFOLIO", "ticker | weight % | sector | probability % | edge pts | primary driver | thesis | key risk | exit condition"]
    for t, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        v = stocks.get(t, {}).get("verdict", {})
        L.append(" | ".join(_c(x) for x in (t, w, stocks.get(t, {}).get("sector", "parking" if t == PARKING else ""),
                                            round(v["probability"] * 100, 1) if v.get("probability") is not None else None,
                                            v.get("edge_pts"), v.get("primary_driver"), v.get("thesis"),
                                            v.get("key_risk"), v.get("exit_condition"))))
    L += ["", "## TRADES", "id | action | ticker | account | amount | reason"]
    L += [" | ".join(_c(t.get(k)) for k in ("id", "action", "ticker", "account", "amount", "reason")) for t in trades]
    L += ["", "## DEBATES AND CATALYSTS", "ticker | bull summary | bear summary | judge winner | catalysts"]
    for t, s in stocks.items():
        if t in weights or t in {x["ticker"] for x in trades}:
            cats = "; ".join(i["text"] for i in s["dossier"] if i["kind"] == "catalyst")[:300]
            L.append(" | ".join(_c(x) for x in (t, (s["debate"].get("bull_open") or {}).get("summary"),
                                                (s["debate"].get("bear_open") or {}).get("summary"),
                                                s["verdict"].get("winner"), cats)))
    geo = []
    for t, s in stocks.items():
        if t in weights or t in {x["ticker"] for x in trades}:
            lines = [i["text"] for i in s.get("dossier", []) if i.get("kind") == "filing_flag"
                     and i["text"].startswith(("Geographic revenue exposure", "Where it makes"))]
            if lines:
                geo.append(f"{t} | " + " / ".join(x.split(": ", 1)[-1] for x in lines)[:500])
    if geo:
        L += ["", "## GEOGRAPHIC EXPOSURE (sentences from each company's latest filing)", "ticker | exposure"] + geo
    L += ["", "SOLD IN THE LAST 60 DAYS: " + (", ".join(recent_sells) or "none")]
    return "\n".join(L)


def critic(session, trades, weights, team_res, macro, recent_sells, digest=None):
    packet = render_review(trades, weights, team_res, macro, recent_sells, digest)
    r = session.ask("portfolio_critic", CRITIC_SYSTEM, "JSON shape:\n" + CRITIC_SHAPE,
                    shared="REVIEW PACKET:\n" + packet, max_tokens=20000)   # 12000 was cut off at 17 trades (Nov 2026); above ~21000 the SDK demands streaming
    d = r.data if isinstance(r.data, dict) else {}
    d.setdefault("overall", "FLAG")
    d.setdefault("trades", {})
    if not r.data:
        d["summary"] = "critic reply unusable: all trades flagged for your review"
        d["trades"] = {t["id"]: {"status": "FLAG", "issue": "not reviewed"} for t in trades}
    return d


# ==================================================================== approval
def approve(trades, crit, block_reasons, book, place_flagged=False):
    """Sets each trade's status: approved | flagged | held. Returns extra parking trades.
    place_flagged (paper mode, after the PM has revised once for the critic's flags): a trade still
    flagged is placed anyway, with the concern kept in the report."""
    for t in trades:
        c = crit["trades"].get(t["id"], {})
        t["critic"], t["critic_issue"], t["recommendation"] = c.get("status", "PASS"), c.get("issue", ""), c.get("recommendation", "")
        if block_reasons:
            t["status"] = "held"
        elif t["wash"] == "blocked":
            t["status"], t["critic_issue"] = "held", t["wash_note"]
        elif t["critic"] == "FAIL":
            t["status"] = "held"
        elif t["critic"] == "FLAG" and place_flagged and t["wash"] == "ok":
            t["status"] = "approved"
            t["recommendation"] = ("placed (paper) after the PM's revision; concern kept for the record. "
                                   + (t["recommendation"] or ""))
        elif t["critic"] == "FLAG" or t["wash"] == "warn":
            t["status"] = "flagged"
        else:
            t["status"] = "approved"
    if block_reasons:
        return []
    extra = []
    for a in ACCOUNTS:
        cash = book["accounts"][a]["cash"]
        cash += sum(t["amount"] if t["amount"] != "all" else t.get("est_value", 0)
                    for t in trades if t["account"] == a and t["action"] == "SELL" and t["status"] == "approved")
        buys = [t for t in trades if t["account"] == a and t["action"] == "BUY" and t["status"] == "approved"]
        need = sum(t["amount"] for t in buys)
        if need > cash + 1 and buys:         # a held sale was funding these buys: shrink them together
            f = max(cash, 0) / need
            for t in buys:
                t["amount"] = round(t["amount"] * f, 2)
                t["reason"] += f" (reduced to {f:.0%}: a sale funding it is on hold)"
            need = sum(t["amount"] for t in buys)
        held_buys = sum(t["amount"] for t in trades if t["account"] == a and t["action"] == "BUY" and t["status"] != "approved")
        park = min(held_buys, cash - need)
        if park >= 50:
            extra.append({"action": "BUY", "account": a, "ticker": PARKING, "amount": round(park, 2), "status": "approved",
                          "reason": "park money from held/flagged buys until you decide", "wash": "ok", "wash_note": "",
                          "critic": "PASS", "critic_issue": "", "recommendation": ""})
    return extra


# ==================================================================== thesis sheet
def theses_md(weights, team_res, date):
    """One page per pick, in plain English: why it's owned, the case against it, and when to sell."""
    st = team_res["stocks"]
    pct = lambda x: f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"
    L = [f"# Pick theses, rebuild of {date}", "",
         "Probability = the judges' forecast that the stock beats its equal-weighted sector over the next 4 weeks. "
         "Base rate = how often stocks with the same momentum, earnings reaction and quality did so historically. "
         "Edge = how far the judges moved it above that.", ""]
    picks = sorted([t for t in weights if t != PARKING and t in st], key=lambda t: -weights[t])
    for t in picks:
        s, v = st[t], st[t]["verdict"]
        d = s.get("debate") or {}
        pts = lambda k: [p.get("claim", "") for p in ((d.get(k) or {}).get("points") or []) if isinstance(p, dict)][:4]
        judges = "; ".join(f"{k} {pct(j.get('probability'))}" + ("" if j.get("live") else " (shadow)")
                           for k, j in (v.get("judges") or {}).items() if j.get("probability") is not None)
        cats = [i["text"] for i in s.get("dossier", []) if i["kind"] == "catalyst"][:3]
        L += [f"## {t} — {s.get('name', '')}",
              f"**{weights[t]:.1f}% of the portfolio** · {s.get('sector')} · probability {pct(v.get('probability'))} "
              f"(base rate {pct(v.get('base_p'))}, edge {v.get('edge_pts', 0):+.1f} pts) · debate won by {v.get('winner', 'n/a')}"
              + (" · **judges disagreed**" if v.get("disagreement") else ""), "",
              f"**Thesis:** {v.get('thesis', '')}", "",
              f"**Main driver:** {v.get('primary_driver', 'n/a')}", ""]
        if pts("bull_open"):
            L += ["**Bull case:**"] + [f"- {x}" for x in pts("bull_open")] + [""]
        if pts("bear_open"):
            L += ["**Bear case:**"] + [f"- {x}" for x in pts("bear_open")] + [""]
        if cats:
            L += ["**Upcoming catalysts:**"] + [f"- {x}" for x in cats] + [""]
        L += [f"**Key risk:** {v.get('key_risk', '')}", "", f"**Sell if:** {v.get('exit_condition', '')}", "",
              f"*Judges: {judges}*", "", "---", ""]
    if weights.get(PARKING):
        L += [f"**SPY {weights[PARKING]:.1f}%:** the rest of the money, parked in the S&P 500 until more stocks clear the buy bar."]
    return "\n".join(L)


# ==================================================================== delivery
def trade_rows_html(rows, prices):
    h = ("<table border='1' cellpadding='4' style='border-collapse:collapse'><tr><th>ID</th><th>Account</th><th>Action</th>"
         "<th>Ticker</th><th>Amount</th><th>Est. shares</th><th>Limit</th><th>Reason</th><th>Checks</th></tr>")
    for t in rows:
        amt = "ALL" if t["amount"] == "all" else f"${float(t['amount']):,.0f}"
        sh = "" if t["amount"] == "all" or not prices.get(t["ticker"]) else f"{float(t['amount']) / prices[t['ticker']]:.2f}"
        checks = "✅" if t["wash"] == "ok" else ("⛔ " if t["wash"] == "blocked" else "⚠️ ") + t["wash_note"]
        if t.get("critic_issue") and t["status"] != "approved":
            checks += f" · {t['critic']}: {t['critic_issue']}"
        h += (f"<tr><td>{t['id']}</td><td>{ACCOUNTS[t['account']]}</td><td><b>{t['action']}</b></td><td>{t['ticker']}</td>"
              f"<td>{amt}</td><td>{sh}</td><td>${t.get('limit', 0):.2f}</td><td>{t['reason']}</td><td>{checks}</td></tr>")
    return h + "</table>"


def deliver(plan, prices, crit, notes, block_reasons, folder, recon):
    status = "BLOCK" if block_reasons else ("FLAG" if any(t["status"] != "approved" for t in plan["trades"]) else "PASS")
    order = lambda t: (t["account"], t["action"] != "SELL", t["id"])
    appr = sorted([t for t in plan["trades"] if t["status"] == "approved"], key=order)
    flag = [t for t in plan["trades"] if t["status"] == "flagged"]
    held = [t for t in plan["trades"] if t["status"] == "held"]
    html = f"<h3>Rebuild {plan['date']}: {status}</h3>" + (f"<p>📈 {plan['status_line']}</p>" if plan.get("status_line") else "")
    if plan.get("paper"):
        how = (f"Approved trades will be placed automatically in your Alpaca paper account on {plan['trade_date']} "
               "at about 10:45 am ET (sells first) and recorded at their actual paper fill prices."
               if broker.enabled() else
               "The plan is recorded as if every approved trade filled at its reference price.")
        html += ("<p style='background:#fff3cd;padding:8px'><b>📝 PAPER MODE: do not place these trades at Robinhood.</b> "
                 + how + " The track record builds without real money. Set the PAPER_MODE variable to 0 in GitHub to "
                 "go live (see SETUP.md).</p>")
    if block_reasons:
        html += "<p><b>⛔ Blocked, no trades this cycle:</b></p><ul>" + "".join(f"<li>{b}</li>" for b in block_reasons) + "</ul>"
    if plan.get("factor_tilts"):
        html += ("<p><b>Style lean</b> (0-100 percentile, 50 = neutral): "
                 + ", ".join(f"{k} {v}" for k, v in plan["factor_tilts"].items()) + "</p>")
    html += (f"<p>Portfolio value ${plan['portfolio_value']:,.0f} · {len(plan['target'])} positions · "
             f"place trades on {plan['trade_date']} after the first 15-30 minutes of trading, sells first, "
             f"limit orders good for the day. Dollar amounts are targets; share counts are estimates.</p>")
    if appr:
        html += "<h4>✅ Ready to place</h4>" + trade_rows_html(appr, prices)
    if flag:
        html += ("<h4>⚠️ Flagged: your call</h4><ul>" + "".join(
            f"<li><b>{t['id']} {t['action']} {t['ticker']}</b>: {t['critic_issue']} <i>{t.get('recommendation', '')}</i></li>" for t in flag) + "</ul>")
    if held:
        html += "<h4>⛔ Held</h4><ul>" + "".join(f"<li>{t['id']} {t['action']} {t['ticker']}: {t['critic_issue']}</li>" for t in held) + "</ul>"
    html += f"<p><b>Critic:</b> {crit.get('overall')}. {crit.get('summary', '')}</p>"
    if crit.get("portfolio_issues"):
        html += "<ul>" + "".join(f"<li>{i}</li>" for i in crit["portfolio_issues"]) + "</ul>"
    if notes:
        html += "<p><b>Sizing notes:</b> " + "; ".join(notes) + "</p>"
    if recon:
        html += "<p><b>Recorded from your last checklist:</b></p><ul>" + "".join(f"<li>{r}</li>" for r in recon) + "</ul>"
    html += f"<p>✔️ Checklist: {plan['checklist']['url']}</p><p>Full report attached.</p>"
    text = "\n".join(f"{t['id']} {ACCOUNTS[t['account']]} {t['action']} {t['ticker']} "
                     f"{'ALL' if t['amount'] == 'all' else '$' + format(float(t['amount']), ',.0f')} [{t['status']}]" for t in plan["trades"])
    headline = f"{len(appr)} trades ready" + (f", {len(flag)} flagged" if flag else "")
    stage = "Rebuild [PAPER]" if plan.get("paper") else "Rebuild"
    send(subject_line(stage, status, headline), text, html, attachments=[folder / "report.md", folder / "theses.md"],
         save_dir=folder)
    return status


def report(plan, pick, weights, notes, crit, team_res, block_reasons):
    st = team_res["stocks"]
    L = [f"# Portfolio rebuild {plan['date']}", f"Trade date {plan['trade_date']} · value ${plan['portfolio_value']:,.0f}", ""]
    if block_reasons:
        L += ["## ⛔ Blocked"] + [f"- {b}" for b in block_reasons] + [""]
    L += ["## Target portfolio", "| Ticker | Weight | Sector | Probability / edge | Driver | Thesis | Exit if |", "|---|---|---|---|---|---|---|"]
    for t, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        v = st.get(t, {}).get("verdict", {})
        L.append(f"| {t} | {w:.1f}% | {st.get(t, {}).get('sector', 'parking' if t == PARKING else '')} | {(str(round(v['probability'] * 100, 1)) + '% / ' + format(v.get('edge_pts', 0), '+.1f')) if v.get('probability') is not None else ''} | "
                 f"{v.get('primary_driver', '')} | {v.get('thesis', '')} | {v.get('exit_condition', '')} |")
    if plan.get("factor_tilts"):
        L += ["", "**Style lean** (0-100 percentile, 50 = neutral): " + ", ".join(f"{k} {v}" for k, v in plan["factor_tilts"].items())]
    L += ["", f"**PM summary:** {pick.get('summary', '')}", ""]
    L += ["## Exits"] + [f"- {e['ticker']}: {e.get('reason', '')} (thesis broken: {e.get('thesis_broken')})" for e in pick["exits"]]
    L += ["", "## Trades", "| ID | Account | Action | Ticker | Amount | Status | Wash | Critic |", "|---|---|---|---|---|---|---|---|"]
    for t in plan["trades"]:
        amt = "ALL" if t["amount"] == "all" else f"${float(t['amount']):,.0f}"
        L.append(f"| {t['id']} | {ACCOUNTS[t['account']]} | {t['action']} | {t['ticker']} | {amt} | {t['status']} | "
                 f"{t['wash']} {t['wash_note']} | {t['critic']} {t['critic_issue']} |")
    L += ["", f"## Critic: {crit.get('overall')}", crit.get("summary", "")] + [f"- {i}" for i in crit.get("portfolio_issues", [])]
    if pick.get("rule_log"):
        L += ["", "## Rule enforcement"] + [f"- attempt {x['attempt']}: {'; '.join(x['violations'])}" for x in pick["rule_log"]]
    if notes:
        L += ["", "## Sizing notes"] + [f"- {n}" for n in notes]
    return "\n".join(L)


def record_holding_decisions(team_res, info, weights, pick, trades):
    """Remember this rebuild's sell signals (a sell needs two in a row), and log every holding as sold
    or kept, and every buy with the critic's verdict, for grading."""
    day = team_res.get("date", TODAY.isoformat())
    signals = read_json(state_path("holding_signals.json"), {}) or {}
    for t, i in info.items():
        signals[t] = {"date": day, "signal": bool(i.get("signal_now"))}
    write_json(state_path("holding_signals.json"), {t: v for t, v in signals.items() if t in info})
    why = {e["ticker"]: e.get("reason", "") for e in pick.get("exits", []) if isinstance(e, dict)}
    ledger.record_sells(day, [{"ticker": t, "action": "kept" if weights.get(t) else "sold",
                               "reason": "" if weights.get(t) else (why.get(t) or "no longer in target"),
                               "edge_pts": i.get("edge"), "probability": i.get("probability"),
                               "must_exit": bool(i.get("must_exit"))} for t, i in info.items()])
    ledger.record_critic(day, trades)


# ==================================================================== MAIN
def make_plan_inputs(names, st, bench):
    bcol = "vol_blend" if "vol_blend" in getattr(bench, "columns", []) else "vol_60d"
    vol = {t: st[t]["vol_60d"] if t in st else float(bench.loc[t, bcol]) if t in bench.index else 0.3 for t in names}
    sector_of = {t: st[t]["sector"] if t in st else (bench.loc[t, "sector"] if t in bench.index else "Unknown") for t in names}
    meta = {t: {"sector": sector_of[t], "vol": vol[t], **{k: st.get(t, {}).get("verdict", {}).get(k)
            for k in ("thesis", "exit_condition", "primary_driver", "conviction", "probability", "edge_pts")}} for t in names}
    return vol, sector_of, meta


def sizing_extras(names, st, info, bench=None):
    """Edge (for weakest-first trims), momentum scores 0-1 (for the momentum-level cap: the screen's
    within-sector rank, or the momentum quintile when that's missing), and gains (loss sold first)."""
    strength = {t: st.get(t, {}).get("verdict", {}).get("edge_pts", 0) for t in names}
    has = bench is not None and len(bench) and "s_momentum" in bench
    mom_top = {t: (float(bench.loc[t, "s_momentum"]) if has and t in bench.index and bench.loc[t, "s_momentum"] == bench.loc[t, "s_momentum"]
                   else ((st.get(t, {}).get("features") or {}).get("m", 3) - 0.5) / 5) for t in names}
    gains = {t: (info or {}).get(t, {}).get("gain_%", 0) for t in names}
    return strength, mom_top, gains


def plan_stage(session, team_res, book, macro, bench, holdings_view, dd, universe, exclude_note=None, digest=None, info=None,
               feedback=""):
    """PM selection -> sizing -> trades -> wash check. Returns a JSON-safe dict."""
    prices, corr = market_prices(universe)
    pick = select(session, team_res, holdings_view, macro, corr, dd, digest, info, feedback)
    if exclude_note:
        pick["summary"] = exclude_note + " " + pick.get("summary", "")
    names = [p["ticker"] for p in pick["portfolio"]]
    vol, sector_of, meta = make_plan_inputs(names, team_res["stocks"], bench)
    strength, mom_top, gains = sizing_extras(names, team_res["stocks"], info, bench)
    groups = clusters(names, getattr(corr, "attrs", {}).get("resid"))
    from .pm import themes_of
    weights, notes = size(names, vol, sector_of, macro.get("weight_ranges_%", {}), dd, strength, mom_top, gains, groups,
                          themes_of(pick))
    trades, total = build_trades(weights, book, prices, meta, pick["exits"])
    pos = positions_df(book, prices)
    for t in trades:
        if t["amount"] == "all":
            t["est_value"] = float(pos[(pos.ticker == t["ticker"]) & (pos.account == t["account"])].value.sum())
    wash_check(trades, book, prices)
    return json.loads(json.dumps({"pick": pick, "weights": weights, "notes": notes, "trades": trades,
                                  "total": total, "prices": prices, "priced_on": TODAY.isoformat()}, default=str))


def reprice(st, team_res, book, bench, universe, crit=None):
    """A resumed plan older than a day: keep the stock choices and target weights, but rebuild the
    trades from today's prices (amounts, share estimates, limit prices). If the critic already
    reviewed the old trades, carry its verdicts over by (action, ticker, account)."""
    prices, _ = market_prices(universe)
    names = [p["ticker"] for p in st["pick"]["portfolio"]]
    _, _, meta = make_plan_inputs(names, team_res["stocks"], bench)
    trades, total = build_trades(st["weights"], book, prices, meta, st["pick"]["exits"])
    pos = positions_df(book, prices)
    for t in trades:
        if t["amount"] == "all":
            t["est_value"] = float(pos[(pos.ticker == t["ticker"]) & (pos.account == t["account"])].value.sum())
    wash_check(trades, book, prices)
    new = json.loads(json.dumps(dict(st, trades=trades, total=total, prices=prices, priced_on=TODAY.isoformat(),
                                     notes=st["notes"] + [f"prices refreshed on {TODAY} (plan made {st.get('priced_on')})"]),
                                default=str))
    if crit is None:
        return new, None
    by_key = {(t["action"], t["ticker"], t["account"]): crit["trades"].get(t["id"]) for t in st["trades"]}
    remapped = {}
    for t in new["trades"]:
        c = by_key.get((t["action"], t["ticker"], t["account"]))
        remapped[t["id"]] = c or {"status": "FLAG", "issue": "trade changed when prices were refreshed; not re-reviewed"}
    return new, dict(crit, trades=remapped)


def main(session, folder, force=None, team_kwargs=None, replan=None, allow_turnover=None):
    """replan: redo only the portfolio steps (PM, sizing, critic, trades) on the last stock-team results:
    no new research or judging (~$0.60 instead of ~$10). For after rule changes, before orders go out."""
    replan = replan if replan is not None else "--replan" in sys.argv
    force = force if force is not None else ("--force" in sys.argv or replan)
    allow_turnover = allow_turnover if allow_turnover is not None else "--allow-turnover" in sys.argv   # owner's one-off approval
    check_macro()                              # apply your APPROVE/REJECT on a held macro view first
    print("1/7 Reconciling checklists...")
    bench = pd.read_csv(state_path("bench.csv")).set_index("ticker") if state_path("bench.csv").exists() else pd.DataFrame()
    book = load_book()
    held_now = sorted({p["ticker"] for p in book["positions"]})
    prices, _ = market_prices(held_now) if held_now else ({}, None)
    recon = reconcile_all(prices)
    for r in recon:
        print("    " + r)
    resuming = cpt.incomplete("rebuild") is not None
    if not resuming and not force and TODAY.isocalendar()[1] % 2 != REBUILD_WEEK_PARITY:
        print("    Not a rebuild week (use --force to run anyway).")
        return {"status": "skipped"}
    done = read_json(cpt._path("rebuild")) or {}
    if not resuming and not force and done.get("completed") and done.get("started") == TODAY.isoformat():
        print("    A rebuild already finished today: not running a second one (use --force to rerun).")
        return {"status": "skipped"}
    ck = Checkpoint("rebuild", fresh=force and not resuming)
    if ck.resumed:
        print(f"    Resuming the rebuild started {ck.data['started']} (attempt {ck.attempts}); no --force needed")
    recon = ck.get("recon") or ck.save("recon", recon)
    macro = config.with_current_ranges(read_json(state_path("macro_view.json")))
    if not macro:
        raise RuntimeError("No approved macro view in state/macro_view.json: run the weekly job first.")

    print("2/7 Stock team...")
    if replan and not ck.has("team_done"):
        if not state_path("team_results.json").exists():
            raise RuntimeError("--replan needs a finished stock-team run (state/team_results.json)")
        print("    replan: reusing the last stock-team results (no new research or judging)")
        ck.save("team_done", True)
    if ck.has("team_done"):
        print("    already finished in an earlier attempt")
    else:
        team_folder = folder / "team"
        team_folder.mkdir(exist_ok=True)
        team.main(session, team_folder, **(team_kwargs or {}))
        ck.save("team_done", True)
    team_res = read_json(state_path("team_results.json"))

    print("3/7 Portfolio manager...")
    book = load_book()
    universe = set(team_res["stocks"]) | {p["ticker"] for p in book["positions"]}
    pos0 = positions_df(book, prices)
    holdings_view = [{"ticker": p["ticker"], "account": p["account"], "value": round(p["value"], 2),
                      "gain_%": round(p["gain"] / p["cost_basis"] * 100, 1), "bought": p["buy_date"],
                      "thesis": p.get("thesis"), "exit_condition": p.get("exit_condition"),
                      "conviction_then": p.get("conviction")} for _, p in pos0.iterrows()] if len(pos0) else []
    dd = (read_json(state_path("drawdown.json"), {}) or {}).get("level", 0)
    signals = read_json(state_path("holding_signals.json"), {}) or {}
    info = holding_info(holdings_view, team_res, signals, team_res.get("date", TODAY.isoformat()))
    digest = read_json(state_path("macro_check.json"), {}) or {}
    if digest.get("view_date") != macro.get("date"):
        digest = {}                            # digest belongs to a different view; don't mislead the PM
    st1 = ck.get("plan1") or ck.save("plan1", plan_stage(session, team_res, book, macro, bench, holdings_view, dd,
                                                         universe, digest=digest, info=info))
    if st1.get("priced_on") != TODAY.isoformat():
        print(f"    plan from {st1.get('priced_on')}: refreshing prices, amounts and limits")
        st1, c1 = reprice(st1, team_res, book, bench, universe, ck.get("critic1"))
        ck.save("plan1", st1)
        if c1:
            ck.save("critic1", c1)
    pick, weights, notes, trades, total, prices = (st1[k] for k in ("pick", "weights", "notes", "trades", "total", "prices"))
    pos = positions_df(book, prices)

    print("4/7 Code checks: turnover, wash sales, drawdown...")
    traded = sum(t["est_value"] if t["amount"] == "all" else float(t["amount"]) for t in trades if t["action"] == "SELL")
    block = []
    if len(pos) and traded > MAX_TURNOVER * total and allow_turnover:
        print(f"    turnover {traded / total:.0%} is over the {MAX_TURNOVER:.0%} cap: approved by the owner for this run")
        notes = list(notes or []) + [f"Turnover {traded / total:.0%} is over the {MAX_TURNOVER:.0%} cap; approved by the owner for this rebuild."]
    elif len(pos) and traded > MAX_TURNOVER * total:
        block.append(f"Turnover {traded / total:.0%} exceeds {MAX_TURNOVER:.0%} of the portfolio in one rebuild")
    if dd >= 2:
        block.append("Drawdown level 2: portfolio trails SPY by 10%+; moving to SPY needs your review")

    print("5/7 Critic review...")
    log = pd.read_csv(state_path("trades.csv")) if state_path("trades.csv").exists() else pd.DataFrame()
    recent_sells = sorted(set(log[(log.action == "SELL") & (pd.to_datetime(log.date) >= pd.Timestamp(TODAY - timedelta(days=60)))].ticker)) if len(log) else []
    crit = ck.get("critic1") or ck.save("critic1", critic(session, trades, weights, team_res, macro, recent_sells, digest))
    held = set(pos.ticker) if len(pos) else set()
    failed_new = [t["ticker"] for t in trades if t["action"] == "BUY" and crit["trades"].get(t["id"], {}).get("status") == "FAIL"
                  and t["ticker"] not in held]
    if failed_new:
        print(f"    Critic failed new buys {failed_new}; asking the PM for replacements once")
        why = "; ".join(f"{t['ticker']}: {crit['trades'][t['id']].get('issue')}" for t in trades if t["ticker"] in failed_new)
        reduced = dict(team_res, stocks={k: v for k, v in team_res["stocks"].items() if k not in failed_new})
        st2 = ck.get("plan2") or ck.save("plan2", plan_stage(
            session, reduced, book, macro, bench, holdings_view, dd, universe - set(failed_new),
            exclude_note=f"(revised after the critic rejected {failed_new}: {why})", digest=digest, info=info))
        if st2.get("priced_on") != TODAY.isoformat():
            st2, c2 = reprice(st2, reduced, book, bench, universe - set(failed_new), ck.get("critic2"))
            ck.save("plan2", st2)
            if c2:
                ck.save("critic2", c2)
        pick, weights, notes, trades, total, prices = (st2[k] for k in ("pick", "weights", "notes", "trades", "total", "prices"))
        crit = ck.get("critic2") or ck.save("critic2", critic(session, trades, weights, reduced, macro, recent_sells, digest))
        still = [t for t in trades if t["action"] == "BUY" and crit["trades"].get(t["id"], {}).get("status") == "FAIL"]
        if len(still) >= 2:
            block.append(f"Critic failed {len(still)} new buys even after the PM revised the portfolio")

    flagged = [t for t in trades if crit["trades"].get(t["id"], {}).get("status") == "FLAG"]
    if flagged and not block:
        # one revision: the PM answers the critic's flags (drop, swap or keep with a reason); code re-sizes
        print(f"    Critic flagged {[t['ticker'] for t in flagged]}; asking the PM to revise once")
        fb = ("REVISE YOUR PORTFOLIO. The risk reviewer flagged these trades:\n- " + "\n- ".join(
            f"{t['action']} {t['ticker']}: {crit['trades'][t['id']].get('issue')} (suggestion: "
            f"{crit['trades'][t['id']].get('recommendation', '')})" for t in flagged)
            + ("\nPortfolio-level concerns:\n- " + "\n- ".join(crit.get("portfolio_issues") or []) if crit.get("portfolio_issues") else "")
            + "\nFor each flagged name: drop it, swap it for another eligible name, or keep it and answer the concern "
              "in its 'why'. Code sizes by edge/volatility and caps any group of names that move together at 20%.")
        cur_team = reduced if failed_new else team_res
        cur_uni = universe - set(failed_new)
        st3 = ck.get("plan3") or ck.save("plan3", plan_stage(
            session, cur_team, book, macro, bench, holdings_view, dd, cur_uni,
            exclude_note="(revised once for the critic's flags)", digest=digest, info=info, feedback=fb))
        if st3.get("priced_on") != TODAY.isoformat():
            st3, c3 = reprice(st3, cur_team, book, bench, cur_uni, ck.get("critic3"))
            ck.save("plan3", st3)
            if c3:
                ck.save("critic3", c3)
        earlier_log = pick.get("rule_log") or []
        pick, weights, notes, trades, total, prices = (st3[k] for k in ("pick", "weights", "notes", "trades", "total", "prices"))
        pick["rule_log"] = earlier_log + (pick.get("rule_log") or [])
        crit = ck.get("critic3") or ck.save("critic3", critic(session, trades, weights, cur_team, macro, recent_sells, digest))
        held_new = [t for t in trades if t["action"] == "BUY" and crit["trades"].get(t["id"], {}).get("status") == "FAIL"
                    and t["ticker"] not in held]
        if len(held_new) >= 2:
            block.append(f"Critic failed {len(held_new)} new buys in the revised portfolio")

    print("6/7 Approval...")
    extra = approve(trades, crit, block, book, place_flagged=bool(config.PAPER_MODE) and bool(flagged))
    for i, x in enumerate(extra, len(trades) + 1):
        x.update(id=f"T{i:02d}", ref_price=prices.get(PARKING), limit=round(prices.get(PARKING, 0) * 1.005, 2))
    trades += extra
    for t in trades:
        t["key"] = integrity.trade_key(ck.data["started"], t)

    # fail-closed safety check by code: any problem blocks the whole plan
    sector_of = {t: (team_res["stocks"].get(t) or {}).get("sector") or
                 (bench.loc[t, "sector"] if len(bench) and t in bench.index else None) for t in weights}
    problems = integrity.check({"trades": [t for t in trades if t["status"] != "held"]}, book, weights, sector_of,
                               macro.get("weight_ranges_%", {}))
    if problems:
        print("    INTEGRITY CHECK FAILED: " + "; ".join(problems[:5]))
        block += [f"Integrity check: {x}" for x in problems]
        for t in trades:
            t["status"] = "held"

    print("7/7 Delivering...")
    plan = {"date": ck.data["started"], "trade_date": trade_day().isoformat(), "portfolio_value": round(total, 2),
            "account_values": account_values(book, prices), "target": weights,
            "trades": [t for t in trades if t["status"] != "held"] if not block else [], "all_trades": trades,
            "blocked": block, "reconciled": None, "paper": bool(config.PAPER_MODE),
            "versions": version_stamp(PM_SYSTEM, CRITIC_SYSTEM, (team_res.get("versions") or {}).get("prompt_hash", ""))}
    plan["factor_tilts"] = factor_tilts(weights, bench.reset_index() if len(bench) else bench)
    from .track import record_rebuild, status_line
    if not ck.has("recorded"):
        record_rebuild(plan, team_res, read_json(state_path("candidates.json"), {}), weights)
        record_holding_decisions(team_res, info, weights, pick, trades)
        ck.save("recorded", True)
    if not ck.has("checklist"):
        ck.save("checklist", {"number": None, "url": broker.paper_note()}
                if plan["paper"] else post_checklist(plan) if plan["trades"] else {"number": None, "url": "no trades this cycle"})
    plan["checklist"] = ck.get("checklist")
    write_json(state_path("pending_plan.json"), plan)
    write_json(folder / "plan.json", dict(plan, pick=pick, critic=crit, notes=notes))
    if not ck.has("council_plan"):             # council test: sandbox portfolios, never traded; never blocks the plan
        try:
            from . import council_plan
            cp = council_plan.council_probs(team_res, team_res.get("date"))
            if cp:
                print("    council test: building the standard and council portfolios in a sandbox...")
                std, cou = council_plan.build_both(session, team_res, council_plan.council_verdicts(team_res, cp), book,
                                                   macro, bench, holdings_view, dd, universe, digest, info)
                council_plan.save(folder, team_res.get("date"), plan["trade_date"], std, cou, weights)
        except Exception as e:
            print(f"    ! council portfolio skipped ({str(e)[:120]})")
        ck.save("council_plan", True)
    write_text(folder / "report.md", report(dict(plan, trades=trades), pick, weights, notes, crit, team_res, block))
    write_text(folder / "theses.md", theses_md(weights, team_res, plan["date"]))
    plan["status_line"] = status_line()
    status = "PASS"
    if not ck.has("emailed"):
        status = deliver(dict(plan, trades=trades), prices, crit, notes, block, folder, recon)
        ck.save("emailed", status)
    status = ck.get("emailed")
    ck.complete()
    print(f"    {status}: {sum(t['status'] == 'approved' for t in trades)} approved, "
          f"{sum(t['status'] == 'flagged' for t in trades)} flagged, {sum(t['status'] == 'held' for t in trades)} held")
    return {"status": status}


if __name__ == "__main__":
    run_stage("rebuild", main)
