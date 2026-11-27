"""
Wraps every stage so failures are never silent, and are explained in plain English:
    run_stage("macro", main_fn)   # main_fn(session, run_folder) -> summary dict

- creates the model Session with the stage's budget
- on any error: saves costs/receipts, emails what happened + what to do + how far the run got
  (progress is checkpointed, so a rerun or the automatic daily resume picks up from there)
- quiet=True (used by automatic retries) skips the email for an expected repeat failure
"""
import sys
import time
import traceback

from .checkpoint import add_spent, progress, spent
from .llm import BudgetExceeded, Session
from .notify import send, subject_line
from . import config
from .util import append_csv, now_et, run_dir, state_path, version_stamp

RESUMABLE = {"macro", "rebuild", "team"}


def explain(stage, err_text, budget_hit=False):
    """(headline, what to do) for the alert email."""
    t = err_text.lower()
    if "job cancelled or timed out" in t:
        return ("Stopped (cancelled or out of time)",
                "The job was cancelled or reached its time limit. Progress and costs so far are saved; "
                "rerun it and it picks up where it stopped.")
    if budget_hit:
        return ("Run hit its spending cap",
                f"The {stage} run reached its per-run budget in pipeline/config.py (BUDGET_PER_RUN). This protects you "
                "from runaway costs. If the cap is too tight for normal runs, raise it; otherwise check the cost log "
                "for what used more than expected. The cap covers the whole run across retries, so automatic "
                "retries won't resume it; after raising the cap, run the workflow manually to continue.")
    if "credit balance" in t:
        return ("Claude API credits ran out",
                "Add credits at platform.claude.com (Settings > Billing). Turning on auto-reload with a monthly "
                "spend limit prevents this. Once credits are added, the daily job resumes this run automatically "
                "that evening, or tap Run workflow in GitHub Actions to resume now.")
    if "invalid x-api-key" in t or "authentication_error" in t:
        return ("Claude API key was rejected",
                "Check the ANTHROPIC_API_KEY secret in GitHub (Settings > Secrets and variables > Actions). "
                "If the key was deleted or rotated in the Claude Console, create a new one and update the secret.")
    if "missing secret" in t:
        return ("A required secret is missing", "Add the secret named in the error below to GitHub Secrets.")
    if any(k in t for k in ("overloaded", "rate_limit", "timed out", "connectionerror", "connection error")):
        return ("Temporary service problem",
                "A service was overloaded or unreachable. Nothing to fix: the daily job will retry automatically.")
    if "market data missing" in t:
        return ("Market prices unavailable",
                "Yahoo Finance didn't return a required price series (usually temporary). Nothing to fix: the "
                "daily job will retry automatically. If it keeps happening, a ticker may have changed.")
    if "integrity check" in t:
        return ("Trade plan failed its safety check",
                "The plan was blocked before any email with trades went out. Copy the error below into Claude "
                "to diagnose it; do not place trades from this run.")
    if "core data missing" in t:
        return ("Key economic data unavailable",
                "FRED didn't return a core series (usually temporary). The daily job will retry automatically.")
    return ("Unexpected error",
            "Something failed that the pipeline doesn't recognize. Copy the error below into Claude to diagnose it. "
            "Progress is saved, so a rerun resumes.")


class Cancelled(Exception):
    """The job was cancelled or hit its time limit (GitHub sends SIGINT/SIGTERM first)."""


def _on_signal(signum, frame):
    raise Cancelled(f"stopped by signal {signum} (job cancelled or timed out)")


def run_stage(stage, main_fn, quiet=False, exit_on_fail=True, **kwargs):
    import signal
    for sig in (signal.SIGTERM, signal.SIGINT):     # save costs and progress when the job is stopped
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):               # not the main thread (tests): skip
            pass
    folder = run_dir(stage)
    prior = spent(stage)               # a resumed run gets only what's left of its budget
    session = Session(stage, prior_spent=prior)
    started = time.time()
    if prior:
        print(f"[{stage}] earlier attempts spent ${prior:.2f}; ${session.budget:.2f} of the cap remains")
    try:
        summary = main_fn(session, folder, **kwargs) or {}
    except Exception as e:
        usage = _finish(session, folder, stage)
        _log_run(stage, "budget" if isinstance(e, BudgetExceeded) else "error", usage, started, str(e)[:200])
        err = traceback.format_exc()[-3000:]
        headline, todo = explain(stage, err, isinstance(e, BudgetExceeded))
        done = progress(stage) + ([f"team: {x}" for x in progress("team")] if stage == "rebuild" else [])
        body = [f"The {stage} run stopped: {headline}.", "", "WHAT TO DO", todo, "",
                "Nothing was traded, and no plan or macro view was changed by this run."]
        if stage in RESUMABLE:
            body += ["", "PROGRESS SAVED (a rerun skips these):"] + ([f"  - {d}" for d in done] or ["  - nothing yet"])
        body += ["", f"Model spend: ${session.spent:.2f} this attempt, ${prior + session.spent:.2f} for the run so far",
                 "", "ERROR DETAILS", err]
        print("\n".join(body[:6]))
        if not quiet:
            send(subject_line(stage.capitalize(), "ERROR", headline), "\n".join(body), save_dir=folder)
        if exit_on_fail:
            sys.exit(2 if isinstance(e, BudgetExceeded) else 1)
        return None
    usage = _finish(session, folder, stage)
    _log_run(stage, str(summary.get("status", "ok")), usage, started)
    return dict(summary, usage=usage)


def _log_run(stage, status, usage, started, error=""):
    """One line per run in state/run_log.csv: what ran, how it ended, what it cost, which version."""
    try:
        v = version_stamp()
        append_csv(state_path("run_log.csv"), [{
            "time": now_et().strftime("%Y-%m-%d %H:%M"), "stage": stage, "status": status,
            "cost": usage.get("cost", 0), "calls": usage.get("calls", 0), "fallbacks": usage.get("fallbacks", 0),
            "seconds": round(time.time() - started), "paper": bool(config.PAPER_MODE),
            "code_version": v["code_version"], "config_hash": v["config_hash"], "error": error}])
    except Exception as e:           # logging must never break a run
        print(f"  ! could not write run log: {e}")


def _finish(session, folder, stage):
    add_spent(stage, session.spent)
    usage = session.save(folder)
    print(f"[{stage}] {usage['calls']} model calls, ${usage['cost']:.2f}, "
          f"{usage['searches']} searches, {usage['fallbacks']} Gemini fallbacks")
    return usage
