"""
Checkpoints: every stage saves its progress as it goes, so a stopped run resumes where it left off.

    ck = Checkpoint("rebuild")             # resumes an unfinished rebuild from the last few days,
                                           # otherwise starts fresh
    if not ck.has("pick"):
        ck.save("pick", select(...))       # saved immediately (survives a crash on the next line)
    pick = ck.get("pick")
    ck.save_item("debate", "AAPL", {...})  # per-stock progress
    ck.complete()                          # finished: the next run starts fresh

Files live in state/checkpoints/, which the GitHub workflows save back to the repo even when a
run fails, so progress carries across workflow runs.
"""
from datetime import date

from .util import now_et, read_json, state_path, write_json

RESUME_WINDOW_DAYS = 4          # a stopped run older than this is stale; start over


def _path(stage):
    return state_path(f"checkpoints/{stage}.json")


class Checkpoint:
    def __init__(self, stage, fingerprint=None, window_days=RESUME_WINDOW_DAYS, fresh=False):
        self.stage = stage
        today = now_et().date()
        d = read_json(_path(stage))
        ok = (d and not fresh and not d.get("completed")
              and (today - date.fromisoformat(d["started"])).days <= window_days
              and (fingerprint is None or d.get("fingerprint") == fingerprint))
        self.data = d if ok else {"stage": stage, "started": today.isoformat(), "fingerprint": fingerprint,
                                  "steps": {}, "attempts": 0, "completed": None, "spent": 0.0}
        self.resumed = bool(ok)
        self.data["attempts"] += 1
        self._write()

    def _write(self):
        write_json(_path(self.stage), self.data)

    # ---------------------------------------------------------------- whole steps
    def has(self, step):
        return step in self.data["steps"]

    def get(self, step, default=None):
        return self.data["steps"].get(step, default)

    def save(self, step, value):
        self.data["steps"][step] = value
        self._write()
        return value

    def drop(self, step):
        self.data["steps"].pop(step, None)
        self._write()

    # ---------------------------------------------------------------- per-item steps
    def item(self, step, key, default=None):
        return (self.data["steps"].get(step) or {}).get(key, default)

    def has_item(self, step, key):
        return key in (self.data["steps"].get(step) or {})

    def save_item(self, step, key, value):
        self.data["steps"].setdefault(step, {})[key] = value
        self._write()
        return value

    # ---------------------------------------------------------------- lifecycle
    def complete(self):
        self.data["completed"] = now_et().date().isoformat()
        self._write()

    @property
    def attempts(self):
        return self.data["attempts"]


def incomplete(stage, window_days=RESUME_WINDOW_DAYS):
    """The saved state of an unfinished, still-fresh run of this stage, or None."""
    d = read_json(_path(stage))
    if not d or d.get("completed"):
        return None
    if (now_et().date() - date.fromisoformat(d["started"])).days > window_days:
        return None
    return d


def spent(stage):
    """Model spend already made by earlier attempts of an unfinished run."""
    d = incomplete(stage)
    return float((d or {}).get("spent", 0.0))


def add_spent(stage, amount):
    """Record an attempt's spend on the unfinished run it belongs to (no-op if none)."""
    d = read_json(_path(stage))
    if d and not d.get("completed") and amount:
        d["spent"] = round(float(d.get("spent", 0.0)) + amount, 4)
        write_json(_path(stage), d)


def progress(stage):
    """Human-readable list of what an unfinished run already completed."""
    d = read_json(_path(stage))
    if not d or d.get("completed"):
        return []
    out = []
    for step, v in d["steps"].items():
        if step.startswith("batch_id:"):
            out.append(f"{step.split(':', 1)[1]}: Claude batch submitted (results will be collected, not re-bought)")
        elif isinstance(v, dict) and step not in ("packet", "plan", "notes") and not step.startswith("batch:"):
            out.append(f"{step}: {len(v)} done")
        elif step.startswith("batch:"):
            out.append(f"{step.split(':', 1)[1]}: {len(v)} results saved")
        else:
            out.append(f"{step}: done")
    return out
