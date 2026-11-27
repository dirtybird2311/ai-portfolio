"""
The data auditor. Plain code, no AI. Every agent's output passes through here before
anything downstream may use it.

Two jobs:
  1. validate_notes()  - facts an agent found on the web. Checks the page really came back
                         from its search, the site obeys the source rules, and (where the
                         source's own words are available) that quoted numbers appear there.
  2. Auditor.check()   - evidence references inside an agent's reasoning ("FRED:UNRATE = 4.3",
                         "NOTE:A2", "SEC:AAPL:gross_margin"). Each must point at something that
                         exists, and any number quoted must match the data.
"""
import re

from . import config


# ------------------------------------------------------------------ domains
def domain(url):
    host = re.sub(r"^https?://", "", str(url or "")).split("/")[0].split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


def in_domains(url, domains):
    h = domain(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def is_rumor(text):
    t = str(text or "").lower()
    return any(p in t for p in config.RUMOR_PHRASES)


def source_class(url, company_domains=()):
    """'primary' | 'reputable' | 'blocked' | 'open' for company research."""
    if in_domains(url, config.COMPANY_BLOCKED_DOMAINS):
        return "blocked"
    if in_domains(url, config.PRIMARY_SOURCE_DOMAINS) or in_domains(url, company_domains):
        return "primary"
    if in_domains(url, config.REPUTABLE_NEWS_DOMAINS):
        return "reputable"
    h = domain(url)
    if h.startswith(("investor.", "investors.", "ir.")):   # company investor-relations sites
        return "primary"
    return "open"


# ------------------------------------------------------------------ numbers
def _numbers(text):
    return re.findall(r"-?\d[\d,]*(?:\.\d+)?", str(text or ""))


def number_in_text(value, text):
    """True if every number in `value` appears in `text` (commas ignored). None if nothing to check."""
    nums = [n.replace(",", "") for n in _numbers(value)]
    if not nums:
        return None
    hay = str(text or "").replace(",", "")
    return all(n in hay for n in nums)


# ------------------------------------------------------------------ web notes
def validate_notes(notes, receipts, mode, company_domains=()):
    """notes: [{"id","finding","value","url","as_of","affects_score"?}]
    mode: "allow" (macro: only config.MACRO_ALLOWED_DOMAINS) or "company" (block-list +
    primary-source rule for anything that affects a score).
    Returns (kept, dropped). Kept notes gain: verified_number, source_class, score_eligible."""
    by_url = {}
    for r in receipts:
        by_url.setdefault(r["url"], []).append(r)
    kept, dropped = [], []
    for n in notes if isinstance(notes, list) else []:
        if not isinstance(n, dict):
            continue
        n = dict(n)
        url = n.get("url", "")
        if "NOT FOUND" in str(n.get("finding", "")).upper():
            continue
        recs = by_url.get(url)
        if not recs:
            dropped.append(dict(n, reason="URL was not in the agent's search results"))
            continue
        if mode == "allow":
            if not in_domains(url, config.MACRO_ALLOWED_DOMAINS):
                dropped.append(dict(n, reason="site not on the allowed list"))
                continue
            n["source_class"] = "allowed"
            n["score_eligible"] = True
        else:
            cls = source_class(url, company_domains)
            if cls == "blocked":
                dropped.append(dict(n, reason="site is on the block list"))
                continue
            n["source_class"] = cls
            n["rumor"] = is_rumor(f"{n.get('finding', '')} {n.get('value', '')}")
            n["score_eligible"] = (cls == "primary" or (cls == "reputable" and not n["rumor"])
                                   or not n.get("affects_score", True))
        src_text = " ".join(s for r in recs if r.get("snippet_kind") == "source_text"
                            for s in r.get("snippets", []))
        n["verified_number"] = number_in_text(n.get("value"), src_text) if src_text else None
        kept.append(n)
    return kept, dropped


# ------------------------------------------------------------------ evidence references
class Auditor:
    """Checks evidence refs of the form KIND:key (value optional).

    Context tables (all optional):
      fred    {series_id: {"latest","3m_ago","12m_ago","z_5yr","percentile_5yr",...}}
      notes   [validated notes]
      calcs   set of calculation names
      sectors set of sector names          (HIST:<sector>, MOM:<sector>)
      metrics {ticker: {metric: value}}    (SEC:<ticker>:<metric>)
      facts   {fact_id: value}             (FACT:<id>, any other code-computed number)
    """

    NUMERIC_FIELDS = ("latest", "3m_ago", "12m_ago", "z_5yr", "percentile_5yr")

    def __init__(self, fred=None, notes=None, calcs=None, sectors=None, metrics=None, facts=None):
        self.fred = fred or {}
        self.notes = {n["id"]: n for n in (notes or [])}
        self.calcs = set(calcs or [])
        self.sectors = set(sectors or [])
        self.metrics = metrics or {}
        self.facts = facts or {}

    @staticmethod
    def _close(v, targets):
        return any(t is not None and abs(v - float(t)) <= max(0.051, abs(float(t)) * 0.01) for t in targets)

    def check(self, ev, for_score=True):
        """Returns (ok, problem)."""
        if not isinstance(ev, dict):
            ev = {"ref": str(ev)}
        ref, val = str(ev.get("ref", "")), ev.get("value")
        kind, _, key = ref.partition(":")
        num = None
        if val not in (None, ""):
            try:
                num = float(str(val).replace(",", "").rstrip("%"))
            except Exception:
                # a number with units or words ("10+ mb/d shut in", "507 mb"): check its first number
                m = re.search(r"-?\d+(?:\.\d+)?", str(val).replace(",", ""))
                num = float(m.group(0)) if m else None

        if kind == "FRED":
            row = self.fred.get(key)
            if not row:
                return False, f"{ref} is not in the data"
            if num is not None and not self._close(num, [row.get(f) for f in self.NUMERIC_FIELDS]):
                return False, f"{ref}: quoted {num} doesn't match the data (latest {row.get('latest')})"
            return True, ""
        if kind == "NOTE":
            n = self.notes.get(key)
            if not n:
                return False, f"{ref} is not a verified note"
            if for_score and not n.get("score_eligible", True):
                return False, f"{ref} isn't from a primary source, so it can't support a score"
            if n.get("verified_number") is False:
                return False, f"{ref}: its number wasn't found in the cited source text"
            return True, ""
        if kind == "SEC":
            ticker, _, metric = key.partition(":")
            m = self.metrics.get(ticker, {})
            if metric not in m:
                return False, f"{ref} is not in the SEC metrics table"
            if num is not None and m[metric] is not None and not self._close(num, [m[metric]]):
                return False, f"{ref}: quoted {num} doesn't match {m[metric]}"
            return True, ""
        if kind == "FACT":
            if key not in self.facts:
                return False, f"{ref} is not a known fact"
            if num is not None and self.facts[key] is not None and not self._close(num, [self.facts[key]]):
                return False, f"{ref}: quoted {num} doesn't match {self.facts[key]}"
            return True, ""
        if kind == "CALC":
            return (key in self.calcs), f"{ref} is not a known calculation"
        if kind in ("HIST", "MOM"):
            return (key in self.sectors), f"{ref}: unknown sector"
        return False, f"unrecognized reference '{ref}'"

    def filter(self, evidence, for_score=True):
        """Returns (valid_evidence, problems)."""
        good, problems = [], []
        for ev in evidence if isinstance(evidence, list) else []:
            ok, why = self.check(ev, for_score)
            (good if ok else problems).append(ev if ok else why)
        return good, problems
