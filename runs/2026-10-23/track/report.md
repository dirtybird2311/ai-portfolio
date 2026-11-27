# Performance, 2026-10-23

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | +4.92% |  |  |  | 14.8 | -1.28% |  |
| AI as recommended | +3.92% |  |  |  | 14.5 | -1.32% |  |
| Screen-only control | +0.57% |  |  |  | 10.8 | -1.55% |  |
| Equal-weight (same picks) | +2.94% |  |  |  | 16.1 | -1.68% |  |
| No-macro (top-rated, no PM) | +2.20% |  |  |  | 17.6 | -2.2% |  |
| SPY | -0.74% |  |  |  | 9.7 | -2.45% |  |
| SPTM (S&P 1500) | -0.65% |  |  |  | 9.8 | -2.4% |  |
| Macro tilts (sector ETFs) | +3.09% |  |  |  | 8.4 | -0.82% |  |
| Momentum rule (sector ETFs) | +2.73% |  |  |  | 6.5 | -0.97% |  |
| AI actual (after AI costs) | +4.78% |  |  |  | 14.9 | -1.29% |  |
| AI actual (after costs and est. tax) | +4.08% |  |  |  | 14.9 | -1.29% |  |

AI costs to date: $36.49. Estimated tax on realized short-term gains (Individual, at 24%): $46.55.
Drawdown rule: level 0 (relative drawdown -0.25% over 3 months).

Review checkpoint: 6-month review in about 6 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): +4.92 pts vs SPY
- Stock picks (stock team): -0.31 pts vs their sector ETFs
  - S&P 500: -1.21 pts
  - S&P 600: -1.00 pts
  - S&P 400: +1.92 pts

## Scorecards
```
{
 "by_conviction": {
  "1": {
   "avg_excess_%": -0.96,
   "n": 14
  },
  "2": {
   "avg_excess_%": -1.67,
   "n": 49
  },
  "3": {
   "avg_excess_%": 0.98,
   "n": 145
  },
  "4": {
   "avg_excess_%": 0.43,
   "n": 32
  }
 },
 "by_debate_winner": {
  "bear": {
   "avg_excess_%": -0.76,
   "n": 118
  },
  "bull": {
   "avg_excess_%": -0.07,
   "n": 47
  },
  "draw": {
   "avg_excess_%": 2.05,
   "n": 75
  }
 },
 "conviction_weighting": "not yet (3 graded rebuilds, 240 picks; need 6 and 40 with a 1-pt edge)",
 "signal_spread_1wk_%": {
  "momentum": {
   "avg_%": -0.77,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "earnings": {
   "avg_%": -0.46,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "reaction": {
   "avg_%": 0.02,
   "weeks": 5,
   "positive_weeks_%": 60
  },
  "industry": {
   "avg_%": -1.87,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "quality": {
   "avg_%": 1.19,
   "weeks": 5,
   "positive_weeks_%": 100
  },
  "value": {
   "avg_%": 1.35,
   "weeks": 5,
   "positive_weeks_%": 60
  },
  "insider": {
   "avg_%": 0.03,
   "weeks": 5,
   "positive_weeks_%": 60
  },
  "reversal": {
   "avg_%": 0.17,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "composite": {
   "avg_%": 0.12,
   "weeks": 5,
   "positive_weeks_%": 60
  },
  "resid_momentum": {
   "avg_%": -1.53,
   "weeks": 4,
   "positive_weeks_%": 25
  },
  "riskadj_momentum": {
   "avg_%": -1.94,
   "weeks": 4,
   "positive_weeks_%": 25
  },
  "high_52w": {
   "avg_%": 0.54,
   "weeks": 4,
   "positive_weeks_%": 50
  },
  "frog_momentum": {
   "avg_%": -2.16,
   "weeks": 4,
   "positive_weeks_%": 25
  },
  "low_vol": {
   "avg_%": 1.45,
   "weeks": 4,
   "positive_weeks_%": 50
  },
  "roic": {
   "avg_%": 1.07,
   "weeks": 4,
   "positive_weeks_%": 50
  },
  "stability": {
   "avg_%": 0.96,
   "weeks": 4,
   "positive_weeks_%": 75
  },
  "fscore": {
   "avg_%": 1.04,
   "weeks": 4,
   "positive_weeks_%": 100
  },
  "net_issuance": {
   "avg_%": 2.1,
   "weeks": 4,
   "positive_weeks_%": 100
  },
  "asset_growth": {
   "avg_%": 1.55,
   "weeks": 4,
   "positive_weeks_%": 75
  },
  "low_short": {
   "avg_%": -0.64,
   "weeks": 4,
   "positive_weeks_%": 50
  },
  "filing_similarity": {
   "avg_%": 0.62,
   "weeks": 4,
   "positive_weeks_%": 75
  },
  "cap_bumped_vs_replacements": {
   "avg_%": -1.91,
   "weeks": 3,
   "positive_weeks_%": 67
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
  "graded": 8,
  "hit_rate_%": 50.0
 }
}
```

## Brokerage cross-check differences (Robinhood exports / Alpaca paper)
- Alpaca paper PBF: book 9.71376 shares, Alpaca 9.87439
- Alpaca paper RS: book 2.36866 shares, Alpaca 2.45349

## Judge report card
4 rebuilds judged since 2026-09-26.
**Decision rule:** collecting — 0.9 months of decisions; first scheduled look at 3 months

IC = rank correlation between a forecast and the stock's return beyond its equal-weighted sector. 0 = no skill; +0.05 sustained is good; t >= 2 means unlikely to be luck. base_rate = the free statistics alone.

| Judge | 2w | 4w | 13w |
|---|---|---|---|
| base_rate | +0.003 (t 0.08, 3 dates) | n/a | n/a |
| panel | +0.100 (t 1.73, 3 dates) | n/a | n/a |
| panel_sharp | +0.150 (t 1.62, 2 dates) | n/a | n/a |
| gemini_pro | +0.137 (t 4.05, 3 dates) | n/a | n/a |
| gpt_sol | +0.021 (t 0.21, 3 dates) | n/a | n/a |
| grok | +0.042 (t 0.47, 2 dates) | n/a | n/a |
| kimi | +0.134 (t n/a, 1 dates) | n/a | n/a |
| replay_opus | +0.001 (t n/a, 1 dates) | n/a | n/a |
| sonnet | +0.093 (t 1.81, 3 dates) | n/a | n/a |

**Best judge combinations, 2w** (33 tested, so the best will look lucky). Live panel: +0.100 (t 1.72, 3 dates)
- gemini_pro+sonnet: +0.123 (t 4.02, 3 dates)
- kimi+sonnet: +0.110 (t n/a, 1 dates)
- gemini_pro+kimi+sonnet: +0.105 (t n/a, 1 dates)
- gemini_pro+gpt_sol+sonnet: +0.100 (t 1.72, 3 dates)

**Bought vs passed over** (avg return beyond sector):
- 2w: bought 0.04% (n 25) vs passed -0.27% (n 215)
**Catalysts:** 66.7% moved the expected way (9 graded)
**Headline labelers** (right direction over the next 2 trading days vs sector): claude-haiku-4-5-20251001 (live) 52.9% of 2066; nvidia:deepseek-ai/deepseek-v4.1-flash 33.3% of 18
**Process errors, last run (2026-10-17):** invalid_citations 0, judge_replies_unusable 97, uncited_adjustments 0, panel_failed 0, judge_disagreements 2, missing_exit_condition 0, model_fallbacks 263

**Macro agent:** no graded macro runs yet