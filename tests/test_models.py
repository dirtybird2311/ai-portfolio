"""
Offline tests for the multi-provider model layer: OpenAI (Responses + Batch), NVIDIA, paid Gemini
batches, thinking levels, Claude adaptive thinking, explicit-model calls. No keys or network.
Run:  python -m pytest tests/  (or)  python tests/test_models.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k, v in {"GEMINI_API_KEY": "free", "GEMINI_PAID_API_KEY": "paid", "OPENAI_API_KEY": "oa",
             "NVIDIA_API_KEY": "nv", "MISTRAL_API_KEY": "mi", "GROQ_API_KEY": "gq", "XAI_API_KEY": "xa"}.items():
    os.environ[k] = v

from pipeline import checkpoint as cpt, config, llm  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = lambda s: None


class Resp:
    def __init__(self, code=200, data=None, text=""):
        self.status_code, self._d, self.text = code, data, text or (json.dumps(data) if data is not None else "")

    def json(self):
        return self._d


def oa_reply(text, i=1000, o=300, cached=0):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": i, "output_tokens": o, "input_tokens_details": {"cached_tokens": cached}}}


def gem_reply(text, i=1000, o=200, thoughts=0):
    return {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": text}]}}],
            "usageMetadata": {"promptTokenCount": i, "candidatesTokenCount": o, "thoughtsTokenCount": thoughts}}


# ---------------------------------------------------------------- helpers
def test_levels_chain_and_groups():
    assert llm.level(0) == "minimal" and llm.level(1024) == "low" and llm.level(4096) == "medium"
    assert llm.level(10000) == "high" and llm.level("high") == "high" and llm.level(None) is None
    assert llm.chain("news", model=config.GPT_SOL) == [config.GPT_SOL]          # explicit: no fallback
    assert llm.chain("judge") == [config.SONNET]
    assert llm.chain("news") == [config.HAIKU, config.GEMMA]                  # Haiku labels; Gemma if it fails
    assert llm.chain("filing_summary")[0] == config.FLASH and config.PAID_FALLBACK in llm.chain("filing_summary")
    assert all(llm.supports_search(m) for m in llm.chain("catalyst", search=True))
    assert llm.batch_group(config.OPUS) == ("claude", None)
    assert llm.batch_group(config.GPT_SOL) == ("openai", config.GPT_SOL)
    assert llm.batch_group(config.GEMINI_PRO) == ("google", config.GEMINI_PRO)
    assert llm.batch_group(config.FLASH) is None                # free tier runs directly
    assert llm.batch_group(config.NV_DEEPSEEK) is None
    assert llm.batch_group(config.GEMINI_PRO, search=True) is None
    for j in config.JUDGE_PANEL:                                # every judge has a price entry
        assert j["model"] in config.PRICES, j


# ---------------------------------------------------------------- Claude adaptive thinking
def test_claude_adaptive_thinking_params():
    p = llm.Session._claude_params(config.OPUS, "S", "P", None, None, 2000, "medium")
    assert p["thinking"] == {"type": "adaptive"} and p["output_config"] == {"effort": "medium"}
    assert p["max_tokens"] == 2000 + config.THINKING_HEADROOM["medium"]
    p = llm.Session._claude_params(config.SONNET, "S", "P", None, None, 2000, "minimal")
    assert p["output_config"] == {"effort": "low"}
    p = llm.Session._claude_params(config.SONNET, "S", "P", None, None, 2000, 1024)   # legacy int: no thinking
    assert "thinking" not in p and p["max_tokens"] == 2000
    assert "budget_tokens" not in json.dumps(llm.Session._claude_params(config.OPUS, "S", "P", None, None, 10, "high"))


# ---------------------------------------------------------------- Gemini 3 thinking + paid key
def test_gemini3_thinking_level_and_paid_key():
    seen = []

    def post(url, json=None, timeout=None, headers=None):
        seen.append((url, json, headers))
        return Resp(200, gem_reply('{"a": 1}', thoughts=500))

    s = llm.Session("team", http_post=post)
    r = s.ask("judge", "S", "P", model=config.GEMINI_PRO, thinking="medium")
    url, body, headers = seen[-1]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "medium"}
    assert headers["x-goog-api-key"] == "paid" and r.data == {"a": 1}
    # output cost includes thinking tokens: 1000*2 + (200+500)*12
    assert abs(s.spent - (1000 * 2 + 700 * 12) / 1e6) < 1e-9
    s.ask("filing_summary", "S", "P", thinking=1024)
    url, body, headers = seen[-1]
    assert config.FLASH in url and headers["x-goog-api-key"] == "free"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


# ---------------------------------------------------------------- OpenAI direct
def test_openai_responses_call():
    seen = []

    def post(url, json=None, timeout=None, headers=None, **kw):
        seen.append((url, json, headers))
        return Resp(200, oa_reply('```json\n{"conviction": 4}\n```', i=3000, o=900, cached=1000))

    s = llm.Session("team", http_post=post)
    r = s.ask("judge", "SYS", "PROMPT", shared="DOSSIER", model=config.GPT_SOL, thinking="high")
    url, body, headers = seen[0]
    assert url.endswith("/responses") and headers["Authorization"] == "Bearer oa"
    assert body["model"] == "gpt-6-sol" and body["reasoning"] == {"effort": "high"}
    assert body["instructions"] == "SYS" and body["input"].startswith("DOSSIER")
    assert r.data == {"conviction": 4} and r.model == config.GPT_SOL
    # 2000 fresh input * $2 + 1000 cached * $2 * 0.1 + 900 out * $10
    assert abs(s.spent - (2000 * 2 + 1000 * 2 * 0.1 + 900 * 10) / 1e6) < 1e-9


def test_openai_failure_does_not_fall_back_when_model_is_explicit():
    s = llm.Session("team", http_post=lambda *a, **k: Resp(400, text="bad model"))
    try:
        s.ask("judge", "S", "P", model=config.GPT_SOL)
        assert False
    except RuntimeError as e:
        assert "400" in str(e)
    assert s.usage == []


# ---------------------------------------------------------------- NVIDIA
def test_nvidia_chat_completions():
    seen = []

    def post(url, json=None, timeout=None, headers=None):
        seen.append((url, json, headers))
        return Resp(200, {"choices": [{"message": {"content": '{"x": 2}'}}],
                          "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    s = llm.Session("team", http_post=post)
    r = s.ask("judge", "S", "P", model=config.NV_DEEPSEEK)
    url, body, headers = seen[0]
    assert url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert body["model"] == config.NV_DEEPSEEK.split(":", 1)[1] and headers["Authorization"] == "Bearer nv"
    assert r.data == {"x": 2} and s.spent == 0


# ---------------------------------------------------------------- multi-provider batch
class FakeBatches:
    def __init__(self):
        self.submitted, self.creates = None, 0

    def create(self, requests):
        self.submitted, self.creates = requests, self.creates + 1
        return N(id="cb1")

    def retrieve(self, bid):
        return N(processing_status="ended")

    def results(self, bid):
        out = []
        for r in self.submitted:
            msg = N(content=[N(type="text", text='{"who": "%s"}' % r["params"]["model"], citations=None)],
                    usage=N(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0,
                            cache_read_input_tokens=0, server_tool_use=None))
            out.append(N(custom_id=r["custom_id"], result=N(type="succeeded", message=msg)))
        return out

    def cancel(self, bid):
        pass


class FakeClaude:
    def __init__(self):
        self.messages = self
        self.batches = FakeBatches()

    def create(self, **p):
        raise AssertionError("should have been batched")


class FakeHTTP:
    """OpenAI files/batches + Gemini batchGenerateContent + NVIDIA chat, all in one."""

    def __init__(self, gemini_polls=1):
        self.uploads, self.oa_batches, self.gem_batches, self.direct = [], 0, [], []
        self.gemini_polls = gemini_polls

    def post(self, url, json=None, timeout=None, headers=None, data=None, files=None):
        if url.endswith("/files"):
            self.uploads.append(files["file"][1].decode())
            return Resp(200, {"id": "file-in"})
        if url.endswith("/batches"):
            self.oa_batches += 1
            assert json["endpoint"] == "/v1/responses" and json["input_file_id"] == "file-in"
            return Resp(200, {"id": "oab1", "status": "validating"})
        if ":batchGenerateContent" in url:
            assert headers["x-goog-api-key"] == "paid"
            self.gem_batches.append(json)
            return Resp(200, {"name": "batches/g1"})
        if url.endswith("/responses"):
            self.direct.append(json["model"])
            return Resp(200, oa_reply('{"who": "sol-direct"}'))
        if url.endswith("/chat/completions"):
            self.direct.append(json["model"])
            return Resp(200, {"choices": [{"message": {"content": '{"who": "nv"}'}}],
                              "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
        raise AssertionError(url)

    def get(self, url, headers=None, timeout=None):
        if url.endswith("/batches/oab1"):
            return Resp(200, {"id": "oab1", "status": "completed", "output_file_id": "file-out"})
        if url.endswith("/files/file-out/content"):
            lines = []
            for line in self.uploads[-1].splitlines():
                req = json.loads(line)
                if req["custom_id"].endswith("BAD"):
                    lines.append(json.dumps({"custom_id": req["custom_id"], "response": None,
                                             "error": {"code": "server_error"}}))
                    continue
                lines.append(json.dumps({"custom_id": req["custom_id"], "response": {"status_code": 200, "body":
                                         oa_reply('{"who": "sol"}', i=2000, o=800)}}))
            return Resp(200, text="\n".join(lines))
        if url.endswith("/batches/g1"):
            self.gemini_polls -= 1
            if self.gemini_polls > 0:
                return Resp(200, {"name": "batches/g1", "metadata": {"state": "JOB_STATE_RUNNING"}})
            reqs = self.gem_batches[-1]["batch"]["input_config"]["requests"]["requests"]
            return Resp(200, {"name": "batches/g1", "done": True, "metadata": {"state": "JOB_STATE_SUCCEEDED"},
                              "response": {"inlinedResponses": {"inlinedResponses": [
                                  {"metadata": {"key": r["metadata"]["key"]}, "response": gem_reply('{"who": "pro"}')}
                                  for r in reversed(reqs)]}}})
        raise AssertionError(url)


def panel_reqs(tickers):
    out = []
    for t in tickers:
        for jid, m in (("sonnet", config.SONNET), ("opus", config.OPUS), ("sol", config.GPT_SOL),
                       ("pro", config.GEMINI_PRO), ("nv", config.NV_DEEPSEEK)):
            out.append({"id": f"{jid}-{t}", "role": "judge", "model": m, "system": "S", "prompt": t,
                        "thinking": "medium" if jid != "nv" else None})
    return out


def test_multi_provider_batch_and_resume():
    http, fc = FakeHTTP(gemini_polls=2), FakeClaude()
    s = llm.Session("rebuild", anthropic_client=fc, http_post=http.post, http_get=http.get)
    ck = cpt.Checkpoint("rebuild", fresh=True)
    reqs = panel_reqs(["AAA", "BAD"])
    out = s.batch(reqs, poll_seconds=0, checkpoint=ck, key="judge")
    assert out["sonnet-AAA"].data == {"who": config.SONNET} and out["opus-AAA"].data == {"who": config.OPUS}
    assert fc.batches.submitted[1]["params"]["thinking"] == {"type": "adaptive"}
    assert out["sol-AAA"].data == {"who": "sol"} and out["sol-AAA"].batched
    assert out["pro-BAD"].data == {"who": "pro"} and out["pro-AAA"].batched
    assert out["nv-AAA"].data == {"who": "nv"} and not out["nv-AAA"].batched
    assert http.oa_batches == 1 and len(http.gem_batches) == 1 and fc.batches.creates == 1
    body = json.loads(http.uploads[0].splitlines()[0])["body"]
    assert body["model"] == "gpt-6-sol" and body["reasoning"]["effort"] == "medium"
    # the OpenAI item that failed inside the batch was rerun directly (a /responses POST)
    assert not out["sol-BAD"].batched and out["sol-BAD"].data == {"who": "sol-direct"}
    sol_cost = [u for u in s.usage if u["model"] == config.GPT_SOL and u["batched"]][0]["cost"]
    assert abs(sol_cost - (2000 * 2 + 800 * 10) / 1e6 * 0.5) < 1e-9
    assert len(out) == len(reqs)

    # a rerun of the same step pays nothing: everything comes back from the checkpoint
    http2 = FakeHTTP()
    s2 = llm.Session("rebuild", anthropic_client=FakeClaude(), http_post=http2.post, http_get=http2.get)
    out2 = s2.batch(reqs, poll_seconds=0, checkpoint=cpt.Checkpoint("rebuild"), key="judge")
    assert set(out2) == set(out) and s2.spent == 0 and http2.oa_batches == 0 and not http2.gem_batches


def test_batch_submitted_then_stopped_is_collected_not_resubmitted():
    http, fc = FakeHTTP(), FakeClaude()
    ck = cpt.Checkpoint("team", fresh=True)
    reqs = [r for r in panel_reqs(["AAA"]) if r["id"].startswith("sol")]
    ck.save(f"batch_id:judge:openai:{config.GPT_SOL}", {"id": "oab1", "ids": ["sol-AAA"]})
    http.uploads.append(json.dumps({"custom_id": "sol-AAA", "body": {}}))   # what the stopped run uploaded
    s = llm.Session("team", anthropic_client=fc, http_post=http.post, http_get=http.get)
    out = s.batch(reqs, poll_seconds=0, checkpoint=ck, key="judge")
    assert http.oa_batches == 0 and out["sol-AAA"].data == {"who": "sol"}
    assert not ck.has(f"batch_id:judge:openai:{config.GPT_SOL}")


# ---------------------------------------------------------------- circuit breaker
def test_failing_model_is_benched():
    calls = []

    def post(url, json=None, timeout=None, headers=None):
        calls.append(url)
        if "nvidia" in url:
            raise TimeoutError("Read timed out")                      # NVIDIA stalled
        return Resp(200, {"choices": [{"message": {"content": "```json\n{}\n```"}}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 2}})

    s = llm.Session("team", http_post=post)
    for _ in range(config.BENCH_AFTER_FAILURES):
        try:
            s.ask("debate_bull", "S", "P", model=config.NV_DEEPSEEK)
        except Exception:
            pass
    assert config.NV_DEEPSEEK in s.benched
    n = len(calls)
    try:
        s.ask("debate_bull", "S", "P", model=config.NV_DEEPSEEK)
        assert False, "benched model should not be called"
    except RuntimeError as e:
        assert "benched" in str(e) and len(calls) == n               # no waiting on it again
    s.benched[config.NV_DEEPSEEK] = 0                                 # cooldown over
    try:
        s.ask("debate_bull", "S", "P", model=config.NV_DEEPSEEK)
    except Exception:
        pass
    assert len(calls) > n and config.NV_DEEPSEEK in s.benched        # retried once, benched again


def test_free_gemini_falls_back_to_paid_gemini():
    old = os.environ.get("GEMINI_PAID_API_KEY")
    try:
        os.environ["GEMINI_PAID_API_KEY"] = "paid"
        c = llm.chain("fundamentals")
        assert c[:3] == [config.FLASH, "gemini-3.7-flash", config.FLASH_PAID]   # free Gemini, then paid Gemini
        assert not any(llm.is_claude(m) for m in c)                   # never Haiku
        assert not any(llm.is_claude(m) for m in llm.chain("catalyst", search=True))
        assert llm.api_name(config.FLASH_PAID) == config.FLASH and llm.key_name(config.FLASH_PAID) == "GEMINI_PAID_API_KEY"
        assert llm.is_paid(config.FLASH_PAID) and not llm.is_paid(config.FLASH)
        s = llm.Session("t", budget=1.0)
        assert s._gemini_headers(config.FLASH_PAID)["x-goog-api-key"] == "paid"
        os.environ.pop("GEMINI_PAID_API_KEY")
        assert config.FLASH_PAID not in llm.chain("fundamentals")      # no billed key: skipped
    finally:
        if old is not None:
            os.environ["GEMINI_PAID_API_KEY"] = old


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")
