"""
Central settings for the whole pipeline. Every other module reads from here,
so changing a model, a price, a budget, or a source rule is a one-line edit.
"""
import os
from pathlib import Path

# ------------------------------------------------------------------ paths
ROOT = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).resolve().parent.parent))
STATE_DIR = ROOT / "state"      # durable memory: holdings, last views, logs (committed by GitHub Actions)
RUNS_DIR = ROOT / "runs"
# Real-money accounts (broker holdings, their daily values, order sheets, the performance sheet) live in a separate
# private repo checked out here, so this repo can be public. Missing folder = those features skip quietly.
PRIVATE_DIR = Path(os.environ.get("PRIVATE_DIR", ROOT / "private"))        # one folder per run: reports, receipts, full outputs

# ------------------------------------------------------------------ models by role
# Claude where judgment matters; free models (Gemini, Gemma, Groq, Mistral) for high-volume work.
# Model IDs for free providers change often: VERIFY these on the first run (the run report lists
# any fallbacks, which is how a retired model shows up).
GEMMA = "gemma-4-31b-it"                        # Google's open model, free on the Gemini API
FLASH = "gemini-3.8-flash"                      # free tier; replaces Gemini 2.5 Flash (retires Oct 16, 2026)
PAID_SUFFIX = "@paid"                            # "<gemini model>@paid" = that model called with the billed key
GEMINI_PRO = "gemini-3.1-pro-preview"           # paid only: needs GEMINI_PAID_API_KEY (billing-enabled project)
GROQ_DEBATE = "groq:openai/gpt-oss-120b"        # no longer used (replaced by Grok); kept for old cost logs
GROK = "xai:grok-4.3"                           # xAI (paid, ~$0.25 per rebuild for its share of the debates)
MISTRAL_LARGE = "mistral:mistral-large-2512"      # NOT on the free plan (403 tier_not_allowed); not used
SONNET = "claude-sonnet-5"
SONNET_55 = "claude-sonnet-5-5"                 # Sonnet 5.5: shadow judge and non-decision roles from Oct 23, 2026
OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-4-5-20251001"
GPT_SOL = "openai:gpt-6-sol"                    # OpenAI mid tier ($2/$10)
GPT_ASTRA = "openai:gpt-6-astra"                # OpenAI top tier ($10/$50) - not used for now
# NVIDIA retired DeepSeek V4 Pro/Flash (HTTP 410, Aug-Sept 2026) and now serves V4.1 Flash. It retires models
# without notice: the monthly connection test lists what it still serves.
NV_DEEPSEEK = "nvidia:deepseek-ai/deepseek-v4.1-flash"
NV_DEEPSEEK_FLASH = NV_DEEPSEEK
NV_KIMI = "nvidia:moonshotai/kimi-k3"              # Moonshot AI's Kimi K3: retired by NVIDIA (HTTP 410), removed Nov 2
MISTRAL_MEDIUM = "mistral:mistral-medium-latest"
# Background headline labelers: run on the same headlines as the live labeler (Haiku), recorded and
# graded, never used for decisions. After ~3 months keep the cheapest one that's about as accurate.
MISTRAL_SMALL = "mistral:mistral-small-latest"
SHADOW_LABELERS = [GEMMA, NV_DEEPSEEK_FLASH]

MODELS = {
    # macro agent (monthly + tripwires)
    "macro_extract":    FLASH,                          # reads fetched pages; code verifies every quote
    "macro_gather":     HAIKU,                          # search fallback only (tool-enforced allowed domains)
    "macro_reason_1":   SONNET,
    "macro_reason_2":   OPUS,
    "macro_reason_3":   FLASH,
    "macro_reason_4":   GROK,                           # independent 4th view (Mistral was unreliable)
    "macro_critic":     SONNET_55,
    # stock team (biweekly)
    "news":             [HAIKU, GEMMA],                 # headline labels; Gemma only if Haiku fails
    "filing_summary":   FLASH,
    "fundamentals":     FLASH,                          # free first pass on every stock (Haiku if Gemini fails)
    "fundamentals_escalation": SONNET,                  # red flags, unverified quotes, likely new buys
    "catalyst":         FLASH,                          # Google search grounding; auditor enforces rules
    "debate_bull":      GROK,
    "debate_bear":      GROK,                           # same model both sides = fair debate
    "council":          FLASH,                          # investor council notes for the hidden council dossier (test)
    "shadow_signals":   FLASH,                          # earnings quality, guidance change, read-across scores (test)
    "judge":            SONNET,                         # used only if JUDGE_PANEL is empty
    "portfolio_manager": OPUS,
    "portfolio_critic": SONNET,                         # different model from the PM
    # daily watch
    "watch_news":       [HAIKU, GEMMA],
    "filing_diff":      FLASH,                          # short note on what changed vs the prior filing
    "watch_escalation": SONNET_55,
}
# Debates for ~80 stocks need ~1.4M tokens per rebuild, far past Groq's free 200K tokens/day, so
# stocks are spread over several free models. Each stock's bull AND bear use the same model (fair
# debate); if that model fails partway, the whole debate reruns on the next one. Entries whose
# key isn't set are skipped. max_stocks caps each model's share of one run.
DEBATE_POOL = [
    {"model": GROK, "max_stocks": 200},              # paid but cheap (~$1.50 per rebuild) and reliable: the main slot
    {"model": NV_DEEPSEEK_FLASH, "max_stocks": 40},  # free NVIDIA endpoints: used if Grok is unavailable
    # Mistral's free tier is removed from debates: its rate limits stalled two overnight rebuilds
]

# If a free model fails (limits, outage, retired model), the call moves down this chain.
# Roles that need web search skip models without it. Claude roles never fall back.
# Fallback order for every non-Claude role: the free Gemini models first, then the same Flash model on the
# billed key (GEMINI_PAID_API_KEY), then other free models as a last resort. No Claude fallback: a role
# that is Gemini's job stays with Gemini. The paid copy is skipped if no billed key is set.
FLASH_PAID = FLASH + PAID_SUFFIX
FREE_FALLBACKS = [FLASH, "gemini-3.7-flash"]
PAID_FALLBACK = FLASH_PAID
LAST_RESORT = [GEMMA]                                   # free, used only if paid Gemini also fails (Mistral dropped Oct 2026: it kept failing the connection test)
GEMINI_FALLBACK = PAID_FALLBACK                         # older name, kept for compatibility
GEMINI_PAID_MODELS = {GEMINI_PRO, FLASH_PAID}           # these use GEMINI_PAID_API_KEY when it exists

PROVIDERS = {  # OpenAI-compatible chat providers: base URL, secret name
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),              # Grok (xAI), OpenAI-compatible
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),   # used via the Responses API
}

# ------------------------------------------------------------------ judge panel
# Every judge sees the SAME packet and never sees the others' scores (blind).
#   live=True   -> its score counts toward the averaged conviction the PM uses
#   live=False  -> shadow: scored and recorded in the ledger only, so we can learn whether it
#                  would have been a better judge before paying for it to matter
#   sample      -> share of stocks it scores (1.0 = all; 0.5 = a random half, fixed per ticker+date)
#   thinking    -> minimal | low | medium | high  (None = model default)
JUDGE_PANEL = [
    {"id": "sonnet", "model": SONNET,        "live": True,  "thinking": "medium", "sample": 1.0, "enabled": True},
    {"id": "sonnet55", "model": SONNET_55,   "live": False, "thinking": "medium", "sample": 1.0, "enabled": True},   # shadow: scored and graded, not counted
    {"id": "gpt_sol", "model": GPT_SOL,      "live": True,  "thinking": "medium", "sample": 1.0, "enabled": True},
    {"id": "gemini_pro", "model": GEMINI_PRO, "live": True, "thinking": "medium", "sample": 1.0, "enabled": True},
    # Opus is not run live: every judge packet is archived, so it can be replayed later (pipeline/replay.py)
    {"id": "opus", "model": OPUS,            "live": False, "thinking": "medium", "sample": 1.0, "enabled": False},
    {"id": "gpt_astra", "model": GPT_ASTRA,  "live": False, "thinking": "medium", "sample": 1.0, "enabled": False},
    {"id": "grok", "model": GROK,             "live": False, "thinking": None,     "sample": 1.0, "enabled": True},   # ~$1/rebuild
    {"id": "deepseek", "model": NV_DEEPSEEK, "live": False, "thinking": None,     "sample": 1.0, "enabled": False},  # NVIDIA timeouts
    {"id": "mistral", "model": MISTRAL_MEDIUM, "live": False, "thinking": None,   "sample": 1.0, "enabled": False},  # always rate-limited
]
# Investor council (a test, added Nov 2): after the debate, three investing styles each write a short cited note.
# The notes go ONLY into a hidden "council dossier" read by a shadow copy of the live Sonnet judge (same model and
# settings), so the live judges and picks are untouched. The look-back and evaluation compare the shadow copy with
# the live Sonnet judge on the same stocks: any difference is the council's doing.
COUNCIL = [
    {"id": "graham", "lens": "Benjamin Graham: margin of safety, balance-sheet strength, price versus conservative value"},
    {"id": "lynch", "lens": "Peter Lynch: growth at a reasonable price, earnings growth versus P/E, is the story simple and intact"},
    {"id": "druckenmiller", "lens": "Stanley Druckenmiller: inflections in fundamentals and liquidity, what changes in the next few months"},
]
COUNCIL_JUDGE = {"id": "sonnet_council", "model": SONNET, "live": False, "thinking": "medium", "sample": 1.0,
                 "enabled": True}

# Shadow signals (a test, added Nov 13): three narrow scores per candidate, logged to the decision ledger as
# pseudo-judges (sig_beat_quality, sig_guidance, sig_read_across) and graded by the look-back like any shadow judge.
# Nothing reads them: not the judges, not the PM. Promote one only if its rank correlation holds over several rebuilds.
SHADOW_SIGNALS = ["beat_quality", "guidance", "read_across"]
PEER_WINDOW_DAYS = 35        # peers' earnings reports this recent feed the read-across score

JUDGE_DISAGREEMENT = 10       # live judges' probability spread (percentage points) at or above this is flagged
JUDGED_PER_REBUILD = 80       # stocks scored by the panel each rebuild (screen shortlist size)

# Pre-registered decision rule (EVALUATION.md). Written down before any results exist; change it
# only with a dated note in EVALUATION.md explaining why, never after peeking at a result.
EVAL_RULE = {
    "horizon": "4w",                        # primary test: live panel IC at 4 weeks, sector-neutral
    "looks_months": [3, 6, 9, 12],          # the only times the rule is allowed to decide
    "t_boundaries": [3.0, 2.6, 2.3, 2.0],   # stricter early looks, so peeking 4 times stays honest
    "min_dates": 6,                         # graded rebuilds needed before any verdict
    "futility_from_look": 2,                # from the 6-month look, a non-positive IC means stop
    "futility_ic": 0.0,
    "promote_horizon": "13w",               # a shadow judge replaces a live one only if it beats the
    "promote_min_dates": 12,                # panel by a clear margin, sustained, at the long horizon
    "promote_t": 2.0,
    "promote_margin": 0.02,
    "brier_min_forecasts": 300,             # second test: the panel must beat the base rate's Brier score
    "prune_min_pairs": 300,                 # a component is removable when, over this many paired forecasts,
    "prune_max_benefit": 0.001,             # the upper 95% bound of its Brier benefit is below this
    "macro_review_months": 12,              # macro agent: revert to neutral if it beats neither opponent by then
}

# ------------------------------------------------------------------ probabilities and portfolio rules
# Every judge forecasts P(stock beats its equal-weighted sector over the next 4 weeks), starting from a
# historical base rate (pipeline/history.py) and moving it with itemized, cited adjustments.
PROB = {
    "adjust_cap": 15,        # max total adjustment (points) unless the judge flags a cited exception
    "clip": (0.03, 0.97),    # no forecast is ever this certain
    "buy_edge": 2,           # new buy: at least this many points above its base rate... (3 until Nov 9: only 10 of
                             # 80 names cleared +3 on Nov 1, 7 of them Energy, too few for a 15-20 name book)
    "buy_min": 0.50,         # ...and above this probability
    "keep_edge": -2,         # a holding keeps its place down to this edge...
    "keep_min": 0.47,        # ...and this probability (the gap is a buffer against churn)
    "swap_margin": 4,        # a newcomer replaces a holding only if its edge is this much larger...
    "tax_points_per_5pct": 1,  # ...plus 1 point per 5% of short-term gain the sale would realize (Individual)
    "long_term_guard_days": 30,  # a non-urgent sale of a winner this close to long-term waits
    "confirm_rebuilds": 2,   # a sell signal must appear at this many rebuilds in a row (unless thesis broken)
}
MOMENTUM_CAP = 40.0          # legacy count-based cap (only used when no momentum scores are available)
MOMENTUM_MAX_LEVEL = 0.80    # the stocks' weighted-average momentum score (0-1, the screen's within-sector rank)
                             # may not exceed this: momentum names are fine, an all-momentum book isn't
PANEL_SHARPEN = 1.5          # shadow 'sharpened' panel: distance from the base rate x1.5 (log-odds); graded only
MIN_HISTORY_DAYS = 365       # no new buys of stocks with less trading history (IPOs, spinoffs)
MAX_PER_FACTOR = 6           # max holdings whose measured dominant macro factor is the same

# Themes (added Nov 5 after the midterm data-center selloff hit SEI, MU and ECG together although they sit in
# three sectors): the PM tags each pick with its main theme and code caps any one theme's combined weight.
THEMES = ["oil_price", "natural_gas", "refining_margins", "ai_datacenter_buildout", "semiconductors",
          "consumer_spending", "interest_rates", "housing", "healthcare_policy", "defense_spending",
          "industrial_metals", "agriculture", "insurance_pricing", "asset_management_flows", "trade_tariffs",
          "shipping", "other"]
THEME_CAP = 25.0             # % of the portfolio any one theme (except "other") may hold
EVENT_LOOKAHEAD_DAYS = 28    # scheduled events this close are shown to the PM
MARKET_EVENTS = [            # known dates the macro step may not list; it adds elections, votes, deadlines itself
    {"date": "2026-12-09", "event": "FOMC rate decision (Dec 8-9 meeting)", "exposed": ["interest_rates", "housing"]},
]
DROP_REVIEW_PCT = -25.0      # a holding this far below cost gets a thesis review (never an automatic sale)
BASE_RATE = {
    "start": "2010-01-01", "horizon_days": 20, "shrink": 200, "recent_years": 5,
    "recent_gap_warn": 5,    # warn when the last-5-years rate differs from the full history by this many points
    "min_group": 100, "rebuild_days": 30,
}
DOSSIER_MAX_ITEMS, DOSSIER_MAX_CHARS = 60, 14000

# ------------------------------------------------------------------ macro
MACRO_MODE = os.environ.get("MACRO_MODE", "active")   # "neutral" = no tilts and no paid macro run (pruned)
MACRO_HORIZON_WEEKS = 4
MACRO_FACTORS = {  # factor: (Yahoo ticker or ratio, unit of the forecast change)
    "rates_10y": "^TNX", "oil": "CL=F", "dollar": "UUP", "credit": "HYG/IEF", "inflation_exp": "TIP/IEF",
}
MACRO_TILT = {"small": 2, "full": 5, "hysteresis": 1, "max_full": 2, "narrative_cap": 5}

# ------------------------------------------------------------------ replay (models to test later on saved packets)
REPLAY = {
    "opus": {"model": OPUS, "thinking": "medium", "retires": None},       # set a date when one is announced
    "twin": {"model": SONNET, "thinking": "medium", "retires": None},
}

# ------------------------------------------------------------------ prices ($ per million tokens: input, output)
# Verified 2026-09-25 against each provider's pricing page. Batch = half price.
PRICES = {
    HAIKU: (1.00, 5.00),
    SONNET: (2.00, 10.00),
    SONNET_55: (2.00, 10.00),        # per a third-party price list on 2026-10-23; confirm on platform.claude.com/docs/en/about-claude/pricing
    OPUS: (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    GPT_SOL: (2.00, 10.00),
    GPT_ASTRA: (10.00, 50.00),
    "openai:gpt-6-luna": (0.10, 0.50),
    GEMINI_PRO: (2.00, 12.00),
    # Free tiers are $0. If you move a provider to paid, put real prices here.
    FLASH_PAID: (0.30, 2.50),        # billed Flash: check ai.google.dev/pricing and update if different
    FLASH: (0.0, 0.0), "gemini-3.7-flash": (0.0, 0.0), "gemini-3.5-flash-lite": (0.0, 0.0),
    "gemini-2.5-flash": (0.0, 0.0), GEMMA: (0.0, 0.0),
    GROQ_DEBATE: (0.0, 0.0), GROK: (1.25, 2.50), NV_KIMI: (0.0, 0.0), "mistral:mistral-large-latest": (0.0, 0.0), MISTRAL_LARGE: (0.0, 0.0), "mistral:mistral-small-latest": (0.0, 0.0),
    NV_DEEPSEEK: (0.0, 0.0), "nvidia:deepseek-ai/deepseek-v4-pro": (0.0, 0.0), "nvidia:deepseek-ai/deepseek-v4-flash": (0.0, 0.0), MISTRAL_MEDIUM: (0.0, 0.0),
    "nvidia:qwen/qwen3-next-80b-a3b-thinking": (0.0, 0.0),
}
UNKNOWN_PRICE = (5.00, 25.00)     # a model missing above is costed pessimistically (and warned about)
CLAUDE_SEARCH_PRICE = 0.01        # $ per web search (~$10 per 1,000)
GEMINI_SEARCH_PRICE = 0.0         # $0 inside any free grounding allowance; set 0.014 if billed
GEMINI_PAID_SEARCH_PRICE = 0.014  # grounded searches on the billed key (the catalyst role searches)
CACHE_WRITE_MULT = 1.25           # prompt-cache write costs 1.25x input
CACHE_READ_MULT = 0.10            # prompt-cache read costs 0.1x input
BATCH_DISCOUNT = 0.50             # Claude, OpenAI and Gemini batch APIs: 50% off
# Extra output tokens allowed for reasoning at each thinking level (thinking is billed as output).
THINKING_HEADROOM = {"minimal": 1024, "low": 4000, "medium": 8192, "high": 16000}

# Free-tier pacing (requests per minute), by model or provider. Check your real limits in each
# console (aistudio.google.com/rate-limit, console.groq.com, console.mistral.ai, build.nvidia.com).
RPM = {FLASH: 8, "gemini-3.7-flash": 8, "gemini-3.5-flash-lite": 12, GEMMA: 25, "google": 8,
       "groq": 2, "xai": 60, "mistral": 50, "nvidia": 35, "openai": 300, GEMINI_PRO: 60, FLASH_PAID: 60}
GEMINI_RPM = RPM                                        # older name
GEMINI_MAX_RETRIES = 3
BENCH_AFTER_FAILURES = 3        # a model failing this many calls in a row is skipped for a while
BENCH_COOLDOWN_SECONDS = 900    # ...15 minutes, then it gets another try (a one-off blip no longer costs a whole run)
COMPAT_TIMEOUT_SECONDS = 120    # Grok / Mistral / NVIDIA: give up on a stalled call after this long

# ------------------------------------------------------------------ budgets
# A run stops (and emails you) if its estimated spend passes its cap.
# The judge panel (~$0.12 per stock with thinking, batched) on ~80 stocks is most of a rebuild.
BUDGET_PER_RUN = {"macro": 1.50, "screen": 0.25, "team": 16.00, "rebuild": 20.00, "watch": 0.50,
                  "grade": 0.10, "council_plan": 4.00, "default": 2.00}

# ------------------------------------------------------------------ run mode
# PAPER_MODE: the full pipeline runs and emails, but trade lists are marked PAPER - do not place.
PAPER_MODE = os.environ.get("PAPER_MODE", "1") != "0"

# ------------------------------------------------------------------ source rules
# Macro: allow-list, enforced by Claude's search tool AND re-checked by the auditor.
MACRO_ALLOWED_DOMAINS = [
    "federalreserve.gov", "bls.gov", "bea.gov", "treasury.gov", "census.gov", "eia.gov",
    "ustr.gov", "trade.gov", "stlouisfed.org", "clevelandfed.org", "atlantafed.org",
    "newyorkfed.org", "cftc.gov", "truflation.com", "factset.com", "aaii.com",
    "cmegroup.com", "shillerdata.com", "econ.yale.edu",
    # business surveys, foreign central banks, international bodies
    "ismworld.org", "ecb.europa.eu", "bankofengland.co.uk", "boj.or.jp", "imf.org", "oecd.org",
    # geopolitics: wire services, energy agencies, export controls and sanctions, defense, freight
    # (Reuters and AP block the web-search crawler, which fails the whole search: not listed)
    "npr.org", "bbc.com", "cnbc.com", "cfr.org", "crisisgroup.org", "iea.org", "opec.org", "bis.gov", "bis.doc.gov", "state.gov",
    "defense.gov", "nato.int", "whitehouse.gov", "drewry.co.uk", "matteoiacoviello.com", "policyuncertainty.com",
]
# Company research: open web minus these...
COMPANY_BLOCKED_DOMAINS = [
    "reddit.com", "stocktwits.com", "x.com", "twitter.com", "facebook.com", "tiktok.com",
    "youtube.com", "quora.com", "medium.com", "substack.com", "seekingalpha.com",
    "fool.com", "investorplace.com", "benzinga.com", "zacks.com", "247wallst.com",
    "coinmarketcap.com", "coindesk.com", "cointelegraph.com", "stockanalysis.com",
    "marketbeat.com", "simplywall.st", "gurufocus.com", "finviz.com",
]
# ...plus: any fact that changes a score must trace to one of these primary sources
# (or the company's own website / investor-relations site).
PRIMARY_SOURCE_DOMAINS = [
    "sec.gov", "reuters.com", "apnews.com", "businesswire.com", "prnewswire.com",
    "globenewswire.com", "accessnewswire.com", "fda.gov", "ftc.gov", "justice.gov",
    "federalregister.gov", "nasdaq.com", "nyse.com", "spglobal.com",
]

# Reputable newsrooms: a DATED, SPECIFIC fact they report can support a forecast; a rumor ("people
# familiar with the matter") is labeled as such and can't move a forecast on its own.
REPUTABLE_NEWS_DOMAINS = ["bloomberg.com", "wsj.com", "ft.com", "cnbc.com", "barrons.com", "marketwatch.com",
                          "morningstar.com"]
RUMOR_PHRASES = ["people familiar", "familiar with the matter", "sources said", "according to people",
                 "people with knowledge", "reportedly", "is said to", "are said to", "rumor", "speculation"]

# How old a dossier item can be before it's marked STALE (days), by kind; others use "default".
STALE_DAYS = {"headline": 14, "news": 14, "event_8k": 45, "catalyst": 30, "fundamentals": 120, "filing_quote": 120,
              "filing_change": 120, "metric": 150, "financials": 150, "default": 120}
MATERIAL_8K_ITEMS = {
    "1.01": "entered a material agreement", "1.02": "terminated a material agreement", "1.03": "bankruptcy",
    "2.01": "completed an acquisition or disposition", "2.03": "took on a material obligation",
    "2.04": "a debt acceleration trigger", "2.05": "exit or restructuring costs", "2.06": "a material impairment",
    "3.01": "a delisting notice", "4.01": "changed auditors", "4.02": "prior financials can't be relied on (restatement)",
    "5.01": "a change in control", "5.02": "a director or executive departure/appointment",
}
MATERIAL_8K_DAYS = 45

# ------------------------------------------------------------------ portfolio shape
SECTORS = {  # sector -> SPDR ETF (used for macro history/momentum, not held in the portfolio)
    "Technology": "XLK", "Financials": "XLF", "Health Care": "XLV", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE",
    "Communication Services": "XLC",
}
# 5-level macro tilt -> allowed share of the stock portfolio (%). Stocks-only design:
# only overweight sectors have a floor; everything else is a ceiling and may hold zero.
# Narrowed Nov 9 (was 12-45 / 6-35 / 0-25 / 0-12 / 0-5): one sector call is a single bet, and a +1 tilt let
# Energy reach 35% of the book the week oil and data-center stocks fell. Sized for 15-20 names at 3-10% each.
TILT_RANGES = {2: (10, 25), 1: (5, 22), 0: (0, 18), -1: (0, 10), -2: (0, 5)}


def ranges_for(tilts):
    """Sector weight ranges (%) from the macro tilts under the CURRENT TILT_RANGES, scaled so they can always sum
    to 100%. Used wherever a stored macro view is read, so a change to TILT_RANGES applies at once rather than
    waiting for the next full macro run to rewrite the view."""
    r = {s: list(TILT_RANGES[int(t)]) for s, t in (tilts or {}).items()}
    lo, hi = sum(v[0] for v in r.values()), sum(v[1] for v in r.values())
    return {s: [round(a * 100 / lo, 1) if lo > 100 else a, round(b * 100 / hi, 1) if hi < 100 else b]
            for s, (a, b) in r.items()}


def with_current_ranges(macro):
    """The macro view with its weight ranges recomputed from its tilts (a copy; None stays None)."""
    if not macro or not macro.get("tilts"):
        return macro
    return dict(macro, **{"weight_ranges_%": ranges_for(macro["tilts"])})

# Sizing (changed Nov 9): the judges' edge had no measurable link to returns over the first five rebuilds
# (rank correlation -0.06), so it no longer scales position sizes. Weights are inverse volatility; the edge still
# decides which names are cut first when a cap binds. Set True again only if the edge proves itself.
SIZE_BY_EDGE = False

# ------------------------------------------------------------------ tracking
# Your marginal federal (+ state) rate on short-term gains; used only for the after-tax estimate.
TAX_RATE_SHORT_TERM = 0.24
TAX_RATE_LONG_TERM = 0.15        # held more than a year (FIFO lots decide which)
STARTING_VALUE = 10000.0

# ------------------------------------------------------------------ email
EMAIL_FROM = os.environ.get("GMAIL_ADDRESS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", EMAIL_FROM)


# ------------------------------------------------------------------ secrets
def secret(name, required=True):
    """GitHub Actions secrets arrive as environment variables; Colab secrets as userdata."""
    val = os.environ.get(name)
    if not val:
        try:
            from google.colab import userdata  # type: ignore
            val = userdata.get(name)
        except Exception:
            val = None
    if isinstance(val, str):
        val = val.strip().strip('"').strip("'").strip()   # a pasted key often carries a space, newline or quotes
    if required and not val:
        raise RuntimeError(f"Missing secret {name}. Add it to GitHub Secrets (or Colab Secrets).")
    return val
