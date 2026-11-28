# Macro view, 2026-11-27
**Status: OK**

Why this run: tripwire: High-yield credit spread is newly unusual (z +1.3 -> +2.0)

## Regime
Code: **Reflation (growth up, inflation up)**, Fed on hold

## Market & recession risk
Recession within 12 months: 24% (normal; typical 23%). S&P 500 10%+ pullback within 3 months: 15% (normal; typical 13%).

**Recession within 12 months: 24%** (typical 23%; model trained on 658 months since 1971; out-of-sample accuracy AUC 0.874 since 1990-01, Brier skill 13.0%)

| Input | Now | Push on risk |
|---|---|---|
| 10-yr minus 3-month Treasury spread (pts) | 0.677 | +0.83 |
| Chicago Fed financial conditions (above 0 = tighter than average) | -0.45 | -0.74 |
| S&P 500, 6-month return (%) | -3.728 | +0.61 |
| Sahm rule, real time (0.5+ has marked every recession start) | 0.0 | -0.03 |
| Jobless claims, 6-month change (%) | -6.585 | +0.01 |

Benchmarks: NY Fed-style yield-curve model 17%; Chauvet-Piger probability we're in a recession now 0% (as of 2026-09-01)

**S&P 500 pullback of 10%+ within 3 months: 15%** (typical 13%; model trained on 484 months since 1986; out-of-sample accuracy AUC 0.68 since 2000-01, Brier skill -1.8%)

| Input | Now | Push on risk |
|---|---|---|
| S&P 500 1-month realized volatility (log) | -1.152 | +0.25 |
| S&P 500 vs its 200-day average (%) | -0.772 | +0.17 |
| Baa corporate bond spread over 10-yr Treasury (pts) | 1.61 | -0.11 |
| Baa spread, 3-month change (pts) | 0.07 | +0.05 |
| Chicago Fed financial conditions | -0.444 | -0.04 |
- Tested input *Geopolitical Risk Index, 30-day average (log)*: not kept (accuracy 0.68 → 0.676)
- Tested input *Economic policy uncertainty, 30-day average (log)*: not kept (accuracy 0.68 → 0.67)

| Indicator | Now | As of | Reading |
|---|---|---|---|
| Yield curve (10y - 3m) | 0.68 | 2026-11-27 | positive; inverted 0 of the last 24 months |
| Sahm rule (real time) | 0.0 | 2026-10-01 | calm |
| High-yield credit spread | 3.77 | 2026-11-26 | 96th percentile since 2023; widening fast |
| Chicago Fed financial conditions (NFCI) | -0.44 | 2026-11-20 | looser than average |
| S&P 500 vs 200-day average | -0.8% | 2026-11-27 | below (downtrend) |
| S&P 500 1-month volatility | 32% | 2026-11-27 | 96th percentile since 1970 (stressed) |
| Geopolitical Risk Index (30-day avg) | 143.6 | 2026-11-23 | 89th percentile since 1985 (elevated) |
| Economic policy uncertainty (30-day avg) | 284.2 | 2026-11-26 | 95th percentile since 1985 (elevated) |
| Trade policy uncertainty (monthly) | 1400.8 | 2026-09-01 | 96th percentile since 1985 (elevated) |
| Oil volatility (OVX) | 48.0 | 2026-11-25 | 82th percentile since 2007 (elevated) |
| Oil futures curve (front vs ~6 months out) | +7.4% | 2026-11-27 | steep backwardation: oil is scarce NOW (real supply squeeze) |
| Jobless claims, 6-month change | -7% | 2026-11-21 | stable |

*Statistical models on public data: they flag risky periods, with false alarms; they don't time tops.*

## Oil shock: sector return vs SPY if oil moves 20%
| Sector | Oil up | Oil down |
|---|---|---|
| Energy | +6.5% | -6.5% |
| Utilities | +1.5% | -1.5% |
| Real Estate | +1.3% | -1.3% |
| Health Care | +0.2% | -0.2% |
| Consumer Staples | +0.2% | -0.2% |
| Communication Services | -0.0% | +0.0% |
| Financials | -0.1% | +0.1% |
| Materials | -0.1% | +0.1% |
| Technology | -0.5% | +0.5% |
| Industrials | -0.6% | +0.6% |
| Consumer Discretionary | -1.4% | +1.4% |

- *claude-sonnet-5*: Growth and inflation are both running hot and accelerating: real GDP +4.3% annualized, GDPNow 2.9 rising, payrolls +165k, unemployment falling to 4.1%, while CPI 4.08% and core PCE 3.26% are both rising for a third straight month. This matches the coded 'Reflation' regime with Fed on hold near the 2026 dot median (DFF 3.88 vs SEP_FEDTARMD_2026 4.1). The complication is that financial-market stress is rising sharply alongside strong activity data: HY credit spreads have jumped to a 2-sigma, 92nd-percentile reading and are 'widening fast,' VIX is at a 90th-percentile/96th-percentile(1m realized) stressed level, and S&P is below its 200-day average. CALC:recession_risk (p=0.243 vs typical 0.229) and CALC:pullback_risk (p=0.149 vs typical 0.132) are both only modestly above normal and don't yet flag acute danger (oos_auc 0.874/0.68), but neither model uses the HY spread directly as a top driver (they use yield curve, NFCI, realized vol, Baa spread) so the fresh credit tripwire is a real incremental risk the models are underweighting right now.
- *claude-opus-5-5*: I agree with the code's regime call (Reflation, Fed on hold), with a market-stress overlay.

Growth is firm:
- Payrolls rebounded to +165k.
- Unemployment is 4.1%.
- Claims are at the 1.6th percentile.
- Retail sales are up 6.82% YoY.
- GDP ran at 4.3% and GDPNow is 2.9%.

Inflation is rising: headline CPI is 4.08% and core PCE 3.26%, both rising.

The tripwire is high-yield spreads widening from 2.85 to 3.77 (z +2.0). This comes alongside a VIX of 26.8 and 1-month S&P volatility at the 96th percentile. The S&P is 0.8% below its 200-day average.

I agree with CALC:recession_risk (0.243 vs typical 0.229, normal). Its inputs are reassuring:
- The curve is positive (10y-3m +0.68).
- The Sahm rule is 0.
- NFCI is still looser than average at -0.44.
- Banks are easing business loan standards (net 1.7%).
- Bank loans are growing 7.5%.

The model's weakness is that it leans on the curve and financial conditions, which lag a geopolitical or oil-driven credit shock. So the spread move is a real but not yet confirmed risk.

CALC:pullback_risk (0.149 vs 0.132) is modestly elevated, and I think it slightly understates risk. Its top drivers do not include the HY spread or the Hormuz escalation (mines hitting ships on Nov 26). With volatility already stressed, I lean toward pullback risk above the model, but not dramatically so, given strong earnings.
- *gemini-3.8-flash@paid (fallback)*: The economy remains in Reflation with growth holding up and inflation re-accelerating, while the Fed is officially on hold. GDP growth is robust at 4.3% annualized (FRED:A191RL1Q225SBEA: 4.3) and Atlanta Fed GDPNow is tracking 2.9% (FRED:GDPNOW: 2.9), while payrolls rebounded to 165k (FRED:PAYEMS: 165) and initial claims dropped to 196k (FRED:IC4WSA: 196000). Simultaneously, headline CPI sits at 4.08% (FRED:CPIAUCSL: 4.08) and Core PCE is 3.26% (FRED:PCEPILFE: 3.26), well above the Fed's 2% objective. Statistical recession risk remains normal at p_12m=0.243 (CALC:recession_risk), supported by an un-inverted yield curve (10y-3m at +0.68) and a dormant Sahm rule at 0.0 (FRED:SAHMREALTIME: 0). However, pullback risk is elevated under the surface despite the model reading p_10pct_3m=0.149 (CALC:pullback_risk), as high-yield credit spreads have spiked sharply to 3.77% (z=+2.01, FRED:BAMLH0A0HYM2: 3.77), 1-month S&P realized volatility sits at the 96th percentile (CALC:risk_indicators), and VIX is elevated at 26.8 (FRED:VIXCLS: 26.8).
- *xai:grok-4.3*: Reflation regime holds with growth and inflation both rising; recession_risk normal at 0.243 and pullback_risk normal at 0.149 per CALC models

## Economic forecast (median of the models, next 4 weeks)
- bp change in the 10-yr Treasury yield: +0
- % change in WTI crude: +1.5
- % change in the dollar (UUP): +0
- % change in HYG/IEF (up = credit spreads tightening): -0.75
- % change in TIP/IEF (up = inflation expectations rising): +0

## Sector probabilities and tilts
| Sector | P(beat SPY) | Base rate | vs market pricing | Tilt | Weight range | Momentum rule | Critic | How decided |
|---|---|---|---|---|---|---|---|---|
| Technology | 40% | 52% | -12.1 | -1 | 0–10% | 0 | PASS | base 52%, factors -12.1, sector-specific +0.0 (models [0, 0, -1.0, 0]) -> 40%; vs market pricing -12.1 pts; capped at +/-1 (only two full tilts allowed) |
| Financials | 49% | 49% | +0.3 | +0 | 0–18% | 0 | PASS | base 49%, factors +0.3, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 49%; vs market pricing +0.3 pts |
| Health Care | 64% | 51% | +12.6 | +1 | 5–22% | 1 | PASS | base 51%, factors +12.6, sector-specific +0.0 (models [0, 0, 1.0, 0]) -> 64%; vs market pricing +12.6 pts; capped at +/-1 (only two full tilts allowed) |
| Energy | 58% | 47% | +11.6 | +1 | 5–22% | 2 | PASS | base 47%, factors +11.6, sector-specific +0.0 (models [0, 0, 1.0, 0]) -> 58%; vs market pricing +11.6 pts; capped at +/-1 (only two full tilts allowed) |
| Industrials | 53% | 53% | +0.0 | +0 | 0–18% | -1 | PASS | base 53%, factors +0.0, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 53%; vs market pricing +0.0 pts |
| Consumer Discretionary | 43% | 49% | -5.8 | -1 | 0–10% | -1 | PASS | base 49%, factors -5.3, sector-specific -0.5 (models [-2.0, 0, -1.0, 0]) -> 43%; vs market pricing -5.8 pts |
| Consumer Staples | 66% | 47% | +19.4 | +2 | 10–25% | 2 | PASS | base 47%, factors +19.4, sector-specific +0.0 (models [0.0, 0, 1.0, 0]) -> 66%; vs market pricing +19.4 pts |
| Utilities | 64% | 48% | +16.0 | +2 | 10–25% | -2 | PASS | base 48%, factors +16.0, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 64%; vs market pricing +16.0 pts |
| Materials | 53% | 47% | +6.0 | +0 | 0–18% | 1 | FLAG | base 47%, factors +6.0, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 53%; vs market pricing +6.0 pts; critic flagged it (The +1 is an artifact of a negative credit coefficient (-0.77) on a cyclical commodity sector. All models gave 0 sector-): tilt +1 -> +0 |
| Real Estate | 54% | 45% | +9.2 | +0 | 0–18% | 0 | FLAG | base 45%, factors +9.2, sector-specific +0.0 (models [-3.0, 0, 0, 0]) -> 54%; vs market pricing +9.2 pts; capped at +/-1 (only two full tilts allowed); critic flagged it (The +1 is credit-factor driven (SENS -1.03), but the sector-specific evidence points the other way. Mortgage rate is 7.2): tilt +1 -> +0 |
| Communication Services | 51% | 49% | +2.4 | +0 | 0–18% | -2 | PASS | base 49%, factors +2.4, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 51%; vs market pricing +2.4 pts |

Critic: **FLAG**. No tilt is clearly unsupported or contradicted, so none fails. But most non-zero tilts rest on one factor call: further credit widening (only Sonnet -2 and Gemini -1.5; Opus and Grok at 0), multiplied by each sector's credit sensitivity. That is a concentrated, correlated bet, and counter-evidence (strong profits, easing bank standards, loose NFCI) is only weakly weighed. Staples and Utilities carry the two full +2 tilts despite negative same-regime history. Materials and Real Estate are flagged because their tilts are mechanical credit-beta artifacts that run against sector fundamentals and history.

### Technology
**claude-sonnet-5** (+0.0 pts): Reflation history is mildly positive for Tech (HIST 1m +0.33, 3m +0.37) but Tech has by far the largest credit-spread sensitivity (SENS 1.38) and the factor view calls for further credit deterioration (-2) and modestly higher 10y rates (+10bp, SENS -0.0474), both headwinds. Momentum is already very negative (-10.5% 1m, -12.7% 6m vs SPY), consistent with the market pricing in the credit/rate stress ahead of the models.
- against: Starting probability of beating SPY in this regime is slightly above 50% (52.3%) and earnings momentum has been strong (C1/C2 estimate revisions, 35%+ Q3 EPS growth), which could offset credit-driven weakness. (survives: True)
**claude-opus-5-5** (+0.0 pts): Factor-driven: high credit sensitivity (1.38). Weak momentum (-10.46% over 1m).
- against: Momentum is not a sector-specific shock, and a credit retracement would favor tech. (survives: True)
**gemini-3.8-flash@paid (fallback)** (-1.0 pts): Severe underperformance over 1m (-10.46%) and 6m (-12.73%) reflects valuation compression in a high rate (10y at 4.85%) and widening credit spread environment.
- against: Earnings expectations for the S&P 500 remain robust, projected to exceed 35% growth (NOTE:C2), which Tech typically leads. (survives: True)
  - 📎 MOM:Technology
**xai:grok-4.3** (+0.0 pts): HIST shows modest outperformance in reflation; MOM negative
- against: High rates pressure growth stocks (survives: True)

### Financials
**claude-sonnet-5** (+0.0 pts): Financials benefit from a steeper curve historically but T10Y2Y is actually flattening (0.25 vs 0.47 3m ago) and credit factor deterioration is a modest net negative (SENS -0.044, small). Dollar strength is a net positive for Financials (SENS 0.26) which the factor view supports (+1%).
- against: Rapid HY spread widening historically precedes bank credit-quality concerns even if sector sensitivity to credit level is small; this could understate risk. (survives: False)
**claude-opus-5-5** (+0.0 pts): Loan growth of 7.5% and a steepish curve support the sector; no sector-specific shock.
- against: Rising HY spreads could foreshadow credit losses. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Financials benefit from higher short rates (2y at 4.61%) and loan growth (TOTLL +7.5% YoY, FRED:TOTLL: 7.5), showing solid momentum (+7.53% 1m vs SPY, MOM:Financials), but this is balanced by widening credit spreads (FRED:BAMLH0A0HYM2: 3.77). Neutral allocation is appropriate.
- against: Bank tightening standards have eased to 1.7% (FRED:DRTSCILM: 1.7), suggesting lending expansion could support an overweight. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST positive in regime; rising 2y yield supportive
- against: HY spread widening offsets (survives: True)

### Health Care
**claude-sonnet-5** (+0.0 pts): Health Care has strong negative credit sensitivity (-1.75) but credit view is only modestly negative; it also benefits from negative rates sensitivity being small and its defensive character fits elevated VIX/pullback risk. Momentum is strongly positive (+8.2%/+13.1%/+27.5% vs SPY).
- against: History in this exact regime is roughly flat (HIST 1m -0.02, 3m +0.01), suggesting momentum may be overextended relative to regime base rates. (survives: True)
**claude-opus-5-5** (+0.0 pts): Defensive; benefits via negative credit sensitivity if spreads keep widening.
- against: Already +13% vs SPY over 3m; no sector-specific catalyst. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Health Care provides robust defensive ballast during market volatility (VIX 26.8) and widening credit spreads (3.77%), with +27.49% 6-month excess return (MOM:Health Care).
- against: In historical Reflation regimes with Fed on hold, Health Care excess return is modest at +0.17% over 1 month (HIST:Health Care). (survives: True)
  - 📎 MOM:Health Care
**xai:grok-4.3** (+0.0 pts): HIST neutral; MOM strong
- against: none material (survives: True)

### Energy
**claude-sonnet-5** (+0.0 pts): Oil factor forecast is modestly positive (+4%) on fresh Hormuz escalation (mines hit two ships, Houthi strike on Saudi refinery) and steep backwardation signaling a real current squeeze (SENS oil sensitivity +0.32, the highest of any sector). Energy's 3-month regime history is strongly positive (+3.58% excess, 56% hit rate).
- against: IEA reports global oil supply now exceeds demand for the first time since the war began and oil has fallen 5% over 3 months despite the ongoing conflict, suggesting the supply-surplus narrative may dominate any escalation premium; OPEC+ meets Nov 29 and could add supply. (survives: True)
**claude-opus-5-5** (+0.0 pts): Oil exposure (0.32 per 1% oil) is handled by the oil factor; the 3m history is supportive (+3.55%).
- against: The IEA surplus and the OPEC+ binary make direction unclear. A Hormuz-related adjustment would double count oil. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Energy historically delivers +3.55% excess return over 3 months in Reflation with Fed on hold (HIST:Energy), and possesses the highest sensitivity to oil price increases (+0.3241, SENS:Energy).
- against: IEA reported global oil supply surpassed demand in October 2026 (NOTE:E13) and 1m momentum is -4.21% vs SPY (MOM:Energy). (survives: True)
  - 📎 CALC:risk_indicators
  - 📎 U.S. commercial crude oil inventories dropped to 410 million barrels at the end of October and are projected to stay below the five-year average through the middle of next year. (2026-11-10) https://www.eia.gov/outlooks/steo/
  - 📎 Oil tanker hit naval mine in restricted zone in Strait of Hormuz on November 26, 2026, caught fire; Iranian mines reportedly struck at least two ships (2026-11-26) https://www.cnbc.com/2026/11/26/oil-wti-brent-hormuz-iran-saudi-arabia.html
**xai:grok-4.3** (+0.0 pts): HIST strong 3m outperformance in regime
- against: recent oil price decline (survives: True)

### Industrials
**claude-sonnet-5** (+0.0 pts): Industrials show modestly positive 3m regime history (+0.67%) and limited sensitivity to the modest credit/rate moves forecast. No standalone catalyst strong enough for a sector-specific adjustment survives scrutiny (see shipping-cost argument below).
- against: Falling shipping rates (WCI -3% to $4,032) and more Suez transits could lower input costs, but Drewry attributes the decline to weak Transpacific demand, which is itself a negative demand signal for industrials, so the two effects roughly cancel. (survives: False)
**claude-opus-5-5** (+0.0 pts): Section 301 manufacturing actions are ambiguous in direction; no adjustment.
- against: Tariff protection could help or hurt input costs. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Industrials exhibit modest positive 1-month momentum (+3.96%, MOM:Industrials) supported by industrial production growth (+1.66% YoY, FRED:INDPRO: 1.66), but section 301 trade investigations (NOTE:B4) and high borrowing costs create cross-currents. Neutral is warranted.
- against: Historical hit rate in Reflation with Fed on hold is 59.3% with +0.39% excess return (HIST:Industrials). (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST positive in regime
- against: none material (survives: True)

### Consumer Discretionary
**claude-sonnet-5** (-2.0 pts): Consumer Discretionary has the largest negative inflation-expectations sensitivity (1.10) and benefits from inflation-exp forecast being down (-1%), but sentiment collapse is a genuine headwind historically underweighted by the factor table.
- against: Hard data contradicts the sentiment signal: retail sales YoY are accelerating sharply (6.82% vs 4.53% 3m ago) and sector momentum is strongly positive (+9.7%/+7.7% vs SPY); this is the strongest case against the adjustment but doesn't fully offset a record-low sentiment reading. (survives: True)
  - 📎 U. Michigan consumer sentiment = 48.0 (FRED UMCSENT, as of 2026-10-01)
**claude-opus-5-5** (+0.0 pts): Sentiment at 48 and a 7.21% mortgage rate weigh on the sector, but retail sales are up 6.82%, so these offset.
- against: Strong recent momentum (+9.72% over 1m). (survives: True)
**gemini-3.8-flash@paid (fallback)** (-1.0 pts): Discretionary spending is vulnerable to high financing costs, negative sensitivity to rate increases (-0.0714, SENS:Consumer Discretionary), and negative sensitivity to oil (+20% oil causes -1.42% vs SPY).
- against: Recent 1-month momentum is strong (+9.72% vs SPY, MOM:Consumer Discretionary) and retail sales YoY grew 6.82% (FRED:RSAFS: 6.82). (survives: True)
  - 📎 U. Michigan consumer sentiment = 48.0 (FRED UMCSENT, as of 2026-10-01)
  - 📎 Personal saving rate % = 4.1 (FRED PSAVERT, as of 2026-10-01)
  - 📎 30-yr mortgage rate % = 7.21 (FRED MORTGAGE30US, as of 2026-11-25)
**xai:grok-4.3** (+0.0 pts): HIST neutral to negative
- against: none material (survives: True)

### Consumer Staples
**claude-sonnet-5** (+0.0 pts): Staples' regime history is negative (3m -1.29% excess) and it has large negative credit sensitivity; with credit forecast negative this reinforces an underweight thesis, but momentum has been unusually strong (+12.4%/+14.3%/+16.5%) suggesting a defensive rotation is already underway given elevated VIX and pullback risk.
- against: Strong recent momentum directly contradicts the regime-history underweight case; no sector-specific catalyst to add beyond what factors already capture. (survives: False)
**claude-opus-5-5** (+0.0 pts): The defensive tilt is captured by credit sensitivity (-2.46).
- against: Reflation history is poor (-1.1% over 3m). (survives: True)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Consumer Staples exhibits elite defensive momentum (+12.42% 1m, +14.27% 3m vs SPY, MOM:Consumer Staples) as investors seek shelter from credit spread deterioration and high volatility.
- against: Historical regime returns for Staples during Reflation are negative (-0.37% 1m, HIST:Consumer Staples). (survives: True)
  - 📎 High-yield credit spread = 3.77 (FRED BAMLH0A0HYM2, as of 2026-11-26)
**xai:grok-4.3** (+0.0 pts): HIST underperformance in regime
- against: none material (survives: True)

### Utilities
**claude-sonnet-5** (+0.0 pts): Utilities show negative regime history (-1.23% 3m) and large negative credit sensitivity, consistent with the credit factor forecast being negative; but Utilities also carry the largest positive inflation-exp sensitivity in reverse (-1.37, so falling inflation-exp is a positive) and positive oil sensitivity (benefiting from oil factor +4%).
- against: These are all factor-driven effects already captured; no standalone sector-specific catalyst survives. (survives: False)
**claude-opus-5-5** (+0.0 pts): Factor-driven.
- against: Rate sensitivity cuts both ways. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Utilities benefit as credit spreads widen (-2.2342 credit sensitivity, SENS:Utilities) and have good 1m momentum (+8.61%, MOM:Utilities). However, high 10-year yields (4.85%, FRED:DGS10: 4.85) and negative historical regime performance (-0.50% 1m, HIST:Utilities) balance out the tailwinds.
- against: Strong negative sensitivity to inflation expectations (-1.3713, SENS:Utilities) could hurt if inflation re-accelerates. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST underperformance in regime
- against: none material (survives: True)

### Materials
**claude-sonnet-5** (+0.0 pts): Section 301 investigations into manufacturing overcapacity (B4) could theoretically weigh on Materials, but EPUTRADE trade-policy-uncertainty is actually falling (1400.8 vs 1631.6 3m ago, 2727 12m ago) and the data is stale (87 days), so the case for escalation doesn't hold up.
- against: Copper at a 98th-percentile reading (though also stale, 87 days) could flag genuine commodity-driven upside, but it's too stale to act on with confidence. (survives: False)
**claude-opus-5-5** (+0.0 pts): Copper is strong but its data are stale; Section 301 overcapacity actions may help domestic producers, but that is uncertain.
- against: Strong dollar hurts (-0.45 sensitivity). (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Copper prices are elevated ($14,473.1/MT, FRED:PCOPPUSDM: 14473.1) and momentum is positive (+6.26% 1m, MOM:Materials), but strong dollar (123.6, FRED:DTWEXBGS: 123.6) creates heavy drag (-0.4464 dollar sensitivity, SENS:Materials). Keep neutral.
- against: Trade policy uncertainty remains high at 1400.77 (FRED:EPUTRADE: 1400.77), which can depress global commodity demand. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST underperformance in regime
- against: none material (survives: True)
- 🔎 Critic FLAG: The +1 is an artifact of a negative credit coefficient (-0.77) on a cyclical commodity sector. All models gave 0 sector-specific points, same-regime history is negative at every window (3m -0.9%, 40% beat), and the copper and trade-policy data are stale. A cyclical sector gaining from credit stress is economically dubious, and Sonnet's own rationale found no supporting catalyst. Neutral would be more defensible.

### Real Estate
**claude-sonnet-5** (-3.0 pts): Real Estate's rates_10y sensitivity is already negative (-0.0292) and the forecasted +10bp rate move adds a small headwind, but the mortgage-specific spread widening and permit collapse represent a sharper, sector-specific deterioration in housing finance conditions.
- against: Real Estate's 3m regime-and-fed history is actually positive (+0.94%, 62.5% hit rate, though small sample n=16), and the sector could be oversold already given its negative 1m/3m excess history pattern; also permits data is lagged (Oct) and may not reflect current conditions. (survives: True)
  - 📎 30-yr mortgage rate % = 7.21 (FRED MORTGAGE30US, as of 2026-11-25)
  - 📎 Building permits (thousands, annual rate) = 1297.0 (FRED PERMIT, as of 2026-10-01)
**claude-opus-5-5** (+0.0 pts): The 7.21% mortgage rate and permits at the 0th percentile are negative, but this is largely a rates story.
- against: Same-regime-and-Fed 3m history is +0.94%, though on small n. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Real Estate carries high mortgage rate pressure (7.21%, FRED:MORTGAGE30US: 7.21) and falling building permits (1,297k, FRED:PERMIT: 1297). Despite strong recent momentum (+10.47% 1m, MOM:Real Estate), structural rate headwinds prevent an overweight tilt.
- against: Real Estate sensitivity to credit is -1.0304 (SENS:Real Estate), allowing it to act defensively in credit drawdowns. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST mixed; high mortgage rates
- against: none material (survives: True)
- 🔎 Critic FLAG: The +1 is credit-factor driven (SENS -1.03), but the sector-specific evidence points the other way. Mortgage rate is 7.21% (91.8th percentile), permits are at the 0th percentile, the 1m/3m regime history is negative, and the starting probability is 45% on a small n of 27. Sonnet's -3 housing-finance adjustment was dropped by the median. The tilt is not contradicted outright but is weakly grounded.

### Communication Services
**claude-sonnet-5** (+0.0 pts): Communication Services has modest negative regime history (3m -1.68%) but limited sensitivity to the factor moves forecast (oil ~0, credit -0.25, small). No standalone sector catalyst identified.
- against: n/a (survives: False)
**claude-opus-5-5** (+0.0 pts): Factor-driven.
- against: None material. (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Communication Services shows strong 1m momentum (+9.90%, MOM:Communication Services), but longer-term 6m momentum is negative (-3.31%). Historical return in Reflation with Fed on hold is modest (+0.36%, HIST:Communication Services). Neutral posture maintained.
- against: Relatively low sensitivity to credit (-0.2478, SENS:Communication Services) makes it fairly insulated from the HY spread spike. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST neutral
- against: none material (survives: True)

## Core variables vs consensus
- **PCEPILFE**: 3.26% YoY, rising from 2.7% a year ago | consensus: n/a | view: above  
  📎 Core PCE inflation YoY % = 3.26 (FRED PCEPILFE, as of 2026-10-31)
- **CPIAUCSL**: 4.08% YoY, up from 3.3% 3m ago | consensus: n/a | view: above  
  📎 CPI inflation YoY % = 4.08 (FRED CPIAUCSL, as of 2026-10-31)
- **CPILFESL**: 2.87% YoY, rising, 24th percentile 5yr | consensus: n/a | view: in line  
  📎 Core CPI inflation YoY % = 2.87 (FRED CPILFESL, as of 2026-10-31)
- **CES0500000003**: 3.12% YoY average hourly earnings, flat trend | consensus: n/a | view: in line  
  📎 Average hourly earnings YoY % = 3.12 (FRED CES0500000003, as of 2026-10-31)
- **UNRATE**: 4.1%, falling from 4.2% | consensus: matches SEP_UNRATEMD_2026 4.1 | view: in line  
  📎 Unemployment rate % = 4.1 (FRED UNRATE, as of 2026-10-01); SEP_UNRATEMD_2026 = 4.1 (FRED Fed projections)
- **PAYEMS**: +165k, improving from -10k 3m ago | consensus: n/a | view: above  
  📎 Payrolls monthly change (thousands) = 165.0 (FRED PAYEMS, as of 2026-10-31)
- **IC4WSA**: 196k, lowest in 5yr (1.64 pctile), falling | consensus: n/a | view: below (stronger labor mkt)  
  📎 Initial jobless claims, 4-wk avg = 196000.0 (FRED IC4WSA, as of 2026-11-21)
- **DFF**: 3.88%, on hold | consensus: SEP_FEDTARMD_2026 4.1 | view: below  
  📎 Fed funds effective rate % = 3.88 (FRED DFF, as of 2026-11-26); SEP_FEDTARMD_2026 = 4.1 (FRED Fed projections)
- **DGS2**: 4.61%, up sharply from 3.60% 12m ago, 78th pctile | consensus: market now pricing further hikes (2yr-fedfunds spread +0.73) | view: above  
  📎 2-yr Treasury yield % = 4.61 (FRED DGS2, as of 2026-11-25); CALC:market_implied_fed_path
- **DGS10**: 4.85%, 93rd pctile 5yr | consensus: markets price ~zero change | view: above  
  📎 10-yr Treasury yield % = 4.85 (FRED DGS10, as of 2026-11-25)
- **T10Y2Y**: 0.25, flattening from 0.47 3m ago but not inverted | consensus: n/a | view: in line  
  📎 10-yr minus 2-yr spread = 0.25 (FRED T10Y2Y, as of 2026-11-27)
- **BAMLH0A0HYM2**: 3.77, UNUSUAL z=+2.0, widening fast from 2.85 3m ago | consensus: markets price ~zero change | view: above (deteriorating)  
  📎 High-yield credit spread = 3.77 (FRED BAMLH0A0HYM2, as of 2026-11-26)
- **NFCI**: -0.44, looser than average, rising (tightening) from -0.53 | consensus: n/a | view: in line  
  📎 Chicago Fed financial conditions (negative = loose) = -0.44 (FRED NFCI, as of 2026-11-20)
- **DCOILWTICO**: $82.24, falling from $86.16 3m ago despite Hormuz disruption | consensus: EIA sees Brent near $100 near-term | view: below  
  📎 WTI crude oil $/bbl = 82.24 (FRED DCOILWTICO, as of 2026-11-24); EIA expects the Brent crude oil spot price to remain near $100 per barrel for the rest of the year before falling to an average of $77 per barrel in Q4 2027. (2026-11-10) https://www.eia.gov/outlooks/steo/
- **DCOILBRENTEU**: $91.80, falling from $96.95 3m ago | consensus: EIA near $100 | view: below  
  📎 Brent crude oil $/bbl = 91.8 (FRED DCOILBRENTEU, as of 2026-11-24)

## Scenarios
*claude-sonnet-5*: base (0.55): Reflation persists: inflation stays sticky/rising, labor market firm, Fed holds through December SEP; HY spreads widen further but don't trigger a disorderly credit event; oil stays choppy in the low-to-mid $80s/$90s on supply-surplus vs. Hormuz-threat tug-of-war.; downside (0.25): Credit stress accelerates (HY spread continues its 2-sigma widening), equity vol stays elevated (VIX 90th pctile, S&P below 200d), and/or Hormuz mine strikes escalate into actual tanker losses, spiking oil and triggering a risk-off repricing beyond what CALC:pullback_risk currently assigns.; upside (0.2): IEA-documented global oil supply surplus (105.4 mb/d vs falling demand) pushes oil lower, OPEC+ Nov 29 meeting signals discipline, Hormuz tensions de-escalate, and credit spreads stabilize; inflation prints (Dec 10 CPI) surprise down, easing both inflation and credit-stress narratives.
*claude-opus-5-5*: base (0.55): Growth holds and the Fed hikes or holds hawkishly on Dec 9. HY spreads stabilize around 3.5-4.0 and oil chops in a range around current levels as the OPEC+ outcome and Hormuz offset each other.; upside (0.2): Hormuz de-escalates or OPEC+ adds supply. Oil falls, spreads retrace toward 3.0, and volatility normalizes, favoring cyclicals and tech.; downside (0.25): Further Hormuz mine attacks or Gulf infrastructure hits spike oil, and the Fed hikes into tightening credit. HY spreads push above 4.5 and a 10% pullback materializes; defensives and energy outperform.
*gemini-3.8-flash@paid (fallback)*: base (0.6): Reflation persists with resilient domestic growth (GDP 4.3%) and sticky inflation (CPI 4.08%). The Fed stays on hold at the December 8-9 FOMC, while credit spread widening keeps financial risk appetite cautious.; downside (0.25): Credit spread blowout accelerates as high yields (30-yr mortgage at 7.21%, 10y at 4.85%) exacerbate private sector defaults, pulling the equity market into a formal correction with VIX spiking over 35.; upside (0.15): Oil supply pressures ease after the Nov 29 OPEC+ meeting, container freight rates continue falling (WCI down 3% to $4,032), inflation cools rapidly, and credit spreads compress back below 3.0%.
*xai:grok-4.3*: base (0.6): Reflation continues with on-hold Fed; HY spreads remain elevated but contained; upside (0.2): Faster disinflation allows earlier cuts; downside (0.2): Credit stress widens further triggering pullback

## Upcoming releases
- 2026-12-01: Job Openings and Labor Turnover Survey
- 2026-12-02: Gross Domestic Product by County
- 2026-12-04: Employment Situation
- 2026-12-07: Chicago Fed Advance Retail Trade Summary
- 2026-12-10: Consumer Price Index
- 2026-12-10: Consumer Price Index Excluding Energy Commodities
- 2026-12-10: Research Consumer Price Index
- 2026-12-15: Producer Price Index
- 2026-12-16: Advance Monthly Sales for Retail and Food Services
- 2026-12-16: Chicago Fed Advance Retail Trade Summary
- 2026-12-16: G.17 Industrial Production and Capacity Utilization
- 2026-12-16: Monthly Retail Trade and Food Services
- 2026-12-16: Selected Real Retail Sales Series
- 2026-12-23: Debt to Gross Domestic Product Ratios
- 2026-12-23: Gross Domestic Product
- 2026-12-23: Gross Domestic Product by Industry
- 2026-12-23: Gross Domestic Product by State
- 2026-12-23: Personal Income and Outlays

## Prediction scorecard
{"graded": 96, "hits": 37, "hit_rate_%": 38.5, "by_model": {"claude-opus-5-5": "16/25", "claude-sonnet-5": "5/28", "gemini-3.8-flash": "8/22", "gemini-3.8-flash (fallback)": "1/3", "gemini-3.8-flash@paid (fallback)": "1/3", "gemma-4-31b-it (fallback)": "1/3", "xai:grok-4.3": "5/12"}}

## Data quality
- High-yield credit spread: UNUSUAL (z=+2.0 vs 5-yr history)
- Copper $/metric ton: UNUSUAL (z=+2.7 vs 5-yr history), STALE (87 days old)
- Global food price index: STALE (87 days old)
- Trade policy uncertainty index: STALE (87 days old)
- Job openings (thousands): STALE (87 days old)
- Quits rate %: STALE (87 days old)
- Global all-commodity price index: STALE (87 days old)
- U.S. trade balance ($M): STALE (87 days old)
- Auditor removed (gemini-3.8-flash@paid (fallback), Technology): unrecognized reference 'SENS:Technology'
- Auditor removed (gemini-3.8-flash@paid (fallback), Health Care): unrecognized reference 'SENS:Health Care'
- Auditor removed (gemini-3.8-flash@paid (fallback), Consumer Staples): unrecognized reference 'SENS:Consumer Staples'

## Evidence notes
- NOTE:A1 The final scheduled FOMC meeting for 2026 is set for December 8-9 and is associated with a Summary of Economic Projections. (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- NOTE:A2 The minutes of the October 27-28, 2026 FOMC meeting were released on November 18, 2026. (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- NOTE:A3 Vice Chair for Supervision Michelle W. Bowman addressed modernizing supervisory frameworks following the SVB failure rather than indicating monetary policy bias. (https://www.federalreserve.gov/newsevents/speech/bowman20261125a.htm)
- NOTE:A4 The Beige Book was updated for November 2026 to characterize regional economic conditions across the 12 Districts. (https://www.federalreserve.gov/monetarypolicy/beigebook202611.htm)
- NOTE:B1 EIA expects the Brent crude oil spot price to remain near $100 per barrel for the rest of the year before falling to an average of $77 per barrel in Q4 2027. (https://www.eia.gov/outlooks/steo/)
- NOTE:B2 EIA forecasts the Henry Hub spot price for natural gas to average $2.87 per million British thermal units from November through March. (https://www.eia.gov/outlooks/steo/)
- NOTE:B3 U.S. commercial crude oil inventories dropped to 410 million barrels at the end of October and are projected to stay below the five-year average through the middle of next year. (https://www.eia.gov/outlooks/steo/)
- NOTE:B4 USTR issued determinations and proposed actions under Section 301 regarding structural excess capacity and production in manufacturing sectors. (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- NOTE:B5 USTR invited public comment on proposed modifications to Section 301 actions addressing Brazil's acts, policies, and practices. (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- NOTE:B6 Ambassador Greer issued a statement regarding the intent to terminate Rwanda and South Africa from the AGOA trade preference program. (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- NOTE:D1 In the January 2026 World Economic Outlook Update, global growth is projected at 3.3 percent for 2026 and 3.2 percent for 2027, revised slightly up from the October 2025 WEO. (https://www.imf.org/en/Publications/WEO)
- NOTE:D2 The Bank of England and other UK authorities completed their annual review of the Memorandum of Understanding on payment systems and concluded that no changes are needed. (https://www.bankofengland.co.uk/news/2024/march/payment-systems-memorandum-of-understanding)
- NOTE:E1 The Drewry World Container Index dropped 3% week-on-week to $4,032 per 40ft container. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E2 Suez Canal transits rose as more carriers returned to Red Sea routes, with 60 vessels transiting the prior week. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E3 Continued geopolitical uncertainty in the Strait of Hormuz remains a primary market concern. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E4 OFAC issued new Iran-related designations on November 23, 2026. (https://ofac.treasury.gov/recent-actions)
- NOTE:E5 OFAC published counter-narcotics and cyber-related designations, along with an amended Russia-related general license. (https://ofac.treasury.gov/recent-actions)
- NOTE:E6 OFAC issued an amended Iran-related General License on October 29, 2026. (https://ofac.treasury.gov/recent-actions)
- NOTE:C1 Analysts raised EPS estimates for S&P 500 companies for the second straight quarter heading into Q3. (https://insight.factset.com/topic/earnings/page/2)
- NOTE:C2 FactSet reported that the S&P 500 was projected to deliver third-quarter earnings growth exceeding 35%. (https://insight.factset.com/topic/earnings/page/2)
- NOTE:C3 Managed money held 20,031 long contracts and 19,819 short contracts in ICE Light Sweet Crude Oil futures. (https://www.cftc.gov/dea/futures/petroleum_sf.htm)
- NOTE:E1 Ukraine struck Russian navy corvette Merkury with seven sea drones in Libya on November 23, 2026, sinking one of Russia's newest ships commissioned in 2023 (https://www.cnbc.com/2026/11/23/ukraine-russia-warship-libya.html)
- NOTE:E2 Ukrainian drones struck Kerch Bridge linking Russia to Crimea on November 17, 2026, with road span collapsing and railway arch damaged (https://www.npr.org/2026/11/17/g-s1-153946/russia-ukraine-war)
- NOTE:E3 Ukrainian drones struck two oil refineries in Samara region on November 25, 2026, causing them to catch fire (https://www.cfr.org/global-conflict-tracker/conflict/conflict-ukraine)
- NOTE:E4 Russian missiles landed in Polish territory on November 20, 2026, 37 miles from Ukrainian border during Russian strikes on Ukraine (https://www.cfr.org/global-conflict-tracker/conflict/conflict-ukraine)
- NOTE:E5 Russian cargo ship struck by presumed Ukrainian drone in Baltic Sea off Finnish coast on November 21, 2026, caught fire (https://www.npr.org/2026/11/22/nx-s1-6050236/ukraine-war-spilling-into-nato-territory)
- NOTE:E6 Strait of Hormuz has been effectively closed to commercial shipping since February 28, 2026, disrupting 30% of global fertilizer supply and 25% of global oil maritime trade (https://www.cnbc.com/2026/11/26/oil-wti-brent-hormuz-iran-saudi-arabia.html)
- NOTE:E7 Oil tanker hit naval mine in restricted zone in Strait of Hormuz on November 26, 2026, caught fire; Iranian mines reportedly struck at least two ships (https://www.cnbc.com/2026/11/26/oil-wti-brent-hormuz-iran-saudi-arabia.html)
- NOTE:E8 Suez Canal transits increasing as carriers resume Red Sea routings; 60 vessels transited last week (as of November 26, 2026) (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E9 Drewry World Container Index decreased 3% to $4,032 per 40ft container as of November 26, 2026, driven by lower Transpacific rates amid weak demand (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E10 WCI declined 3% week-over-week on November 26, 2026; down from $4,176 on November 19 (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E11 Seven core OPEC+ members (Saudi Arabia, Russia, Iraq, Kuwait, Algeria, Kazakhstan, Oman) maintained December 2026 production targets at September 2026 levels in virtual meeting on November 1, 2026 (https://www.opec.org/pr-detail/620-1-november-2026.html)
- NOTE:E12 OPEC+ full 21-country group scheduled to meet on November 29, 2026 to decide 2027 production quotas and framework (https://www.opec.org/pr-detail/620-1-november-2026.html)
- NOTE:E13 Global oil supplies surpassed demand for first time since outbreak of Iran war; global oil supply rose 2.3 mb/d to 105.4 mb/d in October 2026 (https://www.iea.org/reports/oil-market-report-november-2026)
- NOTE:E14 World oil demand forecast to fall by 2.7 mb/d in 2026 to 102.3 mb/d, before rebounding by 2 mb/d in 2027 (https://www.iea.org/reports/oil-market-report-november-2026)
- NOTE:E15 Iran war since February 2026 caused cumulative loss of 2.8 billion barrels of oil and 60 billion cubic metres of gas supply from Gulf; described as largest energy supply shock world has faced (https://www.iea.org/reports/world-energy-outlook-2026/executive-summary)
- NOTE:E16 Yemen's Houthis claimed to have hit Saudi Arabia's largest oil refinery on November 25, 2026 (https://www.cnbc.com/2026/11/26/oil-wti-brent-hormuz-iran-saudi-arabia.html)
- NOTE:E17 Russia lodged formal protest against Estonia on November 25, 2026 over decision to close border crossings with Russia effective December 1, 2026 (https://www.cfr.org/global-conflict-tracker/conflict/conflict-ukraine)

## Direct-fetch sources (fix URLs in pipeline/fetch.py if one keeps failing)
- A fed_policy: read, nothing extracted (https://www.federalreserve.gov/newsevents/pressreleases/monetary20261124a.htm)
- A fed_speeches: used (https://www.federalreserve.gov/newsevents/speech/bowman20261125a.htm)
- A fomc_calendar: used (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- A beige_book: used (https://www.federalreserve.gov/monetarypolicy/beigebook202611.htm)
- B truflation: read, nothing extracted (https://truflation.com/)
- B cleveland_nowcast: read, nothing extracted (https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting)
- B eia_steo: used (https://www.eia.gov/outlooks/steo/)
- B eia_weekly: read, nothing extracted (https://www.eia.gov/petroleum/supply/weekly/)
- B ustr: used (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- B treasury_refunding: read, nothing extracted (https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding)
- D ism_manufacturing: too little readable text (JavaScript page?) (https://ecommerce.ismworld.org/SSO/Login.aspx?DPLF=Y&vi=10&vt=c8b43443c4bb600499864728e27606ca908b808070ef30d71524ccb4af9e81eb570259f09bee69c8d8b85f697ece692eb58dc768dfa70a728284ef317164fb4f5bfd87a2938b32d49453ebbfbf18d824b0c0c99d3c87c51708db8d4eaeefc2780f09cf91fea0a3b9f809feb3c6464eb3)
- D ecb: read, nothing extracted (https://www.ecb.europa.eu//press/govcdec/otherdec/2026/html/ecb.gc261127~13ecadc0f2.en.html)
- D boe: used (https://www.bankofengland.co.uk/news/2024/march/payment-systems-memorandum-of-understanding)
- D boj: read, nothing extracted (http://www.boj.or.jp/en/research/wps_rev/rev_2026/rev26e14.htm)
- D imf_weo: used (https://www.imf.org/en/Publications/WEO)
- D oecd_outlook: page unavailable (https://www.oecd.org/en/publications/oecd-economic-outlook_16097408.html)
- E eia_twip: read, nothing extracted (https://www.eia.gov/petroleum/weekly/)
- E ofac_actions: used (https://ofac.treasury.gov/recent-actions)
- E iea_omr: page unavailable (https://www.iea.org/topics/oil-market-report)
- E drewry_wci: used (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- E gpr_index: read, nothing extracted (https://www.matteoiacoviello.com/gpr.htm)
- C factset: used (https://insight.factset.com/topic/earnings/page/2)
- C fedwatch: HTTPSConnectionPool(host='www.cmegroup.com', port=443): Read timed out. (read timeout=30) (https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html)
- C nyfed_nowcast: read, nothing extracted (https://www.newyorkfed.org/research/policy/nowcast)
- C aaii: read, nothing extracted (https://www.aaii.com/sentimentsurvey)
- C cftc_petroleum: used (https://www.cftc.gov/dea/futures/petroleum_sf.htm)
- C shiller: read, nothing extracted (https://shillerdata.com/)

_Model cost so far ≈ $0.52. Full receipts in sources.csv and full_run.json._