"""
MACRO EVIDENCE BY DIRECT FETCH

Instead of paying for web searches, code fetches the pages where each fact is published, a free
model (Gemini Flash) extracts findings with short exact quotes, and code checks every quote
against the fetched page. Only verified findings become evidence notes.

If a theme's pages can't be read (site changed, page needs JavaScript, outage), that theme alone
falls back to the paid Claude search with the allowed-domain list. The run report shows which
sources worked, so a broken URL is easy to spot and fix here.

URLs change over time: VERIFY them on the first live run and update SOURCES as needed.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import requests

from . import config
from .audit import in_domains
from .sec import html_to_text, strip_boilerplate
from .util import JSON_RULE

UA = {"User-Agent": "Mozilla/5.0 (personal macro research; contact via GitHub)"}
MIN_TEXT = 400            # a page shorter than this after cleanup is treated as unreadable

# theme -> sources. kind: html | rss. follow: regex for a link on the page to open instead.
SOURCES = {
    "A": [
        {"id": "fed_policy", "url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "kind": "rss",
         "items": 3, "what": "FOMC statements, minutes, and policy releases"},
        {"id": "fed_speeches", "url": "https://www.federalreserve.gov/feeds/speeches.xml", "kind": "rss",
         "items": 2, "what": "recent Fed speeches"},
        {"id": "fomc_calendar", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
         "kind": "html", "what": "FOMC meeting dates"},
        {"id": "beige_book", "url": "https://www.federalreserve.gov/monetarypolicy/beige-book-default.htm",
         "kind": "html", "follow": r"beigebook20\d{4}\.htm", "what": "latest Beige Book summary"},
    ],
    "B": [
        {"id": "truflation", "url": "https://truflation.com/", "kind": "html", "what": "Truflation US inflation"},
        {"id": "cleveland_nowcast", "url": "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting",
         "kind": "html", "what": "Cleveland Fed inflation nowcast"},
        {"id": "eia_steo", "url": "https://www.eia.gov/outlooks/steo/", "kind": "html",
         "what": "EIA Short-Term Energy Outlook"},
        {"id": "eia_weekly", "url": "https://www.eia.gov/petroleum/supply/weekly/", "kind": "html",
         "what": "EIA weekly petroleum inventories"},
        {"id": "ustr", "url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases",
         "kind": "html", "what": "recent trade and tariff actions"},
        {"id": "treasury_refunding",
         "url": "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding",
         "kind": "html", "what": "Treasury quarterly refunding"},
    ],
    "C": [
        {"id": "factset", "url": "https://insight.factset.com/topic/earnings", "kind": "html",
         "follow": r"insight\.factset\.com/[^\"']*earnings[^\"']*", "what": "FactSet Earnings Insight"},
        {"id": "fedwatch", "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
         "kind": "html", "what": "CME FedWatch probabilities"},
        {"id": "nyfed_nowcast", "url": "https://www.newyorkfed.org/research/policy/nowcast", "kind": "html",
         "what": "New York Fed Staff Nowcast (current-quarter GDP)"},
        {"id": "aaii", "url": "https://www.aaii.com/sentimentsurvey", "kind": "html", "what": "AAII sentiment"},
        {"id": "cftc_petroleum", "url": "https://www.cftc.gov/dea/futures/petroleum_sf.htm", "kind": "html",
         "what": "CFTC positioning in energy futures"},
        {"id": "shiller", "url": "https://shillerdata.com/", "kind": "html", "what": "Shiller CAPE"},
    ],
}
# Geopolitics: official pages read directly; war and conflict news always comes from a (restricted) search
SOURCES["E"] = [
    {"id": "eia_twip", "url": "https://www.eia.gov/petroleum/weekly/", "kind": "html",
     "what": "EIA This Week in Petroleum (supply disruptions, prices)"},
    {"id": "ofac_actions", "url": "https://ofac.treasury.gov/recent-actions", "kind": "html",
     "what": "U.S. Treasury OFAC recent sanctions actions"},
    {"id": "iea_omr", "url": "https://www.iea.org/topics/oil-market-report", "kind": "html",
     "what": "IEA Oil Market Report highlights"},
    {"id": "drewry_wci", "url": "https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry",
     "kind": "html", "what": "Drewry World Container Index (freight rates)"},
    {"id": "gpr_index", "url": "https://www.matteoiacoviello.com/gpr.htm", "kind": "html",
     "what": "Geopolitical Risk Index (Caldara & Iacoviello) commentary"},
]
ALWAYS_SEARCH = {"E"}          # themes whose news can't come from fixed official pages

SOURCES["D"] = [
    {"id": "ism_manufacturing", "url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
     "kind": "html", "what": "ISM manufacturing and services PMIs"},
    {"id": "ecb", "url": "https://www.ecb.europa.eu/rss/press.html", "kind": "rss", "items": 3,
     "what": "ECB policy decisions and statements"},
    {"id": "boe", "url": "https://www.bankofengland.co.uk/rss/news", "kind": "rss", "items": 3,
     "what": "Bank of England news and policy decisions"},
    {"id": "boj", "url": "https://www.boj.or.jp/en/rss/whatsnew.xml", "kind": "rss", "items": 3,
     "what": "Bank of Japan announcements"},
    {"id": "imf_weo", "url": "https://www.imf.org/en/Publications/WEO", "kind": "html",
     "what": "IMF World Economic Outlook growth forecasts"},
    {"id": "oecd_outlook", "url": "https://www.oecd.org/en/publications/oecd-economic-outlook_16097408.html", "kind": "html",
     "what": "OECD Economic Outlook"},
]
MAX_CHARS = {"A": 14000, "B": 9000, "C": 9000, "D": 9000}   # per source, per theme


def _get(url, get=None, raw=False):
    r = (get or requests.get)(url, headers=UA, timeout=30)
    if r.status_code != 200:
        return None, getattr(r, "url", url) or url
    body = getattr(r, "content", None) if raw else None
    return (body if isinstance(body, bytes) else r.text), getattr(r, "url", url) or url


def parse_feed(raw):
    """RSS as bytes lets the XML parser read the encoding itself (a feed with a byte-order mark and no
    declared charset otherwise decodes to garbage). Anything that isn't XML (a block page) is reported."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    raw = raw.lstrip(b"\xef\xbb\xbf").lstrip()
    if raw.startswith(b"\xc3\xaf\xc2\xbb\xc2\xbf"):          # a BOM that was already mis-decoded once
        raw = raw[6:].lstrip()
    if not raw.startswith(b"<"):
        raise ValueError("feed is not XML")
    if raw[:200].lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("got a web page instead of the feed (blocked or moved)")
    return ET.fromstring(raw)


def fetch_source(src, get=None, max_chars=10000):
    """Returns {"id", "url", "text"} or {"id", "url", "error"}."""
    try:
        if src["kind"] == "rss":
            raw, _ = _get(src["url"], get, raw=True)
            if not raw:
                return {"id": src["id"], "url": src["url"], "error": "feed unavailable"}
            root = parse_feed(raw)
            parts, first_url = [], None
            for it in root.iter("item"):
                title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
                date, desc = (it.findtext("pubDate") or "").strip(), html_to_text(it.findtext("description") or "")
                parts.append(f"ITEM: {title} ({date}) {link}\n{desc}")
                first_url = first_url or link
                if len(parts) >= src.get("items", 3):
                    break
            text = "\n\n".join(parts)
            if first_url:     # read the newest item in full (e.g. the latest FOMC statement)
                page, final = _get(first_url, get)
                if page:
                    text += "\n\nFULL TEXT OF NEWEST ITEM:\n" + strip_boilerplate(html_to_text(page))
            url = first_url or src["url"]
        else:
            page, url = _get(src["url"], get)
            if page and src.get("follow"):
                m = re.search(src["follow"], page)
                if m:
                    g = m.group(0)
                    link = g if g.startswith("http") else ("https://" + g if re.match(r"[\w.-]+\.\w+/", g)
                                                             else urljoin(src["url"], g))
                    page2, url2 = _get(link, get)
                    if page2:
                        page, url = page2, url2
            if not page:
                return {"id": src["id"], "url": src["url"], "error": "page unavailable"}
            text = strip_boilerplate(html_to_text(page))
        text = text[:max_chars]
        if len(text) < MIN_TEXT:
            return {"id": src["id"], "url": url, "error": "too little readable text (JavaScript page?)"}
        if not in_domains(url, config.MACRO_ALLOWED_DOMAINS):
            return {"id": src["id"], "url": url, "error": "redirected off the allowed sites"}
        return {"id": src["id"], "url": url, "text": text}
    except Exception as e:
        return {"id": src["id"], "url": src.get("url"), "error": str(e)[:120]}


def _norm(s):
    return re.sub(r"[^a-z0-9%$.]+", " ", str(s).lower()).strip()


EXTRACT_SYSTEM = ("You extract facts for a macro investment committee from the source pages provided. Report only "
                  "what a page states. For every finding, copy a SHORT EXACT QUOTE (8-30 words) from that page as "
                  "evidence, name its source id, and give the key number exactly as written. If a page doesn't "
                  "answer an item, skip it; never estimate. " + JSON_RULE)


def extract_theme(session, theme, asks, fetched, today):
    ok = [f for f in fetched if "text" in f]
    if not ok:
        return [], []
    pages = "\n\n".join(f"=== SOURCE {f['id']} ({f['url']}) ===\n{f['text']}" for f in ok)
    prompt = (f"Today is {today}. Find:\n{asks}\n\nJSON: [{{\"topic\": \"...\", \"finding\": \"one sentence\", "
              f"\"value\": \"key number as written, or null\", \"as_of\": \"date or month\", "
              f"\"source\": \"source id\", \"quote\": \"exact words from that page\"}}]")
    r = session.ask("macro_extract", EXTRACT_SYSTEM, prompt, shared=pages, max_tokens=4000, thinking=1024)
    by_id = {f["id"]: f for f in ok}
    notes, dropped = [], []
    for i, n in enumerate(r.data if isinstance(r.data, list) else []):
        if not isinstance(n, dict):
            continue
        src = by_id.get(n.get("source"))
        quote = str(n.get("quote", ""))
        note = {"id": f"{theme}{i + 1}", "topic": n.get("topic"), "finding": n.get("finding"), "value": n.get("value"),
                "as_of": n.get("as_of"), "url": src["url"] if src else None, "source_id": n.get("source"),
                "quote": quote, "source_class": "allowed", "score_eligible": True, "method": "direct fetch"}
        if not src:
            dropped.append(dict(note, reason="named a source that wasn't provided"))
            continue
        page = _norm(src["text"])
        if len(_norm(quote)) < 15 or _norm(quote) not in page:
            dropped.append(dict(note, reason="quote not found on the page"))
            continue
        nums = [x.replace(",", "") for x in re.findall(r"-?\d[\d,]*(?:\.\d+)?", str(n.get("value") or ""))]
        note["verified_number"] = (all(x in page.replace(",", "") for x in nums) if nums else None)
        notes.append(note)
    return notes, dropped


def gather_direct(session, themes, today, get=None, ck=None):
    """Returns (notes, dropped, source_log, themes_needing_search)."""
    notes, dropped, log, need_search = [], [], [], []
    for key, (name, asks) in themes.items():
        if ck and ck.has_item("direct", key):
            saved = ck.item("direct", key)
        else:
            fetched = [fetch_source(s, get, MAX_CHARS.get(key, 10000)) for s in SOURCES.get(key, [])]
            n, d = extract_theme(session, key, asks, fetched, today)
            worked = {x["source_id"] for x in n}
            readable = sum("text" in f for f in fetched)
            saved = {"notes": n, "dropped": d,
                     "log": [{"theme": key, "source": f["id"], "url": f["url"],
                              "status": "used" if f["id"] in worked else ("read, nothing extracted" if "text" in f else f["error"])}
                             for f in fetched],
                     # fall back to paid search only if the pages themselves couldn't be read
                     "needs_search": not n or readable < max(1, len(SOURCES.get(key, [])) // 2)}
            if ck:
                ck.save_item("direct", key, saved)
        notes += saved["notes"]
        dropped += saved["dropped"]
        log += saved["log"]
        if saved["needs_search"] or key in ALWAYS_SEARCH:
            need_search.append(key)
    return notes, dropped, log, need_search
