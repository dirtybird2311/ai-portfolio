"""
Offline tests for Alpaca paper orders (pipeline/broker.py) and recording fills (book.reconcile).
A fake Alpaca stands in for the real one. Run:  python -m pytest tests/  (or)  python tests/test_broker.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
os.environ["ALPACA_API_KEY_ID"] = "test-id"
os.environ["ALPACA_API_SECRET_KEY"] = "test-secret"
for k in ("GMAIL_APP_PASSWORD", "GITHUB_TOKEN"):
    os.environ.pop(k, None)

import pandas as pd  # noqa: E402

from pipeline import book, broker, config, util  # noqa: E402

N = types.SimpleNamespace
broker._sleep = lambda s: None
config.PAPER_MODE = True
TODAY = util.now_et().date().isoformat()


class Resp:
    def __init__(self, code, data):
        self.status_code, self._d, self.text = code, data, json.dumps(data)

    def json(self):
        return self._d


class FakeAlpaca:
    """Market orders fill instantly at a fixed price; BBB can't be traded in fractions."""
    PRICE = {"AAA": 50.0, "BBB": 200.0, "CCC": 10.0}

    def __init__(self, is_open=True, next_open="tomorrow"):
        self.is_open, self.orders, self.by_client, self.pos, self.calls = is_open, {}, {}, {"AAA": 10.0}, []
        self.next_open = next_open

    def get(self, url, headers=None, timeout=None, params=None):
        assert url.startswith("https://paper-api.alpaca.markets/v2") and headers["APCA-API-KEY-ID"] == "test-id"
        path = url.split("/v2", 1)[1]
        if path == "/clock":
            return Resp(200, {"is_open": self.is_open, "next_open": self.next_open})
        if path == "/positions":
            return Resp(200, [{"symbol": s, "qty": str(q)} for s, q in self.pos.items() if q])
        if path == "/account":
            return Resp(200, {"status": "ACTIVE", "cash": "100000"})
        if path == "/orders:by_client_order_id":
            return Resp(200, self.orders[self.by_client[params["client_order_id"]]])
        return Resp(200, self.orders[path.split("/orders/")[1]])

    def post(self, url, headers=None, timeout=None, json=None):
        self.calls.append(dict(json))
        b = json
        if b["client_order_id"] in self.by_client:
            return Resp(422, {"message": "client_order_id must be unique"})
        if b["symbol"] == "BBB" and ("notional" in b or "." in b.get("qty", "")):
            return Resp(422, {"message": "asset BBB is not fractionable"})
        px = self.PRICE[b["symbol"]]
        qty = float(b["qty"]) if "qty" in b else float(b["notional"]) / px
        oid = f"o{len(self.orders) + 1}"
        self.orders[oid] = {"id": oid, "status": "filled", "filled_qty": str(qty), "filled_avg_price": str(px)}
        self.by_client[b["client_order_id"]] = oid
        self.pos[b["symbol"]] = self.pos.get(b["symbol"], 0) + (qty if b["side"] == "buy" else -qty)
        return Resp(200, self.orders[oid])


def setup():
    util.write_json(util.state_path("holdings.json"), {
        "accounts": {"individual": {"cash": 1000.0}, "ira": {"cash": 1000.0}},
        "positions": [{"ticker": "AAA", "account": "individual", "shares": 10.0, "cost_basis": 400.0,
                       "buy_date": "2026-01-02", "lots": [{"date": "2026-01-02", "shares": 10.0, "cost": 400.0}]}]})
    for f in util.state_path("x").parent.glob("*plan*.json"):
        f.unlink()
    trades = [{"id": "T01", "action": "SELL", "ticker": "AAA", "account": "individual", "amount": "all",
               "ref_price": 49.0, "status": "approved"},
              {"id": "T02", "action": "BUY", "ticker": "BBB", "account": "ira", "amount": 450.0,
               "ref_price": 200.0, "status": "approved"},
              {"id": "T03", "action": "BUY", "ticker": "CCC", "account": "individual", "amount": 300.0,
               "ref_price": 9.5, "status": "approved"},
              {"id": "T04", "action": "BUY", "ticker": "CCC", "account": "ira", "amount": 100.0,
               "ref_price": 9.5, "status": "flagged"}]
    util.write_json(util.state_path("pending_plan.json"), {"date": TODAY, "trade_date": TODAY, "trades": trades,
                                                           "reconciled": None, "paper": True})


def test_orders_and_fills():
    setup()
    fa = FakeAlpaca()
    # before any order is placed, reconcile waits instead of assuming reference-price fills
    assert book.reconcile({}, http=fa) == [] and not util.read_json(util.state_path("pending_plan.json"))["reconciled"]
    out = broker.main(http=fa, folder=util.run_dir("orders"))
    assert out["status"] == "OK"
    sides = [c["side"] for c in fa.calls if c["symbol"] != "BBB" or "qty" in c]
    assert sides[0] == "sell"                                         # sells first
    sell = fa.calls[0]
    assert sell["symbol"] == "AAA" and sell["qty"] == "10" and sell["type"] == "market"
    bbb = [c for c in fa.calls if c["symbol"] == "BBB"]
    assert "notional" in bbb[0] and bbb[1]["qty"] == "2"              # not fractionable -> 2 whole shares
    assert not any(c["symbol"] == "CCC" and c["notional"] == "100" for c in fa.calls)   # flagged trade not placed
    plan = util.read_json(util.state_path("pending_plan.json"))
    assert set(plan["broker"]) == {"T01", "T02", "T03"} and plan["broker"]["T02"]["note"].startswith("whole")
    n = len(fa.calls)
    assert broker.place(http=fa) == [] and len(fa.calls) == n         # a rerun never places twice

    rec = book.reconcile({}, http=fa)
    b = book.load_book()
    assert not any(p["ticker"] == "AAA" for p in b["positions"])       # sold at the Alpaca fill
    assert abs(b["accounts"]["individual"]["cash"] - (1000 + 500 - 300)) < 0.01
    bb = next(p for p in b["positions"] if p["ticker"] == "BBB")
    assert abs(bb["shares"] - 2) < 1e-9 and abs(bb["cost_basis"] - 400) < 0.01   # what actually filled
    assert any("paper fill at Alpaca" in r for r in rec) and any("T04" in r and "not placed" in r for r in rec)
    assert broker.position_diff(http=fa) == []                          # book matches the Alpaca account


def test_orders_queue_for_a_near_open_and_wait_for_a_far_one():
    setup()
    soon = (util.now_et() + pd.Timedelta(hours=8)).isoformat()
    far = (util.now_et() + pd.Timedelta(hours=40)).isoformat()
    fa = FakeAlpaca(is_open=False, next_open=far)
    assert broker.place(http=fa) == [] and not fa.calls                 # the open is too far off: wait
    plan = util.read_json(util.state_path("pending_plan.json"))
    plan["trade_date"] = soon[:10]                                      # the plan's trade date is that next session
    util.write_json(util.state_path("pending_plan.json"), plan)
    fa = FakeAlpaca(is_open=False, next_open=soon)
    lines = broker.place(http=fa)
    plan = util.read_json(util.state_path("pending_plan.json"))
    assert set(plan["broker"]) == {"T01", "T02", "T03"} and all("queued for the" in o["note"] for o in plan["broker"].values())
    assert len(lines) == 3 and broker.place(http=fa) == []              # queued once, never twice


def test_wrong_alpaca_account_places_nothing():
    setup()
    b = util.read_json(util.state_path("holdings.json"))
    b["positions"] += [dict(b["positions"][0], ticker=t) for t in ("BBB", "CCC")]
    util.write_json(util.state_path("holdings.json"), b)
    fa = FakeAlpaca()
    fa.pos = {"ZZZ": 5.0}                                               # another account: none of the book's stocks
    out = broker.main(http=fa, folder=util.run_dir("orders"))
    assert out["status"] == "FLAG" and not fa.calls
    assert not util.read_json(util.state_path("pending_plan.json")).get("broker")


def test_closed_market_live_mode_and_stale_plan():
    setup()
    fa = FakeAlpaca(is_open=False)
    assert broker.place(http=fa) == [] and not fa.calls                 # waits for the open
    config.PAPER_MODE = False
    try:
        assert broker.main(http=FakeAlpaca())["status"] == "skip" and not broker.enabled()
    finally:
        config.PAPER_MODE = True
    # a plan that never reached Alpaca within a week falls back to reference prices
    plan = util.read_json(util.state_path("pending_plan.json"))
    old = (pd.Timestamp(TODAY) - pd.Timedelta(days=10)).date().isoformat()
    plan.update(date=old, trade_date=old)
    util.write_json(util.state_path("pending_plan.json"), plan)
    rec = book.reconcile({}, http=FakeAlpaca())
    assert any("reference price" in r for r in rec)


def test_daily_watch_records_fills_first():
    from pipeline import watch
    setup()
    fa = FakeAlpaca()
    broker.main(http=fa, folder=util.run_dir("orders"))
    real_req, broker.requests = broker.requests, fa           # the watch reads fills from "Alpaca"

    class Stop(Exception):
        pass

    def stop(*a, **k):
        raise Stop()
    real_md, watch.market_data = watch.market_data, stop
    try:
        try:
            watch.main(None, util.run_dir("watch"))
        except Stop:
            pass                                               # reached the watch itself with fills recorded
        held = {p["ticker"] for p in book.load_book()["positions"]}
        assert {"BBB", "CCC"} <= held and "AAA" not in held
        assert util.read_json(util.state_path("pending_plan.json"))["reconciled"]
    finally:
        broker.requests, watch.market_data = real_req, real_md


def test_fill_date_is_new_york_trading_day():
    assert broker.fill_date("2026-10-06T14:32:05.123Z") == "2026-10-06"
    assert broker.fill_date("2026-10-07T01:30:00Z") == "2026-10-06"      # 9:30 pm ET is still the 6th
    assert broker.fill_date(None) is None


def test_adjusted_book_moves_late_trades_to_planned_open():
    from pipeline import navfill
    t = pd.DataFrame([{"date": "2026-09-28", "ticker": "A", "action": "BUY", "price": 10, "shares": 10, "amount": 100},
                      {"date": "2026-10-06", "ticker": "A", "action": "SELL", "price": 12, "shares": 10, "amount": 120},
                      {"date": "2026-10-06", "ticker": "B", "action": "BUY", "price": 20, "shares": 6, "amount": 120}])
    opens = pd.DataFrame({"A": [11.0, 12], "B": [15.0, 20]}, index=pd.to_datetime(["2026-10-05", "2026-10-06"]))
    st = navfill.shadow_trades(t, {"actual_date": "2026-10-06", "planned_date": "2026-10-05"}, opens)
    assert st.loc[1, "amount"] == 110 and st.loc[2, "shares"] == 8          # same shares sold, same dollars spent
    assert (st.loc[1:, "date"] == "2026-10-05").all()
    sh, cash = navfill.holdings_by_day(st, ["2026-10-05"])["2026-10-05"]
    assert sh == {"B": 8.0} and round(cash, 2) == round(10000 - 100 + 110 - 120, 2)


def test_shadow_full_exit_leaves_no_sliver():
    from pipeline import navfill
    t = pd.DataFrame([{"date": "2026-10-06", "ticker": "A", "action": "BUY", "price": 10, "shares": 10, "amount": 100},
                      {"date": "2026-10-20", "ticker": "A", "action": "SELL", "price": 12, "shares": 10, "amount": 120}])
    opens = pd.DataFrame({"A": [8.0, 10.0]}, index=pd.to_datetime(["2026-10-05", "2026-10-06"]))
    st = navfill.shadow_trades(t, {"actual_date": "2026-10-06", "planned_date": "2026-10-05"}, opens)
    assert st.loc[0, "shares"] == 12.5 and st.loc[1, "shares"] == 12.5 and st.loc[1, "amount"] == 150
    sh, _ = navfill.holdings_by_day(st, ["2026-10-20"])["2026-10-20"]
    assert sh == {}


def test_record_row_with_a_broken_gap_is_not_saved():
    from pipeline import navfill
    old = pd.DataFrame([{"date": "2026-11-04", "record_return_pct": 3.6, "executed_return_pct": 5.4}])
    add = [{"date": "2026-11-05", "record_return_pct": -15.6, "executed_return_pct": 1.6},
           {"date": "2026-11-06", "record_return_pct": 2.0, "executed_return_pct": 3.5}]
    navfill.SKIPS.clear()
    assert [r["date"] for r in navfill.consistent(add, old)] == ["2026-11-06"] and navfill.SKIPS


def test_daily_nav_snapshot_vs_spy():
    from pipeline import watch
    idx = pd.to_datetime(["2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30"])
    close = pd.DataFrame({"SPY": [100, 100, 101, 102], "AAA": [10, 10, 11, 12]}, index=idx, dtype=float)
    bk = {"positions": [
        {"ticker": "AAA", "shares": 10.0, "cost_basis": 100.0, "buy_date": "2026-09-28",
         "lots": [{"date": "2026-09-28", "shares": 10.0, "cost": 100.0}]},
        {"ticker": "SPY", "shares": 1.0, "cost_basis": 100.0, "buy_date": "2026-09-28",
         "lots": [{"date": "2026-09-28", "shares": 1.0, "cost": 100.0}]}]}
    assert watch.nav_snapshot(bk, close)["book_return_pct"] == 11.0                # row keyed on the last price bar
    row = watch.nav_snapshot(bk, close, today=pd.Timestamp("2026-09-30").date())
    assert row["book_value"] == 222.0 and row["book_return_pct"] == 11.0          # (120 + 102) / 200
    assert row["spy_return_pct"] == 2.0 and row["vs_spy_pct_pts"] == 9.0
    assert row["stocks_return_pct"] == 20.0 and row["stocks_vs_spy_pct_pts"] == 18.0
    watch.nav_snapshot(bk, close, today=pd.Timestamp("2026-09-30").date())        # same day again: one row only
    assert len(pd.read_csv(util.state_path("daily_nav.csv"))) == 1
    ext = {"positions": [{"ticker": "AAA", "shares": 10.0, "cost_basis": 105.0, "buy_date": "2026-09-30",
                          "lots": [{"date": "2026-09-30", "shares": 10.0, "cost": 105.0, "spy_price": 101.0}]}]}
    r = watch.nav_snapshot(ext, close, nav_file="daily_nav_test.csv")                # SPY from the entry price given
    assert r["spy_return_pct"] == round((102 / 101 - 1) * 100, 2) and r["book_return_pct"] == round((120 / 105 - 1) * 100, 2)
    assert util.state_path("daily_nav_test.csv").exists()
    acct = dict(bk, accounts={"individual": {"cash": 50.0}})
    a = watch.account_snapshot(acct, close, "2026-09-28", 200.0, spy_in=100.0)       # sold-stock gains sit in cash
    assert a["record_value"] == 272.0 and a["record_return_pct"] == 36.0 and a["spy_return_pct"] == 2.0
    assert a["record_vs_spy_pct_pts"] == 34.0 and a["record_basis"] == "as executed" and a["executed_value"] == 272.0
    lag = close.copy()
    lag.loc[idx[-1], "AAA"] = float("nan")                                          # one holding's newest bar missing
    assert watch.nav_snapshot(bk, lag) is None                                      # mixed-day prices: not saved


if __name__ == "__main__":
    for t in (test_orders_and_fills, test_orders_queue_for_a_near_open_and_wait_for_a_far_one,
              test_wrong_alpaca_account_places_nothing, test_closed_market_live_mode_and_stale_plan, test_daily_watch_records_fills_first,
              test_daily_nav_snapshot_vs_spy, test_fill_date_is_new_york_trading_day,
              test_adjusted_book_moves_late_trades_to_planned_open, test_shadow_full_exit_leaves_no_sliver,
              test_record_row_with_a_broken_gap_is_not_saved):
        t()
        print("PASS", t.__name__)
