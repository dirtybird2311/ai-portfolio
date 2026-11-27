# Schedule

Every automatic job, when it runs, and what it does. Times are set in the files under
`.github/workflows/` (GitHub uses UTC; Eastern times below, summer / winter). Every job can also be started by hand:
GitHub > Actions > pick the job > **Run workflow**.

| Job | When | What it does | Workflow file |
|---|---|---|---|
| Daily | Weekdays 5:30 pm EDT / 4:30 pm EST | Resumes any stopped run; watches holdings (price moves, news, thesis breaks) | `daily.yml` |
| Weekly | Fridays 6:30 pm EDT / 5:30 pm EST | Macro light check (or the full monthly macro run), quant screen, performance tracking | `weekly.yml` |
| Rebuild | Saturdays 10 am EDT / 9 am EST, every other week (even weeks) | Stock team, judge panel, portfolio manager, trade list email | `rebuild.yml` |
| Connection test | 1st of each month, 9 am EDT / 8 am EST | One tiny call to every AI model, data source and Gmail; emails a pass/fail table (< $0.01) | `connections.yml` |
| Paper orders | Weekdays 10:45 am EDT / 9:45 am EST (paper mode only) | Places approved rebuild trades and watch sales in your Alpaca paper account, sells first; emails what was placed | `orders.yml` |
| Replay | Only when you start it | Replays Opus or a "twin" judge on saved packets | `replay.yml` |
| Backfill 10-K similarity | Once, when you start it (resumes if re-run) | Reads every company's annual reports since 2014 for the "Lazy Prices" signal; the weekly run keeps it current | `backfill.yml` |
| Tests | On every code change | Offline test suite, no API costs | `tests.yml` |

**Run the connection test by hand** after adding or changing a key, after editing model names in
`pipeline/config.py`, and before the first live rebuild.

To change a time, edit the `cron:` line in that workflow file (format: minute hour day month weekday,
in UTC).
