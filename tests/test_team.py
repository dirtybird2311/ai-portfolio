"""Offline test of the stock team with simulated Finnhub, SEC, Gemini and Claude."""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("FINNHUB_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "MISTRAL_API_KEY"):
    os.environ[k] = "test"

from pipeline import config, embed, history, inputs, llm, team, util  # noqa: E402

embed.embed = lambda texts, post=None: None          # no embedding service in tests: exact-dedupe only

N = types.SimpleNamespace
llm.time.sleep = lambda s: None
import time as _t  # noqa: E402
_t.sleep = lambda s: None
rng = np.random.default_rng(3)

TICKERS = [f"S{i:02d}" for i in range(30)]
SECT = list(config.SECTORS)
FILING = ("Item 2. Management's Discussion and Analysis of Financial Condition. "
          + "Net revenue increased 14 percent year over year driven by strong demand in our data center segment. " * 60
          + "Item 3. Quantitative and Qualitative Disclosures.")
RELEASE = "The company raised full year guidance to revenue of $4.2 billion reflecting continued strength."


def setup_state():
    rows = []
    for i, t in enumerate(TICKERS):
        rows.append({"ticker": t, "name": f"{t} Corp", "sector": SECT[i % len(SECT)], "kind": "company",
                     "composite": round(0.9 - i * 0.01, 3), "s_momentum": 0.8, "s_earnings": 0.6, "s_quality": 0.7,
                     "s_value": 0.5, "s_insider": 0.5, "mom_12_1": 0.2, "mom_3m": 0.05, "vol_60d": 0.3, "price": 50.0,
                     "mcap": 5e9, "insider_value": 100000.0 if i == 1 else 0.0, "insider_buyers": 2 if i == 1 else 0,
                     "earnings_date": "2026-10-02" if i == 2 else None, "flags": "", "cik": 5000 + i,
                     "sub_industry": "Group A" if i % 2 else "Group B", "q_op_margin": 0.2, "v_ebit_yield": 0.05 + i / 1000})
    bench = pd.DataFrame(rows)
    bench.to_csv(util.state_path("bench.csv"), index=False)
    cands = bench.head(28).assign(incumbent=False).to_dict("records")
    cands.append(dict(bench.iloc[29].to_dict(), incumbent=True))           # low-ranked holding
    util.write_json(util.state_path("candidates.json"), {"date": "2026-09-18", "candidates": cands})
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-09-18", "regime": "Reflation", "fed": "hiking",
                                                         "tilts": {s: (2 if s == "Energy" else 0) for s in SECT}})
    # base rates and today's features (normally written by the weekly pipeline.history step)
    table = {"built": "2026-09-01", "samples": 100000, "overall": 0.48, "recent_overall": 0.47, "groups": {
        "all": {"n": 100000, "p": 0.48, "recent_p": 0.47, "warn": False},
        "e=1|m=5|q=5": {"n": 900, "p": 0.55, "recent_p": 0.49, "warn": True},
        "e=0|m=3|q=3": {"n": 900, "p": 0.47, "recent_p": 0.47, "warn": False},
        "m=3": {"n": 20000, "p": 0.47, "recent_p": 0.47, "warn": False}}}
    util.write_json(util.state_path("base_rates.json"), table)
    feats = {t: {"m": 5 if i < 3 else 3, "e": 1 if i < 3 else 0, "q": 5 if i < 3 else 3, "history_days": 4000,
                 "reactions": [{"date": "2026-07-30", "vs_sector_%": 4.2}, {"date": "2026-04-30", "vs_sector_%": -1.1}],
                 "ps_now": 3.0 + i / 10, "ps_pct_5y": 60, "rev_growth_%": [8.0, 10.0, 12.0]} for i, t in enumerate(TICKERS)}
    util.write_json(util.state_path("current_features.json"), {"date": "2026-09-18", "stocks": feats})
    util.write_json(util.state_path("fundamentals_cache.json"), {str(5000 + i): {
        "revenue": 4e9, "gross_profit": 2e9, "operating_income": 8e8, "net_income": 6e8, "cfo": 7e8, "capex": 1e8,
        "assets": 1e10, "debt": 2e9, "as_of": "2026-06-30", "fetched": "2026-09-01"} for i in range(30)})


def fake_get(url, params=None, timeout=None, headers=None):
    sym = params["symbol"]
    items = [{"headline": f"{sym} wins major contract", "source": "Reuters", "url": "https://www.reuters.com/a", "datetime": 1789000000,
              "summary": "The multi-year award is worth about $2 billion."},
             {"headline": f"{sym} wins major contract", "source": "Dup", "url": "https://x.com/b", "datetime": 1789000000},
             {"headline": f"{sym} faces lawsuit", "source": "AP", "url": "https://apnews.com/c", "datetime": 1789000000},
             {"headline": f"{sym} to the moon!!", "source": "Reddit", "url": "https://www.reddit.com/r/x", "datetime": 1789000000}]
    return N(status_code=200, json=lambda: items if sym != "S05" else [])


def fake_market():
    days = pd.bdate_range(end="2026-09-18", periods=780)
    r = np.random.default_rng(7)
    cols = {t: 100 * np.cumprod(1 + r.normal(0.0003, 0.015, len(days))) for t in TICKERS}
    tnx = 40 + np.cumsum(r.normal(0, 0.5, len(days)))
    cols.update({"^TNX": tnx, "CL=F": 70 * np.cumprod(1 + r.normal(0, 0.02, len(days))),
                 "UUP": 28 * np.cumprod(1 + r.normal(0, 0.004, len(days))),
                 "HYG": 80 * np.cumprod(1 + r.normal(0, 0.004, len(days))),
                 "IEF": 95 * np.cumprod(1 + r.normal(0, 0.003, len(days))),
                 "TIP": 108 * np.cumprod(1 + r.normal(0, 0.003, len(days))),
                 "SPY": 500 * np.cumprod(1 + r.normal(0.0004, 0.01, len(days)))})
    df = pd.DataFrame(cols, index=days)
    df["S00"] = df["S00"] * np.exp(-(tnx - tnx[0]) / 40)           # a genuinely rate-sensitive stock
    return df


MARKET = fake_market()
PER_TICKER = (lambda t, e, p: 6.5, lambda t: 3.2)


PRIOR = FILING.replace("driven by strong demand", "driven by record demand across every region")  # wording change


class FakeSEC:
    def recent_filings(self, cik, forms, days):
        if "8-K" in forms:
            return [{"form": "8-K", "accession": "0001-26-000002", "doc": "k.htm", "filed": "2026-08-05", "items": "2.02,9.01"}]
        return [{"form": "10-Q", "accession": "0001-26-000001", "doc": "q.htm", "filed": "2026-08-06", "items": ""},
                {"form": "10-Q", "accession": "0001-26-000000", "doc": "p.htm", "filed": "2026-05-06", "items": ""}]

    def document_text(self, cik, acc, doc):
        text = PRIOR if doc == "p.htm" else FILING
        if cik == 5000 and doc == "q.htm":
            text += " We identified a material weakness in our internal control over financial reporting."
        return text

    def material_events(self, cik):
        return [{"filed": "2026-09-10", "items": ["5.02"], "what": "a director or executive departure/appointment",
                 "url": "https://www.sec.gov/x"}] if cik == 5000 else []

    def companyfacts(self, cik):
        q = lambda y, m, v: {"start": f"{y}-{m:02d}-01", "end": f"{y}-{m + 2:02d}-28", "val": v, "filed": f"{y}-{m + 3:02d}-10"}
        return {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [q(2025, 4, 100e6), q(2025, 7, 105e6), q(2025, 10, 110e6), q(2026, 1, 112e6),
                                           q(2026, 4, 118e6)]}},
            "InventoryNet": {"units": {"USD": [{"end": "2025-06-28", "val": 50e6}, {"end": "2026-06-28", "val": 70e6}]}}}}}

    def earnings_release_text(self, cik, acc):
        return RELEASE


def gem(text, grounding=None):
    cand = {"content": {"parts": [{"text": text}]}}
    if grounding:
        cand["groundingMetadata"] = grounding
    return N(status_code=200, text="", json=lambda: {"candidates": [cand], "usageMetadata": {"promptTokenCount": 3000, "candidatesTokenCount": 400}})


def sys_and_user(body):
    """Works for Gemini (systemInstruction) and Gemma (instructions inlined in the user text)."""
    user = body["contents"][0]["parts"][0]["text"]
    sysmsg = ((body.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")
    if not sysmsg and user.startswith("INSTRUCTIONS:\n"):
        sysmsg, user = user[len("INSTRUCTIONS:\n"):].split("\n\n", 1)[0], user
    return sysmsg, user


def gemini_post(url, json=None, timeout=None, headers=None):
    """Simulates Gemini/Gemma (Google format) and Groq/Mistral (OpenAI format)."""
    import json as js
    if "generativelanguage" in url:
        sysmsg, body_text = sys_and_user(json)
        wrap = lambda text: N(status_code=200, text="", json=lambda: {
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 3000, "candidatesTokenCount": 400}})
    else:
        sysmsg = json["messages"][0]["content"]
        body_text = json["messages"][1]["content"]
        wrap = lambda text: N(status_code=200, text="", json=lambda: {
            "choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 3000, "completion_tokens": 400}})

    if "For each numbered headline" in sysmsg:
        tick = [line.split(" (")[0] for line in body_text.splitlines() if line and not line.startswith(" ") and "(" in line]
        return wrap("```json\n" + js.dumps({t: ["YES", "NO"] if t != "S03" else ["NO", "NO"] for t in tick}) + "\n```")
    if sysmsg.startswith("You are a careful equity analyst"):
        tick = body_text.split("COMPANY: ")[1].split(" ")[0]
        quotes = [{"point": "demand", "quote": "Net revenue increased 14 percent year over year driven by strong demand", "section": "MD&A"},
                  {"point": "guide", "quote": "raised full year guidance to revenue of $4.2 billion", "section": "Release"}]
        if tick in ("S00", "S06"):      # only these two summaries contain a quote that isn't in the filing
            quotes.insert(1, {"point": "made up", "quote": "Revenue tripled and margins hit record highs across all segments",
                              "section": "MD&A"})
        return wrap("```json\n" + js.dumps({"summary": "Revenue up.", "guidance": "raised", "quotes": quotes,
                                             "red_flags": []}) + "\n```")
    if sysmsg.startswith("You compare a company's latest SEC filing"):
        return wrap('```json\n{"changes": [{"change": "Revenue growth slowed from 22% to 14%", "direction": "negative"}], '
                    '"tone": "more cautious"}\n```')
    if sysmsg.startswith("You are a senior analyst"):          # Mistral: free first-pass review
        t = js.loads(body_text.split("\n\nJSON shape")[0])["ticker"]
        out = {"trajectory": "deteriorating" if t == "S01" else "improving", "score": 4, "one_line": "solid",
               "key_points": [{"point": "margins", "evidence": [{"ref": f"SEC:{t}:operating_margin_%", "value": 20.0},
                                                                {"ref": f"SEC:{t}:gross_margin_%", "value": 99}]},
                              {"point": "demand", "evidence": [{"ref": "NOTE:Q1"}, {"ref": "NOTE:Q2"}]}],
               "red_flags": [], "summary_errors": []}
        return wrap("```json\n" + js.dumps(out) + "\n```")
    if sysmsg.startswith("You are an event-driven analyst"):
        soon = (__import__("datetime").date.today() + __import__("datetime").timedelta(days=20)).isoformat()
        ev = {"events": [{"date": soon, "event": "Product launch", "likely_impact": "positive", "url": "https://www.businesswire.com/news/1"},
                         {"date": "2026-10-20", "event": "Rumor", "likely_impact": "positive", "url": "https://www.reddit.com/r/y"},
                         {"date": "2026-10-25", "event": "Analyst day", "likely_impact": "uncertain", "url": "https://someblog.net/z"},
                         {"date": "2026-10-30", "event": "Invented", "likely_impact": "negative", "url": "https://never-searched.com/q"}]}
        r = wrap("```json\n" + js.dumps(ev) + "\n```")
        data = r.json()
        data["candidates"][0]["groundingMetadata"] = {
            "webSearchQueries": ["q"],
            "groundingChunks": [{"web": {"uri": "https://www.businesswire.com/news/1", "title": "bw"}},
                                {"web": {"uri": "https://someblog.net/z", "title": "sb"}}],
            "groundingSupports": [{"segment": {"text": "launch"}, "groundingChunkIndices": [0]}]}
        return N(status_code=200, text="", json=lambda: data)
    if sysmsg.startswith("You are a judge"):                   # free shadow judge (Mistral)
        return wrap('```json\n{"adjustments": [{"points": -4, "reason": "valuation", "cites": ["D1"]}], "probability": 0.44, '
                    '"winner": "bear", "thesis": "m", "key_risk": "k", "exit_condition": "x", "primary_driver": "rates", '
                    '"evidence": ["D1"]}\n```')
    if sysmsg.startswith("You score three narrow things"):
        return wrap("```json\n" + js.dumps({"beat_quality": {"score": 1, "reason": "core", "cites": ["D1"]},
                                            "guidance": {"score": -5, "reason": "weaker", "cites": ["D2"]},
                                            "read_across": {"score": 2, "reason": "peers beat", "cites": []}}) + "\n```")
    if sysmsg.startswith("You are an investor council"):
        note = {"stance": "favor", "points": [{"claim": "cheap", "cites": ["D1"]}, {"claim": "invented", "cites": ["D77"]}],
                "summary": "s"}
        return wrap("```json\n" + js.dumps({"graham": note, "lynch": note, "druckenmiller": dict(note, stance="against")}) + "\n```")
    if "BULL" in sysmsg or "BEAR" in sysmsg:
        return wrap('```json\n{"points": [{"claim": "good", "cites": ["D1", "D3"]}, {"claim": "made up", "cites": ["D99"]}], "summary": "s"}\n```')
    raise AssertionError(sysmsg[:60])


def usage():
    return N(input_tokens=5000, output_tokens=800, cache_creation_input_tokens=0, cache_read_input_tokens=0, server_tool_use=None)


class FakeClaude:
    def __init__(self):
        self.messages, self.batches, self.sub = self, self, None
        self.batch_sizes = []

    def create(self, **p):  # batches.create and messages.create share this fake
        if "requests" in p:
            self.sub = p["requests"]
            self.batch_sizes.append(len(self.sub))
            return N(id="b")
        sysmsg = p["system"][0]["text"]
        if sysmsg.startswith("You are a financial expert"):                # Haiku labels headlines
            body = p["messages"][0]["content"][-1]["text"]
            tick = [line.split(" (")[0] for line in body.splitlines() if line and not line.startswith(" ") and "(" in line]
            out = {t: ["YES", "NO"] if t != "S03" else ["NO", "NO"] for t in tick}
            return N(content=[N(type="text", text="```json\n" + json.dumps(out) + "\n```", citations=None)],
                     stop_reason="end_turn", usage=usage())
        raise AssertionError("unexpected direct Claude call: " + sysmsg[:40])

    def retrieve(self, b):
        return N(processing_status="ended")

    def results(self, b):
        out = []
        for r in self.sub:
            cid = r["custom_id"]
            t = cid.split("-", 1)[1]
            if cid.startswith(("fund-", "esc-")):
                v = {"trajectory": "improving", "score": 4, "one_line": "solid (Sonnet)",
                     "key_points": [{"point": "margins", "evidence": [{"ref": f"SEC:{t}:operating_margin_%", "value": 20.0},
                                                                      {"ref": f"SEC:{t}:gross_margin_%", "value": 99}]},
                                    {"point": "demand", "evidence": [{"ref": "NOTE:Q1"}, {"ref": "NOTE:Q2"}]}],
                     "red_flags": [], "summary_errors": []}
            else:
                jid, t = t.split("-", 1)                                # judge-<judge id>-<ticker>
                strong = t in ("S00", "S01")
                adj = [{"points": 6, "reason": "guidance raised", "cites": ["D3"]},
                       {"points": 4, "reason": "catalyst", "cites": ["D4"]},
                       {"points": 9, "reason": "made up", "cites": ["D999"]}] if strong else []
                if t == "S02":        # tries to go far past the cap without an exception
                    adj = [{"points": 30, "reason": "huge", "cites": ["D3"]}]
                v = {"adjustments": adj, "probability": 0.9, "winner": "bull", "thesis": "t", "key_risk": "k",
                     "exit_condition": "guidance cut", "primary_driver": "AI capex", "evidence": ["D1", "D999"]}
            msg = N(content=[N(type="text", text="```json\n" + json.dumps(v) + "\n```", citations=None)], usage=usage())
            out.append(N(custom_id=cid, result=N(type="succeeded", message=msg)))
        return out

    def cancel(self, b):
        pass


def batches_create(requests):
    return FC.create(requests=requests)


FC = FakeClaude()
FC.batches = N(create=batches_create, retrieve=FC.retrieve, results=FC.results, cancel=FC.cancel)


def test_team_end_to_end():
    team.SHORTLIST = team.N_DEBATES = 25          # the real run judges config.JUDGED_PER_REBUILD (80)
    setup_state()
    s = llm.Session("team", anthropic_client=FC, http_post=gemini_post, http_head=lambda *a, **k: N(url=a[0]))
    folder = util.run_dir("team")
    team.main(s, folder, sec=FakeSEC(), get=fake_get, market=MARKET, per_ticker=PER_TICKER)
    res = util.read_json(util.state_path("team_results.json"))
    st = res["stocks"]
    assert "S29" in st and st["S29"]["incumbent"]                     # holding always reviewed
    assert len(st) == team.N_DEBATES + 1                              # 25 shortlisted + low-ranked holding
    v0 = st["S00"]["verdict"]
    # base rate for S00's group (momentum 5, strong earnings reaction, top quality) is 55%; the judges'
    # two cited adjustments (+6, +4) count, the uncited +9 is removed
    assert v0["base_p"] == 0.55 and abs(v0["probability"] - 0.65) < 1e-6 and v0["edge_pts"] == 10.0
    assert v0["conviction"] == 5 and st["S05"]["verdict"]["edge_pts"] == 0.0
    assert abs(st["S02"]["verdict"]["probability"] - (0.55 + 0.15)) < 1e-6          # capped at +15 (no exception)
    assert st["S10"]["verdict"]["base_p"] == 0.47
    assert st["S00"]["news"]["count"] == 2 and st["S00"]["news"]["score"] == 0.0   # dup + reddit removed
    assert st["S03"]["news"]["score"] == -1.0
    assert st["S00"]["verdict"]["evidence"] == ["D1"]                 # D999 stripped
    kinds0 = [i["kind"] for i in st["S00"]["dossier"]]
    assert kinds0[0] == "base_rate" and "WARNING" in st["S00"]["dossier"][0]["text"]
    assert {"sensitivity", "valuation", "peers", "track_record"} <= set(kinds0)
    assert st["S00"]["sensitivity"]["rates_10y"]["label"] != "none"   # the rate-sensitive stock is detected
    assert "options price a ±6.5% move" in next(i["text"] for i in st["S02"]["dossier"] if i["kind"] == "valuation")
    assert len(st["S00"]["dossier"]) <= config.DOSSIER_MAX_ITEMS
    assert any("D99" in b for b in st["S00"]["verdict"]["invalid_citations"])
    rc = util.read_json(util.state_path("research_cache.json"))
    picks_count = len([k for k in rc if not k.startswith("_")])
    f = rc["S00"]["fundamentals"]
    q = {x["id"]: x["verified"] for x in f["quotes"]}
    assert q == {"Q1": True, "Q2": False, "Q3": True}                 # fabricated quote caught
    assert any("gross_margin" in p for p in f["audit_problems"])      # wrong number caught
    assert any("NOTE:Q2" in p for p in f["audit_problems"])           # unverified quote can't support
    ev = rc["S00"]["catalysts"]["events"]
    by = {e["event"]: e for e in ev}
    assert by["Product launch"]["score_eligible"] and not by["Analyst day"]["score_eligible"]
    assert "Rumor" not in by and "Invented" not in by
    assert rc["S02"]["catalysts"]["events"][0]["event"] == "Scheduled earnings report"
    # hidden council dossier: notes saved, a shadow council judge scored, never counted in the live average
    assert st["S00"]["council"] and set(st["S00"]["council"]) == {"graham", "lynch", "druckenmiller"}
    vj = st["S00"]["verdict"]["judges"]
    assert "sonnet_council" in vj and vj["sonnet_council"]["live"] is False
    assert "sonnet_council" not in st["S00"]["verdict"]["live_judges"]
    sub = {r["custom_id"]: json.dumps(r) for r in FC.sub}
    assert "INVESTOR COUNCIL" in sub["judge-sonnet_council-S00"] and "INVESTOR COUNCIL" not in sub["judge-sonnet-S00"]
    assert "D77" in sub["judge-sonnet_council-S00"]                    # the council's bad citation is flagged to it
    # shadow signals: scored, clipped to -2..+2, logged as pseudo-judges, never part of the verdict
    sg = st["S00"]["shadow_signals"]
    assert sg["beat_quality"]["score"] == 1 and sg["guidance"]["score"] == -2 and "sig_guidance" not in st["S00"]["verdict"]["judges"]
    kinds = {i["kind"] for i in st["S00"]["dossier"]}
    assert {"macro", "screen", "news", "fundamentals", "metric", "filing_quote", "catalyst"} <= kinds
    assert not any("made up" in i["text"] for i in st["S00"]["dossier"])  # unverified quote kept out of dossier
    assert (folder / "report.md").exists()
    claude = [u for u in s.usage if u["model"].startswith("claude") and u["role"] not in ("news", "watch_news")]
    assert claude and all(u["batched"] for u in claude)               # every research Claude call went through batch
    by_role = {}
    for u in s.usage:
        by_role.setdefault(u["role"], set()).add(u["model"])
    assert by_role["news"] == {config.HAIKU, config.GEMMA}   # Haiku live; Gemma in the background (no NVIDIA key in tests)
    lab = pd.read_csv(util.state_path("label_ledger.csv"))
    assert set(lab[lab.live].model) == {config.HAIKU} and config.GEMMA in set(lab[~lab.live].model)
    assert any("-- " in i["text"] for i in st["S00"]["dossier"] if i["kind"] == "headline")   # Finnhub summary kept
    assert all(i.get("date") for i in st["S00"]["dossier"] if i["kind"] in ("headline", "fundamentals", "base_rate"))
    d0 = {i["kind"]: i["text"] for i in st["S00"]["dossier"]}
    assert "executive departure" in d0["event_8k"] and "MATERIAL WEAKNESS" in d0["filing_flag"]
    assert "slowed from 22% to 14%" in d0["filing_change"] and "tone more cautious" in d0["filing_change"]
    assert "inventory growth yoy % 40.0" in d0["financials"] or "Quarterly revenue" in d0["financials"]
    assert "Analyst estimates" in d0["estimates"]
    kinds_s01 = {i["kind"] for i in st["S01"]["dossier"]}
    assert "event_8k" not in kinds_s01 and "filing_flag" not in kinds_s01
    assert by_role["filing_summary"] == {config.FLASH}
    assert by_role["fundamentals"] == {config.FLASH}          # free first-pass review
    assert by_role["fundamentals_escalation"] == {"claude-sonnet-5"}  # second opinion where it matters
    # debates: Grok is the main slot (NVIDIA has no key here; Mistral is no longer in the pool)
    assert by_role["debate_bull"] == by_role["debate_bear"] == {config.GROK}
    dm = {t: v["debate"].get("model") for t, v in st.items()}
    assert set(dm.values()) == {config.GROK}
    # no OpenAI / paid-Gemini / NVIDIA keys in this test: those judges are skipped, the rest still judge
    assert by_role["judge"] == {config.SONNET, config.SONNET_55, config.GROK}   # live Sonnet, shadow Sonnet 5.5 and Grok
    v0 = st["S00"]["verdict"]
    assert v0["live_judges"] == ["sonnet"] and v0["lead_judge"] == "sonnet"
    assert "opus" not in v0["judges"]                                     # Opus is replayed later, not run live
    assert abs(v0["judges"]["grok"]["probability"] - 0.51) < 1e-6      # 0.55 - 4
    assert abs(v0["probability"] - 0.65) < 1e-6                           # shadows don't move the forecast
    led = pd.read_csv(util.state_path("decision_ledger.csv"))
    assert set(led.judge) == {"sonnet", "sonnet55", "sonnet_council", "grok", "panel", "panel_sharp", "base_rate",
                              "sig_beat_quality", "sig_guidance", "sig_read_across"}
    sig = led[led.judge == "sig_guidance"]
    assert len(sig) and not sig.live.any() and abs(sig.p.iloc[0] - 0.3) < 1e-9
    assert abs(led[(led.ticker == "S00") & (led.judge == "base_rate")].p.iloc[0] - 0.55) < 1e-9
    import gzip
    with gzip.open(util.state_path(f"packets/{res['date']}.jsonl.gz"), "rt") as f:
        pk = [json.loads(line) for line in f]
    assert len(pk) == len(st) and pk[0]["system"].startswith("You are a judge") and pk[0]["items"]
    assert led.ticker.nunique() == len(st)                            # every judged stock, not just buys
    assert led.code_version.notna().all() and led.prompt_hash.notna().all()
    errs = pd.read_csv(util.state_path("process_errors.csv"))
    assert int(errs[errs.category == "invalid_citations"]["count"].iloc[0]) > 0
    assert res["panel"] and res["versions"]["config_hash"]
    assert all(not u["fallback"] for u in s.usage)
    esc = {t for t, v in rc.items() if isinstance(v, dict) and (v.get("fundamentals") or {}).get("review", {}).get("escalated_because")}
    assert "S01" in esc                                               # deteriorating -> Sonnet took over
    assert all((rc[t]["fundamentals"]["review"] or {}).get("reviewed_by") for t in esc)
    n_esc = len(esc)
    assert 0 < n_esc < picks_count, (n_esc, picks_count)              # not everything escalates
    print(f"    simulated Claude cost ${sum(u['cost'] for u in claude):.2f}; "
          f"{n_esc}/{picks_count} reviews escalated to Sonnet; free calls "
          f"{sum(1 for u in s.usage if not u['model'].startswith('claude'))}")

    # second run two days later: research carried forward (no new filings, no material news)
    s2 = llm.Session("team", anthropic_client=FC, http_post=gemini_post, http_head=lambda *a, **k: N(url=a[0]))
    team.main(s2, folder, sec=FakeSEC(), get=fake_get, market=MARKET, per_ticker=PER_TICKER)
    res2 = util.read_json(util.state_path("team_results.json"))
    statuses = {v["research_status"] for v in res2["stocks"].values()}
    assert statuses == {"carried forward"}, statuses
    # every stock, the holding included, is judged fresh (4-week forecasts go stale by the next rebuild)
    assert not any(v["verdict"].get("reused_from") for v in res2["stocks"].values())
    assert res2["stocks"]["S29"]["verdict"]["live_judges"] == ["sonnet"]
    assert util.read_json(util.state_path("guidance_history.json"))["S00"][0]["guidance"] == "raised"
    # the second run's prompts carry the process note built from the first run's errors
    assert "PROCESS NOTES FROM THE LAST RUN" in team.ledger.error_feedback()


if __name__ == "__main__":
    test_team_end_to_end()
    print("PASS test_team_end_to_end")
