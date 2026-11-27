# Performance, 2026-10-09

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | +2.23% |  |  |  | 13.2 | -1.27% |  |
| AI as recommended | +1.70% |  |  |  | 13.9 | -1.32% |  |
| Screen-only control | +0.65% |  |  |  | 10.9 | -0.94% |  |
| Equal-weight (same picks) | +1.94% |  |  |  | 14.6 | -1.31% |  |
| No-macro (top-rated, no PM) | +1.79% |  |  |  | 17.0 | -1.56% |  |
| SPY | +1.69% |  |  |  | 7.3 | -0.66% |  |
| SPTM (S&P 1500) | +1.64% |  |  |  | 7.7 | -0.73% |  |
| Macro tilts (sector ETFs) | +1.94% |  |  |  | 8.4 | -0.82% |  |
| Momentum rule (sector ETFs) | +1.41% |  |  |  | 8.3 | -0.97% |  |
| AI actual (after AI costs) | +2.16% |  |  |  | 13.1 | -1.27% |  |
| AI actual (after costs and est. tax) | +1.83% |  |  |  | 13.1 | -1.27% |  |

AI costs to date: $28.24. Estimated tax on realized short-term gains (Individual, at 24%): $10.50.
Drawdown rule: level 0 (relative drawdown -0.98% over 3 months).

Review checkpoint: 6-month review in about 6 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): +0.55 pts vs SPY
- Stock picks (stock team): -0.51 pts vs their sector ETFs
  - S&P 500: -1.43 pts
  - S&P 600: -0.02 pts
  - S&P 400: +0.95 pts

## Scorecards
```
{
 "signal_spread_1wk_%": {
  "momentum": {
   "avg_%": 0.0,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "earnings": {
   "avg_%": 0.53,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "reaction": {
   "avg_%": 0.24,
   "weeks": 3,
   "positive_weeks_%": 100
  },
  "industry": {
   "avg_%": -0.41,
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
   "avg_%": 0.0,
   "weeks": 3,
   "positive_weeks_%": 67
  },
  "reversal": {
   "avg_%": 0.16,
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
   "avg_%": -0.74,
   "weeks": 2,
   "positive_weeks_%": 0
  },
  "frog_momentum": {
   "avg_%": -0.82,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "low_vol": {
   "avg_%": -1.03,
   "weeks": 2,
   "positive_weeks_%": 0
  },
  "roic": {
   "avg_%": 0.71,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "stability": {
   "avg_%": 0.02,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "fscore": {
   "avg_%": 0.89,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "net_issuance": {
   "avg_%": 1.0,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "asset_growth": {
   "avg_%": 0.24,
   "weeks": 2,
   "positive_weeks_%": 50
  },
  "low_short": {
   "avg_%": 0.92,
   "weeks": 2,
   "positive_weeks_%": 100
  },
  "filing_similarity": {
   "avg_%": 0.24,
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
  "graded": 0,
  "hit_rate_%": null
 }
}
```

## Brokerage cross-check differences (Robinhood exports / Alpaca paper)
- Alpaca paper RS: book 1.4526 shares, Alpaca 1.53742

## Judge report card
no graded decisions yet

**Macro agent:** no graded macro runs yet