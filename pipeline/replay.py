"""
REPLAY  —  test a judge later on the exact packets past judges saw (they're archived every rebuild).

    python -m pipeline.replay opus                      # Opus 5.5 on every saved packet not yet replayed
    python -m pipeline.replay twin no_debate            # Sonnet without the debate section
    python -m pipeline.replay twin no_new_inputs        # ... without sensitivities/valuation/peers/track record
    python -m pipeline.replay council --since 2026-11-01  # investor council + hidden council dossier on past packets
    options: --since YYYY-MM-DD  --until YYYY-MM-DD  --judge sonnet  --budget 15

Why this is fair: a model whose training data ends before the packets' dates can't "remember" what
happened next, so its forecasts are as honest as live ones. (A model released later could have seen
the outcomes, so it can only be tested going forward.) Replays must run before the model is retired;
the monthly email reminds you when a retirement date is set in config.REPLAY.

Results go into the decision ledger under ids like "replay_opus" or "twin_no_debate__sonnet", with the
ORIGINAL decision dates, and are graded and reported like every other judge (pruning tests included).
Replays are batched (half price) and resumable.
"""
import argparse
import glob
import gzip
import json
import re

import pandas as pd

from . import config, ledger
from .checkpoint import Checkpoint
from .team import clean_verdict, council_note, with_council
from .util import state_path

VARIANTS = {
    "no_debate": set(),
    "no_news": {"news", "headline"},
    "no_fundamentals": {"fundamentals", "red_flag", "metric", "filing_quote"},
    "no_catalysts": {"catalyst"},
    "no_new_inputs": {"sensitivity", "valuation", "peers", "track_record"},
}


def load_packets(since=None, until=None):
    out = []
    for path in sorted(glob.glob(str(state_path("packets")) + "/*.jsonl.gz")):
        day = re.search(r"(\d{4}-\d{2}-\d{2})", path).group(1)
        if (since and day < since) or (until and day > until):
            continue
        with gzip.open(path, "rt") as f:
            out += [json.loads(line) for line in f if line.strip()]
    return out


def ablate(pk, variant):
    """(shared text, prompt, valid ids) for a twin with one section removed."""
    items = pk.get("items") or []
    drop = VARIANTS[variant]
    kept = [i for i in items if i["kind"] not in drop]
    header = pk["shared"].split("\n", 1)[0]
    shared = header + "\n" + "\n".join(f"{i['id']}. [{i['kind']}] {i['text']}" for i in kept)
    prompt = pk["prompt"]
    if variant == "no_debate":
        prompt = re.sub(r"^ARGUMENTS:\n.*?\n\nUNCITED OR INVALID CLAIMS \(discount these\):\n.*?\n\n",
                        "ARGUMENTS: none (judge from the dossier alone)\n\n", prompt, flags=re.S)
    return shared, prompt, {i["id"] for i in kept}


def run(session, name, variant=None, judge="sonnet", since=None, until=None):
    if name == "opus":
        spec, jid = config.REPLAY["opus"], "replay_opus"
    elif name == "council":
        spec, jid = config.COUNCIL_JUDGE, config.COUNCIL_JUDGE["id"]
    elif name == "twin":
        if variant not in VARIANTS:
            raise SystemExit(f"twin needs one of {sorted(VARIANTS)}")
        spec, jid = config.REPLAY["twin"], f"twin_{variant}__{judge}"
    else:
        raise SystemExit("usage: python -m pipeline.replay opus | twin <variant>")
    led = ledger._ledger()
    done = set(zip(led.date, led.ticker)) if len(led) and jid in set(led.judge) else set()
    if done:
        done = set(zip(led[led.judge == jid].date, led[led.judge == jid].ticker))
    meta = led[led.judge == "panel"].set_index(["date", "ticker"]) if len(led) else pd.DataFrame()
    packets = [pk for pk in load_packets(since, until) if (pk["date"], pk["ticker"]) not in done]
    if not packets:
        print("Nothing to replay (everything saved has been replayed for this judge).")
        return {"replayed": 0}
    print(f"Replaying {len(packets)} packets as {jid} ({spec['model']})")
    ck = Checkpoint(f"replay_{jid}")
    reqs, ctx, notes_of = [], {}, {}
    for pk in packets:
        rid = f"{pk['date']}-{re.sub(r'[^A-Za-z0-9]', '_', pk['ticker'])}"
        if name == "council":
            ids = {i["id"] for i in pk.get("items") or []}
            if ck.has_item("council", rid):
                notes = ck.item("council", rid)
            else:
                notes = ck.save_item("council", rid, council_note(session, pk["shared"], pk.get("args")))
            prompt = with_council(pk["prompt"], notes, ids) if notes else None
            if not prompt:
                continue
            notes_of[rid] = notes
            shared = pk["shared"]
        elif name == "twin":
            shared, prompt, ids = ablate(pk, variant)
        else:
            shared, prompt, ids = pk["shared"], pk["prompt"], {i["id"] for i in pk.get("items") or []}
        ctx[rid] = (pk, ids)
        reqs.append({"id": rid, "role": "judge", "model": spec["model"], "thinking": spec.get("thinking"),
                     "system": pk["system"], "shared": shared, "prompt": prompt, "max_tokens": 1500})
    res = session.batch(reqs, checkpoint=ck, key=jid, tolerate=True, timeout_seconds=9000)
    rows = []
    for rid, (pk, ids) in ctx.items():
        r = res.get(rid)
        v = clean_verdict(r.data if r else None, ids, pk.get("base_p", 0.5))
        if not v:
            continue
        m = meta.loc[(pk["date"], pk["ticker"])] if (pk["date"], pk["ticker"]) in meta.index else {}
        rows.append({"date": pk["date"], "ticker": pk["ticker"], "judge": jid, "model": spec["model"],
                     "p": v["probability"], "base_p": pk.get("base_p"), "sector": m.get("sector") if len(m) else None,
                     "sector_etf": m.get("sector_etf") if len(m) else None})
    if notes_of:                                 # keep the council's notes beside the run they belong to
        from .util import write_json
        for day in sorted({rid[:10] for rid in notes_of}):
            write_json(state_path(f"council_notes_{day}.json"),
                       {rid[11:]: v for rid, v in notes_of.items() if rid.startswith(day)})
    n = ledger.record_replay(rows)
    ck.complete()
    print(f"Recorded {n} replayed forecasts; they are graded with everything else in the monthly report card.")
    return {"replayed": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=["opus", "twin", "council"])
    ap.add_argument("variant", nargs="?")
    ap.add_argument("--judge", default="sonnet")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--budget", type=float, default=15.0)
    a = ap.parse_args()
    config.BUDGET_PER_RUN["replay"] = a.budget
    from .runner import run_stage
    run_stage("replay", lambda s, f: run(s, a.name, a.variant, a.judge, a.since, a.until))


if __name__ == "__main__":
    main()
