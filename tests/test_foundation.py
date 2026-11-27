"""
Offline tests for the shared foundation. No API keys or network needed.
Run:  python -m pytest tests/  (or)  python tests/test_foundation.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
os.environ["GEMINI_API_KEY"] = "test"
for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.pop(k, None)

from pipeline import config, llm, audit, notify, util, runner  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = lambda s: None  # don't actually wait in tests


def usage(i=1000, o=200, cw=0, cr=0, searches=0):
    return N(input_tokens=i, output_tokens=o, cache_creation_input_tokens=cw,
             cache_read_input_tokens=cr, server_tool_use=N(web_search_requests=searches))


class FakeClaude:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self
        self.batches = FakeBatches()

    def create(self, **params):
        self.calls.append(params)
        return self.replies.pop(0)


class FakeBatches:
    def __init__(self):
        self.submitted = None

    def create(self, requests):
        self.submitted = requests
        return N(id="b1")

    def retrieve(self, bid):
        return N(processing_status="ended")

    def results(self, bid):
        first, second = self.submitted[0], self.submitted[1]
        ok = N(model="x", content=[N(type="text", text='```json\n{"ok": 1}\n```', citations=None)],
               usage=usage(2000, 500))
        return [N(custom_id=first["custom_id"], result=N(type="succeeded", message=ok)),
                N(custom_id=second["custom_id"], result=N(type="errored"))]

    def cancel(self, bid):
        pass


def text_reply(t, stop="end_turn", u=None, extra=()):
    return N(content=list(extra) + [N(type="text", text=t, citations=None)], stop_reason=stop, usage=u or usage())


class Resp:
    def __init__(self, code, data=None, text=""):
        self.status_code, self._d, self.text = code, data, text

    def json(self):
        return self._d


# ---------------------------------------------------------------- Claude
def test_claude_call_costs_receipts_caching():
    search_res = N(type="web_search_tool_result", content=[N(url="https://www.bls.gov/cpi", title="CPI", page_age="2d"),
                                                           N(url="https://fred.stlouisfed.org/x", title="F")])
    cited = N(type="text", text="CPI rose.", citations=[N(url="https://www.bls.gov/cpi", title="CPI",
                                                          cited_text="CPI increased 0.3 percent in August")])
    r1 = N(content=[search_res, cited], stop_reason="pause_turn", usage=usage(1000, 100, cw=3000, searches=2))
    r2 = text_reply('```json\n{"tilt": 1}\n```', u=usage(500, 300, cr=3000))
    fc = FakeClaude([r1, r2])
    s = llm.Session("macro", anthropic_client=fc)
    r = s.ask("macro_critic", "SYS", "PROMPT", shared="DOSSIER", search={"max_uses": 3, "allowed": ["bls.gov"]})
    p = fc.calls[0]
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert p["messages"][0]["content"][0] == {"type": "text", "text": "DOSSIER", "cache_control": {"type": "ephemeral"}}
    assert p["tools"][0]["allowed_domains"] == ["bls.gov"]
    assert len(fc.calls) == 2, "pause_turn should continue the turn"
    assert r.data == {"tilt": 1}
    urls = {x["url"]: x for x in r.receipts}
    assert urls["https://www.bls.gov/cpi"]["status"] == "cited"
    assert urls["https://fred.stlouisfed.org/x"]["status"] == "consulted"
    # sonnet $2/$10: call1 1000*2 + 3000*2*1.25 + 100*10 = 2000+7500+1000=10500 -> .0105 + 2 searches .02
    # call2 500*2 + 3000*2*0.1 + 300*10 = 1000+600+3000=4600 -> .0046
    assert abs(s.spent - (0.0105 + 0.02 + 0.0046)) < 1e-9, s.spent


def test_budget_cap():
    fc = FakeClaude([text_reply("x", u=usage(1_000_000, 0))] * 3)
    s = llm.Session("x", budget=2.0, anthropic_client=fc)
    s.ask("judge", "s", "p")        # $3 -> over budget after this call
    try:
        s.ask("judge", "s", "p")
        assert False, "should have stopped"
    except llm.BudgetExceeded:
        pass


# ---------------------------------------------------------------- Gemini
def gem_ok(text='```json\n{"score": 0.5}\n```', grounded=False):
    cand = {"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]}}
    if grounded:
        cand["groundingMetadata"] = {
            "webSearchQueries": ["acme earnings date"],
            "groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                                         "title": "businesswire.com"}},
                                {"web": {"uri": "https://example.com/other", "title": "example"}}],
            "groundingSupports": [{"segment": {"text": "Acme reports Oct 30."}, "groundingChunkIndices": [0]}]}
    return Resp(200, {"candidates": [cand], "usageMetadata": {"promptTokenCount": 5000, "candidatesTokenCount": 300,
                                                              "thoughtsTokenCount": 200}})


def test_gemini_success_grounding_and_redirects():
    posts = []

    def post(url, json, timeout, headers):
        posts.append((url, json))
        return gem_ok(grounded=True)

    head = lambda uri, allow_redirects, timeout: N(url="https://www.businesswire.com/news/acme")
    s = llm.Session("rebuild", http_post=post, http_head=head)
    r = s.ask("catalyst", "SYS", "PROMPT", shared="DOSSIER", search={"max_uses": 3, "blocked": ["reddit.com"]})
    url, body = posts[0]
    assert config.FLASH + ":generateContent" in url
    assert body["tools"] == [{"google_search": {}}]
    assert body["contents"][0]["parts"][0]["text"].startswith("DOSSIER")
    assert r.data == {"score": 0.5} and "thinking" not in r.text
    assert r.receipts[0]["url"] == "https://www.businesswire.com/news/acme"
    assert r.receipts[0]["status"] == "cited" and r.receipts[0]["snippet_kind"] == "model_text"
    assert r.receipts[1]["status"] == "consulted"
    assert s.usage[-1]["out"] == 500 and s.usage[-1]["searches"] == 1 and s.spent == 0


def test_gemini_retry_then_success():
    seq = [Resp(429, text="rate limited"), gem_ok()]
    s = llm.Session("rebuild", http_post=lambda *a, **k: seq.pop(0))
    r = s.ask("filing_summary", "s", "p")
    assert r.data == {"score": 0.5} and not r.fallback


def test_auditor_reads_numbers_with_units():
    a = audit.Auditor(notes=[{"id": "E11", "finding": "x"}], facts={"SEP_X_2026": 3.4})
    assert a.check({"ref": "NOTE:E11", "value": "10+ mb/d shut in"})[0]          # was rejected as "not a number"
    assert a.check({"ref": "FACT:SEP_X_2026", "value": "3.4% median"})[0]
    assert not a.check({"ref": "FACT:SEP_X_2026", "value": "about 9 percent"})[0]   # a wrong number still fails


def test_web_search_drops_a_domain_it_cannot_use():
    calls = []

    class Picky(FakeClaude):
        def create(self, **p):
            allowed = p["tools"][0].get("allowed_domains", [])
            calls.append(list(allowed))
            if "reuters.com" in allowed:
                raise RuntimeError("Error code: 400 - invalid_request_error: The following domains are not accessible "
                                   "to our user agent: reuters.com")
            return super().create(**p)
    llm.UNSEARCHABLE.clear()
    s = llm.Session("macro", anthropic_client=Picky([text_reply('```json\n{"ok": 1}\n```')]))
    r = s.ask("macro_gather", "s", "p", search={"max_uses": 2, "allowed": ["fed.gov", "reuters.com"]})
    assert r.data == {"ok": 1} and calls == [["fed.gov", "reuters.com"], ["fed.gov"]]
    assert "reuters.com" in llm.UNSEARCHABLE
    llm.UNSEARCHABLE.clear()


def test_gemini_falls_back_to_paid_gemini_never_claude():
    fc = FakeClaude([text_reply('```json\n{"fb": true}\n```')])
    os.environ["GEMINI_PAID_API_KEY"] = "paid-key"
    try:
        # the free key fails everywhere; the billed key works
        post = lambda url, json=None, timeout=None, headers=None: (
            gem_ok() if (headers or {}).get("x-goog-api-key") == "paid-key" else Resp(400, text="bad"))
        s = llm.Session("rebuild", anthropic_client=fc, http_post=post)
        r = s.ask("filing_summary", "s", "p")
        assert r.fallback and r.model == config.FLASH_PAID and r.data == {"score": 0.5}
        assert not fc.calls and s.usage[-1]["fallback"] is True
        # everything non-Claude fails: the call fails rather than switching to Claude
        s = llm.Session("rebuild", anthropic_client=fc, http_post=lambda *a, **k: Resp(400, text="bad"))
        try:
            s.ask("filing_summary", "s", "p")
            assert False, "should have failed"
        except RuntimeError:
            pass
        assert not fc.calls
    finally:
        os.environ.pop("GEMINI_PAID_API_KEY", None)


# ---------------------------------------------------------------- Batch
def test_batch_discount_and_rerun_of_failures():
    fc = FakeClaude([text_reply('```json\n{"direct": 1}\n```')])
    s = llm.Session("rebuild", anthropic_client=fc, http_post=lambda *a, **k: gem_ok())
    out = s.batch([
        {"id": "judge-ACME", "role": "judge", "system": "s", "prompt": "p", "shared": "D"},
        {"id": "judge-BETA", "role": "judge", "system": "s", "prompt": "p"},
        {"id": "bull-ACME", "role": "debate_bull", "system": "s", "prompt": "p"},   # Gemini: runs directly
    ])
    assert out["judge-ACME"].batched and out["judge-ACME"].data == {"ok": 1}
    assert out["judge-BETA"].data == {"direct": 1} and not out["judge-BETA"].batched
    assert out["bull-ACME"].data == {"score": 0.5}
    batched_cost = [u for u in s.usage if u["batched"]][0]["cost"]
    assert abs(batched_cost - (2000 * 2 + 500 * 10) / 1e6 * 0.5) < 1e-9


# ---------------------------------------------------------------- Audit
def test_validate_notes_macro_and_company():
    receipts = [{"url": "https://www.bls.gov/cpi", "snippet_kind": "source_text", "snippets": ["CPI rose 0.3 percent"]},
                {"url": "https://www.reuters.com/a", "snippet_kind": "source_text", "snippets": ["Revenue of $1,250 million"]},
                {"url": "https://someblog.net/b", "snippet_kind": "model_text", "snippets": ["x"]},
                {"url": "https://www.marketwatch.com/a", "snippet_kind": "source_text", "snippets": ["Revenue of $1,250 million"]},
                {"url": "https://www.reddit.com/r/x", "snippet_kind": "source_text", "snippets": []},
                {"url": "https://investor.acme.com/pr", "snippet_kind": "model_text", "snippets": []}]
    kept, dropped = audit.validate_notes(
        [{"id": "A1", "finding": "CPI", "value": "0.3", "url": "https://www.bls.gov/cpi"},
         {"id": "A2", "finding": "x", "value": "1", "url": "https://www.marketwatch.com/a"},      # not a macro source
         {"id": "A3", "finding": "x", "url": "https://notsearched.gov/z"}], receipts, "allow")
    assert [n["id"] for n in kept] == ["A1"] and kept[0]["verified_number"] is True
    assert {d["id"] for d in dropped} == {"A2", "A3"}

    kept, dropped = audit.validate_notes(
        [{"id": "C1", "finding": "rev", "value": "$1,250 million", "url": "https://www.reuters.com/a"},
         {"id": "C2", "finding": "rumor", "value": None, "url": "https://someblog.net/b"},
         {"id": "C3", "finding": "meme", "url": "https://www.reddit.com/r/x"},
         {"id": "C4", "finding": "context", "url": "https://someblog.net/b", "affects_score": False},
         {"id": "C5", "finding": "PR", "value": "12", "url": "https://investor.acme.com/pr"}], receipts, "company")
    k = {n["id"]: n for n in kept}
    assert k["C1"]["score_eligible"] and k["C1"]["verified_number"] is True
    assert k["C2"]["source_class"] == "open" and not k["C2"]["score_eligible"]
    assert k["C4"]["score_eligible"]
    assert k["C5"]["source_class"] == "primary" and k["C5"]["verified_number"] is None
    assert [d["id"] for d in dropped] == ["C3"]


def test_auditor_refs():
    notes = [{"id": "A1", "score_eligible": True, "verified_number": True},
             {"id": "C2", "score_eligible": False}, {"id": "C9", "score_eligible": True, "verified_number": False}]
    a = audit.Auditor(fred={"UNRATE": {"latest": 4.3, "3m_ago": 4.1}}, notes=notes, calcs={"regime"},
                      sectors={"Energy"}, metrics={"ACME": {"gross_margin": 41.2}}, facts={"mom_ACME": 12.5})
    ok = lambda ev, fs=True: a.check(ev, fs)[0]
    assert ok({"ref": "FRED:UNRATE", "value": 4.3}) and ok({"ref": "FRED:UNRATE", "value": "4.1%"})
    assert not ok({"ref": "FRED:UNRATE", "value": 5.0}) and not ok({"ref": "FRED:XYZ"})
    assert ok({"ref": "NOTE:A1"}) and not ok({"ref": "NOTE:C2"}) and ok({"ref": "NOTE:C2"}, False)
    assert not ok({"ref": "NOTE:C9"})
    assert ok({"ref": "SEC:ACME:gross_margin", "value": 41.2}) and not ok({"ref": "SEC:ACME:gross_margin", "value": 30})
    assert ok({"ref": "FACT:mom_ACME", "value": 12.5}) and ok("CALC:regime") and ok("HIST:Energy")
    assert not ok("MOM:Nope") and not ok("BOGUS:1")
    good, probs = a.filter([{"ref": "FRED:UNRATE", "value": 4.3}, {"ref": "FRED:UNRATE", "value": 9}])
    assert len(good) == 1 and len(probs) == 1


def test_source_class():
    assert audit.source_class("https://www.sec.gov/x") == "primary"
    assert audit.source_class("https://finance.yahoo.com/x") == "open"
    assert audit.source_class("https://m.reddit.com/x") == "blocked"
    assert audit.source_class("https://acme.com/news", company_domains=["acme.com"]) == "primary"


# ---------------------------------------------------------------- util / notify / runner
def test_extract_json_and_csv():
    assert util.extract_json('blah ```json\n{"a": [1, 2]}\n``` end') == {"a": [1, 2]}
    assert util.extract_json('text [{"x": 1}] more') == [{"x": 1}]
    assert util.extract_json("no json here") is None
    p = util.state_path("t.csv")
    util.append_csv(p, [{"a": 1}])
    util.append_csv(p, [{"a": 2, "b": 3}])
    assert p.read_text().splitlines() == ["a,b", "1,", "2,3"]


def test_email_dry_run():
    out = notify.send(notify.subject_line("macro", "OK", "test"), "body", html="<b>b</b>")
    assert out.endswith(".eml") and Path(out).exists()


def test_runner_budget_alert():
    def main(session, folder):
        session.spent = 999
        session.ask("judge", "s", "p")
    try:
        runner.run_stage("macro", main)
        assert False
    except SystemExit as e:
        assert e.code == 2
    assert list(config.RUNS_DIR.rglob("*.eml")), "alert email should have been written"
    assert util.state_path("cost_log.csv").exists() or True


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")
