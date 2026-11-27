"""Offline tests: book (trades, wash sales, checklist), PM rules and sizing, and a full two-cycle rebuild."""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ[k] = "test"
for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.pop(k, None)

from pipeline import book, config, integrity, llm, pm, rebuild, util  # noqa: E402

pm.MIN_STOCKS, pm.MAX_STOCKS = 8, 12      # these fixtures are a 10-name book; the live 15-20 limits are checked in test_themes

config.PAPER_MODE = False       # these tests exercise the live flow; paper mode has its own test

N = types.SimpleNamespace
llm.time.sleep = lambda s: None
SECT = list(config.SECTORS)


# ---------------------------------------------------------------- book
def fresh_book():
    util.write_json(util.state_path("holdings.json"), {})
    p = util.state_path("trades.csv")
    if p.exists():
        p.unlink()


def test_apply_trade_and_wash_sales():
    fresh_book()
    b = book.load_book()
    assert b["accounts"]["individual"]["cash"] == 5000
    book.apply_trade(b, {"account": "individual", "action": "BUY", "ticker": "AAA", "amount": 1000, "thesis": "t"}, 50, "2026-09-01")
    book.apply_trade(b, {"account": "individual", "action": "SELL", "ticker": "AAA", "amount": "all"}, 40, "2026-09-10")
    log = book.trade_log()
    assert log.iloc[-1].realized_gain == -200 and b["accounts"]["individual"]["cash"] == 4800 and not b["positions"]
    trades = [{"action": "BUY", "account": "ira", "ticker": "AAA", "amount": 500},
              {"action": "BUY", "account": "individual", "ticker": "AAA", "amount": 500},
              {"action": "BUY", "account": "ira", "ticker": "BBB", "amount": 500}]
    book.wash_check(trades, b, {}, today="2026-09-20")
    assert [t["wash"] for t in trades] == ["blocked", "warn", "ok"]
    # loss sale in Individual while buying the same stock in the IRA this cycle -> blocked
    book.apply_trade(b, {"account": "individual", "action": "BUY", "ticker": "CCC", "amount": 500}, 100, "2026-06-01")
    t2 = [{"action": "SELL", "account": "individual", "ticker": "CCC", "amount": "all"},
          {"action": "BUY", "account": "ira", "ticker": "CCC", "amount": 300}]
    book.wash_check(t2, b, {"CCC": 80}, today="2026-09-20")
    assert t2[0]["wash"] == "blocked"


def test_checklist_roundtrip():
    plan = {"date": "2026-09-19", "trades": [
        {"id": "T01", "action": "SELL", "ticker": "AAA", "account": "individual", "amount": "all", "limit": 49.75, "status": "approved"},
        {"id": "T02", "action": "BUY", "ticker": "BBB", "account": "ira", "amount": 500.0, "limit": 20.1, "status": "flagged"}]}
    body = book.checklist_body(plan)
    assert "Ready to place" in body and "Flagged" in body
    body = body.replace("- [ ] T01", "- [x] T01").replace("limit $49.75 · fill ", "limit $49.75 · fill @49.60")
    got = book.parse_checklist(body)
    assert got["T01"] == (True, 49.6) and got["T02"] == (False, None)


# ---------------------------------------------------------------- PM rules + sizing
def test_size_bounds_ceilings_drawdown():
    names = [f"X{i}" for i in range(16)]
    vol = {t: 0.15 + 0.03 * i for i, t in enumerate(names)}
    sector = {t: SECT[i % 4] for i, t in enumerate(names)}            # 4 sectors, 4 names each
    ranges = {s: [0, 15] for s in SECT}
    ranges[SECT[0]] = [12, 30]
    w, notes = pm.size(names, vol, sector, ranges)
    stocks = {k: v for k, v in w.items() if k != pm.PARKING}
    assert all(v <= pm.POS_MAX + 0.01 for v in stocks.values())
    for s in SECT[1:4]:
        assert sum(v for k, v in stocks.items() if sector[k] == s) <= 15.05
    assert abs(sum(w.values()) - 100) < 0.05 and w.get(pm.PARKING, 0) > 0   # caps force parking
    w2, n2 = pm.size(names, vol, sector, ranges, drawdown_level=1)
    assert w2[pm.PARKING] > 50 and any("drawdown" in x for x in n2)


def verdict_for(edge, t, i, base=0.48):
    p = round(base + edge / 100, 4)
    return {"probability": p, "base_p": base, "edge_pts": float(edge), "conviction": pm_label(edge),
            "thesis": f"thesis {t}", "key_risk": "r", "exit_condition": "guidance cut",
            "primary_driver": f"driver{i % 8}", "winner": "bull"}


def pm_label(edge):
    from pipeline.team import label
    return label(edge)


def team_results(n=24):
    stocks = {}
    for i in range(n):
        t = f"K{i:02d}"
        stocks[t] = {"name": t, "sector": SECT[i % len(SECT)], "incumbent": False, "composite": 0.8 - i * 0.01,
                     "vol_60d": 0.2 + (i % 5) * 0.05, "price": 50.0, "news": {},
                     "verdict": verdict_for(10 if i < 4 else 6 if i < 12 else 3.5 if i < 20 else -1, t, i),
                     "features": {"m": 5 if i % 3 == 0 else 3, "history_days": 4000},
                     "dossier": [{"id": "D1", "kind": "catalyst", "text": "earnings 2026-10-02"}],
                     "debate": {"bull_open": {"summary": "b"}, "bear_open": {"summary": "x"}}}
    return {"date": "2026-09-19", "stocks": stocks}


def test_rules_incumbent_and_driver():
    tr = team_results()
    tr["stocks"]["K05"]["incumbent"] = True
    corr = pd.DataFrame(np.eye(3), index=["K00", "K01", "K02"], columns=["K00", "K01", "K02"])
    corr.loc["K00", "K01"] = corr.loc["K01", "K00"] = 0.9
    pick = {"portfolio": [{"ticker": t} for t in ["K00", "K01", "K20"] + [f"K{i:02d}" for i in range(6, 19)]],
            "exits": [{"ticker": "K05", "reason": "meh", "thesis_broken": False}]}
    v = pm.check_rules(pick, tr, {"K05"}, corr)
    text = " | ".join(v)
    assert "K20: new buy with edge -1.0" in text and "move together" in text
    assert "K05 (edge" not in text                            # K00 (edge 10) >= K05 (6) + 4: a valid swap
    tr["stocks"]["K05"]["verdict"] = verdict_for(10, "K05", 5)
    assert any("K05 (edge +10.0) exited" in x for x in pm.check_rules(pick, tr, {"K05"}, corr))
    tr["stocks"]["K07"]["features"]["history_days"] = 100     # a recent IPO can't be a new buy
    assert any(x.startswith("K07: new buy") for x in pm.check_rules(pick, tr, {"K05"}, corr))


def test_holding_rules_signals_tax_and_guard():
    tr = team_results()
    for t in ("K03", "K04", "K05", "K06"):
        tr["stocks"][t]["incumbent"] = True
    tr["stocks"]["K03"]["verdict"] = verdict_for(-4, "K03", 3)        # sell signal
    tr["stocks"]["K04"]["verdict"] = verdict_for(-4, "K04", 4)        # sell signal, first time
    hv = [{"ticker": "K03", "account": "ira", "gain_%": -5.0, "bought": "2026-03-01"},
          {"ticker": "K04", "account": "ira", "gain_%": 2.0, "bought": "2026-03-01"},
          {"ticker": "K05", "account": "individual", "gain_%": 20.0, "bought": "2025-09-25"},   # 6 days from long-term
          {"ticker": "K06", "account": "individual", "gain_%": 15.0, "bought": "2026-05-01"}]
    signals = {"K03": {"date": "2026-09-05", "signal": True}, "K04": {"date": "2026-09-05", "signal": False}}
    info = pm.holding_info(hv, tr, signals, "2026-09-19")
    assert info["K03"]["must_exit"] and not info["K04"]["must_exit"] and info["K04"]["signal_now"]
    assert info["K05"]["long_term_soon"] and info["K06"]["swap_margin"] == 7.0   # 4 + 15%/5
    held = {"K03", "K04", "K05", "K06"}
    corr = pd.DataFrame()
    keep_all = {"portfolio": [{"ticker": t} for t in sorted(held) + [f"K{i:02d}" for i in range(7, 18)]], "exits": []}
    v = pm.check_rules(keep_all, tr, held, corr, info)
    assert any(x.startswith("K03 must be exited") for x in v)
    drop = {"portfolio": [{"ticker": t} for t in ["K00", "K01", "K02"] + [f"K{i:02d}" for i in range(7, 19)]],
            "exits": [{"ticker": t, "reason": "swap", "thesis_broken": False} for t in held]}
    v = " | ".join(pm.check_rules(drop, tr, held, corr, info))
    assert "K05 is a winner within 30 days" in v and "K03" not in v
    # K04's edge -4 + margin 4 = 0: any positive-edge newcomer may replace it; K06 needs edge +13
    assert "K04 (edge" not in v and "K06 (edge +6.0)" in v
    fixed = pm.auto_fix(keep_all, tr, held, corr, info)
    names = [p["ticker"] for p in fixed["portfolio"]]
    assert "K03" not in names and "K05" in names and any(e["ticker"] == "K03" for e in fixed["exits"])


def test_size_trims_weakest_first_and_caps_momentum():
    names = [f"W{i}" for i in range(16)]
    sector = {t: ("Technology" if i < 8 else "Energy") for i, t in enumerate(names)}
    edge = {t: float(i) for i, t in enumerate(names)}
    w, notes = pm.size(names, {t: 0.3 for t in names}, sector, {"Technology": [0, 20], "Energy": [0, 60]},
                       0, strength=edge, mom_top=names[8:])
    assert "W0" not in w and "W7" in w                                  # the tech ceiling drops the weakest
    assert sum(w[t] for t in names[8:] if t in w) <= config.MOMENTUM_CAP + 0.01
    w2, _ = pm.size(names, {t: 0.3 for t in names}, sector, {"Technology": [0, 60], "Energy": [0, 60]}, 1, strength=edge)
    assert w2["W15"] >= w2.get("W0", 0) and abs(sum(v for k, v in w2.items() if k != "SPY") - 50) < 0.1


# ---------------------------------------------------------------- full rebuild, two cycles
PRICES = {f"K{i:02d}": 50.0 for i in range(24)}
PRICES["SPY"] = 600.0
CORR = pd.DataFrame(np.eye(24), index=[f"K{i:02d}" for i in range(24)], columns=[f"K{i:02d}" for i in range(24)])
CORR.loc["K00", "K01"] = CORR.loc["K01", "K00"] = 0.95


class FakeClaude:
    def __init__(self):
        self.messages = self
        self.pm_calls = 0
        self.pm_script = []

    def create(self, **p):
        sysmsg = p["system"][0]["text"]
        if sysmsg.startswith("You are the portfolio manager"):
            self.pm_calls += 1
            out = self.pm_script.pop(0) if self.pm_script else self.pm_script_default
        elif sysmsg.startswith("You are the risk reviewer"):
            packet = p["messages"][0]["content"][0]["text"].split("REVIEW PACKET:\n", 1)[1]
            assert "## MACRO VIEW" in packet and "## TARGET PORTFOLIO" in packet and "## TRADES" in packet
            rows = [l.split(" | ") for l in packet.splitlines() if l.startswith("T")]
            flag_id = next((r[0] for r in rows if len(r) > 3 and r[1] == "BUY" and r[2] == "K07"), None)
            out = {"overall": "FLAG", "summary": "mostly fine", "portfolio_issues": ["two holdings report the same week"],
                   "trades": {flag_id: {"status": "FLAG", "issue": "stretched valuation", "recommendation": "consider half size"}} if flag_id else {}}
        else:
            raise AssertionError(sysmsg[:50])
        return N(content=[N(type="text", text="```json\n" + json.dumps(out) + "\n```", citations=None)], stop_reason="end_turn",
                 usage=N(input_tokens=8000, output_tokens=1500, cache_creation_input_tokens=0, cache_read_input_tokens=0, server_tool_use=None))


def fake_team_main(tr):
    def f(session, folder, **kw):
        util.write_json(util.state_path("team_results.json"), tr)
    return f


def test_two_cycle_rebuild():
    fresh_book()
    ranges = {s: [0, 15] for s in SECT}
    ranges["Energy"] = [12, 30]
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-09-18", "regime": "Reflation", "tilts": {s: 0 for s in SECT},
                                                         "weight_ranges_%": ranges, "key_risks": []})
    pd.DataFrame({"ticker": list(PRICES), "vol_60d": 0.25, "sector": "Energy"}).to_csv(util.state_path("bench.csv"), index=False)
    rebuild.market_prices = lambda tickers: (PRICES, CORR)
    tr = team_results()
    rebuild.team.main = fake_team_main(tr)
    fc = FakeClaude()
    bad = {"portfolio": [{"ticker": f"K{i:02d}", "why": "w"} for i in list(range(0, 11)) + [21]], "exits": [], "summary": "s"}
    good = {"portfolio": [{"ticker": f"K{i:02d}", "why": "w"} for i in [0] + list(range(2, 12))], "exits": [], "summary": "good"}
    fc.pm_script = [bad, good]
    fc.pm_script_default = good

    s = llm.Session("rebuild", anthropic_client=fc)
    folder = util.run_dir("rebuild")
    out = rebuild.main(s, folder, force=True)
    plan = util.read_json(util.state_path("pending_plan.json"))
    full = util.read_json(folder / "plan.json")
    assert out["status"] == "FLAG" and fc.pm_calls == 3            # rule retry + one revision for the flags
    assert full["pick"]["rule_log"][0]["violations"]                 # first answer's violations were sent back
    assert full["all_trades"][0]["id"].startswith("T")
    w = plan["target"]
    assert "K01" not in w and "K21" not in w and abs(sum(w.values()) - 100) < 0.1
    buys = [t for t in plan["trades"] if t["action"] == "BUY" and t["ticker"] != "SPY"]
    assert all(t["action"] == "BUY" for t in plan["trades"])
    assert {t["account"] for t in buys} == {"individual", "ira"}
    k07 = next(t for t in full["all_trades"] if t["ticker"] == "K07")
    assert k07["status"] == "flagged"
    parking = [t for t in plan["trades"] if t["ticker"] == "SPY" and "park money" in t["reason"]]
    assert parking and abs(parking[0]["amount"] - k07["amount"]) < 1        # flagged buy's money parks in SPY
    assert sum(t["amount"] for t in plan["trades"] if t["account"] == "individual" and t["status"] == "approved") <= 5000.01
    assert util.state_path("checklist.md").exists() and list(folder.glob("*.eml"))
    th = (folder / "theses.md").read_text()
    assert "## K00" in th and "Sell if:" in th and "Thesis:" in th
    rep = (folder / "report.md").read_text()
    assert "Target portfolio" in rep and "Rule enforcement" in rep

    # you place every approved trade (one at a custom fill), skip the flagged one
    body = util.state_path("checklist.md").read_text()
    lines = []
    for line in body.splitlines():
        if line.startswith("- [ ]") and "Flagged" not in body.split(line)[0].splitlines()[-1] and "K07" not in line:
            line = line.replace("- [ ]", "- [x]") + ("@49.00" if "K00" in line else "")
        lines.append(line)
    util.state_path("checklist.md").write_text("\n".join(lines))

    # cycle 2: PM exits K02 claiming no broken thesis and no better replacement -> rule loop -> auto-fix keeps it
    tr2 = team_results()
    tr2["stocks"]["K02"]["incumbent"] = True
    rebuild.team.main = fake_team_main(tr2)
    exit_no_reason = {"portfolio": [{"ticker": f"K{i:02d}", "why": "w"} for i in [0] + list(range(3, 12))],
                      "exits": [{"ticker": "K02", "reason": "bored", "thesis_broken": False}], "summary": "s2"}
    fc.pm_script = [exit_no_reason, exit_no_reason, exit_no_reason]
    s2 = llm.Session("rebuild", anthropic_client=fc)
    folder2 = util.run_dir("rebuild2")
    rebuild.main(s2, folder2, force=True)
    b = book.load_book()
    held = {p["ticker"] for p in b["positions"]}
    assert "K00" in held and "K07" not in held                          # placed vs skipped trades recorded
    k00 = next(p for p in b["positions"] if p["ticker"] == "K00")
    assert abs(k00["cost_basis"] / k00["shares"] - 49.0) < 1e-6 and k00["thesis"] == "thesis K00"
    assert util.state_path("holding_signals.json").exists()
    sl = pd.read_csv(util.state_path("sell_ledger.csv"))
    assert set(sl.action) <= {"sold", "kept"} and len(sl) and util.state_path("critic_ledger.csv").exists()
    plan2 = util.read_json(folder2 / "plan.json")
    assert "K02" in plan2["target"]                                      # incumbent rule enforced
    assert any(x.get("action") == "auto-fixed" for x in plan2["pick"]["rule_log"])   # (kept in the log after the revision)
    print(f"    cycle costs ${s.spent:.2f} and ${s2.spent:.2f} (simulated)")


# ---------------------------------------------------------------- tax lots, idempotency, integrity, paper
def test_fifo_lots_and_terms():
    fresh_book()
    b = book.load_book()
    book.apply_trade(b, {"account": "individual", "action": "BUY", "ticker": "LOT", "amount": 1000}, 10, "2025-01-02")  # 100 sh
    book.apply_trade(b, {"account": "individual", "action": "BUY", "ticker": "LOT", "amount": 1000}, 20, "2026-06-01")  # 50 sh
    row = book.apply_trade(b, {"account": "individual", "action": "SELL", "ticker": "LOT", "amount": 2400}, 20, "2026-09-01")  # 120 sh
    log = book.trade_log()
    sells = log[log.action == "SELL"]
    assert len(sells) == 2 and list(sells.term) == ["long", "short"]          # oldest lot first
    assert abs(sells.iloc[0].realized_gain - 1000) < 1e-6 and abs(sells.iloc[1].realized_gain - 0) < 1e-6
    assert abs(row["realized_gain"] - 1000) < 1e-6
    pos = b["positions"][0]
    assert abs(pos["shares"] - 30) < 1e-6 and abs(pos["cost_basis"] - 600) < 1e-6 and pos["buy_date"] == "2026-06-01"


def test_reconcile_is_idempotent():
    fresh_book()
    plan = {"date": "2026-09-19", "trade_date": "2026-09-21", "checklist": {"number": None}, "trades": [
        {"id": "T01", "action": "BUY", "ticker": "AAA", "account": "individual", "amount": 1000.0, "limit": 50.2,
         "ref_price": 50.0, "status": "approved"}]}
    util.write_json(util.state_path("pending_plan.json"), plan)
    util.state_path("checklist.md").write_text(book.checklist_body(plan).replace("- [ ]", "- [x]"))
    assert "AAA" in book.reconcile({})[0]
    again = dict(plan, reconciled=None)                                       # e.g. a crash before the plan was marked
    util.write_json(util.state_path("pending_plan.json"), again)
    out = book.reconcile({})
    assert "already recorded" in out[0]
    assert len(book.trade_log()) == 1 and abs(book.load_book()["accounts"]["individual"]["cash"] - 4000) < 1e-6


def test_integrity_gate():
    fresh_book()
    b = book.load_book()
    book.apply_trade(b, {"account": "ira", "action": "BUY", "ticker": "OLD", "amount": 500}, 50, "2026-09-01")
    sect = {"A": "Energy", "B": "Energy"}
    good = [{"id": "T01", "action": "BUY", "account": "individual", "ticker": "A", "amount": 400.0, "ref_price": 10,
             "limit": 10.05, "status": "approved"},
            {"id": "T02", "action": "SELL", "account": "ira", "ticker": "OLD", "amount": "all", "est_value": 500,
             "ref_price": 50, "limit": 49.75, "status": "approved"}]
    for t in good:
        t["key"] = integrity.trade_key("2026-09-19", t)
    w = {"A": 10.0, "B": 8.0, "SPY": 82.0}
    assert integrity.check({"trades": good}, b, w, sect, {"Energy": [0, 30]}) == []
    bad = [dict(good[0], amount=float("nan")), dict(good[1], ticker="NOPE"), dict(good[0], id="T03"),
           {"id": "T04", "action": "BUY", "account": "ira", "ticker": "B", "amount": 9e9, "ref_price": 5, "limit": 5,
            "status": "approved", "key": "k"}]
    probs = integrity.check({"trades": bad}, b, {"A": 40.0, "SPY": 50.0}, sect, {"Energy": [0, 15]})
    text = " | ".join(probs)
    for needle in ("NaN", "invalid amount", "holds none", "duplicate", "sum to 90", "above the 10.0% position limit",
                   "exceeds the macro ceiling", "exceed cash", "duplicate idempotency key"):
        assert needle in text, (needle, text)
    assert integrity.check(None, b, w, sect, {})[0].startswith("integrity check crashed")   # fails closed


def test_paper_mode_rebuild_records_without_checklist():
    fresh_book()
    for f in ("pending_plan.json", "checklist.md", "rebuild_history.json"):
        if util.state_path(f).exists():
            util.state_path(f).unlink()
    ranges = {s: [0, 15] for s in SECT}
    ranges["Energy"] = [12, 30]
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-09-18", "regime": "R", "tilts": {s: 0 for s in SECT},
                                                         "weight_ranges_%": ranges, "key_risks": []})
    pd.DataFrame({"ticker": list(PRICES), "vol_60d": 0.25, "sector": "Energy"}).to_csv(util.state_path("bench.csv"), index=False)
    rebuild.market_prices = lambda tickers: (PRICES, CORR)
    rebuild.team.main = fake_team_main(team_results())
    fc = FakeClaude()
    fc.pm_script_default = {"portfolio": [{"ticker": f"K{i:02d}", "why": "w"} for i in [0] + list(range(2, 12))],
                            "exits": [], "summary": "good"}
    config.PAPER_MODE = True
    try:
        folder = util.run_dir("rebuild_paper")
        rebuild.main(llm.Session("rebuild", anthropic_client=fc), folder, force=True)
    finally:
        config.PAPER_MODE = False
    plan = util.read_json(util.state_path("pending_plan.json"))
    assert plan["paper"] and not util.state_path("checklist.md").exists()
    assert plan["versions"]["code_version"] and all(t.get("key") for t in plan["trades"])
    mail = next(folder.glob("*.eml")).read_text()
    assert "PAPER" in mail
    book.reconcile({})
    b = book.load_book()
    approved = {t["ticker"] for t in plan["trades"] if t["status"] == "approved"}
    assert approved and approved <= {p["ticker"] for p in b["positions"]}
    # still flagged after the PM's one revision: in paper mode it's placed, with the concern on record
    full = util.read_json(folder / "plan.json")
    k07 = next(t for t in full["all_trades"] if t["ticker"] == "K07")
    assert k07["status"] == "approved" and "placed (paper) after the PM's revision" in k07["recommendation"]
    assert any(p["ticker"] == "K07" for p in b["positions"])
    hist = util.read_json(util.state_path("rebuild_history.json"))
    assert hist[-1]["equal_weight"] and hist[-1]["no_macro"] and hist[-1]["paper"]


def test_trade_day_same_morning_when_finished_overnight():
    from datetime import datetime
    assert rebuild.trade_day(datetime(2026, 9, 28, 1, 24)).isoformat() == "2026-09-28"    # Mon 1:24 am -> Monday
    assert rebuild.trade_day(datetime(2026, 9, 28, 11, 0)).isoformat() == "2026-09-29"    # after the open -> Tuesday
    assert rebuild.trade_day(datetime(2026, 9, 26, 20, 0)).isoformat() == "2026-09-28"    # Saturday -> Monday
    assert rebuild.trade_day(datetime(2026, 10, 2, 16, 0)).isoformat() == "2026-10-05"    # Friday evening -> Monday


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
