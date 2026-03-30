#!/usr/bin/env python3
"""Send a Telegram notification.

Usage:
    notify.py <message>      — send message to configured chat
    notify.py --test         — send a test message to verify credentials

Env vars (loaded from .env at project root):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Exits 0 always — never crashes the caller.
"""
import os
import sys
from pathlib import Path

# Load .env from project root (two levels up from scripts/)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass  # python-dotenv unavailable; fall back to environment


def send(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("notify.py: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping", file=sys.stderr)
        return

    import urllib.request
    import json

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        print(f"notify.py: Telegram request failed: {exc}", file=sys.stderr)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(f"Usage: {sys.argv[0]} <message>  |  {sys.argv[0]} --test", file=sys.stderr)
        sys.exit(0)

    if args[0] == "--test":
        send("✅ Cal notify.py test — Telegram credentials are working.")
        print("notify.py: test message sent")
        return

    send(args[0])


if __name__ == "__main__":
    main()
