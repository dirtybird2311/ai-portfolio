# Parameter freeze log

Every change to a setting that shapes the picks is dated here with the old and new values, the reason and the
evidence that existed at the time. Rule: between rebuilds the settings stay fixed; a change needs a written reason
that is not "last week's returns". Results are judged from the latest entry onward. Bug fixes that change no
setting are not logged here (see EVALUATION.md). Check: `python -m pipeline.freeze`.

Settings covered: see `REGISTRY` in `pipeline/freeze.py` (signal weights, bars and caps, model routing, sizing
bands, turnover cap, probability tables). The SPY sleeve is not a setting: it is whatever the sizing leaves over.

### 2026-10-16  Baseline: the settings as they stand on Oct 16
- Evidence at the time: paper-trading day 14 (started Sep 28), 2 rebuilds; the account is +5.5% vs SPY +0.9%, which is not yet evidence of skill
- Baseline recorded: 40 settings (values in `state/params_baseline.json`).

### 2026-10-23  Sonnet 5.5 added as a shadow judge (not counted); macro critic and watch escalation moved to Sonnet 5.5
- Evidence at the time: 17 trading days of record, 4 rebuilds (incl. Oct 17); live judges unchanged (Sonnet 5, GPT-6 Sol, Gemini 3.1 Pro), so the judge evidence window is not reset
- `config.JUDGE_PANEL`: [{"enabled": true, "id": "sonnet", "live": true, "model": "claude-sonnet-5", "sample": 1.0, "thinking": "medium"}, {"enabled": true, "id": "gpt_sol", "live": tr... -> [{"enabled": true, "id": "sonnet", "live": true, "model": "claude-sonnet-5", "sample": 1.0, "thinking": "medium"}, {"enabled": true, "id": "sonnet55", "live": f...
- `config.MODELS`: {"catalyst": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash", "filing_summary": "gemini-3.8-... -> {"catalyst": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash", "filing_summary": "gemini-3.8-...

### 2026-11-02  Kimi K3 removed (shadow judge and debate fallback): retired by NVIDIA
- Evidence at the time: 26 trading days of record, 5 rebuilds; Kimi K3 returns HTTP 410 Gone (connection test Nov 2) and gave no usable reply at the Oct 17 and Nov 1 rebuilds; it was a shadow judge (not counted) and an unused debate fallback, so live picks are unaffected and the judge evidence window is not reset
- `config.DEBATE_POOL`: [{"max_stocks": 200, "model": "xai:grok-4.3"}, {"max_stocks": 40, "model": "nvidia:deepseek-ai/deepseek-v4.1-flash"}, {"max_stocks": 40, "model": "nvidia:moonsh... -> [{"max_stocks": 200, "model": "xai:grok-4.3"}, {"max_stocks": 40, "model": "nvidia:deepseek-ai/deepseek-v4.1-flash"}]
- `config.JUDGE_PANEL`: [{"enabled": true, "id": "sonnet", "live": true, "model": "claude-sonnet-5", "sample": 1.0, "thinking": "medium"}, {"enabled": true, "id": "sonnet55", "live": f... -> [{"enabled": true, "id": "sonnet", "live": true, "model": "claude-sonnet-5", "sample": 1.0, "thinking": "medium"}, {"enabled": true, "id": "sonnet55", "live": f...

### 2026-11-02  Investor council test: hidden council dossier read by a shadow copy of the live Sonnet judge
- Evidence at the time: 26 trading days of record, 5 rebuilds. Three personas (Graham, Lynch, Druckenmiller) on Gemini Flash write cited notes after the debate; only the shadow judge sonnet_council (Sonnet 5, same settings as the live Sonnet judge) reads them. Live judges, their packets and the picks are unchanged, so the judge evidence window is not reset. Compare p_sonnet_council with p_sonnet in the look-back and evaluation after 4-6 rebuilds; promote only if it beats the standard dossier on rank IC and Brier.
- `config.COUNCIL`: null -> [{"id": "graham", "lens": "Benjamin Graham: margin of safety, balance-sheet strength, price versus conservative value"}, {"id": "lynch", "lens": "Peter Lynch: g...
- `config.COUNCIL_JUDGE`: null -> {"enabled": true, "id": "sonnet_council", "live": false, "model": "claude-sonnet-5", "sample": 1.0, "thinking": "medium"}
- `config.MODELS`: {"catalyst": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash", "filing_summary": "gemini-3.8-... -> {"catalyst": "gemini-3.8-flash", "council": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash",...

### 2026-11-05  Theme cap (25%) and an upcoming-events calendar for the PM and macro view
- Evidence at the time: 27 trading days of record, 5 rebuilds. After the Nov 3 midterms, data-center stocks fell 15-30% in two days and hit SEI, MU (and ECG in the council book) together although they sit in three sectors, so the sector caps and correlation check did not see one bet; the election date was known in advance. The PM now tags each pick's main theme (fixed list) and code caps any theme at 25%; the PM and the macro view see scheduled events (macro-listed elections/votes/deadlines, the FOMC date, holdings' earnings) in the next 28 days. Changes how the live portfolio is sized from the Nov 14 rebuild.
- `config.EVENT_LOOKAHEAD_DAYS`: null -> 28
- `config.THEMES`: null -> ["oil_price", "natural_gas", "refining_margins", "ai_datacenter_buildout", "semiconductors", "consumer_spending", "interest_rates", "housing", "healthcare_polic...
- `config.THEME_CAP`: null -> 25.0

### 2026-11-09  Risk cuts before the Nov 14 rebuild: volatility sizing, 15-20 names at 3-10%, narrower sector ranges, buy edge +2
- Evidence at the time: 30 trading days of record, 5 rebuilds. Look-back of Nov 6: the judges' edge has rank correlation -0.06 with later returns (noise band +/-0.22) yet sized positions up to 15%; picks beat their own shortlist in 2 of 5 rebuilds; a +1 tilt let Energy reach 35% the week it fell about 10%, and the real retirement accounts trailed SPY by 5.5 pts in one week. Changes: SIZE_BY_EDGE off (inverse-volatility weights; edge only orders forced cuts), POS 3-10% (was 5-15%), 15-20 names (was 8-12), TILT_RANGES narrowed (+2: 10-25, +1: 5-22, 0: 0-18, -1: 0-10), ranges recomputed from the stored tilts at use, and buy_edge 3 -> 2 because only 10 of 80 names cleared +3 on Nov 1 (7 of them Energy), too few to fill the book. Aim is lower risk, not higher return; resets the sizing evidence window. Plan: Beating SPY improvement plan, ideas A1-A3.
- `config.PROB`: {"adjust_cap": 15, "buy_edge": 3, "buy_min": 0.5, "clip": [0.03, 0.97], "confirm_rebuilds": 2, "keep_edge": -2, "keep_min": 0.47, "long_term_guard_days": 30, "s... -> {"adjust_cap": 15, "buy_edge": 2, "buy_min": 0.5, "clip": [0.03, 0.97], "confirm_rebuilds": 2, "keep_edge": -2, "keep_min": 0.47, "long_term_guard_days": 30, "s...
- `config.SIZE_BY_EDGE`: null -> false
- `config.TILT_RANGES`: {"-1": [0, 12], "-2": [0, 5], "0": [0, 25], "1": [6, 35], "2": [12, 45]} -> {"-1": [0, 10], "-2": [0, 5], "0": [0, 18], "1": [5, 22], "2": [10, 25]}
- `pm.MAX_STOCKS`: null -> 20
- `pm.MIN_STOCKS`: null -> 15
- `pm.POS_MAX`: null -> 10.0
- `pm.POS_MIN`: null -> 3.0

### 2026-11-09  Paper orders queue for the open; wrong-account guard
- Evidence at the time: GitHub's scheduler started the order job hours late on most trade days (Oct 20 a day late, Nov 4 at 3:57 pm), so paper trades missed the planned open. Alpaca accepts notional day orders while the market is closed and holds them for the open (checked Nov 9 with a 1 dollar SPY order, cancelled). The job now runs the evening before and early morning and queues orders when the open is within PREOPEN_HOURS = 16; failures before the open are retried, not recorded. It also refuses to trade when the Alpaca account holds fewer than half of the book's stocks (the Nov 3 key swap). No change to picks or sizing.
- `broker.PREOPEN_HOURS`: null -> 16

### 2026-11-10  Momentum crash guard in the live screen
- Evidence at the time: Screen backtest of Nov 10 (141 out-of-sample months, 2015-2026): current weights with the momentum family off while the equal-weighted market's last 12 months are negative gave IC 0.019 (t 2.55) against 0.013 (t 1.66) for the current weights, paired difference t 2.13, top-2-per-sector portfolio +7.0% a year over the equal-weighted universe against +4.9%. One of six mixes tried and active in only 15 months, so promising rather than proven; the rule itself was fixed in advance from the momentum-crash literature. Off today (market +20.6% over 12 months), so no effect on the Nov 14 rebuild. the owner approved Nov 10.
- `screen.MOMENTUM_GUARD`: null -> true

### 2026-11-13  Shadow signals: earnings quality, guidance change and read-across, logged only
- Evidence at the time: 32 trading days of record, 5 rebuilds. Three narrow scores per candidate (-2..+2) from one Gemini Flash call after the debate: quality of the last earnings beat, change in guidance, and read-across from same-sub-industry peers that reported in the last 35 days after the stock's own report. Logged to the decision ledger as pseudo-judges sig_beat_quality, sig_guidance, sig_read_across (p = 0.5 + 0.1 x score) and graded by the look-back; no judge, PM or sizing step reads them, so live picks are unchanged. About 80 cheap calls a rebuild. Promote one only if its rank correlation holds over several rebuilds.
- `config.MODELS`: {"catalyst": "gemini-3.8-flash", "council": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash",... -> {"catalyst": "gemini-3.8-flash", "council": "gemini-3.8-flash", "debate_bear": "xai:grok-4.3", "debate_bull": "xai:grok-4.3", "filing_diff": "gemini-3.8-flash",...
- `config.PEER_WINDOW_DAYS`: null -> 35
- `config.SHADOW_SIGNALS`: null -> ["beat_quality", "guidance", "read_across"]

### 2026-11-14  Nov 14 rebuild: owner approved 53% turnover (over the 50% cap) for this run only
- Evidence at the time: the owner approved the blocked plan on Nov 14; the move to 15-20 positions (step 1) forces a large one-time reshuffle. Critic rerun with its reply limit fixed.
- No setting changed.

### 2026-11-14  Owner override Nov 14: SPY 15% parking moved to XOM, CHRD, OXY at 5% each
- Evidence at the time: the owner expects the Iran/Hormuz conflict to escalate. All three were judged bull (edge +5.3 to +5.7) but left out by the 3-per-driver and correlation limits. Energy stocks go to ~29%, above the 25% macro ceiling. AI's original target kept as ai_target in pending_plan.json and rebuild_history.json so the override can be measured separately.
- No setting changed.
