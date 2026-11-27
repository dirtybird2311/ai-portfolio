# Improvements and to-do list

Living list of changes we want to make to the code and the process. Newest decisions go in the status column; move finished items to "Done" with the date.

Status key: **Ready** = agreed, not built · **Proposed** = offered, waiting on the owner · **Parked** = the owner said wait · **Open** = needs a decision or information

## Priority order (set Oct 14; items 1-4 built Oct 16, see the status column)

1. **Fix the NAV row bug** (1.3, 6.1, 1.1, 1.2): the daily watch succeeds but saves no Yahoo-priced row, so every day needs a manual backfill. Find the cause, add a second price source (Alpaca), retry later in the evening, and have the backfill cover the Robinhood files. The reports depend on this data being complete.
2. **Parameter freeze log** (6.7): a dated record of every change to weights, bars, caps and sleeve size, with a baseline of today's values. Small to start, and it keeps later results readable.
3. **Random-portfolio test per rebuild** (3.1 / 7.1): the fastest honest answer to skill vs luck.
4. **Performance and statistics reports** (2.5): see below.
5. Factor regression, block bootstrap, information ratio (7.2, 7.3, 7.4), which feed the reports.
6. Multiple-testing correction and rank IC on the signal screen (7.5, 7.6).
7. Better-decision methods, starting with signal shrinkage, orthogonalized signals, calibration rescale and covariance shrinkage (section 8). Test each against the random-portfolio baseline before adopting.
8. Written go-live rules (6.6).
9. Everything else, in the order listed in the sections below.

## 1. Reliability and data capture

| # | Item | Why | Status |
|---|---|---|---|
| 1.1 | Daily watch retries the NAV snapshot later in the evening when Yahoo closes haven't settled | The watch saved no NAV rows on Oct 9, 12, 13 and 14; each needed a manual backfill | **Done Oct 16**: the watch re-pulls Yahoo (up to 2 retries) and fills gaps from Alpaca; a nightly catch-up (10:30 pm and 8 am ET) fills any row still missing |
| 1.2 | Backfill (navfill) also covers the two Robinhood NAV files | Robinhood rows stop at Oct 12 because only the watch writes them | **Done Oct 16**: the backfill and nightly catch-up now cover both Robinhood files |
| 1.3 | **Top priority.** Find out why the watch saves no Yahoo-priced rows (run succeeds, row missing) | Job logs aren't readable from the sandbox, so the cause is unconfirmed; add a printed reason when a snapshot is skipped | **Mitigated Oct 16**: rows that cannot be saved now print the reason (which ticker had no price for which day). Root cause still unconfirmed; check the next watch log |
| 1.4 | Data-health alarms (stale prices, missing rows, failed fetches) | Silent gaps are only found when asked | Partly done: `pipeline/health.py` (see 6.8). Stale-price checks still open |
| 1.5 | Orders workflow is best-effort and can be skipped; add a catch-up run | Skipped during the Oct 5 GitHub outage | Open |
| 1.6 | Drop Mistral from the last-resort list and the connection test | It keeps failing the connection test | **Done Oct 16**: removed from the last-resort chain; test updated |

## 2. Records and reporting

| # | Item | Why | Status |
|---|---|---|---|
| 2.1 | Weekly report scorecard uses the adjusted record (Monday-open rebuild) | Adjusted is the official record; the report still shows actual vs recommended | Proposed |
| 2.2 | Confirm real Robinhood share counts per account, update `state/external_books.json` | Counts are assumed from my lists | Open (needs the owner) |
| 2.3 | Plots of paper adjusted / executed / SPY / Robinhood in the weekly report | the owner wants visuals wherever they help | Partly done: charts are in the new performance and statistics reports; the weekly scorecard email itself is unchanged |
| 2.5 | Performance and statistics reports: daily one-page performance sheet (NAV, vs SPY, controls, Robinhood) and a weekly stats report (random-portfolio rank, factor/beta, block-bootstrap range, information ratio, drawdown), each with plots | the owner asked Oct 14; gives one place for the numbers and the evidence | **Done Oct 16**: `python -m pipeline.report` (daily) and `--weekly`; Actions > Statistics report; saved in `reports/performance/` |
| 2.4 | Go-live readiness section in the weekly report | Gives a clear signal for when to move real money | **Done Oct 16** as the go-live checklist in the weekly statistics report (see 6.6) |

## 3. Telling signal from noise

| # | Item | Why | Status |
|---|---|---|---|
| 3.1 | Random-portfolio bootstrap per rebuild (does the pick beat random portfolios from the same universe?) | One portfolio's returns need decades to confirm a few points of alpha; this gives an answer much sooner | **Done Oct 16** (see 7.1) |
| 3.2 | Resample the history backtest | Same reason | Proposed |
| 3.3 | Per-call grading of the debaters | See which agents add value | Proposed |
| 3.4 | Paired controls (screen-only, equal-weight, no-macro) kept in the scorecard | Isolates what each layer adds | In place; keep |

## 4. Portfolio logic

| # | Item | Why | Status |
|---|---|---|---|
| 4.1 | Turnover buffer around the 50% rebuild cap | The Oct 3 rebuild came in at 74% and was blocked | Parked |
| 4.2 | Market-risk sizing guard | Risk model reads recession 4%, pullback 8%; no sizing action tied to it | Parked |
| 4.3 | Cash-based profitability measure | Better quality signal | Parked |
| 4.4 | Survivorship-bias fix and a full-screen backtest | Backtest currently flatters results | Parked |

## 5. Infrastructure and cost

| # | Item | Why | Status |
|---|---|---|---|
| 5.1 | Watch GitHub free minutes (about 900 of 2,000 in a normal month; September about 1,325) | A heavy month or an outage can skip runs | Monitor |
| 5.2 | Self-hosted runner (Oracle Always Free VM) or a small spending limit | Only if minutes or outages become a recurring problem | Parked |
| 5.3 | Workflows warn that Node 20 actions are being forced to Node 24, and ubuntu-latest moves to Ubuntu 26 on Oct 19, 2026 | Check tests pass after the migration; bump action versions | **Done Oct 16**: checkout v5, setup-python v6, runners pinned to ubuntu-24.04. `actions/cache` is still v4 (warning only) |

## 6. New ideas (added Oct 14)

| # | Item | Why | Status |
|---|---|---|---|
| 6.1 | Second price source (Alpaca market data) when Yahoo closes are missing | Likely fixes the missing NAV rows at the root, and lets the watch save the row the same evening | **Done Oct 16**: `pipeline/prices.py` (Alpaca IEX closes fill a day Yahoo lacks; the nightly backfill later rewrites from Yahoo) |
| 6.2 | Robinhood order sheet generated after each rebuild: whole-share buys and sells, diffed against what the real accounts hold, with limit prices from live quotes | Replaces the hand-built lists and price-by-price checks | Proposed |
| 6.3 | Fill-quality log: planned price vs actual fill (paper and Robinhood) | Shows what late or limit fills cost; today's gap between adjusted and executed is the example | Proposed |
| 6.4 | Risk columns in the report: beta to SPY, alpha, tracking error, max drawdown | A +2.5 point lead on a day SPY fell 1.1% is partly market exposure; beta-adjusted alpha separates the two | **Done Oct 16**: beta, alpha, tracking error, information ratio and max drawdown are in the weekly statistics report |
| 6.5 | Prediction log: every rebuild's picks scored against SPY and the controls at 1, 3 and 6 months | Builds the sample size that daily returns can't | Proposed |
| 6.6 | Written go-live rules before any more real money: minimum number of rebuilds, bootstrap percentile, max drawdown, cost check | Stops the decision being made on a good week | **Done Oct 16** as a proposal: 9-rule checklist with thresholds in `GO_LIVE` (pipeline/report.py) and GO_LIVE.md; the owner to confirm or change the thresholds |
| 6.7 | **Priority 2.** Parameter freeze log: any change to weights, bars or caps is dated and justified | Prevents tuning to a few weeks of results; results are scored only from the last change onward; bug fixes don't count as changes | **Done Oct 16**: `PARAMETERS.md`, baseline of 40 settings, `python -m pipeline.freeze`, and a test that fails on an unlogged change |
| 6.8 | Exception-only alerts: failed job, missing NAV row, price gap, AI spend over a per-run cap | Replaces asking "anything new?" | **Done Oct 16**: `pipeline/health.py` emails only when a NAV row or the watch run is missing or a setting changed unlogged |
| 6.9 | Published dashboard page (NAV vs SPY for all books) refreshed by the watch | One link instead of asking for plots | Partly done: a self-contained HTML page is saved to the repo each night and week; not yet a published link that refreshes itself |
| 6.10 | Earnings-date check before a trade | Avoids buying into a report by accident | Open |
| 6.11 | Taxable-account tracking for Robinhood account 2 (holding periods, wash-sale window across both accounts) | The Roth has no tax issue; account 2 does | Open |

## 7. Statistical methods to add (added Oct 14)

Plan: new tests go in a new module `pipeline/stats.py`, called by the reports, out of the live trading path. Existing statistics: IC and t-stat (`history.py`), signal bars and weights (`screen.py`), judge IC and Brier (`ledger.py`), scorecards and metrics (`track.py`), market-risk model (`market_risk.py`). The earlier bootstrap of daily excess returns was a one-off analysis, not repo code.

| # | Method | What it answers | Status |
|---|---|---|---|
| 7.1 | Random-portfolio test (Monte Carlo) per rebuild | Do our picks beat thousands of random portfolios drawn from the same universe, with the same sector and size limits? | **Done Oct 16**: three tests per rebuild: (1) our picks vs random picks from the whole universe, (2) our picks vs random picks from the shortlist (same sectors), (3) the whole shortlist vs random universe picks |
| 7.2 | CAPM / Fama-French factor regression of daily excess returns | How much of the lead is market beta, value, size or momentum rather than stock picking? | **Done Oct 16**: CAPM always; size/value/momentum regression with ETF proxies once there are 20 trading days |
| 7.3 | Block bootstrap (resample runs of days, not single days) | Daily returns are autocorrelated, so the plain bootstrap overstates confidence | **Done Oct 16**: 3-day block bootstrap, in the report |
| 7.4 | Information ratio and t-stat of daily active return | One number for "lead per unit of risk"; t above 2 needs far more days than we have | **Done Oct 16**: in the report |
| 7.5 | Multiple-testing correction on the signal screen (false discovery rate, deflated Sharpe) | We test many signals; some will clear the bar by luck | Built (`stats.benjamini_hochberg`, `stats.deflated_sharpe`, tested); not yet applied to the signal screen's evidence |
| 7.6 | Rank IC (information coefficient) of each signal per rebuild, with a rolling average | Does a signal rank stocks in the right order, independent of portfolio construction? | Partly built: monthly IC with t-stat in `pipeline/history.py` (backtest) and `_ic_series` in `pipeline/ledger.py` (AI judges); no per-rebuild rolling view yet |
| 7.7 | Shrinkage on signal weights (James-Stein / empirical Bayes) | Pulls noisy signal weights toward zero so one lucky signal doesn't dominate | Not built |
| 7.8 | Sequential test (SPRT) against a go-live threshold | Says when evidence is enough to stop or go, without peeking bias | **Done Oct 16**: sequential test on daily lead, looking for 0.04% a day |
| 7.9 | Calibration check of the AI's confidence (Brier score / reliability plot) | When the agents say 70%, are they right about 70% of the time? | Partly built: Brier skill in the monthly evaluation (`pipeline/ledger.py`); no reliability plot yet |
| 7.10 | Walk-forward backtest with a purge gap | Honest out-of-sample numbers; guards against look-ahead | Proposed |
| 7.11 | Covariance shrinkage (Ledoit-Wolf) for position sizing and risk | Stable risk estimates from a short history | Built (`stats.ledoit_wolf`, tested); not used by sizing (changes decisions; see section 8) |
| 7.12 | Look-back agent (`python -m pipeline.lookback`) | After each weekly run, a read-only record in `reports/lookback/latest.md` of which shortlist names did well, which inputs (judge probability, base rate, composite, signal families, sector) lined up with the returns, the biggest hits and misses beside the judges' stated drivers, and a model-written read marked as hypotheses. Raw material for retraining the judges once the go-live evidence exists | **Done Oct 16** (changes no pick or setting; acting on it waits for 60 trading days and 4+ rebuilds, and goes through the freeze log) |

## 8. Methods that could improve the decisions themselves (added Oct 14)

Adopt one at a time, each tested against the random-portfolio baseline and logged in the freeze log. All of them can overfit if tuned on a short history.

| # | Method | What it changes | Status |
|---|---|---|---|
| 8.1 | Signal shrinkage (ridge / elastic-net weights) | Fits signal weights with a penalty so noisy signals shrink toward zero; tests the hand-set weights against data | Proposed |
| 8.2 | Orthogonalize signals | Removes overlap between signals that are the same bet (cheap, profitable, quality) so one idea isn't counted three times | Proposed |
| 8.3 | Signal decay and turnover-aware blending | Favors signals whose edge fades slowly, since they cost less to trade | Proposed |
| 8.4 | Covariance shrinkage (Ledoit-Wolf) | Stable risk estimates from short history for sizing (same as 7.11) | Proposed |
| 8.5 | Risk-parity or shrunk mean-variance sizing | Sizes by risk contribution, not conviction alone | Open |
| 8.6 | Kelly-fraction cap on position size | Limits how much a pick's expected edge can size it | Open |
| 8.7 | Regime detection (hidden Markov model) | Changes exposure in calm vs stressed markets; builds on `market_risk.py`; risky on small samples | Open |
| 8.8 | Calibration rescale of the AI's confidence | If agents say 70% and are right 55%, rescale before it affects sizing | Proposed |
| 8.9 | Bayesian shrinkage of expected returns toward the sector average | Stops one strong signal from dominating a pick | Proposed |
| 8.10 | Hierarchical model by sector | Shares information across stocks in a sector so thin data isn't over-trusted | Open |
| 8.11 | Cost-aware optimization | Trade only when expected gain beats cost (relates to the turnover buffer, 4.1) | Open |
| 8.12 | Event-study checks on earnings and news reactions | Tests whether those signals add anything | Open |

## Done

- 2026-11-09: Improvement plan ("Beating SPY", planning doc) steps 1 and 2. Step 1 (live sizing, in the freeze log): inverse-volatility sizing with the judges' edge no longer scaling weights (`SIZE_BY_EDGE`), 15-20 names at 3-10%, narrower sector ranges recomputed from the stored tilts, buy edge +2. Step 2: paper orders queue at Alpaca for the open from pre-open runs, a wrong-account guard, and `pipeline/brokerimport.py` (Robinhood and Schwab activity files, carried cost). Next in the plan: screen backtest with shrinkage (8.1, 8.2, 3.2), then judge calibration and per-stage grading (8.8, 3.3).
- 2026-11-05: Theme cap (25%) and upcoming-events calendar for the PM and macro view; NAV fixes (full exits in the as-planned record, record-vs-executed gap check).
- 2026-11-02/03: Investor council test (hidden council dossier, shadow judge, sandbox portfolios as shadow books); Discord notifications; order sheet modes for new cash accounts and fractional buys; Kimi K3 removed.
- 2026-10-16: NAV row fix (Alpaca fallback, retries, nightly catch-up, skip reasons), Robinhood backfill, freeze log, `pipeline/stats.py`, performance and statistics reports, health alerts, Mistral dropped, Node 24 action versions. Section 8 methods (change the picks) and several others below were deliberately not built; see each item's status.
- 2026-10: Daily NAV vs SPY; whole-account NAV with adjusted record; Robinhood NAV tracking; account NAV backfill workflow; fill-date fix (fills dated by New York trading day).
