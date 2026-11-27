import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

from pipeline import notify  # noqa: E402


class R:
    status_code = 204


def test_discord_posts_chunks_and_skips_without_webhook():
    os.environ.pop("DISCORD_WEBHOOK_URL", None)
    assert notify.discord("s", "t") == 0
    os.environ["DISCORD_WEBHOOK_URL"] = "https://example.invalid/hook"
    sent = []
    n = notify.discord("Subject", "\n".join(["x" * 100] * 50), post=lambda url, **kw: sent.append(kw) or R())
    assert n == len(sent) >= 3 and all(len(k["json"]["content"]) <= 2000 for k in sent)
    assert sent[0]["json"]["content"].startswith("**Subject**")
    os.environ.pop("DISCORD_WEBHOOK_URL")


if __name__ == "__main__":
    test_discord_posts_chunks_and_skips_without_webhook()
    print("PASS test_discord_posts_chunks_and_skips_without_webhook")
