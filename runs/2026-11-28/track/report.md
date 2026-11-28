# Performance, 2026-11-28

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | +2.55% | -1.81 |  |  | 20.8 | -6.68% | 0.81 |
| AI as recommended | +0.15% | -3.37 |  |  | 20.8 | -8.09% | 0.15 |
| Screen-only control | -9.90% | -11.39 |  |  | 19.2 | -14.84% | -3.08 |
| Equal-weight (same picks) | -0.59% | -3.43 |  |  | 24.4 | -9.14% | -0.02 |
| No-macro (top-rated, no PM) | -10.16% | -11.04 |  |  | 30.0 | -14.98% | -1.94 |
| SPY | -4.87% | -5.7 |  |  | 22.9 | -11.46% | -1.16 |
| SPTM (S&P 1500) | -4.40% | -5.28 |  |  | 22.3 | -10.95% | -1.07 |
| Macro tilts (sector ETFs) | +3.54% | 0.55 |  |  | 14.0 | -6.0% | 1.53 |
| Momentum rule (sector ETFs) | +0.38% | -3.03 |  |  | 15.1 | -7.96% | 0.22 |
| AI actual (after AI costs) | +2.18% | -2.03 |  |  | 21.0 | -6.91% | 0.71 |
| AI actual (after costs and est. tax) | +0.90% | -2.03 |  |  | 21.0 | -6.91% | 0.71 |

AI costs to date: $58.83. Estimated tax on realized short-term gains (Individual, at 24%): $104.84.
Drawdown rule: level 0 (relative drawdown -2.45% over 3 months).

Review checkpoint: 6-month review in about 4 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): +6.86 pts vs SPY
- Stock picks (stock team): -1.62 pts vs their sector ETFs
  - S&P 500: -2.16 pts
  - S&P 600: +0.16 pts
  - S&P 400: +1.43 pts

## Scorecards
```
{
 "by_conviction": {
  "1": {
   "avg_excess_%": -2.42,
   "n": 19
  },
  "2": {
   "avg_excess_%": -0.99,
   "n": 84
  },
  "3": {
   "avg_excess_%": 0.66,
   "n": 218
  },
  "4": {
   "avg_excess_%": -0.01,
   "n": 71
  },
  "5": {
   "avg_excess_%": 0.48,
   "n": 1
  }
 },
 "by_debate_winner": {
  "bear": {
   "avg_excess_%": -1.0,
   "n": 186
  },
  "bull": {
   "avg_excess_%": -0.3,
   "n": 96
  },
  "draw": {
   "avg_excess_%": 2.08,
   "n": 111
  }
 },
 "conviction_weighting": "not yet (5 graded rebuilds, 393 picks; need 6 and 40 with a 1-pt edge)",
 "signal_spread_1wk_%": {
  "momentum": {
   "avg_%": -0.17,
   "weeks": 8,
   "positive_weeks_%": 50
  },
  "earnings": {
   "avg_%": -0.38,
   "weeks": 8,
   "positive_weeks_%": 38
  },
  "reaction": {
   "avg_%": 0.21,
   "weeks": 8,
   "positive_weeks_%": 75
  },
  "industry": {
   "avg_%": -0.87,
   "weeks": 8,
   "positive_weeks_%": 50
  },
  "quality": {
   "avg_%": 0.82,
   "weeks": 8,
   "positive_weeks_%": 75
  },
  "value": {
   "avg_%": 1.18,
   "weeks": 8,
   "positive_weeks_%": 75
  },
  "insider": {
   "avg_%": -0.07,
   "weeks": 8,
   "positive_weeks_%": 38
  },
  "reversal": {
   "avg_%": 0.18,
   "weeks": 8,
   "positive_weeks_%": 50
  },
  "composite": {
   "avg_%": 0.44,
   "weeks": 8,
   "positive_weeks_%": 75
  },
  "resid_momentum": {
   "avg_%": -0.64,
   "weeks": 7,
   "positive_weeks_%": 43
  },
  "riskadj_momentum": {
   "avg_%": -0.74,
   "weeks": 7,
   "positive_weeks_%": 43
  },
  "high_52w": {
   "avg_%": 0.68,
   "weeks": 7,
   "positive_weeks_%": 43
  },
  "frog_momentum": {
   "avg_%": -0.82,
   "weeks": 7,
   "positive_weeks_%": 57
  },
  "low_vol": {
   "avg_%": 1.57,
   "weeks": 7,
   "positive_weeks_%": 57
  },
  "roic": {
   "avg_%": 0.62,
   "weeks": 7,
   "positive_weeks_%": 57
  },
  "stability": {
   "avg_%": 0.96,
   "weeks": 7,
   "positive_weeks_%": 71
  },
  "fscore": {
   "avg_%": 0.67,
   "weeks": 7,
   "positive_weeks_%": 86
  },
  "net_issuance": {
   "avg_%": 1.26,
   "weeks": 7,
   "positive_weeks_%": 71
  },
  "asset_growth": {
   "avg_%": 1.21,
   "weeks": 7,
   "positive_weeks_%": 71
  },
  "low_short": {
   "avg_%": -0.64,
   "weeks": 7,
   "positive_weeks_%": 43
  },
  "filing_similarity": {
   "avg_%": 0.47,
   "weeks": 7,
   "positive_weeks_%": 57
  },
  "cap_bumped_vs_replacements": {
   "avg_%": -3.62,
   "weeks": 6,
   "positive_weeks_%": 33
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
  "graded": 96,
  "hit_rate_%": 38.5
 }
}
```

## Brokerage cross-check differences (Robinhood exports / Alpaca paper)
- Alpaca paper OXY: book 8.01383 shares, Alpaca 9.18977
- Alpaca paper PBF: book 4.32996 shares, Alpaca 4.49058
- Alpaca paper RS: book 2.06478 shares, Alpaca 2.14961

## Judge report card
6 rebuilds judged since 2026-09-26.
**Decision rule:** collecting — 2.1 months of decisions; first scheduled look at 3 months

IC = rank correlation between a forecast and the stock's return beyond its equal-weighted sector. 0 = no skill; +0.05 sustained is good; t >= 2 means unlikely to be luck. base_rate = the free statistics alone.

| Judge | 2w | 4w | 13w |
|---|---|---|---|
| base_rate | +0.010 (t 0.42, 4 dates) | +0.050 (t 0.31, 3 dates) | n/a |
| panel | +0.102 (t 2.43, 5 dates) | +0.129 (t 1.79, 4 dates) | n/a |
| panel_sharp | +0.125 (t 2.39, 4 dates) | +0.141 (t 1.8, 3 dates) | n/a |
| gemini_pro | +0.131 (t 4.42, 5 dates) | +0.117 (t 3.05, 4 dates) | n/a |
| gpt_sol | +0.059 (t 0.95, 5 dates) | +0.153 (t 2.52, 4 dates) | n/a |
| grok | +0.049 (t 1.33, 4 dates) | +0.159 (t 1.83, 3 dates) | n/a |
| kimi | +0.134 (t n/a, 1 dates) | +0.235 (t n/a, 1 dates) | n/a |
| replay_opus | +0.001 (t n/a, 1 dates) | +0.011 (t n/a, 1 dates) | n/a |
| sig_beat_quality | n/a | n/a | n/a |
| sig_guidance | n/a | n/a | n/a |
| sig_read_across | n/a | n/a | n/a |
| sonnet | +0.078 (t 1.52, 5 dates) | +0.121 (t 1.51, 4 dates) | n/a |
| sonnet55 | +0.309 (t n/a, 1 dates) | n/a | n/a |
| sonnet_council | +0.124 (t n/a, 1 dates) | n/a | n/a |

**Brier score, 4 weeks** (lower is better): panel 0.24624, panel_sharp 0.2465, base_rate 0.24772, gemini_pro 0.24726, gpt_sol 0.24698, grok 0.25279, kimi 0.24713, replay_opus 0.24832, sonnet 0.24548, flat 0.24753
- Panel vs base rate (the key test: do the paid judges add anything?): +0.0015 (t 0.7, 319 forecasts)
- Base rate vs a flat guess: -0.0002 (t -0.17, 319 forecasts)

**Calibration, 4 weeks** (forecast vs what happened): 0-40%: said 38.6%, happened 0.0% (n 1); 40-45%: said 43.4%, happened 28.4% (n 67); 45-50%: said 47.5%, happened 52.5% (n 162); 50-55%: said 51.5%, happened 37.5% (n 88); 55-60%: said 55.1%, happened 100.0% (n 1)

**Best judge combinations, 2w** (79 tested, so the best will look lucky). Live panel: +0.102 (t 2.42, 5 dates)
- gemini_pro+grok+sonnet+sonnet55: +0.319 (t n/a, 1 dates)
- gemini_pro+grok+sonnet55: +0.312 (t n/a, 1 dates)
- gemini_pro+gpt_sol+grok+sonnet+sonnet55: +0.295 (t n/a, 1 dates)
- gemini_pro+gpt_sol+grok+sonnet55: +0.286 (t n/a, 1 dates)

**Best judge combinations, 4w** (33 tested, so the best will look lucky). Live panel: +0.129 (t 1.8, 4 dates)
- gpt_sol+kimi: +0.272 (t n/a, 1 dates)
- gpt_sol+kimi+sonnet: +0.269 (t n/a, 1 dates)
- gemini_pro+gpt_sol+kimi+sonnet: +0.269 (t n/a, 1 dates)
- gpt_sol+grok+kimi: +0.263 (t n/a, 1 dates)

**Bought vs passed over** (avg return beyond sector):
- 2w: bought -0.5% (n 48) vs passed -1.39% (n 350)
- 4w: bought -2.86% (n 36) vs passed -2.74% (n 283)
**Sold vs kept, 4 weeks after:** sold -15.41% (n 5) vs kept -0.1% (n 12)
**Critic:** approved buys -3.01% (n 30) vs flagged/held -5.87% (n 44), 4 weeks
**Catalysts:** 66.7% moved the expected way (12 graded)
**Headline labelers** (right direction over the next 2 trading days vs sector): claude-haiku-4-5-20251001 (live) 53.2% of 3264; gemma-4-31b-it 100.0% of 1; nvidia:deepseek-ai/deepseek-v4.1-flash 33.3% of 18
**Process errors, last run (2026-11-14):** invalid_citations 0, judge_replies_unusable 17, uncited_adjustments 3, panel_failed 0, judge_disagreements 2, missing_exit_condition 0, model_fallbacks 498

**Macro agent vs the momentum rule** (sector ranking skill, IC):
- 4w: macro +0.095 (t 0.81, 6 dates); momentum rule -0.253 (t -2.98, 6 dates); macro vs base rate (Brier) +0.0114 (t 1.83, 99 forecasts)
- 8w: macro -0.202 (t -10.56, 2 dates); momentum rule -0.518 (t -4667366886547604.0, 2 dates); macro vs base rate (Brier) -0.0037 (t -0.71, 55 forecasts)
- 12-month macro rule: collecting — 2.1 of 12 months