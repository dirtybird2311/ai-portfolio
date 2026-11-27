"""Tests for this round of changes (all offline)."""
import json
import os
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "MISTRAL_API_KEY", "FRED_API_KEY"):
    os.environ[k] = "test"
for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.pop(k, None)

from pipeline import approvals, checkpoint as cpt, config, embed, fetch, llm, macro, runner, sec, util  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = lambda s: None


def ok_json(data):
    return N(status_code=200, text="", json=lambda: data)


def usage():
    return N(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0, server_tool_use=None)


# ---------------------------------------------------------------- fallback chain + providers
def test_chain_routes_through_free_providers():
    calls = []

    def post(url, json=None, timeout=None, headers=None):
        calls.append(url)
        if "api.x.ai" in url:
            return N(status_code=429, text="rate limited", json=lambda: {})          # Grok busy
        if "generativelanguage" in url:
            return N(status_code=503, text="overloaded", json=lambda: {})            # Gemini + Gemma down
        assert "mistral" in url and headers["Authorization"] == "Bearer test"
        assert json["messages"][0]["role"] == "system"                              # OpenAI format
        return ok_json({"choices": [{"message": {"content": '```json\n{"points": []}\n```'}}],
                        "usage": {"prompt_tokens": 900, "completion_tokens": 100}})

    s = llm.Session("team", http_post=post)
    assert config.MISTRAL_MEDIUM not in llm.chain("debate_bull")                     # dropped from the last resort (Oct 2026)
    try:
        s.ask("debate_bull", "sys", "prompt", shared="dossier")
        raise AssertionError("with Grok, Gemini and Gemma all down the call must fail, not fall back to Mistral")
    except RuntimeError:
        pass
    assert llm.chain("judge") == ["claude-sonnet-5"]                                  # Claude roles never fall back
    assert all(llm.supports_search(m) for m in llm.chain("catalyst", search=True))


def test_gemma_gets_instructions_inline():
    seen = {}

    def post(url, json=None, timeout=None, headers=None):
        seen.update(json)
        return ok_json({"candidates": [{"content": {"parts": [{"text": '{"A": ["YES"]}'}]}}],
                        "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 5}})

    llm.Session("team", http_post=post).ask("news", "LABEL HEADLINES", "A (Acme): 1. up")
    assert "systemInstruction" not in seen and "thinkingConfig" not in seen["generationConfig"]
    assert seen["contents"][0]["parts"][0]["text"].startswith("INSTRUCTIONS:\nLABEL HEADLINES")


def test_budget_spans_attempts():
    ck = cpt.Checkpoint("macro", fresh=True)
    cpt.add_spent("macro", 1.40)                           # earlier attempt spent most of the $1.50 cap

    class C:
        messages = None

        def create(self, **p):
            return N(content=[N(type="text", text="{}", citations=None)], stop_reason="end_turn",
                     usage=N(input_tokens=100_000, output_tokens=0, cache_creation_input_tokens=0,
                             cache_read_input_tokens=0, server_tool_use=None))

    c = C()
    c.messages = c

    def main(session, folder):
        assert abs(session.budget - 0.10) < 1e-9
        session._client = c
        session.ask("macro_critic", "s", "p")          # $0.20 -> over what's left
        session.ask("macro_critic", "s", "p")

    assert runner.run_stage("macro", main, quiet=True, exit_on_fail=False) is None
    assert cpt.spent("macro") >= 1.60                   # this attempt's spend added to the run's total
    ck.complete()


# ---------------------------------------------------------------- direct fetch + verified extraction
PAGE = "<html><body><p>The Committee decided to raise the target range for the federal funds rate to 3-3/4 to 4 percent.</p>" + \
       "<p>Inflation remains elevated and the Committee is strongly committed to returning inflation to its 2 percent objective.</p>" * 6 + "</body></html>"
RSS = """<rss><channel><item><title>FOMC statement</title><link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm</link>
<pubDate>Wed, 16 Sep 2026</pubDate><description>Federal Reserve issues FOMC statement</description></item></channel></rss>"""


def fake_web(url, headers=None, timeout=None, params=None):
    if url.endswith(".xml"):
        return N(status_code=200, text=RSS, url=url)
    if "monetary20260916a" in url or "fomccalendars" in url:
        return N(status_code=200, text=PAGE, url=url)
    if "beige-book-default" in url:
        return N(status_code=200, text='<a href="/monetarypolicy/beigebook202609.htm">Sept</a>', url=url)
    if "beigebook202609" in url:
        return N(status_code=200, text=PAGE.replace("Committee", "District"), url=url)
    if "cmegroup" in url:
        return N(status_code=200, text="<html><script>app()</script></html>", url=url)    # JavaScript-only page
    if "truflation" in url:
        return N(status_code=200, text=PAGE, url="https://evil-mirror.example/x")        # redirected off-list
    return N(status_code=404, text="", url=url)


def test_fetch_sources():
    srcs = {s["id"]: s for t in fetch.SOURCES.values() for s in t}
    r = fetch.fetch_source(srcs["fed_policy"], fake_web)
    assert "FULL TEXT OF NEWEST ITEM" in r["text"] and "monetary20260916a" in r["url"]
    assert "District" in fetch.fetch_source(srcs["beige_book"], fake_web)["text"]         # followed the link
    assert "JavaScript" in fetch.fetch_source(srcs["fedwatch"], fake_web)["error"]
    assert "off the allowed" in fetch.fetch_source(srcs["truflation"], fake_web)["error"]
    assert "unavailable" in fetch.fetch_source(srcs["aaii"], fake_web)["error"]


def test_extraction_verifies_quotes():
    def post(url, json=None, timeout=None, headers=None):
        notes = [{"topic": "Fed", "finding": "Fed raised rates", "value": "4", "as_of": "2026-09-16", "source": "fed_policy",
                  "quote": "decided to raise the target range for the federal funds rate to 3-3/4 to 4 percent"},
                 {"topic": "Fed", "finding": "made up", "value": "5", "source": "fed_policy",
                  "quote": "the Committee will cut rates by 50 basis points next month"},
                 {"topic": "x", "finding": "wrong source", "source": "nope", "quote": "whatever words here and more"}]
        return ok_json({"candidates": [{"content": {"parts": [{"text": "```json\n" + js.dumps(notes) + "\n```"}]}}],
                        "usageMetadata": {"promptTokenCount": 5000, "candidatesTokenCount": 300}})
    js = json
    s = llm.Session("macro", http_post=post)
    themes = {"A": ("Fed", "- decisions")}
    notes, dropped, log, need = fetch.gather_direct(s, themes, "2026-09-20", fake_web)
    assert [n["finding"] for n in notes] == ["Fed raised rates"] and notes[0]["verified_number"] is True
    assert {d["reason"] for d in dropped} == {"quote not found on the page", "named a source that wasn't provided"}
    assert need == []                                   # 2 of 4 Fed sources read -> no search fallback
    statuses = {x["source"]: x["status"] for x in log}
    assert statuses["fed_policy"] == "used" and statuses["fomc_calendar"] == "read, nothing extracted"


# ---------------------------------------------------------------- dedupe + boilerplate
def test_embedding_dedupe():
    vec = {"Acme beats estimates": [1, 0, 0], "Acme tops Q3 forecasts": [0.97, 0.24, 0], "Acme sued by FTC": [0, 1, 0]}

    def post(url, json=None, headers=None, timeout=None):
        texts = [r["content"]["parts"][0]["text"] for r in json["requests"]]
        return ok_json({"embeddings": [{"values": vec[t]} for t in texts]})

    items = [{"headline": h} for h in vec]
    kept, merged = embed.dedupe(items, post=post)
    assert [k["headline"] for k in kept] == ["Acme beats estimates", "Acme sued by FTC"] and merged == 1
    assert embed.dedupe(items, post=lambda *a, **k: N(status_code=500))[1] == 0     # failure -> unchanged


def test_boilerplate_keeps_figures():
    t = "Revenue rose 9% to $2.1 billion.\n\nForward-Looking Statements\n\nThis report contains forward-looking statements. " \
        "We undertake no obligation to update them.\n\nGuidance, a forward-looking statement, is $8.5 billion at 41% margin."
    out = sec.strip_boilerplate(t)
    assert "Revenue rose" in out and "Guidance" in out and "undertake" not in out


# ---------------------------------------------------------------- macro: economy forecast -> sector probabilities -> tilts
def test_macro_combine_from_factor_forecasts():
    sens = {s: {"beta": {"rates_10y": 0.0, "oil": 0.0, "dollar": 0.0, "credit": 0.0, "inflation_exp": 0.0}, "sd_4w_%": 3.0}
            for s in macro.SECTORS}
    sens["Energy"]["beta"]["oil"] = 0.5          # +0.5% vs SPY per +1% oil
    sens["Utilities"]["beta"]["rates_10y"] = -0.02   # -0.02% per +1bp
    sens["Financials"]["beta"]["rates_10y"] = 0.03
    base = {s: {"p": 0.5, "n_months": 40} for s in macro.SECTORS}
    base["Technology"]["p"] = 0.56               # history says Tech tends to win in regimes like this...
    packet = {"sector_sensitivities": sens, "sector_base_rates": base,
              "market_implied": {"rates_10y": 0, "oil": 0, "dollar": 0, "credit": 0, "inflation_exp": 0}}

    def run(oil, rates, energy_pts=0.0):
        fv = {f: {"change": 0.0} for f in macro.FACTORS}
        fv["oil"], fv["rates_10y"] = {"change": oil}, {"change": rates}
        return {"model": "m", "factor_view": fv, "tilts": {"Energy": {"points": energy_pts}}}

    runs = [run(8, 25), run(6, 25), run(10, 30, 2.0), run(-2, 0)]
    final, moves = macro.combine(runs, None, packet)
    assert moves["oil"] == 7.0 and moves["rates_10y"] == 25.0          # medians of the four models
    e, u, f, t = final["Energy"], final["Utilities"], final["Financials"], final["Technology"]
    assert e["p"] > 0.8 and e["tilt"] == 2                             # oil +7% x 0.5 = +3.5% vs 3% noise
    assert f["tilt"] == 2 and u["disagreement_pts"] < -6
    assert u["tilt"] == -1 and "only two full tilts" in u["note"]     # third-largest bet capped at -1
    assert sum(abs(v["tilt"]) == 2 for v in final.values()) == 2        # at most two full tilts
    # ...but agreeing with history is not disagreeing with the market: Tech stays neutral
    assert t["p"] == 0.56 and t["disagreement_pts"] == 0 and t["tilt"] == 0
    # no forecast change at all -> every sector neutral, whatever the base rates say
    calm, _ = macro.combine([run(0, 0)], None, packet)
    assert all(v["tilt"] == 0 for v in calm.values())


def test_macro_tilt_buffer():
    assert macro.tilt_for(3.1, 0) == 1 and macro.tilt_for(2.5, 0) == 0     # needs 2 + 1 buffer to start
    assert macro.tilt_for(1.5, 1) == 1 and macro.tilt_for(0.9, 1) == 0     # and to stop
    assert macro.tilt_for(5.5, 1) == 1 and macro.tilt_for(6.1, 1) == 2


# ---------------------------------------------------------------- tripwires, schedule, digest, tables
def row(z, latest, tier="core", label="x"):
    return {"id": "X", "label": label, "tier": tier, "latest": latest, "z_5yr": z, "flags": [], "as_of": "2026-09-01"}


def test_tripwires_schedule_digest():
    base = {"date": "2026-09-01", "dff": 3.9, "facts": {"SEP_FEDTARMD_2026": 4.1},
            "fred": {"UNRATE": {"latest": 4.2, "z": 0.5}, "BAMLH0A0HYM2": {"latest": 3.0, "z": 1.5}, "DFF": {"latest": 3.9, "z": 0}}}
    fred = {"UNRATE": row(1.7, 4.6, label="Unemployment"), "BAMLH0A0HYM2": row(2.3, 4.1, label="HY spread"),
            "DFF": dict(row(0, 4.15, label="Fed funds"), id="DFF")}
    w = macro.tripwires(fred, {"SEP_FEDTARMD_2026": 4.1}, [], base)
    assert any("Unemployment moved +1.2" in x for x in w) and any("HY spread is newly unusual" in x for x in w)
    assert any("Fed funds rate changed" in x for x in w) and not any("dot plot" in x for x in w)
    assert any("dot plot" in x for x in macro.tripwires(fred, {"SEP_FEDTARMD_2026": 4.35}, [], base))
    assert macro.tripwires(fred, {}, ["VIX at 40"], None) == ["VIX at 40"]

    macro.release_dates = lambda start, end, with_future: [
        {"date": "2026-09-04", "release_name": "Employment Situation"}, {"date": "2026-09-11", "release_name": "Consumer Price Index"}]
    macro.TODAY = pd.Timestamp("2026-09-18").date()
    assert "jobs report (2026-09-04) and CPI (2026-09-11)" in macro.full_run_due(base, {"date": "2026-09-01"})
    assert macro.full_run_due(dict(base, date="2026-09-12"), {"date": "2026-09-12"}) is None
    assert macro.full_run_due(None, None) == "no macro view yet"
    assert "5 weeks" in macro.full_run_due(dict(base, date="2026-08-01"), {"d": 1})
    d = macro.what_changed(fred, base)
    assert d[0]["label"] == "Unemployment" and d[0]["at_view"] == 4.2 and d[0]["now"] == 4.6


def test_render_packet_is_complete_and_compact():
    p = {"today": "2026-09-20", "why_this_run": ["tripwire: VIX"], "facts": {"SEP_FEDTARMD_2026": 4.1},
         "fred": {"UNRATE": {"id": "UNRATE", "label": "Unemployment rate %", "tier": "core", "latest": 4.3, "as_of": "2026-08-01",
                             "3m_ago": 4.1, "12m_ago": 4.0, "direction_3m": "rising", "z_5yr": 1.2, "percentile_5yr": 88.0, "flags": []}},
         "calc": {"regime": "Stagflation risk", "market_implied_fed_path": {"2yr_minus_fed_funds": 0.3, "reading": "hikes"}},
         "history_by_regime": {"current_regime": "Stagflation risk", "current_fed": "hiking",
                               "sectors": {"Energy": {"same_regime_1m": {"avg_excess_%": 1.2, "beat_spy_%": 60.0, "n_months": 40}}}},
         "momentum": {"Energy": {"excess_vs_spy_1m_%": 2.0, "excess_vs_spy_3m_%": 5.5}},
         "notes": [{"id": "A1", "finding": "Fed raised", "value": "4", "as_of": "2026-09-16", "url": "https://fed", "verified_number": True}],
         "calendar": [{"date": "2026-10-02", "release": "Employment Situation"}], "triggers": [],
         "previous_view": {"date": "2026-08-15", "tilts": {"Energy": 1}}, "prediction_scorecard": {"graded": 0}}
    text = macro.render_packet(p)
    for needle in ("UNRATE | Unemployment rate % | core | 4.3 | 2026-08-01 | 4.1 | 4 | rising | 1.2 | 88",
                   "SEP_FEDTARMD_2026 | 4.1", "market_implied_fed_path | 2yr_minus_fed_funds=0.3; reading=hikes",
                   "Energy | same_regime_1m | 1.2 | 60 | 40", "Energy | 2 | 5.5 |", "A1 | Fed raised | 4 | 2026-09-16",
                   "date 2026-08-15: Energy +1", "tripwire: VIX"):
        assert needle in text, needle
    # on a realistic packet (45 series) the tables are far smaller than the JSON they replace
    big = dict(p, fred={f"S{i}": dict(p["fred"]["UNRATE"], id=f"S{i}") for i in range(45)})
    assert len(macro.render_packet(big)) < len(json.dumps(big)) * 0.6


# ---------------------------------------------------------------- approvals
def test_macro_approval_roundtrip():
    view = {"date": "2026-09-20", "tilts": {"Energy": 2, "Utilities": 0}}
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-08-15", "tilts": {"Energy": 1}})
    pend = approvals.request_macro_review(view, {"overall": "FAIL", "summary": "weak evidence",
                                                 "sectors": {"Energy": {"status": "FAIL", "issue": "cites stale oil data"}}})
    assert pend["issue"] is None and "cites stale oil data" in util.state_path("macro_review.md").read_text()
    assert approvals.check_macro() == "waiting"
    assert util.read_json(util.state_path("macro_view.json"))["date"] == "2026-08-15"       # old view still live
    md = util.state_path("macro_review.md")
    md.write_text(md.read_text().replace("- [ ] APPROVE", "- [x] APPROVE"))
    assert approvals.check_macro() == "approved"
    live = util.read_json(util.state_path("macro_view.json"))
    assert live["date"] == "2026-09-20" and live["status"].startswith("OK (approved")
    assert approvals.check_macro() is None                                                  # nothing pending now


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
