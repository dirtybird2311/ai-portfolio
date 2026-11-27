# Screen backtest (2026-11-13)

Out-of-sample months: 2015-01-30 to 2026-09-30 (141 months). Signals tested: 18. About 27% of the live screen's weight (earnings estimates, insider buying) has no history here and is left out of every mix.

## Mixes compared

| Mix | IC | t | Top-2-per-sector vs equal-weight universe, a year | 95% range | t | After costs | vs SPY, a year | Months ahead of SPY | Monthly turnover |
|---|---|---|---|---|---|---|---|---|---|
| Current weights | +0.0129 | 1.66 | +4.9% | +0.3% to +9.6% | 2.08 | +3.7% | +6.4% (t 2.12) | 56% | 53% |
| Starting weights | +0.0093 | 0.92 | +3.3% | -2.0% to +8.6% | 1.23 | +2.3% | +4.8% (t 1.53) | 52% | 42% |
| Equal per family | +0.0140 | 1.99 | +6.4% | +1.7% to +11.1% | 2.67 | +4.5% | +7.9% (t 2.27) | 58% | 79% |
| Walk-forward, by past IC | +0.0031 | 0.31 | +3.5% | -1.8% to +8.7% | 1.3 | +1.8% | +4.9% (t 1.56) | 55% | 69% |
| Walk-forward ridge | +0.0127 | 1.3 | +2.7% | -2.6% to +8.1% | 1.0 | +0.9% | +4.2% (t 1.31) | 51% | 76% |
| Halfway: current + ridge | +0.0134 | 1.48 | +3.8% | -1.2% to +8.7% | 1.48 | +2.1% | +5.2% (t 1.73) | 57% | 67% |
| Current + momentum crash guard | +0.0193 | 2.55 | +7.0% | +2.5% to +11.5% | 3.07 | +5.7% | +8.5% (t 2.69) | 56% | 56% |

IC = monthly rank correlation between the mix's score and the next 4 weeks' return inside each sector. A t above about 2 means the result is unlikely to be luck. Portfolio results count a single 4-week move of at most +/-50% (736 of 193,113 stock-months were larger). After costs = minus 10 basis points for each buy and sell the monthly turnover implies. Read the equal-weight-universe columns first: the SPY column is flattered by survivorship (see Limits).

## Is any mix better than the current one?

| Mix | IC difference | t | vs-SPY difference, a month | t |
|---|---|---|---|---|
| Starting weights | -0.0036 | -0.93 | -0.13% | -1.06 |
| Equal per family | +0.0012 | 0.32 | +0.12% | 0.79 |
| Walk-forward, by past IC | -0.0098 | -2.23 | -0.12% | -0.62 |
| Walk-forward ridge | -0.0001 | -0.03 | -0.18% | -0.84 |
| Halfway: current + ridge | +0.0005 | 0.17 | -0.10% | -0.75 |
| Current + momentum crash guard | +0.0064 | 2.13 | +0.17% | 1.84 |

## By period (top-2-per-sector portfolio vs SPY, a year; IC in brackets)

| Mix | 2015-2019 | 2020-2022 | 2023-now |
|---|---|---|---|
| Current weights | +7.7% (+0.022) | +8.2% (-0.004) | +3.2% (+0.014) |
| Starting weights | +8.0% (+0.018) | +4.6% (-0.017) | +0.6% (+0.018) |
| Equal per family | +9.4% (+0.029) | +9.7% (+0.001) | +4.4% (+0.005) |
| Walk-forward, by past IC | +4.0% (+0.013) | +10.5% (-0.011) | +1.7% (+0.001) |
| Walk-forward ridge | +1.7% (+0.020) | +11.2% (-0.012) | +1.9% (+0.023) |
| Halfway: current + ridge | +6.3% (+0.022) | +6.5% (-0.009) | +2.7% (+0.019) |
| Current + momentum crash guard | +10.5% (+0.032) | +12.8% (+0.006) | +2.4% (+0.014) |

## Weights by family

| Mix | Weights |
|---|---|
| Current weights | momentum 29%, value 27%, quality 23%, reaction 12%, reversal 8% |
| Starting weights | momentum 41%, quality 27%, value 20%, reaction 8%, reversal 3% |
| Equal per family | momentum 20%, quality 20%, value 20%, reaction 20%, reversal 20% |
| Walk-forward, by past IC | momentum 34%, low_short 20%, value 16%, reaction 11%, quality 10%, reversal 5%, filing_similarity 2%, net_issuance 1%, asset_growth 1% |
| Walk-forward ridge | momentum 44%, low_short 19%, value 12%, reversal 8%, reaction 7%, quality 4%, asset_growth 3%, filing_similarity 3% |

The momentum crash guard was on in 15 of the test months. Today it would be off: the equal-weighted market's last 12 months are +20.6% (to 2026-11-06).

## Each signal on its own, same months

| Signal | IC | t |
|---|---|---|
| low_short | +0.0173 | 1.9 |
| quality | +0.0063 | 1.4 |
| value | +0.0098 | 1.38 |
| roic | +0.0053 | 1.1 |
| reaction | +0.0051 | 1.05 |
| fscore | +0.0036 | 0.93 |
| filing_similarity | +0.0032 | 0.92 |
| net_issuance | +0.0045 | 0.88 |
| resid_momentum | +0.0094 | 0.74 |
| industry | +0.0053 | 0.64 |
| reversal | +0.0041 | 0.43 |
| asset_growth | +0.0015 | 0.34 |
| riskadj_momentum | +0.0039 | 0.32 |
| frog_momentum | +0.0012 | 0.1 |
| momentum | +0.0007 | 0.06 |
| stability | +0.0001 | 0.01 |
| high_52w | -0.0035 | -0.25 |
| low_vol | -0.0079 | -0.52 |

## Red flags: what flagged stocks did next

Each flag marks stocks at month-end; the figure is what they earned against their sector over the next 4 weeks, a year. A flag worth screening on is clearly negative in both halves of the history (split at 2018-05-31). With 15 flags tried, a t below about -2.9 is the bar for one of them alone.

| Flag | Share of stocks | All years | t | First half | t | Second half | t | Effect on the portfolio if never bought | t |
|---|---|---|---|---|---|---|---|---|---|
| Missed earnings (fell over 3% on the report) | 26% | -1.4% | -2.15 | -1.6% | -1.7 | -1.2% | -1.33 | +0.02% | 0.03 |
| Most-changed annual report | 7% | -2.1% | -1.9 | -1.7% | -0.92 | -2.3% | -1.65 | -1.18% | -1.54 |
| Lowest profitability | 5% | -2.6% | -1.81 | -6.2% | -2.9 | +0.5% | 0.29 | -0.01% | -1.0 |
| Fastest asset growth | 6% | -1.5% | -1.05 | -2.5% | -1.26 | -0.7% | -0.35 | -2.11% | -2.44 |
| Biggest 1-month jump | 10% | -0.7% | -0.4 | -1.5% | -0.86 | +0.2% | 0.06 | -0.26% | -0.41 |
| Most heavily shorted | 3% | -0.6% | -0.34 | n/a | None | -0.6% | -0.34 | +0.46% | 0.66 |
| Biggest 12-month losers | 9% | +1.2% | 0.53 | -1.4% | -0.51 | +3.7% | 1.11 | -0.14% | -0.68 |
| Negative return on capital | 8% | +1.0% | 0.53 | -0.9% | -0.31 | +2.9% | 1.06 | -0.79% | -1.74 |
| Least stable margins | 5% | +1.3% | 0.79 | +0.9% | 0.34 | +1.7% | 0.75 | -0.17% | -0.28 |
| Most share issuance | 6% | +1.6% | 0.89 | +0.3% | 0.12 | +2.9% | 1.2 | +0.17% | 0.28 |
| Weak financial health (F-score 3 or less) | 4% | +1.6% | 0.9 | +1.9% | 0.68 | +1.4% | 0.59 | -0.65% | -1.28 |
| Most expensive | 6% | +2.6% | 1.26 | -0.9% | -0.37 | +6.1% | 1.86 | +0.00% | None |
| Three or more flags at once | 14% | +2.6% | 1.26 | +0.3% | 0.09 | +5.0% | 1.85 | -1.01% | -1.5 |
| Furthest below 52-week high | 10% | +4.9% | 1.81 | +2.5% | 0.73 | +7.3% | 1.74 | -0.65% | -1.14 |
| Highest volatility | 10% | +6.8% | 2.39 | +3.8% | 1.09 | +9.8% | 2.18 | -1.07% | -0.77 |

## Limits

- Today's index members only: companies that failed or were dropped are missing, which flatters every mix.
- No trading costs. At 10 basis points a trade, a portfolio that replaces X% of its names each month loses about X% x 12 x 0.2% a year.
- The portfolio here is 2 names per sector, equal weight, rebuilt monthly: a stand-in, not the live rules.
- The SPY column is not a fair fight. The universe is today's S&P 1500 members carried back in time, so it already holds the small companies that went on to grow; that puts the equal-weighted universe ahead of SPY in this test, where real equal-weighted funds lagged it. The equal-weight-universe column removes most of the effect and is the one to trust.
