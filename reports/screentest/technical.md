# Technical-indicator backtest (2026-11-13)

Month-ends 2010-01-29 to 2026-09-30; every indicator uses closing prices up to that day only and is scored in the direction chartists read as bullish. Target: the next 4 weeks against the stock's sector. With 25 indicators and patterns tried, a t beyond about 3 either way is the bar for one alone; a real effect should also keep its sign in both halves (split at 2018-05-31).

## Each indicator alone

| Indicator (bullish reading) | IC | t | First half t | Second half t | Top-2-per-sector vs universe, a year | t | Monthly turnover |
|---|---|---|---|---|---|---|---|
| Low in its 14-day range (stochastic oversold) | +0.0115 | 1.96 | 2.09 | 0.84 | +0.8% | 0.43 | 96% |
| Near or under the lower Bollinger band | +0.0105 | 1.68 | 1.98 | 0.54 | +3.2% | 1.54 | 96% |
| Low 14-day RSI (oversold) | +0.0090 | 1.24 | 1.26 | 0.56 | +3.0% | 1.34 | 92% |
| Close to its 3-month low (buy at support) | +0.0053 | 0.75 | 1.25 | -0.02 | +0.7% | 0.38 | 92% |
| Far above its 52-week low | +0.0060 | 0.72 | 0.9 | 0.23 | +11.7% | 3.12 | 30% |
| Volatility squeezed (20-day vs 120-day) | +0.0018 | 0.45 | 1.27 | -0.42 | -1.2% | -0.62 | 84% |
| 50-day average above the 200-day (golden-cross state) | +0.0005 | 0.05 | 0.36 | -0.23 | +9.7% | 2.73 | 35% |
| Price far above its 200-day average (uptrend) | -0.0022 | -0.21 | 0.1 | -0.36 | +6.9% | 2.08 | 49% |
| Up over the last 6 months | -0.0022 | -0.22 | 0.15 | -0.43 | +7.1% | 2.03 | 48% |
| 50-day average rising | -0.0040 | -0.47 | 0.41 | -0.99 | +6.3% | 2.07 | 64% |
| Up over the last 3 months | -0.0057 | -0.65 | -0.04 | -0.81 | +7.8% | 2.41 | 64% |
| At or through its 3-month high (resistance breakout) | -0.0077 | -0.8 | -0.34 | -0.78 | -2.0% | -0.74 | 94% |
| MACD above its signal line | -0.0064 | -0.98 | -2.61 | 0.77 | +1.3% | 0.43 | 95% |
| Up over the last month | -0.0083 | -1.06 | -1.24 | -0.37 | +2.0% | 0.64 | 93% |
| Price far above its 50-day average | -0.0094 | -1.17 | -0.83 | -0.83 | +4.3% | 1.41 | 81% |

A negative IC means the bullish reading pointed the wrong way: those stocks went on to lag.

## Patterns: what stocks showing one did next (vs their sector, a year)

| Pattern | Share of stock-months | All years | t | First half | t | Second half | t |
|---|---|---|---|---|---|---|---|
| Below the lower Bollinger band | 4% | +7.1% | 1.85 | +9.8% | 1.67 | +4.3% | 0.88 |
| RSI under 30 (oversold) | 3% | +6.1% | 1.42 | +7.2% | 1.15 | +4.9% | 0.84 |
| New 3-month low today (break below support) | 4% | +1.2% | 0.36 | +3.7% | 0.81 | -1.2% | -0.24 |
| Golden cross in the last month | 6% | -0.7% | -0.42 | -0.3% | -0.13 | -1.1% | -0.44 |
| New 3-month high today (breakout through resistance) | 8% | -1.1% | -0.45 | -0.6% | -0.25 | -1.5% | -0.38 |
| RSI over 70 (overbought) | 6% | -3.7% | -0.86 | +4.7% | 1.24 | -11.8% | -1.55 |
| Bounce off support (3-month low in the last 10 days, within 5% of it, up over 5 days) | 4% | -1.7% | -0.88 | -2.1% | -0.82 | -1.3% | -0.44 |
| Death cross in the last month | 6% | -1.4% | -0.95 | -3.2% | -1.7 | +0.4% | 0.19 |
| Above the upper Bollinger band | 5% | -5.2% | -1.79 | -4.2% | -1.87 | -6.2% | -1.16 |
| Above its 200-day average | 63% | -2.8% | -3.21 | -2.3% | -2.25 | -3.3% | -2.33 |

## As a screen-out rule

Each rule drops a group of stocks every month: the bottom or top tenth of an indicator inside each sector, or every stock showing a pattern. 'Dropped stocks' is what they earned against their sector over the next 4 weeks, a year: a useful rule drops stocks that went on to LAG (clearly negative, in both halves). The last columns are what the current screen's top-2-per-sector portfolio gained when it could never buy them. With 40 rules tried, a t beyond about 3.2 is the bar for one alone.

| Rule: never buy... | Share dropped | Dropped stocks, a year | t | First half t | Second half t | Portfolio gain, a year | t |
|---|---|---|---|---|---|---|---|
| Volatility squeezed (20-day vs 120-day): the LEAST so (bottom tenth) | 10% | -2.9% | -3.5 | -2.43 | -2.61 | -0.86% | -1.1 |
| Above its 200-day average | 63% | -2.8% | -3.21 | -2.25 | -2.33 | -3.28% | -1.08 |
| Near or under the lower Bollinger band: the LEAST so (bottom tenth) | 10% | -4.3% | -3.01 | -2.92 | -1.79 | -0.55% | -0.81 |
| At or through its 3-month high (resistance breakout): the MOST so (top tenth) | 10% | -4.1% | -2.48 | -1.42 | -2.03 | -0.82% | -0.94 |
| Low in its 14-day range (stochastic oversold): the LEAST so (bottom tenth) | 8% | -3.6% | -2.28 | -1.51 | -1.75 | -1.04% | -1.6 |
| Low 14-day RSI (oversold): the LEAST so (bottom tenth) | 10% | -3.4% | -2.22 | -2.1 | -1.29 | -0.19% | -0.29 |
| Above the upper Bollinger band | 5% | -5.2% | -1.79 | -1.87 | -1.16 | -0.20% | -0.42 |
| Price far above its 50-day average: the MOST so (top tenth) | 10% | -1.9% | -1.17 | -1.07 | -0.71 | -0.01% | -0.01 |
| Far above its 52-week low: the LEAST so (bottom tenth) | 9% | -1.6% | -1.08 | -0.46 | -0.99 | -0.22% | -0.84 |
| Death cross in the last month | 6% | -1.4% | -0.95 | -1.7 | 0.19 | -0.83% | -1.24 |
| Bounce off support (3-month low in the last 10 days, within 5% of it, up over 5 days) | 4% | -1.7% | -0.88 | -0.82 | -0.44 | +0.46% | 1.0 |
| RSI over 70 (overbought) | 6% | -3.7% | -0.86 | 1.24 | -1.55 | +0.06% | 0.11 |
| New 3-month high today (breakout through resistance) | 8% | -1.1% | -0.45 | -0.25 | -0.38 | -0.56% | -0.94 |
| Up over the last month: the MOST so (top tenth) | 10% | -0.7% | -0.42 | -0.71 | -0.05 | -0.22% | -0.35 |
| Golden cross in the last month | 6% | -0.7% | -0.42 | -0.13 | -0.44 | -0.09% | -0.19 |
| MACD above its signal line: the MOST so (top tenth) | 10% | -0.2% | -0.15 | -1.01 | 0.55 | -0.38% | -0.57 |
| Volatility squeezed (20-day vs 120-day): the MOST so (top tenth) | 10% | -0.1% | -0.09 | 0.66 | -0.7 | +0.46% | 0.45 |
| Up over the last 3 months: the MOST so (top tenth) | 10% | +0.2% | 0.11 | 0.35 | -0.1 | -2.22% | -1.66 |
| Price far above its 200-day average (uptrend): the MOST so (top tenth) | 10% | +0.4% | 0.21 | 0.04 | 0.23 | -3.65% | -2.31 |
| Close to its 3-month low (buy at support): the MOST so (top tenth) | 10% | +0.3% | 0.24 | 1.19 | -0.47 | -0.11% | -0.14 |
| New 3-month low today (break below support) | 4% | +1.2% | 0.36 | 0.81 | -0.24 | +0.33% | 0.52 |
| Up over the last 6 months: the MOST so (top tenth) | 10% | +1.0% | 0.54 | 0.31 | 0.44 | -2.54% | -1.73 |
| 50-day average rising: the LEAST so (bottom tenth) | 10% | +1.1% | 0.57 | 0.03 | 0.7 | -0.44% | -0.86 |
| 50-day average above the 200-day (golden-cross state): the MOST so (top tenth) | 10% | +1.1% | 0.59 | 0.69 | 0.28 | -3.31% | -1.81 |
| 50-day average rising: the MOST so (top tenth) | 10% | +1.3% | 0.8 | 0.89 | 0.36 | -3.65% | -2.63 |
| MACD above its signal line: the LEAST so (bottom tenth) | 10% | +1.2% | 0.82 | 1.16 | 0.24 | -1.75% | -1.42 |
| 50-day average above the 200-day (golden-cross state): the LEAST so (bottom tenth) | 10% | +2.0% | 0.91 | 0.58 | 0.69 | -0.17% | -0.68 |
| Low 14-day RSI (oversold): the MOST so (top tenth) | 10% | +1.5% | 0.99 | 1.45 | 0.35 | -1.49% | -1.59 |
| Price far above its 200-day average (uptrend): the LEAST so (bottom tenth) | 10% | +2.4% | 1.01 | 0.3 | 1.03 | -0.87% | -1.98 |
| Close to its 3-month low (buy at support): the LEAST so (bottom tenth) | 10% | +2.0% | 1.12 | 0.32 | 1.13 | -2.37% | -2.01 |
| Near or under the lower Bollinger band: the MOST so (top tenth) | 10% | +1.2% | 1.12 | 1.15 | 0.6 | -0.99% | -0.95 |
| Up over the last 3 months: the LEAST so (bottom tenth) | 10% | +2.4% | 1.15 | 0.8 | 0.84 | -0.54% | -0.81 |
| Price far above its 50-day average: the LEAST so (bottom tenth) | 10% | +2.4% | 1.2 | 0.94 | 0.8 | -1.28% | -1.43 |
| Up over the last 6 months: the LEAST so (bottom tenth) | 10% | +2.9% | 1.23 | 0.46 | 1.2 | -0.66% | -1.52 |
| Up over the last month: the LEAST so (bottom tenth) | 10% | +2.7% | 1.35 | 1.29 | 0.75 | -1.56% | -1.33 |
| At or through its 3-month high (resistance breakout): the LEAST so (bottom tenth) | 10% | +3.3% | 1.37 | 0.74 | 1.15 | -1.83% | -1.73 |
| RSI under 30 (oversold) | 3% | +6.1% | 1.42 | 1.15 | 0.84 | +0.05% | 0.11 |
| Below the lower Bollinger band | 4% | +7.1% | 1.85 | 1.67 | 0.88 | -0.58% | -0.95 |
| Low in its 14-day range (stochastic oversold): the MOST so (top tenth) | 9% | +2.8% | 2.01 | 1.62 | 1.32 | -2.98% | -2.76 |
| Far above its 52-week low: the MOST so (top tenth) | 10% | +3.9% | 2.02 | 0.99 | 1.76 | -3.32% | -2.01 |

## Together (out of sample from 2015-01-30)

| Mix | IC | t | Top-2-per-sector vs universe, a year | 95% range | t | After costs | Monthly turnover |
|---|---|---|---|---|---|---|---|
| Current screen | +0.0129 | 1.66 | +4.9% | +0.3% to +9.6% | 2.08 | +3.7% | 53% |
| Technical only: all indicators, equal parts | -0.0002 | -0.02 | +3.4% | -2.9% to +9.6% | 1.06 | +1.4% | 81% |
| Technical only: walk-forward, by past IC | +0.0054 | 0.69 | +1.2% | -3.8% to +6.2% | 0.46 | -1.1% | 95% |
| Technical only: walk-forward ridge | -0.0030 | -0.36 | -0.8% | -5.9% to +4.4% | -0.29 | -3.0% | 93% |
| Current screen + technical ridge at 20% | +0.0103 | 1.34 | +4.4% | -0.0% to +8.9% | 1.94 | +2.6% | 74% |

| Against the current screen | IC difference | t | Portfolio difference, a month | t |
|---|---|---|---|---|
| Technical only: all indicators, equal parts | -0.0131 | -1.33 | -0.13% | -0.51 |
| Technical only: walk-forward, by past IC | -0.0074 | -0.68 | -0.31% | -1.19 |
| Technical only: walk-forward ridge | -0.0158 | -1.55 | -0.48% | -1.8 |
| Current screen + technical ridge at 20% | -0.0025 | -0.81 | -0.04% | -0.3 |

Latest walk-forward ridge weights: stochastic_low 24%, bollinger_low 21%, rsi_oversold 18%, above_52w_low 18%, squeeze 12%, near_support 9%.

## Limits

- Closing prices only: no volume, no daily highs or lows.
- Today's index members only, month-end decisions, a 4-week hold, no trading costs except in the after-costs column.
- Support and resistance here are rule-based (3-month highs and lows), not hand-drawn chart levels.
