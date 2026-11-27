"""Small shared helpers: JSON parsing from model replies, time, file storage, version stamps."""
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = timezone.utc


def now_et():
    return datetime.now(ET)


def today_iso():
    return now_et().date().isoformat()


def extract_json(text):
    """Pull the last valid JSON object/list out of a model reply (fenced block preferred)."""
    if not text:
        return None
    chunks = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S) + [text]
    for chunk in reversed(chunks):
        pairs = sorted((("{", "}"), ("[", "]")),
                       key=lambda oc: chunk.find(oc[0]) if chunk.find(oc[0]) != -1 else 10**9)
        for o, c in pairs:  # try whichever bracket opens first (a list of objects stays a list)
            i, j = chunk.find(o), chunk.rfind(c)
            if i != -1 and j > i:
                try:
                    return json.loads(chunk[i:j + 1])
                except Exception:
                    pass
    return None


class MissingData(RuntimeError):
    """Required market data didn't arrive (usually a temporary data-provider problem)."""


def require_columns(df, cols, what="market data"):
    """Fail with a clear, retryable error instead of a bare KeyError deep inside a calculation."""
    have = set(getattr(df, "columns", []))
    missing = [c for c in cols if c not in have or not df[c].notna().any()]
    if missing:
        raise MissingData(f"Market data missing: {', '.join(missing)} not returned for {what} "
                          "(usually a temporary Yahoo Finance problem; the run will retry).")
    return df


JSON_RULE = "End your reply with a single ```json code block exactly matching the requested shape."


# ------------------------------------------------------------------ storage
def run_dir(stage, date=None):
    d = config.RUNS_DIR / (date or today_iso()) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_private(name):
    """Files about the real-money accounts: kept in the private repo (config.PRIVATE_DIR), never in this one."""
    name = str(name)
    return name == "external_books.json" or (name.startswith("daily_nav_") and not name.startswith("daily_nav_shadow_")
                                             and name != "daily_nav.csv")


def state_path(name):
    d = config.PRIVATE_DIR / "state" if is_private(name) else config.STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def private_reports(sub):
    """Report folder in the private repo (order sheets and the performance sheet show real holdings)."""
    d = config.PRIVATE_DIR / "reports" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with p.open() as f:
        return json.load(f)


def _atomic_write(p, text):
    """Write to a temp file in the same folder, then rename over the target in one step, so a crash
    mid-write can never leave a half-written state file behind."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, obj):
    _atomic_write(path, json.dumps(obj, indent=1, default=str))


def write_text(path, text):
    _atomic_write(path, text)


def append_csv(path, rows):
    """Append dict rows; writes a header on first use and widens it if new columns appear."""
    if not rows:
        return
    p = Path(path)
    existing, fields = [], []
    if p.exists():
        with p.open(newline="") as f:
            r = csv.DictReader(f)
            fields = list(r.fieldnames or [])
            existing = list(r)
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(existing + rows)
    _atomic_write(p, buf.getvalue())


# ------------------------------------------------------------------ version stamps
def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def code_version():
    """Git commit on GitHub Actions; otherwise a hash of the pipeline source."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    src = sorted(Path(__file__).resolve().parent.glob("*.py"))
    return "src-" + _hash("".join(f.read_text() for f in src))


def config_hash():
    keep = {k: getattr(config, k) for k in dir(config) if k.isupper()
            and k not in ("ROOT", "STATE_DIR", "RUNS_DIR", "EMAIL_FROM", "EMAIL_TO")}
    return _hash(json.dumps(keep, sort_keys=True, default=str))


def version_stamp(*prompts):
    """What produced a decision: code, settings, and the exact prompt text used."""
    return {"code_version": code_version(), "config_hash": config_hash(),
            "prompt_hash": _hash("\n".join(str(x) for x in prompts)) if prompts else ""}
