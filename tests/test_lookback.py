"""Offline tests for the look-back report (pipeline/lookback.py): fake prices, fake model, real saved state."""
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import lookback  # noqa: E402

N = types.SimpleNamespace
DAYS = pd.bdate_range("2026-09-25", "2026-10-16")


def fake_loader(tickers, start):
    rng = np.random.default_rng(1)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(DAYS), len(tickers))), axis=0)), index=DAYS, columns=tickers)


def test_rank_ic_and_band():
    assert lookback.rank_ic(range(20), range(20)) > 0.99
    assert lookback.rank_ic(range(5), range(5)) != lookback.rank_ic(range(5), range(5))      # too few: nan
    assert 0.2 < lookback.ic_band(80) < 0.25


def test_build_without_model_has_every_section():
    md = lookback.build(fake_loader, use_llm=False, today="2026-10-16")
    assert md and "How each rebuild did" in md and "Which inputs lined up" in md and "panel_p" in md
    assert "Skipped (numbers only)" in md and "biggest hits and misses" in md


def test_model_read_is_included_and_a_model_failure_does_not_lose_the_numbers():
    ok = N(ask=lambda *a, **k: N(text="## What separated winners from losers\nnothing clear"), spent=0.01)
    assert "nothing clear" in lookback.build(fake_loader, use_llm=True, session=ok)

    def boom(*a, **k):
        raise RuntimeError("no key")
    md = lookback.build(fake_loader, use_llm=True, session=N(ask=boom, spent=0))
    assert "unavailable" in md and "How each rebuild did" in md


def test_no_prices_returns_none():
    assert lookback.build(lambda t, s: pd.DataFrame(), use_llm=False) is None


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn(); print("PASS", n)
