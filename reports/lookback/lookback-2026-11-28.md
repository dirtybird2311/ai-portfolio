# Look-back: what worked on the shortlist and why

Built 2026-11-28. Read-only record; it changes no pick, weight or setting. Windows are short, so treat every pattern as a lead to test, not a finding.

## How each rebuild did

| Traded | Measured to | Days | Picks | Picks % | Shortlist % | Passed over % | Picks above shortlist median |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | 2026-11-27 | 43 | 8 | -3.68 | -4.16 | -4.22 | 38% |
| 2026-09-29 | 2026-11-27 | 42 | 6 | +2.45 | -2.16 | -2.54 | 50% |
| 2026-10-05 | 2026-11-27 | 38 | 11 | +0.87 | -0.33 | -0.52 | 55% |
| 2026-10-19 | 2026-11-27 | 28 | 11 | -1.91 | -4.10 | -4.46 | 64% |
| 2026-11-02 | 2026-11-27 | 18 | 12 | -6.00 | -5.33 | -5.20 | 33% |
| 2026-11-16 | 2026-11-27 | 8 | 17 | -2.25 | -2.74 | -2.86 | 59% |

## Which inputs lined up with what happened

Rank correlation with the return since each rebuild. About ±0.22 is noise at this sample size, so values inside that band say nothing yet. `panel_p` is the judges' averaged probability, `base_p` the base rate before the judges, `edge_pts` the gap between them (the judges' added view), `composite` the screen score, and `m e q v l` the five signal families.

| Input | 2026-09-28 | 2026-09-29 | 2026-10-05 | 2026-10-19 | 2026-11-02 | 2026-11-16 | Mean |
|---|---|---|---|---|---|---|---|
| panel_p | +0.13 | +0.10 | +0.19 | -0.24 | -0.20 | -0.21 | -0.04 |
| base_p | -0.06 | +0.11 | +0.30 | n/a | +0.03 | -0.14 | +0.05 |
| edge_pts | +0.14 | +0.11 | +0.06 | -0.24 | -0.24 | -0.21 | -0.06 |
| composite | +0.01 | -0.02 | -0.00 | -0.08 | -0.12 | -0.14 | -0.06 |
| news_score | -0.19 | -0.21 | -0.24 | -0.06 | +0.11 | -0.19 | -0.13 |
| m | +0.09 | +0.08 | +0.00 | -0.10 | -0.18 | -0.31 | -0.07 |
| e | +0.46 | +0.33 | +0.36 | +0.38 | +0.38 | +0.26 | +0.36 |
| q | +0.15 | +0.38 | +0.25 | +0.17 | +0.27 | +0.31 | +0.25 |
| v | +0.08 | -0.15 | -0.12 | -0.20 | -0.10 | -0.08 | -0.09 |
| l | +0.40 | +0.34 | +0.35 | +0.52 | +0.39 | +0.36 | +0.39 |
| p_gemini_pro | +0.18 | +0.09 | +0.08 | -0.19 | -0.15 | -0.10 | -0.02 |
| p_gpt_sol | +0.16 | +0.10 | +0.19 | -0.12 | -0.20 | -0.11 | +0.01 |
| p_grok | n/a | -0.03 | +0.22 | -0.19 | -0.14 | -0.33 | -0.09 |
| p_kimi | n/a | n/a | +0.23 | n/a | n/a | n/a | +0.23 |
| p_replay_opus | +0.05 | n/a | n/a | n/a | n/a | n/a | +0.05 |
| p_sig_beat_quality | n/a | n/a | n/a | n/a | n/a | -0.02 | -0.02 |
| p_sig_guidance | n/a | n/a | n/a | n/a | n/a | +0.24 | +0.24 |
| p_sig_read_across | n/a | n/a | n/a | n/a | n/a | +0.07 | +0.07 |
| p_sonnet | +0.01 | +0.17 | +0.24 | -0.25 | -0.19 | -0.38 | -0.07 |
| p_sonnet55 | n/a | n/a | n/a | n/a | -0.01 | -0.11 | -0.06 |
| p_sonnet_council | n/a | n/a | n/a | n/a | -0.17 | -0.32 | -0.24 |

## Rebuild traded 2026-09-28: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| ANF | 37.45 | no | 0.00 | Consumer Discretionary | 0.46 | -1.30 | bear | consumer demand |
| QNST | 34.06 | no | 0.00 | Communication Services | 0.48 | -0.70 | bear | high-yield credit spreads |
| REGN | 32.02 | no | 0.00 | Health Care | 0.50 | 2.70 | bull | Biotech sentiment |
| SN | 30.22 | no | 0.00 | Consumer Discretionary | 0.44 | -3.30 | bear | valuation/momentum tension |
| DLTR | 28.02 | yes | 5.00 | Consumer Staples | 0.52 | 5.30 | bull | consumer spending |
| CON | 23.46 | no | 0.00 | Health Care | 0.51 | 2.70 | bull | earnings momentum |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| STX | -44.69 | no | 0.00 | Technology | 0.46 | -2.00 | draw | AI storage demand |
| IESC | -44.54 | no | 0.00 | Industrials | 0.50 | 2.00 | draw | Backlog/demand growth |
| TER | -44.41 | no | 0.00 | Technology | 0.45 | -4.00 | bear | semiconductor cycle |
| FORM | -43.20 | no | 0.00 | Technology | 0.48 | -1.00 | bear | credit spreads |
| CORT | -42.59 | no | 0.00 | Health Care | 0.46 | -0.30 | bear | credit spreads |
| DELL | -41.59 | no | 0.00 | Technology | 0.51 | 2.00 | bull | AI infrastructure spending |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 4.00 | 9.40 | 0.00 |
| Consumer Discretionary | 9.00 | 8.57 | 0.00 |
| Consumer Staples | 7.00 | 7.46 | 3.00 |
| Utilities | 7.00 | 4.69 | 0.00 |
| Real Estate | 8.00 | 1.31 | 0.00 |
| Health Care | 8.00 | 0.02 | 2.00 |
| Financials | 9.00 | -0.51 | 1.00 |
| Industrials | 9.00 | -12.30 | 1.00 |
| Materials | 8.00 | -18.21 | 0.00 |
| Technology | 9.00 | -30.47 | 1.00 |

## Rebuild traded 2026-09-29: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| ANF | 38.06 | no | 0.00 | Consumer Discretionary | 0.45 | -0.70 | bear | 10-yr yield |
| REGN | 32.33 | no | 0.00 | Health Care | 0.48 | -0.70 | bear | Product execution |
| QNST | 31.93 | no | 0.00 | Communication Services | 0.50 | -1.00 | draw | credit spreads |
| DLTR | 31.09 | yes | 10.00 | Consumer Staples | 0.50 | 3.70 | draw | consumer spending |
| CON | 23.53 | no | 0.00 | Health Care | 0.47 | -1.30 | bear | margin trajectory |
| JLL | 20.97 | no | 0.00 | Real Estate | 0.51 | 2.70 | draw | 10-year yield |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| IESC | -44.94 | no | 0.00 | Industrials | 0.48 | 2.70 | bear | data-center spending |
| DELL | -41.18 | no | 0.00 | Technology | 0.52 | 2.70 | draw | AI-server demand |
| KALU | -34.88 | no | 0.00 | Materials | 0.45 | -1.70 | bear | 10-yr yield |
| ADAM | -33.29 | no | 0.00 | Real Estate | 0.50 | 2.30 | bull | 10-year yields |
| HPE | -30.46 | no | 0.00 | Technology | 0.48 | 0.30 | draw | AI/networking demand |
| HL | -29.30 | no | 0.00 | Materials | 0.39 | -5.40 | bear | dollar strength |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Consumer Staples | 6.00 | 11.79 | 2.00 |
| Communication Services | 5.00 | 11.78 | 0.00 |
| Consumer Discretionary | 7.00 | 8.34 | 0.00 |
| Utilities | 6.00 | 6.55 | 0.00 |
| Real Estate | 7.00 | 5.00 | 0.00 |
| Health Care | 8.00 | 2.83 | 0.00 |
| Financials | 9.00 | -0.27 | 2.00 |
| Energy | 8.00 | -7.97 | 1.00 |
| Technology | 9.00 | -15.65 | 1.00 |
| Industrials | 7.00 | -17.25 | 0.00 |
| Materials | 7.00 | -18.30 | 0.00 |

## Rebuild traded 2026-10-05: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| REGN | 36.71 | no | 0.00 | Health Care | 0.50 | 2.00 | draw | earnings results |
| DLTR | 31.22 | yes | 5.00 | Consumer Staples | 0.51 | 2.30 | draw | consumer spending |
| ANF | 30.43 | no | 0.00 | Consumer Discretionary | 0.43 | -3.00 | bear | consumer spending |
| QNST | 27.08 | no | 0.00 | Communication Services | 0.47 | -2.30 | bear | client concentration |
| CART | 26.12 | no | 0.00 | Consumer Staples | 0.45 | -4.00 | bear | earnings revisions |
| JLL | 24.41 | no | 0.00 | Real Estate | 0.53 | 4.00 | bull | 10-year yields |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| IESC | -47.40 | no | 0.00 | Industrials | 0.47 | 1.30 | bear | Data-center capex |
| CORT | -45.60 | no | 0.00 | Health Care | 0.44 | -1.00 | draw | credit spreads |
| KALU | -36.80 | no | 0.00 | Materials | 0.49 | 2.00 | draw | credit spreads |
| ADAM | -31.48 | yes | 9.28 | Real Estate | 0.52 | 4.00 | bull | 10-year yield |
| ENS | -31.41 | no | 0.00 | Industrials | 0.48 | -0.30 | draw | Tariff-driven demand |
| PARR | -30.39 | no | 0.00 | Energy | 0.46 | 0.30 | bear | Oil price |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 4.00 | 13.13 | 1.00 |
| Consumer Discretionary | 6.00 | 10.29 | 1.00 |
| Consumer Staples | 10.00 | 8.05 | 2.00 |
| Utilities | 9.00 | 7.82 | 1.00 |
| Financials | 8.00 | 3.21 | 2.00 |
| Real Estate | 3.00 | 3.09 | 1.00 |
| Health Care | 16.00 | 2.21 | 1.00 |
| Technology | 4.00 | -13.91 | 1.00 |
| Industrials | 6.00 | -14.55 | 0.00 |
| Materials | 9.00 | -16.07 | 1.00 |
| Energy | 4.00 | -18.43 | 0.00 |

## Rebuild traded 2026-10-19: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| REGN | 26.99 | no | 0.00 | Health Care | 0.50 | 2.00 | bull | Dupixent growth |
| DLTR | 20.61 | yes | 5.00 | Consumer Staples | 0.49 | 1.70 | draw | Consumer discretionary spending |
| TPC | 18.24 | no | 0.00 | Industrials | 0.47 | -0.30 | bear | 10-year yield |
| AVNT | 16.88 | no | 0.00 | Materials | 0.47 | -1.00 | draw | 10-year yields |
| WTRG | 16.43 | no | 0.00 | Utilities | 0.51 | 3.00 | bull | credit spreads |
| CON | 14.34 | no | 0.00 | Health Care | 0.49 | 1.70 | bear | valuation multiples |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| KALU | -34.47 | no | 0.00 | Materials | 0.51 | 3.00 | bull | aluminum prices |
| DELL | -30.31 | no | 0.00 | Technology | 0.50 | 2.70 | draw | AI server demand |
| DINO | -29.82 | no | 0.00 | Energy | 0.54 | 6.30 | bull | oil prices |
| PBF | -28.96 | yes | 8.02 | Energy | 0.53 | 5.70 | bull | oil prices |
| IESC | -28.78 | no | 0.00 | Industrials | 0.49 | 1.70 | draw | data center demand |
| ADAM | -28.22 | no | 0.00 | Real Estate | 0.49 | 1.30 | bear | 10-year yields |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Utilities | 10.00 | 6.78 | 0.00 |
| Consumer Discretionary | 4.00 | 2.49 | 1.00 |
| Communication Services | 3.00 | 2.16 | 1.00 |
| Health Care | 10.00 | 1.59 | 1.00 |
| Consumer Staples | 8.00 | 0.20 | 2.00 |
| Real Estate | 5.00 | -1.74 | 0.00 |
| Financials | 8.00 | -2.10 | 2.00 |
| Industrials | 6.00 | -6.33 | 0.00 |
| Materials | 7.00 | -12.58 | 1.00 |
| Technology | 3.00 | -14.42 | 1.00 |
| Energy | 14.00 | -16.22 | 2.00 |

## Rebuild traded 2026-11-02: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| TPC | 16.53 | no | 0.00 | Industrials | 0.45 | -2.30 | bear | 10-yr yield |
| ANF | 12.34 | no | 0.00 | Consumer Discretionary | 0.41 | -4.70 | bear | Valuation/momentum extension |
| TGT | 9.35 | no | 0.00 | Consumer Staples | 0.46 | 0.30 | bear | Earnings event risk |
| CON | 8.25 | no | 0.00 | Health Care | 0.49 | 1.70 | draw | credit spreads |
| DLTR | 7.16 | yes | 5.23 | Consumer Staples | 0.48 | -2.00 | bear | consumer spending |
| EL | 6.92 | no | 0.00 | Consumer Staples | 0.46 | -1.70 | bear | Tariff policy |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| HALO | -26.48 | no | 0.00 | Health Care | 0.46 | -0.00 | bear | credit spreads |
| PBF | -23.11 | yes | 7.99 | Energy | 0.53 | 5.30 | bull | oil price |
| AMN | -22.50 | no | 0.00 | Health Care | 0.47 | -3.00 | bear | healthcare staffing demand |
| MU | -22.39 | yes | 5.99 | Technology | 0.51 | 4.00 | bull | credit spreads |
| DINO | -21.80 | no | 0.00 | Energy | 0.48 | 2.30 | bull | oil price |
| ECG | -21.52 | no | 0.00 | Industrials | 0.49 | 2.30 | bear | earnings catalyst |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 3.00 | 5.01 | 0.00 |
| Consumer Staples | 9.00 | 2.14 | 2.00 |
| Consumer Discretionary | 4.00 | -0.19 | 1.00 |
| Utilities | 8.00 | -1.20 | 0.00 |
| Financials | 8.00 | -2.90 | 2.00 |
| Real Estate | 5.00 | -3.41 | 0.00 |
| Health Care | 11.00 | -4.97 | 1.00 |
| Industrials | 6.00 | -8.88 | 0.00 |
| Energy | 13.00 | -10.54 | 4.00 |
| Materials | 7.00 | -13.19 | 1.00 |
| Technology | 3.00 | -18.83 | 1.00 |

## Rebuild traded 2026-11-16: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| ANF | 26.52 | no | 0.00 | Consumer Discretionary | 0.43 | -3.00 | bear | Consumer discretionary spending |
| UPBD | 15.73 | no | 0.00 | Consumer Discretionary | 0.51 | 3.00 | draw | 10-yr yield sensitivity |
| TGT | 7.27 | no | 0.00 | Consumer Staples | 0.45 | -1.30 | bear | consumer spending |
| DLTR | 7.09 | yes | 5.00 | Consumer Staples | 0.42 | -2.70 | bear | consumer spending |
| COKE | 6.59 | no | 0.00 | Consumer Staples | 0.45 | -3.30 | bear | credit spreads |
| IPAR | 6.16 | no | 0.00 | Consumer Staples | 0.47 | -1.00 | bear | holiday demand |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| CVI | -22.16 | no | 0.00 | Energy | 0.49 | 2.70 | draw | Oil prices |
| LQDT | -19.84 | no | 0.00 | Industrials | 0.46 | -0.00 | draw | earnings reaction |
| PBF | -16.28 | yes | 3.00 | Energy | 0.52 | 4.00 | bull | Oil prices |
| PARR | -15.45 | no | 0.00 | Energy | 0.56 | 5.00 | bull | oil price |
| UNH | -14.71 | no | 0.00 | Health Care | 0.51 | 3.70 | draw | credit spreads |
| DINO | -12.30 | no | 0.00 | Energy | 0.51 | 3.00 | draw | oil price |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Consumer Discretionary | 4.00 | 10.23 | 0.00 |
| Consumer Staples | 9.00 | 1.31 | 3.00 |
| Utilities | 7.00 | 0.67 | 0.00 |
| Real Estate | 6.00 | -1.33 | 1.00 |
| Communication Services | 3.00 | -2.02 | 0.00 |
| Financials | 8.00 | -2.31 | 3.00 |
| Industrials | 6.00 | -3.56 | 0.00 |
| Materials | 5.00 | -3.84 | 1.00 |
| Health Care | 12.00 | -4.26 | 3.00 |
| Energy | 19.00 | -7.20 | 6.00 |
| Technology | 2.00 | -9.10 | 0.00 |

## Written read

## What separated winners from losers
- Picks beat the shortlist average in 5 of 6 rebuilds, by 0.5 to 4.6 pts, and lost to it in the Nov 2 rebuild. The share of picks beating the shortlist median was 33–64%, which is near a coin flip. With 6–17 picks and single-name moves of ±40%, this is within luck.
- The windows are 8–43 days, longer than usual, and they all end on 2026-11-27. They share the same names (ANF, REGN, DLTR, IESC, DELL), so they are not six independent tests.
- Hypothesis: the winners and losers cluster by theme. The worst names were tech hardware (STX, TER, FORM, DELL, HPE) and oil refiners (PBF, DINO, PARR, CVI), plus IESC, KALU and CORT. The best were consumer and health care names (ANF, REGN, DLTR, CON, QNST).
- The inputs that ranked names best were `e` (+0.36, positive in all six rebuilds), `l` (+0.39, all six) and `q` (+0.25, all six). Most per-rebuild values sit at or above the ±0.22 luck band. They have consistent signs, but the overlap means this is a hypothesis.
- `panel_p` and `edge_pts` were +0.10 to +0.19 on the three longest windows (38–43 days) and −0.20 to −0.24 on the three shortest (8–28 days). The mean is about zero. The `p_sonnet_council` input was −0.24 on its two rebuilds.

## Where the judges' reasoning held up or missed
- The oil-bull calls missed. PBF was picked in three rebuilds and was the worst pick each time (−29.0%, −23.1%, −16.3%). DINO and PARR had bull calls on oil and also fell. MU, picked on a "credit spreads" bull call, fell 22.4%.
- Several top performers carried bear calls. ANF was called bear in all five rebuilds and gained +12% to +38%. QNST and SN also carried bear calls.
- This is a cherry-picked extreme list, so treat it as anecdote, not a pattern.
- The same macro labels ("credit spreads", "10-year yield") appear on unrelated sectors. That suggests the macro reasoning may be generic rather than name-specific.
- The DLTR thesis says "slightly less likely than its 44.2% base rate", yet its edge is +1.7 to +5.3 pts in four rebuilds and −2.0 to −2.7 pts in the last two. The text and the number don't match, and the text barely changes from one rebuild to the next.

## Hypotheses to test (each with how we would test it)
1. **Earnings, quality and liquidity-type inputs (`e`, `q`, `l`) carry the signal.** Log their rank correlation on the next rebuilds with non-overlapping windows and see if all three stay above +0.22.
2. **The panel signal depends on horizon.** Record each rebuild's return at fixed 10-, 20- and 40-day marks, so windows are comparable.
3. **Energy and tech picks are crowded on one macro bet.** Log picks by sector and by theme, and compare their returns to the shortlist in the same sector.
4. **Bear calls on strong-momentum names are too harsh.** Tag bear/bull calls per name and compare returns by call, with sector held constant.
5. **Judges' theses are stale.** Log the thesis text hash per name per rebuild to see how often it repeats.

## What not to conclude yet
- Don't conclude the picks add value. A gain of a few points over the shortlist on overlapping windows is within what luck gives.
- Don't conclude `e`, `l` or `q` work. The consistent sign is encouraging, but the data is effectively one market episode.
- Don't conclude the panel has flipped from helpful to harmful. Three early positive and three late negative values could be a single regime or noise.
- Don't read the oil or ANF examples as proof the judges are wrong. They are extremes picked after the fact, and the shortlist fell in every rebuild, so the market backdrop dominates.

_Model cost for this read: $0.047._
