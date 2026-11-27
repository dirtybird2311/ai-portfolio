"""Offline tests for pipeline.sec and pipeline.screen (simulated Wikipedia, SEC, Finnhub, Yahoo)."""
import os
import zlib
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
os.environ["FINNHUB_API_KEY"] = "test"

from pipeline import config, sec, screen, util  # noqa: E402

N = types.SimpleNamespace
screen.time.sleep = sec.time.sleep = lambda s: None
rng = np.random.default_rng(1)


# ---------------------------------------------------------------- SEC parsing
def r(start, end, val, filed="2026-08-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_ttm_with_ytd_cash_flows():
    rows = [r("2025-01-01", "2025-12-31", 1000),            # FY2025
            r("2025-01-01", "2025-06-30", 450),             # 1H2025 (prior YTD)
            r("2026-01-01", "2026-06-30", 520),             # 1H2026 (current YTD)
            r("2026-04-01", "2026-06-30", 270)]             # Q2 alone: must be ignored
    v, end = sec.ttm(rows)
    assert v == 1000 + 520 - 450 and end == "2026-06-30"
    assert sec.ttm([r("2025-01-01", "2025-12-31", 1000)]) == (1000, "2025-12-31")
    assert sec.ttm([]) == (None, None)


def test_extract_metrics_prefers_freshest_concept_and_gross_profit_fallback():
    cf = {"facts": {"us-gaap": {
        "SalesRevenueNet": {"units": {"USD": [r("2022-01-01", "2022-12-31", 5)]}},       # stale concept
        "Revenues": {"units": {"USD": [r("2025-01-01", "2025-12-31", 900)]}},
        "CostOfRevenue": {"units": {"USD": [r("2025-01-01", "2025-12-31", 600)]}},
        "Assets": {"units": {"USD": [{"end": "2025-12-31", "val": 2000}, {"end": "2026-06-30", "val": 2100}]}},
        "LongTermDebt": {"units": {"USD": [{"end": "2026-06-30", "val": 300}]}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-07-20", "val": 50}]}}}}}
    m = sec.extract_metrics(cf)
    assert m["revenue"] == 900 and m["gross_profit"] == 300 and m["assets"] == 2100
    assert m["debt"] == 300 and m["shares"] == 50 and m["as_of"] == "2025-12-31"


def test_parse_index_and_form4():
    idx = """Description: Daily Index of EDGAR Dissemination Feed by Form Type
Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
4           ACME  CORP                                                    1111        20260915    edgar/data/1111/0001.txt
10-Q        BETA INC                                                      2222        20260915    edgar/data/2222/0002.txt
SC TO-T     GAMMA HOLDINGS                                                3333        20260915    edgar/data/3333/0003.txt
"""
    rows = sec.parse_form_index(idx)
    assert [x["form"] for x in rows] == ["4", "10-Q", "SC TO-T"] and rows[0]["cik"] == 1111
    form4 = """<SEC-DOCUMENT><XML><ownershipDocument>
      <issuer><issuerCik>0000001111</issuerCik></issuer>
      <reportingOwner><reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship></reportingOwner>
      <nonDerivativeTable>
        <nonDerivativeTransaction><transactionDate><value>2026-09-12</value></transactionDate>
          <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
          <transactionAmounts><transactionShares><value>1000</value></transactionShares>
            <transactionPricePerShare><value>25.50</value></transactionPricePerShare>
            <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction><transactionDate><value>2026-09-12</value></transactionDate>
          <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
          <transactionAmounts><transactionShares><value>500</value></transactionShares>
            <transactionPricePerShare><value>26</value></transactionPricePerShare>
            <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
        </nonDerivativeTransaction>
      </nonDerivativeTable></ownershipDocument></XML></SEC-DOCUMENT>"""
    buys = sec.parse_form4(form4)
    assert len(buys) == 1 and buys[0]["value"] == 25500 and buys[0]["role"] == "director" and buys[0]["issuer_cik"] == 1111
    assert sec.parse_form4("garbage") == []


# ---------------------------------------------------------------- screen pieces
def test_slots_follow_tilts_and_fill_to_target():
    tilts = {s: 0 for s in config.SECTORS}
    tilts.update({"Energy": 2, "Utilities": -2, "Technology": 1})
    avail = {s: 50 for s in config.SECTORS}
    avail["Materials"] = 1
    slots = screen.allocate_slots(tilts, avail)
    assert sum(slots.values()) == screen.N_CANDIDATES and slots["Utilities"] == 0 and slots["Materials"] <= 1
    assert slots["Energy"] > slots["Technology"] > slots["Health Care"]


def test_kind_of():
    k = lambda sector, sub: screen.kind_of({"sector": sector, "sub_industry": sub})
    assert k("Financials", "Regional Banks") == "bank" and k("Financials", "Property & Casualty Insurance") == "insurer"
    assert k("Real Estate", "Industrial REITs") == "reit" and k("Technology", "Semiconductors") == "company"


# ---------------------------------------------------------------- end to end
TICKERS = []
for i, sector in enumerate(config.SECTORS):
    for j in range(6):
        TICKERS.append((f"T{i}{j}" if not (i == 0 and j == 0) else "BRK.B", sector))
GICS = {"Technology": "Information Technology"}


def wiki_html(index):
    rows = [t for k, t in enumerate(TICKERS) if k % 3 == list(screen.WIKI).index(index)]
    sub = lambda s: {"Financials": "Regional Banks", "Real Estate": "Retail REITs"}.get(s, "Something")
    df = pd.DataFrame({"Symbol": [t for t, _ in rows],
                       ("Security" if index != "S&P 600" else "Company"): [f"{t} Inc" for t, _ in rows],
                       "GICS Sector": [GICS.get(s, s) for _, s in rows], "GICS Sub-Industry": [sub(s) for _, s in rows]})
    return "<html>" + pd.DataFrame({"junk": [1]}).to_html() + df.to_html(index=False) + "</html>"


def fake_get(url, headers=None, timeout=None, params=None):
    for idx, u in screen.WIKI.items():
        if url == u:
            return N(text=wiki_html(idx), status_code=200)
    if "stock/earnings" in url:
        sym = params["symbol"]
        return N(status_code=200, json=lambda: [{"surprisePercent": (zlib.crc32(sym.encode()) % 20) - 5}, {"surprisePercent": 3}])
    if "calendar/earnings" in url:
        return N(status_code=200, json=lambda: {"earningsCalendar": [{"symbol": "T30", "date": (screen.TODAY + timedelta(days=5)).isoformat()}]})
    raise AssertionError(url)


class FakeSEC:
    def __init__(self):
        self.metric_calls = 0

    def ticker_map(self):
        return {t: 1000 + k for k, (t, _) in enumerate(TICKERS)}

    def daily_index(self, d):
        if d == screen.TODAY - timedelta(days=3) or (d.weekday() < 5 and d == screen.TODAY):
            return [{"form": "4", "cik": 1001, "filed": d.strftime("%Y%m%d"), "file": "f4"},
                    {"form": "10-Q", "cik": 1002, "filed": d.strftime("%Y%m%d"), "file": "q"},
                    {"form": "SC TO-T", "cik": 1003, "filed": d.strftime("%Y%m%d"), "file": "t"}]
        return []

    def form4_purchases(self, f):
        return [{"issuer_cik": 1001, "owner": f"Exec {k}", "role": "officer", "date": screen.TODAY.isoformat(),
                 "shares": 1000, "price": 50, "value": 50000} for k in range(3)]

    def metrics(self, cik):
        self.metric_calls += 1
        g = rng.uniform
        return {"revenue": g(500, 2000), "gross_profit": g(100, 800), "operating_income": g(-50, 400),
                "net_income": g(-20, 300), "cfo": g(0, 400), "capex": g(10, 100), "dna": g(10, 80),
                "assets": g(1000, 5000), "equity": g(300, 2000), "debt": g(0, 1500), "cash": g(0, 300),
                "shares": g(10, 100), "as_of": "2026-06-30", "stale": cik == 1004,
                "roic": g(-0.05, 0.3), "margin_stability": -g(0, 0.1), "v": sec.METRICS_VERSION}


idx = pd.bdate_range(end=pd.Timestamp(screen.TODAY), periods=320)
names = [t for t, _ in TICKERS]
CLOSE = pd.DataFrame({t.replace(".", "-"): 50 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(idx)))) for t in names}, index=idx)
CLOSE["T11"] = 3.0                                                        # penny stock: filtered out
VOL = pd.DataFrame(200_000, index=idx, columns=CLOSE.columns)
yf = types.ModuleType("yfinance")
yf.download = lambda *a, **k: pd.concat({"Close": CLOSE.copy(), "Volume": VOL.copy()}, axis=1)
yf.Ticker = lambda t: N(eps_revisions=pd.DataFrame({"upLast30days": [5, 3], "downLast30Days": [1, 0]}, index=["0q", "0y"]))
sys.modules["yfinance"] = yf


def test_screen_end_to_end():
    tilts = {s: 0 for s in config.SECTORS}
    tilts.update({"Energy": 2, "Utilities": -2})
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-09-18", "tilts": tilts,
        "weight_ranges_%": {s: list(config.TILT_RANGES[t]) for s, t in tilts.items()}})
    util.write_json(util.state_path("holdings.json"), {"positions": [{"ticker": "T80"}]})  # a Utilities stock
    fs = FakeSEC()
    folder = util.run_dir("screen")
    out = screen.main(None, folder, sec=fs, get=fake_get)
    c = util.read_json(util.state_path("candidates.json"))
    cands = pd.DataFrame(c["candidates"])
    assert "T11" not in set(cands.ticker)                                  # filtered (price < $5)
    assert c["slots"]["Utilities"] == 0 and c["slots"]["Energy"] >= 5
    assert "T80" in set(cands.ticker) and cands.set_index("ticker").loc["T80", "incumbent"]   # incumbent kept
    bench = pd.read_csv(util.state_path("bench.csv")).set_index("ticker")
    assert bench.loc["T01", "insider_buyers"] == 3 and bench.loc["T01", "s_insider"] >= 0.9
    assert "possible acquisition" in bench.loc["T03", "flags"]
    assert "earnings" in str(bench.loc["T30", "flags"])
    assert "old filings" in str(bench.loc["T04", "flags"])
    assert bench.composite.between(0, 1).all()
    assert set(bench[bench.sector == "Financials"].kind) == {"bank"}
    assert bench.loc[bench.sector == "Financials", "q_roa"].notna().all()
    assert "BRK.B" in bench.index
    ctrl = c["control_portfolio"]
    assert len(ctrl) <= screen.CONTROL_SIZE and abs(sum(x["weight_%"] for x in ctrl) - 100) < 0.1
    assert not any(x["sector"] == "Utilities" for x in ctrl)              # -2 ceiling 3% -> 0 slots of 18
    assert (folder / "report.md").exists() and "Signal weights" in (folder / "report.md").read_text()
    assert {"s_reaction", "s_industry", "s_reversal"} <= set(bench.columns) and abs(sum(c["weights"].values()) - 1) < 1e-6
    # second week: only new filers are re-read
    calls = fs.metric_calls
    screen.main(None, folder, sec=fs, get=fake_get)
    assert fs.metric_calls - calls <= 2, fs.metric_calls - calls


# ---------------------------------------------------------------- screener upgrades
def test_weights_move_halfway_toward_evidence_once_a_year():
    w, _ = screen.screen_weights(evidence={}, saved={})
    assert w == screen.PRIOR_WEIGHTS                                      # no history yet: starting weights
    ev = {"signals": {"momentum": {"mean_ic": 0.03, "t": 4.0, "months": 180}, "reaction": {"mean_ic": 0.01, "t": 2.0, "months": 180},
                      "quality": {"mean_ic": 0.0, "t": 0.1, "months": 180}, "reversal": {"mean_ic": 0.02, "t": 3.0, "months": 12}}}
    w, saved = screen.screen_weights(evidence=ev, saved={}, today=pd.Timestamp("2026-10-01").date())
    assert abs(sum(w.values()) - 1) < 1e-3
    assert w["momentum"] > screen.PRIOR_WEIGHTS["momentum"] > w["quality"]      # evidence moves weight toward what worked
    assert w["quality"] >= 0.5 * screen.PRIOR_WEIGHTS["quality"] - 1e-3     # ...but only halfway (never to zero at once)
    assert abs(w["reversal"] - screen.PRIOR_WEIGHTS["reversal"] / sum(screen.PRIOR_WEIGHTS.values())) < 0.02  # too little history
    w2, _ = screen.screen_weights(evidence={"signals": {}}, saved=saved, today=pd.Timestamp("2027-03-01").date())
    assert w2 == w                                                        # not re-set until a year has passed
    v = screen.signal_verdicts(ev)
    assert v["quality"].startswith("adds nothing") and v["momentum"] == "keep" and v["reversal"] == "not enough history"
    assert screen.signal_verdicts({"signals": {"x": {"mean_ic": -0.02, "t": -2.5, "months": 100}}})["x"].startswith("HURTS")


def test_momentum_guard_turns_momentum_off_after_a_down_year():
    w = {"momentum": 0.2, "industry": 0.1, "value": 0.4, "quality": 0.3}
    assert screen.momentum_guard(w, 0.12) == (w, False) and screen.momentum_guard(w, None) == (w, False)
    g, on = screen.momentum_guard(w, -0.05)
    assert on and g["momentum"] == g["industry"] == 0 and abs(sum(g.values()) - 1.0) < 1e-3
    assert abs(g["value"] / g["quality"] - 4 / 3) < 1e-3                 # the rest keep their proportions
    days = pd.bdate_range("2025-01-01", periods=300)
    up = pd.DataFrame({"A": np.linspace(100, 130, 300), "B": np.linspace(50, 60, 300)}, index=days)
    assert screen.market_12m(up) > 0 > screen.market_12m(up.iloc[::-1].set_axis(days)) and screen.market_12m(up.tail(100)) is None


def test_sub_industry_cap_scales_and_exempts():
    rows = [{"ticker": f"C{i:02d}", "sector": "Technology", "sub_industry": "Chips" if i < 12 else f"Other{i}",
             "composite": 0.99 - i * 0.01} for i in range(30)]
    pool = pd.DataFrame(rows)
    got, bumped, repl = screen.pick_candidates(pool, {"Technology": 8}, set(), standout_cut=2.0)
    assert (got.sub_industry == "Chips").sum() == 4 and len(got) == 8     # neutral sector: max(4, 35% of 8) = 4
    assert bumped == ["C04", "C05", "C06", "C07"] and repl == ["C12", "C13", "C14", "C15"]
    got20, _, _ = screen.pick_candidates(pool, {"Technology": 20}, set(), standout_cut=2.0)
    assert (got20.sub_industry == "Chips").sum() == 7                     # overweight sector: 35% of 20 = 7
    got_s, _, _ = screen.pick_candidates(pool, {"Technology": 8}, {"C09"}, standout_cut=0.945)
    chips = set(got_s[got_s.sub_industry == "Chips"].ticker)
    assert {"C00", "C01", "C02", "C03", "C04", "C09"} <= chips            # standouts and holdings aren't capped


def test_distress_filter_and_new_signals():
    df = pd.DataFrame({"ticker": ["A", "B", "C"], "kind": ["company", "company", "bank"], "sector": "Energy",
                       "q_low_leverage": [-0.8, -0.8, -0.9], "v_fcf_yield": [-0.02, 0.03, -0.1], "q_op_margin": [-0.1, 0.1, -0.1]})
    assert list(screen.distressed(df)) == [True, False, False]
    n = 12
    df = pd.DataFrame({"ticker": [f"T{i}" for i in range(n)], "sector": "Energy", "kind": "company",
                       "sub_industry": ["X"] * 6 + ["Y"] * 6, "mom_12_1": [0.5] * 6 + [-0.1] * 6, "mom_3m": 0.0,
                       "mom_1m": [0.30] + [0.0] * (n - 1), "surprise": np.nan, "revisions": np.nan, "insider_value": 0.0,
                       "insider_buyers": 0, "mcap": 1e9, "q_roa": 0.1, "v_ey": 0.05})
    out = screen.score(df, {"T1": {"reaction_now_%": 6.0}, "T2": {"reaction_now_%": -5.0}})
    assert out.loc[1, "s_reaction"] > out.loc[2, "s_reaction"]            # post-earnings drift
    assert out.loc[0, "s_industry"] > out.loc[11, "s_industry"]           # strong sub-industry
    assert out.loc[0, "s_reversal"] < out.loc[5, "s_reversal"]            # last month's spike is penalized


def test_sec_client_retries_a_timeout_instead_of_stopping_the_run():
    import time
    import requests
    from pipeline import sec
    real, time.sleep = time.sleep, lambda s: None
    try:
        n = [0]

        class R:
            status_code, text = 200, "ok"

        def flaky(url, **k):
            n[0] += 1
            if n[0] < 3:
                raise requests.ReadTimeout("slow")
            return R()

        def dead(url, **k):
            raise requests.ReadTimeout("slow")
        assert sec.SEC(get=flaky).get("u", as_json=False) == "ok" and n[0] == 3
        assert sec.SEC(get=dead).get("u", as_json=False) is None
    finally:
        time.sleep = real


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
