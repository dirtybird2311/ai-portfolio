"""
Offline tests for the edge tests (pipeline/edgetest.py) on made-up history.
Run:  python -m pytest tests/  (or)  python tests/test_edgetest.py
"""
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import edgetest as et  # noqa: E402


def world(seed=0, months=96):
    """3 sectors x 20 stocks of daily prices. 'value' stocks drift up steadily (a slow signal); stocks whose peers
    just reported well, and stocks insiders bought, rise over the following weeks."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2012-01-02", periods=months * 21 + 260)
    tick = [f"S{s}T{i}" for s in range(3) for i in range(20)]
    val = {t: rng.normal() for t in tick}
    r = pd.DataFrame(rng.normal(0, 0.01, (len(days), len(tick))), index=days, columns=tick)
    for t in tick:
        r[t] += 0.0004 * val[t]
    ends = [days[k * 21 + 20] for k in range(months)]
    reactions, buys = {}, []
    for k, d in enumerate(ends):
        i = days.get_loc(d)
        for s in range(3):
            lead, good = f"S{s}T{k % 5}", rng.normal(0, 0.05)
            reactions.setdefault(lead, []).append(((d - pd.Timedelta(days=10)).date().isoformat(), round(good, 4)))
            for t in tick:
                if t.startswith(f"S{s}T") and t != lead:
                    r.iloc[i + 2:i + 22, r.columns.get_loc(t)] += good * 0.02
        for t in rng.choice(tick, 6, replace=False):
            n = 3 if rng.random() < 0.5 else 1
            for o in range(n):
                buys.append({"cik": tick.index(t) + 1, "filed": (d - pd.Timedelta(days=5 + o)).date().isoformat(),
                             "owner": f"o{o}", "value": 100000.0})
            r.iloc[i + 2:i + 62, r.columns.get_loc(t)] += 0.001 * n
    px = (1 + r).cumprod() * 50
    rows = [{"date": d.date().isoformat(), "ticker": t, "sector": t[:2], "value_raw": val[t], "mom_raw": rng.normal()}
            for d in ends for t in tick]
    df = pd.DataFrame(rows)
    sub_of = {t: t[:2] for t in tick}
    cik_of = {t: i + 1 for i, t in enumerate(tick)}
    return df, px, reactions, sub_of, pd.DataFrame(buys), cik_of


def test_three_edges_are_found_where_they_exist_and_only_there():
    df, px, reactions, sub_of, buys, cik_of = world()
    start = sorted(df["date"].unique())[12]
    res = et.run(df, px, {"value": 0.5, "momentum": 0.5}, start, reactions, sub_of, buys, cik_of)
    h = res["horizons"]
    assert set(h["Current screen"]) == {"1 month", "3 months", "6 months"}
    assert h["Value alone"]["6 months"]["t"] > 3 and abs(h["12-month momentum alone"]["1 month"]["t"]) < 3
    assert h["Value alone"]["6 months"]["periods"] < h["Value alone"]["1 month"]["periods"] / 4    # no overlapping windows
    assert h["Value alone"]["1 month"]["after_costs"] <= h["Value alone"]["1 month"]["excess"]
    ra = res["read_across"]
    assert ra["coverage"] > 0.5 and ra["horizons"]["1 month"]["ic"]["t"] > 3 and ra["horizons"]["1 month"]["spread"]["mean"] > 0
    ins = res["insider"]["flags"]
    c3, any1 = ins["Cluster: 3 or more insiders bought"], ins["Any officer or director bought (last 90 days)"]
    assert c3["3 months"]["t"] > 3 and c3["3 months"]["mean"] > any1["3 months"]["mean"] > 0 and 0 < c3["share"] < any1["share"]
    md = et.report(res)
    assert "Holding period" in md and "Insider buying" in md and "Read-across" in md


def test_read_across_only_uses_peers_that_reported_after_the_stock_itself():
    df = pd.DataFrame({"date": ["2020-03-31"] * 3, "ticker": ["A", "B", "C"], "sector": ["X"] * 3})
    reactions = {"A": [("2020-03-10", 0.10)], "B": [("2020-03-20", -0.04)], "C": [("2020-01-05", 0.5), ("2020-03-30", 0.9)]}
    ra = et.read_across_raw(df, reactions, {"A": "s", "B": "s", "C": "s"})
    # A: B reported later (-0.04). B: nobody reported after it (C's Mar 30 report is too fresh to have a reaction).
    # C's own last settled report is from January, outside the window; both peers reported after it: mean 0.03.
    assert abs(ra[0] + 0.04) < 1e-9 and np.isnan(ra[1]) and abs(ra[2] - 0.03) < 1e-9


def test_insider_file_keeps_only_open_market_buys_by_officers_and_directors():
    def tsv(rows):
        return "\n".join("\t".join(r) for r in rows) + "\n"
    files = {
        "SUBMISSION.tsv": tsv([["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"],
                               ["a1", "15-MAR-2020", "0000000111", "AAA"], ["a2", "16-MAR-2020", "111", "AAA"],
                               ["a3", "17-MAR-2020", "111", "AAA"], ["a4", "18-MAR-2020", "999", "ZZZ"]]),
        "REPORTINGOWNER.tsv": tsv([["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"],
                                   ["a1", "7", "Director"], ["a2", "8", "TenPercentOwner"], ["a3", "9", "Officer,Director"],
                                   ["a4", "7", "Officer"]]),
        "NONDERIV_TRANS.tsv": tsv([["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"],
                                   ["a1", "P", "100", "10", "A"], ["a1", "P", "50", "10", "A"], ["a2", "P", "100", "10", "A"],
                                   ["a3", "S", "100", "10", "D"], ["a3", "A", "100", "0", "A"], ["a4", "P", "100", "10", "A"]]),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, t in files.items():
            z.writestr(n, t)
    m = et.parse_insider_zip(buf.getvalue(), {111})
    assert m.to_dict("records") == [{"cik": 111, "filed": "2020-03-15", "owner": "7", "value": 1500.0}]

    class R:
        status_code, content = 200, buf.getvalue()
    calls = []
    got = et.insider_history({111}, {}, start="2025q1", get=lambda url, **k: calls.append(url) or R())
    assert len(got) == len(calls) and len(calls) >= 6 and all("form345.zip" in u for u in calls)
    n = len(calls)
    et.insider_history({111}, {}, start="2025q1", get=lambda url, **k: calls.append(url) or R())
    assert len(calls) == n                                                   # cached quarters are not fetched again


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
