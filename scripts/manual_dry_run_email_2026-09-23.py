"""
One-off manual dry run: emails today's current Word docs + Excel tracker
to NOTIFY_EMAIL, clearly labeled as a manual test — NOT a claim that any
regulatory change happened today.

This exists because notify.py's own `send_summary([], [])` (its
__main__ block) deliberately sends NO attachments when there are no
applied changes (see _attach_docs / _regulatory_changes in notify.py) --
that's correct behaviour for the real daily pipeline, but it means it
can't be used as-is to just "see the current files by email". This
script reuses the same Gmail settings and attaches the docs unconditionally.

Usage (from the repo root, with your usual venv):
    python scripts/manual_dry_run_email_2026-09-23.py

Requires the same .env vars notify.py uses: GMAIL_ADDRESS,
GMAIL_APP_PASSWORD, NOTIFY_EMAIL.
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

from db import PROJECT_ROOT  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

ATTACHMENT_PATHS = [
    PROJECT_ROOT / "docs" / "DPDP_Rules_2025.docx",
    PROJECT_ROOT / "docs" / "DPDP_Act_2023.docx",
    PROJECT_ROOT / "data" / "DPDP_Rules_Tracker.xlsx",
]
MIME_TYPES = {
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


def main() -> None:
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and NOTIFY_EMAIL):
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD / NOTIFY_EMAIL not set — check .env")

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = EmailMessage()
    msg["Subject"] = f"DPDP Monitor — MANUAL DRY RUN, current files as of {today}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL
    msg.set_content(
        "This is a manual dry run, not a real pipeline run — no regulatory change is "
        "being claimed today.\n\n"
        "Attached are the two Word documents and the Excel tracker exactly as they "
        "currently stand in db/dpdpa.db on this machine (post the 23 Sep 2026 audit-fix "
        "merge to main), so you can see the current state by email.\n\n"
        "If you want the real thing next time, just run:\n"
        "    python src/run_pipeline.py\n"
        "which fetches sources, classifies with Claude, applies any real change, "
        "regenerates these same files, and emails a normal summary.\n"
    )

    missing = [p for p in ATTACHMENT_PATHS if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Expected file(s) missing, run src/export_word.py / "
                                 f"src/export_excel.py first: {missing}")

    for path in ATTACHMENT_PATHS:
        maintype, subtype = MIME_TYPES[path.suffix]
        msg.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"[manual dry run] sent to {NOTIFY_EMAIL}: {msg['Subject']}")


if __name__ == "__main__":
    main()
