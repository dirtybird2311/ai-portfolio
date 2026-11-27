# Look-back: what worked on the shortlist and why

Built 2026-11-20. Read-only record; it changes no pick, weight or setting. Windows are short, so treat every pattern as a lead to test, not a finding.

## How each rebuild did

| Traded | Measured to | Days | Picks | Picks % | Shortlist % | Passed over % | Picks above shortlist median |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | 2026-11-20 | 39 | 8 | -8.70 | -9.68 | -9.79 | 38% |
| 2026-09-29 | 2026-11-20 | 38 | 6 | -0.93 | -7.60 | -8.15 | 50% |
| 2026-10-05 | 2026-11-20 | 34 | 11 | -3.93 | -5.65 | -5.93 | 45% |
| 2026-10-19 | 2026-11-20 | 24 | 11 | -5.50 | -8.63 | -9.14 | 55% |
| 2026-11-02 | 2026-11-20 | 14 | 12 | -10.63 | -9.69 | -9.51 | 42% |
| 2026-11-16 | 2026-11-20 | 4 | 17 | -4.58 | -6.33 | -6.79 | 65% |

## Which inputs lined up with what happened

Rank correlation with the return since each rebuild. About ±0.22 is noise at this sample size, so values inside that band say nothing yet. `panel_p` is the judges' averaged probability, `base_p` the base rate before the judges, `edge_pts` the gap between them (the judges' added view), `composite` the screen score, and `m e q v l` the five signal families.

| Input | 2026-09-28 | 2026-09-29 | 2026-10-05 | 2026-10-19 | 2026-11-02 | 2026-11-16 | Mean |
|---|---|---|---|---|---|---|---|
| panel_p | +0.13 | +0.18 | +0.28 | -0.14 | -0.05 | -0.02 | +0.06 |
| base_p | -0.07 | +0.15 | +0.37 | n/a | +0.04 | -0.01 | +0.10 |
| edge_pts | +0.15 | +0.16 | +0.12 | -0.14 | -0.08 | -0.03 | +0.03 |
| composite | -0.01 | -0.05 | -0.04 | -0.16 | -0.21 | -0.09 | -0.09 |
| news_score | -0.25 | -0.23 | -0.27 | -0.08 | +0.20 | +0.03 | -0.10 |
| m | -0.06 | -0.08 | -0.11 | -0.26 | -0.14 | -0.30 | -0.16 |
| e | +0.40 | +0.31 | +0.38 | +0.31 | +0.34 | +0.17 | +0.32 |
| q | +0.13 | +0.24 | +0.17 | +0.09 | +0.14 | +0.17 | +0.16 |
| v | +0.11 | -0.09 | -0.14 | -0.25 | -0.07 | +0.05 | -0.07 |
| l | +0.56 | +0.50 | +0.48 | +0.69 | +0.62 | +0.64 | +0.58 |
| p_gemini_pro | +0.18 | +0.16 | +0.15 | -0.08 | -0.01 | +0.10 | +0.08 |
| p_gpt_sol | +0.16 | +0.18 | +0.29 | -0.05 | -0.04 | +0.03 | +0.09 |
| p_grok | n/a | +0.01 | +0.29 | -0.09 | -0.01 | -0.13 | +0.01 |
| p_kimi | n/a | n/a | +0.32 | n/a | n/a | n/a | +0.32 |
| p_replay_opus | +0.06 | n/a | n/a | n/a | n/a | n/a | +0.06 |
| p_sig_beat_quality | n/a | n/a | n/a | n/a | n/a | -0.03 | -0.03 |
| p_sig_guidance | n/a | n/a | n/a | n/a | n/a | +0.23 | +0.23 |
| p_sig_read_across | n/a | n/a | n/a | n/a | n/a | +0.02 | +0.02 |
| p_sonnet | +0.01 | +0.19 | +0.30 | -0.17 | -0.07 | -0.18 | +0.01 |
| p_sonnet55 | n/a | n/a | n/a | n/a | +0.11 | +0.09 | +0.10 |
| p_sonnet_council | n/a | n/a | n/a | n/a | -0.06 | -0.12 | -0.09 |

## Rebuild traded 2026-09-28: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| QNST | 30.12 | no | 0.00 | Communication Services | 0.48 | -0.70 | bear | high-yield credit spreads |
| REGN | 22.52 | no | 0.00 | Health Care | 0.50 | 2.70 | bull | Biotech sentiment |
| DLTR | 18.91 | yes | 5.00 | Consumer Staples | 0.52 | 5.30 | bull | consumer spending |
| CON | 18.50 | no | 0.00 | Health Care | 0.51 | 2.70 | bull | earnings momentum |
| SN | 16.84 | no | 0.00 | Consumer Discretionary | 0.44 | -3.30 | bear | valuation/momentum tension |
| LFST | 16.72 | no | 0.00 | Health Care | 0.46 | -2.70 | bear | valuation sentiment |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| IESC | -51.55 | no | 0.00 | Industrials | 0.50 | 2.00 | draw | Backlog/demand growth |
| STX | -50.41 | no | 0.00 | Technology | 0.46 | -2.00 | draw | AI storage demand |
| TER | -48.97 | no | 0.00 | Technology | 0.45 | -4.00 | bear | semiconductor cycle |
| DELL | -48.77 | no | 0.00 | Technology | 0.51 | 2.00 | bull | AI infrastructure spending |
| CORT | -44.98 | no | 0.00 | Health Care | 0.46 | -0.30 | bear | credit spreads |
| FORM | -44.25 | no | 0.00 | Technology | 0.48 | -1.00 | bear | credit spreads |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 4.00 | 3.78 | 0.00 |
| Utilities | 7.00 | 2.05 | 0.00 |
| Consumer Staples | 7.00 | 1.91 | 3.00 |
| Consumer Discretionary | 9.00 | -0.12 | 0.00 |
| Real Estate | 8.00 | -3.30 | 0.00 |
| Financials | 9.00 | -5.50 | 1.00 |
| Health Care | 8.00 | -5.83 | 2.00 |
| Industrials | 9.00 | -17.24 | 1.00 |
| Materials | 8.00 | -25.14 | 0.00 |
| Technology | 9.00 | -35.32 | 1.00 |

## Rebuild traded 2026-09-29: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| QNST | 28.05 | no | 0.00 | Communication Services | 0.50 | -1.00 | draw | credit spreads |
| REGN | 22.80 | no | 0.00 | Health Care | 0.48 | -0.70 | bear | Product execution |
| DLTR | 21.77 | yes | 10.00 | Consumer Staples | 0.50 | 3.70 | draw | consumer spending |
| WMG | 19.19 | no | 0.00 | Communication Services | 0.52 | 2.70 | bull | streaming revenues |
| CON | 18.57 | no | 0.00 | Health Care | 0.47 | -1.30 | bear | margin trajectory |
| ALL | 18.45 | yes | 15.00 | Financials | 0.52 | 3.30 | bull | credit spreads |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| IESC | -51.90 | no | 0.00 | Industrials | 0.48 | 2.70 | bear | data-center spending |
| DELL | -48.40 | no | 0.00 | Technology | 0.52 | 2.70 | draw | AI-server demand |
| ADAM | -40.98 | no | 0.00 | Real Estate | 0.50 | 2.30 | bull | 10-year yields |
| KALU | -39.96 | no | 0.00 | Materials | 0.45 | -1.70 | bear | 10-yr yield |
| HL | -38.66 | no | 0.00 | Materials | 0.39 | -5.40 | bear | dollar strength |
| FCX | -34.89 | no | 0.00 | Materials | 0.46 | 0.70 | bear | Copper prices |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 5.00 | 7.46 | 0.00 |
| Consumer Staples | 6.00 | 5.06 | 2.00 |
| Utilities | 6.00 | 3.70 | 0.00 |
| Real Estate | 7.00 | -0.23 | 0.00 |
| Consumer Discretionary | 7.00 | -0.68 | 0.00 |
| Health Care | 8.00 | -2.84 | 0.00 |
| Financials | 9.00 | -3.88 | 2.00 |
| Energy | 8.00 | -9.80 | 1.00 |
| Technology | 9.00 | -22.39 | 1.00 |
| Industrials | 7.00 | -24.05 | 0.00 |
| Materials | 7.00 | -25.41 | 0.00 |

## Rebuild traded 2026-10-05: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| REGN | 26.86 | no | 0.00 | Health Care | 0.50 | 2.00 | draw | earnings results |
| CART | 25.49 | no | 0.00 | Consumer Staples | 0.45 | -4.00 | bear | earnings revisions |
| QNST | 23.35 | no | 0.00 | Communication Services | 0.47 | -2.30 | bear | client concentration |
| DLTR | 21.88 | yes | 5.00 | Consumer Staples | 0.51 | 2.30 | draw | consumer spending |
| WMG | 19.15 | yes | 7.48 | Communication Services | 0.53 | 3.80 | bull | streaming revenue growth |
| ALL | 18.82 | yes | 14.10 | Financials | 0.54 | 5.70 | bull | underwriting margins |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| IESC | -54.05 | no | 0.00 | Industrials | 0.47 | 1.30 | bear | Data-center capex |
| CORT | -47.87 | no | 0.00 | Health Care | 0.44 | -1.00 | draw | credit spreads |
| KALU | -41.73 | no | 0.00 | Materials | 0.49 | 2.00 | draw | credit spreads |
| ADAM | -39.38 | yes | 9.28 | Real Estate | 0.52 | 4.00 | bull | 10-year yield |
| HL | -38.15 | no | 0.00 | Materials | 0.41 | -3.00 | bear | US dollar |
| FCX | -36.52 | no | 0.00 | Materials | 0.48 | 2.70 | bull | copper demand |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 4.00 | 10.21 | 1.00 |
| Utilities | 9.00 | 5.02 | 1.00 |
| Consumer Staples | 10.00 | 4.35 | 2.00 |
| Consumer Discretionary | 6.00 | -1.05 | 1.00 |
| Financials | 8.00 | -1.14 | 2.00 |
| Real Estate | 3.00 | -3.59 | 1.00 |
| Health Care | 16.00 | -3.80 | 1.00 |
| Energy | 4.00 | -19.58 | 0.00 |
| Industrials | 6.00 | -20.44 | 0.00 |
| Technology | 4.00 | -20.92 | 1.00 |
| Materials | 9.00 | -22.69 | 1.00 |

## Rebuild traded 2026-10-19: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| REGN | 17.85 | no | 0.00 | Health Care | 0.50 | 2.00 | bull | Dupixent growth |
| WTRG | 12.81 | no | 0.00 | Utilities | 0.51 | 3.00 | bull | credit spreads |
| DLTR | 12.03 | yes | 5.00 | Consumer Staples | 0.49 | 1.70 | draw | Consumer discretionary spending |
| TPC | 11.28 | no | 0.00 | Industrials | 0.47 | -0.30 | bear | 10-year yield |
| MGEE | 10.22 | no | 0.00 | Utilities | 0.45 | -2.70 | bear | credit spreads |
| DGX | 9.95 | no | 0.00 | Health Care | 0.48 | 0.70 | draw | credit spreads |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| KALU | -39.57 | no | 0.00 | Materials | 0.51 | 3.00 | bull | aluminum prices |
| DELL | -38.87 | no | 0.00 | Technology | 0.50 | 2.70 | draw | AI server demand |
| IESC | -37.78 | no | 0.00 | Industrials | 0.49 | 1.70 | draw | data center demand |
| ADAM | -36.50 | no | 0.00 | Real Estate | 0.49 | 1.30 | bear | 10-year yields |
| FCX | -34.06 | no | 0.00 | Materials | 0.46 | -2.00 | bear | Copper price |
| HL | -30.10 | no | 0.00 | Materials | 0.42 | -5.70 | bear | silver prices |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Utilities | 10.00 | 4.09 | 0.00 |
| Communication Services | 3.00 | -0.44 | 1.00 |
| Consumer Staples | 8.00 | -2.27 | 2.00 |
| Health Care | 10.00 | -4.32 | 1.00 |
| Financials | 8.00 | -5.36 | 2.00 |
| Real Estate | 5.00 | -5.95 | 0.00 |
| Consumer Discretionary | 4.00 | -9.82 | 1.00 |
| Industrials | 6.00 | -13.37 | 0.00 |
| Energy | 14.00 | -17.78 | 2.00 |
| Materials | 7.00 | -20.35 | 1.00 |
| Technology | 3.00 | -22.61 | 1.00 |

## Rebuild traded 2026-11-02: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| COCO | 10.58 | no | 0.00 | Consumer Staples | 0.42 | -2.30 | bear | consumer demand |
| TPC | 9.67 | no | 0.00 | Industrials | 0.45 | -2.30 | bear | 10-yr yield |
| WMG | 6.30 | no | 0.00 | Communication Services | 0.47 | -1.30 | bear | streaming growth |
| TGT | 5.44 | no | 0.00 | Consumer Staples | 0.46 | 0.30 | bear | Earnings event risk |
| CON | 3.90 | no | 0.00 | Health Care | 0.49 | 1.70 | draw | credit spreads |
| NJR | 2.51 | no | 0.00 | Utilities | 0.45 | -1.40 | bear | credit spreads |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| HALO | -29.16 | no | 0.00 | Health Care | 0.46 | -0.00 | bear | credit spreads |
| MU | -28.68 | yes | 5.99 | Technology | 0.51 | 4.00 | bull | credit spreads |
| LQDT | -28.61 | no | 0.00 | Industrials | 0.44 | -1.30 | bear | earnings catalyst |
| NGVT | -27.08 | no | 0.00 | Materials | 0.48 | -0.30 | bear | 10-year yield |
| FCX | -26.97 | no | 0.00 | Materials | 0.45 | -2.30 | bear | copper demand |
| ECG | -25.63 | no | 0.00 | Industrials | 0.49 | 2.30 | bear | earnings catalyst |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Communication Services | 3.00 | 2.29 | 0.00 |
| Consumer Staples | 9.00 | -1.03 | 2.00 |
| Utilities | 8.00 | -3.93 | 0.00 |
| Financials | 8.00 | -5.93 | 2.00 |
| Real Estate | 5.00 | -7.87 | 0.00 |
| Health Care | 11.00 | -9.88 | 1.00 |
| Consumer Discretionary | 4.00 | -11.15 | 1.00 |
| Energy | 13.00 | -12.55 | 4.00 |
| Industrials | 6.00 | -15.70 | 0.00 |
| Materials | 7.00 | -20.84 | 1.00 |
| Technology | 3.00 | -22.86 | 1.00 |

## Rebuild traded 2026-11-16: biggest hits and misses

Best performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| TGT | 3.44 | no | 0.00 | Consumer Staples | 0.45 | -1.30 | bear | consumer spending |
| IPAR | 2.32 | no | 0.00 | Consumer Staples | 0.47 | -1.00 | bear | holiday demand |
| UPBD | 2.09 | no | 0.00 | Consumer Discretionary | 0.51 | 3.00 | draw | 10-yr yield sensitivity |
| WMG | 1.45 | no | 0.00 | Communication Services | 0.46 | -1.70 | draw | streaming revenue growth |
| LNTH | 0.37 | no | 0.00 | Health Care | 0.43 | -4.70 | bear | M&A regulatory outcome |
| MGEE | 0.03 | no | 0.00 | Utilities | 0.51 | 4.70 | bull | credit spreads |

Worst performers on the shortlist:

| name | ret | picked | weight | sector | panel_p | edge_pts | winner | driver |
|---|---|---|---|---|---|---|---|---|
| LQDT | -27.50 | no | 0.00 | Industrials | 0.46 | -0.00 | draw | earnings reaction |
| UNH | -17.52 | no | 0.00 | Health Care | 0.51 | 3.70 | draw | credit spreads |
| MU | -17.32 | no | 0.00 | Technology | 0.54 | 1.30 | bull | credit spreads |
| CENX | -16.90 | no | 0.00 | Materials | 0.41 | -5.00 | bear | credit spreads |
| FCX | -16.67 | no | 0.00 | Materials | 0.45 | -2.30 | bear | copper price/margin trajectory |
| SDGR | -16.19 | no | 0.00 | Health Care | 0.44 | -3.00 | bear | credit spreads |

By sector:

| name | n | avg | picks |
|---|---|---|---|
| Utilities | 8.00 | -2.42 | 0.00 |
| Consumer Staples | 9.00 | -3.05 | 3.00 |
| Real Estate | 6.00 | -3.59 | 1.00 |
| Financials | 8.00 | -4.33 | 3.00 |
| Communication Services | 3.00 | -4.52 | 0.00 |
| Consumer Discretionary | 4.00 | -5.07 | 0.00 |
| Energy | 19.00 | -7.78 | 6.00 |
| Health Care | 12.00 | -8.38 | 3.00 |
| Industrials | 6.00 | -8.62 | 0.00 |
| Materials | 5.00 | -10.60 | 1.00 |
| Technology | 2.00 | -14.74 | 0.00 |

## Written read

## What separated winners from losers
- Every shortlist fell, by 5.65% to 9.69%. Picks beat the shortlist in 5 of 6 rebuilds (by 1.0 to 6.7 pts) and trailed in the 2026-11-02 rebuild. But the picks beat the shortlist median only 38-65% of the time, about a coin flip.
- The big losers were mostly passed-over Technology, Materials and Industrials names (IESC, DELL, FCX, KALU, HL, STX, TER), repeating across rebuilds. The big winners were REGN, QNST and DLTR, also repeating. The windows overlap and share an end date, so these are not six independent tests.
- Input rank correlations: `l` (+0.58 mean, +0.48 to +0.69 in every rebuild) and `e` (+0.32, +0.17 to +0.40) are the only clear signals. Both sit above the ±0.22 luck band every time. `m` was negative in all six (mean -0.16), though only the -0.26 and -0.30 readings clear the luck band.
- `panel_p` (+0.06), `edge_pts` (+0.03) and `composite` (-0.09) are within luck.

## Where the judges' reasoning held up or missed
- The edges were small, mostly within ±5 pts of even, and they ranked names poorly. IESC (edge +2.0) and DELL (+2.0 to +2.7) were among the worst; LFST (-2.7) and QNST (-0.7 to -2.3) were among the best.
- 'Credit spreads' was cited on both sides: bull on ALL (+18.4%) but also bull on MU (-28.7% picked), bear on QNST (+30.1%), and bear or draw on CORT, HALO and FORM, which all fell. It looks like a repeated rationale without visible discrimination.
- Some calls held up: DLTR was picked and rose +12.0% to +21.9% in four rebuilds, and ALL and WMG did well when picked. ADAM was picked at -39.4% on a '10-year yield' bull call.
- The DLTR thesis said "slightly less likely than its 44.2% base rate", yet it was picked and won. That is one name, so it may be luck.

## Hypotheses to test (each with how we would test it)
1. **`l` and `e` carry real ranking information.** Log their rank correlation on new rebuilds with non-overlapping windows. Check that the sign holds and that the correlation survives controlling for sector.
2. **Sector exposure drove the shortfall, not stock-level judgment.** Compare passed-over losers with sector medians, and compute pick returns relative to sector rather than to the shortlist.
3. **Judge macro calls ('credit spreads') add noise.** Log each macro-factor call alongside the realized factor move, and score the call separately from the stock thesis.
4. **`m` is a mild contrarian signal.** See whether the negative sign persists beyond ~80 new names per rebuild.
5. **Repeated names inflate the apparent pattern.** Report results with names deduplicated across rebuilds.

## What not to conclude yet
- Samples range from 4 to 39 trading days, longer than the 9-14 range I'd normally expect. The 4-day rebuild (65% of picks beating the median) is essentially noise.
- Picks beating the shortlist in 5 of 6 rebuilds is not evidence of skill, since the windows overlap and one broad drawdown dominates.
- `p_kimi` (+0.32), `p_sig_guidance` (+0.23) and `p_replay_opus` have data in only one or two rebuilds, so I would not treat them as established.
- I can't say what drove the broad decline from this evidence.

_Model cost for this read: $0.039._
