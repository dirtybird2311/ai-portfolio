"""
Your sign-off on a flagged macro view.

When the macro critic marks a view NEEDS_REVIEW, it is held in state/macro_view_pending.json and
a GitHub issue asks you to tick APPROVE or REJECT (the GitHub phone app works). Until you decide,
the pipeline keeps using the last approved view. Every run checks the issue first:
  APPROVE -> the pending view becomes the active one
  REJECT  -> it is discarded and the previous view stays
Without GitHub (local runs) the checklist is state/macro_review.md.
"""
import re

import requests

from .book import _gh
from .util import now_et, read_json, state_path, write_json


def request_macro_review(view, critic, get=requests):
    body = "\n".join([
        f"The {view['date']} macro view was flagged by the logic critic and is **on hold**.",
        f"Critic: {critic.get('overall')}. {critic.get('summary', '')}", "",
        "Problem tilts:"] + [f"- {s}: {v.get('status')}: {v.get('issue')}" for s, v in (critic.get("sectors") or {}).items()
                             if v.get("status") != "PASS"] + [
        "", "Proposed tilts: " + ", ".join(f"{s} {t:+d}" for s, t in view["tilts"].items() if t), "",
        "Tick ONE box. Until then, the last approved view stays in use.", "",
        "- [ ] APPROVE this macro view", "- [ ] REJECT it (keep the previous view)"])
    pending = {"view": view, "issue": None, "requested": now_et().date().isoformat()}
    gh = _gh()
    if gh:
        base, h = gh
        r = get.post(f"{base}/issues", headers=h, timeout=30, json={
            "title": f"Macro view {view['date']} needs your review", "body": body, "labels": ["macro-review"]})
        if r.status_code in (200, 201):
            pending["issue"] = r.json()["number"]
            pending["url"] = r.json()["html_url"]
    if not pending["issue"]:
        state_path("macro_review.md").write_text(body)
        pending["url"] = str(state_path("macro_review.md"))
    write_json(state_path("macro_view_pending.json"), pending)
    return pending


def check_macro(get=requests):
    """Apply your decision on a pending macro view, if you've made one. Returns
    'approved' | 'rejected' | 'waiting' | None (nothing pending)."""
    pending = read_json(state_path("macro_view_pending.json"))
    if not pending:
        return None
    body, gh = "", _gh()
    if gh and pending.get("issue"):
        base, h = gh
        r = get.get(f"{base}/issues/{pending['issue']}", headers=h, timeout=30)
        if r.status_code == 200:
            body = r.json().get("body", "")
    elif state_path("macro_review.md").exists():
        body = state_path("macro_review.md").read_text()
    approve = re.search(r"-\s*\[[xX]\]\s*APPROVE", body)
    reject = re.search(r"-\s*\[[xX]\]\s*REJECT", body)
    if approve and not reject:
        view = dict(pending["view"], status="OK (approved by you)", approved=now_et().date().isoformat())
        write_json(state_path("macro_view.json"), view)
        decision = "approved"
    elif reject and not approve:
        decision = "rejected"
    else:
        return "waiting"
    state_path("macro_view_pending.json").unlink()
    if gh and pending.get("issue"):
        base, h = gh
        get.post(f"{base}/issues/{pending['issue']}/comments", headers=h, timeout=30,
                 json={"body": f"Recorded: {decision}."})
        get.patch(f"{base}/issues/{pending['issue']}", headers=h, json={"state": "closed"}, timeout=30)
    print(f"Macro view {pending['view']['date']}: {decision} by you")
    return decision
