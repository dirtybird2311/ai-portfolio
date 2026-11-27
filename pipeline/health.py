"""
HEALTH CHECK (exception-only alerts)  —  run:  python -m pipeline.health
Runs after the 8 am catch-up. Silent when everything is fine; otherwise one short email listing what is wrong:

  - trading days with no row in the paper-account NAV file or a real-account NAV file
  - no daily watch run logged for the last trading day
  - a setting changed without a freeze-log entry
  - a run that stopped with an error since the last check is already emailed by the run itself, so it is not repeated

The same problem is not re-sent within a day (state/health_alerts.json).
"""
import sys

import pandas as pd

from .notify import send, subject_line
from .prices import expected_day
from .util import now_et, read_json, state_path, write_json

HOLIDAYS = {pd.Timestamp(d) for d in (
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24")}


WATCH_GRACE_HOUR = 23                 # ET hour after which a missing same-day watch run is flagged


def trading_days(first, last):
    return [d for d in pd.bdate_range(first, last) if d not in HOLIDAYS]


def missing_rows(path_name, last, first=None):
    p = state_path(path_name)
    if not p.exists() or not p.stat().st_size:
        return None
    have = set(pd.to_datetime(pd.read_csv(p)["date"]))
    first = first or min(have)
    return [d.date().isoformat() for d in trading_days(first, last) if d not in have]


def checks(now=None):
    """[(key, message)] for everything wrong right now."""
    now = now or now_et()
    last = expected_day(now)
    while last in HOLIDAYS:
        last -= pd.Timedelta(days=1)
    out = []
    books = (read_json(state_path("external_books.json"), {}) or {}).get("books", {})   # real accounts (private repo)
    files = [("daily_account_nav.csv", "paper account")] + [(f"daily_nav_{k}.csv", b.get("label", k)) for k, b in books.items()]
    for name, label in files:
        miss = missing_rows(name, last)
        if miss:
            out.append((f"nav:{name}", f"{label}: no NAV row for {', '.join(miss[:6])}"
                        f"{' and more' if len(miss) > 6 else ''} (the nightly catch-up could not fill it; "
                        f"run Actions > Backfill NAV rows)"))
    log = state_path("run_log.csv")
    if log.exists():
        d = pd.read_csv(log)
        w = d[d["stage"] == "watch"]
        seen = pd.to_datetime(w["time"].str[:10]).max() if len(w) else None
        due = last                                  # GitHub starts the 5:30 pm watch late (often 8 to 9 pm): until 11 pm
        if last.date() == now.date() and now.hour < WATCH_GRACE_HOUR:   # ET, today's run is not yet overdue
            due = last - pd.Timedelta(days=1)
            while due.weekday() >= 5 or due in HOLIDAYS:
                due -= pd.Timedelta(days=1)
        if seen is None or seen < due:
            out.append(("watch", f"no daily watch run logged for {due.date()} (last: {seen.date() if seen is not None else 'never'})"))
    try:
        from . import freeze
        base = freeze.load_baseline()
        if base:
            ch = freeze.diff(base, freeze.snapshot())
            if ch:
                out.append(("freeze", f"{len(ch)} setting(s) changed without a freeze-log entry: {', '.join(k for k, _, _ in ch[:5])}"))
    except Exception:
        pass
    return out


def main(now=None, send_fn=send):
    now = now or now_et()
    found = checks(now)
    seen = read_json(state_path("health_alerts.json"), {}) or {}
    today = now.date().isoformat()
    fresh = [(k, m) for k, m in found if seen.get(k) != today and seen.get(k) != (now - pd.Timedelta(days=1)).date().isoformat()]
    if not found:
        print("Health: all good.")
    for k, m in found:
        print(f"  ! {m}")
    if fresh:
        send_fn(subject_line("health", "FLAG", f"{len(fresh)} problem(s)"),
                "Things that need a look:\n\n" + "\n".join(f"- {m}" for _, m in fresh) +
                "\n\nThis email only comes when something is wrong, and not more than once a day per problem.")
        seen.update({k: today for k, _ in fresh})
    write_json(state_path("health_alerts.json"), {k: v for k, v in seen.items() if k in {x for x, _ in found}})
    return {"status": "flag" if found else "ok", "problems": len(found)}


if __name__ == "__main__":
    main()
    sys.exit(0)
