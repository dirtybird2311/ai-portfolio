"""
Email delivery through Gmail (SMTP + an app password).

Secrets needed (GitHub Secrets):
  GMAIL_ADDRESS       the Gmail account that sends
  GMAIL_APP_PASSWORD  a 16-character app password (Google Account > Security > App passwords;
                      requires 2-Step Verification). Never your normal password.
  EMAIL_TO            optional; defaults to GMAIL_ADDRESS
  DISCORD_WEBHOOK_URL optional; every notification is also posted to that Discord channel

If the secrets are missing (e.g., testing), the email is saved as a .eml file instead.
"""
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from . import config
from .util import today_iso

STATUS_ICON = {"OK": "✅", "PASS": "✅", "FLAG": "⚠️", "NEEDS_REVIEW": "⚠️", "BLOCK": "⛔", "ERROR": "❌"}


def send(subject, text, html=None, attachments=(), save_dir=None):
    """Send an email. Returns 'sent' or the path of the saved .eml when running dry."""
    msg = EmailMessage()
    sender = os.environ.get("GMAIL_ADDRESS") or config.EMAIL_FROM
    to = os.environ.get("EMAIL_TO") or config.EMAIL_TO or sender
    msg["Subject"], msg["From"], msg["To"] = subject, sender or "pipeline@localhost", to or "you@localhost"
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments:
        p = Path(path)
        if p.exists():
            import mimetypes
            main, _, sub = (mimetypes.guess_type(p.name)[0] or "text/plain").partition("/")
            msg.add_attachment(p.read_bytes(), maintype=main, subtype=sub, filename=p.name)

    try:
        discord(subject, text, attachments)
    except Exception as e:                       # Discord is a convenience: never let it stop a run or the email
        print(f"  (Discord post failed: {str(e)[:120]})")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if sender and password:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
            s.login(sender, password)
            s.send_message(msg)
        return "sent"
    out = Path(save_dir or config.RUNS_DIR / today_iso())
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in subject.encode("ascii", "ignore").decode())[:90]
    path = out / f"email_{safe.strip('_')}.eml"
    path.write_bytes(bytes(msg))
    print(f"  (no Gmail secrets set; email saved to {path})")
    return str(path)


DISCORD_LIMIT = 1900                            # Discord caps a message at 2,000 characters


def discord_chunks(subject, text, limit=DISCORD_LIMIT):
    """The subject in bold, then the body split on line breaks into messages under the limit."""
    out, cur = [], f"**{subject}**"
    for line in (text or "").splitlines():
        while len(line) > limit:                 # a single overlong line is cut into pieces
            out.append(cur)
            cur, line = line[:limit], line[limit:]
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur += "\n" + line
    out.append(cur)
    return [c for c in out if c.strip()]


def discord(subject, text, attachments=(), post=None):
    """Mirror a notification to a Discord channel through its webhook (secret DISCORD_WEBHOOK_URL). Images and
    reports attach to the last message. Returns the number of messages posted (0 when no webhook is set)."""
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return 0
    import json as _json
    import requests
    post = post or requests.post
    chunks = discord_chunks(subject, text)[:10]
    files = [Path(a) for a in attachments if Path(a).exists() and Path(a).stat().st_size < 8_000_000][:4]
    for i, c in enumerate(chunks):
        last = i == len(chunks) - 1
        if last and files:
            r = post(url, data={"payload_json": _json.dumps({"content": c})}, timeout=30,
                     files={f"files[{k}]": (f.name, f.read_bytes()) for k, f in enumerate(files)})
        else:
            r = post(url, json={"content": c}, timeout=30)
        if getattr(r, "status_code", 204) >= 300:
            raise RuntimeError(f"HTTP {r.status_code}")
    return len(chunks)


def subject_line(stage, status, headline=""):
    return f"{STATUS_ICON.get(status, '')} AI Portfolio · {stage} · {today_iso()}" + (f" · {headline}" if headline else "")


def alert(stage, error, save_dir=None):
    """Short failure/budget email so a broken run never goes unnoticed."""
    return send(subject_line(stage, "ERROR", "run stopped"),
                f"The {stage} run stopped.\n\nReason:\n{error}\n\nNo trades or views were changed by this run.",
                save_dir=save_dir)
