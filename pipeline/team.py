"""
STOCK TEAM  —  run:  python -m pipeline.team   (every two weeks, after the weekly screen)

Input: state/candidates.json (~90 + current holdings) and state/macro_view.json.

 1. NEWS         all candidates   Finnhub headlines (14 days), same stories merged via free
                                  embeddings, labeled good/bad/uncertain by Gemma (free).
 2. SHORTLIST    ~80 + holdings   screen score adjusted by news; holdings always included.
                                  Research carries forward if nothing material changed.
 3. FUNDAMENTALS shortlist        code pulls the latest 10-Q/10-K (MD&A + risk factors) and the
                                  earnings release from SEC; Gemini Flash summarizes with short
                                  quotes; code verifies every quote against the filing text;
                                  Mistral Large (free) reviews summary vs. the numbers; Sonnet
                                  (batched) takes over for red flags and likely new buys.
 4. CATALYSTS    shortlist        Gemini Flash + Google search: dated events in the next 90 days.
                                  Auditor: blocked sites dropped; only primary sources can
                                  affect a score.
 5. DEBATE       top ~80          one numbered dossier per stock; bull and bear on the same free
                                  model (Groq, NVIDIA DeepSeek or Mistral, spread to stay inside
                                  free limits), each citing dossier items; one rebuttal each.
                                  Holdings are re-debated and re-judged every rebuild.
 6. JUDGE PANEL  same             several judges from different companies score each stock BLIND
                                  (same packet, never each other's scores, never told what is owned),
                                  batched at half price: the PROBABILITY the stock beats its
                                  equal-weighted sector over 4 weeks, built from a historical base
                                  rate (pipeline/history.py) plus cited, capped adjustments; thesis,
                                  key risk, exit condition, main driver.
                                  LIVE judges (Sonnet, GPT-6 Sol, Gemini 3.1 Pro) are averaged (log-odds)
                                  into the forecast the PM uses; free SHADOW judges (DeepSeek, Mistral)
                                  are recorded only. Every packet is archived for later replays. Big disagreements
                                  are flagged. Every score, including rejections, goes in the
                                  decision ledger for grading at 2/4/13 weeks (see ledger.py).
Output: state/team_results.json (for the portfolio manager), runs/<date>/team/report.md
"""
import gzip
import hashlib
import json
import math
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from . import config, history, inputs, ledger, llm
from .audit import Auditor, domain, is_rumor, source_class
from .checkpoint import Checkpoint
from .embed import dedupe
from .runner import run_stage
from .sec import SEC, extra_metrics, filing_diff, filing_sections, red_flag_scan
from .util import JSON_RULE, now_et, read_json, state_path, version_stamp, write_json, write_text

TODAY = now_et().date()
LIKELY_NEW_BUYS = 10         # top non-held candidates always get the Sonnet fundamentals review
SHORTLIST = N_DEBATES = config.JUDGED_PER_REBUILD   # research, debate and judge this many (+ holdings)
NEWS_DAYS, NEWS_MAX = 14, 12
CARRY_FORWARD_DAYS = 14
FILING_CHARS = 40000


# ==================================================================== 1. NEWS
def fetch_news(tickers, get=requests.get):
    import os, time
    key = os.environ.get("FINNHUB_API_KEY")
    out = {}
    if not key:
        return out
    for t in tickers:
        try:
            r = get("https://finnhub.io/api/v1/company-news", timeout=20, params={
                "symbol": t.replace(".", "-"), "from": (TODAY - timedelta(days=NEWS_DAYS)).isoformat(),
                "to": TODAY.isoformat(), "token": key})
            rows = r.json() if r.status_code == 200 else []
        except Exception:
            rows = []
        seen, items = set(), []
        for x in rows if isinstance(rows, list) else []:
            h = (x.get("headline") or "").strip()
            sig = h.lower()[:70]
            if h and sig not in seen and domain(x.get("url", "")) not in config.COMPANY_BLOCKED_DOMAINS:
                seen.add(sig)
                items.append({"headline": h, "source": x.get("source", ""), "url": x.get("url", ""),
                              "summary": " ".join(str(x.get("summary") or "").split())[:300],
                              "date": pd.Timestamp(x.get("datetime", 0), unit="s").date().isoformat()})
        items, merged = dedupe(items)          # same story from different outlets counts once
        out[t] = items[:NEWS_MAX]
        time.sleep(1.05)
    return out


NEWS_SYSTEM = ("You are a financial expert. For each numbered headline about the named company, answer YES if it "
               "is good news for the stock price over the next 1-3 months, NO if bad, UNKNOWN if uncertain or "
               "irrelevant. Judge from the headline and its one-line summary. " + JSON_RULE)


def _labels(data, t, n):
    labels = [str(a).upper() for a in ((data or {}).get(t) or [])][:n] if isinstance(data, dict) else []
    return labels + ["UNKNOWN"] * (n - len(labels))


def score_news(session, cands, news, source="team"):
    """Live labels from Haiku (Gemma if Haiku fails). The same prompt also goes to the background labelers
    (config.SHADOW_LABELERS); their labels are recorded and graded, never used."""
    results, names = {}, {c["ticker"]: c["name"] for c in cands}
    have = [t for t in names if news.get(t)]
    rows = []
    for i in range(0, len(have), 8):
        group = have[i:i + 8]
        blocks = "\n\n".join(f"{t} ({names[t]}):\n" + "\n".join(
            f"  {k + 1}. {n['headline']}" + (f" -- {n['summary']}" if n.get("summary") else "")
            for k, n in enumerate(news[t])) for t in group)
        prompt = blocks + '\n\nJSON: {"TICKER": ["YES", "NO", ...], ...}'
        r = session.ask("news", NEWS_SYSTEM, prompt, max_tokens=1500, thinking=0)
        shadows = {}
        for m in config.SHADOW_LABELERS:
            if not llm.has_key(m):
                continue
            try:
                shadows[m] = session.ask("news", NEWS_SYSTEM, prompt, max_tokens=1500, thinking=0, model=m).data
            except llm.BudgetExceeded:
                raise
            except Exception as e:
                print(f"    background labeler {m} failed ({str(e)[:60]})")
        for t in group:
            labels = _labels(r.data, t, len(news[t]))
            vals = [{"YES": 1, "NO": -1}.get(a, 0) for a in labels]
            for n, a in zip(news[t], labels):
                n["label"] = a
            for model, data in [(r.model, r.data)] + list(shadows.items()):
                for n, a in zip(news[t], _labels(data, t, len(news[t]))):
                    rows.append({"date": n["date"], "ticker": t, "headline": n["headline"][:160], "model": model,
                                 "live": model == r.model, "label": a, "source": source})
            top = next((n for n, v in zip(news[t], vals) if v == (1 if sum(vals) > 0 else -1)), None)
            results[t] = {"score": round(float(np.mean(vals)), 3), "count": len(vals), "good": vals.count(1),
                          "bad": vals.count(-1), "top_story": top, "items": news[t]}
    ledger.record_labels(rows)
    for t in names:
        results.setdefault(t, {"score": 0.0, "count": 0, "good": 0, "bad": 0, "top_story": None, "items": []})
    return results


# ==================================================================== 2. SHORTLIST
def shortlist(cands, news):
    df = pd.DataFrame(cands)
    df["news_score"] = df.ticker.map(lambda t: news[t]["score"])
    df["news_count"] = df.ticker.map(lambda t: news[t]["count"])
    # news only counts when there is enough of it
    df["adj"] = df.composite + 0.10 * df.news_score * np.minimum(df.news_count, 5) / 5
    df = df.sort_values("adj", ascending=False)
    picks = list(df.head(SHORTLIST).ticker) + [t for t in df[df.incumbent.fillna(False)].ticker if t not in set(df.head(SHORTLIST).ticker)]
    return df.set_index("ticker"), picks


def needs_refresh(t, cache, news, filers, events=None):
    c = cache.get(t)
    if not c:
        return True, "new"
    if any(e["filed"] > c["date"] for e in (events or {}).get(t, [])):
        return True, "material 8-K"
    if (TODAY - pd.Timestamp(c["date"]).date()).days > CARRY_FORWARD_DAYS:
        return True, "stale"
    if t in filers:
        return True, "new filing"
    n = news.get(t, {})
    if n.get("count", 0) >= 3 and abs(n.get("score", 0)) >= 0.5:
        return True, "material news"
    return False, "carried forward"


# ==================================================================== 3. FUNDAMENTALS
def metrics_table(row, f):
    g = lambda k: (f or {}).get(k)
    div = lambda a, b: round(a / b * 100, 2) if a is not None and b not in (None, 0) else None
    m = {"revenue_ttm_$M": round(g("revenue") / 1e6, 1) if g("revenue") else None,
         "gross_margin_%": div(g("gross_profit"), g("revenue")), "operating_margin_%": div(g("operating_income"), g("revenue")),
         "net_margin_%": div(g("net_income"), g("revenue")),
         "fcf_ttm_$M": round((g("cfo") - (g("capex") or 0)) / 1e6, 1) if g("cfo") is not None else None,
         "cash_conversion_%": div(g("cfo"), g("net_income")), "debt_to_assets_%": div(g("debt"), g("assets")),
         "roa_%": div(g("net_income"), g("assets")), "market_cap_$M": round(row.get("mcap") / 1e6, 1) if row.get("mcap") else None,
         "screen_momentum": round(row["s_momentum"], 2), "screen_earnings": round(row["s_earnings"], 2),
         "screen_quality": round(row["s_quality"], 2), "screen_value": round(row["s_value"], 2),
         "screen_insider": round(row["s_insider"], 2), "screen_composite": round(row["composite"], 3),
         "financials_as_of": g("as_of")}
    return {k: v for k, v in m.items() if v is not None}


def get_filing(sec, cik):
    if not cik:
        return None
    periodic = sec.recent_filings(cik, {"10-Q", "10-K"}, 500)
    if not periodic:
        return None
    p = periodic[0]
    full = sec.document_text(cik, p["accession"], p["doc"])
    text = filing_sections(full, FILING_CHARS)
    flags = red_flag_scan(full)
    prior = next((f for f in periodic[1:] if f["form"] == p["form"]), None)
    diff = None
    if prior:
        try:
            diff = filing_diff(text, filing_sections(sec.document_text(cik, prior["accession"], prior["doc"]), FILING_CHARS))
            if diff:
                diff["prior_filed"] = prior["filed"]
        except Exception as e:
            print(f"    ! prior filing for comparison: {str(e)[:60]}")
    rel = next((f for f in sec.recent_filings(cik, {"8-K"}, 120) if "2.02" in f["items"]), None)
    release = sec.earnings_release_text(cik, rel["accession"])[:15000] if rel else ""
    return {"form": p["form"], "filed": p["filed"], "text": text, "flags": flags, "diff": diff,
            "release_filed": rel["filed"] if rel else None, "release": release}


def norm(s):
    return re.sub(r"[^a-z0-9%$.]+", " ", str(s).lower()).strip()


def verify_quotes(summary, filing):
    """Gemini must quote the filing; code confirms each quote really appears in it."""
    hay = norm(filing["text"] + " " + filing["release"])
    notes = []
    for i, q in enumerate(summary.get("quotes", []) if isinstance(summary.get("quotes"), list) else []):
        if not isinstance(q, dict):
            continue
        quote = str(q.get("quote", ""))
        ok = len(norm(quote)) >= 15 and norm(quote) in hay
        notes.append({"id": f"Q{i + 1}", "point": q.get("point", ""), "quote": quote, "section": q.get("section", ""),
                      "verified": ok, "score_eligible": ok, "verified_number": ok})
    return notes


SUMMARY_SYSTEM = ("You are a careful equity analyst reading an SEC filing and earnings release. Summarize what "
                  "CHANGED and what matters for the next 1-3 months: revenue and margin trends, guidance, demand "
                  "commentary, balance sheet, and red flags (accounting changes, customer concentration, rising "
                  "inventory or receivables, going-concern language, material weaknesses) and which business "
                  "segments drove the results. Back every point with a "
                  "SHORT VERBATIM quote (8-25 words) copied exactly from the text. " + JSON_RULE)
SUMMARY_SHAPE = ('{"summary": "3-5 sentences", "guidance": "what management guided, or none", '
                 '"segments": "which segments grew or shrank, or none reported", '
                 '"quotes": [{"point": "...", "quote": "exact words from the text", "section": "MD&A|Risk Factors|Release"}], '
                 '"red_flags": ["..."]}')

REVIEW_SYSTEM = ("You are a senior analyst reviewing a junior's filing summary against hard numbers from SEC data. "
                 "Assess the business trajectory for the next 1-3 months. Cite evidence as {\"ref\": ..., \"value\": ...}: "
                 "\"SEC:<TICKER>:<metric>\" for the metrics table (exact value) or \"NOTE:Q<n>\" for verified quotes. "
                 "Unverified quotes may not support conclusions. Point out anything the summary got wrong or missed. " + JSON_RULE)
REVIEW_SHAPE = ('{"trajectory": "improving|stable|deteriorating", "score": 1-5, '
                '"key_points": [{"point": "...", "evidence": [{"ref": "...", "value": null}]}], '
                '"red_flags": ["..."], "summary_errors": ["..."], "one_line": "..."}')


def review_request(t, c, role="fundamentals", prefix="fund"):
    summary = c.get("summary") or {}
    payload = {"ticker": t, "metrics_table": c["metrics"], "filing": c["filing"],
               "junior_summary": {k: summary.get(k) for k in ("summary", "guidance", "red_flags")},
               "quotes": [{k: q[k] for k in ("id", "point", "quote", "section", "verified")} for q in c["quotes"]]}
    return {"id": f"{prefix}-{re.sub(r'[^A-Za-z0-9]', '_', t)}", "ticker": t, "role": role,
            "system": REVIEW_SYSTEM, "prompt": json.dumps(payload) + "\n\nJSON shape:\n" + REVIEW_SHAPE, "max_tokens": 3000}   # 1500 cut replies off


def needs_escalation(t, c, review, likely_new):
    """Sonnet takes a second look when there's something to check or the stock is a likely new buy."""
    why = []
    if t in likely_new:
        why.append("likely new buy")
    quotes = c.get("quotes", [])
    if quotes and sum(not q["verified"] for q in quotes) / len(quotes) > 0.5:
        why.append("most summary quotes unverified")        # a few misquotes are dropped anyway
    flags = c.get("flags") or {}
    if flags.get("material_weakness") or flags.get("going_concern"):
        why.append("serious filing flag (material weakness / going concern)")   # every summary lists some risks
    if review.get("trajectory") == "deteriorating":
        why.append("deteriorating")
    if review.get("summary_errors"):
        why.append("summary errors found")
    if not review:
        why.append("first review unusable")
    return why


DIFF_SYSTEM = ("You compare a company's latest SEC filing with its previous one of the same type. You get ONLY the "
               "sentences that were added and removed (MD&A and risk factors). List the changes that matter for the "
               "stock over the next 1-3 months, e.g. a new risk factor, a dropped growth claim, softer demand "
               "language. Ignore date and number roll-forwards. " + JSON_RULE)
DIFF_SHAPE = ('{"changes": [{"change": "one sentence", "direction": "negative|positive|neutral"}], '
              '"tone": "more cautious|similar|more confident"}')


def diff_note(session, t, diff):
    if not diff or not diff.get("added_count") and not diff.get("removed_count"):
        return None
    prompt = (f"COMPANY: {t}\nADDED SENTENCES:\n{diff['added_text'] or '(none)'}\n\nREMOVED SENTENCES:\n"
              f"{diff['removed_text'] or '(none)'}\n\nAt most 5 changes. JSON shape:\n{DIFF_SHAPE}")
    try:
        r = session.ask("filing_diff", DIFF_SYSTEM, prompt, max_tokens=800, thinking="low")
    except llm.BudgetExceeded:
        raise
    except Exception as e:
        if "credit balance" in str(e):                 # out of credit: stop so the run can resume later
            raise
        print(f"    ! filing comparison note {t}: {str(e)[:60]}")
        return None
    d = r.data if isinstance(r.data, dict) else {}
    ch = [c for c in d.get("changes", []) if isinstance(c, dict) and c.get("change")][:5]
    return {"changes": ch, "tone": d.get("tone", "similar")}


def fundamentals(session, sec, picks, bench, fcache, todo, ck=None, likely_new=()):
    out, reqs, ctx = {}, [], {}
    for t in todo:
        row = bench.loc[t]
        if ck and ck.has_item("fund_ctx", t):
            ctx[t] = ck.item("fund_ctx", t)
            reqs.append(review_request(t, ctx[t]))
            continue
        cik = int(row["cik"]) if pd.notna(row.get("cik")) else None
        f = fcache.get(str(cik)) if cik else None
        metrics = metrics_table(row, f)
        try:
            filing = get_filing(sec, cik)
        except Exception as e:
            print(f"    ! filing fetch {t}: {str(e)[:80]}")
            filing = None
        summary, notes = {}, []
        if filing and filing["text"]:
            doc = f"COMPANY: {t} ({row['name']})\nFILING: {filing['form']} filed {filing['filed']}\n\n{filing['text']}"
            if filing["release"]:
                doc += f"\n\nEARNINGS RELEASE filed {filing['release_filed']}:\n{filing['release']}"
            r = session.ask("filing_summary", SUMMARY_SYSTEM, "JSON shape:\n" + SUMMARY_SHAPE, shared=doc,
                            max_tokens=3000, thinking=1024)
            summary = r.data if isinstance(r.data, dict) else {}
            notes = verify_quotes(summary, filing)
        extras = {}
        if cik and hasattr(sec, "companyfacts"):
            try:
                extras = extra_metrics(sec.companyfacts(cik))
            except Exception as e:
                print(f"    ! extra SEC metrics {t}: {str(e)[:60]}")
        diff = (filing or {}).get("diff")
        ctx[t] = {"metrics": metrics, "filing": filing and {k: filing[k] for k in ("form", "filed", "release_filed")},
                  "summary": summary, "quotes": notes, "extras": extras, "flags": (filing or {}).get("flags") or {},
                  "diff": diff and {k: diff[k] for k in ("unchanged_share", "added_count", "removed_count", "prior_filed")},
                  "diff_note": diff_note(session, t, diff)}
        if ck:
            ck.save_item("fund_ctx", t, ctx[t])
        reqs.append(review_request(t, ctx[t]))
    results = session.batch(reqs, checkpoint=ck, key="fund_review") if reqs else {}     # Mistral (free)
    first = {q["ticker"]: (results.get(q["id"]).data if results.get(q["id"]) and isinstance(results.get(q["id"]).data, dict) else {})
             for q in reqs}
    escalate = {t: needs_escalation(t, ctx[t], first[t], set(likely_new)) for t in first}
    esc_reqs = [review_request(t, ctx[t], "fundamentals_escalation", "esc") for t, why in escalate.items() if why]
    esc = session.batch(esc_reqs, checkpoint=ck, key="fund_escalation") if esc_reqs else {}   # Sonnet (batched)
    for req in reqs:
        t = req["ticker"]
        er = esc.get(f"esc-{re.sub(r'[^A-Za-z0-9]', '_', t)}")
        if er and isinstance(er.data, dict) and er.data:
            review = dict(er.data, reviewed_by=er.model, escalated_because=escalate[t])
        else:
            res = results.get(req["id"])
            review = dict(first[t], reviewed_by=res.model if res else None) if first[t] else {}
        auditor = Auditor(notes=[{"id": q["id"], "score_eligible": q["verified"], "verified_number": q["verified"]}
                                 for q in ctx[t]["quotes"]],
                          metrics={t: {k: v for k, v in ctx[t]["metrics"].items() if isinstance(v, (int, float))}})
        problems = []
        for kp in review.get("key_points", []) if isinstance(review.get("key_points"), list) else []:
            kp["evidence"], p = auditor.filter(kp.get("evidence"))
            problems += p
        try:
            review["score"] = int(min(5, max(1, round(float(review.get("score", 3))))))
        except Exception:
            review["score"] = 3
        out[t] = dict(ctx[t], review=review, audit_problems=problems)
    return out


# ==================================================================== 4. CATALYSTS
CATALYST_SYSTEM = ("You are an event-driven analyst. Use search to find DATED events for this company in the next "
                   "90 days that could move the stock: earnings date, guidance updates, product launches, FDA or "
                   "regulatory decisions, court rulings, index additions/removals, investor days, share lockups, "
                   "debt maturities, pending mergers. Prefer the company's own press releases, SEC filings, and major "
                   "wire services. Every event needs a date (or 'expected <month>') and the exact source URL. "
                   "Do not use forums, social media, or stock-promotion sites. " + JSON_RULE)


def catalysts(session, todo, bench, calendar_dates, ck=None):
    out = {}
    for t in todo:
        if ck and ck.has_item("catalysts", t):
            out[t] = ck.item("catalysts", t)
            continue
        row = bench.loc[t]
        prompt = (f"Company: {row['name']} (ticker {t}). Today is {TODAY}.\n"
                  'JSON: {"events": [{"date": "YYYY-MM-DD or expected Month YYYY", "event": "...", '
                  '"likely_impact": "positive|negative|uncertain", "url": "exact source URL"}]}')
        r = session.ask("catalyst", CATALYST_SYSTEM, prompt, max_tokens=2000, thinking=1024,
                        search={"max_uses": 3, "blocked": config.COMPANY_BLOCKED_DOMAINS})
        events = (r.data or {}).get("events", []) if isinstance(r.data, dict) else []
        rec_urls = {x["url"] for x in r.receipts}
        rec_domains = {domain(u) for u in rec_urls}
        kept, dropped = [], []
        for e in events if isinstance(events, list) else []:
            if not isinstance(e, dict):
                continue
            url = e.get("url", "")
            cls = source_class(url)
            if cls == "blocked":
                dropped.append(dict(e, reason="blocked site"))
                continue
            if url not in rec_urls and domain(url) not in rec_domains:
                dropped.append(dict(e, reason="source not in search results"))
                continue
            e["source_class"] = cls
            e["rumor"] = is_rumor(e.get("event"))
            # primary sources, or a dated specific fact from a reputable newsroom (never a rumor)
            e["score_eligible"] = cls == "primary" or (cls == "reputable" and not e["rumor"] and bool(e.get("date")))
            kept.append(e)
        if calendar_dates.get(t):
            kept.insert(0, {"date": calendar_dates[t], "event": "Scheduled earnings report", "likely_impact": "uncertain",
                            "url": "finnhub earnings calendar", "source_class": "data", "score_eligible": True})
        out[t] = {"events": kept, "dropped": dropped, "found_on": TODAY.isoformat()}
        if ck:
            ck.save_item("catalysts", t, out[t])
    return out


# ==================================================================== 5-6. DEBATE + JUDGE
def build_dossier(t, row, news, fund, cat, macro, base=None, extra=(), events=None, today=None):
    """Numbered facts (D1, D2, ...) with the date each is as of; anything past its age limit is marked
    STALE. Order: base rate, macro, screen, price, the new inputs, then news, filings and catalysts."""
    items = []
    today = today or TODAY.isoformat()

    def add(kind, text, date=None, **kw):
        items.append(dict({"id": f"D{len(items) + 1}", "kind": kind, "text": text, "date": date}, **kw))

    if base:
        add("base_rate", history.describe(base), today)
    sec_tilt = (macro or {}).get("tilts", {}).get(row["sector"], 0)
    add("macro", f"Macro view: {row['sector']} tilt {int(sec_tilt):+d} (scale -2..+2); regime {(macro or {}).get('regime', 'n/a')}; "
                 f"Fed {(macro or {}).get('fed', 'n/a')}."
        + (f" Expected moves: {json.dumps((macro or {}).get('factor_view'))}." if (macro or {}).get("factor_view") else ""),
        (macro or {}).get("date"))
    add("screen", f"Screen percentile ranks within sector (0-1): composite {row['composite']:.2f}, momentum {row['s_momentum']:.2f}, "
                  f"earnings {row['s_earnings']:.2f}, quality {row['s_quality']:.2f}, value {row['s_value']:.2f}, insider {row['s_insider']:.2f}.",
        today)
    add("price", f"12-1 month return {row.get('mom_12_1', float('nan')):.1%}, 3-month {row.get('mom_3m', float('nan')):.1%}, "
                 f"annualized volatility {row.get('vol_60d', float('nan')):.0%}, price ${row.get('price', float('nan')):.2f}.", today)
    for kind, text in extra:
        add(kind, text, today)
    for e in events or []:
        add("event_8k", f"8-K filed {e['filed']}: {e['what']} (items {', '.join(e['items'])}).", e["filed"], url=e.get("url"))
    if row.get("insider_value", 0) > 0:
        add("insider", f"Insider open-market buys last 90 days: ${row['insider_value']:,.0f} by {int(row['insider_buyers'])} insiders (SEC Form 4).", today)
    if row.get("flags"):
        add("flags", f"Screen flags: {row['flags']}", today)
    n = news or {}
    add("news", f"News last {NEWS_DAYS} days: {n.get('count', 0)} headlines, {n.get('good', 0)} good / {n.get('bad', 0)} bad, score {n.get('score', 0):+.2f}.", today)
    for x in (n.get("items") or [])[:6]:
        add("headline", f"[{x.get('label', '?')}] {x['source']}: {x['headline']}" + (f" -- {x['summary']}" if x.get("summary") else ""),
            x.get("date"), url=x.get("url"))
    fund = fund or {}
    fdate = (fund.get("filing") or {}).get("filed")
    rv = fund.get("review") or {}
    if rv:
        add("fundamentals", f"Fundamentals review: trajectory {rv.get('trajectory')}, score {rv.get('score')}/5. {rv.get('one_line', '')}", fdate)
        for kp in rv.get("key_points", [])[:5]:
            add("fundamentals", kp.get("point", ""), fdate, evidence=kp.get("evidence"))
        for rf in rv.get("red_flags", [])[:3]:
            add("red_flag", f"Red flag: {rf}", fdate)
    seg = (fund.get("summary") or {}).get("segments")
    if seg and str(seg).lower() not in ("none", "none reported", "n/a"):
        add("fundamentals", f"Segments: {seg}", fdate)
    fl = fund.get("flags") or {}
    for label, key in (("MATERIAL WEAKNESS in accounting controls", "material_weakness"),
                       ("GOING-CONCERN doubt", "going_concern"), ("Customer concentration", "customer_concentration"),
                       ("Geographic revenue exposure", "geo_revenue"), ("Where it makes/sources products", "geo_supply")):
        for sentence in fl.get(key, [])[:2]:
            add("filing_flag", f"{label} (from the filing): \"{sentence}\"", fdate)
    dn, dd = fund.get("diff_note"), fund.get("diff")
    if dd:
        txt = (f"Filing vs the prior {(fund.get('filing') or {}).get('form')} (filed {dd.get('prior_filed')}): "
               f"{dd['unchanged_share']:.0%} of sentences unchanged, {dd['added_count']} added, {dd['removed_count']} removed")
        if dn:
            txt += f"; tone {dn.get('tone')}. " + " ".join(f"[{c.get('direction')}] {c['change']}" for c in dn.get("changes", []))
        add("filing_change", txt, fdate)
    ex = fund.get("extras") or {}
    if ex.get("quarters"):
        q = ex["quarters"]
        add("financials", "Quarterly revenue $M / gross margin % / operating margin %: " + "; ".join(
            f"{x['end']}: {x['revenue_$M']} / {x.get('gross_margin_%')} / {x.get('operating_margin_%')}" for x in q[-6:]),
            q[-1]["end"])
    det = {k: v for k, v in ex.items() if k not in ("quarters",)}
    if det:
        add("financials", "Latest vs a year ago: " + "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in det.items()),
            (ex.get("quarters") or [{}])[-1].get("end") or fdate)
    for k, v in (fund.get("metrics") or {}).items():
        if not k.startswith("screen_"):
            add("metric", f"{k} = {v} (SEC filings)", (fund.get("metrics") or {}).get("financials_as_of"))
    for q in fund.get("quotes", []):
        if q["verified"]:
            add("filing_quote", f"{q['point']}: \"{q['quote']}\" ({(fund.get('filing') or {}).get('form')} {q['section']})", fdate)
    for e in (cat or {}).get("events", []):
        d = str(e.get("date") or "")
        if re.match(r"\d{4}-\d{2}-\d{2}$", d) and d < today:
            # an event dated before today isn't upcoming: recent ones stay as context, old ones are dropped
            if (date.fromisoformat(today) - date.fromisoformat(d)).days <= 30:
                add("recent_event", f"Already happened on {d}: {e.get('event')} (source: {e.get('source_class')})",
                    (cat or {}).get("found_on") or today, url=e.get("url"))
            continue
        add("catalyst", f"{e.get('date')}: {e.get('event')} (impact: {e.get('likely_impact')}; source: {e.get('source_class')})",
            (cat or {}).get("found_on") or today, url=e.get("url"))
    for i in items:                               # age check
        try:
            age = (pd.Timestamp(today) - pd.Timestamp(i["date"])).days if i.get("date") else None
        except (ValueError, TypeError):
            age = None
        limit = config.STALE_DAYS.get(i["kind"], config.STALE_DAYS["default"])
        i["stale"] = bool(age is not None and age > limit)
    return inputs.limit_dossier(items)


def dossier_text(t, name, items):
    tag = lambda i: f"[{i['kind']}" + (f", as of {i['date']}" if i.get("date") else "") + (", STALE" if i.get("stale") else "") + "]"
    return f"DOSSIER: {t} ({name})\n" + "\n".join(f"{i['id']}. {tag(i)} {i['text']}" for i in items)


DEBATE_SYSTEM = {
    "bull": "You are the BULL analyst. Make the strongest honest case to OWN this stock for the next 1-3 months.",
    "bear": "You are the BEAR analyst. Make the strongest honest case AGAINST owning this stock for the next 1-3 months.",
}
DEBATE_RULES = (" Use ONLY the dossier. Every point must cite dossier item ids (e.g. D4). No outside facts. "
                "Be concrete; 3-5 points. " + JSON_RULE)
ARG_SHAPE = '{"points": [{"claim": "...", "cites": ["D1"]}], "summary": "one sentence"}'


def debate_models(n):
    """Which free model debates each of n stocks (in order): fill each pool entry up to its cap."""
    pool = [e for e in config.DEBATE_POOL if llm.has_key(e["model"])]
    if not pool:
        return [None] * n                       # no pool keys: use the debate roles' own fallback chain
    out = []
    for e in pool:
        out += [e["model"]] * int(e["max_stocks"])
    out += [pool[-1]["model"]] * max(0, n - len(out))
    return out[:n]


def _one_debate(session, text, feedback, model):
    a = {}
    for side in ("bull", "bear"):
        r = session.ask(f"debate_{side}", DEBATE_SYSTEM[side] + DEBATE_RULES, feedback + "Opening argument. JSON: " + ARG_SHAPE,
                        shared=text, max_tokens=1500, thinking=512, model=model)
        a[f"{side}_open"] = r.data if isinstance(r.data, dict) else {"points": [], "summary": r.text[:300]}
    for side, other in (("bull", "bear"), ("bear", "bull")):
        r = session.ask(f"debate_{side}", DEBATE_SYSTEM[side] + DEBATE_RULES,
                        f"{feedback}The {other} argued:\n{json.dumps(a[f'{other}_open'])}\n\nRebut their strongest points. JSON: " + ARG_SHAPE,
                        shared=text, max_tokens=1200, thinking=512, model=model)
        a[f"{side}_rebuttal"] = r.data if isinstance(r.data, dict) else {"points": [], "summary": r.text[:300]}
    a["model"] = r.model                       # recorded for the ledger; judges don't see it
    return a


def debate(session, dossiers, ck=None, feedback=""):
    """Per stock: independent bull and bear openings, then each side rebuts the other once.
    Both sides always use the same model; a debate that fails partway reruns whole on the next model."""
    args = {}
    assigned = debate_models(len(dossiers))
    pool = [e["model"] for e in config.DEBATE_POOL if llm.has_key(e["model"])]
    for i, (t, text) in enumerate(dossiers.items()):
        if ck and ck.has_item("debate", t):
            args[t] = ck.item("debate", t)
            continue
        order = ([assigned[i]] + [m for m in pool if m != assigned[i]] if assigned[i] else []) + [None]
        order = [m for m in order if m is None or m not in session.benched]   # skip providers that keep failing
        for j, model in enumerate(order):
            try:
                a = _one_debate(session, text, feedback, model)
                break
            except llm.BudgetExceeded:
                raise
            except Exception as e:
                if j + 1 == len(order):
                    raise
                print(f"  ! {t}: debate on {model} failed ({str(e)[:80]}); rerunning on {order[j + 1] or 'fallback chain'}")
        args[t] = ck.save_item("debate", t, a) if ck else a
    return args


COUNCIL_SYSTEM = ("You are an investor council of three distinct investing styles reviewing one stock. You get a dossier "
                  "and the bull/bear debate. Each member speaks ONLY from their own lens about owning the stock over the "
                  "next 1-3 months. Use ONLY the dossier; every point must cite dossier item ids (e.g. D4). No outside "
                  "facts. 2-3 points per member. " + JSON_RULE)


def council_prompt(debate_args):
    lenses = "\n".join(f"- {m['id']}: {m['lens']}" for m in config.COUNCIL)
    shape = "{" + ", ".join(f'"{m["id"]}": {{"stance": "favor|against|neutral", "points": [{{"claim": "...", "cites": ["D1"]}}], '
                            f'"summary": "one sentence"}}' for m in config.COUNCIL) + "}"
    shown = {k: v for k, v in (debate_args or {}).items() if k != "model"}
    return f"MEMBERS:\n{lenses}\n\nDEBATE:\n{json.dumps(shown)}\n\nJSON shape:\n{shape}"


def council_note(session, text, debate_args, label=""):
    """One stock's council notes {member id: {stance, points, summary}}, or None if the call failed."""
    try:
        r = session.ask("council", COUNCIL_SYSTEM, council_prompt(debate_args), shared=text, max_tokens=2000,
                        thinking=512)
        if isinstance(r.data, dict):
            notes = {m["id"]: r.data[m["id"]] for m in config.COUNCIL if isinstance(r.data.get(m["id"]), dict)}
            return notes or None
    except llm.BudgetExceeded:
        raise
    except Exception as e:
        print(f"  ! {label}: council failed ({str(e)[:80]}); no council dossier for it")
    return None


def council(session, dossiers, args, ck=None):
    """Per stock, the investor council's cited notes (or None if the call failed). Feeds only the hidden council
    dossier (config.COUNCIL_JUDGE); never the live judges. A failure here never stops the rebuild."""
    cj = config.COUNCIL_JUDGE or {}
    if not cj.get("enabled") or not config.COUNCIL or not llm.has_key(cj["model"]):
        return {}
    out = {}
    for t, text in dossiers.items():
        if ck and ck.has_item("council", t):
            out[t] = ck.item("council", t)
            continue
        notes = council_note(session, text, args.get(t), label=t)
        out[t] = ck.save_item("council", t, notes) if ck else notes
    done = sum(1 for v in out.values() if v)
    print(f"    council notes for {done} of {len(dossiers)} stocks")
    return out


SIGNALS_SYSTEM = ("You score three narrow things about one stock, each from -2 (clearly bad for the stock over the "
                  "next 1-3 months) to +2 (clearly good), 0 when the evidence is absent or balanced. Use ONLY the "
                  "dossier and the PEER RESULTS table; cite dossier item ids for the first two.\n"
                  "- beat_quality: was the latest earnings result driven by the core business (+) or by one-offs, "
                  "accounting, tax or timing items (-)?\n"
                  "- guidance: did management's outlook and wording get stronger (+) or weaker (-) versus before?\n"
                  "- read_across: what do the recent results of this company's peers, customers and suppliers imply "
                  "for its OWN next report, beyond what its price already shows? " + JSON_RULE)
SIGNALS_SHAPE = ("{" + ", ".join(f'"{k}": {{"score": 0, "reason": "one sentence", "cites": ["D1"]}}'
                                 for k in config.SHADOW_SIGNALS) + "}")


def peer_results(tickers, bench, feats, today=None):
    """Per stock, a text table of same-sub-industry peers that reported earnings in the last PEER_WINDOW_DAYS and
    after the stock's own last report: news the stock has not yet reported against."""
    today = today or TODAY
    cut = (today - timedelta(days=config.PEER_WINDOW_DAYS)).isoformat()
    last = {}
    for t, f in (feats or {}).items():
        rs = (f or {}).get("reactions") or []
        if rs:
            last[t] = (str(rs[-1]["date"])[:10], rs[-1].get("vs_sector_%"))
    group = "sub_industry" if "sub_industry" in bench.columns else "sector"
    out = {}
    for t in tickers:
        if t not in bench.index:
            continue
        own = last.get(t, ("", None))[0]
        peers = [(last[p][0], p, last[p][1]) for p in bench.index[bench[group] == bench.loc[t, group]]
                 if p != t and p in last and last[p][0] >= cut and last[p][0] > own and last[p][1] is not None]
        peers.sort(reverse=True)
        out[t] = ("PEER RESULTS (same sub-industry, reported after this company's last report):\n"
                  + ("\n".join(f"{p} reported {d}: moved {v:+.1f}% vs its sector" for d, p, v in peers[:8]) or "none")
                  + (f"\nThis company last reported {own}." if own else ""))
    return out


def shadow_signals(session, dossiers, peers, ck=None):
    """{ticker: {signal: {"score": -2..2, "reason", "cites"}}} or None per stock. A test logged to the ledger only;
    a failure here never stops the rebuild."""
    if not config.SHADOW_SIGNALS or not llm.has_key(config.MODELS["shadow_signals"]):
        return {}
    out = {}
    for t, text in dossiers.items():
        if ck and ck.has_item("signals", t):
            out[t] = ck.item("signals", t)
            continue
        got = None
        try:
            r = session.ask("shadow_signals", SIGNALS_SYSTEM, f"{peers.get(t, 'PEER RESULTS: none')}\n\nJSON shape:\n{SIGNALS_SHAPE}",
                            shared=text, max_tokens=1200, thinking=512)
            if isinstance(r.data, dict):
                got = {}
                for k in config.SHADOW_SIGNALS:
                    v = r.data.get(k)
                    if isinstance(v, dict) and isinstance(v.get("score"), (int, float)):
                        got[k] = {"score": max(-2.0, min(2.0, float(v["score"]))), "reason": str(v.get("reason") or "")[:300],
                                  "cites": [c for c in (v.get("cites") or []) if isinstance(c, str)][:6]}
                got = got or None
        except llm.BudgetExceeded:
            raise
        except Exception as e:
            print(f"  ! {t}: shadow signals failed ({str(e)[:80]})")
        out[t] = ck.save_item("signals", t, got) if ck else got
    print(f"    shadow signals for {sum(1 for v in out.values() if v)} of {len(dossiers)} stocks")
    return out


COUNCIL_HEADER = ("INVESTOR COUNCIL (three investing styles reviewed the dossier and debate; their points are "
                  "perspectives, not evidence: weigh one only through the dossier items it cites):")


def with_council(prompt, notes, ids):
    """The standard judge prompt with the council's notes inserted before the invalid-claims list, and the
    council's own bad citations added to that list. Used live and by the replay of past rebuilds."""
    m = re.match(r"(ARGUMENTS:\n.*?)\n\nUNCITED OR INVALID CLAIMS \(discount these\):\n(.*?)\n\n(.*)$", prompt, re.S)
    if not m:
        return None
    head, bad_json, rest = m.groups()
    bad = json.loads(bad_json) + citation_check(notes, ids)
    return (f"{head}\n\n{COUNCIL_HEADER}\n{json.dumps(notes)}\n\nUNCITED OR INVALID CLAIMS (discount these):\n"
            f"{json.dumps(bad)}\n\n{rest}")


def citation_check(arg_set, ids):
    bad = []
    for k, a in arg_set.items():
        if not isinstance(a, dict):
            continue
        for p in (a or {}).get("points", []) if isinstance((a or {}).get("points"), list) else []:
            cites = p.get("cites") or []
            if not cites or any(c not in ids for c in cites):
                bad.append(f"{k}: '{str(p.get('claim', ''))[:80]}' cites {cites or 'nothing'}")
    return bad


JUDGE_SYSTEM = (
    "You are a judge on an investment committee. Forecast the PROBABILITY that this stock beats its "
    "equal-weighted sector over the next 4 weeks, using only the dossier and the bull/bear arguments.\n"
    "- Start from the BASE RATE item: how often similar stocks beat their sector. It lists exactly what it "
    "already reflects (momentum, earnings reaction, quality, and sometimes value or volatility): do NOT adjust "
    "for those again.\n"
    "- Move it only for information the base rate doesn't contain (filings, news, catalysts, valuation, macro "
    "sensitivities vs the macro view, the debate). List each adjustment in percentage points with the dossier "
    "ids that support it. Uncited adjustments are removed.\n"
    "- Keep the total within +/-15 points. Only something exceptional (an acquisition offer, a regulatory "
    "decision, a guidance shock) justifies more: then set exception true and cite it.\n"
    "- Realistic 4-week forecasts mostly land between 40% and 62%; 70%+ should be rare.\n"
    "- Ignore claims listed as uncited or citing items that don't exist. The exit condition must be specific "
    "and observable (e.g. 'guidance cut below $X'), not a price move, and must NOT already be true today: "
    "check any level it names (yields, oil, spreads) against the macro data in the dossier. Catalysts marked "
    "'Already happened' are past, not upcoming. " + JSON_RULE)
JUDGE_SHAPE = ('{"adjustments": [{"points": 3, "reason": "...", "cites": ["D7"]}], "exception": false, '
               '"exception_reason": "", "probability": 0.55, "winner": "bull|bear|draw", "thesis": "2 sentences", '
               '"key_risk": "...", "exit_condition": "...", "primary_driver": "the one macro/market factor this stock '
               'most depends on, 1-3 words", "evidence": ["D1", "D5"], "discounted_claims": ["..."]}')


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def expit(x):
    return 1 / (1 + math.exp(-x))


def label(edge_pts):
    """A 1-5 label derived from the probability's edge over its base rate (for emails and old reports)."""
    return 5 if edge_pts >= 7 else 4 if edge_pts >= 3 else 3 if edge_pts > -2 else 2 if edge_pts > -5 else 1


def active_panel(panel=None):
    """Enabled judges whose API key is set. A judge without a key is skipped (and said so)."""
    out = []
    for j in (config.JUDGE_PANEL if panel is None else panel):
        if not j.get("enabled", True):
            continue
        if not llm.has_key(j["model"]):
            print(f"    judge {j['id']} ({j['model']}) skipped: no {llm.key_name(j['model'])} secret")
            continue
        out.append(j)
    if not any(j.get("live") for j in out):
        out.append({"id": "judge_default", "model": config.MODELS["judge"], "live": True, "thinking": None, "sample": 1.0})
        print(f"    no live judge available; using {config.MODELS['judge']}")
    return out


def in_sample(j, ticker, day=None):
    """A judge with sample < 1 scores a fixed pseudo-random share of stocks (stable across retries)."""
    share = float(j.get("sample", 1.0))
    if share >= 1:
        return True
    h = int(hashlib.sha256(f"{j['id']}|{ticker}|{day or TODAY}".encode()).hexdigest()[:8], 16)
    return h / 0xFFFFFFFF < share


def clean_verdict(v, ids, base_p=0.5):
    """A usable single-judge forecast, or None. The probability is rebuilt by code from the base rate
    plus the judge's CITED adjustments (capped), so an uncited or out-of-bounds number can't slip in."""
    if not isinstance(v, dict):
        return None
    adj_in = v.get("adjustments") if isinstance(v.get("adjustments"), list) else None
    stated = v.get("probability")
    try:
        stated = float(stated)
        stated = stated / 100 if stated > 1 else stated
    except (TypeError, ValueError):
        stated = None
    if adj_in is None and stated is None:
        return None
    kept, dropped = [], 0
    for a in adj_in or []:
        try:
            pts = float(a.get("points"))
        except (TypeError, ValueError, AttributeError):
            dropped += 1
            continue
        cites = [c for c in (a.get("cites") or []) if c in ids]
        if not cites or pts != pts:
            dropped += 1
            continue
        kept.append({"points": round(pts, 1), "reason": str(a.get("reason", ""))[:200], "cites": cites})
    total = sum(a["points"] for a in kept)
    cap = config.PROB["adjust_cap"]
    exception = bool(v.get("exception")) and bool(v.get("exception_reason")) and bool(kept)
    if not exception:
        total = max(-cap, min(cap, total))
    lo, hi = config.PROB["clip"]
    p = min(hi, max(lo, base_p + total / 100))
    out = dict(v, probability=round(p, 4), base_p=round(base_p, 4), edge_pts=round((p - base_p) * 100, 1),
               adjustments=kept, dropped_adjustments=dropped, exception=exception,
               stated_probability=round(stated, 4) if stated is not None else None)
    out["conviction"] = label(out["edge_pts"])
    out["evidence"] = [e for e in v.get("evidence", []) if e in ids] if isinstance(v.get("evidence"), list) else []
    if not out.get("exit_condition"):
        out["exit_condition"] = "not provided (review manually)"
    return out


# ==================================================================== sell triggers already met
EXIT_LEVELS = [  # (words that name the level, FRED series, label)
    (r"10[- ]?(?:yr|year)|ten[- ]year", "DGS10", "10-year Treasury yield"),
    (r"2[- ]?(?:yr|year)|two[- ]year", "DGS2", "2-year Treasury yield"),
    (r"brent", "DCOILBRENTEU", "Brent crude"),
    (r"\bwti\b|crude|\boil\b", "DCOILWTICO", "WTI crude"),
    (r"\bvix\b", "VIXCLS", "VIX"),
    (r"fed funds|federal funds|policy rate", "DFF", "fed funds rate"),
    (r"mortgage rate", "MORTGAGE30US", "30-year mortgage rate"),
    (r"high[- ]yield spread|credit spread|hy spread", "BAMLH0A0HYM2", "high-yield spread"),
]
UP = r"(?:rises? above|climbs? above|goes above|moves? above|above|exceeds?|over|tops?|>|higher than)"
DOWN = r"(?:falls? below|drops? below|goes below|below|under|<|lower than)"


def exit_already_met(text, levels):
    """A sell trigger that names a macro level already past its threshold (e.g. '10-yr above 4.5%' with the
    10-year at 5.18%): returns a plain-English reason, or None. Checks only what it can parse."""
    t = str(text or "").lower()
    for words, sid, label in EXIT_LEVELS:
        now = (levels.get(sid) or {}).get("latest") if isinstance(levels.get(sid), dict) else levels.get(sid)
        if now is None:
            continue
        for m in re.finditer(words, t):
            tail = t[m.end():m.end() + 60]
            hit = re.search(rf"({UP}|{DOWN})\s*\$?\s*(\d+(?:\.\d+)?)\s*(%|bp|bps)?", tail)
            if not hit:
                continue
            lvl = float(hit.group(2))
            if hit.group(3) in ("bp", "bps") and sid == "BAMLH0A0HYM2":
                lvl /= 100
            up = re.fullmatch(UP, hit.group(1)) is not None
            if (up and now > lvl) or (not up and now < lvl):
                return f"{label} is already {now:g} ({'above' if up else 'below'} the {lvl:g} trigger)"
    return None


def combine(per_judge, panel, bad, base_p=0.5):
    """Live judges averaged on the log-odds scale; the written rationale comes from the live judge
    closest to that average. Shadows are recorded but never move the forecast."""
    order = {j["id"]: i for i, j in enumerate(panel)}
    info = {j["id"]: j for j in panel}
    live = {jid: v for jid, v in per_judge.items() if v and info.get(jid, {}).get("live")}
    judges = {jid: {"model": info[jid]["model"], "live": bool(info[jid].get("live")),
                    **({k: v.get(k) for k in ("probability", "edge_pts", "exception", "winner", "primary_driver",
                                              "thesis", "key_risk", "exit_condition", "dropped_adjustments")} if v
                       else {"probability": None, "error": "no usable reply"})}
              for jid, v in per_judge.items()}
    if not live:
        return {"probability": base_p, "base_p": base_p, "edge_pts": 0.0, "conviction": 1, "spread": None,
                "disagreement": True, "panel_failed": True, "winner": "draw",
                "thesis": "No live judge returned a usable forecast.", "key_risk": "unjudged",
                "exit_condition": "not provided (review manually)", "primary_driver": "", "evidence": [],
                "judges": judges, "live_judges": [], "lead_judge": None, "invalid_citations": bad}
    x = sum(logit(v["probability"]) for v in live.values()) / len(live)
    p = expit(x)
    lead = min(live, key=lambda jid: (abs(logit(live[jid]["probability"]) - x), order.get(jid, 99)))
    probs = [v["probability"] for v in live.values()]
    spread = round((max(probs) - min(probs)) * 100, 1)
    out = {k: v for k, v in live[lead].items() if k not in ("adjustments", "stated_probability", "dropped_adjustments")}
    edge = round((p - base_p) * 100, 1)
    # shadow: the average pushed further from the base rate (averages of forecasters come out too timid);
    # recorded and graded against the plain average, never used for decisions
    sharp = expit(logit(base_p) + config.PANEL_SHARPEN * (x - logit(base_p)))
    out.update({"probability": round(p, 4), "probability_sharp": round(sharp, 4),
                "base_p": round(base_p, 4), "edge_pts": edge, "conviction": label(edge),
                "spread": spread, "disagreement": spread >= config.JUDGE_DISAGREEMENT, "lead_judge": lead,
                "live_judges": sorted(live, key=lambda k: order.get(k, 99)), "judges": judges,
                "adjustments": live[lead].get("adjustments", []), "invalid_citations": bad,
                "exceptions": sorted(j for j, v in live.items() if v.get("exception"))})
    return out


def judge(session, dossiers, args, dossier_ids, ck=None, panel=None, feedback="", base=None, council_notes=None):
    """Every judge sees the identical packet (blind: nobody is told which stocks are owned). One batch
    call covers all judges and stocks; each provider's share goes through its own batch API, resumable
    from the checkpoint. Returns (verdicts, panel, packets); packets are archived for later replays.
    With council notes, the shadow council judge (config.COUNCIL_JUDGE) gets the same packet plus the notes."""
    panel = active_panel(panel)
    council_notes = council_notes or {}
    cj = dict(config.COUNCIL_JUDGE or {})
    if council_notes and cj.get("enabled") and llm.has_key(cj["model"]) and all(j["id"] != cj["id"] for j in panel):
        cj["live"] = False                      # the hidden dossier never counts toward the forecast
        panel = panel + [cj]
    base = base or {}
    reqs, bad_of, packets = [], {}, {}
    for t, text in dossiers.items():
        bad = citation_check(args[t], dossier_ids[t])
        bad_of[t] = bad
        shown = {k: v for k, v in args[t].items() if k != "model"}
        prompt = (f"ARGUMENTS:\n{json.dumps(shown)}\n\nUNCITED OR INVALID CLAIMS (discount these):\n"
                  f"{json.dumps(bad)}\n\n{feedback}JSON shape:\n{JUDGE_SHAPE}")
        safe = re.sub(r"[^A-Za-z0-9]", "_", t)
        packets[t] = {"system": JUDGE_SYSTEM, "shared": text, "prompt": prompt,
                      "base_p": (base.get(t) or {}).get("p", 0.5)}
        notes = council_notes.get(t)
        c_prompt = with_council(prompt, notes, dossier_ids[t]) if notes else None
        if c_prompt:
            packets[t]["council_prompt"] = c_prompt
        for j in panel:
            is_council = j["id"] == cj.get("id")
            if is_council and not c_prompt:
                continue
            if in_sample(j, t):
                reqs.append({"id": f"judge-{j['id']}-{safe}", "ticker": t, "judge": j["id"], "role": "judge",
                             "model": j["model"], "thinking": j.get("thinking"), "system": JUDGE_SYSTEM,
                             "shared": text, "max_tokens": 1500, "prompt": c_prompt if is_council else prompt})
    # generous wait: if the workflow is stopped first, the daily job collects the saved batches later
    res = session.batch(reqs, checkpoint=ck, key="judge", tolerate=True, timeout_seconds=9000)
    per = {t: {} for t in dossiers}
    for q in reqs:
        r = res.get(q["id"])
        bp = (base.get(q["ticker"]) or {}).get("p", 0.5)
        per[q["ticker"]][q["judge"]] = clean_verdict(r.data if r else None, dossier_ids[q["ticker"]], bp)
    out = {t: combine(per[t], panel, bad_of[t], (base.get(t) or {}).get("p", 0.5)) for t in dossiers}
    missing = sum(1 for t in per for v in per[t].values() if v is None)
    if missing:
        print(f"    {missing} judge replies unusable or missing (averaged over the rest)")
    flagged = [t for t, v in out.items() if v.get("disagreement")]
    if flagged:
        print(f"    judges disagree (spread >= {config.JUDGE_DISAGREEMENT} pts) on {len(flagged)}: {flagged[:12]}")
    return out, panel, packets


def update_guidance(fund):
    """Builds each company's guidance track record from the releases the team already reads."""
    hist = read_json(state_path("guidance_history.json"), {}) or {}
    for t, f in (fund or {}).items():
        g = inputs.normalize_guidance(((f or {}).get("summary") or {}).get("guidance"))
        when = ((f or {}).get("filing") or {}).get("release_filed") or ((f or {}).get("filing") or {}).get("filed")
        if g and when and not any(x["date"] == when for x in hist.get(t, [])):
            hist.setdefault(t, []).append({"date": when, "guidance": g})
            hist[t] = sorted(hist[t], key=lambda x: x["date"])[-8:]
    write_json(state_path("guidance_history.json"), hist)
    return hist


def archive_packets(day, packets, items, args, stamp):
    """Every judge packet exactly as sent, so other models (e.g. Opus) or ablated 'twin' judges can be
    replayed later on the same inputs (pipeline/replay.py). ~1 MB per rebuild, compressed."""
    path = state_path(f"packets/{day}.jsonl.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        for t, pk in packets.items():
            f.write(json.dumps({"date": day, "ticker": t, **pk, "items": items.get(t), "args": args.get(t),
                                "versions": stamp}, default=str) + "\n")
    tmp.replace(path)
    return path


# ==================================================================== MAIN
def main(session, folder, sec=None, get=requests.get, market=None, per_ticker=None):
    sec = sec or SEC()
    cdata = read_json(state_path("candidates.json"))
    if not cdata:
        raise RuntimeError("No state/candidates.json: run the weekly screen first.")
    macro = read_json(state_path("macro_view.json"))
    # same screen + macro inputs = same run; if either changed, stale progress is discarded
    # (the candidate list itself is part of the fingerprint: two screens on the same day are different inputs)
    import hashlib
    cand_hash = hashlib.sha256(",".join(sorted(c["ticker"] for c in cdata["candidates"])).encode()).hexdigest()[:10]
    ck = Checkpoint("team", fingerprint=f"{cdata.get('date')}|{(macro or {}).get('date')}|{cand_hash}")
    if ck.resumed:
        print(f"Resuming the stock-team run started {ck.data['started']} (attempt {ck.attempts})")
    cands = cdata["candidates"]
    bench = pd.read_csv(state_path("bench.csv")).set_index("ticker")
    fcache = read_json(state_path("fundamentals_cache.json"), {})
    rcache = read_json(state_path("research_cache.json"), {})
    table = read_json(state_path("base_rates.json"))
    feats = (read_json(state_path("current_features.json"), {}) or {}).get("stocks", {})
    if not table:
        print("    ! no base-rate table yet (python -m pipeline.history): every stock starts at 50%")

    print(f"1/6 News for {len(cands)} candidates...")
    if ck.has("news"):
        news = ck.get("news")
        print("    reusing saved news")
    else:
        news = ck.save("news", score_news(session, cands, fetch_news([c["ticker"] for c in cands], get)))

    print("2/6 Shortlist...")
    ranked, picks = shortlist(cands, news)
    since = rcache.get("_last_run", "2000-01-01")
    filers = {t for t in picks if pd.notna(bench.loc[t].get("cik"))
              and fcache.get(str(int(bench.loc[t]["cik"])), {}).get("fetched", "2000-01-01") > since}
    events = ck.get("events_8k")
    if events is None:
        events = {}
        for t in picks:
            cik = bench.loc[t].get("cik")
            if pd.notna(cik) and hasattr(sec, "material_events"):
                try:
                    events[t] = sec.material_events(int(cik))
                except Exception as e:
                    print(f"    ! 8-K check {t}: {str(e)[:60]}")
        ck.save("events_8k", events)
    decisions = ck.get("decisions") or ck.save("decisions", {t: list(needs_refresh(t, rcache, news, filers, events))
                                                              for t in picks})
    todo = [t for t, (need, _) in decisions.items() if need]
    print(f"    {len(picks)} shortlisted; researching {len(todo)}, carrying forward {len(picks) - len(todo)}")

    print("3/6 Fundamentals (SEC filings -> Gemini summary -> quote check -> Sonnet review)...")
    ranked_new = [t for t in ranked.index if t in picks and not ranked.loc[t].get("incumbent")]
    fund = fundamentals(session, sec, picks, bench, fcache, todo, ck, likely_new=ranked_new[:LIKELY_NEW_BUYS])

    print("4/6 Catalysts...")
    cal = {t: bench.loc[t].get("earnings_date") for t in todo if isinstance(bench.loc[t].get("earnings_date"), str)}
    cats = catalysts(session, todo, bench, cal, ck)
    for t in todo:
        rcache[t] = {"date": TODAY.isoformat(), "fundamentals": fund.get(t), "catalysts": cats.get(t)}
    research = {t: rcache[t] for t in picks}
    guidance = update_guidance(fund)

    print("5/6 Debates...")
    finalists = list(ranked.loc[picks].assign(
        fscore=lambda d: [((research[t].get("fundamentals") or {}).get("review") or {}).get("score", 3) for t in d.index])
        .assign(order=lambda d: d.adj + 0.05 * (d.fscore - 3))
        .sort_values("order", ascending=False).index)
    held = [t for t in picks if ranked.loc[t].get("incumbent")]
    finalists = list(dict.fromkeys(finalists[:N_DEBATES] + held))
    # every stock is judged fresh every rebuild, holdings included (4-week forecasts go stale by the
    # next rebuild), and nobody on the panel is told which stocks are owned
    base = {t: history.lookup(table, feats.get(t)) for t in finalists}
    extra = ck.get("inputs") or ck.save("inputs", inputs.gather(
        finalists, bench.reset_index(), feats, guidance, market=market, per_ticker=per_ticker))
    dossiers, dossier_ids, dossier_items = {}, {}, {}
    for t in finalists:
        row = bench.loc[t].to_dict()
        row["name"] = row.get("name", t)
        items = build_dossier(t, row, news.get(t), research[t].get("fundamentals"), research[t].get("catalysts"),
                              macro, base[t], [tuple(x) for x in (extra.get(t) or {}).get("items", [])], events.get(t))
        dossier_items[t] = items
        dossier_ids[t] = {i["id"] for i in items}
        dossiers[t] = dossier_text(t, row["name"], items)
    feedback = ledger.error_feedback()
    args = debate(session, dossiers, ck, feedback=feedback)
    try:                                       # a test: never let it stop the rebuild
        notes = council(session, dossiers, args, ck)
    except llm.BudgetExceeded:
        raise
    except Exception as e:
        print(f"    ! investor council skipped ({str(e)[:100]})")
        notes = {}
    try:                                       # a test logged to the ledger only: never let it stop the rebuild
        sigs = shadow_signals(session, dossiers, peer_results(list(dossiers), bench, feats), ck)
    except llm.BudgetExceeded:
        raise
    except Exception as e:
        print(f"    ! shadow signals skipped ({str(e)[:100]})")
        sigs = {}

    print("6/6 Judge panel...")
    verdicts, panel, packets = judge(session, dossiers, args, dossier_ids, ck, feedback=feedback, base=base,
                                     council_notes=notes)
    levels = (read_json(state_path("macro_baseline.json"), {}) or {}).get("fred") or {}
    for t, v in verdicts.items():             # a sell trigger that's already met can't be a new buy's exit plan
        why = exit_already_met(v.get("exit_condition"), levels)
        if why:
            v["exit_breached"] = why
            print(f"    ! {t}: sell trigger already met ({why})")
    stamp = version_stamp(JUDGE_SYSTEM, JUDGE_SHAPE, DEBATE_RULES, feedback)   # council prompt: see COUNCIL_SYSTEM
    to_judge = dossiers
    archive_packets(TODAY.isoformat(), packets, dossier_items, args, stamp)

    rcache["_last_run"] = TODAY.isoformat()
    write_json(state_path("research_cache.json"), rcache)
    results = {"date": TODAY.isoformat(), "macro_view_date": (macro or {}).get("date"), "screen_date": cdata.get("date"),
               "stocks": {t: {"name": bench.loc[t].get("name"), "sector": bench.loc[t].get("sector"),
                              "incumbent": bool(ranked.loc[t].get("incumbent")), "composite": float(ranked.loc[t]["composite"]),
                              # volatility used for sizing: 60-day / 1-year blend when the screen has it
                              "vol_60d": float(bench.loc[t].get("vol_blend") if pd.notna(bench.loc[t].get("vol_blend", np.nan))
                                               else bench.loc[t].get("vol_60d")), "price": float(bench.loc[t].get("price")),
                              "news": {k: news[t][k] for k in ("score", "count", "good", "bad")},
                              "research_status": decisions[t][1], "verdict": verdicts[t],
                              "base_rate": base[t], "features": feats.get(t),
                              "sensitivity": (extra.get(t) or {}).get("sensitivity"),
                              "dossier": dossier_items[t], "debate": args[t], "council": notes.get(t),
                              "shadow_signals": sigs.get(t)}
                          for t in finalists}}
    results["panel"] = [{k: j.get(k) for k in ("id", "model", "live", "thinking", "sample")} for j in panel]
    results["versions"] = stamp
    if not ck.get("ledger_written"):
        ledger.record_judgments(results, {t for t in to_judge})
        try:
            ledger.record_signals(results)
        except Exception as e:
            print(f"    ! shadow signals not logged ({str(e)[:100]})")
        ledger.record_process_errors(results, session)
        ck.save("ledger_written", True)
    write_json(state_path("team_results.json"), results)
    write_json(folder / "team_results.json", results)
    write_text(folder / "report.md", report(results))
    ck.complete()
    top = sorted(results["stocks"].items(), key=lambda kv: -kv[1]["verdict"]["edge_pts"])
    for t, s in top[:15]:
        v = s["verdict"]
        print(f"  {t:<6} {v['probability'] * 100:5.1f}% (base {v['base_p'] * 100:4.1f}%, edge {v['edge_pts']:+5.1f})  {s['sector']}")
    return {"finalists": len(finalists)}


def report(res):
    L = [f"# Stock team, {res['date']}", f"Macro view {res['macro_view_date']} · screen {res['screen_date']}", "",
         "Judges: " + ", ".join(f"{j['id']} ({'live' if j['live'] else 'shadow'})" for j in res.get("panel", [])), "",
         "Probability = chance of beating the equal-weighted sector over 4 weeks; edge = points above the base rate.", "",
         "| Ticker | Sector | Probability | Base rate | Edge | Spread | Winner | Driver | Thesis | Research |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    ranked = sorted(res["stocks"].items(), key=lambda kv: (-kv[1]["verdict"].get("edge_pts", 0), -kv[1]["composite"]))
    pct = lambda x: f"{x * 100:.1f}%" if isinstance(x, (int, float)) else ""
    for t, s in ranked:
        v = s["verdict"]
        flag = " ⚠" if v.get("disagreement") else ""
        L.append(f"| {t}{' (held)' if s['incumbent'] else ''} | {s['sector']} | {pct(v.get('probability'))}{flag} | "
                 f"{pct(v.get('base_p'))} | {v.get('edge_pts', 0):+.1f} | {v.get('spread', '')} | {v.get('winner', '')} | "
                 f"{v.get('primary_driver', '')} | {v.get('thesis', '')} | {s['research_status']} |")
    for t, s in ranked:
        v = s["verdict"]
        L += ["", f"## {t}: {s['name']} ({pct(v.get('probability'))}, edge {v.get('edge_pts', 0):+.1f})",
              f"**Thesis:** {v.get('thesis', '')}",
              f"**Key risk:** {v.get('key_risk', '')}", f"**Exit if:** {v.get('exit_condition', '')}",
              f"**Evidence:** {', '.join(v.get('evidence', []))}"]
        if v.get("adjustments"):
            L.append("**Adjustments (" + str(v.get("lead_judge")) + "):** " + "; ".join(
                f"{a['points']:+g} {a['reason']} ({', '.join(a['cites'])})" for a in v["adjustments"]))
        if v.get("judges"):
            L.append("**Judges:** " + "; ".join(
                f"{jid}{'' if j.get('live') else ' (shadow)'} {pct(j.get('probability')) or 'n/a'}"
                for jid, j in v["judges"].items()))
        if v.get("invalid_citations"):
            L.append(f"**Discounted (uncited/invalid):** {len(v['invalid_citations'])} claims")
        L += ["", "<details><summary>Dossier</summary>", ""] + [f"- {i['id']} [{i['kind']}] {i['text']}" for i in s["dossier"]]
        L += ["", "</details>"]
    return "\n".join(L)


if __name__ == "__main__":
    run_stage("team", main)
