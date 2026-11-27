# Performance, 2026-10-16

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | -99.55% |  |  |  | 424.3 | -99.57% |  |
| AI as recommended | -100.00% |  |  |  | 425.9 | -100.0% |  |
| Screen-only control | -100.00% |  |  |  | 425.1 | -100.0% |  |
| Equal-weight (same picks) | -100.00% |  |  |  | 426.0 | -100.0% |  |
| No-macro (top-rated, no PM) | -100.00% |  |  |  | 426.1 | -100.0% |  |
| SPY | -100.00% |  |  |  | 424.6 | -100.0% |  |
| SPTM (S&P 1500) | -100.00% |  |  |  | 424.6 | -100.0% |  |
| Macro tilts (sector ETFs) | -100.00% |  |  |  | 425.3 | -100.0% |  |
| Momentum rule (sector ETFs) | -100.01% |  |  |  | 425.1 | -100.01% |  |
| AI actual (after AI costs) | -99.83% |  |  |  | 425.4 | -99.84% |  |
| AI actual (after costs and est. tax) | -99.94% |  |  |  | 425.4 | -99.84% |  |

AI costs to date: $28.81. Estimated tax on realized short-term gains (Individual, at 24%): $10.50.
Drawdown rule: level 0 (relative drawdown nan% over 3 months).

Review checkpoint: 6-month review in about 6 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): +nan pts vs SPY
- Stock picks (stock team): +1.53 pts vs their sector ETFs

## Scorecards
```
{
 "by_conviction": {
  "1": {
   "avg_excess_%": -1.66,
   "n": 12
  },
  "2": {
   "avg_excess_%": -3.73,
   "n": 31
  },
  "3": {
   "avg_excess_%": 0.42,
   "n": 98
  },
  "4": {
   "avg_excess_%": -0.58,
   "n": 19
  }
 },
 "by_debate_winner": {
  "bear": {
   "avg_excess_%": -1.79,
   "n": 81
  },
  "bull": {
   "avg_excess_%": -0.81,
   "n": 30
  },
  "draw": {
   "avg_excess_%": 1.3,
   "n": 49
  }
 },
 "conviction_weighting": "not yet (2 graded rebuilds, 160 picks; need 6 and 40 with a 1-pt edge)",
 "signal_spread_1wk_%": {
  "momentum": {
   "avg_%": 0.0,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "earnings": {
   "avg_%": 0.54,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "reaction": {
   "avg_%": 0.23,
   "weeks": 3,
   "positive_weeks_%": 100
  },
  "industry": {
   "avg_%": -0.4,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "quality": {
   "avg_%": 0.6,
   "weeks": 3,
   "positive_weeks_%": 100
  },
  "value": {
   "avg_%": -0.37,
   "weeks": 3,
   "positive_weeks_%": 33
  },
  "insider": {
   "avg_%": 0.01,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "reversal": {
   "avg_%": 0.17,
   "weeks": 3,
   "positive_weeks_%": 33
  },
  "composite": {
   "avg_%": 0.22,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "resid_momentum": {
   "avg_%": -0.16,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "riskadj_momentum": {
   "avg_%": -0.91,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "high_52w": {
   "avg_%": -0.75,
   "weeks": 2,
   "positive_weeks_%": 0
  },
  "frog_momentum": {
   "avg_%": -0.82,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "low_vol": {
   "avg_%": -1.05,
   "weeks": 2,
   "positive_weeks_%": 0
  },
  "roic": {
   "avg_%": 0.69,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "stability": {
   "avg_%": 0.01,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "fscore": {
   "avg_%": 0.88,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "net_issuance": {
   "avg_%": 1.0,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "asset_growth": {
   "avg_%": 0.26,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "low_short": {
   "avg_%": 0.92,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "filing_similarity": {
   "avg_%": 0.23,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "cap_bumped_vs_replacements": {
   "avg_%": 1.84,
   "weeks": 1,
   "positive_weeks_%": 100
  }
 },
 "screen_signals_15yr": {
  "momentum": {
   "mean_ic": 0.0062,
   "t": 0.65,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "reaction": {
   "mean_ic": 0.0087,
   "t": 1.33,
   "months": 199,
   "verdict": "keep"
  },
  "quality": {
   "mean_ic": 0.01,
   "t": 1.53,
   "months": 189,
   "verdict": "keep"
  },
  "industry": {
   "mean_ic": 0.0091,
   "t": 1.42,
   "months": 199,
   "verdict": "keep"
  },
  "reversal": {
   "mean_ic": 0.0069,
   "t": 0.88,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "value": {
   "mean_ic": 0.0181,
   "t": 2.54,
   "months": 199,
   "verdict": "keep"
  },
  "resid_momentum": {
   "mean_ic": 0.0108,
   "t": 1.1,
   "months": 199,
   "verdict": "keep"
  },
  "riskadj_momentum": {
   "mean_ic": 0.0073,
   "t": 0.76,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "low_vol": {
   "mean_ic": -0.0071,
   "t": -0.53,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "roic": {
   "mean_ic": 0.0058,
   "t": 1.15,
   "months": 198,
   "verdict": "keep"
  },
  "stability": {
   "mean_ic": -0.0056,
   "t": -0.86,
   "months": 176,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "net_issuance": {
   "mean_ic": 0.001,
   "t": 0.18,
   "months": 198,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "asset_growth": {
   "mean_ic": 0.0031,
   "t": 0.61,
   "months": 177,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "fscore": {
   "mean_ic": 0.0074,
   "t": 1.39,
   "months": 177,
   "verdict": "keep"
  },
  "high_52w": {
   "mean_ic": -0.0047,
   "t": -0.41,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "frog_momentum": {
   "mean_ic": 0.0064,
   "t": 0.67,
   "months": 199,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "low_short": {
   "mean_ic": 0.0178,
   "t": 1.86,
   "months": 62,
   "verdict": "keep"
  },
  "filing_similarity": {
   "mean_ic": 0.004,
   "t": 1.09,
   "months": 138,
   "verdict": "keep"
  }
 },
 "macro_predictions": {
  "graded": 5,
  "hit_rate_%": 60.0
 }
}
```

## Brokerage cross-check differences (Robinhood exports / Alpaca paper)
- Alpaca paper RS: book 1.4526 shares, Alpaca 1.53742

## Judge report card
3 rebuilds judged since 2026-09-26.
**Decision rule:** collecting — 0.7 months of decisions; first scheduled look at 3 months

IC = rank correlation between a forecast and the stock's return beyond its equal-weighted sector. 0 = no skill; +0.05 sustained is good; t >= 2 means unlikely to be luck. base_rate = the free statistics alone.

| Judge | 2w | 4w | 13w |
|---|---|---|---|
| base_rate | -0.027 (t -1.04, 2 dates) | n/a | n/a |
| panel | +0.112 (t 1.15, 2 dates) | n/a | n/a |
| panel_sharp | +0.243 (t n/a, 1 dates) | n/a | n/a |
| gemini_pro | +0.168 (t 7.66, 2 dates) | n/a | n/a |
| gpt_sol | +0.032 (t 0.18, 2 dates) | n/a | n/a |
| grok | -0.046 (t n/a, 1 dates) | n/a | n/a |
| kimi | n/a | n/a | n/a |
| replay_opus | +0.001 (t n/a, 1 dates) | n/a | n/a |
| sonnet | +0.073 (t 0.89, 2 dates) | n/a | n/a |

**Best judge combinations, 2w** (18 tested, so the best will look lucky). Live panel: +0.113 (t 1.15, 2 dates)
- gemini_pro+sonnet: +0.128 (t 2.47, 2 dates)
- gemini_pro+gpt_sol: +0.119 (t 1.39, 2 dates)
- gemini_pro+gpt_sol+sonnet: +0.113 (t 1.15, 2 dates)
- gemini_pro+replay_opus: +0.093 (t n/a, 1 dates)

**Bought vs passed over** (avg return beyond sector):
- 2w: bought -0.12% (n 14) vs passed -0.39% (n 146)
**Catalysts:** 62.5% moved the expected way (8 graded)
**Headline labelers** (right direction over the next 2 trading days vs sector): claude-haiku-4-5-20251001 (live) 52.7% of 1546; nvidia:deepseek-ai/deepseek-v4.1-flash 33.3% of 18
**Process errors, last run (2026-10-03):** invalid_citations 0, judge_replies_unusable 27, uncited_adjustments 0, panel_failed 0, judge_disagreements 0, missing_exit_condition 0, model_fallbacks 158

**Macro agent:** no graded macro runs yet