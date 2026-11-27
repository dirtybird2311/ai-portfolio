"""
Offline tests for the second price source (pipeline/prices.py), the watch's price settling, skip reasons and
the nightly backfill of the real-account NAV files. Run:  python -m pytest tests/  (or)  python tests/test_prices.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
os.environ["ALPACA_API_KEY_ID"] = "test-id"
os.environ["ALPACA_API_SECRET_KEY"] = "test-secret"

import pandas as pd  # noqa: E402

from pipeline import navfill, prices, util, watch  # noqa: E402

N = types.SimpleNamespace
DAYS = pd.to_datetime(["2026-10-13", "2026-10-14", "2026-10-15"])


def yahoo(adm_last=True):
    c = pd.DataFrame({"SPY": [770.0, 774.0, 778.0], "ADM": [80.0, 81.0, 82.0], "^VIX": [18.0, 19.0, 17.0]}, index=DAYS)
    if not adm_last:
        c.loc[DAYS[-1], "ADM"] = float("nan")
    return c


def alpaca_get(bars):
    def get(url, headers=None, params=None, timeout=None):
        assert headers["APCA-API-KEY-ID"] == "test-id" and params["feed"] == "iex"
        return N(status_code=200, json=lambda: {"bars": bars, "next_page_token": None})
    return get


def test_gaps_found_and_ignores_vix():
    c = yahoo(adm_last=False)
    assert prices.gaps(c, ["SPY", "ADM"]) == ["ADM"]
    assert prices.gaps(yahoo(), ["SPY", "ADM", "ZZZ"]) == ["ZZZ"]   # a ticker Yahoo never returned is a gap too


def test_fill_gaps_from_alpaca():
    c = yahoo(adm_last=False)
    get = alpaca_get({"ADM": [{"t": "2026-10-15T04:00:00Z", "c": 82.5}], "SPY": [{"t": "2026-10-15T04:00:00Z", "c": 778.1}]})
    lines, short = prices.fill_gaps(c, ["SPY", "ADM"], get=get, now=pd.Timestamp("2026-10-15 20:00"))
    assert short == [] and abs(float(c["ADM"].iloc[-1]) - 82.5) < 1e-9
    assert float(c["SPY"].iloc[-1]) == 778.0               # Yahoo's SPY is kept: only missing days are filled
    assert lines and "ADM" in lines[0]


def test_no_keys_or_failure_gives_a_report_not_a_crash():
    c = yahoo(adm_last=False)
    bad = lambda *a, **k: N(status_code=500, json=lambda: {})
    lines, short = prices.fill_gaps(c, ["SPY", "ADM"], get=bad, now=pd.Timestamp("2026-10-15 20:00"))
    assert short == ["ADM"] and "no Alpaca fallback" in lines[0]
    assert prices.alpaca_closes(["ADM"], "2026-10-10", get=lambda *a, **k: (_ for _ in ()).throw(OSError("down"))) is None


def test_expected_day_rolls_back_over_weekends_and_before_the_close():
    assert prices.expected_day(pd.Timestamp("2026-10-15 17:00")) == pd.Timestamp("2026-10-15")
    assert prices.expected_day(pd.Timestamp("2026-10-15 10:00")) == pd.Timestamp("2026-10-14")
    assert prices.expected_day(pd.Timestamp("2026-10-17 12:00")) == pd.Timestamp("2026-10-16")
    assert prices.expected_day(pd.Timestamp("2026-10-19 09:00")) == pd.Timestamp("2026-10-16")


def test_settle_prices_retries_yahoo_then_saves_row():
    c = yahoo(adm_last=False)
    calls = []
    get = lambda *a, **k: N(status_code=500, json=lambda: {})           # Alpaca down: only the Yahoo re-pull helps
    out, _ = watch.settle_prices(c, None, ["SPY", "ADM"], tries=3, wait=0, get=get, sleep=lambda s: None, now=pd.Timestamp("2026-10-15 20:00"),
                                 loader=lambda need: (calls.append(1) or yahoo(), None))
    assert calls == [1] and float(out["ADM"].iloc[-1]) == 82.0


def test_skip_reason_is_recorded_not_silent():
    watch.SKIPS.clear()
    book = {"positions": [{"ticker": "ADM", "shares": 1, "cost_basis": 80.0,
                           "lots": [{"date": "2026-10-13", "shares": 1, "cost": 80.0}]}]}
    assert watch.nav_snapshot(book, yahoo(adm_last=False)) is None
    assert watch.SKIPS and "ADM" in watch.SKIPS[-1] and "2026-10-15" in watch.SKIPS[-1]


def test_navfill_adds_missing_real_account_rows():
    ext = {"books": {"acct": {"label": "Acct", "positions": [
        {"ticker": "ADM", "shares": 2, "cost_basis": 160.0, "buy_date": "2026-10-13",
         "lots": [{"date": "2026-10-13", "shares": 2, "cost": 160.0, "price": 80.0, "spy_price": 770.0}]}]}}}
    util.write_json(util.state_path("external_books.json"), ext)
    c = yahoo()
    n = navfill.fill_external(c)
    df = pd.read_csv(util.state_path("daily_nav_acct.csv"))
    assert n == 3 and list(df["date"]) == ["2026-10-13", "2026-10-14", "2026-10-15"]
    assert abs(df["book_value"].iloc[-1] - 164.0) < 1e-9 and abs(df["spy_return_pct"].iloc[-1] - 1.04) < 0.01
    assert navfill.fill_external(c) == 0                       # existing rows are left alone


def test_cash_after_a_rebalance_counts_in_the_book_and_active_from_skips_earlier_days():
    book = {"positions": [{"ticker": "ADM", "shares": 2, "cost_basis": 160.0, "buy_date": "2026-10-13",
                           "lots": [{"date": "2026-10-13", "shares": 2, "cost": 160.0, "price": 80.0, "spy_price": 770.0}]}],
            "cash": {"amount": 50.0, "cost": 48.0, "spy_price": 770.0}}
    r = watch.nav_snapshot(book, yahoo(), nav_file="daily_nav_cashtest.csv")
    assert abs(r["book_value"] - (2 * 82.0 + 50.0)) < 1e-9 and abs(r["cost"] - 208.0) < 1e-9
    assert abs(r["spy_return_pct"] - (208.0 / 770.0 * 778.0 / 208.0 - 1) * 100) < 0.01
    ext = {"books": {"c2": {"label": "C2", "active_from": "2026-10-15", "positions": [
        {"ticker": "ADM", "shares": 1, "cost_basis": 80.0, "buy_date": "2026-10-13",
         "lots": [{"date": "2026-10-13", "shares": 1, "cost": 80.0, "price": 80.0, "spy_price": 770.0}]}]}}}
    util.write_json(util.state_path("external_books.json"), ext)
    assert navfill.fill_external(yahoo()) == 1                 # only 2026-10-15 is on or after active_from


def test_phases_price_earlier_days_on_the_book_held_then():
    lot = lambda sh, c: {"date": "2026-10-13", "shares": sh, "cost": c, "price": 80.0, "spy_price": 770.0}
    old = [{"ticker": "ADM", "shares": 2, "cost_basis": 160.0, "buy_date": "2026-10-13", "lots": [lot(2, 160.0)]}]
    ext = {"books": {"ph": {"label": "Ph", "active_from": "2026-10-15", "phases": [
        {"until": "2026-10-14", "positions": old}], "positions": [
        {"ticker": "ADM", "shares": 1, "cost_basis": 80.0, "buy_date": "2026-10-13", "lots": [lot(1, 80.0)]}]}}}
    util.write_json(util.state_path("external_books.json"), ext)
    assert navfill.fill_external(yahoo()) == 3
    df = pd.read_csv(util.state_path("daily_nav_ph.csv"))
    assert abs(df["cost"].iloc[0] - 160.0) < 1e-9 and abs(df["cost"].iloc[-1] - 80.0) < 1e-9


def test_account_row_with_an_implausible_jump_is_refused():
    util.write_json(util.state_path("holdings.json"), {})
    path = util.state_path(watch.ACCOUNT_NAV_FILE)
    pd.DataFrame([{"date": "2026-10-14", "since": "2026-10-13", "start_value": 1000.0, "record_value": 1000.0}]).to_csv(path, index=False)
    book = {"accounts": {"x": {"cash": 0.0}}, "positions": [{"ticker": "ADM", "shares": 6.0}]}   # 6 x 82 = 492: a 51% drop
    watch.SKIPS.clear()
    assert watch.account_snapshot(book, yahoo(), "2026-10-13", 1000.0, spy_in=770.0) is None
    assert watch.SKIPS and "not saved" in watch.SKIPS[-1]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
