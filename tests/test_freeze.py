"""
The parameter freeze log (pipeline/freeze.py): the settings that shape the picks must match the logged baseline.
If this fails you changed a setting: run  python -m pipeline.freeze record "reason" "evidence"  and commit
PARAMETERS.md and state/params_baseline.json with the change. Run:  python -m pytest tests/  (or)  python tests/test_freeze.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import freeze  # noqa: E402


def test_no_unlogged_parameter_changes():
    base = json.loads((ROOT / "state" / "params_baseline.json").read_text())
    d = freeze.diff(base, freeze.snapshot())
    assert not d, f"unlogged setting changes: {[k for k, _, _ in d]}; run python -m pipeline.freeze record"


def test_diff_and_record_write_an_entry():
    old = {"a.X": 1, "a.Y": [1, 2]}
    new = {"a.X": 2, "a.Y": [1, 2]}
    assert freeze.diff(old, new) == [("a.X", 1, 2)]
    tmp = Path(tempfile.mkdtemp())
    text = freeze.record("test change", "5 days", old=old, new=new, log=tmp / "PARAMETERS.md", baseline=tmp / "b.json")
    log = (tmp / "PARAMETERS.md").read_text()
    assert json.loads((tmp / "b.json").read_text()) == new
    assert "a.X" in text and "1 -> 2" in text and "Evidence at the time: 5 days" in text and "# Parameter freeze log" in log


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
