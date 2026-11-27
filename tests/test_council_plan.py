"""
Offline tests for the council portfolio sandbox (pipeline/council_plan.py) and the shadow books
(pipeline/shadowbooks.py).  Run:  python -m pytest tests/  (or)  python tests/test_council_plan.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import pandas as pd  # noqa: E402

from pipeline import council_plan, shadowbooks, util  # noqa: E402


def team(p_sonnet, p_gpt, p_gem, base=0.5):
    judges = {"sonnet": {"probability": p_sonnet}, "gpt_sol": {"probability": p_gpt}, "gemini_pro": {"probability": p_gem}}
    return {"verdict": {"probability": 0.5, "base_p": base, "edge_pts": 0.0, "live_judges": ["sonnet", "gpt_sol", "gemini_pro"],
                        "judges": judges}}


def test_council_verdicts_swap_only_the_sonnet_judge():
    res = {"date": "2026-11-01", "stocks": {"A": team(0.50, 0.55, 0.60), "B": team(0.50, 0.50, 0.50)}}
    out = council_plan.council_verdicts(res, {"A": 0.70})
    lg = lambda p: math.log(p / (1 - p))
    want = 1 / (1 + math.exp(-(lg(0.70) + lg(0.55) + lg(0.60)) / 3))
    assert abs(out["stocks"]["A"]["verdict"]["probability"] - round(want, 4)) < 1e-9
    assert abs(out["stocks"]["A"]["verdict"]["edge_pts"] - (want - 0.5) * 100) < 0.06
    assert out["stocks"]["B"]["verdict"]["probability"] == 0.5 and "council_variant" not in out["stocks"]["B"]["verdict"]
    assert res["stocks"]["A"]["verdict"]["probability"] == 0.5          # the real results are untouched
    assert out["council_variant"]["stocks"] == 1


def test_shadow_book_rebalances_at_the_open_and_tracks_spy():
    days = pd.to_datetime(["2026-11-02", "2026-11-03", "2026-11-04"])
    open_ = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [20.0, 20.0, 20.0], "SPY": [100.0, 100.0, 100.0]}, index=days)
    close = pd.DataFrame({"A": [11.0, 12.0, 12.0], "B": [20.0, 20.0, 22.0], "SPY": [101.0, 102.0, 103.0]}, index=days)
    shadowbooks.add_segment("t", "2026-11-02", {"A": 50, "B": 50})
    shadowbooks.add_segment("t", "2026-11-04", {"B": 100})
    shadowbooks.add_segment("t", "2026-11-04", {"B": 100})          # a rerun replaces, never stacks
    b = shadowbooks.load()["books"]["t"]
    assert len(b["segments"]) == 2
    s = shadowbooks.series(b, close, open_)
    assert abs(s["value"].iloc[0] - (500 * 11 + 250 * 20)) < 1e-6        # 500 A + 250 B on day one
    v_open = 500 * 12 + 250 * 20                                         # value at the Nov 4 open, all into B
    assert abs(s["value"].iloc[-1] - v_open / 20 * 22) < 1e-6
    assert abs(s["spy"].iloc[-1] - 10000 * 103 / 100) < 1e-6
    out = shadowbooks.write_all(close, open_)
    assert abs(out["t"]["return_pct"] - round((v_open / 20 * 22 / 10000 - 1) * 100, 2)) < 1e-9
    assert util.state_path("daily_nav_shadow_t.csv").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
