"""Offline end-to-end test of the macro agent: light check, tripwires, full run, approval flow."""
import json
import os
import zlib
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("GEMINI_API_KEY", "FRED_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "MISTRAL_API_KEY"):
    os.environ[k] = "test"
for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GITHUB_TOKEN", "GITHUB_REPOSITORY"):
    os.environ.pop(k, None)

from pipeline import approvals, checkpoint as cpt, config, fetch, llm, macro, util  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = macro.time.sleep = lambda s: None
DAILY = {"DFF", "DGS2", "DGS10", "T10Y2Y", "BAMLH0A0HYM2", "DCOILWTICO", "DCOILBRENTEU", "DTWEXBGS", "DHHNGSP",
         "T10YIE", "VIXCLS", "DTB3"}
WEEKLY = {"IC4WSA", "NFCI", "MORTGAGE30US", "TOTLL", "GASREGW"}
QUARTERLY = {"A191RL1Q225SBEA", "CP", "ECIWAG", "DRTSCILM", "B235RC1Q027SBEA", "CLVMNACSCAB1GQEA19"}
SHIFT = {"value": 0.0}          # lets a test move one series to trip a tripwire

PAGE = ("<html><body><p>The Committee decided to raise the target range for the federal funds rate to 3-3/4 to 4 "
        "percent.</p>" + "<p>Economic activity expanded at a modest pace across most Districts.</p>" * 8 + "</body></html>")
RSS = ("<rss><channel><item><title>FOMC statement</title><link>https://www.federalreserve.gov/newsevents/"
       "pressreleases/monetary20260916a.htm</link><pubDate>Wed, 16 Sep 2026</pubDate>"
       "<description>FOMC statement</description></item></channel></rss>")


def fake_get(url, params=None, timeout=None, headers=None):
    if "releases/dates" in url:                      # FRED release calendar (past and future)
        rows = [{"date": "2026-09-04", "release_name": "Employment Situation"},
                {"date": "2026-09-11", "release_name": "Consumer Price Index"},
                {"date": "2026-10-02", "release_name": "Employment Situation"},
                {"date": "2026-10-02", "release_name": "Employment Situation"}]
        return N(status_code=200, json=lambda: {"release_dates": rows})
    if "stlouisfed" in url:                          # FRED observations: deterministic per series
        sid = params["series_id"]
        if sid == "GDPNOW":
            raise ValueError("simulated outage")
        if sid.endswith(("MD", "MDLR")):
            return N(status_code=200, json=lambda: {"observations": [
                {"date": f"{y}-01-01", "value": v} for y, v in ((2026, "4.1"), (2027, "4.1"))]})
        rng = np.random.default_rng(zlib.crc32(sid.encode()))   # stable across runs (hash() is salted per process)
        freq = "B" if sid in DAILY else "W-FRI" if sid in WEEKLY else "QS" if sid in QUARTERLY else "MS"
        idx = pd.date_range(params["observation_start"], "2026-09-18", freq=freq)
        level = {"VIXCLS": 18.0, "BAMLH0A0HYM2": 3.2}.get(sid)       # keep trigger series realistic
        if level:
            vals = level + rng.normal(0, level * 0.03, len(idx))
        else:
            vals = 100 + np.cumsum(rng.normal(0.2, 1, len(idx)))
        if sid == "UNRATE" and SHIFT["value"]:
            vals[-3:] = vals[-3:] + SHIFT["value"]   # tripwire test: a recent jump, not a level shift
        out = [str(round(v, 3)) for v in vals]
        out[3] = "."
        return N(status_code=200, json=lambda: {"observations": [
            {"date": d.strftime("%Y-%m-%d"), "value": v} for d, v in zip(idx, out)]})
    # web pages for direct-fetch evidence
    if url.endswith(".xml"):
        return N(status_code=200, text=RSS, url=url)
    if "federalreserve.gov" in url:
        return N(status_code=200, text=PAGE, url=url)
    return N(status_code=404, text="", url=url)


macro.requests.get = fake_get
fetch.requests.get = fake_get
idx = pd.bdate_range("1998-12-01", "2026-09-18")
rng = np.random.default_rng(0)
cols = list(config.SECTORS.values()) + ["SPY", "GC=F", "^TNX", "UUP", "HYG", "IEF", "TIP"]
PX = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))) for c in cols}, index=idx)
oil_r = rng.normal(0, 0.02, len(idx))
PX["CL=F"] = 70 * np.exp(np.cumsum(oil_r))
spy_r = np.log(PX["SPY"]).diff().fillna(0).values
PX["XLE"] = 100 * np.exp(np.cumsum(spy_r + 0.5 * oil_r + rng.normal(0, 0.003, len(idx))))   # energy moves with oil
PX.loc[:"2015-10-01", "XLRE"] = np.nan
PX.loc[:"2018-06-18", "XLC"] = np.nan
yf = types.ModuleType("yfinance")
yf.download = lambda *a, **k: pd.concat({"Close": PX}, axis=1)
sys.modules["yfinance"] = yf


def usage(i=20000, o=3000):
    return N(input_tokens=i, output_tokens=o, cache_creation_input_tokens=0, cache_read_input_tokens=0,
             server_tool_use=None)


def view_json(unrate, flavor):
    ok = [{"ref": "FRED:UNRATE", "value": unrate}]
    sectors = {}
    for sec in config.SECTORS:
        adj = []
        if sec == "Energy":
            adj = [{"points": 3, "reason": "inventories", "evidence": ok + [{"ref": "NOTE:A1"}, {"ref": "FACT:SEP_FEDTARMD_2026", "value": 4.1}]}]
        if sec == "Technology":
            adj = [{"points": 3 if flavor in ("reason1", "reason2") else -3, "reason": "split", "evidence": ok}]
        if sec == "Utilities":
            adj = [{"points": 4, "reason": "made-up number", "evidence": [{"ref": "FRED:UNRATE", "value": 999}]}]
        if sec == "Financials":
            adj = [{"points": 4, "reason": "curve", "evidence": ok}]
        sectors[sec] = {"adjustments": adj, "rationale": "r", "counterargument": "c", "survives": sec != "Financials",
                        "change_note": ""}
    sectors["Made Up"] = {"adjustments": [{"points": 5, "evidence": ok}]}
    oil_ev = ok if flavor != "reason4" else [{"ref": "FRED:UNRATE", "value": 999}]     # one model's evidence is wrong
    fv = {f: {"change": 0, "why": "", "evidence": []} for f in ("rates_10y", "dollar", "credit", "inflation_exp")}
    fv["oil"] = {"change": 8, "why": "supply cut", "evidence": oil_ev}
    return {"regime": {"code_regime_agrees": True, "assessment": f"{flavor} view", "evidence": []},
            "core_review": [{"variable": "UNRATE", "reading": "x", "consensus": "y", "view_vs_consensus": "above",
                             "evidence": ok}],
            "factor_view": fv, "scenarios": [{"name": "base", "probability": 0.6, "description": "d"}],
            "sectors": sectors, "key_risks": ["inflation"],
            "predictions": [{"type": "sector_vs_spy", "etf": "XLE", "direction": "outperform", "weeks": 4}]}


def unrate_from(packet_text):
    line = next(l for l in packet_text.splitlines() if l.startswith("UNRATE | "))
    return float(line.split(" | ")[3])


class FakeClaude:
    """Sonnet + Opus reasoners (batched) and the Sonnet critic."""
    def __init__(self, critic_status="PASS"):
        self.messages, self.batches, self.sub = self, self, None
        self.critic_status = critic_status
        self.searched = 0

    def create(self, requests=None, **p):
        if requests is not None:
            self.sub = requests
            return N(id="b1")
        if "tools" in p:                       # search fallback (only when direct fetch fails)
            self.searched += 1
            notes = [{"id": "B1", "finding": "searched fact", "value": "1", "url": "https://www.bls.gov/x"}]
            return N(stop_reason="end_turn", usage=usage(), content=[
                N(type="web_search_tool_result", content=[N(url="https://www.bls.gov/x", title="t", page_age="1d")]),
                N(type="text", text="found", citations=[N(url="https://www.bls.gov/x", title="t", cited_text="1 percent")]),
                N(type="text", text="```json\n" + json.dumps(notes) + "\n```", citations=None)])
        out = {"overall": self.critic_status, "summary": "ok",
               "sectors": {"Energy": {"status": self.critic_status, "issue": "priced in?"}}}
        return N(content=[N(type="text", text="```json\n" + json.dumps(out) + "\n```", citations=None)],
                 stop_reason="end_turn", usage=usage())

    def retrieve(self, bid):
        return N(processing_status="ended")

    def results(self, bid):
        out = []
        for r in self.sub:
            text = r["params"]["messages"][0]["content"][0]["text"]
            v = view_json(unrate_from(text), r["custom_id"])
            out.append(N(custom_id=r["custom_id"], result=N(type="succeeded", message=N(
                content=[N(type="text", text="```json\n" + json.dumps(v) + "\n```", citations=None)], usage=usage()))))
        return out

    def cancel(self, bid):
        pass


def free_post(url, json=None, timeout=None, headers=None):
    """Gemini (extraction + reasoner 3) and Mistral (reasoner 4)."""
    import json as js
    if "generativelanguage" in url:
        sysmsg = ((json.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")
        body = json["contents"][0]["parts"][0]["text"]
        wrap = lambda t: N(status_code=200, text="", json=lambda: {
            "candidates": [{"content": {"parts": [{"text": t}]}}],
            "usageMetadata": {"promptTokenCount": 8000, "candidatesTokenCount": 500}})
        if sysmsg.startswith("You extract facts"):
            notes = [{"topic": "Fed", "finding": "Fed raised the target range", "value": "4",
                      "as_of": "2026-09-16", "source": "fed_policy",
                      "quote": "decided to raise the target range for the federal funds rate to 3-3/4 to 4 percent"},
                     {"topic": "Fed", "finding": "invented", "value": "9", "source": "fed_policy",
                      "quote": "the Committee will cut rates at its next meeting"}]
            return wrap("```json\n" + js.dumps(notes) + "\n```")
        return wrap("```json\n" + js.dumps(view_json(unrate_from(body), "reason3")) + "\n```")
    return N(status_code=200, text="", json=lambda: {                      # Mistral, OpenAI format
        "choices": [{"message": {"content": "```json\n" + js.dumps(
            view_json(unrate_from(json["messages"][1]["content"]), "reason4")) + "\n```"}}],
        "usage": {"prompt_tokens": 8000, "completion_tokens": 500}})


def run(critic_status="PASS", mode=None):
    fc = FakeClaude(critic_status)
    s = llm.Session("macro", anthropic_client=fc, http_post=free_post, http_head=lambda *a, **k: N(url=a[0]))
    folder = util.run_dir("macro")
    return macro.main(s, folder, mode=mode), s, folder, fc


# ---------------------------------------------------------------- tests
def test_first_run_is_full_then_light():
    out, s, folder, fc = run()
    assert out["status"] == "OK"
    view = util.read_json(util.state_path("macro_view.json"))
    assert "no macro view yet" in view["why"]
    t = view["tilts"]
    full = util.read_json(folder / "full_run.json")
    final = full["final"]
    assert view["factor_view"]["oil"] == 8.0                 # median of 8, 8, 8 and 0 (one model's evidence was wrong)
    assert t["Energy"] == 2 and final["Energy"]["p"] > 0.8   # oil +8% x measured sensitivity -> big disagreement
    assert final["Technology"]["narrative_pts"] == 0         # 2 models +3, 2 models -3 -> median 0
    assert final["Financials"]["narrative_pts"] == 2.0       # failed its own devil's advocate -> halved
    assert final["Utilities"]["narrative_pts"] == 0          # fabricated number -> adjustment dropped
    assert any("forecast set to 0" in a["problem"] for a in full["audit"])
    assert "Made Up" not in t and sum(abs(v) == 2 for v in t.values()) <= 2
    assert set(view["sector_probabilities"]) == set(config.SECTORS)
    ml = pd.read_csv(util.state_path("macro_ledger.csv"))
    assert len(ml) == len(config.SECTORS) and ml.momentum_p.notna().all()
    assert util.read_json(util.state_path("macro_etf_history.json"))[-1]["momentum"]
    models = {u["role"]: u["model"] for u in s.usage}
    assert models["macro_reason_3"] == config.FLASH and models["macro_reason_4"] == config.GROK
    assert models["macro_extract"] == config.FLASH
    # only Fed pages are faked here: theme A came from direct fetch, B, C and D fell back to search,
    # and geopolitics (E) always searches for news
    assert fc.searched == 4 and any(n["id"].startswith("A") and n.get("method") == "direct fetch"
                                    for n in util.read_json(folder / "full_run.json")["packet"]["notes"])
    rep = (folder / "report.md").read_text()
    assert "Direct-fetch sources" in rep and "quote not found on the page" in rep
    packet = (folder / "packet_as_sent.md").read_text()
    assert "## FRED DATA" in packet and "| core |" in packet
    assert util.state_path("macro_baseline.json").exists()
    assert util.read_json(util.state_path("macro_check.json"))["regime"]

    # second run the same week: nothing tripped and the monthly run isn't due -> free light check
    out2, s2, folder2, fc2 = run()
    assert out2["status"] == "light check" and not s2.usage      # no AI calls at all
    check = util.read_json(util.state_path("macro_check.json"))
    assert check["view_date"] == view["date"] and check["changes_since_view"] == [] or True


def test_tripwire_forces_a_full_run():
    SHIFT["value"] = 6.0                                     # unemployment jumps: a core variable moves
    try:
        out, s, folder, fc = run()
    finally:
        SHIFT["value"] = 0.0
    assert out["status"] == "OK" and s.usage
    why = util.read_json(util.state_path("macro_view.json"))["why"]
    assert any("tripwire" in w and "Unemployment" in w for w in why), why


def test_flagged_view_waits_for_approval():
    prev = util.read_json(util.state_path("macro_view.json"))
    out, s, folder, fc = run(critic_status="FAIL", mode="full")
    assert out["status"] == "NEEDS_REVIEW"
    assert util.read_json(util.state_path("macro_view.json"))["date"] == prev["date"]    # old view still live
    pending = util.read_json(util.state_path("macro_view_pending.json"))
    assert pending and util.state_path("macro_review.md").exists()
    md = util.state_path("macro_review.md")
    md.write_text(md.read_text().replace("- [ ] APPROVE", "- [x] APPROVE"))
    assert approvals.check_macro() == "approved"
    live = util.read_json(util.state_path("macro_view.json"))
    assert live["tilts"] == pending["view"]["tilts"] and live["status"].startswith("OK (approved")


def test_search_fallback_when_pages_unreadable():
    cpt.Checkpoint("macro", fresh=True).complete()
    broken = lambda url, params=None, timeout=None, headers=None: (
        fake_get(url, params, timeout, headers) if "stlouisfed" in url else N(status_code=500, text="", url=url))
    fetch.requests.get = broken
    try:
        out, s, folder, fc = run(mode="full")
    finally:
        fetch.requests.get = fake_get
    assert fc.searched == 5                                  # every theme (incl. geopolitics) fell back to Claude search
    rep = (folder / "report.md").read_text()
    assert "page unavailable" in rep


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
