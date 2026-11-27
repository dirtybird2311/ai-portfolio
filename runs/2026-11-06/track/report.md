# Performance, 2026-11-06

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | +0.46% | -2.09 |  |  | 20.8 | -6.16% | 0.29 |
| AI as recommended | -2.00% | -3.95 |  |  | 20.4 | -7.56% | -0.76 |
| Screen-only control | -5.40% | -6.28 |  |  | 17.0 | -7.39% | -2.75 |
| Equal-weight (same picks) | -2.23% | -4.37 |  |  | 24.2 | -8.05% | -0.69 |
| No-macro (top-rated, no PM) | -9.74% | -11.64 |  |  | 30.3 | -14.73% | -2.78 |
| SPY | -3.96% | -4.99 |  |  | 17.2 | -5.92% | -1.95 |
| SPTM (S&P 1500) | -3.60% | -4.6 |  |  | 16.9 | -5.6% | -1.8 |
| Macro tilts (sector ETFs) | +2.54% | 1.19 |  |  | 11.6 | -2.71% | 1.94 |
| Momentum rule (sector ETFs) | -0.12% | -1.05 |  |  | 12.7 | -4.35% | -0.02 |
| AI actual (after AI costs) | +0.21% | -2.28 |  |  | 20.9 | -6.27% | 0.19 |
| AI actual (after costs and est. tax) | -0.55% | -2.28 |  |  | 20.9 | -6.27% | 0.19 |

AI costs to date: $46.35. Estimated tax on realized short-term gains (Individual, at 24%): $53.54.
Drawdown rule: level 0 (relative drawdown -3.71% over 3 months).

Review checkpoint: 6-month review in about 5 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): +5.35 pts vs SPY
- Stock picks (stock team): -3.06 pts vs their sector ETFs
  - S&P 500: -4.84 pts
  - S&P 400: +2.35 pts
  - S&P 600: -0.56 pts

## Scorecards
```
{
 "by_conviction": {
  "1": {
   "avg_excess_%": -0.67,
   "n": 17
  },
  "2": {
   "avg_excess_%": -1.1,
   "n": 64
  },
  "3": {
   "avg_excess_%": 1.61,
   "n": 178
  },
  "4": {
   "avg_excess_%": 0.55,
   "n": 60
  },
  "5": {
   "avg_excess_%": 0.48,
   "n": 1
  }
 },
 "by_debate_winner": {
  "bear": {
   "avg_excess_%": -0.31,
   "n": 146
  },
  "bull": {
   "avg_excess_%": 0.45,
   "n": 78
  },
  "draw": {
   "avg_excess_%": 2.59,
   "n": 96
  }
 },
 "conviction_weighting": "not yet (4 graded rebuilds, 320 picks; need 6 and 40 with a 1-pt edge)",
 "signal_spread_1wk_%": {
  "momentum": {
   "avg_%": -0.79,
   "weeks": 6,
   "positive_weeks_%": 33
  },
  "earnings": {
   "avg_%": -0.56,
   "weeks": 6,
   "positive_weeks_%": 33
  },
  "reaction": {
   "avg_%": 0.13,
   "weeks": 6,
   "positive_weeks_%": 67
  },
  "industry": {
   "avg_%": -1.27,
   "weeks": 6,
   "positive_weeks_%": 50
  },
  "quality": {
   "avg_%": 0.84,
   "weeks": 6,
   "positive_weeks_%": 83
  },
  "value": {
   "avg_%": 1.17,
   "weeks": 6,
   "positive_weeks_%": 67
  },
  "insider": {
   "avg_%": 0.02,
   "weeks": 6,
   "positive_weeks_%": 50
  },
  "reversal": {
   "avg_%": 0.39,
   "weeks": 6,
   "positive_weeks_%": 50
  },
  "composite": {
   "avg_%": 0.13,
   "weeks": 6,
   "positive_weeks_%": 67
  },
  "resid_momentum": {
   "avg_%": -1.4,
   "weeks": 5,
   "positive_weeks_%": 20
  },
  "riskadj_momentum": {
   "avg_%": -1.66,
   "weeks": 5,
   "positive_weeks_%": 20
  },
  "high_52w": {
   "avg_%": 0.04,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "frog_momentum": {
   "avg_%": -1.73,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "low_vol": {
   "avg_%": 1.11,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "roic": {
   "avg_%": 0.63,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "stability": {
   "avg_%": 0.64,
   "weeks": 5,
   "positive_weeks_%": 60
  },
  "fscore": {
   "avg_%": 0.73,
   "weeks": 5,
   "positive_weeks_%": 80
  },
  "net_issuance": {
   "avg_%": 1.43,
   "weeks": 5,
   "positive_weeks_%": 80
  },
  "asset_growth": {
   "avg_%": 1.27,
   "weeks": 5,
   "positive_weeks_%": 80
  },
  "low_short": {
   "avg_%": -0.61,
   "weeks": 5,
   "positive_weeks_%": 40
  },
  "filing_similarity": {
   "avg_%": 0.45,
   "weeks": 5,
   "positive_weeks_%": 80
  },
  "cap_bumped_vs_replacements": {
   "avg_%": -3.78,
   "weeks": 4,
   "positive_weeks_%": 50
  }
 },
 "screen_signals_15yr": {
  "momentum": {
   "mean_ic": 0.0068,
   "t": 0.71,
   "months": 201,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "reaction": {
   "mean_ic": 0.0076,
   "t": 1.81,
   "months": 201,
   "verdict": "keep"
  },
  "quality": {
   "mean_ic": 0.0093,
   "t": 1.46,
   "months": 191,
   "verdict": "keep"
  },
  "industry": {
   "mean_ic": 0.0101,
   "t": 1.55,
   "months": 201,
   "verdict": "keep"
  },
  "reversal": {
   "mean_ic": 0.0082,
   "t": 1.06,
   "months": 201,
   "verdict": "keep"
  },
  "value": {
   "mean_ic": 0.0179,
   "t": 2.48,
   "months": 201,
   "verdict": "keep"
  },
  "resid_momentum": {
   "mean_ic": 0.0113,
   "t": 1.15,
   "months": 201,
   "verdict": "keep"
  },
  "riskadj_momentum": {
   "mean_ic": 0.0081,
   "t": 0.83,
   "months": 201,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "low_vol": {
   "mean_ic": -0.0064,
   "t": -0.48,
   "months": 201,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "roic": {
   "mean_ic": 0.0062,
   "t": 1.22,
   "months": 200,
   "verdict": "keep"
  },
  "stability": {
   "mean_ic": -0.0042,
   "t": -0.66,
   "months": 178,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "net_issuance": {
   "mean_ic": 0.002,
   "t": 0.35,
   "months": 200,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "asset_growth": {
   "mean_ic": 0.0048,
   "t": 0.94,
   "months": 179,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "fscore": {
   "mean_ic": 0.0086,
   "t": 1.65,
   "months": 179,
   "verdict": "keep"
  },
  "high_52w": {
   "mean_ic": -0.0043,
   "t": -0.38,
   "months": 201,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "frog_momentum": {
   "mean_ic": 0.0071,
   "t": 0.73,
   "months": 201,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
  },
  "low_short": {
   "mean_ic": 0.0174,
   "t": 1.87,
   "months": 64,
   "verdict": "keep"
  },
  "filing_similarity": {
   "mean_ic": 0.0035,
   "t": 0.95,
   "months": 140,
   "verdict": "adds nothing: candidate for removal (needs your approval)"
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
- Alpaca paper RS: book 1.32016 shares, Alpaca 1.40498

## Judge report card
5 rebuilds judged since 2026-09-26.
**Decision rule:** collecting — 1.3 months of decisions; first scheduled look at 3 months

IC = rank correlation between a forecast and the stock's return beyond its equal-weighted sector. 0 = no skill; +0.05 sustained is good; t >= 2 means unlikely to be luck. base_rate = the free statistics alone.

| Judge | 2w | 4w | 13w |
|---|---|---|---|
| base_rate | +0.003 (t 0.08, 3 dates) | +0.050 (t 0.31, 3 dates) | n/a |
| panel | +0.079 (t 1.74, 4 dates) | +0.156 (t 1.82, 3 dates) | n/a |
| panel_sharp | +0.107 (t 1.54, 3 dates) | +0.188 (t 2.64, 2 dates) | n/a |
| gemini_pro | +0.115 (t 3.57, 4 dates) | +0.132 (t 3.01, 3 dates) | n/a |
| gpt_sol | +0.040 (t 0.53, 4 dates) | +0.155 (t 1.82, 3 dates) | n/a |
| grok | +0.040 (t 0.79, 3 dates) | +0.171 (t 1.16, 2 dates) | n/a |
| kimi | +0.134 (t n/a, 1 dates) | +0.235 (t n/a, 1 dates) | n/a |
| replay_opus | +0.001 (t n/a, 1 dates) | +0.011 (t n/a, 1 dates) | n/a |
| sonnet | +0.050 (t 0.9, 4 dates) | +0.156 (t 1.77, 3 dates) | n/a |
| sonnet55 | n/a | n/a | n/a |
| sonnet_council | n/a | n/a | n/a |

**Brier score, 4 weeks** (lower is better): panel 0.24581, panel_sharp 0.24497, base_rate 0.24859, gemini_pro 0.24781, gpt_sol 0.24591, grok 0.25492, kimi 0.24713, replay_opus 0.24832, sonnet 0.24456, flat 0.24829
- Panel vs base rate (the key test: do the paid judges add anything?): +0.0028 (t 2.04, 240 forecasts)
- Base rate vs a flat guess: -0.0003 (t -0.19, 240 forecasts)

**Calibration, 4 weeks** (forecast vs what happened): 0-40%: said 38.6%, happened 0.0% (n 1); 40-45%: said 43.4%, happened 32.1% (n 56); 45-50%: said 47.5%, happened 52.4% (n 126); 50-55%: said 51.5%, happened 42.1% (n 57)

**Best judge combinations, 2w** (33 tested, so the best will look lucky). Live panel: +0.079 (t 1.73, 4 dates)
- kimi+sonnet: +0.110 (t n/a, 1 dates)
- gemini_pro+kimi+sonnet: +0.105 (t n/a, 1 dates)
- gemini_pro+kimi: +0.093 (t n/a, 1 dates)
- gemini_pro+replay_opus: +0.093 (t n/a, 1 dates)

**Best judge combinations, 4w** (33 tested, so the best will look lucky). Live panel: +0.155 (t 1.82, 3 dates)
- gpt_sol+kimi: +0.272 (t n/a, 1 dates)
- gpt_sol+kimi+sonnet: +0.269 (t n/a, 1 dates)
- gemini_pro+gpt_sol+kimi+sonnet: +0.269 (t n/a, 1 dates)
- gpt_sol+grok+kimi: +0.263 (t n/a, 1 dates)

**Bought vs passed over** (avg return beyond sector):
- 2w: bought 0.01% (n 36) vs passed -0.93% (n 284)
- 4w: bought -3.17% (n 25) vs passed -1.63% (n 215)
**Sold vs kept, 4 weeks after:** sold -13.5% (n 3) vs kept 6.17% (n 3)
**Critic:** approved buys -2.51% (n 29) vs flagged/held -6.86% (n 39), 4 weeks
**Catalysts:** 63.6% moved the expected way (11 graded)
**Headline labelers** (right direction over the next 2 trading days vs sector): claude-haiku-4-5-20251001 (live) 52.9% of 2650; nvidia:deepseek-ai/deepseek-v4.1-flash 33.3% of 18
**Process errors, last run (2026-11-01):** invalid_citations 0, judge_replies_unusable 105, uncited_adjustments 0, panel_failed 0, judge_disagreements 0, missing_exit_condition 0, model_fallbacks 322

**Macro agent vs the momentum rule** (sector ranking skill, IC):
- 4w: macro +0.090 (t 0.35, 3 dates); momentum rule -0.112 (t -2.31, 3 dates); macro vs base rate (Brier) +0.0055 (t 0.52, 66 forecasts)
- 12-month macro rule: collecting — 1.3 of 12 months