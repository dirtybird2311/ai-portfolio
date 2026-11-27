"""Interrupted-run tests: checkpoints, resumable batches, plain-English alerts, and automatic resume."""
import json
import os
import sys
import types
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_team as tt  # noqa: E402  (sets PIPELINE_ROOT and API env vars; provides team fakes)
import test_rebuild as tr  # noqa: E402

from pipeline import checkpoint as cpt  # noqa: E402
from pipeline import llm, rebuild, resume, runner, team, util  # noqa: E402
from pipeline import config  # noqa: E402
from pipeline import pm  # noqa: E402

pm.MIN_STOCKS, pm.MAX_STOCKS = 8, 12      # these fixtures are a 10-name book; the live 15-20 limits are checked in test_themes
config.PAPER_MODE = False       # live checklist flow

N = types.SimpleNamespace
CREDIT_ERR = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
              "'message': 'Your credit balance is too low to access the Anthropic API.'}}")


def reset(stage):
    p = util.state_path(f"checkpoints/{stage}.json")
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------- checkpoint basics
def test_checkpoint_lifecycle():
    reset("x")
    a = cpt.Checkpoint("x", fingerprint="f1")
    a.save("step1", {"v": 1})
    a.save_item("per", "AAA", 5)
    b = cpt.Checkpoint("x", fingerprint="f1")
    assert b.resumed and b.get("step1") == {"v": 1} and b.item("per", "AAA") == 5 and b.attempts == 2
    assert cpt.incomplete("x") and any("per: 1 done" in p for p in cpt.progress("x"))
    c = cpt.Checkpoint("x", fingerprint="f2")                      # inputs changed -> fresh
    assert not c.resumed and not c.has("step1")
    c.complete()
    assert not cpt.Checkpoint("x", fingerprint="f2").resumed        # completed -> next run is fresh
    d = cpt.Checkpoint("x")
    d.data["started"] = (cpt.now_et().date() - timedelta(days=cpt.RESUME_WINDOW_DAYS + 1)).isoformat()
    d._write()
    assert cpt.incomplete("x") is None                               # stale: not offered for resume
    assert not cpt.Checkpoint("x").resumed                           # and a new run starts fresh


# ---------------------------------------------------------------- batch resume
class Killed(BaseException):
    """The runner being shut down mid-wait (a plain error while polling is just retried)."""


class BatchClient:
    def __init__(self, fail_retrieve_times=0):
        self.messages, self.batches = self, self
        self.creates, self.fail = 0, fail_retrieve_times
        self.sub = None

    def create(self, requests=None, **p):
        self.creates += 1
        self.sub = requests
        return N(id=f"b{self.creates}")

    def retrieve(self, bid):
        if self.fail:
            self.fail -= 1
            raise Killed("runner shut down while waiting on the batch")
        return N(processing_status="ended")

    def results(self, bid):
        return [N(custom_id=r["custom_id"], result=N(type="succeeded", message=N(
            content=[N(type="text", text='```json\n{"ok": "%s"}\n```' % r["custom_id"], citations=None)],
            usage=N(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                    server_tool_use=None)))) for r in self.sub]

    def cancel(self, bid):
        pass


def test_batch_submitted_once_across_a_crash():
    reset("b")
    client = BatchClient(fail_retrieve_times=1)
    reqs = [{"id": f"j{i}", "role": "judge", "system": "s", "prompt": "p"} for i in range(3)]
    ck = cpt.Checkpoint("b")
    try:
        llm.Session("rebuild", anthropic_client=client).batch(reqs, checkpoint=ck, key="judge")
        assert False
    except Killed:
        pass
    assert ck.get("batch_id:judge")["id"] == "b1"
    ck2 = cpt.Checkpoint("b")
    s2 = llm.Session("rebuild", anthropic_client=client)
    out = s2.batch(reqs, checkpoint=ck2, key="judge")
    assert client.creates == 1                                        # not paid for twice
    assert {k: v.data["ok"] for k, v in out.items()} == {"j0": "j0", "j1": "j1", "j2": "j2"}
    out3 = llm.Session("rebuild", anthropic_client=client).batch(reqs, checkpoint=cpt.Checkpoint("b"), key="judge")
    assert client.creates == 1 and len(out3) == 3                     # saved results reused


# ---------------------------------------------------------------- friendly alerts
def test_runner_explains_and_quiets():
    def boom(session, folder):
        raise RuntimeError(CREDIT_ERR)

    folder = util.run_dir("macro")
    for e in folder.glob("*.eml"):
        e.unlink()
    assert runner.run_stage("macro", boom, quiet=True, exit_on_fail=False) is None
    assert not list(folder.glob("*.eml"))                             # quiet retry: no email
    runner.run_stage("macro", boom, exit_on_fail=False)
    mail = list(folder.glob("*.eml"))[0].read_text()
    assert "Claude_API_credits_ran_out" in mail.replace(" ", "_") or "Claude API credits ran out" in mail
    assert "platform.claude.com" in mail and "Nothing was traded" in mail and "PROGRESS SAVED" in mail
    assert runner.explain("x", "invalid x-api-key")[0] == "Claude API key was rejected"
    assert runner.explain("x", "Overloaded")[0] == "Temporary service problem"


# ---------------------------------------------------------------- team: out of credits mid-debate, then resume
def test_team_resumes_mid_debate():
    reset("team")
    tt.setup_state()
    util.write_json(util.state_path("research_cache.json"), {})
    calls = {"filing_diff": 0, "news": 0, "summary": 0, "review": 0, "catalyst": 0, "debate": 0, "judge": 0, "council": 0, "signals": 0}

    def counting(fail_after=None):
        """Counts calls across all three provider formats (Gemini/Gemma, Groq, Mistral)."""
        def post(url, json=None, timeout=None, headers=None):
            sysmsg = (tt.sys_and_user(json)[0] if "generativelanguage" in url else json["messages"][0]["content"])
            kind = ("filing_diff" if sysmsg.startswith("You compare a company's") else
                    "news" if "numbered headline" in sysmsg else "summary" if "careful equity analyst" in sysmsg
                    else "review" if "senior analyst" in sysmsg else "catalyst" if "event-driven" in sysmsg
                    else "judge" if sysmsg.startswith("You are a judge")
                    else "council" if sysmsg.startswith("You are an investor council")
                    else "signals" if sysmsg.startswith("You score three narrow things") else "debate")
            calls[kind] += 1
            if kind == "debate" and fail_after is not None and calls["debate"] > fail_after:
                return N(status_code=400, text="bad", json=lambda: {})
            return tt.gemini_post(url, json=json, timeout=timeout, headers=headers)
        return post

    class NoCredits(tt.FakeClaude):
        def create(self, **p):
            if "requests" in p:
                return super().create(**p)
            raise RuntimeError(CREDIT_ERR)                             # Gemini fallback to Claude hits the wall

    nc = NoCredits()
    nc.batches = N(create=lambda requests: nc.create(requests=requests), retrieve=nc.retrieve, results=nc.results, cancel=nc.cancel)
    folder = util.run_dir("team")
    s1 = llm.Session("team", anthropic_client=nc, http_post=counting(fail_after=10), http_head=lambda *a, **k: N(url=a[0]))
    try:
        team.main(s1, folder, sec=tt.FakeSEC(), get=tt.fake_get, market=tt.MARKET, per_ticker=tt.PER_TICKER)
        assert False, "should have stopped"
    except RuntimeError as e:
        assert "bad" in str(e) or "failed" in str(e)                  # every non-Claude fallback failed; no Claude
    first = dict(calls)
    saved_debates = len(cpt.incomplete("team")["steps"]["debate"])
    assert saved_debates == 2                                          # 10 debate calls = 2 full stocks + part of a 3rd
    assert first["debate"] > 10                                        # the failing call tried every free provider
    for k in calls:
        calls[k] = 0
    s2 = llm.Session("team", anthropic_client=tt.FC, http_post=counting(), http_head=lambda *a, **k: N(url=a[0]))
    team.main(s2, folder, sec=tt.FakeSEC(), get=tt.fake_get, market=tt.MARKET, per_ticker=tt.PER_TICKER)
    assert calls["news"] == 0 and calls["summary"] == 0 and calls["catalyst"] == 0 and calls["review"] == 0
    stocks = len(util.read_json(util.state_path("team_results.json"))["stocks"])
    assert calls["debate"] == 4 * (stocks - saved_debates)             # only unfinished debates rerun
    assert cpt.incomplete("team") is None                              # completed
    print(f"    first attempt {first}; resume redid only {calls['debate']} debate calls")


# ---------------------------------------------------------------- rebuild: stops at the critic, resumes in an off week
def test_rebuild_resumes_without_force():
    reset("rebuild")
    tr.fresh_book()
    for f in ("rebuild_history.json", "pending_plan.json", "checklist.md", "verdict_history.csv"):
        p = util.state_path(f)
        if p.exists():
            p.unlink()
    ranges = {s: [0, 15] for s in tr.SECT}
    ranges["Energy"] = [12, 30]
    util.write_json(util.state_path("macro_view.json"), {"date": "2026-09-18", "regime": "R", "tilts": {s: 0 for s in tr.SECT},
                                                         "weight_ranges_%": ranges, "key_risks": []})
    import pandas as pd
    pd.DataFrame({"ticker": list(tr.PRICES), "vol_60d": 0.25, "sector": "Energy"}).to_csv(util.state_path("bench.csv"), index=False)
    rebuild.market_prices = lambda tickers: (tr.PRICES, tr.CORR)
    rebuild.team.main = tr.fake_team_main(tr.team_results())
    good = {"portfolio": [{"ticker": f"K{i:02d}", "why": "w"} for i in [0] + list(range(2, 12))], "exits": [], "summary": "good"}

    class CriticDown(tr.FakeClaude):
        def create(self, **p):
            if p["system"][0]["text"].startswith("You are the risk reviewer"):
                raise RuntimeError(CREDIT_ERR)
            return super().create(**p)

    fc1 = CriticDown()
    fc1.pm_script, fc1.pm_script_default = [], good
    try:
        rebuild.main(llm.Session("rebuild", anthropic_client=fc1), util.run_dir("rebuild"), force=True)
        assert False
    except RuntimeError:
        pass
    assert fc1.pm_calls == 1 and cpt.incomplete("rebuild")["steps"].get("plan1")

    # credits added; resume in an ODD (non-rebuild) week without --force
    later = rebuild.TODAY + timedelta(days=1)                          # a day later, so the saved plan is stale
    while later.isocalendar()[1] % 2 == rebuild.REBUILD_WEEK_PARITY:   # ...and in an off week
        later += timedelta(days=1)
    rebuild.TODAY = later
    class CriticPasses(tr.FakeClaude):              # no flags this time, so no revision round
        def create(self, **p):
            if p["system"][0]["text"].startswith("You are the risk reviewer"):
                return N(content=[N(type="text", text='```json\n{"overall": "PASS", "summary": "ok", "trades": {}}\n```',
                                    citations=None)], stop_reason="end_turn",
                         usage=N(input_tokens=10, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                                 server_tool_use=None))
            return super().create(**p)

    fc2 = CriticPasses()
    fc2.pm_script, fc2.pm_script_default = [], good
    out = rebuild.main(llm.Session("rebuild", anthropic_client=fc2), util.run_dir("rebuild"), force=False)
    assert out["status"] in ("PASS", "FLAG") and fc2.pm_calls == 0     # PM work reused, not redone
    plan = util.read_json(util.state_path("pending_plan.json"))
    full = util.read_json(util.run_dir("rebuild") / "plan.json")
    assert any("prices refreshed" in n for n in full["notes"])         # stale plan repriced before delivery
    assert all(t.get("limit") for t in plan["trades"])
    assert len(util.read_json(util.state_path("rebuild_history.json"))) == 1
    # a stray re-run can't double-deliver: the checkpoint is complete, so an off-week run just skips
    out2 = rebuild.main(llm.Session("rebuild", anthropic_client=fc2), util.run_dir("rebuild"), force=False)
    assert out2["status"] == "skipped" and len(util.read_json(util.state_path("rebuild_history.json"))) == 1


# ---------------------------------------------------------------- automatic resume job
def test_resume_job():
    reset("macro")
    reset("rebuild")
    assert resume.main() == []
    ck = cpt.Checkpoint("macro")
    ck.save("packet", {"x": 1})
    ran = []
    import pipeline.macro as macro_mod
    import pipeline.screen as screen_mod
    orig_m, orig_s = macro_mod.main, screen_mod.main

    def fake_macro(session, folder):
        ran.append("macro")
        cpt.Checkpoint("macro").complete()
        return {"status": "OK"}

    macro_mod.main = fake_macro
    screen_mod.main = lambda session, folder: ran.append("screen") or {}
    try:
        assert resume.main() == [("macro", "resumed")] and ran == ["macro", "screen"]
        # a run that keeps failing: quiet retries, then one final email and it stops trying
        ck = cpt.Checkpoint("macro", fresh=True)

        def failing(session, folder):
            cpt.Checkpoint("macro")          # each attempt increments the counter, like a real run
            raise RuntimeError(CREDIT_ERR)

        macro_mod.main = failing
        folder = util.run_dir("macro")
        for e in folder.glob("*.eml"):
            e.unlink()
        for _ in range(resume.MAX_ATTEMPTS + 2):
            resume.main()
        texts = [p.read_text(errors="ignore") for p in util.config.RUNS_DIR.rglob("*.eml")]
        assert sum("Automatic retries have stopped" in t for t in texts) == 1     # exactly one give-up email
        assert cpt.incomplete("macro")["attempts"] >= resume.MAX_ATTEMPTS
    finally:
        macro_mod.main, screen_mod.main = orig_m, orig_s


def test_cancelled_job_still_logs_its_costs():
    import signal
    import time
    import pandas as pd
    before = len(pd.read_csv(util.state_path("cost_log.csv"))) if util.state_path("cost_log.csv").exists() else 0

    def main(session, folder):
        session.usage.append({"role": "x", "model": "m", "in": 1, "out": 1, "cache_write": 0, "cache_read": 0,
                              "searches": 0, "batched": False, "fallback": False, "cost": 0.25})
        session.spent += 0.25
        os.kill(os.getpid(), signal.SIGTERM)      # what GitHub sends when a job is cancelled or times out
        time.sleep(5)
    assert runner.run_stage("replay", main, quiet=True, exit_on_fail=False) is None
    assert len(pd.read_csv(util.state_path("cost_log.csv"))) == before + 1
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.default_int_handler)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
