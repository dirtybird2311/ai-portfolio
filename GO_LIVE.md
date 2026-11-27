# Go-live checklist

A checklist for a human decision about putting more real money behind the portfolio. It is not an instruction to
trade, and a good week does not meet it. It is printed at the end of every weekly statistics report
(`python -m pipeline.report --weekly`, or Actions > Statistics report) with each rule's current value.

The thresholds below are a proposal from Oct 16, 2026 and live in `GO_LIVE` in `pipeline/report.py`. Change them
there (and here) only with a written reason in `PARAMETERS.md`'s spirit: not because of last week's returns.

| Rule | Threshold |
|---|---|
| Length of record | at least 60 trading days |
| Rebuilds completed | at least 4 |
| Lead is unlikely to be noise | block-bootstrap p-value at most 0.10 |
| Picks beat random portfolios | median over rebuilds with 10+ days: beats at least 90% |
| Alpha against SPY after beta | positive (shown with its beta; very noisy in short samples) |
| Drawdown | no worse than 1.5x SPY's |
| After AI costs | still ahead of SPY |
| Freeze log | no setting changed without an entry |
| NAV record | no missing weekdays |

How to read it: all nine must be met for a "go" conversation; fewer is "keep paper trading". Even all nine does not
prove skill, it shows nothing in the record argues against it. Stage any real-money increase in steps.
