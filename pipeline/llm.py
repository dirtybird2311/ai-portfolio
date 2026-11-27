"""
One doorway for every model call in the pipeline.

    s = Session("rebuild")
    r = s.ask("judge", system, prompt, shared=dossier)          # routed by config.MODELS
    r = s.ask("judge", system, prompt, model="openai:gpt-6-sol")  # or an explicit model
    rs = s.batch([...], checkpoint=ck, key="judge")              # batched at 50% off where possible
    s.save(run_folder)                                           # cost log + receipts

What it handles for every agent:
  - routing a role to its model, and down a FALLBACK CHAIN if that model fails:
    free providers first (Gemini, Gemma, Groq, Mistral), Claude Haiku as the last resort.
    Calls with an explicit `model` never fall back (judges must stay who they are).
  - providers: Claude (Anthropic SDK), Gemini/Gemma (REST), OpenAI (Responses API),
    Groq / Mistral / NVIDIA (OpenAI-compatible chat completions)
  - thinking effort, one vocabulary for every provider: "minimal" | "low" | "medium" | "high"
    (integers are legacy token budgets and are mapped to a level; Claude only thinks when a
    level string is passed explicitly)
  - prompt caching (a shared dossier is cached so repeat reads cost ~10%)
  - batch APIs for calls that can wait (50% off): Claude, OpenAI, and paid Gemini models,
    each resumable from a checkpoint so a batch is never paid for twice
  - web search: Claude with allowed/blocked domains; Gemini with Google grounding
  - free-tier pacing per model, retries on rate limits
  - receipts: every source a model cited or was shown, in one format
  - cost of every call, and a hard per-run budget cap
"""
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import requests

from . import config
from .util import append_csv, extract_json, state_path, today_iso

LEVELS = ("minimal", "low", "medium", "high")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_BASE = "https://api.openai.com/v1"
GEMINI_DONE = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED",
               "BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED", "BATCH_STATE_EXPIRED"}
OPENAI_DONE = {"completed", "failed", "expired", "cancelled"}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Result:
    role: str
    model: str
    text: str
    data: Any
    receipts: list = field(default_factory=list)
    cost: float = 0.0
    fallback: bool = False
    batched: bool = False


# ==================================================================== model helpers
def provider(model):
    if model.startswith("claude"):
        return "claude"
    if model.startswith(("gemini", "gemma")):
        return "google"
    if ":" in model:
        return model.split(":", 1)[0]          # "groq:<m>", "mistral:<m>", "nvidia:<m>", "openai:<m>"
    raise ValueError(f"unknown model {model}")


def is_claude(model):
    return provider(model) == "claude"


def is_gemini(model):                          # kept for older callers
    return provider(model) == "google"


def supports_search(model):
    return model.startswith(("claude", "gemini"))   # Gemma, Groq, Mistral, NVIDIA, OpenAI: no search here


UNSEARCHABLE = set()     # domains web search refused this run (e.g. sites that block its crawler)


def unsearchable_in_error(text, search):
    """Domains from the search's allowed/blocked list that an API error names as unusable."""
    if not search or not text:
        return set()
    low = text.lower()
    if not any(k in low for k in ("domain", "not accessible", "user agent", "not allowed", "blocked", "crawl")):
        return set()
    listed = (search.get("allowed") or []) + (search.get("blocked") or [])
    return {d for d in listed if d.lower() in low}


def drop_unsearchable(search):
    if not search or not UNSEARCHABLE:
        return search
    out = dict(search)
    for k in ("allowed", "blocked"):
        if out.get(k):
            out[k] = [d for d in out[k] if d not in UNSEARCHABLE]
    return out


def api_name(model):
    """The provider's model name ("gemini-3.8-flash@paid" is gemini-3.8-flash on the billed key)."""
    return model[:-len(config.PAID_SUFFIX)] if model.endswith(config.PAID_SUFFIX) else model


def key_name(model):
    """Which secret a model's calls need."""
    p = provider(model)
    if p == "claude":
        return "ANTHROPIC_API_KEY"
    if p == "google":
        return "GEMINI_PAID_API_KEY" if model in config.GEMINI_PAID_MODELS else "GEMINI_API_KEY"
    return config.PROVIDERS[p][1]


def has_key(model):
    return bool(config.secret(key_name(model), required=False))


def is_paid(model):
    return sum(config.PRICES.get(model, (0.0, 0.0))) > 0


def level(thinking):
    """Thinking effort as a level string. Integers are legacy token budgets."""
    if thinking is None or isinstance(thinking, str):
        return thinking
    if thinking <= 0:
        return "minimal"
    if thinking <= 1024:
        return "low"
    if thinking <= 4096:
        return "medium"
    return "high"


# Gemini 3.x models don't all accept every thinking level (e.g. no "minimal"). Known substitutions,
# plus any learned during a run (so later calls and batches use a level the model accepts).
GEMINI_LEVEL_SUBS = {"minimal": "low"}
_learned_levels = {}


def gemini_level(model, lvl):
    lvl = _learned_levels.get((model, lvl), lvl)
    return GEMINI_LEVEL_SUBS.get(lvl, lvl)


def next_gemini_level(model, lvl, error_text=""):
    """The nearest level the model accepts: one named in the error if any, else the next one up/down."""
    t = error_text.lower()
    named = [x for x in ("low", "medium", "high") if x != lvl and (f'"{x}"' in t or f" {x}," in t or f" {x}." in t)]
    order = {"minimal": ["low", "medium", "high"], "low": ["medium", "high"], "medium": ["high", "low"],
             "high": ["medium", "low"]}.get(lvl, ["low"])
    pick = next((x for x in order if x in named), None) or next((x for x in order if (model, x) not in _learned_levels), None)
    if pick:
        _learned_levels[(model, lvl)] = pick
    return pick


def headroom(lvl):
    """Extra output tokens to allow for hidden reasoning at a given effort."""
    return config.THINKING_HEADROOM.get(lvl or "medium", 8192)


def chain(role, search=False, model=None):
    """Models to try for a call, in order. An explicit model is used alone (no fallback).
    Claude-primary roles don't fall back to other providers (they are the judgment roles)."""
    if model:
        return [model]
    primary = config.MODELS[role]
    primary = list(primary) if isinstance(primary, (list, tuple)) else [primary]
    if is_claude(primary[0]):
        return primary
    out = []
    for m in primary + list(config.FREE_FALLBACKS) + [config.PAID_FALLBACK] + list(config.LAST_RESORT):
        if m.endswith(config.PAID_SUFFIX) and not has_key(m):
            continue                                  # no billed Gemini key: skip the paid copy
        if m not in out and (not search or supports_search(m)):
            out.append(m)
    return out


def batch_group(model, search=False):
    """Which batch API a call can use, or None to run it directly."""
    if search:
        return None
    p = provider(model)
    if p == "claude":
        return ("claude", None)
    if p == "openai":
        return ("openai", model)
    if p == "google" and is_paid(model) and not model.startswith("gemma"):
        return ("google", model)                # free-tier Gemini runs directly (no discount to gain)
    return None


def result_dict(r):
    """JSON-safe copy of a Result for checkpoints (cost zeroed: it was already paid and logged)."""
    return {"role": r.role, "model": r.model, "text": r.text, "data": r.data, "receipts": r.receipts,
            "cost": 0.0, "fallback": r.fallback, "batched": r.batched}


# ==================================================================== session
class Session:
    def __init__(self, stage, budget=None, anthropic_client=None, http_post=None, http_head=None,
                 prior_spent=0.0, http_get=None):
        self.stage = stage
        cap = budget if budget is not None else config.BUDGET_PER_RUN.get(stage, config.BUDGET_PER_RUN["default"])
        # a resumed run only gets what's left of its cap, so retries can't multiply the spend
        self.budget = cap - (prior_spent or 0.0)
        self.prior_spent = prior_spent or 0.0
        self.spent = 0.0
        self.usage = []
        self.receipts = []
        self._client = anthropic_client
        self._post = http_post or requests.post
        self._head = http_head or requests.head
        self._get = http_get or requests.get
        self._calls = defaultdict(deque)
        self.poll_seconds = 30
        # circuit breaker: a model that keeps failing (outage, timeouts, exhausted free tier) is benched for the
        # rest of this run, so later calls skip straight to the next model instead of waiting it out again
        self.strikes = defaultdict(int)
        self.benched = {}                       # model -> time it may be tried again (a cooldown, not forever)
        self.bench_log = []

    # ================================================================== public
    def ask(self, role, system, prompt, shared=None, search=None, max_tokens=4000, thinking=None, model=None):
        """search: None | {"max_uses": n, "allowed": [...]} | {"max_uses": n, "blocked": [...]}
        model: call this exact model (no fallback). thinking: level string or legacy int budget."""
        self._check_budget()
        now = time.time()
        for m in [m for m, until in self.benched.items() if until <= now]:
            del self.benched[m]                 # cooldown over: give it another chance
            self.strikes[m] = config.BENCH_AFTER_FAILURES - 1   # one more failure benches it again
        models = [m for m in chain(role, bool(search), model) if m not in self.benched]
        if not models:
            raise RuntimeError(f"{model or role}: benched for the rest of this run after repeated failures")
        last = None
        for i, m in enumerate(models):
            try:
                r = self._call(role, m, system, prompt, shared, search, max_tokens, thinking)
                self.strikes[m] = 0
            except BudgetExceeded:
                raise
            except Exception as e:
                last = e
                if "credit balance" not in str(e):
                    self.strikes[m] += 1
                    if self.strikes[m] >= config.BENCH_AFTER_FAILURES and m not in self.benched:
                        self.benched[m] = time.time() + config.BENCH_COOLDOWN_SECONDS
                        self.bench_log.append({"model": m, "error": str(e)[:200]})
                        print(f"  ! {m} failed {self.strikes[m]} times in a row ({str(e)[:100]}): "
                              f"skipping it for {config.BENCH_COOLDOWN_SECONDS // 60} minutes")
                if i + 1 < len(models):
                    print(f"  ! {role}: {m} failed ({str(e)[:100]}) -> trying {models[i + 1]}")
                    continue
                raise
            full = chain(role, bool(search), model)
            if i > 0 or (full and m != full[0]):   # also counts a primary that was skipped while benched
                r.fallback = True
                self.usage[-1]["fallback"] = True
            return r
        raise last

    def _call(self, role, model, system, prompt, shared, search, max_tokens, thinking):
        p = provider(model)
        if p == "claude":
            return self._claude(role, model, system, prompt, shared, search, max_tokens, thinking)
        if p == "google":
            return self._gemini(role, model, system, prompt, shared, search, max_tokens, thinking)
        if p == "openai":
            return self._openai(role, model, system, prompt, shared, max_tokens, thinking)
        return self._openai_compat(role, model, system, prompt, shared, max_tokens)

    def batch(self, reqs, poll_seconds=None, timeout_seconds=5400, checkpoint=None, key=None, tolerate=False):
        """reqs: [{"id", "role", "system", "prompt", "shared"?, "max_tokens"?, "thinking"?, "model"?,
        "search"?}] -> {id: Result}.

        Claude, OpenAI and paid Gemini requests go through their batch APIs (50% off); everything
        else runs directly. Anything that fails or times out in a batch reruns directly.
        With checkpoint + key the batch is resumable: finished results are saved as they arrive,
        and a batch already submitted by a stopped run is collected instead of paid for twice.
        tolerate=True: a request that fails everywhere is left out of the result (and printed) instead
        of stopping the run; the budget cap still stops it."""
        poll_seconds = self.poll_seconds if poll_seconds is None else poll_seconds
        out = {}
        done_step = f"batch:{key}"
        if checkpoint and key:
            for rid, d in (checkpoint.get(done_step) or {}).items():
                out[rid] = Result(**d)

        def remember(rid, r):
            if checkpoint and key:
                checkpoint.save_item(done_step, rid, result_dict(r))

        def direct(r):
            try:
                res = self.ask(r["role"], r["system"], r["prompt"], r.get("shared"), r.get("search"),
                               r.get("max_tokens", 4000), r.get("thinking"), r.get("model"))
            except BudgetExceeded:
                raise
            except Exception as e:
                if not tolerate:
                    raise
                print(f"  ! {r['id']} failed ({str(e)[:120]}); left out")
                return
            out[r["id"]] = res
            remember(r["id"], res)

        groups = defaultdict(list)
        for r in reqs:
            if r["id"] in out:
                continue
            g = batch_group(r.get("model") or chain(r["role"])[0], bool(r.get("search")))
            if g is None:
                direct(r)
            else:
                groups[g].append(r)
        if not groups:
            return out

        # submit (or resume) one batch per group
        handles = {}
        for g, rs in groups.items():
            pend = self._pending_key(key, g)
            saved = checkpoint.get(pend) if checkpoint and key else None
            if saved and set(saved.get("ids", [])) >= {r["id"] for r in rs}:
                print(f"  resuming {g[0]} batch {saved['id']} submitted by an earlier attempt")
                handles[g] = saved["id"]
            else:
                self._check_budget()
                try:
                    handles[g] = self._submit(g, rs, key)
                except Exception as e:
                    if not tolerate:
                        raise
                    print(f"  ! {g[0]} batch could not be submitted ({str(e)[:120]}); running its calls directly")
                    for r in rs:
                        direct(r)
                    continue
                if checkpoint and key:
                    checkpoint.save(pend, {"id": handles[g], "ids": [r["id"] for r in rs]})

        # wait for all of them together
        start, finished = time.time(), set()
        while len(finished) < len(handles):
            for g, h in handles.items():
                try:
                    if g not in finished and self._batch_done(g, h):
                        finished.add(g)
                except Exception as e:          # a failed status check just waits for the next poll
                    print(f"  ! could not check {g[0]} batch {h}: {str(e)[:100]}")
            if len(finished) == len(handles):
                break
            if time.time() - start > timeout_seconds:
                print("  ! batch timed out; cancelling and running the rest directly")
                for g, h in handles.items():
                    if g not in finished:
                        self._cancel(g, h)
                break
            time.sleep(poll_seconds)

        # collect
        for g, h in handles.items():
            by_id = {r["id"]: r for r in groups[g]}
            try:
                for rid, res in self._collect(g, h, by_id):
                    if rid in by_id and rid not in out:
                        out[rid] = res
                        remember(rid, res)
            except Exception as e:
                print(f"  ! could not read {g[0]} batch results: {e}")
            if checkpoint and key:
                checkpoint.drop(self._pending_key(key, g))
            for rid, r in by_id.items():
                if rid not in out:
                    print(f"  ! {rid} missing from batch; running directly")
                    direct(r)
        return out

    @staticmethod
    def _pending_key(key, g):
        return f"batch_id:{key}" if g[0] == "claude" else f"batch_id:{key}:{g[0]}:{g[1]}"

    def save(self, run_folder=None):
        rows = [dict(u, date=today_iso(), stage=self.stage) for u in self.usage]
        append_csv(state_path("cost_log.csv"), rows)
        if self.bench_log:                      # why a model was skipped, for diagnosing free-tier trouble
            append_csv(state_path("bench_log.csv"), [dict(b, date=today_iso(), stage=self.stage) for b in self.bench_log])
            self.bench_log = []
        if run_folder and self.receipts:
            append_csv(f"{run_folder}/sources.csv",
                       [dict(r, snippets=" | ".join(r.get("snippets", []))) for r in self.receipts])
        return {"calls": len(self.usage), "cost": round(self.spent, 4),
                "fallbacks": sum(1 for u in self.usage if u.get("fallback")),
                "searches": sum(u["searches"] for u in self.usage)}

    # ================================================================== budget
    def _check_budget(self):
        if self.spent >= self.budget:
            raise BudgetExceeded(f"{self.stage} run hit its ${self.budget:.2f} budget "
                                 f"(spent ${self.spent:.2f}). Stopped to prevent overspend.")

    def _log(self, role, model, tin, tout, cache_w, cache_r, searches, batched):
        if model not in config.PRICES:
            print(f"  ! no price for {model} in config.PRICES; costing it as ${config.UNKNOWN_PRICE}")
        pin, pout = config.PRICES.get(model, config.UNKNOWN_PRICE)
        disc = config.BATCH_DISCOUNT if batched else 1.0
        tokens = (tin * pin + cache_w * pin * config.CACHE_WRITE_MULT
                  + cache_r * pin * config.CACHE_READ_MULT + tout * pout) / 1e6 * disc
        sprice = (config.CLAUDE_SEARCH_PRICE if is_claude(model) else
                  config.GEMINI_PAID_SEARCH_PRICE if model in config.GEMINI_PAID_MODELS else config.GEMINI_SEARCH_PRICE)
        cost = tokens + searches * sprice
        self.spent += cost
        self.usage.append({"role": role, "model": model, "in": tin, "out": tout, "cache_write": cache_w,
                           "cache_read": cache_r, "searches": searches, "batched": batched,
                           "fallback": False, "cost": round(cost, 5)})
        return cost

    def _pace(self, model):
        rpm = config.RPM.get(model, config.RPM.get(provider(model), 8))
        q = self._calls[model]
        while q and time.time() - q[0] > 60:
            q.popleft()
        if len(q) >= rpm:
            time.sleep(max(0.0, 60 - (time.time() - q[0])) + 0.5)
        q.append(time.time())

    # ================================================================== batch plumbing
    def _submit(self, g, rs, key):
        prov, model = g
        if prov == "claude":
            params = [{"custom_id": r["id"], "params": self._claude_params(
                r.get("model") or config.MODELS[r["role"]], r["system"], r["prompt"], r.get("shared"), None,
                r.get("max_tokens", 4000), r.get("thinking"))} for r in rs]
            return self._anthropic().messages.batches.create(requests=params).id
        if prov == "openai":
            lines = [json.dumps({"custom_id": r["id"], "method": "POST", "url": "/v1/responses",
                                 "body": self._openai_body(model, r["system"], r["prompt"], r.get("shared"),
                                                           r.get("max_tokens", 4000), r.get("thinking"))})
                     for r in rs]
            h = self._openai_headers(json_body=False)
            up = self._post(f"{OPENAI_BASE}/files", headers=h, timeout=120, data={"purpose": "batch"},
                            files={"file": (f"{self.stage}-{key}.jsonl", "\n".join(lines).encode(), "application/jsonl")})
            if up.status_code not in (200, 201):
                raise RuntimeError(f"OpenAI file upload failed: HTTP {up.status_code} {up.text[:150]}")
            b = self._post(f"{OPENAI_BASE}/batches", headers=self._openai_headers(), timeout=60,
                           json={"input_file_id": up.json()["id"], "endpoint": "/v1/responses",
                                 "completion_window": "24h", "metadata": {"stage": self.stage, "key": str(key)}})
            if b.status_code not in (200, 201):
                raise RuntimeError(f"OpenAI batch create failed: HTTP {b.status_code} {b.text[:150]}")
            return b.json()["id"]
        # paid Gemini
        body = {"batch": {"display_name": f"{self.stage}-{key}", "input_config": {"requests": {"requests": [
            {"request": self._gemini_body(model, r["system"], r["prompt"], r.get("shared"), None,
                                          r.get("max_tokens", 4000), r.get("thinking")),
             "metadata": {"key": r["id"]}} for r in rs]}}}}
        resp = self._post(f"{GEMINI_BASE}/models/{api_name(model)}:batchGenerateContent", json=body, timeout=120,
                          headers=self._gemini_headers(model))
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini batch create failed: HTTP {resp.status_code} {resp.text[:150]}")
        return resp.json()["name"]

    def _batch_done(self, g, h):
        prov, model = g
        if prov == "claude":
            return self._anthropic().messages.batches.retrieve(h).processing_status == "ended"
        if prov == "openai":
            r = self._get(f"{OPENAI_BASE}/batches/{h}", headers=self._openai_headers(), timeout=60)
            return r.json().get("status") in OPENAI_DONE
        d = self._get(f"{GEMINI_BASE}/{h}", headers=self._gemini_headers(model), timeout=60).json()
        state = (d.get("metadata") or {}).get("state") or d.get("state")
        return bool(d.get("done")) or state in GEMINI_DONE

    def _cancel(self, g, h):
        prov, model = g
        try:
            if prov == "claude":
                self._anthropic().messages.batches.cancel(h)
            elif prov == "openai":
                self._post(f"{OPENAI_BASE}/batches/{h}/cancel", headers=self._openai_headers(), timeout=60)
            else:
                self._post(f"{GEMINI_BASE}/{h}:cancel", headers=self._gemini_headers(model), timeout=60)
        except Exception:
            pass

    def _collect(self, g, h, by_id):
        """Yields (request id, Result) for every request that succeeded in the batch."""
        prov, model = g
        if prov == "claude":
            for item in self._anthropic().messages.batches.results(h):
                req = by_id.get(item.custom_id)
                if req and item.result.type == "succeeded":
                    msg = item.result.message
                    yield item.custom_id, self._finish_claude(
                        req["role"], req.get("model") or config.MODELS[req["role"]], list(msg.content),
                        [msg.usage], batched=True)
            return
        if prov == "openai":
            b = self._get(f"{OPENAI_BASE}/batches/{h}", headers=self._openai_headers(), timeout=60).json()
            fid = b.get("output_file_id")
            if not fid:
                return
            text = self._get(f"{OPENAI_BASE}/files/{fid}/content", headers=self._openai_headers(), timeout=120).text
            for line in text.splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                req = by_id.get(item.get("custom_id"))
                resp = item.get("response") or {}
                if req and resp.get("status_code") == 200 and resp.get("body"):
                    try:
                        yield item["custom_id"], self._openai_parse(req["role"], model, resp["body"], batched=True)
                    except Exception as e:
                        print(f"  ! {item['custom_id']}: unusable batch reply ({e})")
            return
        d = self._get(f"{GEMINI_BASE}/{h}", headers=self._gemini_headers(model), timeout=120).json()
        items = None
        for container in (d.get("response"), d.get("dest"), (d.get("output") or {}).get("inlinedResponses")):
            if isinstance(container, dict) and "inlinedResponses" in container:
                items = container["inlinedResponses"]
                break
            if isinstance(container, list):
                items = container
                break
        if isinstance(items, dict):
            items = items.get("inlinedResponses", [])
        ids = list(by_id)
        for i, item in enumerate(items or []):
            rid = ((item.get("metadata") or {}).get("key")) or (ids[i] if i < len(ids) else None)
            req = by_id.get(rid)
            if req and item.get("response"):
                try:
                    yield rid, self._gemini_parse(req["role"], model, item["response"], batched=True)
                except Exception as e:
                    print(f"  ! {rid}: unusable batch reply ({e})")

    # ================================================================== Claude
    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.secret("ANTHROPIC_API_KEY"), max_retries=8)
        return self._client

    @staticmethod
    def _claude_params(model, system, prompt, shared, search, max_tokens, thinking=None):
        content = []
        if shared:  # cached: repeat reads of the same dossier cost ~10% of normal input
            content.append({"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}})
        content.append({"type": "text", "text": prompt})
        p = {"model": model, "max_tokens": max_tokens,
             "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
             "messages": [{"role": "user", "content": content}]}
        if isinstance(thinking, str):          # Claude thinks only when a level is asked for explicitly
            effort = {"minimal": "low"}.get(thinking, thinking)
            p["thinking"] = {"type": "adaptive"}
            p["output_config"] = {"effort": effort}
            p["max_tokens"] = max_tokens + headroom(effort)
        if search:
            tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": search.get("max_uses", 5)}
            if search.get("allowed"):
                tool["allowed_domains"] = search["allowed"]
            elif search.get("blocked"):
                tool["blocked_domains"] = search["blocked"]
            p["tools"] = [tool]
        return p

    def _claude(self, role, model, system, prompt, shared, search, max_tokens, thinking=None):
        client = self._anthropic()
        search = drop_unsearchable(search)
        params = self._claude_params(model, system, prompt, shared, search, max_tokens, thinking)
        blocks, usages = [], []
        for _ in range(4):  # web search can pause a long turn; continue it
            try:
                r = client.messages.create(**params)
            except Exception as e:
                # a site in the domain list that web search can't reach makes the whole request fail:
                # drop the site(s) the error names, remember them for the rest of the run, retry once
                bad = unsearchable_in_error(str(e), search)
                if not bad or blocks:
                    raise
                UNSEARCHABLE.update(bad)
                print(f"  ! web search can't use {', '.join(sorted(bad))}: dropped from the domain list, retrying")
                search = drop_unsearchable(search)
                params = self._claude_params(model, system, prompt, shared, search, max_tokens, thinking)
                r = client.messages.create(**params)
            blocks += list(r.content)
            usages.append(r.usage)
            if r.stop_reason != "pause_turn":
                break
            params = dict(params, messages=params["messages"] + [{"role": "assistant", "content": r.content}])
        return self._finish_claude(role, model, blocks, usages)

    def _finish_claude(self, role, model, blocks, usages, batched=False):
        cost = 0.0
        for u in usages:
            st = getattr(u, "server_tool_use", None)
            cost += self._log(role, model, u.input_tokens or 0, u.output_tokens or 0,
                              getattr(u, "cache_creation_input_tokens", 0) or 0,
                              getattr(u, "cache_read_input_tokens", 0) or 0,
                              (getattr(st, "web_search_requests", 0) or 0) if st else 0, batched)
        text = "".join(b.text for b in blocks if getattr(b, "type", "") == "text")
        rec = claude_receipts(role, blocks)
        self.receipts += rec
        return Result(role, model, text, extract_json(text), rec, cost, batched=batched)

    # ================================================================== Gemini / Gemma
    def _gemini_headers(self, model):
        key = None
        if model in config.GEMINI_PAID_MODELS:   # paid models live on a billing-enabled project's key
            key = config.secret("GEMINI_PAID_API_KEY", required=False)
        return {"x-goog-api-key": key or config.secret("GEMINI_API_KEY"), "Content-Type": "application/json"}

    @staticmethod
    def _gemini_body(model, system, prompt, shared, search, max_tokens, thinking):
        user = (shared + "\n\n" + prompt) if shared else prompt
        gemma = model.startswith("gemma")
        if gemma:        # Gemma on the Gemini API takes no system instruction, thinking config, or tools
            user, thinking, search = f"INSTRUCTIONS:\n{system}\n\n{user}", None, None
        lvl = level(thinking)
        body = {"contents": [{"role": "user", "parts": [{"text": user}]}],
                # Gemini counts its hidden "thinking" against the output limit, so add headroom
                "generationConfig": {"maxOutputTokens": max(max_tokens, 2048) + (0 if gemma else headroom(lvl))}}
        if not gemma:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if lvl is not None and not gemma:
            if model.startswith("gemini-2"):     # 2.x models take a token budget
                body["generationConfig"]["thinkingConfig"] = {
                    "thinkingBudget": thinking if isinstance(thinking, int) else headroom(lvl) // 2}
            else:                                # 3.x models take a level (thinking can't be fully off)
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": gemini_level(model, lvl)}
        if search:
            body["tools"] = [{"google_search": {}}]
        return body

    def _gemini(self, role, model, system, prompt, shared, search, max_tokens, thinking):
        body = self._gemini_body(model, system, prompt, shared, search, max_tokens, thinking)
        url = f"{GEMINI_BASE}/models/{api_name(model)}:generateContent"
        last = None
        for attempt in range(config.GEMINI_MAX_RETRIES):
            self._pace(model)
            resp = self._post(url, json=body, timeout=180, headers=self._gemini_headers(model))
            if resp.status_code == 200:
                try:
                    return self._gemini_parse(role, model, resp.json())
                except ValueError as e:
                    last = str(e)
                    continue
            last = f"HTTP {resp.status_code}: {resp.text[:150]}"
            cfg = body["generationConfig"].get("thinkingConfig") or {}
            if resp.status_code == 400 and "thinking level" in resp.text.lower() and cfg.get("thinkingLevel"):
                nxt = next_gemini_level(model, cfg["thinkingLevel"], resp.text)
                if nxt:                          # this model doesn't take that level: use the nearest it does
                    print(f"  ! {model}: thinking level {cfg['thinkingLevel']} not supported; using {nxt}")
                    cfg["thinkingLevel"] = nxt
                    continue
            if resp.status_code in (429, 500, 503):
                time.sleep([10, 30, 60][min(attempt, 2)])
                continue
            break
        raise RuntimeError(last or "Gemini call failed")

    def _gemini_parse(self, role, model, data, batched=False):
        cands = data.get("candidates") or []
        parts = (cands[0].get("content", {}) or {}).get("parts", []) if cands else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise ValueError(f"empty reply (finishReason={cands[0].get('finishReason') if cands else 'none'})")
        um = data.get("usageMetadata", {})
        gm = cands[0].get("groundingMetadata", {}) or {}
        cached = um.get("cachedContentTokenCount", 0) or 0
        cost = self._log(role, model, (um.get("promptTokenCount", 0) or 0) - cached,
                         (um.get("candidatesTokenCount", 0) or 0) + (um.get("thoughtsTokenCount", 0) or 0),
                         0, cached, len(gm.get("webSearchQueries", []) or []), batched)
        rec = self._gemini_receipts(role, gm)
        self.receipts += rec
        return Result(role, model, text, extract_json(text), rec, cost, batched=batched)

    def _gemini_receipts(self, role, gm):
        chunks = gm.get("groundingChunks", []) or []
        supports = defaultdict(list)
        for s in gm.get("groundingSupports", []) or []:
            for i in s.get("groundingChunkIndices", []) or []:
                supports[i].append((s.get("segment", {}) or {}).get("text", "")[:300])
        out = []
        for i, ch in enumerate(chunks):
            web = ch.get("web") or {}
            uri = web.get("uri")
            if not uri:
                continue
            out.append({"agent": role, "url": self._resolve(uri), "title": web.get("title", ""),
                        "status": "cited" if supports.get(i) else "consulted",
                        # Gemini gives the MODEL's sentence that the source supports, not the
                        # source's own words, so these can't be used to verify numbers.
                        "snippet_kind": "model_text", "snippets": supports.get(i, [])})
        return out

    def _resolve(self, uri):
        """Gemini grounding links are Google redirect URLs; follow them to the real page."""
        if "grounding-api-redirect" not in uri:
            return uri
        try:
            r = self._head(uri, allow_redirects=True, timeout=10)
            return r.url or uri
        except Exception:
            return uri

    # ================================================================== OpenAI (Responses API)
    @staticmethod
    def _openai_headers(json_body=True):
        h = {"Authorization": f"Bearer {config.secret('OPENAI_API_KEY')}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    @staticmethod
    def _openai_body(model, system, prompt, shared, max_tokens, thinking):
        lvl = level(thinking) or "medium"
        effort = {"minimal": "low"}.get(lvl, lvl)
        # shared dossier first: OpenAI caches repeated prompt prefixes automatically
        user = (shared + "\n\n" + prompt) if shared else prompt
        return {"model": model.split(":", 1)[1], "instructions": system, "input": user,
                "reasoning": {"effort": effort}, "max_output_tokens": max(max_tokens, 2048) + headroom(effort)}

    def _openai(self, role, model, system, prompt, shared, max_tokens, thinking):
        body = self._openai_body(model, system, prompt, shared, max_tokens, thinking)
        last = None
        for attempt in range(config.GEMINI_MAX_RETRIES):
            self._pace(model)
            resp = self._post(f"{OPENAI_BASE}/responses", json=body, timeout=300, headers=self._openai_headers())
            if resp.status_code == 200:
                try:
                    return self._openai_parse(role, model, resp.json())
                except ValueError as e:
                    last = str(e)
                    continue
            last = f"HTTP {resp.status_code}: {resp.text[:150]}"
            if resp.status_code in (429, 500, 502, 503):
                time.sleep([10, 30, 60][min(attempt, 2)])
                continue
            break
        raise RuntimeError(last or "OpenAI call failed")

    def _openai_parse(self, role, model, data, batched=False):
        text = data.get("output_text") or "".join(
            c.get("text", "") for o in data.get("output") or [] if o.get("type") == "message"
            for c in o.get("content") or [] if c.get("type") in ("output_text", "text"))
        if not text.strip():
            raise ValueError(f"empty reply (status={data.get('status')})")
        u = data.get("usage") or {}
        cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
        # reasoning tokens are included in output_tokens and billed as output
        cost = self._log(role, model, (u.get("input_tokens", 0) or 0) - cached, u.get("output_tokens", 0) or 0,
                         0, cached, 0, batched)
        return Result(role, model, text, extract_json(text), [], cost, batched=batched)

    # ================================================================== Groq / Mistral / NVIDIA
    def _openai_compat(self, role, model, system, prompt, shared, max_tokens):
        """Groq, Mistral and NVIDIA all speak the OpenAI chat-completions format."""
        prov, name = model.split(":", 1)
        base, key_name = config.PROVIDERS[prov]
        key = config.secret(key_name)
        user = (shared + "\n\n" + prompt) if shared else prompt
        body = {"model": name, "temperature": 0.3,
                "max_tokens": max(max_tokens, 2048) + 2048,     # reasoning models spend some tokens thinking
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last = None
        for attempt in range(config.GEMINI_MAX_RETRIES):
            self._pace(model)
            resp = self._post(f"{base}/chat/completions", json=body, timeout=config.COMPAT_TIMEOUT_SECONDS,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if not text.strip():
                    last = "empty reply"
                    continue
                u = data.get("usage") or {}
                cost = self._log(role, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), 0, 0, 0, False)
                return Result(role, model, text, extract_json(text), [], cost)
            last = f"HTTP {resp.status_code}: {resp.text[:150]}"
            if resp.status_code in (429, 500, 502, 503):
                time.sleep([10, 30, 60][min(attempt, 2)])
                continue
            break
        raise RuntimeError(last or f"{prov} call failed")


def claude_receipts(role, blocks):
    cited, seen = {}, {}
    for b in blocks:
        t = getattr(b, "type", "")
        if t == "text":
            for c in getattr(b, "citations", None) or []:
                url = getattr(c, "url", None)
                if url:
                    e = cited.setdefault(url, {"agent": role, "url": url, "title": getattr(c, "title", ""),
                                               "status": "cited", "snippet_kind": "source_text", "snippets": []})
                    s = (getattr(c, "cited_text", "") or "")[:500]
                    if s and s not in e["snippets"]:
                        e["snippets"].append(s)
        elif t == "web_search_tool_result":
            content = getattr(b, "content", None)
            for res in content if isinstance(content, list) else []:
                url = getattr(res, "url", None)
                if url:
                    seen.setdefault(url, {"agent": role, "url": url, "title": getattr(res, "title", ""),
                                          "status": "consulted", "snippet_kind": "source_text",
                                          "page_age": getattr(res, "page_age", ""), "snippets": []})
    for u in cited:
        seen.pop(u, None)
    return list(cited.values()) + list(seen.values())
