"""
PARAMETER FREEZE LOG  —  run:  python -m pipeline.freeze            (check: exit 1 if a setting changed unlogged)
                              python -m pipeline.freeze record "reason" ["evidence: N trading days / M rebuilds"]

The settings that shape the picks (signal weights, bars, caps, model routing, sizing bands) are snapshotted into
state/params_baseline.json. Changing one of them without logging it makes this check (and tests/test_freeze.py,
which runs in CI) fail. `record` writes a dated entry to PARAMETERS.md with the old and new values, the reason and
how much evidence existed at the time, then refreshes the baseline. Results are judged only from the latest entry
onward, so an old record is never credited to a newer rule. Bug fixes that change no setting need no entry.
"""
import importlib
import json
import sys
from pathlib import Path

from .util import now_et, state_path

REGISTRY = {
    "screen": ["PRIOR_WEIGHTS", "FAMILIES", "CANDIDATE_T_MIN", "CANDIDATE_T_MIN_NEW", "WEIGHT_RULE", "MOMENTUM_GUARD",
               "WEIGHT_REFRESH_DAYS", "MIN_EVIDENCE_MONTHS", "SUB_CAP_MIN", "SUB_CAP_SHARE", "STANDOUT_PCT",
               "SLOT_WEIGHT", "MIN_PRICE", "MIN_DOLLAR_VOLUME", "CONTROL_SIZE"],
    "config": ["MODELS", "DEBATE_POOL", "JUDGE_PANEL", "COUNCIL", "COUNCIL_JUDGE", "SHADOW_SIGNALS", "PEER_WINDOW_DAYS", "THEMES", "THEME_CAP", "EVENT_LOOKAHEAD_DAYS", "JUDGE_DISAGREEMENT", "JUDGED_PER_REBUILD", "EVAL_RULE",
               "PROB", "BASE_RATE", "MOMENTUM_CAP", "MOMENTUM_MAX_LEVEL", "PANEL_SHARPEN", "MIN_HISTORY_DAYS",
               "MAX_PER_FACTOR", "DROP_REVIEW_PCT", "MACRO_HORIZON_WEEKS", "MACRO_TILT", "TILT_RANGES", "SIZE_BY_EDGE",
               "STARTING_VALUE"],
    "pm": ["MIN_STOCKS", "MAX_STOCKS", "POS_MIN", "POS_MAX", "BAND", "MIN_TRADE", "CLUSTER_CORR", "CLUSTER_CAP", "MIN_BUY_CONVICTION", "PARKING"],
    "rebuild": ["MAX_TURNOVER"],
    "broker": ["MAX_AGE_DAYS", "PREOPEN_HOURS"],
}
LOG = "PARAMETERS.md"
BASELINE = "params_baseline.json"


def _plain(v):
    """JSON-safe, order-stable form of a setting."""
    return json.loads(json.dumps(v, default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else repr(o),
                                 sort_keys=True))


def snapshot():
    out = {}
    for mod, names in REGISTRY.items():
        m = importlib.import_module(f"pipeline.{mod}")
        for n in names:
            out[f"{mod}.{n}"] = _plain(getattr(m, n))
    return out


def load_baseline():
    p = state_path(BASELINE)
    return json.loads(p.read_text()) if p.exists() else None


def diff(old, new):
    keys = sorted(set(old) | set(new))
    return [(k, old.get(k), new.get(k)) for k in keys if old.get(k) != new.get(k)]


def _short(v, n=160):
    s = json.dumps(v, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."


def record(reason, evidence="", old=None, new=None, log=None, baseline=None):
    """Append a dated entry to PARAMETERS.md and refresh the baseline. Returns the entry text."""
    new = new if new is not None else snapshot()
    old = old if old is not None else load_baseline()
    today = now_et().date().isoformat()
    lines = [f"\n### {today}  {reason}\n"]
    if evidence:
        lines.append(f"- Evidence at the time: {evidence}\n")
    if old is None:
        lines.append(f"- Baseline recorded: {len(new)} settings (values in `state/params_baseline.json`).\n")
    else:
        for k, a, b in diff(old, new):
            lines.append(f"- `{k}`: {_short(a)} -> {_short(b)}\n")
        if not diff(old, new):
            lines.append("- No setting changed.\n")
    text = "".join(lines)
    log = Path(log) if log else Path(state_path(BASELINE)).parent.parent / LOG
    baseline = Path(baseline) if baseline else state_path(BASELINE)
    if not log.exists():
        log.write_text(HEADER)
    with log.open("a") as f:
        f.write(text)
    baseline.write_text(json.dumps(new, indent=1, sort_keys=True))
    return text


HEADER = """# Parameter freeze log

Every change to a setting that shapes the picks is dated here with the old and new values, the reason and the
evidence that existed at the time. Rule: between rebuilds the settings stay fixed; a change needs a written reason
that is not "last week's returns". Results are judged from the latest entry onward. Bug fixes that change no
setting are not logged here (see EVALUATION.md). Check: `python -m pipeline.freeze`.

Settings covered: see `REGISTRY` in `pipeline/freeze.py` (signal weights, bars and caps, model routing, sizing
bands, turnover cap, probability tables). The SPY sleeve is not a setting: it is whatever the sizing leaves over.
"""


def main(argv):
    if argv and argv[0] == "record":
        reason = argv[1] if len(argv) > 1 else "update"
        print(record(reason, argv[2] if len(argv) > 2 else ""))
        return 0
    base, now = load_baseline(), snapshot()
    if base is None:
        print("No baseline yet: run  python -m pipeline.freeze record \"baseline\"")
        return 1
    d = diff(base, now)
    for k, a, b in d:
        print(f"CHANGED {k}: {_short(a)} -> {_short(b)}")
    print("OK: no unlogged changes" if not d else f"{len(d)} setting(s) changed without a log entry")
    return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
