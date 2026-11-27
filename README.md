# AI Portfolio Pipeline

Multi-agent stock portfolio: weekly macro view, weekly quant screen, biweekly AI stock team
and portfolio manager, daily holdings watch. Trades are emailed; you place them in Robinhood.

## Status
- [x] Shared foundation (`pipeline/`): config, model layer, auditor, email, runner
- [x] Macro agent (`python -m pipeline.macro`)
- [x] Quant screen (`python -m pipeline.screen`) + SEC data module (`pipeline/sec.py`)
- [x] Stock team (`python -m pipeline.team`): news, fundamentals, catalysts, debate, judge
- [x] Portfolio manager, review, trade email, GitHub checklist (`python -m pipeline.rebuild`)
- [x] Tracking (`python -m pipeline.track`) and daily watch (`python -m pipeline.watch`)
- [x] GitHub Actions workflows: weekly, rebuild (biweekly), daily watch, tests
- [x] Judge panel: 3 live judges (Sonnet 5, GPT-6 Sol, Gemini 3.1 Pro) + shadow judges (Grok 4.3,
      Kimi K3 via NVIDIA), blind, ~80 stocks per rebuild, holdings re-judged every rebuild
- [x] Probability forecasts: P(beat the equal-weighted sector in 4 weeks) from historical base rates
      (`python -m pipeline.history`) plus cited, capped judge adjustments
- [x] Better inputs: macro sensitivities, what's priced in, peer tables, earnings track record (`pipeline/inputs.py`)
- [x] Selling rules: separate buy/keep/sell bars, sell confirmed at two rebuilds, tax-aware swaps,
      long-term guard, weakest-first trims, momentum-level cap (stocks' average momentum score <= 0.80), 12-month history rule, 25%-below-cost review
- [x] Macro: economy forecast -> measured sector effects -> tilts only where the view disagrees with
      market pricing; graded against a free momentum rule; 12-month pruning rule
- [x] Screener: evidence-based weights (re-set yearly, halfway), post-earnings drift, industry momentum,
      short-term reversal, distress filter, scaled sub-industry cap, per-signal verdicts
- [x] Research dossier upgrades: every item dated and marked STALE when old; material 8-Ks (and a
      forced refresh when one lands); filing-vs-prior-filing comparison (code diff + short Flash note);
      quarterly trends, working capital, share count, backlog, stock pay, near-term debt; full-filing scan
      for material weaknesses, going-concern doubt and customer concentration; analyst estimate trends;
      Finnhub summaries with headlines. Legal proceedings are skipped; call transcripts deferred.
- [x] Headline labels: Haiku live, Gemma and Mistral Small in the background, all graded
      (`label_ledger.csv`); daily watch reads up to 2 full articles, only for thesis reviews
- [x] Sources: ISM PMIs, ECB/BoE/BoJ, IMF/OECD added for macro; reputable-newsroom tier (Bloomberg, WSJ,
      FT, CNBC, Barron's, MarketWatch, Morningstar) where dated specific facts count and rumors don't
- [x] Replays: every judge packet archived; Opus and ablated "twin" judges tested later (`pipeline/replay.py`)
- [x] Decision ledger + grading at 2/4/13 weeks + judge report card + pre-registered decision rule
      (`pipeline/ledger.py`, **EVALUATION.md**)
- [x] Safety: preflight, fail-closed trade-plan integrity gate, FIFO tax lots, idempotent
      reconciliation, atomic state writes, version stamps, run log, paper mode, pinned dependencies

- [x] Alpaca paper trading: in paper mode approved trades are placed automatically in an Alpaca paper
      account (weekday mornings, sells first) and recorded at their real fills (`pipeline/broker.py`)
- [x] After the first live run: the PM revises once for the critic's flags (paper mode then places the
      result); hidden common bets (names whose market-adjusted moves correlate) capped at 20% together;
      positions sized by edge / volatility; a critic-flagged macro tilt moves one step toward neutral;
      stalled free models paused 15 minutes; **Replan** (Actions → Rebuild → replan) redoes only the
      portfolio steps on the last judging (~$0.60)
- [x] Candidate screen signals, tested on 15 years of history before earning any weight: residual momentum,
      risk-adjusted momentum, low volatility, ROIC, margin stability; value now tested from point-in-time
      filings; estimate revisions for every stock; sizing uses blended 60-day / 1-year volatility
- [x] Connection test: one tiny call to every model, data source and Gmail; monthly + on demand
      (`python -m pipeline.connections`, Actions → Connection test). All job times: **SCHEDULE.md**

See **SETUP.md** for the full setup and weekly routine, and **EVALUATION.md** for how results are judged.

## Secrets (GitHub > Settings > Secrets and variables > Actions)
| Name | Where to get it |
|---|---|
| ANTHROPIC_API_KEY | platform.claude.com > Settings > API keys |
| OPENAI_API_KEY | platform.openai.com > API keys (paid; GPT-6 Sol live judge) — optional, judge skipped without it |
| GEMINI_PAID_API_KEY | aistudio.google.com key on a project **with billing on** (Gemini 3.1 Pro live judge) — optional |
| NVIDIA_API_KEY | build.nvidia.com (free; optional — its DeepSeek models were retired, so nothing uses it now; the connection test lists what it still serves) |
| XAI_API_KEY | console.x.ai (paid, prepaid credits; ~50¢/month) — Grok runs part of the bull/bear debates |
| MISTRAL_API_KEY | console.mistral.ai (free Experiment tier; phone verification, opt-in to data use) |
| GEMINI_API_KEY | aistudio.google.com > Get API key |
| FRED_API_KEY | fred.stlouisfed.org > My Account > API Keys |
| FINNHUB_API_KEY | finnhub.io dashboard |
| GMAIL_ADDRESS | the Gmail account that sends reports |
| GMAIL_APP_PASSWORD | Google Account > Security > App passwords (needs 2-Step Verification) |
| EMAIL_TO | optional, where reports go (defaults to GMAIL_ADDRESS) |

Variable (Settings > Secrets and variables > Actions > **Variables** tab): `PAPER_MODE` — leave unset
(or `1`) for paper trading; set to `0` to go live.

## Foundation at a glance
- `config.py` – every model, price, budget, judge, and source rule in one place
- `llm.py` – `Session.ask()` / `Session.batch()`: Claude, Gemini, OpenAI (Responses API), xAI (Grok), Groq,
  Mistral, NVIDIA; one thinking vocabulary (minimal/low/medium/high) for all; prompt caching;
  50%-off batching on Claude, OpenAI and paid Gemini, resumable so a batch is never paid twice;
  free-tier pacing + fallback chain; receipts, cost log, budget cap
- `history.py` – base rates (2010-now) and today's stock features; equal-weighted sector benchmark
- `inputs.py` – sensitivities, valuation vs peers/history, options-implied earnings move, peers, track record
- `ledger.py` – decision ledger, grading, judge report card, pre-registered decision rules, pruning tests
- `replay.py` – replay a model (or an ablated twin) on archived judge packets
- `integrity.py` – fail-closed checks on every trade plan before it's emailed
- `preflight.py` – settings and secrets check that runs before every workflow
- `audit.py` – source rules (allow-list for macro; block-list + primary-source rule for
  companies) and evidence checks (every cited number must match the data)
- `notify.py` – Gmail delivery (saves .eml files when secrets are missing)
- `runner.py` – wraps each stage: budget/errors trigger an alert email, costs always saved

## Tests
`python -m pytest tests/` runs every test file in its own process (offline, no keys needed). Any
single file also runs on its own, e.g. `python tests/test_ledger.py`.

## Rebuild cycle (every two weeks)
1. Saturday: the rebuild emails you the trade list and opens a GitHub issue with a checklist.
2. Monday: place the "Ready to place" trades in Robinhood (sells first, limit orders).
3. Tick each trade in the issue (GitHub app works). Optional: add your fill price, e.g. `@51.10`.
4. The next rebuild reads the checklist and updates `state/holdings.json` before planning.

## Schedule
| Workflow | When | What |
|---|---|---|
| Weekly | Fri after close | macro light check (free; full run when due or tripped) -> quant screen -> tracking |
| Rebuild | Sat, even ISO weeks | stock team -> portfolio manager -> critic -> trade email + checklist |
| Daily | weekdays after close | resume any stopped run, then the holdings watch (emails only when needed) |
| Paper orders | weekday mornings (paper mode) | places approved trades in Alpaca paper; fills recorded at tracking |
| Connection test | 1st of each month + on demand | one tiny call to every model, data source and Gmail; emails pass/fail |
| Tests | on code changes | offline test suite, no API costs |

## Models
| Work | Model | Paid? |
|---|---|---|
| Macro reasoning (4 independent economy forecasts) | Sonnet 5, Opus 5.5 (batched) + Gemini 3.8 Flash + Grok 4.3 | 3 of 4 |
| Macro evidence | code fetches the pages; Gemini Flash extracts, code verifies every quote | free |
| Judge panel, live (averaged) | Sonnet 5, GPT-6 Sol, Gemini 3.1 Pro, medium thinking, batched | paid |
| Judge panel, shadow (recorded only) | Grok 4.3 (xAI, ~$1/rebuild), Kimi K3 (NVIDIA, free) | mostly free |
| Replayed later on saved packets | Opus 5.5; Sonnet "twins" with one section removed | paid when run |
| Macro critic, portfolio manager, portfolio critic | Sonnet 5 / Opus 5.5 | paid |
| Headline labels, daily news screen | Haiku 4.5 live; Gemma 4 + Mistral Small in the background (graded) | ~$0.40/mo |
| Filing comparison note (what changed vs prior filing) | Gemini Flash | free |
| Filing summaries, catalysts | Gemini Flash | free |
| Fundamentals review | Gemini Flash (free); Sonnet for red flags and likely new buys | mostly free |
| Bull/bear debates | Grok 4.3 (xAI), DeepSeek V4.1 Flash, Mistral Medium, spread across providers (same model both sides) | ~50¢/mo |

If a free model fails, the call moves down a fallback chain and only reaches Claude Haiku as a last
resort; the run report counts fallbacks. Free-provider model IDs change often — verify them in
`config.py` after the first run.

## Macro cadence
Full (paid) macro runs happen monthly, after both the jobs report and CPI are out, plus any week a
tripwire fires: an emergency trigger, a core variable moving 1+ standard deviation or turning
unusual, a Fed rate change, or a new dot plot. Every other week the free light check refreshes the
data and writes a "what changed since the view" digest that the rebuild passes to the portfolio
manager and critic. A flagged macro view waits for your APPROVE/REJECT on a GitHub issue.

## Settings worth reviewing in `pipeline/config.py`
- `TAX_RATE_SHORT_TERM`, `TAX_RATE_LONG_TERM` (for the after-tax estimate)
- `JUDGE_PANEL` (who judges, live vs shadow, thinking level, sample share), `JUDGED_PER_REBUILD`
- `PRICES` (verified 2026-09-25), `BUDGET_PER_RUN` (hard spending caps per run)
- `EVAL_RULE` (the pre-registered decision rule; see EVALUATION.md before touching it)

## Optional Robinhood cross-check
Export account activity CSVs from Robinhood and commit them to `imports/robinhood/` with
`individual` or `ira` in the file name. Tracking compares net shares with the book.

## When a run stops (credits, outages, budget caps)
- You get one plain-English email: what happened, what to do, and what progress was saved.
- Nothing is traded and no plan or macro view changes.
- Progress is checkpointed in `state/checkpoints/`: finished steps, per-stock research and debates,
  and submitted Claude batches (collected on resume, never paid for twice).
- **Resuming is automatic:** every weekday evening the daily job resumes any run that stopped in the
  last 4 days. Fix the cause (e.g. add credits) and it finishes that evening, or tap Run workflow
  to resume immediately. A stopped rebuild resumes without the force option.
- Retries are quiet; after 4 attempts you get one final email and retries stop.
