# Edge tests (2026-11-13)

Three ideas tested on the same history as the screen backtest. Returns are against the stock's sector, single moves capped. Holds longer than a month are rebuilt only as often as they are held, so periods never overlap.

## 1. Holding period (out of sample from 2015-01-30)

Top-2-per-sector portfolio against the equal-weighted universe, a year, before and after trading costs (10 basis points each way).

| Mix | Hold | Excess a year | t | After costs | Names replaced each rebuild | IC | IC t |
|---|---|---|---|---|---|---|---|
| Current screen | 1 month | +4.9% | +2.08 | +3.6% | 53% | +0.0129 | +1.67 |
| Current screen | 3 months | +5.0% | +1.99 | +4.4% | 67% | +0.0216 | +1.84 |
| Current screen | 6 months | +3.9% | +1.34 | +3.5% | 76% | +0.0217 | +1.31 |
| Value alone | 1 month | +8.1% | +3.13 | +7.8% | 13% | +0.0099 | +1.38 |
| Value alone | 3 months | +9.9% | +3.70 | +9.7% | 26% | +0.0152 | +1.21 |
| Value alone | 6 months | +10.0% | +3.45 | +9.9% | 38% | +0.0225 | +1.33 |
| Quality alone | 1 month | -1.1% | -0.52 | -1.1% | 3% | +0.0063 | +1.40 |
| Quality alone | 3 months | -1.6% | -0.73 | -1.7% | 8% | +0.0126 | +1.50 |
| Quality alone | 6 months | -1.8% | -0.75 | -1.8% | 16% | +0.0105 | +0.85 |
| 12-month momentum alone | 1 month | +8.9% | +1.89 | +8.0% | 37% | +0.0008 | +0.07 |
| 12-month momentum alone | 3 months | +10.0% | +2.05 | +9.5% | 59% | +0.0033 | +0.18 |
| 12-month momentum alone | 6 months | +9.8% | +1.99 | +9.5% | 77% | -0.0016 | -0.05 |
| Earnings reaction alone | 1 month | +8.4% | +2.49 | +7.4% | 41% | +0.0052 | +1.06 |
| Earnings reaction alone | 3 months | +8.1% | +2.38 | +7.3% | 91% | +0.0052 | +0.71 |
| Earnings reaction alone | 6 months | +8.7% | +2.79 | +8.3% | 93% | +0.0109 | +1.21 |
| 1-month reversal alone | 1 month | +5.0% | +1.21 | +2.8% | 93% | +0.0041 | +0.42 |
| 1-month reversal alone | 3 months | +7.5% | +1.78 | +6.7% | 93% | +0.0035 | +0.22 |
| 1-month reversal alone | 6 months | +6.9% | +1.64 | +6.6% | 93% | -0.0086 | -0.44 |
| Low short interest alone | 1 month | -0.6% | -0.26 | -1.4% | 35% | +0.0173 | +1.90 |
| Low short interest alone | 3 months | -1.1% | -0.45 | -1.4% | 37% | +0.0168 | +1.31 |
| Low short interest alone | 6 months | -0.1% | -0.09 | -0.3% | 38% | +0.0277 | +1.70 |

## 2. Read-across from peers' earnings

Signal: the average earnings-day reaction of same-sub-industry peers that reported in the last 35 days and after the stock's own last report. Available for 69% of stock-months. 'Spread' is the top third minus the bottom third of covered stocks, a year.

| Horizon | IC | t | First half t | Second half t | Spread a year | t | First half t | Second half t |
|---|---|---|---|---|---|---|---|---|
| 1 month | +0.0012 | +0.29 | -0.07 | +0.47 | +1.0% | +1.06 | -0.04 | +1.37 |
| 3 months | -0.0003 | -0.06 | -0.40 | +0.28 | +0.1% | +0.18 | -0.48 | +0.60 |

## 3. Insider buying

Open-market purchases by officers and directors filed in the 90 days before each month-end (35,711 filings for today's index members). What the flagged stocks earned against their sector afterwards, a year, with t-stats for all years and each half (split at 2018-05-31).

| Flag | Share of stock-months | Next 1 month | t (halves) | Next 3 months | t (halves) | Next 6 months | t (halves) |
|---|---|---|---|---|---|---|---|
| Any officer or director bought (last 90 days) | 16.7% | +1.8% | +2.86 (+2.55, +1.68) | +2.1% | +3.64 (+3.32, +2.30) | +1.8% | +2.95 (+2.18, +2.01) |
| Cluster: 2 or more insiders bought | 5.6% | +1.9% | +1.52 (+1.85, +0.41) | +2.3% | +1.94 (+2.25, +0.75) | +2.5% | +1.99 (+1.73, +1.10) |
| Cluster: 3 or more insiders bought | 2.7% | +2.6% | +1.55 (+1.21, +0.99) | +2.6% | +1.62 (+1.47, +0.89) | +2.4% | +1.40 (+1.43, +0.65) |
| Insiders bought $500,000 or more in total | 4.3% | +2.4% | +1.79 (+1.48, +1.10) | +2.0% | +1.56 (+1.25, +0.97) | +2.2% | +1.83 (+1.49, +1.20) |

## Limits

- Today's index members only, so companies that failed are missing; this flatters buying beaten-down or insider-bought stocks in particular.
- Insider data uses the filing date, so nothing is known before it was public. Purchases by 10% owners who are not officers or directors are left out.
- With several mixes, horizons and flags tried, treat a t under about 3 as suggestive only.
