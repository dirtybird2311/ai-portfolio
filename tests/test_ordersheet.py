"""Offline tests for the Robinhood order sheet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import ordersheet  # noqa: E402


def test_whole_shares_stay_within_value_and_use_cash():
    w = {"A": 50.0, "B": 50.0}
    n, cash = ordersheet.whole_shares(w, {"A": 30.0, "B": 70.0}, 1000.0)
    assert n["A"] * 30 + n["B"] * 70 + cash == 1000.0 or abs(n["A"] * 30 + n["B"] * 70 + cash - 1000) < 1e-6
    assert cash >= 0 and cash < 70 and n == {"A": 17, "B": 7}


def test_plan_sells_exits_and_buys_new_names():
    book = {"positions": [{"ticker": "OLD", "shares": 10}, {"ticker": "KEEP", "shares": 5}]}
    p = ordersheet.plan(book, {"KEEP": 50.0, "NEW": 50.0}, {"OLD": 10.0, "KEEP": 20.0, "NEW": 25.0})
    acts = {(r["action"], r["ticker"]) for r in p["rows"]}
    assert ("SELL", "OLD") in acts and ("BUY", "NEW") in acts and p["value"] == 200.0
    assert all(r["to"] >= 0 for r in p["rows"])


def test_prices_fall_back_when_alpaca_is_unavailable():
    bad = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
    got = ordersheet.latest_prices(["X", "Y"], get=bad, fallback=lambda m: {t: 1.5 for t in m})
    assert got == {"X": 1.5, "Y": 1.5}


def test_fractional_buys_fill_shortfalls_with_the_cash_only():
    from pipeline import ordersheet
    book = {"positions": [{"ticker": "A", "shares": 10}], "cash": {"amount": 100.0}}
    p = ordersheet.plan_fractional(book, {"A": 50.0, "B": 50.0}, {"A": 10.0, "B": 40.0})
    # value 200: A is at target ($100), B is $100 short and the cash covers it exactly
    assert [r["ticker"] for r in p["rows"]] == ["B"] and abs(p["rows"][0]["dollars"] - 100) < 1e-9
    assert abs(p["rows"][0]["shares"] - 2.5) < 1e-9 and abs(p["cash"]) < 1e-9




def test_cash_accounts_are_planned_from_scratch():
    from pipeline import ordersheet
    b = ordersheet.parse_cash("Account A=20,104.50; Account B=9085.18")
    assert set(b) == {"new_account_a", "new_account_b"}
    p = ordersheet.plan(b["new_account_a"], {"A": 60.0, "B": 40.0}, {"A": 100.0, "B": 50.0})
    assert {r["ticker"]: r["shares"] for r in p["rows"]} == {"A": 120, "B": 161} and abs(p["cash"] - 54.5) < 1e-6


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn(); print("PASS", n)
