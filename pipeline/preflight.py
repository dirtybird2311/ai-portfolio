"""
PREFLIGHT  —  run:  python -m pipeline.preflight [stage]    (every workflow runs this first)

Checks the settings and secrets BEFORE any money is spent, and stops with a plain-English list
of problems if something is wrong. Warnings are printed but don't stop the run.
"""
import sys

from . import config, llm

RETIRED = ("gemini-2.0", "gemini-2.5", "gemini-1.5")          # Gemini 2.5 Flash retires Oct 16, 2026
PER_STOCK_TOKENS = (8000, 3200)                               # judge packet in, reply + thinking out
STAGE_SECRETS = {"macro": ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FRED_API_KEY"],
                 "screen": [], "team": ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY"],
                 "rebuild": ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY"],
                 "watch": ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY"], "track": [], "history": []}


def all_models():
    out = set()
    for m in config.MODELS.values():
        out |= set(m) if isinstance(m, (list, tuple)) else {m}
    out |= set(config.FREE_FALLBACKS) | {config.PAID_FALLBACK} | set(config.LAST_RESORT)
    out |= {j["model"] for j in config.JUDGE_PANEL if j.get("enabled", True)}
    return out


def judge_cost_estimate(panel=None):
    """Rough $ per rebuild for the paid judges that will actually run (batched = half price)."""
    tin, tout = PER_STOCK_TOKENS
    per_stock = 0.0
    for j in panel if panel is not None else config.JUDGE_PANEL:
        if not j.get("enabled", True) or not llm.has_key(j["model"]):
            continue
        pin, pout = config.PRICES.get(j["model"], config.UNKNOWN_PRICE)
        per_stock += (tin * pin + tout * pout) / 1e6 * config.BATCH_DISCOUNT * float(j.get("sample", 1.0))
    return per_stock * config.JUDGED_PER_REBUILD


def check(stage=None):
    errors, warnings = [], []
    # ---- models, providers, prices
    for m in sorted(all_models()):
        try:
            p = llm.provider(m)
        except ValueError:
            errors.append(f"unknown model id format: {m}")
            continue
        if p not in ("claude", "google") and p not in config.PROVIDERS:
            errors.append(f"{m}: provider '{p}' has no entry in config.PROVIDERS")
        if m not in config.PRICES:
            errors.append(f"{m}: no price in config.PRICES (costs would be guessed)")
        if m.startswith(RETIRED):
            warnings.append(f"{m} is retired or retiring; switch to a current model")
    # ---- judge panel
    ids = [j.get("id") for j in config.JUDGE_PANEL]
    if len(ids) != len(set(ids)):
        errors.append("JUDGE_PANEL has duplicate ids")
    for j in config.JUDGE_PANEL:
        for k in ("id", "model", "live"):
            if k not in j:
                errors.append(f"judge {j.get('id')}: missing '{k}'")
        if j.get("thinking") not in (None,) + llm.LEVELS:
            errors.append(f"judge {j.get('id')}: thinking must be one of {llm.LEVELS} or None")
        if not 0 < float(j.get("sample", 1.0)) <= 1:
            errors.append(f"judge {j.get('id')}: sample must be in (0, 1]")
    enabled = [j for j in config.JUDGE_PANEL if j.get("enabled", True)]
    runnable = [j for j in enabled if llm.has_key(j["model"])]
    for j in enabled:
        if j not in runnable:
            warnings.append(f"judge {j['id']} ({j['model']}) will be skipped: secret {llm.key_name(j['model'])} not set")
    if stage in (None, "team", "rebuild") and not any(j.get("live") for j in runnable):
        warnings.append("no live judge has its key set; the team will fall back to the default judge")
    # ---- rules and budgets
    R = config.EVAL_RULE
    if len(R["looks_months"]) != len(R["t_boundaries"]):
        errors.append("EVAL_RULE: looks_months and t_boundaries must be the same length")
    est = judge_cost_estimate()
    for st in ("team", "rebuild"):
        if config.BUDGET_PER_RUN.get(st, 0) < est * 1.3:
            warnings.append(f"BUDGET_PER_RUN['{st}'] ${config.BUDGET_PER_RUN.get(st, 0):.2f} is tight for the judge "
                            f"panel (~${est:.2f} per rebuild estimated)")
    for lvl, (lo, hi) in config.TILT_RANGES.items():
        if not 0 <= lo <= hi <= 100:
            errors.append(f"TILT_RANGES[{lvl}] invalid: {lo}-{hi}")
    # ---- secrets for this stage
    for name in STAGE_SECRETS.get(stage, []) if stage else []:
        if not config.secret(name, required=False):
            errors.append(f"missing secret {name} (GitHub > Settings > Secrets and variables > Actions)")
    if config.PAPER_MODE and not (config.secret("ALPACA_API_KEY_ID", required=False)
                                  and config.secret("ALPACA_API_SECRET_KEY", required=False)):
        warnings.append("Alpaca paper keys not set: paper trades are recorded at reference prices, not placed")
    if not config.secret("GMAIL_APP_PASSWORD", required=False):
        warnings.append("GMAIL_APP_PASSWORD not set: emails will be saved to the run folder instead of sent")
    return errors, warnings, est


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    stage = argv[0] if argv else None
    errors, warnings, est = check(stage)
    print(f"Preflight{' for ' + stage if stage else ''}: {'PAPER' if config.PAPER_MODE else 'LIVE'} mode; "
          f"judge panel ~${est:.2f} per rebuild")
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    if errors:
        print("Preflight failed: nothing was run and nothing was spent.")
        return 1
    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
