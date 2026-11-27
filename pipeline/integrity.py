"""
FAIL-CLOSED INTEGRITY GATE for a trade plan, run by code right before anything is emailed.

If any check fails (or the checker itself crashes), the whole plan is BLOCKED: no trades go out,
and the email says why. A wrong trade list is worse than no trade list.

Checks:
  weights     sum to 100%, none negative, positions within limits, sectors within the macro ranges
  trades      valid action/account/amount/price/limit; sells only of shares actually held in
              that account; no buy and sell of the same stock in the same account; no duplicates
  cash        approved buys in each account fit within its cash plus approved sales
  keys        every trade has a unique idempotency key
  numbers     no NaN or infinity anywhere in the plan
"""
import hashlib
import json
import math

from .book import ACCOUNTS
from .pm import PARKING, POS_MAX

TOL = 0.5          # percentage points of slack for rounding


def trade_key(plan_date, t, source="rebuild"):
    """Idempotency key: the same trade from the same plan always gets the same key, so recording it
    twice (e.g. a rerun after a crash) is detected and skipped."""
    raw = f"{source}|{plan_date}|{t.get('id')}|{t['account']}|{t['action']}|{t['ticker']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _finite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def check(plan, book, weights, sector_of, ranges):
    """Returns a list of problems (empty = pass). Never raises: a crash is itself a problem."""
    try:
        return _check(plan, book, weights, sector_of, ranges)
    except Exception as e:  # fail closed
        return [f"integrity check crashed: {type(e).__name__}: {e}"]


def _check(plan, book, weights, sector_of, ranges):
    p = []
    try:
        json.dumps(plan, allow_nan=False, default=str)
    except ValueError:
        p.append("plan contains NaN or infinite numbers")

    # ---- weights
    if not weights:
        p.append("target portfolio is empty")
    total = sum(float(w) for w in weights.values()) if weights else 0
    if weights and abs(total - 100) > TOL:
        p.append(f"target weights sum to {total:.2f}%, not 100%")
    for t, w in (weights or {}).items():
        if not _finite(w) or float(w) < 0:
            p.append(f"{t}: invalid weight {w}")
        elif t != PARKING and float(w) > POS_MAX + TOL:
            p.append(f"{t}: weight {float(w):.2f}% is above the {POS_MAX}% position limit")
    by_sector = {}
    for t, w in (weights or {}).items():
        if t != PARKING:
            s = sector_of.get(t)
            if s is None:
                p.append(f"{t}: unknown sector")
                continue
            by_sector[s] = by_sector.get(s, 0) + float(w)
    for s, w in by_sector.items():
        hi = (ranges or {}).get(s, [0, 15])[1]
        if w > hi + TOL:
            p.append(f"{s}: {w:.1f}% exceeds the macro ceiling of {hi}%")

    # ---- trades
    held = {}
    for pos in book.get("positions", []):
        held[(pos["account"], pos["ticker"])] = held.get((pos["account"], pos["ticker"]), 0) + float(pos["shares"])
    seen, keys, sides = set(), set(), {}
    for t in plan.get("trades", []):
        tid = t.get("id", "?")
        if t.get("action") not in ("BUY", "SELL"):
            p.append(f"{tid}: invalid action {t.get('action')}")
            continue
        if t.get("account") not in ACCOUNTS:
            p.append(f"{tid}: unknown account {t.get('account')}")
            continue
        if t["amount"] != "all" and (not _finite(t["amount"]) or float(t["amount"]) <= 0):
            p.append(f"{tid}: invalid amount {t['amount']}")
        if t["amount"] == "all" and t["action"] == "BUY":
            p.append(f"{tid}: a buy can't be 'all'")
        if not _finite(t.get("ref_price")) or float(t.get("ref_price") or 0) <= 0:
            p.append(f"{tid}: no valid price for {t['ticker']}")
        if not _finite(t.get("limit")) or float(t.get("limit") or 0) <= 0:
            p.append(f"{tid}: invalid limit price")
        k = (t["account"], t["action"], t["ticker"])
        if k in seen and t["ticker"] != PARKING:          # a second SPY parking buy is fine
            p.append(f"{tid}: duplicate {t['action']} {t['ticker']} in {t['account']}")
        seen.add(k)
        sides.setdefault((t["account"], t["ticker"]), set()).add(t["action"])
        if t["action"] == "SELL":
            sh = held.get((t["account"], t["ticker"]), 0)
            if sh <= 0:
                p.append(f"{tid}: sells {t['ticker']} in {t['account']}, which holds none")
            elif t["amount"] != "all" and _finite(t.get("ref_price")) and float(t["ref_price"]) > 0 \
                    and float(t["amount"]) / float(t["ref_price"]) > sh * 1.02:
                p.append(f"{tid}: sells more {t['ticker']} than {t['account']} holds")
        if not t.get("key"):
            p.append(f"{tid}: missing idempotency key")
        elif t["key"] in keys:
            p.append(f"{tid}: duplicate idempotency key")
        keys.add(t.get("key"))
    for (a, tk), s in sides.items():
        if s == {"BUY", "SELL"} and tk != PARKING:
            p.append(f"{tk}: both bought and sold in {a} in the same plan")

    # ---- cash per account (approved trades only: those are what you'll place without asking)
    for a in ACCOUNTS:
        cash = float(book["accounts"][a]["cash"])
        sells = sum(float(t["est_value"] if t["amount"] == "all" else t["amount"]) for t in plan.get("trades", [])
                    if t.get("account") == a and t.get("action") == "SELL" and t.get("status") == "approved"
                    and _finite(t.get("est_value") if t["amount"] == "all" else t["amount"]))
        buys = sum(float(t["amount"]) for t in plan.get("trades", [])
                   if t.get("account") == a and t.get("action") == "BUY" and t.get("status") == "approved"
                   and _finite(t["amount"]))
        if buys > cash + sells + 1:
            p.append(f"{a}: approved buys ${buys:,.0f} exceed cash ${cash:,.0f} + approved sales ${sells:,.0f}")
    return p
