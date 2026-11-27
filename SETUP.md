# Setup checklist

Two parts: **A. get it running on GitHub** (about an hour, laptop) and **B. the routine once it's live**
(a few minutes a week, phone is fine).

---

## A. Get it onto GitHub

### 1. Collect the API keys (paid: Claude, OpenAI, the paid Gemini key; the rest are free)

| Key | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | platform.claude.com → Settings → API keys | Paid. Buy credits (minimum $5) and consider auto-reload with a monthly cap. Copy the key once — it isn't shown again. |
| `OPENAI_API_KEY` | platform.openai.com → API keys | Paid (prepaid credits). Runs the GPT-6 Sol live judge. Optional: without it that judge is skipped. |
| `GEMINI_PAID_API_KEY` | aistudio.google.com → Get API key, on a Google Cloud project **with billing enabled** | Paid. Gemini 3.1 Pro has no free tier, so it needs its own billed key; keep `GEMINI_API_KEY` on the free project so free work stays free. Optional. |
| `NVIDIA_API_KEY` | build.nvidia.com → sign in → Get API Key | Free. Optional: NVIDIA retired its DeepSeek models (Sept 2026), so nothing uses it now; the connection test lists what it still serves in case a replacement is worth adding. |
| `GEMINI_API_KEY` | aistudio.google.com → Get API key | Free tier. Used for filing summaries, catalysts, news, embeddings. |
| `XAI_API_KEY` | console.x.ai → API Keys | Paid (prepaid credits; $5 lasts months). Grok 4.3 runs part of the bull/bear debates, about 50¢ a month. Keys start with `xai-`. Optional: without it those debates go to the free models. |
| `MISTRAL_API_KEY` | console.mistral.ai | Free "Experiment" tier: phone verification, and you must opt in to their data use. Runs the fundamentals review, the 4th macro reasoner, a shadow judge and most debates. |
| `FRED_API_KEY` | fred.stlouisfed.org → My Account → API Keys | Free. All the macro data. |
| `FINNHUB_API_KEY` | finnhub.io | Free. Company news, earnings surprises, earnings calendar. |
| `GMAIL_APP_PASSWORD` | Google Account → Security → App passwords (needs 2-Step Verification on) | 16 characters. Sends the reports. |
| `GMAIL_ADDRESS` | — | The Gmail address that sends. |
| `EMAIL_TO` | — | Optional: where reports go (defaults to `GMAIL_ADDRESS`). |
| `ALPACA_API_KEY_ID` | alpaca.markets → Paper Trading → API Keys | Free. Paper mode only: approved trades are placed automatically in your Alpaca **paper** account and recorded at their real paper fills. Use the paper keys (live keys won't work: the code only talks to the paper endpoint). Optional: without them paper trades are recorded at reference prices. |
| `ALPACA_API_SECRET_KEY` | same page (shown once) | The secret that goes with the key ID. |

### 2. Create the repository
1. Sign up at github.com and turn on two-factor authentication.
2. **+ → New repository**, name it `ai-portfolio`, set it to **Private** (it will hold your trade history), create.

### 3. Upload the code (laptop)
1. Unzip `ai_portfolio.zip`.
2. In the repo: **Add file → Upload files**, drag in everything *inside* the folder (`pipeline/`, `tests/`,
   `README.md`, `SETUP.md`, `EVALUATION.md`, `SCHEDULE.md`, `requirements.txt`, `.gitignore`), commit. The files
   must sit at the top level of the repo, not inside an `ai_portfolio` folder, or GitHub won't find the workflows.
3. The `.github` folder is hidden on most computers and usually won't drag. Add the seven workflow files by
   hand: **Add file → Create new file**, name it `.github/workflows/weekly.yml` (the slashes create the
   folders), paste the contents, commit. Repeat for `rebuild.yml`, `daily.yml`, `tests.yml`,
   `replay.yml`, `connections.yml`, `orders.yml` and `backfill.yml`.

### 4. Add the secrets
**Settings → Secrets and variables → Actions → New repository secret**, one per row in the table above.
Names must match exactly. GitHub provides `GITHUB_TOKEN` automatically — don't add it.
Keys live only in GitHub Secrets: never paste one into `config.py` or any file in the repo.

Then the **Variables** tab → New repository variable: `PAPER_MODE` = `1` (paper trading; this is also
the default when it's missing). Change it to `0` only when you go live (step 7).

### 5. Check the settings you own
In `pipeline/config.py`:
- `TAX_RATE_SHORT_TERM` — your marginal rate on short-term gains (default 24%), used for the after-tax estimate.
- `PRICES` — verified against each provider's pricing page on 2026-09-25.
- `BUDGET_PER_RUN` — hard per-run spending caps (rebuild $20: the judge panel is ~$10 of it).
- `JUDGE_PANEL` — who judges; `JUDGED_PER_REBUILD` — how many stocks (80).
- `GEMMA`, `GROK`, `MISTRAL_MEDIUM`, `MISTRAL_SMALL` — free-provider model IDs change often; the
  preflight step and the run report flag a retired one.

In `pipeline/book.py`: `STARTING_CASH` — set to what each account actually starts with ($5,000 each by default).

### 6. First runs, in this order
1. **Actions → Tests → Run workflow.** Free, ~2 minutes, no API calls. Confirms the upload is complete and
   that the settings pass the preflight check.
2. **Actions → Connection test → Run workflow.** Under a penny, ~3 minutes. Makes one tiny call to every
   model, data source and Gmail and emails you a pass/fail table with what to fix (key rejected, model
   renamed, out of credits). Fix any FAIL line and re-run it until it's clean. Run it again whenever you
   add or change a key or a model name.
3. **Actions → Weekly → Run workflow.** The first run is slow (1–3 hours): it downloads SEC data for the
   whole S&P 1500, 60 days of insider filings, and — once — 15 years of prices, earnings dates and annual
   reports to build the base rates. It will do a full macro run (no view exists yet) and cost about
   $0.50–$1. You should get a macro email and a new commit with `state/` and `runs/`. If the first run
   times out during the base-rate backfill, just run Weekly again: the downloaded history is cached and
   it picks up where it stopped.
4. **Actions → Rebuild → Run workflow with "force" ticked.** ~1–2 hours (the judges' batches take a while),
   about $7–9. In paper mode you get the trade email marked PAPER and no checklist; the approved trades
   are recorded automatically as if filled.

### 7. Paper first, then live
- The pipeline starts in **paper mode**: everything runs for real (research, judges, trade lists,
  tracking, grading) except that you don't place trades; approved trades are recorded as filled at
  their reference price. First-run bugs cost nothing, and the judges' track record starts building.
- **Going live:** open and fund the two Robinhood accounts; in `pipeline/book.py` set `STARTING_CASH` to
  the real balances; run `python -m pipeline.book --go-live` once (it archives the paper book to
  `state/paper_archive/`) and commit; then set the `PAPER_MODE` variable to `0`. The judge ledger and
  grades carry over — they don't depend on real money.

---

## B. The routine once it's live

### Automatic schedule
| When | What happens | Email? |
|---|---|---|
| Fri after close | Macro light check (free) or full run if due/tripped → screen → tracking | Only on a full macro run, a drawdown level change, or in the first week of a month (performance report) |
| Sat, every 2nd week | Stock team → portfolio manager → critic → trade list + checklist | Yes |
| Weekdays after close | Resume any stopped run, then the holdings watch | Only when something needs you |
| 1st of each month | Connection test (every model, data source, Alpaca, Gmail) | Yes: pass/fail table |
| Weekday mornings (paper mode) | Places approved paper trades in Alpaca, sells first | Yes, when orders are placed |

Exact times for every job: **SCHEDULE.md**.

### Your part (a few minutes)
1. **Saturday:** read the trade email. Approved trades are ready; flagged ones include the critic's concern
   and a recommendation.
2. **Monday:** (paper mode with Alpaca: nothing to do; the orders go in automatically at ~10:45 am ET and
   you get a "Paper orders" email.) Live: place the trades in Robinhood after the first 15–30 minutes of trading. Sells first, limit
   orders good for the day, dollar amounts as listed.
3. **Tick each trade** in the GitHub issue (phone app works). Optionally add your fill price, e.g. `@51.10`.
   Anything unticked is treated as not placed.
4. **When a macro view is flagged:** tick APPROVE or REJECT on its issue. Until you do, the previous view stays in use.
5. **Monthly:** read the performance email: the portfolios (AI actual, AI as recommended, equal-weight and
   no-macro controls, screen-only control, SPY, SPTM), attribution, and the **judge report card** with this
   month's verdict from the pre-registered decision rule (EVALUATION.md). Optionally export Robinhood
   activity CSVs into `imports/robinhood/` for the position cross-check.

### If something breaks
- You get one plain-English email: what happened, what to do, and what progress was saved.
- Fix the cause (usually adding credits). The daily job resumes the run automatically that evening, or tap
  **Run workflow** to resume immediately. After 4 failed attempts it stops retrying and tells you.

### Review points, decided in advance
- **Portfolio (6 and 12 months):** beats SPY *and* the screen-only control after costs → continue.
  Beats SPY but not the screen → drop the AI stages, keep the free screen. Beats neither → pause and rethink.
- **Judges (3, 6, 9, 12 months):** the pre-registered rule in EVALUATION.md decides whether the panel's
  stock-picking skill is real, and whether a shadow judge has earned a live seat (your approval required).
  Scaling to the 401(k) waits for "EDGE CONFIRMED".

### Expected cost
About **$22.40 a month** (~2.7% a year of $10,000): three live judges on ~80 stocks (~$6 per rebuild),
re-judging holdings (~$1.40), the portfolio manager, critic, reviews, monthly macro run and the Haiku
headline labeler (~$0.40). Opus and the
pruning "twins" aren't run live; replaying them later on the saved packets costs roughly $4 (Opus) or
$2 (a twin) per rebuild's worth of packets, only when you choose to run them (Actions → Replay).
`state/cost_log.csv` records every call; `state/run_log.csv` one line per run.
