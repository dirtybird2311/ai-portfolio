"""
Offline test of the council replay (python -m pipeline.replay council): past packets get the investor council's
notes and a shadow council-judge forecast, recorded under the original decision date.
Run:  python -m pytest tests/  (or)  python tests/test_replay_council.py
"""
import gzip
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import pandas as pd  # noqa: E402

from pipeline import config, replay, team, util  # noqa: E402

N = types.SimpleNamespace


def packet(t):
    items = [{"id": "D1", "kind": "base_rate", "text": "Base rate 48%"}, {"id": "D2", "kind": "news", "text": "beat"}]
    shared = team.dossier_text(t, t, items)
    args = {"bull_open": {"points": [{"claim": "beat", "cites": ["D2"]}], "summary": "s"}, "model": "x"}
    prompt = (f"ARGUMENTS:\n{json.dumps({k: v for k, v in args.items() if k != 'model'})}\n\n"
              f"UNCITED OR INVALID CLAIMS (discount these):\n[]\n\nJSON shape:\n{team.JUDGE_SHAPE}")
    return {"date": "2026-11-01", "ticker": t, "system": team.JUDGE_SYSTEM, "shared": shared, "prompt": prompt,
            "base_p": 0.48, "items": items, "args": args}


class FakeSession:
    def __init__(self):
        self.asked, self.reqs = [], []

    def ask(self, role, system, prompt, **kw):
        self.asked.append(role)
        note = {"stance": "favor", "points": [{"claim": "cheap", "cites": ["D1"]}, {"claim": "x", "cites": ["D9"]}],
                "summary": "s"}
        return N(data={m["id"]: note for m in config.COUNCIL})

    def batch(self, reqs, **kw):
        self.reqs = reqs
        v = {"adjustments": [{"points": 2, "reason": "cheap", "cites": ["D1"]}], "probability": 0.5, "winner": "bull",
             "thesis": "t", "key_risk": "k", "exit_condition": "x", "primary_driver": "d", "evidence": ["D1"]}
        return {r["id"]: N(data=v) for r in reqs}


def test_council_replay_records_shadow_forecasts_on_the_original_date():
    d = util.state_path("packets")
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "2026-11-01.jsonl.gz", "wt") as f:
        for t in ("AAA", "BBB"):
            f.write(json.dumps(packet(t)) + "\n")
    s = FakeSession()
    out = replay.run(s, "council", since="2026-11-01")
    assert out["replayed"] == 2 and s.asked == ["council", "council"]
    r = s.reqs[0]
    assert r["model"] == config.COUNCIL_JUDGE["model"] and team.COUNCIL_HEADER in r["prompt"] and "D9" in r["prompt"]
    led = pd.read_csv(util.state_path("decision_ledger.csv"))
    assert set(led.judge) == {"sonnet_council"} and set(led.date) == {"2026-11-01"} and not led.live.any()
    assert set(util.read_json(util.state_path("council_notes_2026-11-01.json"))) == {"AAA", "BBB"}
    assert replay.run(FakeSession(), "council", since="2026-11-01")["replayed"] == 0     # nothing twice


if __name__ == "__main__":
    test_council_replay_records_shadow_forecasts_on_the_original_date()
    print("PASS test_council_replay_records_shadow_forecasts_on_the_original_date")
