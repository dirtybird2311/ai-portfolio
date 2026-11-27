"""
AUTOMATIC RESUME  —  run:  python -m pipeline.resume   (the daily workflow runs this first)

Finds runs that stopped in the last few days (credits ran out, a service was down, a budget cap
was hit) and resumes them from their checkpoints. If the underlying problem isn't fixed yet, the
retry fails quietly; you get one email on the first failure and a final one when it gives up.

  macro    stopped -> resume macro, then re-run the screen so it uses the new macro view
  rebuild  stopped -> resume rebuild (stock team, PM, critic, delivery), no --force needed
"""
from . import checkpoint as cpt
from .notify import send, subject_line
from .runner import run_stage

MAX_ATTEMPTS = 4          # original run + 3 automatic retries


def pending():
    return [s for s in ("macro", "rebuild") if cpt.incomplete(s)]


def main():
    from .approvals import check_macro
    check_macro()                  # your APPROVE/REJECT on a held macro view takes effect daily
    todo = pending()
    if not todo:
        print("Nothing to resume.")
        return []
    results = []
    for stage in todo:
        d = cpt.incomplete(stage)
        if d["attempts"] >= MAX_ATTEMPTS:
            print(f"{stage}: gave up after {d['attempts']} attempts; run it manually once the problem is fixed.")
            continue
        final_try = d["attempts"] + 1 >= MAX_ATTEMPTS
        print(f"Resuming {stage} (started {d['started']}, attempt {d['attempts'] + 1} of {MAX_ATTEMPTS})")
        if stage == "macro":
            from .macro import main as fn
        else:
            from .rebuild import main as fn
        out = run_stage(stage, fn, quiet=not final_try, exit_on_fail=False)
        if out is None:
            if final_try:
                send(subject_line(stage.capitalize(), "ERROR", "automatic retries exhausted"),
                     f"The {stage} run failed {MAX_ATTEMPTS} times. Automatic retries have stopped. Fix the cause in the "
                     f"previous alert, then run the workflow manually: saved progress is kept for a few days.")
            results.append((stage, "failed"))
            continue
        results.append((stage, "resumed"))
        send(subject_line(stage.capitalize(), "OK", "resumed and finished"),
             f"The {stage} run that stopped on {d['started']} has now finished from its saved progress. "
             f"Its normal report email was sent separately.")
        if stage == "macro":
            from .screen import main as screen_main
            run_stage("screen", screen_main, exit_on_fail=False)
    return results


if __name__ == "__main__":
    main()
