"""Offline tests: tracking (portfolios, attribution, scorecards, drawdown, email) and the daily watch."""
import json
import os
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = tempfile.mkdtemp()
os.environ["PIPELINE_ROOT"] = ROOT
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY"):
    os.environ[k] = "test"
for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.pop(k, None)

from pipeline import book, config, embed, llm, track, util, watch  # noqa: E402
config.PAPER_MODE = False       # live checklist flow

embed.embed = lambda texts, post=None: None      # no embedding service in tests

N = types.SimpleNamespace
llm.time.sleep = lambda s: None
import time as _t  # noqa: E402
_t.sleep = lambda s: None

TODAY = track.TODAY
DAYS = pd.bdate_range(end=pd.Timestamp(TODAY), periods=160)
D0, D1 = DAYS[20].date().isoformat(), DAYS[30].date().isoformat()     # two rebuild trade dates


def make_prices():
    rng = np.random.default_rng(7)
    cols = ["AAA", "BBB", "CCC", "SPY", "SPTM"] + list(config.SECTORS.values())
    px = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(DAYS)))) for c in cols}, index=DAYS)
    px["SPY"] = 100 * np.exp(np.linspace(0, 0.20, len(DAYS)))            # market rallies 20%
    px["AAA"] = 100 * np.exp(np.linspace(0, -0.15, len(DAYS)))           # our holding falls 15% -> drawdown rule
    return px


def setup_track_state(px):
    util.write_json(util.state_path("rebuild_history.json"), [
        {"date": D0, "trade_date": D0, "target": {"AAA": 50, "BBB": 40, "SPY": 10}, "control": {"CCC": 100},
         "sectors": {"AAA": "Technology", "BBB": "Energy"}},
        {"date": D1, "trade_date": D1, "target": {"AAA": 60, "BBB": 40}, "control": {"CCC": 100},
         "sectors": {"AAA": "Technology", "BBB": "Energy"}}])
    a0, b0 = px.loc[pd.Timestamp(D0), "AAA"], px.loc[pd.Timestamp(D0), "BBB"]
    rows = [{"date": D0, "account": "individual", "ticker": "AAA", "action": "BUY", "price": a0, "shares": 5000 / a0, "amount": 5000,
             "realized_gain": 0, "holding_days": ""},
            {"date": D0, "account": "ira", "ticker": "BBB", "action": "BUY", "price": b0, "shares": 4000 / b0, "amount": 4000,
             "realized_gain": 0, "holding_days": ""}]
    pd.DataFrame(rows).to_csv(util.state_path("trades.csv"), index=False)
    util.write_json(util.state_path("holdings.json"), {"accounts": {"individual": {"cash": 0.0}, "ira": {"cash": 1000.0}},
        "positions": [{"ticker": "AAA", "account": "individual", "shares": 5000 / a0, "cost_basis": 5000, "buy_date": D0,
                       "thesis": "AI demand", "exit_condition": "loses the XYZ contract"},
                      {"ticker": "BBB", "account": "ira", "shares": 4000 / b0, "cost_basis": 4000, "buy_date": D0,
                       "thesis": "oil", "exit_condition": "guidance cut"}]})
    pd.DataFrame([{"date": D0, "stage": "macro", "cost": 0.6}, {"date": D1, "stage": "rebuild", "cost": 1.4}]).to_csv(
        util.state_path("cost_log.csv"), index=False)
    pd.DataFrame([{"date": D0, "ticker": "AAA", "conviction": 5, "winner": "bull", "composite": 0.9, "in_portfolio": True},
                  {"date": D0, "ticker": "BBB", "conviction": 3, "winner": "bear", "composite": 0.7, "in_portfolio": True}]).to_csv(
        util.state_path("verdict_history.csv"), index=False)
    util.write_json(util.state_path("signal_history.json"), {D0: {"momentum": {"top": ["BBB"], "bottom": ["AAA"]}}})
    pd.DataFrame({"ticker": ["AAA", "BBB"], "sector": ["Technology", "Energy"], "index": ["S&P 500", "S&P 600"]}).to_csv(
        util.state_path("bench.csv"), index=False)
    rh = Path(ROOT) / "imports" / "robinhood"
    rh.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Activity Date": [D0], "Instrument": ["AAA"], "Trans Code": ["Buy"], "Quantity": [1.0]}).to_csv(
        rh / "individual_activity.csv", index=False)


def test_tracking():
    px = make_prices()
    track.closes = lambda names, start: px
    setup_track_state(px)
    folder = util.run_dir("track")
    track.main(None, folder, monthly=True)
    perf = util.read_json(util.state_path("performance.json"))
    m = perf["metrics"]
    for k in ("AI actual", "AI as recommended", "Screen-only control", "SPY", "SPTM (S&P 1500)", "AI actual (after AI costs)"):
        assert m[k] and "since_inception_%" in m[k], k
    assert m["SPY"]["since_inception_%"] > 10
    assert m["AI actual (after AI costs)"]["value"] < m["AI actual"]["value"]
    a = perf["attribution"][0]
    assert abs(a["portfolio_%"] - (a["allocation_%"] + a["selection_%"] + a["spy_%"])) < 0.05
    assert any(k.startswith("selection_S&P") for k in a)
    sc = perf["scorecards"]
    assert sc["by_conviction"]["5"]["n"] == 1 and "not yet" in sc["conviction_weighting"]
    assert sc["signal_spread_1wk_%"]["momentum"]["weeks"] == 1
    assert perf["drawdown"]["level"] >= 1                                   # AI badly trails SPY
    assert any("Robinhood 1.0000 shares" in n for n in perf["robinhood_differences"])
    assert (folder / "performance.png").exists()
    emails = [p.name for p in folder.glob("*.eml")]
    assert any("Drawdown" in e for e in emails) and any("Monthly" in e for e in emails)
    assert "since inception" in track.status_line()
    # running again without a level change sends no new drawdown alert
    for e in folder.glob("*.eml"):
        e.unlink()
    track.main(None, folder, monthly=False)
    assert not list(folder.glob("*.eml"))


def test_nav_from_schedule_math():
    idx = pd.bdate_range("2026-01-05", periods=5)
    px = pd.DataFrame({"X": [10, 11, 12, 12, 12], "Y": [20, 20, 20, 10, 10]}, index=idx)
    nav = track.nav_from_schedule([("2026-01-05", {"X": 50, "Y": 50}), ("2026-01-08", {"X": 100})], px, 1000)
    assert abs(nav.iloc[2] - (50 * 12 + 25 * 20)) < 1e-9                   # 50 sh X, 25 sh Y
    v3 = 50 * 12 + 25 * 10
    assert abs(nav.iloc[3] - v3) < 1e-9 and abs(nav.iloc[4] - v3) < 1e-9     # rebalanced into X on day 4


# ---------------------------------------------------------------- watch
def test_watch_alerts_and_quiet():
    util.write_json(util.state_path("holdings.json"), {"accounts": {"individual": {"cash": 0}, "ira": {"cash": 0}}, "positions": [
        {"ticker": "AAA", "account": "individual", "shares": 10, "cost_basis": 1000, "buy_date": "2026-09-01",
         "thesis": "AI demand", "exit_condition": "loses the XYZ contract"},
        {"ticker": "BBB", "account": "ira", "shares": 10, "cost_basis": 1000, "buy_date": "2026-09-01",
         "thesis": "oil", "exit_condition": "guidance cut"}]})
    idx = pd.bdate_range(end=pd.Timestamp(TODAY), periods=40)
    n = len(idx)
    close = pd.DataFrame({"AAA": np.r_[np.full(n - 1, 100.0), 85.0], "BBB": np.linspace(50, 51, n), "SPY": 600.0, "^VIX": 18.0}, index=idx)
    volume = pd.DataFrame({"AAA": np.r_[np.full(n - 1, 1e6), 5e6], "BBB": 1e6, "SPY": 1e8, "^VIX": 0}, index=idx)
    watch.market_data = lambda t: (close, volume)

    fetched = []

    def get(url, params=None, timeout=None, headers=None):
        if params is None:                                    # article text, for the thesis review only
            fetched.append(url)
            return N(status_code=200, text="<html><p>" + "Rival wins the XYZ contract from AAA after a review. " * 20 + "</p></html>")
        items = [{"headline": "AAA loses XYZ contract to rival", "source": "Reuters", "url": "https://news.example.com/aaa",
                  "summary": "The customer moved the contract to a rival."}] if params["symbol"] == "AAA" else []
        return N(status_code=200, json=lambda: items)

    def gemini_post(url, json=None, timeout=None, headers=None):
        import json as js
        text = json["contents"][0]["parts"][0]["text"]
        assert text.startswith("INSTRUCTIONS:\nYou monitor stock holdings")   # Gemma: instructions inlined
        out = {"AAA": {"status": "possible_break", "why": "exit condition named in headline"}}
        return N(status_code=200, json=lambda: {"candidates": [{"content": {"parts": [{"text": "```json\n" + js.dumps(out) + "\n```"}]}}],
                                                "usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 60}})

    class FakeClaude:
        messages = None

        def create(self, **p):
            sysmsg = p["system"][0]["text"] if isinstance(p["system"], list) else p["system"]
            if sysmsg.startswith("You monitor stock holdings"):       # Haiku: live headline screen
                assert "moved the contract to a rival" in json.dumps(p["messages"])   # Finnhub summary included
                out = {"AAA": {"status": "possible_break", "why": "exit condition named in headline"}}
            else:
                assert sysmsg.startswith("You are the risk reviewer")
                msg = json.dumps(p["messages"])
                if "loses XYZ contract" in msg:
                    assert "Rival wins the XYZ contract" in msg                     # article text in the review
                out = {"verdict": "broken", "action": "sell", "why": "The XYZ contract was the thesis; it is gone."}
            return N(content=[N(type="text", text="```json\n" + json.dumps(out) + "\n```", citations=None)], stop_reason="end_turn",
                     usage=N(input_tokens=900, output_tokens=120, cache_creation_input_tokens=0, cache_read_input_tokens=0, server_tool_use=None))

    fc = FakeClaude()
    fc.messages = fc
    s = llm.Session("watch", anthropic_client=fc, http_post=gemini_post)
    folder = util.run_dir("watch")
    out = watch.main(s, folder, get=get)
    assert out["status"] == "BLOCK"
    assert fetched == ["https://news.example.com/aaa"]
    lab = pd.read_csv(util.state_path("label_ledger.csv"))
    assert set(lab[lab.live].model) == {config.HAIKU} and config.GEMMA in set(lab[~lab.live].model)
    assert set(lab[lab.ticker == "AAA"].label) == {"NO"}
    pf = f"adhoc_plan_{TODAY.isoformat()}.json"
    plan = util.read_json(util.state_path(pf))
    assert plan["trades"][0]["ticker"] == "AAA" and plan["trades"][0]["account"] == "individual"
    log = util.read_json(folder / "watch.json")
    assert "BBB" in log["reviews"] and any("below cost" in f for f in log["price_flags"]["BBB"]["flags"])  # -49% from cost
    assert util.read_json(util.state_path("drop_reviews.json"))["BBB"]
    ck = util.state_path(f"adhoc_checklist_{TODAY.isoformat()}.md")
    assert ck.exists() and list(folder.glob("*.eml"))
    # you place the sale; tracking/rebuild reconcile records it
    body = ck.read_text().replace("- [ ] T01", "- [x] T01")
    ck.write_text(body)
    rec = book.reconcile_all({"AAA": 85.0})
    assert rec and "SELL AAA" in rec[0] and "AAA" not in {p["ticker"] for p in book.load_book()["positions"]}

    # quiet day: no moves, no news -> no email, no Claude
    close2 = close.copy()
    close2["AAA"] = 100.0
    volume2 = volume.copy()
    volume2["AAA"] = 1e6
    watch.market_data = lambda t: (close2, volume2)
    folder2 = util.run_dir("watch2")
    s2 = llm.Session("watch", anthropic_client=fc, http_post=gemini_post)
    out2 = watch.main(s2, folder2, get=lambda url, params=None, timeout=None: N(status_code=200, json=lambda: []))
    assert out2["status"] == "quiet" and not list(folder2.glob("*.eml")) and not s2.usage


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
