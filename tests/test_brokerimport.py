"""
Offline tests for the broker activity import (pipeline/brokerimport.py).
Run:  python -m pytest tests/  (or)  python tests/test_brokerimport.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

from pipeline import brokerimport as bi  # noqa: E402

ROBINHOOD = '''"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"
"11/17/2026","11/17/2026","11/18/2026","BBB","Bee Corp
CUSIP: 000000001","Buy","2.5","$40.00","($100.00)"
"11/16/2026","11/16/2026","11/17/2026","AAA","Aye Inc
CUSIP: 000000002","Sell","5","$24.00","$120.00"
"11/16/2026","11/16/2026","11/16/2026","AAA","Cash Div: R/D 2026-11-01 P/D 2026-11-16 - 10 shares at 0.1","CDIV","","","$1.00"
"11/3/2026","11/3/2026","11/4/2026","AAA","Aye Inc
CUSIP: 000000002","Buy","10","$20.00","($200.00)"
""
"","","","","","","","","","The data provided is for informational purposes only."
'''
SCHWAB = '''"Transactions for account XXXX-123 as of 11/20/2026"
"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"
"11/17/2026","Buy","BBB","BEE CORP","2.5","$40.00","","-$100.00"
"11/16/2026","Sell","AAA","AYE INC","5","$24.00","","$120.00"
"11/16/2026","Qualified Dividend","AAA","AYE INC","","","","$1.00"
'''


def book():
    lot = {"date": "2026-11-03", "shares": 10.0, "cost": 200.0, "price": 20.0, "spy_price": 700.0}
    return {"label": "T", "imported_through": "2026-11-03", "active_from": "2026-11-03", "phases": [],
            "positions": [{"ticker": "AAA", "shares": 10.0, "cost_basis": 200.0, "buy_date": "2026-11-03", "lots": [lot]}],
            "cash": {"amount": 10.0, "cost": 10.0, "spy_price": 700.0}}


def write(text):
    p = Path(tempfile.mkdtemp()) / "a.csv"
    p.write_text(text)
    return p


def test_robinhood_file_applies_with_carried_cost():
    txs = bi.parse_robinhood(write(ROBINHOOD))
    assert [(t["date"], t["action"], t["ticker"]) for t in txs] == [
        ("2026-11-17", "BUY", "BBB"), ("2026-11-16", "SELL", "AAA"), ("2026-11-16", "DIV", "AAA"), ("2026-11-03", "BUY", "AAA")]
    b = book()
    s = bi.apply(b, txs)
    assert s["days"] == ["2026-11-16", "2026-11-17"]                     # the Nov 3 buy is already in the book
    pos = {p["ticker"]: p for p in b["positions"]}
    assert pos["AAA"]["shares"] == 5 and pos["AAA"]["cost_basis"] == 100.0
    # cash after the sale and dividend: $131 carrying $110 of cost; the $100 buy takes 100/131 of that cost
    assert pos["BBB"]["shares"] == 2.5 and abs(pos["BBB"]["cost_basis"] - 83.97) < 0.01 and pos["BBB"]["lots"][0]["carried"]
    assert b["cash"]["amount"] == 31.0 and abs(s["cost"] - 210.0) < 0.02      # the account's cost base never moved
    assert [p["until"] for p in b["phases"]] == ["2026-11-15", "2026-11-16"]
    assert b["phases"][0]["positions"][0]["shares"] == 10.0 and b["phases"][1]["cash"]["amount"] == 131.0
    assert b["imported_through"] == b["active_from"] == "2026-11-17"
    again = copy.deepcopy(b)
    assert bi.apply(again, txs)["days"] == [] and again == b                 # the same file twice changes nothing


def test_schwab_file_reads_the_same_trades():
    a, c = book(), book()
    bi.apply(a, bi.parse_robinhood(write(ROBINHOOD)))
    bi.apply(c, bi.parse_schwab(write(SCHWAB)))
    assert a["positions"] == c["positions"] and a["cash"] == c["cash"]


def test_overselling_and_unfunded_buys_stop_the_import():
    for bad, word in (([{"date": "2026-11-16", "ticker": "AAA", "action": "SELL", "shares": 11, "price": 1, "amount": 11}], "holds"),
                      ([{"date": "2026-11-16", "ticker": "CCC", "action": "BUY", "shares": 1, "price": 500, "amount": 500}], "--deposit")):
        try:
            bi.apply(book(), bad)
            assert False, "should have refused"
        except ValueError as e:
            assert word in str(e)
    b = book()
    s = bi.apply(b, [{"date": "2026-11-16", "ticker": "CCC", "action": "BUY", "shares": 1, "price": 500, "amount": 500}], deposit=500)
    assert b["cash"]["amount"] == 10.0 and abs(s["cost"] - 710.0) < 0.01   # new money counts at cost, not as a gain


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
