"""
CONNECTION TEST  —  run:  python -m pipeline.connections        (Actions > Connection test > Run workflow)

Makes one tiny real call to every service the pipeline uses and emails you a pass/fail table:
  - every AI model named in config.py (a one-line "reply OK"), plus access to the batch APIs
  - data: Finnhub, FRED, SEC, Yahoo prices and estimates, Gemini embeddings, each macro source page
  - broker: the Alpaca paper account (when its keys are set)
  - email: logs in to Gmail and sends the report

Costs well under a penny. Never trades, never changes saved state (portfolio, ledgers, views).
Every check runs even if an earlier one fails. Exit code 1 if anything required FAILED.

Results:  PASS | FAIL (needs fixing) | WARN (works with a fallback) | SKIP (optional key not set)
"""
import os
import smtplib
import sys
import time
from datetime import date, timedelta

import requests

from . import config, llm, notify
from .preflight import all_models

last_rows = []
REQUIRED_KEYS = {"ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY", "FRED_API_KEY"}
PING_SYSTEM = "You are a connection test. Reply with exactly: OK"


def hint(err):
    """Turn a raw error into what to do about it."""
    e = str(err).lower()
    if ("credit balance" in e or "billing" in e or "insufficient_quota" in e or "payment" in e
            or "credits" in e or "licenses" in e):
        return "out of credits / billing not set up"
    if any(k in e for k in ("401", "403", "unauthorized", "invalid api key", "invalid_api_key", "authentication",
                            "permission", "api key not valid", "incorrect api key")):
        return "key rejected: re-copy the key into GitHub Secrets"
    if any(k in e for k in ("404", "not found", "does not exist", "not_found", "unknown model", "invalid model",
                            "model_not_found", "no such model")):
        return "model name not found: the provider renamed or retired it; update config.py"
    if "timed out" in e or "timeout" in e or "connectionpool" in e:
        return "provider slow or unreachable (free endpoints sometimes are); re-run later"
    if "429" in e or "rate limit" in e or "rate_limit" in e or "resource_exhausted" in e:
        return "rate limited: if it persists across runs, check the account's plan/limits in the provider's console"
    return "see error"


def _timed(fn):
    t0 = time.time()
    try:
        return fn(), None, round(time.time() - t0, 1)
    except Exception as e:
        return None, e, round(time.time() - t0, 1)


def _row(group, name, status, secs=None, detail=""):
    return {"group": group, "name": name, "status": status, "secs": secs,
            "detail": str(detail)[:1500 if name == "NVIDIA model list" else 300]}


# ==================================================================== models
def models_to_test():
    ms = set(all_models()) | set(config.SHADOW_LABELERS) | {config.OPUS}
    return sorted(ms)


def check_models(session):
    rows = []
    judge_levels = {j["model"]: j.get("thinking") for j in config.JUDGE_PANEL if j.get("enabled", True)}
    for m in models_to_test():
        key = llm.key_name(m)
        if not llm.has_key(m):
            rows.append(_row("AI models", m, "FAIL" if key in REQUIRED_KEYS else "SKIP", detail=f"{key} not set"))
            continue
        if llm.provider(m) in ("mistral", "groq"):
            time.sleep(2)                        # free tiers allow about one request a second
        # judges are tested at the thinking level they actually run with
        lvl = judge_levels.get(m, None if llm.is_claude(m) else "minimal")
        r, err, secs = _timed(lambda: session.ask("connection_test", PING_SYSTEM, "Reply with exactly: OK",
                                                  max_tokens=300, thinking=lvl, model=m))
        if err:
            rows.append(_row("AI models", m, "FAIL", secs, f"{hint(err)} | {str(err)[:120]}"))
        elif "ok" not in (r.text or "").lower():
            rows.append(_row("AI models", m, "WARN", secs, f"answered, but not 'OK': {(r.text or '')[:60]!r}"))
        else:
            rows.append(_row("AI models", m, "PASS", secs, f"${r.cost:.5f}"))
    return rows


NV_FAMILIES = ("deepseek", "qwen", "kimi", "glm", "llama", "nemotron", "gpt-oss", "mistral", "minimax")


def check_nvidia(get=requests.get):
    """NVIDIA retires free models without notice; list what it serves now so a replacement can be picked."""
    key = config.secret("NVIDIA_API_KEY", required=False)
    if not key:
        return []
    def listing():
        r = get("https://integrate.api.nvidia.com/v1/models", timeout=30, headers={"Authorization": f"Bearer {key}"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:100]}")
        return sorted(m["id"] for m in r.json().get("data", []))
    ids, err, secs = _timed(listing)
    if err:
        return [_row("AI models", "NVIDIA model list", "WARN", secs, f"{hint(err)} | {err}")]
    fam = [i for i in ids if any(f in i.lower() for f in NV_FAMILIES)]
    return [_row("AI models", "NVIDIA model list", "PASS", secs,
                 f"{len(ids)} listed; chat candidates: " + ", ".join(fam[:40]))]


def check_batch_access(session, get=requests.get):
    """Can the keys use the batch APIs (50% off)? Listing batches is free."""
    rows = []
    if config.secret("ANTHROPIC_API_KEY", required=False):
        _, err, secs = _timed(lambda: list(session._anthropic().messages.batches.list(limit=1)))
        rows.append(_row("Batch APIs", "Claude batches", "FAIL" if err else "PASS", secs, f"{hint(err)} | {err}" if err else ""))
    key = config.secret("OPENAI_API_KEY", required=False)
    if key:
        def openai_list():
            r = get("https://api.openai.com/v1/batches", params={"limit": 1}, timeout=30,
                    headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:100]}")
        _, err, secs = _timed(openai_list)
        rows.append(_row("Batch APIs", "OpenAI batches", "FAIL" if err else "PASS", secs, f"{hint(err)} | {err}" if err else ""))
    return rows


# ==================================================================== data
def _need(name):
    k = config.secret(name, required=False)
    if not k:
        raise KeyError(f"{name} not set")
    return k


def check_data(get=requests.get):
    rows = []

    def finnhub():
        today = date.today()
        r = get("https://finnhub.io/api/v1/company-news", timeout=20, params={
            "symbol": "AAPL", "from": (today - timedelta(days=7)).isoformat(), "to": today.isoformat(),
            "token": _need("FINNHUB_API_KEY")})
        if r.status_code != 200 or not isinstance(r.json(), list):
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:100]}")
        return f"{len(r.json())} AAPL headlines this week"

    def fred():
        r = get("https://api.stlouisfed.org/fred/series/observations", timeout=30, params={
            "series_id": "DGS10", "api_key": _need("FRED_API_KEY"), "file_type": "json", "sort_order": "desc", "limit": 1})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:100]}")
        o = r.json()["observations"][0]
        return f"10-yr Treasury {o['value']}% on {o['date']}"

    def sec_data():
        from .sec import SEC
        s = SEC(get=get)
        tick = s.ticker_map()
        if not tick:
            raise RuntimeError("no ticker list (SEC may be blocking the User-Agent; set SEC_CONTACT)")
        facts = s.companyfacts(tick.get("AAPL", 320193))
        if not facts:
            raise RuntimeError("company facts unavailable")
        return f"{len(tick):,} tickers; AAPL financials OK"

    def yahoo():
        import yfinance as yf
        px = yf.download("SPY", period="5d", progress=False, auto_adjust=True)
        if px is None or px.empty:
            raise RuntimeError("no SPY prices returned")
        return f"SPY {len(px)} days"

    def estimates():
        from .inputs import estimates as est
        if not est("AAPL"):
            raise RuntimeError("no estimate data (the dossier will say 'not available')")
        return "AAPL estimate trend OK"

    def embeddings():
        from .embed import embed
        _need("GEMINI_API_KEY")
        v = embed(["connection test"])
        if v is None:
            raise RuntimeError("embedding call failed (news de-duplication falls back to exact matches)")
        return "OK"

    for name, fn, required in (("Finnhub news", finnhub, True), ("FRED economic data", fred, True),
                               ("SEC filings", sec_data, True), ("Yahoo prices", yahoo, True),
                               ("Yahoo analyst estimates", estimates, False),
                               ("Gemini embeddings", embeddings, False)):
        out, err, secs = _timed(fn)
        if err:
            status = "FAIL" if required else "WARN"
            if isinstance(err, KeyError):
                status = "FAIL"
            h = hint(err)
            rows.append(_row("Data", name, status, secs,
                             f"{h} | {err}" if h != "see error" and not isinstance(err, KeyError) else str(err).strip("'")))
        else:
            rows.append(_row("Data", name, "PASS", secs, out))
    return rows


def check_macro_sources(get=None):
    """Each macro page/feed. A broken one isn't fatal (the macro run searches instead) but should be fixed."""
    from .fetch import SOURCES, fetch_source
    rows = []
    for theme, srcs in sorted(SOURCES.items()):
        for src in srcs:
            out, err, secs = _timed(lambda: fetch_source(src, get, max_chars=2000))
            if err or (out or {}).get("error"):
                rows.append(_row("Macro sources", f"{theme}: {src['id']}", "WARN", secs,
                                 f"{(out or {}).get('error') or err} ({src['url']}); macro falls back to search"))
            else:
                rows.append(_row("Macro sources", f"{theme}: {src['id']}", "PASS", secs, ""))
    return rows


def check_alpaca(http=None):
    from . import broker
    if not all(broker._keys()):
        return [_row("Broker", "Alpaca paper", "SKIP", detail="ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not set: "
                                                             "paper trades are recorded at reference prices")]
    a, err, secs = _timed(lambda: broker.account(http))
    if err:
        return [_row("Broker", "Alpaca paper", "FAIL", secs, f"{hint(err)} | {err} (use the PAPER keys, not live keys)")]
    note = "" if config.PAPER_MODE else " (PAPER_MODE is 0: orders are not placed)"
    return [_row("Broker", "Alpaca paper", "PASS" if a.get("status") == "ACTIVE" else "WARN", secs,
                 f"account {a.get('status')}, ${float(a.get('cash') or 0):,.0f} paper cash{note}")]


def check_gmail():
    sender, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (sender and pw):
        return [_row("Email", "Gmail login", "WARN", detail="GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set: emails are "
                                                          "saved to the run folder instead of sent")]

    def login():
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(sender, pw)
    _, err, secs = _timed(login)
    if err:
        return [_row("Email", "Gmail login", "FAIL", secs,
                     "login refused: use a Gmail App Password (not your normal password), 2-step verification on"
                     if "535" in str(err) or "auth" in str(err).lower() else err)]
    return [_row("Email", "Gmail login", "PASS", secs)]


# ==================================================================== report
ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "–"}


def render(rows):
    n = {k: sum(r["status"] == k for r in rows) for k in ICON}
    head = (f"Connection test {date.today().isoformat()}: {n['PASS']} passed, {n['FAIL']} failed, "
            f"{n['WARN']} warnings, {n['SKIP']} skipped (optional key not set)")
    lines = [head, ""]
    group = None
    for r in sorted(rows, key=lambda r: (r["group"], ("FAIL", "WARN", "PASS", "SKIP").index(r["status"]), r["name"])):
        if r["group"] != group:
            group = r["group"]
            lines.append(f"\n{group}")
        secs = f" ({r['secs']}s)" if r["secs"] is not None else ""
        lines.append(f"  {ICON[r['status']]} {r['status']:<4} {r['name']}{secs}" + (f" — {r['detail']}" if r["detail"] else ""))
    if n["FAIL"]:
        lines += ["", "Fix the FAIL lines before the next scheduled run. Keys go in GitHub > Settings > Secrets and "
                      "variables > Actions; model names are at the top of pipeline/config.py."]
    return "\n".join(lines), n


def _scrub(text):
    """Never let a key value reach a note on GitHub, even inside an echoed error or URL."""
    for k, v in os.environ.items():
        if v and len(v) >= 8 and any(w in k for w in ("KEY", "SECRET", "PASSWORD", "TOKEN")):
            text = text.replace(v, "***")
    return text


def annotate(rows, n):
    """On GitHub Actions, post each problem as a note on the run (readable in the run's summary page and
    through the GitHub API), so results can be checked without opening the log."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    clean = lambda x: _scrub(str(x)).replace("%", "%25").replace("\r", " ").replace("\n", " ")
    for r in rows:
        if r["status"] in ("FAIL", "WARN", "SKIP") or r["name"] == "NVIDIA model list":
            level = {"FAIL": "error", "WARN": "warning", "SKIP": "notice", "PASS": "notice"}[r["status"]]
            print(f"::{level} title={clean(r['status'] + ' ' + r['group'] + ': ' + r['name'])}::{clean(r['detail'])}")
    print(f"::notice title=Connection test summary::{n['PASS']} passed, {n['FAIL']} failed, {n['WARN']} warnings, "
          f"{n['SKIP']} skipped")


def main(argv=None, get=requests.get, session=None, send=True, alpaca_http=None):
    session = session or llm.Session("connections", budget=0.25)
    rows = []
    for step in (lambda: check_models(session), lambda: check_nvidia(get), lambda: check_batch_access(session, get),
                 lambda: check_data(get), lambda: check_macro_sources(), lambda: check_alpaca(alpaca_http), check_gmail):
        try:
            rows += step()
        except Exception as e:                      # a broken check never hides the others
            rows.append(_row("Test itself", "check crashed", "FAIL", detail=e))
    global last_rows
    last_rows = rows
    text, n = render(rows)
    print(text)
    annotate(rows, n)
    print(f"\nModel calls cost ${session.spent:.4f}")
    if send:
        status = "ERROR" if n["FAIL"] else ("FLAG" if n["WARN"] else "OK")
        headline = f"{n['FAIL']} failed" if n["FAIL"] else ("all connected" if not n["WARN"] else f"{n['WARN']} warnings")
        notify.send(notify.subject_line("Connection test", status, headline), text)
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
