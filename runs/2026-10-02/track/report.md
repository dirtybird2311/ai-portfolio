# Performance, 2026-10-02

| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| AI actual | +1.71% |  |  |  |  | -0.44% |  |
| AI as recommended | +1.27% |  |  |  |  | -0.86% |  |
| Screen-only control | +0.21% |  |  |  |  | -0.81% |  |
| Equal-weight (same picks) | +1.29% |  |  |  |  | -1.04% |  |
| No-macro (top-rated, no PM) | +1.15% |  |  |  |  | -1.06% |  |
| SPY | +0.53% |  |  |  |  | -0.39% |  |
| SPTM (S&P 1500) | +0.57% |  |  |  |  | -0.48% |  |
| Macro tilts (sector ETFs) | -0.25% |  |  |  |  | -0.82% |  |
| Momentum rule (sector ETFs) | -0.21% |  |  |  |  | -0.97% |  |
| AI actual (after AI costs) | +1.71% |  |  |  |  | -0.44% |  |
| AI actual (after costs and est. tax) | +1.48% |  |  |  |  | -0.44% |  |

AI costs to date: $21.97. Estimated tax on realized short-term gains (Individual, at 24%): $0.00.
Drawdown rule: level 0 (relative drawdown 0% over 3 months).

Review checkpoint: 6-month review in about 6 months.

## Attribution (sum of rebuild periods)
- Sector choices (macro agent): -0.67 pts vs SPY
- Stock picks (stock team): +1.43 pts vs their sector ETFs
  - S&P 400: +1.21 pts
  - S&P 600: +0.76 pts
  - S&P 500: -0.55 pts

## Scorecards
```
{
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

## Judge report card
no graded decisions yet

**Macro agent:** no graded macro runs yet