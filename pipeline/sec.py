"""
SEC EDGAR access (free, official, government data).

  sec = SEC()                              # polite client: identifies you, max ~8 requests/sec
  sec.ticker_map()                         # ticker -> CIK
  sec.metrics(cik)                         # trailing-12-month fundamentals from XBRL filings
  sec.daily_index(date)                    # every filing made that day (form, CIK, file)
  sec.form4_purchases(filename)            # open-market insider BUYS in one Form 4

The SEC requires a User-Agent with contact info. It uses GMAIL_ADDRESS (or SEC_CONTACT).
"""
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import numpy as np
import requests

MIN_INTERVAL = 0.125   # SEC allows 10 requests/second; stay under it


class SEC:
    def __init__(self, get=None, contact=None):
        contact = contact or os.environ.get("SEC_CONTACT") or os.environ.get("GMAIL_ADDRESS") or "research@example.com"
        self.headers = {"User-Agent": f"Personal portfolio research {contact}", "Accept-Encoding": "gzip, deflate"}
        self._get = get or requests.get
        self._last = 0.0

    def get(self, url, as_json=True):
        wait = MIN_INTERVAL - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self._last = time.time()
            try:
                r = self._get(url, headers=self.headers, timeout=60)
            except requests.RequestException:   # a timeout or dropped connection: back off and try again
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code == 404:
                return None
            time.sleep(2 * (attempt + 1))   # 429/5xx: back off
        return None

    # ---------------------------------------------------------------- tickers
    def ticker_map(self):
        data = self.get("https://www.sec.gov/files/company_tickers.json") or {}
        return {v["ticker"].upper().replace("-", "."): int(v["cik_str"]) for v in data.values()}

    # ---------------------------------------------------------------- fundamentals
    def companyfacts(self, cik):
        return self.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")

    def metrics(self, cik):
        cf = self.companyfacts(cik)
        return extract_metrics(cf) if cf else None

    # ---------------------------------------------------------------- filings index
    def daily_index(self, d):
        q = (d.month - 1) // 3 + 1
        text = self.get(f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{q}/form.{d:%Y%m%d}.idx",
                        as_json=False)
        return parse_form_index(text) if text else []

    def form4_purchases(self, filename):
        text = self.get(f"https://www.sec.gov/Archives/{filename}", as_json=False)
        return parse_form4(text) if text else []

    # ---------------------------------------------------------------- filing documents
    def recent_filings(self, cik, forms, max_age_days=400):
        """Newest-first list of {form, accession, doc, filed, items} for the given form types."""
        sub = self.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json") or {}
        r = (sub.get("filings") or {}).get("recent") or {}
        n = len(r.get("form", []))
        items = r.get("items") or [""] * n
        cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
        out = [{"form": r["form"][i], "accession": r["accessionNumber"][i], "doc": r["primaryDocument"][i],
                "filed": r["filingDate"][i], "items": items[i] or ""}
               for i in range(n) if r["form"][i] in forms and r["filingDate"][i] >= cutoff]
        return sorted(out, key=lambda x: x["filed"], reverse=True)

    def earnings_dates(self, cik, since="2009-01-01", full=True):
        """Dates of earnings 8-Ks (Item 2.02). full=True also walks the older filing pages, which the
        base-rate history needs once; weekly updates only read the recent page."""
        sub = self.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json") or {}
        pages = [(sub.get("filings") or {}).get("recent") or {}]
        if full:
            for f in (sub.get("filings") or {}).get("files") or []:
                if f.get("filingTo", "9999") >= since:
                    pages.append(self.get(f"https://data.sec.gov/submissions/{f['name']}") or {})
        out = set()
        for r in pages:
            forms, dates, items = r.get("form", []), r.get("filingDate", []), r.get("items") or []
            for i, form in enumerate(forms):
                if form == "8-K" and i < len(items) and "2.02" in (items[i] or "") and dates[i] >= since:
                    out.add(dates[i])
        return sorted(out)

    def material_events(self, cik, days=None):
        """Recent 8-Ks with material items (executive changes, big contracts, impairments, restatements...)."""
        from . import config
        days = days or config.MATERIAL_8K_DAYS
        out = []
        for f in self.recent_filings(cik, {"8-K", "8-K/A"}, days):
            items = [i.strip() for i in (f.get("items") or "").split(",") if i.strip() in config.MATERIAL_8K_ITEMS]
            if items:
                out.append({"filed": f["filed"], "items": items,
                            "what": "; ".join(config.MATERIAL_8K_ITEMS[i] for i in items),
                            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accession'].replace('-', '')}/{f['doc']}"})
        return out

    def document_text(self, cik, accession, doc):
        html = self.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{doc}",
                        as_json=False)
        return html_to_text(html) if html else ""

    def earnings_release_text(self, cik, accession):
        """Exhibit 99.1 (the press release) attached to an earnings 8-K (Item 2.02)."""
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
        idx = self.get(f"{base}/index.json") or {}
        names = [i.get("name", "") for i in (idx.get("directory") or {}).get("item", [])]
        ex = [n for n in names if re.search(r"ex-?99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
        if not ex:
            return ""
        html = self.get(f"{base}/{sorted(ex)[0]}", as_json=False)
        return strip_boilerplate(html_to_text(html)) if html else ""


# ==================================================================== XBRL -> metrics
DURATION = {  # metric: concept candidates (first with the freshest data wins)
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation",
            "DepreciationAmortizationAndAccretionNet"],
}
INSTANT = {
    "assets": ["Assets"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "lt_debt": ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "st_debt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
}


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _rows(cf, concept, unit="USD", taxonomy="us-gaap"):
    node = (cf.get("facts", {}).get(taxonomy, {}) or {}).get(concept)
    if not node or unit not in node.get("units", {}):
        return []
    dedup = {}
    for r in node["units"][unit]:
        key = (r.get("start"), r["end"])
        if key not in dedup or r.get("filed", "") > dedup[key].get("filed", ""):
            dedup[key] = r
    return list(dedup.values())


def ttm(rows):
    """Trailing 12 months = last fiscal year + current year-to-date - prior year-to-date.
    Works for income AND cash-flow items (10-Q cash flows are reported year-to-date)."""
    dur = [r for r in rows if r.get("start")]
    annual = [r for r in dur if 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380]
    if not annual:
        return None, None
    a = max(annual, key=lambda r: r["end"])
    fy_start = _d(a["end"]) + timedelta(days=1)
    ytd = [r for r in dur if abs((_d(r["start"]) - fy_start).days) <= 5 and _d(r["end"]) > fy_start]
    if not ytd:
        return a["val"], a["end"]
    y = max(ytd, key=lambda r: r["end"])
    days = (_d(y["end"]) - _d(y["start"])).days
    target_end = _d(y["end"]) - timedelta(days=365)
    prior = [r for r in dur if abs((_d(r["end"]) - _d(r["start"])).days - days) <= 10
             and abs((_d(r["end"]) - target_end).days) <= 10]
    if not prior:
        return a["val"], a["end"]
    return a["val"] + y["val"] - prior[0]["val"], y["end"]


def latest_instant(rows):
    inst = [r for r in rows if not r.get("start")]
    if not inst:
        return None, None
    r = max(inst, key=lambda r: r["end"])
    return r["val"], r["end"]


def _best(cf, concepts, fn, unit="USD", taxonomy="us-gaap"):
    best = (None, None)
    for c in concepts:
        v, end = fn(_rows(cf, c, unit, taxonomy))
        if v is not None and (best[1] is None or end > best[1]):
            best = (v, end)
    return best


def extract_metrics(cf):
    m, as_of = {}, []
    for k, cs in DURATION.items():
        v, end = _best(cf, cs, ttm)
        m[k] = v
        if end and k in ("revenue", "net_income"):
            as_of.append(end)
    for k, cs in INSTANT.items():
        m[k], _ = _best(cf, cs, latest_instant)
    m["shares"], _ = _best(cf, ["EntityCommonStockSharesOutstanding"], latest_instant, "shares", "dei")
    if m["gross_profit"] is None and m["revenue"] is not None and m["cost_of_revenue"] is not None:
        m["gross_profit"] = m["revenue"] - m["cost_of_revenue"]
    m["debt"] = (m["lt_debt"] or 0) + (m["st_debt"] or 0)
    # return on invested capital: after-tax operating income / (debt + equity - cash)
    invested = (m["debt"] or 0) + (m["equity"] or 0) - (m["cash"] or 0)
    m["roic"] = (m["operating_income"] * (1 - 0.21) / invested
                 if m["operating_income"] is not None and m["equity"] is not None and invested > 0 else None)
    # margin stability: minus the spread of annual operating margins over the last 5 fiscal years
    om = [om for _, om in annual_margins(cf)[-5:]]
    m["margin_stability"] = -float(np.std(om)) if len(om) >= 3 else None
    # candidate signals: share issuance, asset growth (both over ~1 year) and the Piotroski F-score
    m["share_growth"] = yoy_change(_instant_map(cf, SHARE_CONCEPTS))
    m["asset_growth"] = yoy_change(_instant_map(cf, INSTANT["assets"]))
    fs = fscores(cf)
    m["fscore"] = fs[max(fs)][0] if fs else None
    m["v"] = METRICS_VERSION
    m["as_of"] = max(as_of) if as_of else None
    m["stale"] = not m["as_of"] or (date.today() - _d(m["as_of"])).days > 550
    return m


METRICS_VERSION = 3            # bump when extract_metrics gains fields, so cached companies are re-read


def _annual(cf, concepts):
    """{fiscal year end: (value, filed)} from 12-month facts, first concept with data wins per year."""
    out = {}
    for c in concepts:
        for r in _rows(cf, c):
            if r.get("start") and 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380 and r.get("filed"):
                out.setdefault(r["end"], (r["val"], r["filed"]))
    return out


def annual_margins(cf):
    """[(fiscal year end, operating margin)] oldest first."""
    if not cf:
        return []
    rev, op = _annual(cf, DURATION["revenue"]), _annual(cf, DURATION["operating_income"])
    return sorted((e, op[e][0] / rev[e][0]) for e in rev if e in op and rev[e][0])


SHARE_CONCEPTS = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]


def _instant_map(cf, concepts):
    """{date: value} for point-in-time facts; concepts are names (us-gaap, USD) or (taxonomy, name) share counts."""
    out = {}
    for c in concepts:
        tax, name, unit = (c[0], c[1], "shares") if isinstance(c, tuple) else ("us-gaap", c, "USD")
        for r in _rows(cf, name, unit, tax):
            if not r.get("start"):
                out.setdefault(r["end"], r["val"])
    return out


def _near(m, when, tol=45):
    """Value in {date: value} closest to `when` (a date string), within tol days."""
    best = None
    for e, v in m.items():
        gap = abs((_d(e) - _d(when)).days)
        if gap <= tol and v is not None and (best is None or gap < best[0]):
            best = (gap, v)
    return best[1] if best else None


def yoy_change(m, as_of=None):
    """Change over ~1 year in a {date: value} series, measured at its latest date on or before as_of."""
    ds = sorted(e for e in m if as_of is None or e <= as_of)
    if not ds:
        return None
    now = m[ds[-1]]
    prev = _near(m, (_d(ds[-1]) - timedelta(days=365)).isoformat())
    return round(now / prev - 1, 4) if now and prev and prev > 0 else None


def fscores(cf):
    """Piotroski F-score per fiscal year end: {end: (score 0-9, filed)}. Nine pass/fail tests of this year vs
    last: profitable, cash-generative, improving ROA, cash > earnings, less leverage, better liquidity, no new
    shares, better gross margin, better asset turnover. Missing tests are scaled out (needs 6 of 9)."""
    if not cf:
        return {}
    ni, cfo = _annual(cf, DURATION["net_income"]), _annual(cf, DURATION["cfo"])
    rev, gp = _annual(cf, DURATION["revenue"]), _annual(cf, DURATION["gross_profit"])
    cost = _annual(cf, DURATION["cost_of_revenue"])
    assets, ca, cl = _instant_map(cf, INSTANT["assets"]), _instant_map(cf, ["AssetsCurrent"]), _instant_map(cf, ["LiabilitiesCurrent"])
    ltd = _instant_map(cf, INSTANT["lt_debt"])
    shares = _instant_map(cf, SHARE_CONCEPTS)
    gross = lambda e: gp[e][0] if e in gp else (rev[e][0] - cost[e][0] if e in rev and e in cost else None)
    ratio = lambda a, b: a / b if a is not None and b else None
    out = {}
    for e, (n, filed) in ni.items():
        p = next((x for x in ni if 330 <= (_d(e) - _d(x)).days <= 400), None)
        a_e, a_p = assets.get(e), assets.get(p) if p else None
        tests = []
        tests.append(n > 0)
        tests.append(cfo[e][0] > 0 if e in cfo else None)
        tests.append(ratio(n, a_e) > ratio(ni[p][0], a_p) if p and a_e and a_p else None)
        tests.append(cfo[e][0] > n if e in cfo else None)
        if p and a_e and a_p and ltd:
            tests.append((ltd.get(e) or 0) / a_e <= (ltd.get(p) or 0) / a_p)
        else:
            tests.append(None)
        cr_e, cr_p = ratio(ca.get(e), cl.get(e)), ratio(ca.get(p), cl.get(p)) if p else None
        tests.append(cr_e > cr_p if cr_e is not None and cr_p is not None else None)
        s_e, s_p = _near(shares, e, 60), _near(shares, p, 60) if p else None
        tests.append(s_e <= s_p * 1.005 if s_e and s_p else None)
        gm_e = ratio(gross(e), rev[e][0]) if e in rev else None
        gm_p = ratio(gross(p), rev[p][0]) if p and p in rev else None
        tests.append(gm_e > gm_p if gm_e is not None and gm_p is not None else None)
        to_e = ratio(rev[e][0], a_e) if e in rev else None
        to_p = ratio(rev[p][0], a_p) if p and p in rev else None
        tests.append(to_e > to_p if to_e is not None and to_p is not None else None)
        known = [t for t in tests if t is not None]
        if len(known) >= 6:
            out[e] = (round(9 * sum(known) / len(known), 2), filed)
    return out


def fundamental_history(cf):
    """Point-in-time value and quality inputs from each annual report, keyed by the date it was FILED:
    [(filed, {"op_income", "fcf", "shares", "roic", "margin_stability", "share_growth", "asset_growth",
    "fscore"})]. Lets 15 years of history test
    value, ROIC and margin stability the same way momentum and gross profitability are tested."""
    if not cf:
        return []
    op, cfo = _annual(cf, DURATION["operating_income"]), _annual(cf, DURATION["cfo"])
    capex = _annual(cf, DURATION["capex"])
    inst = lambda cs, unit="USD", tax="us-gaap": {r["end"]: r["val"] for c in cs for r in _rows(cf, c, unit, tax)
                                                  if not r.get("start")}
    equity, cash = inst(INSTANT["equity"]), inst(INSTANT["cash"])
    debt = {}
    for cs in (INSTANT["lt_debt"], INSTANT["st_debt"]):
        for e, v in inst(cs).items():
            debt[e] = debt.get(e, 0) + v
    shares = sorted(inst(["EntityCommonStockSharesOutstanding"], "shares", "dei").items())
    all_shares, assets = _instant_map(cf, SHARE_CONCEPTS), _instant_map(cf, INSTANT["assets"])
    fs = fscores(cf)
    margins = annual_margins(cf)
    out = []
    for end, (oi, filed) in sorted(op.items()):
        sh = [v for e, v in shares if e <= filed]
        inv = debt.get(end, 0) + (equity.get(end) or 0) - (cash.get(end) or 0)
        past = [m for e, m in margins if e <= end][-5:]
        out.append((filed, {"op_income": oi,
                            "fcf": cfo[end][0] - (capex.get(end, (0, None))[0] or 0) if end in cfo else None,
                            "shares": sh[-1] if sh else None,
                            "roic": oi * 0.79 / inv if equity.get(end) is not None and inv > 0 else None,
                            "margin_stability": -float(np.std(past)) if len(past) >= 3 else None,
                            # as known on the filing date: shares on the latest cover page vs a year earlier
                            "share_growth": yoy_change(all_shares, as_of=filed),
                            "asset_growth": yoy_change({k: v for k, v in assets.items() if k <= end}),
                            "fscore": fs[end][0] if end in fs else None}))
    return sorted(out, key=lambda x: x[0])


def quality_history(cf):
    """Point-in-time gross profitability (gross profit / assets) from each annual report, keyed by the
    date it was FILED, so history never uses a number before the public could see it."""
    if not cf:
        return []
    gp = {}
    for c in DURATION["gross_profit"]:
        for r in _rows(cf, c):
            if r.get("start") and 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380 and r.get("filed"):
                gp.setdefault(r["end"], (r["val"], r["filed"]))
    if not gp:   # revenue - cost of revenue
        rev, cost = {}, {}
        for c in DURATION["revenue"]:
            for r in _rows(cf, c):
                if r.get("start") and 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380 and r.get("filed"):
                    rev.setdefault(r["end"], (r["val"], r["filed"]))
        for c in DURATION["cost_of_revenue"]:
            for r in _rows(cf, c):
                if r.get("start") and 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380:
                    cost.setdefault(r["end"], r["val"])
        gp = {e: (v - cost[e], f) for e, (v, f) in rev.items() if e in cost}
    assets = {r["end"]: r["val"] for r in _rows(cf, "Assets") if not r.get("start")}
    out = [(filed, round(v / assets[end], 4)) for end, (v, filed) in gp.items() if assets.get(end)]
    return sorted(out)


def revenue_history(cf):
    """Annual revenue by the date it was filed (point-in-time), for valuation-vs-history and growth."""
    if not cf:
        return []
    rev = {}
    for c in DURATION["revenue"]:
        for r in _rows(cf, c):
            if r.get("start") and 350 <= (_d(r["end"]) - _d(r["start"])).days <= 380 and r.get("filed"):
                rev.setdefault(r["end"], (r["val"], r["filed"]))
    return sorted((f, v, end) for end, (v, f) in rev.items())


# ==================================================================== extra detail for the dossier
def _dur_days(r):
    return (_d(r["end"]) - _d(r["start"])).days if r.get("start") else None


def _first_rows(cf, concepts, unit="USD", taxonomy="us-gaap"):
    for c in concepts:
        rows = _rows(cf, c, unit, taxonomy)
        if rows:
            return rows
    return []


def quarterly(cf, concepts, n=8):
    """Last n quarterly values {end: value}. Uses 3-month facts; a fiscal Q4 missing from the filings is
    derived as the annual figure minus the first three quarters."""
    rows = _first_rows(cf, concepts)
    q = {r["end"]: r["val"] for r in rows if r.get("start") and 80 <= _dur_days(r) <= 100}
    for a in (r for r in rows if r.get("start") and 350 <= _dur_days(r) <= 380):
        if a["end"] in q:
            continue
        start, end = _d(a["start"]), _d(a["end"])
        inside = [v for e, v in q.items() if start < _d(e) < end]
        if len(inside) == 3:
            q[a["end"]] = a["val"] - sum(inside)
    return dict(sorted(q.items())[-n:])


def _yoy(series):
    """Latest value vs the value closest to one year earlier (percent change)."""
    if len(series) < 2:
        return None
    ends = sorted(series)
    last = _d(ends[-1])
    prior = min(ends[:-1], key=lambda e: abs((last - _d(e)).days - 365))
    if abs((last - _d(prior)).days - 365) > 45 or not series[prior]:
        return None
    return round((series[ends[-1]] / series[prior] - 1) * 100, 1)


def _instants(cf, concepts, unit="USD", taxonomy="us-gaap"):
    rows = _first_rows(cf, concepts, unit, taxonomy)
    return dict(sorted({r["end"]: r["val"] for r in rows if not r.get("start")}.items()))


def extra_metrics(cf):
    """Quarterly trends, working capital vs sales, share count change, backlog, stock pay and near-term
    debt: compact numbers for the dossier, all from SEC's structured data (no reading needed)."""
    if not cf:
        return {}
    out = {}
    rev = quarterly(cf, DURATION["revenue"])
    gp = quarterly(cf, DURATION["gross_profit"])
    op = quarterly(cf, DURATION["operating_income"])
    if rev:
        out["quarters"] = [{"end": e, "revenue_$M": round(v / 1e6, 1),
                            "gross_margin_%": round(gp[e] / v * 100, 1) if e in gp and v else None,
                            "operating_margin_%": round(op[e] / v * 100, 1) if e in op and v else None}
                           for e, v in rev.items()]
        out["revenue_growth_yoy_%"] = _yoy(rev)
    for name, concepts in (("inventory", ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"]),
                           ("receivables", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]),
                           ("deferred_revenue", ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"]),
                           ("backlog", ["RevenueRemainingPerformanceObligation"])):
        g = _yoy(_instants(cf, concepts))
        if g is not None:
            out[f"{name}_growth_yoy_%"] = g
    sh = _instants(cf, ["EntityCommonStockSharesOutstanding"], "shares", "dei") or \
        _instants(cf, ["CommonStockSharesOutstanding"], "shares")
    g = _yoy(sh)
    if g is not None:
        out["share_count_change_yoy_%"] = g
    sbc, _ = _best(cf, ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"], ttm)
    rttm, _ = _best(cf, DURATION["revenue"], ttm)
    if sbc and rttm:
        out["stock_comp_%_of_revenue"] = round(sbc / rttm * 100, 1)
    due, _ = _best(cf, ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", "LongTermDebtCurrent",
                        "DebtCurrent"], latest_instant)
    cash, _ = _best(cf, INSTANT["cash"], latest_instant)
    assets, _ = _best(cf, INSTANT["assets"], latest_instant)
    if due and cash is not None and assets and due > max(cash, 0) and due > 0.1 * assets:
        out["debt_due_12m_flag"] = f"${due / 1e6:,.0f}M due within 12 months vs ${cash / 1e6:,.0f}M cash"
    return out


# ==================================================================== text scans and filing comparison
WEAKNESS = re.compile(r"[^.]{0,200}material weakness(es)?[^.]{0,200}\.", re.I)
GOING_CONCERN = re.compile(r"[^.]{0,200}substantial doubt[^.]{0,120}going concern[^.]{0,120}\.", re.I)
CONCENTRATION = re.compile(r"[^.]{0,160}\b(customer|customers|distributor|client)s?\b[^.]{0,120}?\b\d{1,2}(\.\d)?\s?%"
                           r"[^.]{0,40}\b(revenue|revenues|net sales|sales)\b[^.]{0,120}\.", re.I)


GEO_PLACES = (r"China|Chinese|Hong Kong|Taiwan|Russia|Ukraine|Israel|Iran|Middle East|Saudi|Persian Gulf|"
              r"Vietnam|Mexico|Asia[- ]Pacific|Asia|Europe|EMEA|Latin America|international|foreign|"
              r"outside (?:of )?the United States|outside the U\.S\.")
# revenue share by region: "sales to customers in China were 23% of net revenue"
GEO_REVENUE = re.compile(r"[^.]{0,200}\b(?:" + GEO_PLACES + r")\b[^.]{0,160}?\b\d{1,3}(?:\.\d)?\s?%[^.]{0,120}\.", re.I)
GEO_REVENUE_WORDS = ("revenue", "net sales", "sales", "net revenue")
# where things are made or sourced: "substantially all of our products are manufactured in Taiwan"
GEO_SUPPLY = re.compile(r"[^.]{0,200}\b(?:manufactur\w*|produced|sourced|suppliers?|foundr\w*|assembl\w*|contract manufacturers?)"
                        r"\b[^.]{0,120}\b(?:China|Taiwan|Vietnam|Mexico|Israel|Malaysia|India|Korea|Russia|Ukraine)\b[^.]{0,160}\.", re.I)


def geo_scan(text, limit=3):
    """Sentences stating where a company sells (with a %) and where it makes or sources things, so the
    team can weigh geopolitical exposure (tariffs, export controls, conflicts). Hypothetical risk-factor
    language ("could", "may") is skipped."""
    hypothetical = (" could ", " may ", " might ", " if ", " would ")
    out = {"geo_revenue": [], "geo_supply": []}
    for key, rx, need in (("geo_revenue", GEO_REVENUE, GEO_REVENUE_WORDS), ("geo_supply", GEO_SUPPLY, ())):
        for m in rx.finditer(text or ""):
            sent = " ".join(m.group(0).split())
            low = f" {sent.lower()} "
            if any(h in low for h in hypothetical) or (need and not any(w in low for w in need)) or sent in out[key]:
                continue
            out[key].append(sent[:400])
            if len(out[key]) >= limit:
                break
    return out


def red_flag_scan(text, limit=3):
    """Sentences from the FULL filing (not just MD&A) about material weaknesses in accounting controls,
    going-concern doubt, and customer concentration. Boilerplate 'we may have a material weakness in the
    future' risk language is dropped."""
    def grab(rx, skip=()):
        out = []
        for m in rx.finditer(text or ""):
            s = " ".join(m.group(0).split())
            if any(k in s.lower() for k in skip) or s in out:
                continue
            out.append(s[:400])
            if len(out) >= limit:
                break
        return out
    hypothetical = ("could ", "may ", "might ", "if we ", "in the future", "no material weakness", "not identified")
    return {"material_weakness": grab(WEAKNESS, hypothetical),
            "going_concern": grab(GOING_CONCERN, ("could ", "may ", "might ", "no substantial doubt")),
            "customer_concentration": grab(CONCENTRATION), **geo_scan(text, limit)}


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
    return [p for p in parts if len(p) > 40]


def _key(s):
    return re.sub(r"[^a-z ]", "", s.lower())[:160]


def filing_diff(current, prior, max_chars=6000):
    """Sentences added to and removed from a filing vs the prior one of the same type. Returns the share
    of sentences unchanged (low = heavy rewriting, which research links to weaker returns) and the text
    of the changes, capped, so a model reads only what changed."""
    cur, pri = _sentences(current), _sentences(prior)
    if not cur or not pri:
        return None
    ck, pk = {_key(x) for x in cur}, {_key(x) for x in pri}
    added = [x for x in cur if _key(x) not in pk]
    removed = [x for x in pri if _key(x) not in ck]
    same = 1 - len(added) / max(1, len(cur))
    take = lambda xs, n: "\n".join(f"- {x[:350]}" for x in xs)[:n]
    return {"unchanged_share": round(same, 3), "added_count": len(added), "removed_count": len(removed),
            "added_text": take(added, int(max_chars * 0.65)), "removed_text": take(removed, int(max_chars * 0.35))}


# ==================================================================== filings index
def parse_form_index(text):
    out, started = [], False
    for line in text.splitlines():
        if line.startswith("----"):
            started = True
            continue
        if not started or not line.strip():
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue
        form, cik, filed, fname = parts[0], parts[-3], parts[-2], parts[-1]
        if cik.isdigit():
            out.append({"form": form, "company": " ".join(parts[1:-3]), "cik": int(cik), "filed": filed, "file": fname})
    return out


# ==================================================================== Form 4
def _txt(node, path):
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else ""


def parse_form4(text):
    """Open-market purchases (transaction code P) by officers/directors/10% owners."""
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", text or "", re.S)
    if not m:
        return []
    try:
        doc = ET.fromstring(m.group(0))
    except ET.ParseError:
        return []
    issuer = _txt(doc, "issuer/issuerCik")
    owner = _txt(doc, "reportingOwner/reportingOwnerId/rptOwnerName")
    rel = doc.find("reportingOwner/reportingOwnerRelationship")
    role = []
    if rel is not None:
        for tag, lab in (("isDirector", "director"), ("isOfficer", "officer"), ("isTenPercentOwner", "10% owner")):
            if _txt(rel, tag) in ("1", "true"):
                role.append(lab)
    out = []
    for t in doc.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if _txt(t, "transactionCoding/transactionCode") != "P":
            continue
        if _txt(t, "transactionAmounts/transactionAcquiredDisposedCode/value") not in ("A", ""):
            continue
        try:
            shares = float(_txt(t, "transactionAmounts/transactionShares/value") or 0)
            price = float(_txt(t, "transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        out.append({"issuer_cik": int(issuer) if issuer.isdigit() else None, "owner": owner,
                    "role": ",".join(role), "date": _txt(t, "transactionDate/value"),
                    "shares": shares, "price": price, "value": round(shares * price, 2)})
    return out


# ==================================================================== filing text
def html_to_text(html):
    from html import unescape
    t = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def extract_section(text, start_pat, end_pat, max_chars):
    """Pull a section like MD&A. Tables of contents also contain the heading, so take the
    first occurrence that is followed by substantial text before the end heading."""
    for m in re.finditer(start_pat, text, re.I):
        end = re.compile(end_pat, re.I).search(text, m.end())
        stop = end.start() if end else min(len(text), m.end() + max_chars)
        if stop - m.start() > 2000:
            return text[m.start():stop][:max_chars]
    return ""


APOS = "['\u2019]?"
MDA_START = rf"item\s*[27]\.?\s*[-\u2013\u2014:]?\s*management{APOS}s?\s+discussion\s+and\s+analysis"
MDA_END = r"item\s*(3|7a)\.?\s*[-\u2013\u2014:]?\s*quantitative\s+and\s+qualitative"
RISK_START = r"item\s*1a\.?\s*[-\u2013\u2014:]?\s*risk\s+factors"
RISK_END = r"item\s*(1b|1c|2)\.?\s*[-\u2013\u2014:]?\s*\w"


BOILERPLATE = re.compile("|".join([
    r"forward[- ]looking statements?", r"private securities litigation reform act", r"safe harbor",
    r"undertakes? no (obligation|duty)", r"assumes? no (obligation|duty) to update",
    r"pursuant to the requirements of the securities exchange act", r"^\s*signatures?\s*$",
    r"incorporated (herein )?by reference", r"^\s*exhibit index\s*$",
    r"this (press release|report) (contains|includes|may contain) (certain )?statements",
]), re.I | re.M)


def strip_boilerplate(text):
    """Drop legal disclaimer paragraphs (forward-looking-statement legends, safe-harbor language,
    signature blocks, exhibit indexes). Numbers, tables and business discussion are kept: a
    paragraph is only dropped if it matches a legal pattern AND carries no financial figures."""
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        if BOILERPLATE.search(para) and len(re.findall(r"\$\s?\d|\d+(\.\d+)?\s?%", para)) < 2:
            continue
        out.append(para)
    return "\n\n".join(out)


def filing_sections(text, max_chars=40000):
    """MD&A plus risk factors (legal boilerplate removed), capped. Falls back to the document start."""
    text = strip_boilerplate(text)
    mda = extract_section(text, MDA_START, MDA_END, int(max_chars * 0.75))
    risk = extract_section(text, RISK_START, RISK_END, int(max_chars * 0.25))
    body = "\n\n".join(x for x in (mda, risk) if x)
    return body or text[:max_chars]
