"""
PORTFOLIO MANAGER (Claude Opus picks names; code enforces every rule and does all the math)

Opus decides WHICH stocks to own and which holdings to exit (and why). Code then:
  - checks the rules and sends violations back to Opus (up to 2 retries), then auto-fixes:
      new buys: edge >= +3 pts over the base rate and probability >= 50%, 12+ months of history
      holdings: kept while edge >= -2 and probability >= 47% (a buffer against churn); a sell
        signal must show at two rebuilds in a row unless the thesis is broken; a swap needs a
        newcomer whose edge beats the holding's by 4 pts + the tax cost of selling (Individual);
        a winner within 30 days of long-term status waits unless the thesis is broken
      no more than 3 names per judge-stated driver or 6 per measured dominant macro factor;
      correlation limit; 15-20 names
  - sizes positions by inverse volatility, 3-10% each, inside the macro sector ranges, the
    momentum-level cap and a 20% cap on any group of names that move together (a hidden common bet); any forced trim (sector, momentum, drawdown) comes from the weakest edge first,
    and among equals from the position with the bigger loss
  - turns targets into trades with a 2-point rebalancing band and a $50 minimum
  - places trades in accounts: steadier holdings in Individual (taxable), the rest in the IRA
"""
import json

import numpy as np
import pandas as pd

from . import config
from .book import ACCOUNTS, positions_df
from .util import JSON_RULE

MIN_STOCKS, MAX_STOCKS = 15, 20     # was 8-12 until Nov 9: more, smaller, more independent bets
POS_MIN, POS_MAX = 3.0, 10.0        # was 5-15%; with fewer names than 10 the remainder parks in SPY
BAND = 2.0                    # percentage points before a holding is trimmed/topped up
MIN_TRADE = 50.0
CORR_LIMIT, MAX_PER_DRIVER = 0.80, 3
CLUSTER_CORR = 0.45           # names whose market-adjusted daily moves correlate this much are one hidden bet...
CLUSTER_CAP = 20.0            # ...and together get at most this % of the portfolio
MIN_BUY_CONVICTION = 3              # legacy label threshold (reports only)
PARKING = "SPY"
P = config.PROB

PM_SYSTEM = f"""You are the portfolio manager of a long-only U.S. stock portfolio with a 1-3 month horizon,
rebuilt every two weeks. For each stock a panel of independent judges gave the PROBABILITY it beats its
equal-weighted sector over the next 4 weeks, starting from a historical BASE RATE; EDGE is how many points
the judges moved it above that base rate. Choose {MIN_STOCKS}-{MAX_STOCKS} stocks. Code sizes positions and
enforces sector ranges and a momentum cap, so you choose names, not weights. Rules:
- New buys need edge >= +{P['buy_edge']} points and probability >= {P['buy_min']:.0%}. Rank newcomers by EDGE,
  not raw probability. Where judges disagreed (flagged), weigh the key risk more heavily.
- Holdings marked MUST EXIT must be exited. Holdings marked LONG-TERM SOON must be kept unless the thesis
  is broken. Exit any holding whose thesis is broken (its exit condition has occurred): say thesis_broken true.
- Otherwise replace a holding only with a newcomer whose edge exceeds the holding's edge by at least the
  holding's SWAP MARGIN (shown; it includes the tax cost of selling).
- No more than {MAX_PER_DRIVER} stocks sharing the same primary driver, and no more than {config.MAX_PER_FACTOR}
  sharing the same measured dominant macro factor. Avoid hidden common bets.
- Respect the macro view: sector weight ranges are hard limits (a 0 floor means you may hold none).
- Tag every pick with its single main THEME, the thing most likely to move it over the next month, from:
  {", ".join(config.THEMES)}. Code caps any one theme at {config.THEME_CAP:.0f}% of the portfolio, across
  sectors (a data-center power supplier and a memory-chip maker can share "ai_datacenter_buildout").
- UPCOMING EVENTS lists scheduled events (elections, Fed meetings, policy votes, earnings) in the next
  {config.EVENT_LOOKAHEAD_DAYS} days. Where one could hit a theme hard either way, don't stack new buys in that theme
  ahead of it; say in "why" when a pick is exposed to one.
- If fewer than {MIN_STOCKS} stocks deserve a place, own fewer; the remainder is parked in SPY.
The packet also shows how macro data moved since the macro view was formed: weigh that when the view is
older, but the sector weight ranges stay binding. Explain each choice in one sentence. """ + JSON_RULE

PM_SHAPE = ('{"portfolio": [{"ticker": "...", "theme": "<one of the themes>", "why": "..."}], '
            '"exits": [{"ticker": "...", "reason": "...", "thesis_broken": true}], "summary": "2-3 sentences"}')


# ==================================================================== selection
def eligible_new(s):
    v = s["verdict"]
    f = s.get("features") or {}
    old_enough = f.get("history_days") is None or f.get("history_days", 0) >= config.MIN_HISTORY_DAYS
    return (v.get("edge_pts", -99) >= P["buy_edge"] and v.get("probability", 0) >= P["buy_min"] and old_enough
            and not v.get("exit_breached"))     # its own sell trigger is already met: not a buy


def upcoming_events(macro, team, today=None):
    """Scheduled events in the next EVENT_LOOKAHEAD_DAYS: the macro view's list, the fixed calendar, and each
    candidate's dated catalysts (earnings etc.) from its dossier."""
    import datetime as _dt
    today = today or _dt.date.today()
    end = (today + _dt.timedelta(days=config.EVENT_LOOKAHEAD_DAYS)).isoformat()
    t0 = today.isoformat()
    out = []
    for e in list((macro or {}).get("upcoming_events") or []) + list(config.MARKET_EVENTS):
        d = str((e or {}).get("date", ""))[:10]
        if t0 <= d <= end:
            out.append({"date": d, "event": e.get("event"), "exposed": e.get("exposed") or e.get("sectors_or_themes")})
    for tk, s in (team.get("stocks") or {}).items():
        for i in s.get("dossier") or []:
            if i.get("kind") == "catalyst":
                d = str(i.get("text", ""))[:10]
                if t0 <= d <= end:
                    out.append({"date": d, "event": f"{tk}: {i['text'][12:].split(' (')[0]}", "exposed": [tk]})
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: e["date"]):
        k = (e["date"], str(e["event"]).lower())
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def pm_packet(team, holdings_view, macro, drawdown_level, digest=None, info=None):
    info = info or {}
    stocks = {t: {"sector": s["sector"], "probability": s["verdict"].get("probability"),
                  "base_rate": s["verdict"].get("base_p"), "edge": s["verdict"].get("edge_pts"),
                  "judges_disagree": bool(s["verdict"].get("disagreement")), "thesis": s["verdict"].get("thesis"),
                  "key_risk": s["verdict"].get("key_risk"), "exit_condition": s["verdict"].get("exit_condition"),
                  "primary_driver": s["verdict"].get("primary_driver"),
                  "macro_factor": (s.get("sensitivity") or {}).get("_dominant"), "winner": s["verdict"].get("winner"),
                  "screen_composite": round(s["composite"], 3), "volatility": round(s["vol_60d"], 3),
                  "incumbent": s["incumbent"],
                  "exit_already_met": s["verdict"].get("exit_breached")}
              for t, s in team["stocks"].items()
              # names that can't be bought stay out of the packet (they're still in the ledger)
              if eligible_new(s) or s["incumbent"]}
    holdings = [dict(h, **{k: (info.get(h["ticker"]) or {}).get(k) for k in
                           ("edge", "probability", "must_exit", "long_term_soon", "swap_margin", "signal")})
                for h in holdings_view]
    return {"macro": {"date": (macro or {}).get("date"), "regime": (macro or {}).get("regime"),
                      "tilts": (macro or {}).get("tilts"), "weight_ranges_%": (macro or {}).get("weight_ranges_%"),
                      "key_risks": (macro or {}).get("key_risks")},
            "macro_changes_since_view": digest or {}, "candidates": stocks, "current_holdings": holdings,
            "drawdown_level": drawdown_level, "events": upcoming_events(macro, team)}


def _c(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v).replace("|", "/")


def render_macro(m, digest):
    """Macro view + what changed since it, as compact tables (shared by the PM and the critic)."""
    L = [f"## MACRO VIEW ({m.get('date')}): regime {m.get('regime')}", "sector | tilt (-2..+2) | allowed weight %"]
    for sec, t in (m.get("tilts") or {}).items():
        lo, hi = (m.get("weight_ranges_%") or {}).get(sec, [0, 15])
        L.append(f"{sec} | {t:+d} | {lo}-{hi}")
    if m.get("key_risks"):
        L.append("Key risks: " + "; ".join(m["key_risks"]))
    d = digest or {}
    if d.get("changes_since_view"):
        L += ["", f"## MACRO DATA CHANGES SINCE THAT VIEW (code check of {d.get('date')}; z = std devs vs 5-yr history)",
              "id | label | at view | now | as_of | z change | flags"]
        L += [f"{r['id']} | {r['label']} | {_c(r['at_view'])} | {_c(r['now'])} | {r['as_of']} | {_c(r['z_change'])} | "
              + "; ".join(r["flags"]) for r in d["changes_since_view"][:20]]
    if d.get("market_risk"):
        L += ["", f"## MARKET & RECESSION RISK (statistical models, {d.get('date')}): {d['market_risk']}"]
    for k in ("triggers", "tripwires"):
        if d.get(k):
            L += [f"{k.upper()}: " + "; ".join(d[k])]
    return L


def render_pm_packet(p):
    L = render_macro(p["macro"], p.get("macro_changes_since_view"))
    L += ["", "## CANDIDATES (probability of beating the equal-weighted sector over 4 weeks)",
          "ticker | sector | probability % | base rate % | edge pts | judges disagree | primary driver | macro factor | "
          "screen score | volatility | held now | thesis | key risk | exit condition"]
    pct = lambda x: round(x * 100, 1) if isinstance(x, (int, float)) else None
    for t, c in sorted(p["candidates"].items(), key=lambda kv: -(kv[1].get("edge") or -99)):
        L.append(" | ".join(_c(x) for x in (t, c["sector"], pct(c.get("probability")), pct(c.get("base_rate")), c.get("edge"),
                                            "YES" if c.get("judges_disagree") else "", c["primary_driver"], c.get("macro_factor"),
                                            c["screen_composite"], c["volatility"], "yes" if c["incumbent"] else "no",
                                            c["thesis"], c["key_risk"], c["exit_condition"])))
    L += ["", "## CURRENT HOLDINGS", "ticker | account | value $ | gain % | bought | edge now | must exit | long-term soon | "
          "swap margin pts | thesis | exit condition"]
    L += [" | ".join(_c(x) for x in (h.get("ticker"), h.get("account"), h.get("value"), h.get("gain_%"), h.get("bought"),
                                     h.get("edge"), "YES: " + h["signal"] if h.get("must_exit") else "",
                                     "YES" if h.get("long_term_soon") else "", h.get("swap_margin"), h.get("thesis"),
                                     h.get("exit_condition"))) for h in p["current_holdings"]] or ["none"]
    held = {h.get("ticker") for h in p["current_holdings"]} | set(p["candidates"])
    ev = [e for e in p.get("events") or [] if not (isinstance(e.get("exposed"), list) and len(e["exposed"]) == 1
                                                  and e["exposed"][0] not in held and e["exposed"][0] == str(e["event"]).split(":")[0])]
    L += ["", f"## UPCOMING EVENTS (next {config.EVENT_LOOKAHEAD_DAYS} days)", "date | event | exposed"]
    L += [f"{e['date']} | {_c(e['event'])} | {_c(', '.join(map(str, e['exposed'])) if isinstance(e.get('exposed'), list) else e.get('exposed'))}"
          for e in ev] or ["none listed"]
    L += ["", f"DRAWDOWN LEVEL: {p['drawdown_level']} (0 normal, 1 = half of stock weight moves to SPY, 2 = all)"]
    return "\n".join(L)


def ask_pm(session, packet, feedback=""):
    prompt = f"{feedback}\nJSON shape:\n{PM_SHAPE}" if feedback else f"JSON shape:\n{PM_SHAPE}"
    r = session.ask("portfolio_manager", PM_SYSTEM, prompt, shared="PORTFOLIO PACKET:\n" + render_pm_packet(packet),
                    max_tokens=16000)   # 15-20 picks with reasons; 4000 can cut it off
    d = r.data if isinstance(r.data, dict) else {}
    d.setdefault("portfolio", [])
    d.setdefault("exits", [])
    return d


def holding_info(holdings_view, team, signals, today):
    """Per held ticker: current edge/probability, whether its sell signal is confirmed (two rebuilds in
    a row), whether it's a winner close to long-term status (Individual), and its swap margin."""
    st = team["stocks"]
    out = {}
    for h in holdings_view:
        t = h["ticker"]
        if t == PARKING:
            continue
        v = (st.get(t) or {}).get("verdict") or {}
        edge, prob = v.get("edge_pts"), v.get("probability")
        sig = edge is not None and prob is not None and (edge < P["keep_edge"] or prob < P["keep_min"])
        prev = (signals or {}).get(t) or {}
        confirmed = bool(sig and prev.get("signal") and prev.get("date") != today)
        i = out.setdefault(t, {"edge": edge, "probability": prob, "signal_now": sig, "must_exit": confirmed,
                               "signal": (f"sell signal at two rebuilds in a row (edge {edge:+.1f}, "
                                          f"probability {prob:.0%})" if confirmed else ""),
                               "long_term_soon": False, "swap_margin": float(P["swap_margin"]), "gain_%": 0.0})
        gain = float(h.get("gain_%") or 0.0)
        i["gain_%"] = min(i["gain_%"], gain) if i["gain_%"] else gain
        if h.get("account") == "individual" and gain > 0 and h.get("bought"):
            held_days = (pd.Timestamp(today) - pd.Timestamp(h["bought"])).days
            if held_days < 365:
                i["swap_margin"] = max(i["swap_margin"], P["swap_margin"] + P["tax_points_per_5pct"] * gain / 5)
                if 365 - held_days <= P["long_term_guard_days"]:
                    i["long_term_soon"] = True
        i["swap_margin"] = round(i["swap_margin"], 1)
    return out


def _edge(st, t):
    return (st.get(t) or {}).get("verdict", {}).get("edge_pts", -99)


def _factor(st, t):
    return (st.get(t) or {}).get("sensitivity", {}) and (st.get(t) or {}).get("sensitivity", {}).get("_dominant")


def check_rules(pick, team, held, corr, info=None):
    """Returns a list of rule violations (plain English) for Opus to fix."""
    v = []
    st = team["stocks"]
    info = info or {}
    names = [p["ticker"] for p in pick["portfolio"] if isinstance(p, dict)]
    eligible = [t for t, s in st.items() if (eligible_new(s) and t not in held)] + \
               [t for t in held if not (info.get(t) or {}).get("must_exit")]
    if len(set(names)) != len(names):
        v.append("duplicate tickers in portfolio")
    unknown = [t for t in names if t not in st and t not in held]
    if unknown:
        v.append(f"not reviewed by the committee: {unknown}")
    if len(names) > MAX_STOCKS:
        v.append(f"{len(names)} stocks; maximum is {MAX_STOCKS}")
    # the minimum applies only when 15+ names are eligible; with fewer, the PM may leave out weak or
    # flagged ones (the rest parks in SPY) instead of being forced to own every name that cleared the bar
    if len(eligible) >= MIN_STOCKS and len(names) < MIN_STOCKS:
        v.append(f"only {len(names)} stocks; own at least {MIN_STOCKS} (enough eligible names exist)")
    for t in names:
        if t in st and t not in held and not eligible_new(st[t]):
            vv = st[t]["verdict"]
            v.append(f"{t}: new buy with edge {vv.get('edge_pts', 0):+.1f} and probability {vv.get('probability', 0):.0%} "
                     f"(needs edge >= +{P['buy_edge']} and >= {P['buy_min']:.0%}, and 12+ months of trading history)")
    exits = {e["ticker"]: e for e in pick["exits"] if isinstance(e, dict)}
    for t in names:
        if t in held and (info.get(t) or {}).get("must_exit"):
            v.append(f"{t} must be exited: {info[t]['signal']}")
    dropped = [t for t in held if t not in names]
    for t in dropped:
        if t not in exits:
            v.append(f"{t} is held but neither kept nor listed as an exit")
    newcomers = sorted([_edge(st, t) for t in names if t in st and t not in held], reverse=True)
    for t in dropped:
        e, i = exits.get(t, {}), info.get(t) or {}
        if e.get("thesis_broken") or i.get("must_exit"):
            continue
        if i.get("long_term_soon"):
            v.append(f"{t} is a winner within {P['long_term_guard_days']} days of long-term tax status: keep it unless "
                     f"its thesis is broken")
            continue
        need = _edge(st, t) + i.get("swap_margin", P["swap_margin"])
        better = [c for c in newcomers if c >= need]
        if better:
            newcomers.remove(better[0])
        else:
            v.append(f"{t} (edge {_edge(st, t):+.1f}) exited without a broken thesis or a confirmed sell signal, and no "
                     f"newcomer has edge {need:+.1f}+ to replace it")
    drivers, factors = {}, {}
    for t in names:
        d = str(st.get(t, {}).get("verdict", {}).get("primary_driver", "")).strip().lower()
        if d:
            drivers.setdefault(d, []).append(t)
        f = _factor(st, t)
        if f:
            factors.setdefault(f, []).append(t)
    for d, ts in drivers.items():
        if len(ts) > MAX_PER_DRIVER:
            v.append(f"{len(ts)} stocks share driver '{d}' ({ts}); max {MAX_PER_DRIVER}")
    for f, ts in factors.items():
        if len(ts) > config.MAX_PER_FACTOR:
            v.append(f"{len(ts)} stocks have the same measured dominant macro factor '{f}' ({ts}); max {config.MAX_PER_FACTOR}")
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a in corr.index and b in corr.index and corr.loc[a, b] > CORR_LIMIT:
                v.append(f"{a} and {b} move together (60-day correlation {corr.loc[a, b]:.2f}); keep only one")
    return v


def auto_fix(pick, team, held, corr, info=None):
    """Last resort after retries: exit confirmed sells, restore wrongly exited holdings, drop ineligible
    buys, then drop violators (weakest edge first) until every rule holds."""
    st = team["stocks"]
    info = info or {}
    edge = lambda t: _edge(st, t)
    names = list(dict.fromkeys(p["ticker"] for p in pick["portfolio"] if p["ticker"] in st or p["ticker"] in held))
    names = [t for t in names if (t in held and not (info.get(t) or {}).get("must_exit")) or
             (t not in held and t in st and eligible_new(st[t]))]
    exits = {e["ticker"]: e for e in pick["exits"] if isinstance(e, dict)}
    for t in held:
        if (info.get(t) or {}).get("must_exit"):
            exits.setdefault(t, {"ticker": t, "reason": info[t]["signal"], "thesis_broken": False})
    newcomers = sorted([edge(t) for t in names if t not in held], reverse=True)
    for t in held:
        i = info.get(t) or {}
        if t in names or exits.get(t, {}).get("thesis_broken") or i.get("must_exit"):
            continue
        need = edge(t) + i.get("swap_margin", P["swap_margin"])
        better = [c for c in newcomers if c >= need] if not i.get("long_term_soon") else []
        if better:
            newcomers.remove(better[0])
        else:
            names.append(t)
            exits.pop(t, None)
    names = sorted(names, key=lambda t: (t in held, edge(t)), reverse=True)[:MAX_STOCKS]
    keep, drivers, factors = [], {}, {}
    for t in names:
        d = str(st.get(t, {}).get("verdict", {}).get("primary_driver", "")).lower()
        f = _factor(st, t)
        if d and drivers.get(d, 0) >= MAX_PER_DRIVER:
            continue
        if f and factors.get(f, 0) >= config.MAX_PER_FACTOR:
            continue
        if any(t in corr.index and k in corr.index and corr.loc[t, k] > CORR_LIMIT for k in keep):
            continue
        keep.append(t)
        drivers[d] = drivers.get(d, 0) + 1
        if f:
            factors[f] = factors.get(f, 0) + 1
    ex = [e for t, e in exits.items() if t not in keep]
    ex += [{"ticker": t, "reason": "removed by rule enforcement", "thesis_broken": False}
           for t in held if t not in keep and t not in exits]
    why = {p["ticker"]: p.get("why", "") for p in pick["portfolio"] if isinstance(p, dict)}
    return {"portfolio": [{"ticker": t, "why": why.get(t, "kept by rule enforcement (holding rules)")} for t in keep],
            "exits": ex, "summary": pick.get("summary", ""), "auto_fixed": True}


def select(session, team, holdings_view, macro, corr, drawdown_level=0, digest=None, info=None, feedback=""):
    held = {h["ticker"] for h in holdings_view if h["ticker"] != PARKING}
    packet = pm_packet(team, holdings_view, macro, drawdown_level, digest, info)
    pick, log = ask_pm(session, packet, feedback), []
    for attempt in range(2):
        v = check_rules(pick, team, held, corr, info)
        if not v:
            break
        log.append({"attempt": attempt + 1, "violations": v})
        pick = ask_pm(session, packet, (feedback + "\n\n" if feedback else "")
                      + "Your last answer broke these rules. Fix ALL of them:\n- " + "\n- ".join(v))
    v = check_rules(pick, team, held, corr, info)
    if v:
        log.append({"attempt": "final", "violations": v, "action": "auto-fixed"})
        pick = auto_fix(pick, team, held, corr, info)
    pick["rule_log"] = log
    return pick


# ==================================================================== sizing
def trim_weakest(w, names, excess, order):
    """Take `excess` weight out of `names`, weakest first: down to the position floor, then whole positions."""
    ranked = sorted([t for t in names if w.get(t, 0) > 0], key=order)
    for t in ranked:
        if excess <= 1e-9:
            break
        cut = min(excess, max(0.0, w[t] - POS_MIN))
        w[t] -= cut
        excess -= cut
    for t in ranked:                  # still over: drop whole positions (the freed weight goes elsewhere)
        if excess <= 1e-9:
            break
        excess -= w[t]
        w[t] = 0.0
    return w


def clusters(names, rcorr, thr=CLUSTER_CORR):
    """Groups of 2+ names whose market-adjusted returns move together (a hidden common bet even when
    their sector or driver labels differ). Linked when any pair in the group clears the threshold."""
    names = [t for t in names if rcorr is not None and t in rcorr.index]
    parent = {t: t for t in names}

    def root(t):
        while parent[t] != t:
            t = parent[t]
        return t
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if rcorr.loc[a, b] >= thr:
                parent[root(a)] = root(b)
    groups = {}
    for t in names:
        groups.setdefault(root(t), []).append(t)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


def cap_momentum_level(w, score, caps, order, notes, cap=None, step=0.25):
    """Keep the stocks' weighted-average momentum score at or below the cap: move weight from the
    highest-momentum names (weakest edge first) to lower-momentum names with room; with no room left,
    the moved weight goes to SPY. Records the level in the notes."""
    cap = config.MOMENTUM_MAX_LEVEL if cap is None else cap
    sc = {t: float(score.get(t, 0.5)) for t in w.index}
    level = lambda: float(sum(w[t] * sc[t] for t in w.index) / max(w.sum(), 1e-9))
    start = level()
    full = lambda t: any(t in g and float(w[g].sum()) >= c - 1e-9 for _, g, c in caps)
    for _ in range(2000):
        if level() <= cap + 1e-6:
            break
        hi = [t for t in w.index if w[t] > 0 and sc[t] > cap]
        if not hi:
            break
        src = sorted(hi, key=lambda t: (order(t), -sc[t]))[0]
        take = w[src] if w[src] - step < POS_MIN else step         # below the floor: drop it entirely
        w[src] -= take
        dst = [t for t in w.index if 0 < w[t] < POS_MAX - 1e-9 and sc[t] < level() and not full(t)]
        if dst:
            w[sorted(dst, key=lambda t: sc[t])[0]] += take          # else it parks in SPY
    notes.append(f"momentum level {level():.2f} (cap {cap:.2f}; was {start:.2f} before the cap)")
    return w


def themes_of(pick):
    """{theme: [tickers]} from the PM's tags (unknown or missing tags count as "other", which is not capped)."""
    out = {}
    for p in pick.get("portfolio") or []:
        if isinstance(p, dict) and p.get("ticker"):
            th = str(p.get("theme") or "other").strip().lower()
            out.setdefault(th if th in config.THEMES else "other", []).append(p["ticker"])
    return out


def size(tickers, vol, sector_of, ranges, drawdown_level=0, strength=None, mom_top=None, gains=None, groups=None,
         themes=None):
    """Weights (%) by steadiness: inverse volatility (times the judges' edge only when config.SIZE_BY_EDGE),
    POS_MIN-POS_MAX each, inside sector ceilings/floors, the momentum cap, the hidden-bet (cluster) cap and the theme cap.
    With `strength` (edge per ticker), every forced cut comes from the weakest names first (then the
    bigger loss among equals); without it, cuts are proportional. Returns (weights, notes)."""
    notes = []
    if not tickers:
        return {PARKING: 100.0}, ["no stocks selected: fully parked in SPY"]
    by_edge = bool(strength) and config.SIZE_BY_EDGE
    conv = (lambda t: min(max(float((strength or {}).get(t) or 0), 1.0), 15.0)) if by_edge else (lambda t: 1.0)
    inv = pd.Series({t: conv(t) / max(vol.get(t, 0.3), 0.05) for t in tickers})
    order = (lambda t: ((strength or {}).get(t, 0), (gains or {}).get(t, 0), -inv[t]))
    mom_level = mom_top if isinstance(mom_top, dict) else None      # {ticker: 0-1 momentum score}
    mom = set() if mom_level is not None else set(mom_top or []) & set(tickers)
    caps = [(s, [t for t in tickers if sector_of[t] == s], ranges.get(s, [0, 15])[1]) for s in set(sector_of[t] for t in tickers)]
    if mom:
        caps.append(("momentum", sorted(mom), config.MOMENTUM_CAP))
    for g in groups or []:
        g = [t for t in g if t in tickers]
        if len(g) >= 2:
            caps.append(("hidden bet " + "+".join(g), g, CLUSTER_CAP))
    for th, g in (themes or {}).items():
        g = [t for t in g if t in tickers]
        if th != "other" and len(g) >= 2:
            caps.append((f"theme {th}", g, config.THEME_CAP))
    w = (inv / inv.sum() * 100)
    for _ in range(200):
        w = w.clip(upper=POS_MAX)
        w[(w > 0) & (w < POS_MIN)] = POS_MIN
        changed = False
        for name, g, cap in caps:
            tot = float(w[g].sum())
            if tot > cap + 1e-9:
                changed = True
                if strength is None:
                    w[g] = w[g] * cap / tot
                else:
                    w = pd.Series(trim_weakest(w.to_dict(), g, tot - cap, order))
        total = float(w.sum())
        if abs(total - 100) < 0.01 and not changed:
            break
        if total > 100:
            w = w * 100 / total
            continue
        full = lambda t: any(t in g and float(w[g].sum()) >= cap - 1e-9 for _, g, cap in caps)
        room = [t for t in w.index if 0 < w[t] < POS_MAX - 1e-9 and not full(t)]
        if not room or abs(total - 100) < 0.01:
            break
        w[room] += (100 - total) * inv[room] / inv[room].sum()
    if mom_level is not None:
        w = cap_momentum_level(w, mom_level, caps, order, notes)
    for s, (lo, hi) in ranges.items():
        have = w[[t for t in w.index if sector_of[t] == s]].sum()
        if lo > 0 and have < lo - 0.5:
            notes.append(f"{s}: {have:.1f}% is below its {lo}% floor (not enough strong candidates)")
    if mom:
        notes.append(f"top-momentum names {float(w[sorted(mom)].sum()):.1f}% of stock weight (cap {config.MOMENTUM_CAP:.0f}%)")
    for name, g, cap in caps:
        if name.startswith("hidden bet") or name.startswith("theme "):
            notes.append(f"{name} move together: {float(w[g].sum()):.1f}% combined (cap {cap:.0f}%)")
    dropped = [t for t in tickers if w.get(t, 0) <= 0.01]
    if dropped:
        notes.append(f"dropped by caps (weakest first): {dropped}")
    weights = {t: round(float(x), 2) for t, x in w.items() if x > 0.01}
    if any(x < POS_MIN - 0.01 for x in weights.values()):
        notes.append(f"some positions sit below {POS_MIN:.0f}% because their sector ceiling is tight")
    if drawdown_level:
        cut = 0.5 if drawdown_level == 1 else 1.0
        stock_total = sum(weights.values())
        if strength is None or cut >= 1.0:
            weights = {t: round(x * (1 - cut), 2) for t, x in weights.items()}
        else:
            weights = {t: round(x, 2) for t, x in trim_weakest(dict(weights), list(weights), stock_total * cut, order).items()
                       if x > 0.01}
        notes.append(f"drawdown level {drawdown_level}: {int(cut * 100)}% of stock weight moved to SPY"
                     + (" (from the weakest names first)" if strength is not None and cut < 1 else ""))
    park = round(100 - sum(weights.values()), 2)
    if park > 0.05:
        weights[PARKING] = park
        notes.append(f"{park:.1f}% parked in SPY")
    return weights, notes


def factor_tilts(weights, bench):
    """Weighted average percentile (0-100) of the portfolio on momentum, value, quality and volatility,
    so drift toward any one style is visible."""
    b = bench if "ticker" not in getattr(bench, "columns", []) else bench.set_index("ticker")
    names = [t for t in weights if t != PARKING and t in b.index]
    tot = sum(weights[t] for t in names)
    if not tot:
        return {}
    vol_pct = b["vol_60d"].rank(pct=True) if "vol_60d" in b else None
    out = {}
    for label, col in (("momentum", "s_momentum"), ("value", "s_value"), ("quality", "s_quality")):
        if col in b:
            out[label] = round(float(sum(weights[t] * (b.loc[t, col] if b.loc[t, col] == b.loc[t, col] else 0.5)
                                         for t in names) / tot * 100))
    if vol_pct is not None:
        out["volatility"] = round(float(sum(weights[t] * vol_pct.get(t, 0.5) for t in names) / tot * 100))
    return out


# ==================================================================== trades + placement
def build_trades(weights, book, prices, meta, exits):
    """Target weights -> trades per account. Existing positions stay in their account; new money
    goes to Individual for the steadiest names (high conviction, low volatility) and to the IRA
    for the rest, splitting a buy across accounts only when needed."""
    pos = positions_df(book, prices)
    cash = {a: book["accounts"][a]["cash"] for a in ACCOUNTS}
    total = sum(cash.values()) + float(pos.value.sum())
    exit_reason = {e["ticker"]: e.get("reason", "") for e in exits}
    trades = []

    def add(action, acct, t, amount, reason):
        p = prices.get(t) or 0
        trades.append({"action": action, "account": acct, "ticker": t, "amount": amount, "ref_price": p,
                       "limit": round(p * (1.005 if action == "BUY" else 0.995), 2), "reason": reason, **meta.get(t, {})})

    # sells: exits and trims
    for _, p in pos.iterrows():
        tgt = weights.get(p.ticker, 0) / 100 * total
        held_total = float(pos[pos.ticker == p.ticker].value.sum())
        if p.ticker not in weights:
            add("SELL", p.account, p.ticker, "all", exit_reason.get(p.ticker, "no longer in target portfolio"))
            cash[p.account] += p.value
        elif held_total - tgt > max(BAND / 100 * total, MIN_TRADE):
            cut = (held_total - tgt) * p.value / held_total
            add("SELL", p.account, p.ticker, round(cut, 2), "trim to target weight")
            cash[p.account] += cut
    # buys: new names and top-ups
    need = []
    for t, wt in weights.items():
        tgt = wt / 100 * total
        have = float(pos[pos.ticker == t].value.sum())
        gap = tgt - have
        if have == 0 and gap >= MIN_TRADE or have > 0 and gap > max(BAND / 100 * total, MIN_TRADE):
            home = pos[pos.ticker == t].account.iloc[0] if have > 0 else None
            stab = meta.get(t, {}).get("conviction", 3) - 5 * meta.get(t, {}).get("vol", 0.3)
            need.append((t, gap, home, stab))
    for t, gap, home, _ in sorted(need, key=lambda x: (x[2] is None, -x[3])):
        order = [home] if home else ["individual", "ira"]
        order += [a for a in ACCOUNTS if a not in order]
        left = gap
        for a in order:
            amt = min(left, cash[a])
            if amt >= MIN_TRADE:
                add("BUY", a, t, round(amt, 2), "top up to target weight" if home else "new position")
                cash[a] -= amt
                left -= amt
            if left < MIN_TRADE:
                break
    for i, t in enumerate(trades, 1):
        t["id"] = f"T{i:02d}"
    return trades, total
