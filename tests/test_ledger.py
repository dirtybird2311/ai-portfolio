"""
Offline tests for the judge panel's probability rules, the decision ledger, grading against the
equal-weighted sector, evaluation (IC, Brier vs the base rate, calibration, sells, critic, pruning,
macro vs its momentum opponent) and the pre-registered decision rules. Synthetic data only.
Run:  python -m pytest tests/  (or)  python tests/test_ledger.py
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY"):
    os.environ[k] = "test"
for k in ("GEMINI_PAID_API_KEY", "NVIDIA_API_KEY"):
    os.environ.pop(k, None)

from pipeline import config, ledger, team, track, util  # noqa: E402

PANEL = [{"id": "a", "model": config.SONNET, "live": True}, {"id": "b", "model": config.GPT_SOL, "live": True},
         {"id": "c", "model": config.GEMINI_PRO, "live": True}, {"id": "s", "model": config.MISTRAL_LARGE, "live": False}]
IDS = {"D1", "D2", "D3"}


def V(p, base=0.5, **kw):
    """A cleaned single-judge forecast at probability p."""
    return team.clean_verdict(dict({"adjustments": [{"points": round((p - base) * 100, 1), "reason": "x", "cites": ["D1"]}],
                                    "thesis": f"thesis {p}", "exit_condition": "e", "primary_driver": "d",
                                    "exception": abs(p - base) > 0.15, "exception_reason": "big news"}, **kw), IDS, base)


# ---------------------------------------------------------------- one judge's forecast
def test_clean_verdict_rebuilds_the_probability():
    v = team.clean_verdict({"adjustments": [{"points": 6, "cites": ["D1"]}, {"points": 5, "cites": ["D9"]},
                                            {"points": "lots", "cites": ["D2"]}], "probability": 0.9}, IDS, 0.48)
    assert v["probability"] == 0.54 and v["edge_pts"] == 6.0 and v["dropped_adjustments"] == 2
    assert v["stated_probability"] == 0.9                        # the judge's own number is ignored
    capped = team.clean_verdict({"adjustments": [{"points": 40, "cites": ["D1"]}]}, IDS, 0.5)
    assert capped["probability"] == 0.65 and not capped["exception"]
    exc = team.clean_verdict({"adjustments": [{"points": 30, "cites": ["D1"]}], "exception": True,
                              "exception_reason": "takeover bid at a 30% premium"}, IDS, 0.5)
    assert exc["probability"] == 0.8 and exc["exception"]
    bare = team.clean_verdict({"probability": 0.7}, IDS, 0.47)  # no itemized adjustments -> stays at the base rate
    assert bare["probability"] == 0.47 and bare["edge_pts"] == 0
    assert team.clean_verdict("x", IDS) is None and team.clean_verdict({"thesis": "t"}, IDS) is None
    assert team.clean_verdict({"adjustments": [{"points": -80, "cites": ["D1"]}], "exception": True,
                               "exception_reason": "fraud"}, IDS, 0.5)["probability"] == config.PROB["clip"][0]


# ---------------------------------------------------------------- panel
def test_combine_log_odds_live_only():
    v = team.combine({"a": V(0.60), "b": V(0.55), "c": V(0.58), "s": V(0.20)}, PANEL, [], 0.5)
    x = np.mean([np.log(p / (1 - p)) for p in (0.60, 0.55, 0.58)])
    assert abs(v["probability"] - round(1 / (1 + np.exp(-x)), 4)) < 1e-9
    assert v["edge_pts"] == round((v["probability"] - 0.5) * 100, 1) and v["lead_judge"] == "c"
    assert v["spread"] == 5.0 and not v["disagreement"] and v["judges"]["s"]["live"] is False
    d = team.combine({"a": V(0.66), "b": None, "c": V(0.50), "s": V(0.5)}, PANEL, ["bad"], 0.5)
    assert d["disagreement"] and d["live_judges"] == ["a", "c"] and d["judges"]["b"]["probability"] is None
    dead = team.combine({"a": None, "b": None, "c": None, "s": V(0.7)}, PANEL, [], 0.46)
    assert dead["panel_failed"] and dead["probability"] == 0.46 and dead["conviction"] == 1


def test_sampling_and_key_skipping():
    half = {"id": "h", "sample": 0.5}
    picked = [t for t in (f"T{i}" for i in range(200)) if team.in_sample(half, t, "2026-09-25")]
    assert 70 < len(picked) < 130
    active = [j["id"] for j in team.active_panel()]
    assert {"sonnet", "gpt_sol", "grok"} <= set(active)
    assert "gemini_pro" not in active and "deepseek" not in active and "opus" not in active


# ---------------------------------------------------------------- ledger -> grades -> evaluation
def world(n_dates=10, n_names=16, seed=1):
    """Judge 'a' (live) has real skill beyond the base rate; 's' (shadow) is noise. Base rates carry a
    little signal of their own. The universe has two sectors of extra names for the equal-weighted
    benchmark."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-01-02", periods=n_dates * 10 + 90)
    names = [f"N{i:02d}" for i in range(n_names)]
    extra = [f"X{i:02d}" for i in range(20)]
    sector_of = {t: ("Technology" if i % 2 else "Energy") for i, t in enumerate(names + extra)}
    px = pd.DataFrame(index=days)
    px["SPY"] = 100 * np.cumprod(1 + rng.normal(0.0003, 0.008, len(days)))
    for etf in ("XLK", "XLE"):
        px[etf] = px["SPY"] * np.cumprod(1 + rng.normal(0, 0.002, len(days)))
    drift = {t: rng.normal(0, 1) for t in names}
    for t in names:
        px[t] = px["SPY"] * np.cumprod(1 + drift[t] * 0.002 + rng.normal(0, 0.004, len(days)))
    for t in extra:
        px[t] = px["SPY"] * np.cumprod(1 + rng.normal(0, 0.004, len(days)))
    runs = []
    for k in range(n_dates):
        d = days[k * 10].date().isoformat()
        stocks = {}
        for t in names:
            base = float(np.clip(0.48 + 0.01 * drift[t] + rng.normal(0, 0.01), 0.35, 0.6))
            good = float(np.clip(base + 0.06 * drift[t] + rng.normal(0, 0.02), 0.05, 0.95))
            per = {"a": V(good, base), "b": V(good, base), "c": V(good, base), "s": V(float(rng.uniform(0.3, 0.7)), base)}
            verdict = team.combine(per, PANEL, [], base)
            stocks[t] = {"sector": sector_of[t], "incumbent": False, "composite": 0.5, "price": 50.0, "news": {"score": 0},
                         "verdict": verdict, "base_rate": {"p": base, "group": "m=3"}, "sensitivity": {"_dominant": "oil"},
                         "dossier": [{"id": "D1", "kind": "catalyst",
                                      "text": f"{days[k * 10 + 3].date()}: Earnings (impact: positive; source: primary)"}]}
        runs.append({"date": d, "stocks": stocks, "versions": util.version_stamp("prompt")})
    return px, runs, sector_of, days


def test_ledger_grades_and_finds_the_skilled_judge():
    px, runs, sector_of, days = world()
    for r in runs:
        ledger.record_judgments(r, set(r["stocks"]))
        ledger.record_process_errors(r)
    led = pd.read_csv(util.state_path("decision_ledger.csv"))
    assert set(led.judge) == {"a", "b", "c", "s", "panel", "panel_sharp", "base_rate"} and len(led) == 10 * 16 * 7
    assert ledger.pending()
    n = ledger.grade(px, sector_of)
    assert n > 0 and ledger.grade(px, sector_of) == 0              # idempotent
    g = pd.read_csv(util.state_path("grades.csv"), dtype={"date": str})
    assert set(g.horizon) == {"2w", "4w", "13w"} and (g.benchmark == "equal-weighted sector").all()
    r0 = g.iloc[0]
    assert abs(r0.resid - (r0.ret - r0.sector_ew)) < 1e-4 and pd.Timestamp(r0.start) > pd.Timestamp(r0.date)
    # a replayed Opus and a twin without the debate, recorded later with the original dates
    rows = []
    for r in runs:
        for t, s in r["stocks"].items():
            rows.append({"date": r["date"], "ticker": t, "judge": "replay_opus", "model": config.OPUS,
                         "p": s["verdict"]["judges"]["s"]["probability"]})
            rows.append({"date": r["date"], "ticker": t, "judge": "twin_no_debate__a", "model": config.SONNET,
                         "p": s["verdict"]["base_p"]})                    # the twin adds nothing over the base rate
    assert ledger.record_replay(rows) == len(rows) and ledger.record_replay(rows) == 0
    ev = ledger.evaluate()
    four = ev["judges"]["4w"]
    assert four["a"]["mean_ic"] > 0.3 and four["panel"]["mean_ic"] > 0.3 and abs(four["s"]["mean_ic"]) < four["a"]["mean_ic"]
    b = ev["brier"]["4w"]
    assert b["scores"]["panel"] < b["scores"]["base_rate"] and b["panel_vs_base"]["improvement"] > 0
    assert ev["calibration"]["4w"] and all("actual_%" in c for c in ev["calibration"]["4w"])
    assert ev["pruning"]["twin_no_debate__a"]["improvement"] > 0      # the section helps the live judge
    assert ev["combos"]["4w"]["tested"] >= 11 and ev["catalysts"]["graded"] > 0
    md = ledger.render_md(ev)
    assert "Panel vs base rate" in md and "| panel |" in md and "Pruning test" in md and "<table" in ledger.render_html(ev)


def test_decision_rule_needs_both_tests():
    first = "2026-01-02"
    good_b = {"n": 900, "improvement": 0.004, "t": 2.5}
    weak_b = {"n": 900, "improvement": 0.0005, "t": 0.6}
    ev = lambda ic, t, n, b: {"first_decision": first, "judges": {"4w": {"panel": {"dates": n, "mean_ic": ic, "t": t}}},
                              "brier": {"4w": {"panel_vs_base": b}}}
    R = ledger.decision_rule
    assert R(ev(0.08, 2.8, 8, good_b), today=date(2026, 2, 15))["verdict"] == "collecting"
    assert R(ev(0.08, 2.8, 8, good_b), today=date(2026, 4, 10))["verdict"] == "continue"      # 2.8 < 3.0 at look 1
    assert R(ev(0.08, 2.8, 12, good_b), today=date(2026, 7, 10))["verdict"] == "EDGE CONFIRMED"
    assert R(ev(0.08, 2.8, 12, weak_b), today=date(2026, 7, 10))["verdict"] == "STATISTICS ONLY"
    assert R(ev(-0.01, -0.3, 12, weak_b), today=date(2026, 7, 10))["verdict"] == "NO EDGE (futility)"
    assert R(ev(0.02, 1.5, 24, weak_b), today=date(2027, 1, 10))["verdict"] == "NOT PROVEN"


def test_sells_critic_macro_and_reminders():
    px, runs, sector_of, days = world(seed=3)
    for f in ("decision_ledger.csv", "grades.csv"):
        if util.state_path(f).exists():
            util.state_path(f).unlink()
    for r in runs:
        ledger.record_judgments(r, set(r["stocks"]))
        ledger.record_sells(r["date"], [{"ticker": "N00", "action": "sold", "reason": "x"},
                                        {"ticker": "N01", "action": "kept", "reason": ""}])
        ledger.record_critic(r["date"], [{"ticker": "N02", "account": "ira", "action": "BUY", "critic": "PASS", "status": "approved"},
                                         {"ticker": "N03", "account": "ira", "action": "BUY", "critic": "FLAG", "status": "flagged"}])
        mom = {s: {"etf": e, "base_p": 0.5, "p": 0.6 if s == "Energy" else 0.45, "disagreement_pts": 1, "tilt": 0,
                   "momentum_rank": i + 1, "momentum_p": 0.6 - i * 0.02} for i, (s, e) in enumerate(config.SECTORS.items())}
        ledger.record_macro(r["date"], mom)
    for etf in config.SECTORS.values():
        if etf not in px:
            px[etf] = px["SPY"] * (1 + 0.0001 * np.arange(len(px)))
    ledger.grade(px, sector_of)
    ev = ledger.evaluate(today=date(2026, 9, 1))
    assert ev["sells"]["n_sold"] > 0 and ev["sells"]["n_kept"] > 0
    assert ev["critic"]["n_approved"] > 0 and ev["critic"]["n_flagged"] > 0
    m = ev["macro"]
    assert m["4w"]["macro_ic"]["dates"] > 0 and m["rule"]["verdict"] == "collecting"
    assert ledger.macro_rule(m, today=date(2027, 3, 1))["verdict"].startswith(("keep", "REVERT"))
    old = config.REPLAY["opus"]["retires"]
    config.REPLAY["opus"]["retires"] = "2026-10-15"
    try:
        assert "replay opus" in ledger.replay_warnings(today=date(2026, 9, 25))[0]
    finally:
        config.REPLAY["opus"]["retires"] = old


def test_error_feedback_text():
    ledger.record_process_errors({"date": "2099-01-01", "stocks": {
        "A": {"verdict": {"invalid_citations": ["x", "y"], "exit_condition": "e",
                          "judges": {"a": {"probability": None}, "b": {"probability": 0.5, "dropped_adjustments": 3}}}}}})
    fb = ledger.error_feedback()
    assert "2 debate claims" in fb and "1 judge replies" in fb and "3 probability adjustments" in fb


# ---------------------------------------------------------------- control portfolios
def test_control_portfolios():
    mk = lambda p, e, c=0.5: {"verdict": {"probability": p, "edge_pts": e, "conviction": 3}, "composite": c}
    st = {"A": mk(0.60, 9), "B": mk(0.55, 4), "C": mk(0.58, 6), "D": mk(0.49, 8), "E": mk(0.52, 1)}
    eq, nm = track.control_portfolios({"stocks": st}, {"A": 10.0, "B": 30.0, "SPY": 60.0})
    assert eq == {"A": 20.0, "B": 20.0, "SPY": 60.0}
    assert nm == {"A": 50.0, "C": 50.0}          # top edges among buyable names (D is under 50%, E's edge too small)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")
