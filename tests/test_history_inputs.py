"""
Offline tests: base rates (history.py), the new judge inputs (inputs.py), SEC history parsing, and
replaying saved judge packets (replay.py). Synthetic data only.
Run:  python -m pytest tests/  (or)  python tests/test_history_inputs.py
"""
import gzip
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
os.environ["ANTHROPIC_API_KEY"] = "test"

from pipeline import config, history, inputs, ledger, llm, replay, sec, util  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = lambda s: None
rng = np.random.default_rng(11)
DAYS = pd.bdate_range("2011-01-03", "2026-09-18")
TICK = [f"S{i:02d}" for i in range(40)]
SECTOR = {t: ["Technology", "Energy", "Financials"][i % 3] for i, t in enumerate(TICK)}
DRIFT = {t: rng.normal(0, 0.0004) for t in TICK}
PX = pd.DataFrame({t: 100 * np.cumprod(1 + DRIFT[t] + rng.normal(0, 0.015, len(DAYS))) for t in TICK}, index=DAYS)
PX.loc[:"2026-01-01", "S39"] = np.nan                       # a recent IPO


# ---------------------------------------------------------------- base rates
def test_equal_weight_sector_index():
    ew = history.ew_sector_index(PX, SECTOR)
    names = [t for t in TICK if SECTOR[t] == "Energy"]
    r = PX[names].pct_change(fill_method=None).mean(axis=1).fillna(0)
    assert abs(ew["Energy"].iloc[-1] - (1 + r).cumprod().iloc[-1]) < 1e-9


def test_samples_table_lookup():
    ed = {t: [d.date().isoformat() for d in DAYS[40::63]] for t in TICK}
    qh = {t: [(f"{y}-03-01", float(rng.uniform(0, 0.6))) for y in range(2011, 2027)] for t in TICK}
    ew = history.ew_sector_index(PX, SECTOR)
    re_ = history.event_reactions(PX, ew, SECTOR, ed)
    df = history.samples(PX, SECTOR, re_, qh, "2012-06-01")
    assert len(df) > 5000 and set(df.beat.unique()) <= {0, 1}
    assert df[df.ticker == "S39"].date.min() >= "2026-01-01"       # no history before it traded
    table = history.build_table(df)
    g = table["groups"]
    assert "all" in g and "m=5" in g and any(k.count("|") == 2 for k in g)
    # thin groups are pulled toward the overall rate
    k = min((k for k in g if k.count("|") == 2), key=lambda k: g[k]["n"])
    raw = g[k]["raw_%"] / 100
    assert abs(g[k]["p"] - table["overall"]) <= abs(raw - table["overall"]) + 1e-9
    full = history.lookup(table, {"m": 5, "e": 1, "q": 5}, min_group=1)
    assert full["group"] == "e=1|m=5|q=5"
    fallback = history.lookup(table, {"m": 5, "e": None, "q": float("nan")})
    assert fallback["group"] == "m=5"
    assert history.lookup(None, {"m": 5})["p"] == 0.5
    warn = dict(full, warn=True, recent_p=0.4)
    assert "WARNING" in history.describe(warn) and "Last 5 years: 40.0%" in history.describe(warn)
    cur = history.current(PX, SECTOR, re_, qh, ["S00", "S39"],
                          {"S00": [("2025-02-01", 1000.0, "2024-12-31"), ("2026-02-01", 1100.0, "2025-12-31")]},
                          {"S00": 10.0})
    assert cur["S39"]["history_days"] < 365 and cur["S00"]["history_days"] > 5000
    assert cur["S00"]["rev_growth_%"] == [10.0] and cur["S00"]["reactions"]


def test_signal_evidence_finds_a_real_signal():
    rng2 = np.random.default_rng(5)
    rows = []
    for d in pd.date_range("2012-01-31", periods=80, freq="ME"):
        for i in range(60):
            mom = rng2.normal()
            rows.append({"date": d.date().isoformat(), "ticker": f"S{i}", "sector": ["A", "B"][i % 2],
                         "mom_raw": mom, "react_raw": rng2.normal(), "qual_raw": rng2.normal(), "rev_1m": rng2.normal(),
                         "ind_mom": rng2.normal(), "resid": 0.02 * mom + rng2.normal(0, 0.05)})
    ev = history.signal_evidence(pd.DataFrame(rows))["signals"]
    assert ev["momentum"]["mean_ic"] > 0.2 and ev["momentum"]["t"] > 5
    assert abs(ev["quality"]["mean_ic"]) < 0.05 and ev["momentum"]["months"] == 80


def test_history_main_end_to_end():
    bench = pd.DataFrame({"ticker": TICK, "sector": [SECTOR[t] for t in TICK], "cik": range(1000, 1000 + len(TICK))})
    bench.to_csv(util.state_path("bench.csv"), index=False)
    util.write_json(util.state_path("fundamentals_cache.json"), {str(1000 + i): {"shares": 1e6} for i in range(len(TICK))})

    class FakeSEC:
        def earnings_dates(self, cik, since, full=True):
            return [d.date().isoformat() for d in DAYS[40::63]]

        def companyfacts(self, cik):
            return {"facts": {"us-gaap": {
                "GrossProfit": {"units": {"USD": [{"start": f"{y}-01-01", "end": f"{y}-12-31", "val": 40.0 + cik % 7,
                                                   "filed": f"{y + 1}-02-20", "form": "10-K"} for y in range(2010, 2026)]}},
                "Revenues": {"units": {"USD": [{"start": f"{y}-01-01", "end": f"{y}-12-31", "val": 100.0 * 1.1 ** (y - 2010),
                                                "filed": f"{y + 1}-02-20", "form": "10-K"} for y in range(2010, 2026)]}},
                "Assets": {"units": {"USD": [{"end": f"{y}-12-31", "val": 200.0, "filed": f"{y + 1}-02-20"}
                                             for y in range(2010, 2026)]}}}}}

    history.download_prices = lambda tickers, start: PX[[t for t in tickers if t in PX]]
    from pipeline import altdata
    real_fetch, altdata.fetch_short = altdata.fetch_short, (lambda d, get=None: None)   # offline: no FINRA files
    try:
        out = history.main(sec=FakeSEC())
    finally:
        altdata.fetch_short = real_fetch
    assert out["status"] == "rebuilt"
    table = util.read_json(util.state_path("base_rates.json"))
    feats = util.read_json(util.state_path("current_features.json"))["stocks"]
    assert table["samples"] > 1000 and feats["S00"]["q"] in (1, 2, 3, 4, 5) and feats["S00"]["ps_now"]
    assert len(feats["S00"]["rev_growth_%"]) == 4 and all(abs(g - 10.0) < 0.2 for g in feats["S00"]["rev_growth_%"])
    assert util.read_json(util.state_path("signal_evidence.json"))["signals"]["momentum"]["months"] > 12
    altdata.fetch_short = lambda d, get=None: None
    try:
        assert history.main(sec=FakeSEC())["status"] == "features"      # fresh table: features only
    finally:
        altdata.fetch_short = real_fetch


def test_sec_history_parsers():
    cf = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"start": "2024-01-01", "end": "2024-12-31", "val": 100, "filed": "2025-02-10"},
                                       {"start": "2025-01-01", "end": "2025-12-31", "val": 120, "filed": "2026-02-10"}]}},
        "CostOfRevenue": {"units": {"USD": [{"start": "2024-01-01", "end": "2024-12-31", "val": 60},
                                            {"start": "2025-01-01", "end": "2025-12-31", "val": 70}]}},
        "Assets": {"units": {"USD": [{"end": "2024-12-31", "val": 200}, {"end": "2025-12-31", "val": 250}]}}}}}
    assert sec.quality_history(cf) == [("2025-02-10", 0.2), ("2026-02-10", 0.2)]
    assert [r[1] for r in sec.revenue_history(cf)] == [100, 120]

    pages = {"https://data.sec.gov/submissions/CIK0000000001.json": {"filings": {
        "recent": {"form": ["8-K", "8-K", "10-Q"], "filingDate": ["2026-07-30", "2026-06-01", "2026-07-31"],
                   "items": ["2.02,9.01", "5.02", ""]},
        "files": [{"name": "CIK0000000001-submissions-001.json", "filingTo": "2020-12-31"}]}},
        "https://data.sec.gov/submissions/CIK0000000001-submissions-001.json": {
            "form": ["8-K"], "filingDate": ["2019-04-25"], "items": ["2.02"]}}
    s = sec.SEC(get=lambda url, headers=None, timeout=None: N(status_code=200, json=lambda: pages[url]))
    sec.time.sleep = lambda x: None
    assert s.earnings_dates(1, "2010-01-01") == ["2019-04-25", "2026-07-30"]
    assert s.earnings_dates(1, "2010-01-01", full=False) == ["2026-07-30"]


# ---------------------------------------------------------------- inputs
def test_sensitivities_and_dossier_limit():
    days = pd.bdate_range(end="2026-09-18", periods=780)
    r = np.random.default_rng(3)
    tnx = 42 + np.cumsum(r.normal(0, 0.6, len(days)))
    oil = 70 * np.cumprod(1 + r.normal(0, 0.02, len(days)))
    spy = 500 * np.cumprod(1 + r.normal(0.0004, 0.01, len(days)))
    px = pd.DataFrame({"^TNX": tnx, "CL=F": oil, "SPY": spy,
                       "UUP": 28 * np.cumprod(1 + r.normal(0, 0.004, len(days))),
                       "HYG": 80 * np.cumprod(1 + r.normal(0, 0.004, len(days))),
                       "IEF": 95 * np.cumprod(1 + r.normal(0, 0.003, len(days))),
                       "TIP": 108 * np.cumprod(1 + r.normal(0, 0.003, len(days)))}, index=days)
    px["OILCO"] = spy * (oil / oil[0]) ** 0.8 * np.cumprod(1 + r.normal(0, 0.005, len(days)))
    px["BANK"] = spy * np.exp((tnx - tnx[0]) / 30) * np.cumprod(1 + r.normal(0, 0.005, len(days)))
    px["NOISE"] = spy * np.cumprod(1 + r.normal(0, 0.01, len(days)))
    s = inputs.sensitivities(px, ["OILCO", "BANK", "NOISE"])
    assert s["OILCO"]["_dominant"] == "oil" and s["OILCO"]["oil"]["sign"] == "+"
    assert s["BANK"]["_dominant"] == "rates_10y" and s["BANK"]["rates_10y"]["label"] == "strong"
    assert "Dominant: oil" in inputs.sensitivity_text(s["OILCO"])
    items = [{"id": f"D{i}", "kind": "headline" if i < 30 else "metric", "text": "x" * 400} for i in range(1, 80)]
    out = inputs.limit_dossier(items, max_items=40, max_chars=9000)
    assert len(out) <= 60 and sum(len(i["text"]) for i in out) <= 9000 and out[0]["id"] == "D1"
    assert [i["id"] for i in out] == [f"D{n}" for n in range(1, len(out) + 1)]
    assert inputs.normalize_guidance("Raised FY revenue outlook") == "raised"
    assert inputs.normalize_guidance("reaffirmed guidance") == "maintained"
    assert inputs.normalize_guidance("lowered its forecast") == "lowered" and inputs.normalize_guidance("none") is None


def test_peer_table_and_valuation():
    bench = pd.DataFrame({"ticker": ["A", "B", "C", "D", "E", "F"], "sector": "Technology",
                          "sub_industry": ["Chips"] * 5 + ["Software"], "mcap": [1e10, 2e10, 5e9, 1.1e10, 9e10, 1e10],
                          "q_op_margin": 0.2, "v_ebit_yield": [0.05, 0.04, 0.06, 0.07, 0.02, 0.03], "mom_3m": 0.05,
                          "price": 50.0, "earnings_date": ["2026-10-01", None, None, None, None, None]})
    feats = {t: {"ps_now": v, "ps_pct_5y": 40, "rev_growth_%": [10.0]} for t, v in zip("ABCDEF", [3, 4, 2, 5, 9, 6])}
    vals = inputs.valuation_rows(bench, feats)
    assert vals["A"]["ps_pct_peers"] == 40 and vals["E"]["ebit_yield_pct_peers"] == 20
    assert inputs.peers(bench, "A")[0] == "D"                 # closest market cap in the same sub-industry
    out = inputs.gather(["A"], bench, feats, {"A": [{"date": "2026-07-30", "guidance": "raised"}]},
                        market=pd.DataFrame({"SPY": [1.0]}), per_ticker=(lambda t, e, p: 7.5, lambda t: 2.0))
    kinds = dict(out["A"]["items"])
    assert "±7.5%" in kinds["valuation"] and "raised 1" in kinds["track_record"] and "(this stock)" in kinds["peers"]


# ---------------------------------------------------------------- replay
def test_replay_opus_and_twin():
    pk = {"date": "2026-10-02", "ticker": "ACME", "system": "You are a judge ...", "base_p": 0.5,
          "shared": "DOSSIER: ACME (Acme)\nD1. [base_rate] b\nD2. [headline] h\nD3. [catalyst] c",
          "prompt": "ARGUMENTS:\n{\"bull\": 1}\n\nUNCITED OR INVALID CLAIMS (discount these):\n[]\n\nJSON shape:\n{}",
          "items": [{"id": "D1", "kind": "base_rate", "text": "b"}, {"id": "D2", "kind": "headline", "text": "h"},
                    {"id": "D3", "kind": "catalyst", "text": "c"}]}
    path = util.state_path("packets/2026-10-02.jsonl.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        f.write(json.dumps(pk) + "\n")
    shared, prompt, ids = replay.ablate(pk, "no_news")
    assert "headline" not in shared and ids == {"D1", "D3"}
    _, prompt2, _ = replay.ablate(pk, "no_debate")
    assert prompt2.startswith("ARGUMENTS: none") and "JSON shape" in prompt2
    ledger.record_judgments({"date": "2026-10-02", "stocks": {"ACME": {"sector": "Technology", "verdict": {
        "probability": 0.55, "base_p": 0.5, "edge_pts": 5, "judges": {}}}}}, {"ACME"})

    class Batches:
        def create(self, requests):
            self.sub = requests
            return N(id="b")

        def retrieve(self, b):
            return N(processing_status="ended")

        def results(self, b):
            out = []
            for r in self.sub:
                text = '{"adjustments": [{"points": 7, "reason": "x", "cites": ["D3"]}]}'
                out.append(N(custom_id=r["custom_id"], result=N(type="succeeded", message=N(
                    content=[N(type="text", text=text, citations=None)],
                    usage=N(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                            server_tool_use=None)))))
            return out

    fc = N(batches=Batches())
    fc.messages = fc
    s = llm.Session("replay", budget=5, anthropic_client=fc)
    assert replay.run(s, "opus")["replayed"] == 1
    assert fc.batches.sub[0]["params"]["model"] == config.OPUS
    assert replay.run(s, "opus")["replayed"] == 0                       # never replayed twice
    assert replay.run(s, "twin", "no_catalysts")["replayed"] == 1        # D3 removed -> its adjustment is dropped
    led = pd.read_csv(util.state_path("decision_ledger.csv"))
    got = dict(zip(led.judge, led.p))
    assert got["replay_opus"] == 0.57 and got["twin_no_catalysts__sonnet"] == 0.5
    assert (led[led.judge == "replay_opus"].sector == "Technology").all()


# ---------------------------------------------------------------- dossier helpers (SEC extras, scans, diffs)
def _fact(start, end, val, filed="2026-08-01"):
    r = {"end": end, "val": val, "filed": filed}
    if start:
        r["start"] = start
    return r


def test_sec_extra_metrics():
    qs = [("2025-01-01", "2025-03-31"), ("2025-04-01", "2025-06-30"), ("2025-07-01", "2025-09-30"),
          ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30")]
    rev = [_fact(a, b, v) for (a, b), v in zip(qs, [100e6, 110e6, 120e6, 125e6, 132e6])]
    rev.append(_fact("2025-01-01", "2025-12-31", 460e6))           # Q4 derived = 460 - 330 = 130
    rev.append(_fact("2025-07-01", "2026-06-30", 507e6))           # TTM helper
    gp = [_fact(a, b, v * 0.5) for (a, b), v in zip(qs, [100e6, 110e6, 120e6, 125e6, 132e6])]
    inv = [_fact(None, "2025-06-30", 50e6), _fact(None, "2026-06-30", 80e6)]
    sh = [_fact(None, "2025-07-20", 1000), _fact(None, "2026-07-20", 1050)]
    cf = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "GrossProfit": {"units": {"USD": gp}},
                                "InventoryNet": {"units": {"USD": inv}}},
                    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": sh}}}}}
    q = sec.quarterly(cf, ["Revenues"])
    assert q["2025-12-31"] == 130e6 and len(q) == 6
    ex = sec.extra_metrics(cf)
    assert ex["revenue_growth_yoy_%"] == 20.0                        # 132 vs 110
    assert ex["quarters"][-1]["gross_margin_%"] == 50.0
    assert ex["inventory_growth_yoy_%"] == 60.0 and ex["share_count_change_yoy_%"] == 5.0
    assert sec.extra_metrics({}) == {}


def test_red_flags_and_filing_diff():
    text = ("We may identify a material weakness in the future, which could hurt us. "
            "Management identified a material weakness in our controls over revenue recognition. "
            "One customer accounted for 23% of net sales in the quarter. "
            "There is substantial doubt about our ability to continue as a going concern.")
    f = sec.red_flag_scan(text)
    assert len(f["material_weakness"]) == 1 and "revenue recognition" in f["material_weakness"][0]
    assert f["going_concern"] and "23%" in f["customer_concentration"][0]
    assert not any(sec.red_flag_scan("We have no material weakness. Revenue rose sharply this quarter.").values())
    base = "Demand for our data center products remained strong across all regions this quarter. " \
           "We continue to invest in research and development to support new product launches."
    d = sec.filing_diff(base + " Revenue grew 14 percent over the prior year period on higher volumes.",
                        base + " Revenue grew 22 percent over the prior year period on higher volumes.")
    assert d["added_count"] == 0                                     # number roll-forwards don't count
    d = sec.filing_diff(base + " We now face export restrictions that could reduce sales to China materially.", base)
    assert d["added_count"] == 1 and "export restrictions" in d["added_text"] and d["unchanged_share"] < 1
    assert sec.filing_diff("", base) is None


def test_material_8k_events():
    class S(sec.SEC):
        def __init__(self):
            pass

        def recent_filings(self, cik, forms, days):
            return [{"form": "8-K", "accession": "0000-26-000001", "doc": "a.htm", "filed": "2026-09-10", "items": "5.02,9.01"},
                    {"form": "8-K", "accession": "0000-26-000002", "doc": "b.htm", "filed": "2026-09-01", "items": "2.02,9.01"}]
    ev = S().material_events(123)
    assert len(ev) == 1 and ev[0]["items"] == ["5.02"] and "executive" in ev[0]["what"]


def test_reputable_sources_and_rumors():
    from pipeline import audit
    assert audit.source_class("https://www.morningstar.com/stocks/x") == "reputable"
    assert audit.source_class("https://www.sec.gov/x") == "primary"
    assert audit.is_rumor("Deal talks, according to people familiar with the matter") and not audit.is_rumor("Q3 revenue $4B")


def test_estimates_text():
    e = {"0y": {"now": 5.5, "30d_ago": 5.0, "90d_ago": 5.0}, "revisions_30d": {"up": 7, "down": 1}}
    t = inputs.estimates_text(e)
    assert "+10.0% vs 30 days ago" in t and "7 up / 1 down" in t
    assert "not available" in inputs.estimates_text(None)


# ---------------------------------------------------------------- hidden bets, conviction sizing, critic-flag tilts
def test_clusters_conviction_and_flag_tilts():
    from pipeline import macro, pm
    idx = ["A", "B", "C", "D"]
    rc = pd.DataFrame([[1, .6, .1, .0], [.6, 1, .5, .0], [.1, .5, 1, .0], [0, 0, 0, 1]], index=idx, columns=idx)
    assert pm.clusters(idx, rc) == [["A", "B", "C"]]                      # A-B and B-C link into one group
    assert pm.clusters(idx, None) == []
    names = [f"T{i}" for i in range(16)]
    vol = {t: 0.3 for t in names}
    sec = {t: f"S{i % 5}" for i, t in enumerate(names)}
    ranges = {f"S{i}": [0, 40] for i in range(5)}
    edge = {t: (8.0 if t == "T0" else 3.0) for t in names}
    w, notes = pm.size(names, vol, sec, ranges, strength=edge)
    assert abs(w["T0"] - w["T1"]) < 1e-6                                 # edge no longer sizes (SIZE_BY_EDGE off)
    config.SIZE_BY_EDGE = True
    w, notes = pm.size(names, vol, sec, ranges, strength=edge)
    assert w["T0"] > w["T1"]                                             # with it on: higher edge -> bigger
    config.SIZE_BY_EDGE = False
    w, notes = pm.size(names, vol, sec, ranges, strength=edge, groups=[["T1", "T2", "T3", "T4", "T5"]])
    assert sum(w.get(t, 0) for t in ["T1", "T2", "T3", "T4", "T5"]) <= 20.01 and any("hidden bet" in n for n in notes)
    score = {t: (0.95 if i < 12 else 0.3) for i, t in enumerate(names)}          # mostly high-momentum names
    w, notes = pm.size(names, vol, sec, ranges, strength=edge, mom_top=score)
    stocks = {t: x for t, x in w.items() if t != pm.PARKING}
    lvl = sum(stocks[t] * score[t] for t in stocks) / sum(stocks.values())
    assert lvl <= config.MOMENTUM_MAX_LEVEL + 0.01 and any("momentum level" in n for n in notes)
    final = {s: {"tilt": 0, "note": ""} for s in config.SECTORS}
    final["Energy"]["tilt"] = -2
    moved = macro.apply_critic_flags(final, {"sectors": {"Energy": {"status": "FLAG", "issue": "double counted"},
                                                         "Utilities": {"status": "FLAG"}}})
    assert moved == ["Energy"] and final["Energy"]["tilt"] == -1 and final["Energy"]["range_%"][1] == config.TILT_RANGES[-1][1]


# ---------------------------------------------------------------- candidate signals
def test_candidate_signals():
    from pipeline import screen
    # risk-adjusted and residual momentum: a steady climber beats a jumpy one with the same return
    idx = pd.bdate_range("2025-01-01", periods=300)
    mkt = pd.Series(rng.normal(0.0004, 0.01, len(idx)), index=idx)
    steady = mkt + 0.001 + rng.normal(0, 0.002, len(idx))
    jumpy = 1.8 * mkt + 0.0003 + rng.normal(0, 0.03, len(idx))
    a = screen.risk_signals(steady, mkt, 0.3, 0.2)
    b = screen.risk_signals(jumpy, mkt, 0.3, 0.6)
    assert a["mom_riskadj"] > b["mom_riskadj"] and a["mom_resid"] > b["mom_resid"]
    assert b["vol_blend"] > a["vol_blend"] > 0
    # point-in-time fundamentals: keyed by filing date, with ROIC and margin stability
    fy = lambda y, v, f: {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "filed": f"{y + 1}-02-20"}
    cf = {"facts": {"us-gaap": {
        "OperatingIncomeLoss": {"units": {"USD": [fy(y, 100 + 10 * i, None) for i, y in enumerate(range(2019, 2025))]}},
        "Revenues": {"units": {"USD": [fy(y, 1000, None) for y in range(2019, 2025)]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fy(y, 150, None) for y in range(2019, 2025)]}},
        "StockholdersEquity": {"units": {"USD": [{"end": f"{y}-12-31", "val": 800, "filed": f"{y + 1}-02-20"} for y in range(2019, 2025)]}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2023-01-31", "val": 50, "filed": "2023-02-20"}]}}}}}
    h = sec.fundamental_history(cf)
    assert h[0][0] == "2020-02-20" and h[-1][1]["op_income"] == 150 and h[-1][1]["shares"] == 50
    assert h[-1][1]["roic"] > 0 and h[-1][1]["margin_stability"] < 0 and h[1][1]["margin_stability"] is None
    # yearly weights: a candidate with real evidence earns weight early; one without stays at zero
    ev = {"signals": {"momentum": {"mean_ic": 0.005, "t": 0.6, "months": 180},
                      "resid_momentum": {"mean_ic": 0.02, "t": 3.0, "months": 180},
                      "low_vol": {"mean_ic": -0.01, "t": -1.5, "months": 180}}}
    saved = {"set": "2026-09-26", "weights": dict(screen.PRIOR_WEIGHTS), "evidence": {"momentum": {}}}
    w, _ = screen.screen_weights(ev, saved, today=pd.Timestamp("2026-10-01").date())
    assert w["resid_momentum"] > 0.05 and w["low_vol"] == 0 and w["momentum"] < 0.25
    assert abs(sum(w.values()) - 1) < 0.01
    # family budget: a strong momentum variant only reshuffles weight inside the momentum family
    fam = lambda w: sum(w[k] for k in screen.FAMILIES["momentum"])
    base = {"signals": {k: {"mean_ic": 0.01, "t": 1.6, "months": 180} for k in ("momentum", "industry", "quality", "value")}}
    w0, _ = screen.screen_weights(base, {}, today=pd.Timestamp("2026-10-01").date())
    strong = {"signals": {**base["signals"], "high_52w": {"mean_ic": 0.03, "t": 4.0, "months": 180}}}
    w1, _ = screen.screen_weights(strong, {}, today=pd.Timestamp("2026-10-01").date())
    assert w1["high_52w"] > 0.05 and abs(fam(w1) - fam(w0)) < 0.005 and w1["momentum"] < w0["momentum"]
    # bars: 1.5 for earlier candidates, 2.0 for the newest; a stand-alone candidate past its bar takes weight
    bars = {"signals": {**base["signals"], "roic": {"mean_ic": 0.02, "t": 1.7, "months": 180},
                        "fscore": {"mean_ic": 0.02, "t": 1.8, "months": 180},
                        "net_issuance": {"mean_ic": 0.02, "t": 2.5, "months": 180},
                        "asset_growth": {"mean_ic": 0.02, "t": 1.9, "months": 180}}}
    w2, saved = screen.screen_weights(bars, {}, today=pd.Timestamp("2026-10-01").date())
    assert w2["roic"] > 0 and w2["fscore"] == 0 and w2["net_issuance"] > 0.03 and w2["asset_growth"] == 0
    assert saved["rule"] == screen.WEIGHT_RULE and abs(sum(w2.values()) - 1) < 0.01
    # weights saved under an older rule are re-set even within the year
    old = {"set": "2026-09-26", "weights": {"momentum": 0.5}, "evidence": dict(bars["signals"])}
    w3, s3 = screen.screen_weights(bars, old, today=pd.Timestamp("2026-10-01").date())
    assert s3["rule"] == screen.WEIGHT_RULE and w3["momentum"] < 0.5

    # F-score, share issuance and asset growth from filings, point in time
    def fyv(y, v):
        return {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "filed": f"{y + 1}-02-20"}

    def inst(vals):
        return {"units": {"USD": [{"end": f"{y}-12-31", "val": v, "filed": f"{y + 1}-02-20"} for y, v in vals.items()]}}
    cf2 = {"facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [fyv(2022, 50), fyv(2023, 80)]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fyv(2022, 60), fyv(2023, 100)]}},
        "Revenues": {"units": {"USD": [fyv(2022, 1000), fyv(2023, 1200)]}},
        "GrossProfit": {"units": {"USD": [fyv(2022, 300), fyv(2023, 400)]}},
        "OperatingIncomeLoss": {"units": {"USD": [fyv(2022, 70), fyv(2023, 100)]}},
        "Assets": inst({2022: 1000, 2023: 1100}), "LongTermDebt": inst({2022: 300, 2023: 250}),
        "AssetsCurrent": inst({2022: 400, 2023: 500}), "LiabilitiesCurrent": inst({2022: 200, 2023: 200}),
        "StockholdersEquity": inst({2022: 500, 2023: 600})},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2023-01-31", "val": 100, "filed": "2023-02-20"}, {"end": "2024-01-31", "val": 95, "filed": "2024-02-20"}]}}}}}
    fs = sec.fscores(cf2)
    assert fs["2023-12-31"][0] == 9 and "2022-12-31" not in fs          # every test passes; 2022 has no prior year
    h2 = sec.fundamental_history(cf2)[-1][1]
    assert h2["fscore"] == 9 and h2["share_growth"] == -0.05 and h2["asset_growth"] == 0.1
    m2 = sec.extract_metrics(cf2)
    assert m2["fscore"] == 9 and m2["share_growth"] == -0.05 and m2["asset_growth"] == 0.1


# ---------------------------------------------------------------- judge-side fixes
def test_exit_check_sharpening_and_optional_features():
    from pipeline import team
    lv = {"DGS10": {"latest": 5.18}, "DCOILBRENTEU": {"latest": 114.9}, "BAMLH0A0HYM2": {"latest": 2.8}}
    assert "already 5.18" in team.exit_already_met("Sell if the 10-yr yield rises above 4.5%", lv)
    assert team.exit_already_met("Exit if the 10-year yield rises above 5.5%", lv) is None
    assert team.exit_already_met("exit if Brent falls below $120", lv)
    assert team.exit_already_met("exit if high-yield spreads widen over 350 bps", lv) is None
    assert team.exit_already_met("guidance cut below $7.91", lv) is None
    v = team.combine({"a": {"probability": 0.55}, "b": {"probability": 0.56}},
                     [{"id": "a", "model": "m", "live": True}, {"id": "b", "model": "m", "live": True}], [], 0.50)
    assert v["probability_sharp"] > v["probability"] > 0.5                  # pushed further from the base rate
    ev = {"signals": {"value": {"t": 2.4}, "low_vol": {"t": 0.8}}}
    assert history.table_features(ev) == ("m", "e", "q", "v")
    df = pd.DataFrame({"date": ["2020-01-31"] * 400, "m": [1, 5] * 200, "e": [0] * 400, "q": [3] * 400,
                       "v": [1, 5] * 200, "beat": [0, 1] * 200})
    tab = history.build_table(df, features=("m", "e", "q", "v"))
    assert tab["features"] == ["m", "e", "q", "v"] and "e=0|m=5|q=3|v=5" in tab["groups"]
    b = history.lookup(tab, {"m": 5, "e": 0, "q": 3, "v": 5, "l": 2}, min_group=50)
    assert b["group"] == "e=0|m=5|q=3|v=5" and "value" in history.describe(b)


def test_alt_signals():
    from datetime import date
    from pipeline import altdata, screen
    # FINRA file (pipe-separated, FINRA's column names) -> days to cover; point in time with a 10-day lag
    text = ("accountingYearMonthNumber|symbolCode|issueName|currentShortPositionQuantity|averageDailyVolumeQuantity|"
            "daysToCoverQuantity|settlementDate\n" + "\n".join(f"20260915|S{i:02d}|Co|{1000 * i}|1000|{i}|2026-09-15"
                                                            for i in range(1, 40)) + "\n20260915|BRK.B|Berk|500|1000||2026-09-15")
    got = altdata.parse_short_file(text)
    assert got["S05"] == 5 and got["BRKB"] == 0.5                  # missing days-to-cover computed from short / volume

    class R:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append(url)
        return R(200, text) if url.endswith(("20260915.csv", "20260831.csv")) else R(404)
    hist = {}
    altdata.SHORT_START = date(2026, 8, 1)
    n = altdata.refresh_short_history(hist, get=fake_get, today=date(2026, 9, 27), sleep=0)
    assert n == 2 and set(hist["files"]) == {"2026-08-31", "2026-09-15"}
    k = len(calls)
    altdata.refresh_short_history(hist, get=fake_get, today=date(2026, 9, 27), sleep=0)
    assert not any(u.endswith(("20260915.csv", "20260831.csv")) for u in calls[k:])   # found files not re-downloaded
    assert altdata.short_at(hist, "2026-09-20") == hist["files"]["2026-08-31"]   # Sep 15 file not public until ~Sep 25
    assert altdata.short_at(hist, "2026-09-26")["S05"] == 5
    # Lazy Prices: similarity of consecutive 10-Ks, saved by filing date
    docs = {"a1": "revenue grew strongly customers loyal margins stable " * 50,
            "a2": "revenue grew strongly customers loyal margins stable " * 50,
            "a3": "litigation investigation material weakness restatement impairment going concern " * 50}

    class FakeSEC:
        def get(self, url, as_json=True):
            return {"filings": {"recent": {"form": ["10-K", "10-K", "10-K", "8-K"], "accessionNumber": ["a1", "a2", "a3", "x"],
                                           "primaryDocument": ["d", "d", "d", "d"],
                                           "filingDate": ["2023-02-20", "2024-02-20", "2025-02-20", "2025-03-01"]}}}

        def document_text(self, cik, acc, doc):
            return docs[acc]
    st = altdata.update_lazy(FakeSEC(), [("AAA", 1)], minutes=1)
    sims = dict(st["companies"]["AAA"]["sims"])
    assert st["complete"] and sims["2024-02-20"] > 0.99 and sims["2025-02-20"] < 0.1
    lh = altdata.lazy_history(st)
    assert altdata.lazy_at(lh, "AAA", "2024-06-30") > 0.99 and altdata.lazy_at(lh, "AAA", "2025-06-30") < 0.1
    assert altdata.lazy_at(lh, "AAA", "2023-06-30") is None
    # frog in the pan: the same 12-month gain from steady small moves beats one from a jump
    mom = pd.Series({"steady": 0.3, "jumpy": 0.3, "loser": -0.2})
    fp = history.frog(mom, pd.Series({"steady": -0.3, "jumpy": 0.2, "loser": -0.3}))
    assert fp["steady"] > fp["jumpy"] > 0 > fp["loser"]
    # all three are candidates at the stricter bar; frog shares the momentum budget
    assert "frog_momentum" in screen.FAMILIES["momentum"] and screen.t_min("low_short") == 2.0
    assert all(screen.PRIOR_WEIGHTS[k] == 0 for k in ("frog_momentum", "low_short", "filing_similarity"))


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")
