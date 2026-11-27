# How results are judged (pre-registered)

Written on 2026-09-25, **before any results exist**. The point of writing it now is that nothing
here can be tuned after seeing how things went. If a rule changes, add a dated entry at the bottom
saying what changed and why — and never change it in response to a result.

## The question
Does the AI stock team pick stocks better than chance, after stripping out what the market and each
stock's sector did — and better than the free statistics alone? Only if both are answered "yes",
with evidence strong enough to survive luck, does money scale up (the 401(k) is the end goal).

## What each judge forecasts
The probability that a stock beats its **equal-weighted sector** over the next **4 weeks**. Every
forecast starts from a **base rate**: how often stocks with the same momentum, earnings reaction and
quality did that from 2010 on (`pipeline/history.py`). Judges move it only with itemized, cited
adjustments (±15 points unless a cited exception). Code rebuilds each probability from the base
rate plus the valid adjustments; the live judges are averaged on the log-odds scale.

## What is recorded (state/decision_ledger.csv)
Every stock the panel scores on every rebuild — about 80, including rejections — with each judge's
probability, the panel average, the base rate (recorded as its own "judge"), the spread between
judges, and version stamps (code commit, settings hash, prompt hash). Every judge packet is archived
(`state/packets/`), so other models can be replayed on the identical inputs later.

## How each decision is graded (state/grades.csv)
- Clock starts at the close of the first trading day **after** the decision (no peeking).
- Horizons: **2, 4 and 13 weeks** (10, 20, 65 trading days).
- Score: the stock's return minus its **equal-weighted sector** ("residual"); beat = residual > 0.
  Equal-weighted because a few giants can drive a cap-weighted sector ETF (the ETF version is kept
  as a secondary figure).

## The two tests
1. **Ranking skill — information coefficient (IC):** on each rebuild date, the rank correlation
   between the panel's probabilities and the residual returns; averaged across dates. 0 = no skill;
   +0.05 sustained is good; t ≥ 2 = unlikely to be luck. The t-statistic is corrected for overlap.
2. **Value over the free statistics — Brier score:** the panel's forecasts must be more accurate than
   the base rate's on the same stocks (paired, per date, overlap-corrected), over at least **300**
   graded forecasts, with t ≥ 2. If ranking skill exists but this test fails, the edge belongs to the
   statistics, not the AI: don't pay for scale on it.

## The decision rule
Decisions are allowed only at these looks, counted from the first ledger entry, using the **4-week**
horizon:

| Look | Months | IC t needed |
|---|---|---|
| 1 | 3 | 3.0 |
| 2 | 6 | 2.6 |
| 3 | 9 | 2.3 |
| 4 | 12 | 2.0 |

- At least **6 graded rebuilds** before any verdict.
- **EDGE CONFIRMED:** the IC bar is met at a look **and** test 2 passes.
- **STATISTICS ONLY:** the IC bar is met but test 2 fails.
- **NO EDGE (futility):** from look 2 on, a mean IC at or below 0 — do not scale; redesign or stop.
- **NOT PROVEN:** the final look without reaching the bar — do not scale on this evidence.
- Otherwise **continue**, unchanged.

These numbers live in `config.EVAL_RULE`; the monthly email reports the verdict.

## Shadow and replayed judges
Shadow judges (Grok 4.3 from xAI; Kimi K3 via NVIDIA) score the same packets live. Paid candidates (Opus 5.5) are
**replayed later** on the archived packets (`python -m pipeline.replay opus`): a model whose training
data ends before the packets' dates can't know the outcomes, so replayed forecasts are fair. A model
released later can only be tested going forward. Replays must run before a model is retired (set
`retires` in `config.REPLAY`; the monthly email warns within 90 days).

A shadow or replayed judge becomes a **promotion candidate** only if, at the **13-week** horizon, over
at least **12 graded rebuilds**, its IC beats the live panel's by at least **0.02** with t ≥ 2.
Promotion still needs your approval. The best **combinations** of judges are also listed; with many
tested, the best will look better than it is, so trust only what holds up over time.

## Pruning the stock team
Each part is tested by a **twin**: the same live model replayed on the archived packets with one
section removed (`python -m pipeline.replay twin no_debate | no_news | no_fundamentals | no_catalysts
| no_new_inputs`). Benefit of the section = Brier(twin without it) − Brier(live judge with it).
A section is **removable** when, over at least **300** paired forecasts, even the upper 95% bound of
its benefit is below **0.001** — i.e. we're fairly sure it doesn't help, not merely unsure that it
does. Removal needs your approval and a dated entry below; a removed part can be restored.
The portfolio manager, sizing and macro tilts are tested by the control portfolios (equal-weight
same picks; top-rated stocks with no PM and no sector limits); the critic by comparing the trades it
flagged with the ones it approved.

## The macro agent
Each full run records per-sector probabilities of beating SPY over 4 weeks, the historical base rate,
the tilt, and a free opponent's call (**momentum rule**: favor the sectors with the strongest past
12 months). Graded at 4 and 8 weeks; the report compares sector ranking skill (IC) and Brier scores.
**After 12 months**, if the macro view beats neither the momentum rule (sector IC) nor the no-macro
portfolio, the rule recommends reverting to neutral sector ranges and stopping the paid macro run
(`MACRO_MODE=neutral`, with your approval).

## Other things the report card shows
- **Calibration:** of forecasts in each band (e.g. 55–60%), how often the stock actually beat its sector.
- **Bought vs passed over**, **sold vs kept** (4 weeks after each rebuild — if sold stocks keep doing
  better, the selling is hurting), and **critic-flagged vs approved** buys.
- **Catalysts:** share of positive/negative catalysts where the stock moved the expected way.
- **Headline labelers:** Haiku (live) vs Gemma and Mistral Small (background) on the same headlines;
  a YES/NO label is right if the stock beat/trailed its sector ETF over the next 2 trading days. After
  ~3 months, keep the cheapest labeler that's about as accurate (your call; nothing switches automatically).
- **Process errors:** invalid citations, uncited adjustments, unusable replies, missing exit
  conditions, fallbacks. Last run's counts are fed into the next run's prompts (mechanical fixes only).

## Not automated on purpose
Lessons about *judgment* ("the judges overrate turnaround stories") are not written into prompts
automatically. They need to be proposed, shown to you with the evidence, and approved. Per-judge
calibration corrections start only after 6 months and 300 graded forecasts per judge, and only if
they improve accuracy on data they weren't fitted to.

## Change log
- 2026-09-25: initial rule (1–5 conviction, sector-ETF residuals).
- 2026-09-25, before the first live rebuild and before any results: forecasts changed to probabilities
  with historical base rates; benchmark changed to the equal-weighted sector; Brier test vs the base
  rate added as the second test; twin-based pruning, macro 12-month rule and replayed judges added.
- 2026-09-26, before any results: headline labeler switched to Haiku with graded background labelers;
  dossier items dated/marked stale; reputable-newsroom tier (no rumors) added. No change to the rule.
- 2026-09-27, after the first rebuild and before any grading: shadow judges switched to Grok 4.3 and Kimi K3
  (Mistral and DeepSeek never answered); portfolio construction changed (PM revision for critic flags, edge /
  volatility sizing, 20% cap on correlated groups, critic-flagged macro tilts move one step to neutral).
  Forecasting and the decision rule are unchanged.
- 2026-09-27: screen gains zero-weight candidate signals (residual and risk-adjusted momentum, low volatility,
  ROIC, margin stability); value becomes testable. Weights still move only by the pre-set yearly rule
  (halfway toward the 15-year evidence), re-run early once when a new signal first has evidence.
- 2026-09-27: base rates may add value and volatility groups when their 15-year evidence has |t| >= 2;
  a "sharpened" panel (x1.5 distance from the base rate) is recorded as a graded shadow only; new buys whose
  own sell trigger is already met are excluded; past-dated catalysts are shown as already happened.
- 2026-09-27: screen starting weights tilted toward growth (momentum family 30%, earnings 22%, quality 20%,
  value 15%, reaction 6%, insider 5%, reversal 2%). New zero-weight candidates: net share issuance, asset
  growth, Piotroski F-score, 52-week-high proximity. Weight rule: candidates earn weight only at t >= 1.5
  (2.0 for these four); momentum and quality variants share their family's budget, whose total is judged on
  the established members only. Weights re-set at the next screen under the new rule.
- 2026-09-27: three more zero-weight candidates at the t >= 2.0 bar: "frog in the pan" momentum (momentum
  family), short interest days-to-cover (FINRA, tested from June 2021), and 10-K wording similarity
  ("Lazy Prices", SEC; tested once the one-time backfill of annual reports since 2014 is complete).
- 2026-09-27: macro agent gains a market & recession risk section (pipeline/market_risk.py): P(recession
  within 12 months) and P(S&P 500 10%+ pullback within 3 months) from small logistic models on FRED + S&P
  history, with out-of-sample accuracy, the indicator readings, and yield-curve / Chauvet-Piger benchmarks.
  Computed weekly, logged to state/market_risk_history.csv for grading; a jump to HIGH triggers a full macro
  run. Information only: it does not change position sizing.
- 2026-09-27: geopolitics. Macro agent gains a Geopolitics research theme (conflicts, chokepoints, OPEC+,
  export controls/sanctions, China-Taiwan, critical minerals, defense, U.S. policy shocks; always searched
  on restricted news/official domains), an oil-shock sector table from measured sensitivities, and new
  FRED series (OVX, trade and economic policy uncertainty). The risk dashboard adds the Geopolitical Risk
  Index, policy uncertainty, OVX and the oil futures curve; GPR and EPU are tested as pullback-model inputs
  and kept only if out-of-sample AUC improves by >= 0.01. Filings are scanned for where each company sells
  (with %) and makes/sources things; the portfolio critic checks that exposure against the macro risks.

- 2026-10-08: Daily account NAV (state/daily_account_nav.csv) now records the account *as intended*: the Oct 3 rebuild, delayed by a GitHub Actions outage from Mon Oct 5 to Tue Oct 6, is counted at Monday's open (state/adjusted_book.json: same shares sold, same dollars per buy). What actually executed in Alpaca is kept beside it (executed_* columns). Decided by the owner.

## Change log, 2026-10-16: reliability, statistics and reports
- NAV rows: `pipeline/prices.py` fills any close Yahoo lacks from Alpaca's IEX bars; the daily watch re-pulls Yahoo
  before giving up; rows that cannot be saved print why; a nightly catch-up (`navfill.yml`, 10:30 pm and 8 am ET)
  fills missing paper and Robinhood rows. IEX closes can differ from consolidated closes by a few cents; the backfill
  rewrites from Yahoo once it has settled.
- `pipeline/freeze.py` and `PARAMETERS.md`: dated log of every setting that shapes the picks; a test fails on an
  unlogged change. Results are judged from the latest entry onward.
- `pipeline/stats.py`: block bootstrap, random-portfolio test, CAPM and factor regression (ETF proxies), information
  ratio, sequential test, false-discovery and deflated-Sharpe helpers, Ledoit-Wolf covariance. None of it changes
  the live picks or sizes.
- `pipeline/report.py`: daily performance sheet and weekly statistics report (HTML in `reports/performance/`), with
  the go-live checklist (`GO_LIVE.md`). `pipeline/health.py`: emails only when something is missing or changed unlogged.
- Mistral removed from the last-resort fallback chain. Workflows use checkout v5, setup-python v6, ubuntu-24.04.
