"""
Offline test for the connection test (pipeline/connections.py): every service is faked.
Run:  python -m pytest tests/  (or)  python tests/test_connections.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()
for k in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "GEMINI_PAID_API_KEY", "GMAIL_APP_PASSWORD", "GMAIL_ADDRESS"):
    os.environ.pop(k, None)
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FINNHUB_API_KEY", "FRED_API_KEY", "XAI_API_KEY", "MISTRAL_API_KEY"):
    os.environ[k] = "test"

import pandas as pd  # noqa: E402

from pipeline import config, connections, embed, fetch, inputs, llm, util  # noqa: E402

N = types.SimpleNamespace
llm.time.sleep = lambda s: None


class Resp:
    def __init__(self, code=200, data=None, text=""):
        self.status_code, self._d, self.text = code, data, text or json.dumps(data)

    def json(self):
        return self._d


class FakeClaude:
    def __init__(self):
        self.messages = self
        self.batches = N(list=lambda limit=1: iter([]))

    def create(self, **p):
        if p["model"] == config.OPUS:
            raise RuntimeError("Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', 'message': 'model: x'}}")
        return N(content=[N(type="text", text="OK", citations=None)], stop_reason="end_turn",
                 usage=N(input_tokens=20, output_tokens=2, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                         server_tool_use=None))


def post(url, json=None, timeout=None, headers=None):
    if "generativelanguage" in url:
        if config.FLASH in url:
            return Resp(404, {"error": {"message": f"models/{config.FLASH} is not found"}})
        return Resp(200, {"candidates": [{"content": {"parts": [{"text": "OK"}]}}],
                          "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 2}})
    if "api.x.ai" in url:
        return Resp(401, {"error": {"message": "Invalid API Key"}})
    return Resp(200, {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 20, "completion_tokens": 2}})


def get(url, params=None, timeout=None, headers=None):
    if "finnhub" in url:
        return Resp(200, [{"headline": "x"}])
    if "stlouisfed" in url:
        return Resp(200, {"observations": [{"date": "2026-09-24", "value": "4.1"}]})
    if "company_tickers" in url:
        return Resp(200, {"0": {"ticker": "AAPL", "cik_str": 320193}})
    if "companyfacts" in url:
        return Resp(200, {"facts": {"us-gaap": {}}})
    return Resp(404, {})


def test_connection_report():
    sys.modules["yfinance"] = N(download=lambda *a, **k: pd.DataFrame({"Close": [1.0, 2.0]}))
    inputs.estimates = lambda t: None                              # optional -> WARN, not FAIL
    embed.embed = lambda texts, post=None: [[0.1]]
    fetch.fetch_source = lambda src, get=None, max_chars=0: (
        {"id": src["id"], "error": "page unavailable"} if src["id"] == "boj" else {"id": src["id"], "text": "x"})
    import pipeline.sec as sec
    sec.MIN_INTERVAL = 0
    s = llm.Session("connections", budget=0.25, anthropic_client=FakeClaude(), http_post=post)
    code = connections.main(get=get, session=s)
    assert code == 1                                               # something required failed
    folder = config.RUNS_DIR / util.today_iso()
    assert next(folder.glob("email_*Connection_test*.eml"))       # report emailed (saved here: no Gmail in tests)
    rows = {r["name"]: (r["status"], r["detail"]) for r in connections.last_rows}
    assert rows[config.SONNET][0] == "PASS" and rows[config.HAIKU][0] == "PASS"
    assert rows[config.OPUS][0] == "FAIL" and "model name not found" in rows[config.OPUS][1]
    assert rows[config.FLASH][0] == "FAIL" and "update config.py" in rows[config.FLASH][1]
    assert rows[config.GROK][0] == "FAIL" and "key rejected" in rows[config.GROK][1]
    assert rows[config.GPT_SOL][0] == "SKIP" and rows[config.GEMINI_PRO][0] == "SKIP"   # optional keys not set
    assert rows["Claude batches"][0] == "PASS"
    assert all(rows[k][0] == "PASS" for k in ("Finnhub news", "FRED economic data", "SEC filings", "Yahoo prices"))
    assert rows["Yahoo analyst estimates"][0] == "WARN" and rows["D: boj"][0] == "WARN" and rows["D: ecb"][0] == "PASS"
    assert rows["Gmail login"][0] == "WARN" and s.spent < 0.01


if __name__ == "__main__":
    test_connection_report()
    print("PASS test_connection_report")
