# Macro view, 2026-11-20
**Status: OK**

Why this run: tripwire: S&P 500 down -8.6% in a week

## ⚠️ Off-cycle triggers
- S&P 500 down -8.6% in a week

## Regime
Code: **Reflation (growth up, inflation up)**, Fed on hold

## Market & recession risk
Recession within 12 months: 30% (elevated; typical 23%). S&P 500 10%+ pullback within 3 months: 15% (normal; typical 13%).

**Recession within 12 months: 30%** (typical 23%; model trained on 658 months since 1971; out-of-sample accuracy AUC 0.874 since 1990-01, Brier skill 13.2%)

| Input | Now | Push on risk |
|---|---|---|
| S&P 500, 6-month return (%) | -8.835 | +0.98 |
| 10-yr minus 3-month Treasury spread (pts) | 0.713 | +0.80 |
| Chicago Fed financial conditions (above 0 = tighter than average) | -0.475 | -0.79 |
| Sahm rule, real time (0.5+ has marked every recession start) | 0.0 | -0.03 |
| Jobless claims, 6-month change (%) | -4.301 | +0.01 |

Benchmarks: NY Fed-style yield-curve model 16%; Chauvet-Piger probability we're in a recession now 0% (as of 2026-09-01)

**S&P 500 pullback of 10%+ within 3 months: 15%** (typical 13%; model trained on 484 months since 1986; out-of-sample accuracy AUC 0.68 since 2000-01, Brier skill -1.8%)

| Input | Now | Push on risk |
|---|---|---|
| S&P 500 vs its 200-day average (%) | -5.963 | +0.36 |
| S&P 500 1-month realized volatility (log) | -1.363 | +0.19 |
| Baa corporate bond spread over 10-yr Treasury (pts) | 1.56 | -0.12 |
| Baa spread, 3-month change (pts) | -0.07 | -0.05 |
| Chicago Fed financial conditions | -0.478 | -0.05 |
- Tested input *Geopolitical Risk Index, 30-day average (log)*: not kept (accuracy 0.68 → 0.676)
- Tested input *Economic policy uncertainty, 30-day average (log)*: not kept (accuracy 0.68 → 0.669)

| Indicator | Now | As of | Reading |
|---|---|---|---|
| Yield curve (10y - 3m) | 0.71 | 2026-11-20 | positive; inverted 0 of the last 24 months |
| Sahm rule (real time) | 0.0 | 2026-10-01 | calm |
| High-yield credit spread | 3.52 | 2026-11-19 | 92th percentile since 2023; widening |
| Chicago Fed financial conditions (NFCI) | -0.48 | 2026-11-13 | looser than average |
| S&P 500 vs 200-day average | -6.0% | 2026-11-20 | below (downtrend) |
| S&P 500 1-month volatility | 26% | 2026-11-20 | 92th percentile since 1970 (stressed) |
| Geopolitical Risk Index (30-day avg) | 151.5 | 2026-11-16 | 91th percentile since 1985 (elevated) |
| Economic policy uncertainty (30-day avg) | 295.3 | 2026-11-19 | 95th percentile since 1985 (elevated) |
| Trade policy uncertainty (monthly) | 1400.8 | 2026-09-01 | 96th percentile since 1985 (elevated) |
| Oil volatility (OVX) | 50.7 | 2026-11-19 | 86th percentile since 2007 (elevated) |
| Oil futures curve (front vs ~6 months out) | +7.8% | 2026-11-20 | steep backwardation: oil is scarce NOW (real supply squeeze) |
| Jobless claims, 6-month change | -4% | 2026-11-14 | stable |

*Statistical models on public data: they flag risky periods, with false alarms; they don't time tops.*

## Oil shock: sector return vs SPY if oil moves 20%
| Sector | Oil up | Oil down |
|---|---|---|
| Energy | +6.5% | -6.5% |
| Utilities | +1.5% | -1.5% |
| Real Estate | +1.3% | -1.3% |
| Health Care | +0.3% | -0.3% |
| Consumer Staples | +0.2% | -0.2% |
| Communication Services | -0.0% | +0.0% |
| Financials | -0.1% | +0.1% |
| Materials | -0.1% | +0.1% |
| Technology | -0.5% | +0.5% |
| Industrials | -0.6% | +0.6% |
| Consumer Discretionary | -1.4% | +1.4% |

- *claude-sonnet-5*: Growth is accelerating (GDPNow 3.21%, retail sales YoY 6.82%, payrolls +165k) while inflation is reaccelerating (CPI 4.08% YoY rising, core CPI 2.87% rising, core PCE 3.12%) — a genuine Reflation regime, confirmed by CALC:regime. But this is happening alongside a violent equity drawdown (tripwire: SPX -8.6%/week), VIX at 92nd percentile, HY spreads widening to 86-92nd percentile, and an actual physical oil-supply shock (Hormuz effectively closed since Feb 2026). The recession model (p=0.299, elevated vs 0.229 typical) is being pulled up mainly by the S&P 500's own 6-month return and NFCI is still loose (-0.48), so the model likely understates how much of this is a liquidity/geopolitics shock rather than a classic growth-rolling-over recession; the yield-curve sub-model (0.162) is far more sanguine, consistent with a positive 10s2s curve (0.29) that has not inverted. Pullback risk (0.15 vs 0.132 typical, 'normal' label) looks stale given VIX at a 92nd-percentile stressed reading and SPX -6% below its 200dma — the model's own top driver (S&P vs 200dma) is already flashing red, so I weight the pullback risk higher than the model's 'normal' label implies.
- *claude-opus-5-5*: Reflation confirmed: growth firm (GDP 3.4%, GDPNow 3.21, payrolls +165k, claims 4wk 197,750 near 5yr lows, retail sales +6.82% YoY) and inflation rising (CPI 4.08 from 3.3, import prices +9.23). The -8.6% weekly equity drop is a rates/geopolitical shock, not a growth scare: 10y at 5.04 (96.7 pctl), 2y 4.76 with 2y-FF 0.88 pricing hikes, dot plot 2026 median 4.1 vs DFF 3.88 implies a December hike, and Hormuz closure plus attacks on Saudi infrastructure. Recession model p=0.299 vs 0.229 typical: agree it is elevated but not alarming; Sahm 0, NFCI loose -0.48, bank standards easing (1.7) and low claims argue against near-term recession. Pullback model p=0.15 (normal) likely understates risk; its AUC is only 0.68 and it under-weights HY widening (2.85->3.52), VIX 28.44, S&P 6% below its 200-day, 92nd-pctl volatility, escalating geopolitics (GPR 91st pctl) and a binary FOMC. I'd put a further 10% drawdown nearer 0.25.
- *gemini-3.8-flash@paid (fallback)*: The economy remains in Reflation with growth running above trend (Q3 GDP 3.4%, Atlanta Fed GDPNow at 3.21%) and inflation reaccelerating (CPI YoY at 4.08%, Core PCE at 3.12%). The Fed is officially on hold with the effective funds rate at 3.88%, but markets are actively pricing further tightening with 2-year yields at 4.76% (88 bp above funds rate). However, an acute geopolitical and supply shock in the Persian Gulf has triggered severe market stress, marked by an emergency tripwire (-8.6% weekly plunge in the S&P 500) and VIX jumping to 28.44. While CALC:recession_risk sits at an elevated 29.9% and CALC:pullback_risk shows 15.0%, the pullback model understates the immediate risk given that the market is already down -6.0% below its 200-day moving average and realized 1-month volatility has spiked to 26%.
- *xai:grok-4.3*: Reflation (growth up, inflation up) with Fed on hold; S&P -8.6% weekly drop and VIX 28.44 signal stress but recession_risk 0.299 remains only mildly elevated vs typical 0.229 while pullback_risk 0.15 is normal.

## Economic forecast (median of the models, next 4 weeks)
- bp change in the 10-yr Treasury yield: +0
- % change in WTI crude: +4
- % change in the dollar (UUP): +0
- % change in HYG/IEF (up = credit spreads tightening): -0.75
- % change in TIP/IEF (up = inflation expectations rising): +0

## Sector probabilities and tilts
| Sector | P(beat SPY) | Base rate | vs market pricing | Tilt | Weight range | Momentum rule | Critic | How decided |
|---|---|---|---|---|---|---|---|---|
| Technology | 39% | 52% | -12.5 | -1 | 0–10% | 0 | PASS | base 52%, factors -12.5, sector-specific +0.0 (models [0.0, 0.0, -1.0, 0]) -> 39%; vs market pricing -12.5 pts; capped at +/-1 (only two full tilts allowed) |
| Financials | 49% | 49% | -0.2 | +0 | 0–18% | 0 | PASS | base 49%, factors -0.2, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 49%; vs market pricing -0.2 pts |
| Health Care | 65% | 52% | +12.8 | +1 | 5–22% | 1 | PASS | base 52%, factors +12.8, sector-specific +0.0 (models [0.0, 0.0, 1.0, 0]) -> 65%; vs market pricing +12.8 pts; capped at +/-1 (only two full tilts allowed) |
| Energy | 65% | 47% | +18.3 | +1 | 5–22% | 2 | FLAG | base 47%, factors +16.8, sector-specific +1.5 (models [0.0, 1.0, 2.0, 2.0]) -> 65%; vs market pricing +18.3 pts; critic flagged it (Double counting: the +1.5 sector-specific points rest on Hormuz closure and backwardation (+7.8%), which are already the): tilt +2 -> +1 |
| Industrials | 52% | 54% | -1.5 | +0 | 0–18% | -1 | PASS | base 54%, factors -1.5, sector-specific +0.0 (models [-1.0, 0, 0, 0]) -> 52%; vs market pricing -1.5 pts |
| Consumer Discretionary | 41% | 49% | -7.7 | -1 | 0–10% | -1 | PASS | base 49%, factors -7.7, sector-specific +0.0 (models [0.0, 0.0, -1.0, 0]) -> 41%; vs market pricing -7.7 pts; capped at +/-1 (only two full tilts allowed) |
| Consumer Staples | 67% | 47% | +19.5 | +1 | 5–22% | 2 | FLAG | base 47%, factors +19.5, sector-specific +0.0 (models [0.0, 0.0, 1.0, 0]) -> 67%; vs market pricing +19.5 pts; critic flagged it (The +2 comes almost entirely from the credit-widening factor (beta -2.41), which only two of four models forecast. Regim): tilt +2 -> +1 |
| Utilities | 65% | 47% | +17.4 | +0 | 0–18% | -2 | FLAG | base 47%, factors +17.4, sector-specific +0.0 (models [0.0, 0.0, 1.0, 0]) -> 65%; vs market pricing +17.4 pts; capped at +/-1 (only two full tilts allowed); critic flagged it (Rests on the same credit factor. Regime history is negative (-1.32% 3m, 40% beat), 10y is at 5.04% (96.7th percentile) a): tilt +1 -> +0 |
| Materials | 53% | 47% | +5.7 | +0 | 0–18% | 1 | FLAG | base 47%, factors +5.7, sector-specific +0.0 (models [0.0, 0.0, 0, 0]) -> 53%; vs market pricing +5.7 pts; critic flagged it (The +5.7 pt factor effect comes mainly from the odd sign of a negative credit beta (spread widening helps), against nega): tilt +1 -> +0 |
| Real Estate | 54% | 44% | +10.3 | +0 | 0–18% | 0 | FLAG | base 44%, factors +10.3, sector-specific +0.0 (models [0, 0.0, 0, 0]) -> 54%; vs market pricing +10.3 pts; capped at +/-1 (only two full tilts allowed); critic flagged it (Rests on the credit and inflation-expectation betas, but mortgage rates of 7.28% (95th percentile) and permits at the 0t): tilt +1 -> +0 |
| Communication Services | 51% | 48% | +3.0 | +0 | 0–18% | -2 | FLAG | base 48%, factors +3.0, sector-specific +0.0 (models [0.0, 0, 0, 0]) -> 51%; vs market pricing +3.0 pts; critic flagged it (The +3 pt factor effect is thin and all models gave 0 sector-specific points. Regime history is negative (-1.79% 3m, 36.): tilt +1 -> +0 |

Critic: **FLAG**. No tilt is clearly contradicted by its evidence, so none fails. The defensive and risk-off tilts (Staples, Utilities, Health Care, Real Estate, Technology, Consumer Discretionary) all lean on one credit-widening forecast that only two of four models hold, and the market prices no change. Energy has mild double counting. Materials, Communication Services and Real Estate rest on weak factor residuals against negative regime history.

### Technology
**claude-sonnet-5** (+0.0 pts): Factor-driven: rates +10bp hurts (beta -0.0462), credit widening -3 hurts sharply (beta 1.3508, largest credit sensitivity of any sector), partly offset by nothing; momentum already -8.57% 1m vs SPY confirms weakness.
- against: Earnings revisions have been positive for 2 straight quarters (NOTE:C1), which could cushion the credit-driven drag, but that's a fundamentals point not captured by weekly factor betas and doesn't survive as a sector adjustment distinct from factors. (survives: False)
**claude-opus-5-5** (+0.0 pts): Led the selloff (1m -8.57 vs SPY) via rate sensitivity; factors capture it.
- against: Prior -1 assumed continued rate pressure, but no sector-specific evidence and the sector is oversold; regime history is mildly positive. (survives: False)
**gemini-3.8-flash@paid (fallback)** (-1.0 pts): High-duration tech equities suffer when 10-year yields hold above 5% and credit spreads widen.
- against: Historical ref/hold regime excess return is mildly positive (+0.23% 1m), and tech may bounce after an -8.6% index drop. (survives: True)
  - 📎 MOM:Technology
  - 📎 10-yr Treasury yield % = 5.04 (FRED DGS10, as of 2026-11-19)
**xai:grok-4.3** (+0.0 pts): HIST:Technology same_regime_1m +0.3; MOM -8.57
- against: SENS rates_10y -0.0462 would hurt if yields rise further (survives: True)

### Financials
**claude-sonnet-5** (+0.0 pts): Dollar strength (+1%) helps (beta 0.2708); rates/credit roughly neutral given small betas; momentum strong (+6.03% 1m).
- against: Widening HY spreads should hurt bank credit books, but Financials' credit beta is near zero (-0.0024) historically, so this doesn't survive as an extra adjustment. (survives: False)
**claude-opus-5-5** (+0.0 pts): Steeper hike pricing helps NIM, but the flattening curve offsets; neutral.
- against: n/a (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Benefits from high short rates and positive net interest margins (bank loans up 7.48% YoY), but offset by credit spread widening (3.52) and stock market volatility.
- against: Tightening loan standards and commercial real estate exposure could lead to credit write-downs. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST:Financials same_regime_1m +0.41; MOM +6.03
- against: yield curve flattening T10Y2Y 0.29 (survives: True)

### Health Care
**claude-sonnet-5** (+0.0 pts): Large negative credit beta (-1.7407) means spread-widening (-3) is a big positive for Health Care as a defensive haven; also benefits from any further disinflation surprise given negative inflation_exp beta, momentum already strong (+7.47/+11.27/+26.24).
- against: None of the notes point to a HC-specific regulatory or tariff event this cycle strong enough to offset the rotation argument. (survives: False)
**claude-opus-5-5** (+0.0 pts): Defensive bid already in momentum (+7.47 1m); factor model handles it.
- against: Prior +1 lacked a sector-specific catalyst. (survives: False)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Health care offers defensive cash flows, insulating investors from growth shocks and credit widening.
- against: High 10-year yields typically pressure dividend and long-duration defensive equities. (survives: True)
  - 📎 MOM:Health Care
  - 📎 MOM:Health Care
**xai:grok-4.3** (+0.0 pts): HIST:Health Care same_regime_1m +0.03; MOM +7.47
- against: SENS inflation_exp -0.7737 (survives: True)

### Energy
**claude-sonnet-5** (+0.0 pts): Oil +6% forecast feeds through the largest oil beta (+0.3244) for a clearly positive Energy tilt; geopolitical risk (Hormuz closure, Houthi attacks on Saudi infrastructure) is the direct driver already expressed via the oil factor.
- against: IEA reports global supply actually rose 2.3mb/d in October and projects a further 2027 rebound to 108.1mb/d with demand falling 2.7mb/d in 2026 — a glut narrative that could cap oil upside and argues against adding extra sector points beyond the factor pass-through. This argument is strong enough that I decline to add a discretionary sector adjustment on top of the oil factor. (survives: False)
**claude-opus-5-5** (+1.0 pts): Oil +3% factor plus a small physical-scarcity tilt.
- against: Oil factor already captures most of this; IEA sees a 6.6 mb/d supply rebound in 2027 and an OPEC+ quota increase risk on Nov 29; 1m momentum -0.74. (survives: True)
  - 📎 IEA November 2026 report states global oil supply rose 2.3 mb/d to 105.4 mb/d in October; Gulf exports (ex-Oman) reached 18.4 mb/d, 26% below pre-war levels. 2027 supply projected to rebound 6.6 mb/d to 108.1 mb/d. (2026-11-13) https://www.iea.org/reports/oil-market-report-november-2026
  - 📎 CALC:risk_indicators
  - 📎 HIST:Energy
**gemini-3.8-flash@paid (fallback)** (+2.0 pts): Energy directly benefits from elevated crude prices ($89-$93/bbl) and persistent supply risk in the Middle East.
- against: IEA projects 2026 global oil demand to fall by 2.7 mb/d, which could limit further equity upside if macroeconomic demand softens. (survives: True)
  - 📎 HIST:Energy
  - 📎 Strait of Hormuz has been effectively closed since February 28, 2026 due to Iranian control. Iran warns strait remains closed until U.S. accepts Iranian conditions; only four vessels crossed as of November 19. (2026-11-19) https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry
  - 📎 CALC:risk_indicators
**xai:grok-4.3** (+2.0 pts): HIST:Energy same_regime_3m +3.75; SENS oil 0.3244
- against: EIA expects gradual decline to 77 by 2027 Q4 (survives: True)
  - 📎 CALC:risk_indicators
  - 📎 WTI crude oil $/bbl = 89.53 (FRED DCOILWTICO, as of 2026-11-17)
- 🔎 Critic FLAG: Double counting: the +1.5 sector-specific points rest on Hormuz closure and backwardation (+7.8%), which are already the basis of the +3 to +6% oil factor view. Grok set oil change to 0 as 'already priced', then added +2 on the same backwardation and cited a null evidence value. The oil factor alone gives about 64%, so +2 is defensible, but the extra points are not independent. IEA supply and demand and EIA's decline to $77 by Q4 2027 are acknowledged counter-evidence.

### Industrials
**claude-sonnet-5** (-1.0 pts): Small negative trade-volume signal on top of modestly negative oil/rate betas.
- against: Falling freight rates could simply reflect lower input costs (helpful for Industrials margins) rather than a demand problem; GDPNow and retail sales are both strong, arguing against a trade-slowdown story. (survives: True)
  - 📎 Drewry World Container Index decreased 3% to $4,176 per 40ft container as of November 19, 2026, down for fourth consecutive week. Shanghai to New York rates fell 9% to $8,194, lowest in 15 weeks. (2026-11-19) https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry
**claude-opus-5-5** (+0.0 pts): Neutral; container rates falling helps modestly, captured by the macro picture.
- against: n/a (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Balanced between strong domestic production (INDPRO +2.15% YoY) and container shipping disruptions/higher fuel costs.
- against: Supply chain snarls around Hormuz and Cape rerouting will compress industrial margins. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST:Industrials same_regime_3m +0.74; MOM +3.49
- against: SENS dollar 0.0727 (survives: True)

### Consumer Discretionary
**claude-sonnet-5** (+0.0 pts): Negative rates beta, negative oil beta, but large positive credit/inflation_exp betas; net factor push is negative given rates up and credit tighter (spreads wider).
- against: Retail sales YoY is strong at 6.82% and rising, which argues for consumer resilience, but this is already reflected in momentum (+7.49% 1m) not a forward-looking edge. (survives: False)
**claude-opus-5-5** (+0.0 pts): Weak sentiment (48) and a 7.28% mortgage rate versus strong retail sales (+6.82%); offsetting.
- against: Prior -1 contradicted by +7.49 1m momentum and strong sales. (survives: False)
**gemini-3.8-flash@paid (fallback)** (-1.0 pts): Discretionary spending is vulnerable to high borrowing costs, gasoline prices ($3.81/gal), and inflation eroding real disposable income.
- against: Retail sales YoY printed robustly at 6.82% in October, indicating consumer resilience. (survives: True)
  - 📎 30-yr mortgage rate % = 7.28 (FRED MORTGAGE30US, as of 2026-11-19)
  - 📎 Personal saving rate % = 3.8 (FRED PSAVERT, as of 2026-09-01)
  - 📎 U. Michigan consumer sentiment = 48.0 (FRED UMCSENT, as of 2026-10-01)
**xai:grok-4.3** (+0.0 pts): HIST:Consumer Discretionary same_regime_1m -0.1
- against: MOM +7.49 (survives: True)

### Consumer Staples
**claude-sonnet-5** (+0.0 pts): Large negative credit beta (-2.4144) means spread widening (-3) is a strong positive; defensive momentum already running hot (+10.23% 1m).
- against: None strong enough; staples typically underperform in true reflation 3m windows (HIST avg -1.0% to -1.23%), which caps conviction but doesn't flip the factor-driven positive tilt. (survives: False)
**claude-opus-5-5** (+0.0 pts): Defensive momentum already priced (+10.23 1m); regime history negative (-1.0 3m).
- against: Prior +1 had no sector-specific basis. (survives: False)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Inelastic demand protects revenue streams while food commodity prices have stabilized (+0.16 z-score).
- against: Historically underperforms in Reflation regimes (-1.0% over 3m) when cyclical reflation leads. (survives: True)
  - 📎 MOM:Consumer Staples
  - 📎 MOM:Consumer Staples
**xai:grok-4.3** (+0.0 pts): HIST:Consumer Staples same_regime_1m -0.16; MOM +10.23
- against: SENS credit -2.4144 (survives: True)
- 🔎 Critic FLAG: The +2 comes almost entirely from the credit-widening factor (beta -2.41), which only two of four models forecast. Regime history is negative (-1.0% 3m, 38.5% beat) and 1m momentum is already +10.23, so the move may be crowded. The factor push is real, but this is the highest-conviction defensive tilt on a single contested input.

### Utilities
**claude-sonnet-5** (+0.0 pts): Largest negative credit beta (-2.1941) and large negative inflation_exp beta (-1.438) both argue for Utilities outperforming on wider spreads/falling breakevens; oil-shock table also shows positive Utilities exposure to higher oil (+1.46 at oil+20%).
- against: Utilities underperform in HIST reflation samples (-0.61% to -1.32%), a real tension with the factor-implied tailwind. (survives: False)
**claude-opus-5-5** (+0.0 pts): Regime history negative (-1.32 3m); the inflation-expectations factor is a small drag.
- against: Prior +1 had no sector-specific basis. (survives: False)
**gemini-3.8-flash@paid (fallback)** (+1.0 pts): Utilities provide critical domestic cash flow stability amid escalating geopolitical uncertainty.
- against: Benchmark 10-year yield at 5.04% creates strong yield competition and negative historical excess return (-1.32% 3m in Reflation/Hold). (survives: True)
  - 📎 MOM:Utilities
**xai:grok-4.3** (+0.0 pts): HIST:Utilities same_regime_1m -0.61
- against: SENS rates_10y 0.0812 (survives: True)
- 🔎 Critic FLAG: Rests on the same credit factor. Regime history is negative (-1.32% 3m, 40% beat), 10y is at 5.04% (96.7th percentile) against a positive rates beta, and momentum is already +9.29. All sector-specific arguments were weak or offset.

### Materials
**claude-sonnet-5** (+0.0 pts): Large negative dollar beta (-0.4464) is a headwind given dollar +1% forecast; otherwise small factor exposures.
- against: Copper at a 98th-percentile reading (though stale, 80 days old) suggests underlying demand strength that could offset dollar headwind, but staleness limits confidence to use it as an adjustment. (survives: False)
**claude-opus-5-5** (+0.0 pts): Gold collapse (4697.8 to 3539) hurts miners, but copper is very strong; net neutral.
- against: The gold drop is already priced. (survives: False)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Supported by copper prices at $14,473/t (z=+2.7), but offset by dollar strength (122.65) and global demand deceleration.
- against: Dollar strength directly penalizes materials (dollar sensitivity -0.4464). (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST:Materials same_regime_1m -0.34; MOM +3.23
- against: copper 98th pct but stale (survives: True)
- 🔎 Critic FLAG: The +5.7 pt factor effect comes mainly from the odd sign of a negative credit beta (spread widening helps), against negative regime history (-0.84% 3m) and a dollar headwind (-0.45 beta). The copper signal is stale (80 days) and gold has fallen from 4698 to 3539. All four models put sector-specific points at 0, so the tilt is weakly supported.

### Real Estate
**claude-sonnet-5** (+0.0 pts): Negative credit beta (-0.9594) and negative inflation_exp beta (-0.5688) both favor Real Estate from wider spreads/falling breakevens, but rates +10bp is a modest headwind (beta -0.0338, small).
- against: Mortgage rates have spiked to 7.28% (95th percentile) and permits are falling (-1.54z), both real-economy negatives for REITs not fully captured by the weekly factor beta on rates. (survives: True)
**claude-opus-5-5** (+0.0 pts): Permits at their 5yr low and mortgage rate 7.28 are housing-negative, but REIT rate sensitivity is small and momentum is strong.
- against: A cut fails against +9.56 1m momentum. (survives: False)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Recent defensive bounce (+9.56% 1m MOM) counterbalanced by severe headwinds from 7.28% mortgage rates and building permits falling to 1,295k (0th percentile).
- against: Historical Reflation/Hold 3m excess return is positive (+0.68%), suggesting potential value. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST:Real Estate same_regime_3m -1.55
- against: MOM +9.56 (survives: True)
- 🔎 Critic FLAG: Rests on the credit and inflation-expectation betas, but mortgage rates of 7.28% (95th percentile) and permits at the 0th percentile (1295) were noted and not weighed in the tilt. Regime history is negative (-1.55% 3m, n=25), and the +9.56 1m momentum is a bounce rather than confirmation.

### Communication Services
**claude-sonnet-5** (+0.0 pts): Small negative betas across most factors; momentum weak (-1.22% 3m, -5.83% 6m).
- against: None material enough to add a discretionary adjustment. (survives: False)
**claude-opus-5-5** (+0.0 pts): Neutral.
- against: n/a (survives: True)
**gemini-3.8-flash@paid (fallback)** (+0.0 pts): Mild positive 1m momentum (+2.83%) offset by poor 6m track record (-5.83%) and weak historical returns in Reflation/Hold (-1.27% 3m).
- against: Modest rates sensitivity (+0.0259) provides better duration tolerance than Technology. (survives: True)
**xai:grok-4.3** (+0.0 pts): HIST:Communication Services same_regime_1m -0.5
- against: MOM +2.83 (survives: True)
- 🔎 Critic FLAG: The +3 pt factor effect is thin and all models gave 0 sector-specific points. Regime history is negative (-1.79% 3m, 36.8% beat, n=19) and 3m and 6m momentum are weak (-1.22 and -5.83). The +1 looks like noise rather than a view.

## Core variables vs consensus
- **CPIAUCSL**: 4.08% YoY, rising from 3.3% 3m ago | consensus: markets price gradual disinflation toward target | view: above  
  📎 CPI inflation YoY % = 4.08 (FRED CPIAUCSL, as of 2026-10-31)
- **CPILFESL**: 2.87% YoY, rising | consensus: n/a | view: above  
  📎 Core CPI inflation YoY % = 2.87 (FRED CPILFESL, as of 2026-10-31)
- **PCEPILFE**: 3.12% YoY, flat trend but above Fed's 2026 median (3.4 proj suggests Fed expects similar) | consensus: Fed SEP core PCE 2026 median 3.4 | view: in line  
  📎 Core PCE inflation YoY % = 3.12 (FRED PCEPILFE, as of 2026-09-30); SEP_JCXFEMD_2026 = 3.4 (FRED Fed projections)
- **UNRATE/PAYEMS/IC4WSA**: Unemployment 4.1% falling, payrolls +165k rising, claims 4wk avg 197,750 falling | consensus: Fed median unemployment 4.1% through 2029 | view: in line  
  📎 Unemployment rate % = 4.1 (FRED UNRATE, as of 2026-10-01); Payrolls monthly change (thousands) = 165.0 (FRED PAYEMS, as of 2026-10-31); Initial jobless claims, 4-wk avg = 197750.0 (FRED IC4WSA, as of 2026-11-14)
- **CES0500000003**: Avg hourly earnings 3.12% YoY, flat/decelerating | consensus: n/a | view: in line  
  📎 Average hourly earnings YoY % = 3.12 (FRED CES0500000003, as of 2026-10-31)
- **DFF vs DGS2**: Fed funds 3.88% on hold, 2yr yield 4.76% — market pricing further hikes (2yr-FF spread 0.88) | consensus: Fed dot median 2026 4.1% | view: above  
  📎 Fed funds effective rate % = 3.88 (FRED DFF, as of 2026-11-19); 2-yr Treasury yield % = 4.76 (FRED DGS2, as of 2026-11-19); CALC:market_implied_fed_path
- **DGS10**: 5.04%, 96.7th percentile 5yr, rising | consensus: zero change priced | view: above  
  📎 10-yr Treasury yield % = 5.04 (FRED DGS10, as of 2026-11-19)
- **T10Y2Y**: 0.29, falling but still positive (not inverted) | consensus: n/a | view: in line  
  📎 10-yr minus 2-yr spread = 0.29 (FRED T10Y2Y, as of 2026-11-20)
- **BAMLH0A0HYM2**: 3.52, 86.5th percentile, rising from 2.85 3m ago | consensus: zero change priced | view: above  
  📎 High-yield credit spread = 3.52 (FRED BAMLH0A0HYM2, as of 2026-11-19)
- **NFCI**: -0.48, looser than average despite the equity selloff | consensus: n/a | view: in line  
  📎 Chicago Fed financial conditions (negative = loose) = -0.48 (FRED NFCI, as of 2026-11-13)
- **DCOILWTICO/DCOILBRENTEU**: WTI 89.53, Brent 92.94, flat but 75-77th percentile, backwardation +7.8% signals real physical scarcity (Hormuz closure) | consensus: zero change priced; EIA sees Brent near $100 near-term | view: above  
  📎 WTI crude oil $/bbl = 89.53 (FRED DCOILWTICO, as of 2026-11-17); Brent crude oil $/bbl = 92.94 (FRED DCOILBRENTEU, as of 2026-11-17); CALC:risk_indicators; EIA expects Brent crude oil spot prices to remain near $100 per barrel for the rest of the year. (2026-11-10) https://www.eia.gov/outlooks/steo/

## Scenarios
*claude-sonnet-5*: base (0.55): Reflation persists; Fed holds through Dec 8-9 FOMC; oil stays elevated/volatile on Hormuz closure but doesn't spike further; equities stabilize after the -8.6% week; credit spreads drift wider but no disorderly widening.; downside (0.25): Iran/Houthi conflict escalates further (more tanker strikes, wider Gulf disruption), oil spikes, credit spreads blow out past 4%, recession-risk model's elevated reading (0.299) is validated as financial conditions tighten sharply.; upside (0.2): De-escalation in Strait of Hormuz/Red Sea, IEA's reported supply rebound (+2.3mb/d) feeds through, oil retreats toward $77 EIA 2027 forecast, equity volatility fades, credit spreads retrace tightening.
*claude-opus-5-5*: base (0.5): Choppy stabilization: Hormuz stays closed without major new supply loss, Fed hikes or signals a hike in Dec in line with the dot plot, oil drifts toward the mid-90s Brent, equities range-bound with high vol.; downside (0.3): Escalation hits Saudi export capacity or tankers, and/or a hawkish Fed plus hot CPI push 10y further above 5%; HY spreads widen past 4, a further 10% equity drawdown.; upside (0.2): De-escalation/partial Hormuz reopening plus OPEC+ supply; oil falls, yields ease, cyclicals and tech rebound sharply from oversold.
*gemini-3.8-flash@paid (fallback)*: base (0.6): Oil supply bottlenecks in Hormuz persist, keeping crude elevated near $95-$100/bbl. Reflationary pressures keep bond yields near 5% while tight financial conditions suppress high-multiple tech and consumer spending, sustaining defensive outperformance.; downside (0.25): Geopolitical conflict in the Gulf escalates to direct strikes on major oil terminals, driving Brent past $110/bbl. The stagflationary shock triggers a wider credit crunch (HY spreads >4.50%) and sends equities into a deeper bear market.; upside (0.15): Naval de-escalation reopens Hormuz shipping corridors, oil swiftly recedes towards $80/bbl, yields ease back below 4.75%, and oversold equities stage a relief rally.
*xai:grok-4.3*: base (0.6): Reflation continues with yields elevated and oil supply squeeze persisting; downside (0.25): S&P drawdown extends on VIX 28.44 and HY spreads widening to 92nd pct; upside (0.15): FOMC Dec 8-9 signals pause and de-escalation in Hormuz

## Upcoming releases
- 2026-11-24: G.17 Industrial Production and Capacity Utilization
- 2026-11-25: Debt to Gross Domestic Product Ratios
- 2026-11-25: Gross Domestic Product
- 2026-11-25: Personal Income and Outlays
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
- Copper $/metric ton: UNUSUAL (z=+2.7 vs 5-yr history), STALE (80 days old)
- Global food price index: STALE (80 days old)
- Personal saving rate %: STALE (80 days old)
- Corporate profits YoY %: STALE (204 days old)
- Trade policy uncertainty index: STALE (80 days old)
- Job openings (thousands): STALE (80 days old)
- Quits rate %: STALE (80 days old)
- Global all-commodity price index: STALE (80 days old)
- U.S. trade balance ($M): STALE (80 days old)
- Auditor removed (gemini-3.8-flash@paid (fallback), Technology): unrecognized reference 'SENS:Technology'
- Auditor removed (gemini-3.8-flash@paid (fallback), Utilities): unrecognized reference 'SENS:Utilities'
- Dropped note: No recent Commerce BIS export controls or Treasury OFAC sanctions announcements found in last 4 weeks (October 23 - November 20, 2026) with available sources. (NOT FOUND): URL was not in the agent's search results
- Dropped note: No specific China-Taiwan military or political incidents found in search results for last 4 weeks. (NOT FOUND): URL was not in the agent's search results
- Dropped note: No new Chinese export controls on rare earths or critical minerals found in search results for last 4 weeks. (NOT FOUND): URL was not in the agent's search results
- Dropped note: No NATO or U.S. defense budget decisions found in last 4 weeks with available sources. (NOT FOUND): URL was not in the agent's search results
- Dropped note: No U.S. government shutdown or debt-ceiling deadlines found in search results for last 4 weeks. (NOT FOUND): URL was not in the agent's search results

## Evidence notes
- NOTE:A1 The next scheduled FOMC meeting is set for December 8-9, 2026, and is associated with a Summary of Economic Projections. (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- NOTE:A2 The Federal Reserve released the minutes of the October 27–28, 2026 FOMC meeting on November 18, 2026. (https://www.federalreserve.gov/newsevents/pressreleases/monetary20261118a.htm)
- NOTE:B1 EIA expects Brent crude oil spot prices to remain near $100 per barrel for the rest of the year. (https://www.eia.gov/outlooks/steo/)
- NOTE:B2 EIA forecasts Brent crude spot prices to decline gradually to an average of $77 per barrel by the fourth quarter of 2027. (https://www.eia.gov/outlooks/steo/)
- NOTE:B3 EIA projects the Henry Hub natural gas spot price to average $2.87 per million British thermal units from November through March. (https://www.eia.gov/outlooks/steo/)
- NOTE:B4 U.S. commercial crude oil inventories dropped to 410 million barrels at the end of October and are projected to stay below the five-year average through mid-2027. (https://www.eia.gov/outlooks/steo/)
- NOTE:B5 USTR issued a statement regarding the President's intent to terminate Rwanda and South Africa from the AGOA trade preference program. (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- NOTE:B6 Ambassador Greer wrote a letter to the editor of the Wall Street Journal discussing the role of tariffs in advancing long-term prosperity. (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- NOTE:D1 In its January 2026 World Economic Outlook Update, the IMF projected global growth at 3.3 percent for 2026, slightly higher than in October 2025. (https://www.imf.org/en/Publications/WEO)
- NOTE:D2 The IMF projected global growth at 3.2 percent for 2027 in the January 2026 World Economic Outlook Update. (https://www.imf.org/en/Publications/WEO)
- NOTE:E1 The Drewry World Container Index dropped 3% week-on-week to $4,176 per 40ft container. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E2 Suez Canal vessel transits improved to 57 vessels last week, while only 4 vessels transited the Strait of Hormuz. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E3 OFAC issued Iran Designations alongside Cuba Frequently Asked Questions on November 20, 2026. (https://ofac.treasury.gov/recent-actions)
- NOTE:E4 OFAC issued an amended Russia-related General License and FAQs alongside Counter Narcotics and Cyber-related Designations. (https://ofac.treasury.gov/recent-actions)
- NOTE:E5 OFAC issued Iran-related designations and an amended Venezuela-related General License on November 4, 2026. (https://ofac.treasury.gov/recent-actions)
- NOTE:E6 OFAC published North Korea Designations and Democratic Republic of the Congo-related Designations. (https://ofac.treasury.gov/recent-actions)
- NOTE:C1 Analysts raised EPS estimates for S&P 500 companies for the second straight quarter. (https://insight.factset.com/topic/earnings/page/2)
- NOTE:C2 The latest weekly AAII survey reported bullish sentiment among individual investors at 33.3%. (https://www.aaii.com/sentimentsurvey)
- NOTE:C3 The latest weekly AAII survey reported bearish sentiment among individual investors at 42.2%. (https://www.aaii.com/sentimentsurvey)
- NOTE:C4 Managed money held 20,031 long contracts and 19,819 short contracts in light sweet crude oil (WTI) on ICE Futures Europe. (https://www.cftc.gov/dea/futures/petroleum_sf.htm)
- NOTE:E1 U.S. military struck Iran's Qeshm Island in the Strait of Hormuz on November 3, 2026; third U.S. aircraft carrier arrived in Gulf region by November 17 amid escalating threats. (https://www.cnbc.com/2026/11/17/iran-war-trump-hormuz-oil-.html)
- NOTE:E2 Houthis attacked Saudi Aramco offices and hit Saudi oil infrastructure; Iran fired six drones at U.S. radar in Bahrain on November 17; Saudi infrastructure including PIF Tower hit by missiles. (https://cnbc.com/2026/11/18/stock-market-today-live-updates.html)
- NOTE:E3 Ukrainian forces conducted coordinated drone and missile strike on Kerch Bridge linking Russia to occupied Crimea on November 18, described as unprecedented operation and symbolic blow to Kremlin war effort. (https://www.cnbc.com/2026/11/18/ukraine-russia-war-trump-putin-deep-strikes.html)
- NOTE:E4 Strait of Hormuz has been effectively closed since February 28, 2026 due to Iranian control. Iran warns strait remains closed until U.S. accepts Iranian conditions; only four vessels crossed as of November 19. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E5 Red Sea maritime traffic remains disrupted by Houthi attacks. Suez Canal transits improved to 57 vessels last week but shipping forced to reroute through Cape of Good Hope due to continued threats. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E6 Drewry World Container Index decreased 3% to $4,176 per 40ft container as of November 19, 2026, down for fourth consecutive week. Shanghai to New York rates fell 9% to $8,194, lowest in 15 weeks. (https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry)
- NOTE:E7 OPEC+ maintained production targets on November 1, 2026; next full ministerial meeting scheduled for November 29 to decide 2027 quotas. Seven core members (Saudi Arabia, Russia, Iraq, Kuwait, Algeria, Kazakhstan, Oman) hold monthly reviews. (https://opec.org/pr-detail/2033620-1-november-2026.html)
- NOTE:E8 IEA November 2026 report states global oil supply rose 2.3 mb/d to 105.4 mb/d in October; Gulf exports (ex-Oman) reached 18.4 mb/d, 26% below pre-war levels. 2027 supply projected to rebound 6.6 mb/d to 108.1 mb/d. (https://www.iea.org/reports/oil-market-report-november-2026)
- NOTE:E9 IEA forecasts world oil demand to fall 2.7 mb/d in 2026 to 102.3 mb/d, then rebound by 2 mb/d in 2027. YoY decline easing to 2.7 mb/d in Q4 2026 from average 4.4 mb/d in Q2-Q3 2026. (https://www.iea.org/reports/oil-market-report-november-2026)

## Direct-fetch sources (fix URLs in pipeline/fetch.py if one keeps failing)
- A fed_policy: used (https://www.federalreserve.gov/newsevents/pressreleases/monetary20261118a.htm)
- A fed_speeches: read, nothing extracted (https://www.federalreserve.gov/newsevents/speech/cook20261120a.htm)
- A fomc_calendar: used (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- A beige_book: read, nothing extracted (https://www.federalreserve.gov/monetarypolicy/beigebook202610.htm)
- B truflation: read, nothing extracted (https://truflation.com/)
- B cleveland_nowcast: read, nothing extracted (https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting)
- B eia_steo: used (https://www.eia.gov/outlooks/steo/)
- B eia_weekly: read, nothing extracted (https://www.eia.gov/petroleum/supply/weekly/)
- B ustr: used (https://ustr.gov/about-us/policy-offices/press-office/press-releases)
- B treasury_refunding: read, nothing extracted (https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding)
- D ism_manufacturing: too little readable text (JavaScript page?) (https://ecommerce.ismworld.org/SSO/Login.aspx?DPLF=Y&vi=10&vt=cfb19d24243043cfb384fdb113b18602ae19c0b960c506fb3777491eaefaa9fb0ccef807b8aa443f2a918697ab0e9fc6c3eaffb8823f543240b171e17f39dff200e533c5174e6879749498716dfea2289cbbbce3eaa0cfece0960f7baeb059f172a8de71ea187373d8601ef7c5557f20)
- D ecb: read, nothing extracted (https://www.ecb.europa.eu//press/key/date/2026/html/ecb.sp261120~e52bcc4db2.en.html)
- D boe: read, nothing extracted (https://www.bankofengland.co.uk/news/2026/november/cyber-resilience-guidance-consultation-and-ai-and-quantum-effective-practices)
- D boj: read, nothing extracted (http://www.boj.or.jp/en/research/imes/mes/mes26.htm)
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
- C aaii: used (https://www.aaii.com/sentimentsurvey)
- C cftc_petroleum: used (https://www.cftc.gov/dea/futures/petroleum_sf.htm)
- C shiller: read, nothing extracted (https://shillerdata.com/)

_Model cost so far ≈ $0.51. Full receipts in sources.csv and full_run.json._