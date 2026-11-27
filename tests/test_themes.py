"""
Offline tests for the theme cap and the event calendar the PM sees.
Run:  python -m pytest tests/  (or)  python tests/test_themes.py
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

from pipeline import config, macro, pm  # noqa: E402


def test_theme_cap_limits_a_cross_sector_theme():
    names = ["SEI", "MU", "ECG", "ALL", "ADM", "DLTR", "DXCM", "VCTR"]
    sector = {"SEI": "Energy", "MU": "Technology", "ECG": "Industrials", "ALL": "Financials", "ADM": "Consumer Staples",
              "DLTR": "Consumer Staples", "DXCM": "Health Care", "VCTR": "Financials"}
    vol = {t: 0.3 for t in names}
    strength = {"SEI": 6, "MU": 6, "ECG": 6, "ALL": 2, "ADM": 2, "DLTR": 2, "DXCM": 2, "VCTR": 2}
    ranges = {s: [0, 45] for s in set(sector.values())}
    pick = {"portfolio": [{"ticker": t, "theme": "ai_datacenter_buildout" if t in ("SEI", "MU", "ECG") else "nonsense"}
                          for t in names]}
    th = pm.themes_of(pick)
    assert th["ai_datacenter_buildout"] == ["SEI", "MU", "ECG"] and "nonsense" not in th
    free, _ = pm.size(names, vol, sector, ranges, strength=strength)
    capped, notes = pm.size(names, vol, sector, ranges, strength=strength, themes=th)
    assert sum(free[t] for t in ("SEI", "MU", "ECG")) > config.THEME_CAP + 1
    assert sum(capped[t] for t in ("SEI", "MU", "ECG")) <= config.THEME_CAP + 0.05
    assert any(n.startswith("theme ai_datacenter_buildout") for n in notes)


def test_upcoming_events_merge_macro_calendar_and_earnings():
    today = dt.date(2026, 11, 20)
    mv = {"upcoming_events": [{"date": "2026-12-01", "event": "Texas data-center moratorium vote", "exposed": ["ai_datacenter_buildout"]},
                              {"date": "2027-03-01", "event": "too far", "exposed": []}]}
    team = {"stocks": {"MU": {"dossier": [{"kind": "catalyst", "text": "2026-12-17: Scheduled earnings report (impact: uncertain)"}]}}}
    ev = pm.upcoming_events(mv, team, today)
    names = [e["event"] for e in ev]
    assert "Texas data-center moratorium vote" in names and "too far" not in names
    assert any(n.startswith("FOMC") for n in names) and "MU: Scheduled earnings report" in names
    assert [e["date"] for e in ev] == sorted(e["date"] for e in ev)


def test_macro_events_are_merged_once():
    runs = [{"upcoming_events": [{"date": "2026-12-09", "event": "FOMC decision", "exposed": ["rates"]}]},
            {"upcoming_events": [{"date": "2026-12-09", "event": "FOMC Decision", "exposed": ["rates"]},
                                 {"date": "bad", "event": "x"}]}]
    assert macro.merge_events(runs) == [{"date": "2026-12-09", "event": "FOMC decision", "exposed": ["rates"]}]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
