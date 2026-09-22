"""
Send one summary email per pipeline run via Gmail SMTP (smtplib + ssl,
app password — no OAuth). Sends whether or not any changes were found.

Env vars (from .env locally, GitHub Actions secrets in CI):
    GMAIL_ADDRESS       sender Gmail address
    GMAIL_APP_PASSWORD  16-char Gmail app password (not the account password)
    NOTIFY_EMAIL        recipient address

Usage:
    from notify import send_summary
    send_summary(applied_changes, errors)
"""
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage

from dotenv import load_dotenv

from db import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

# Attached only when changes were actually applied (that's when
# export_word.py/export_excel.py regenerate them — see run_pipeline.py).
ATTACHMENT_PATHS = [
    PROJECT_ROOT / "docs" / "DPDP_Rules_2025.docx",
    PROJECT_ROOT / "docs" / "DPDP_Act_2023.docx",
    PROJECT_ROOT / "data" / "DPDP_Rules_Tracker.xlsx",
]

MIME_TYPES = {
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


def _build_body(applied_changes: list[dict], errors: list[str]) -> tuple[str, str]:
    today = date.today().isoformat()
    n = len(applied_changes)

    if errors:
        subject = f"DPDP Monitor — {len(errors)} error(s) today ({today})" + (
            f", {n} change{'s' if n != 1 else ''} applied" if n else ""
        )
    elif n == 0:
        subject = f"DPDP Monitor — No changes detected today ({today})"
    else:
        subject = f"DPDP Monitor — {n} change{'s' if n != 1 else ''} applied today ({today})"

    if n == 0:
        lines = ["No changes were detected across PIB, MeitY, or eGazette today."]
    else:
        lines = [f"{n} change{'s' if n != 1 else ''} applied today:\n"]
        for c in applied_changes:
            lines.append(f"  - {c['provision_id']} — {c['change_type']}: {c['new_value_summary']}")

    if errors:
        lines.append(f"\n{len(errors)} error(s) during this run:")
        for e in errors:
            lines.append(f"  - {e}")

    if applied_changes:
        lines.append("\nUpdated Word docs and Excel tracker are attached to this email.")

    lines.append("\n—\nDPDP Regulatory Change Monitor (automated, no human review gate)")
    return subject, "\n".join(lines)


def _attach_docs(msg: EmailMessage) -> None:
    for path in ATTACHMENT_PATHS:
        if not path.exists():
            print(f"[notify] WARNING: expected attachment missing, skipping: {path}")
            continue
        maintype, subtype = MIME_TYPES[path.suffix]
        msg.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )


def send_summary(applied_changes: list[dict], errors: list[str] | None = None) -> None:
    errors = errors or []
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set (check .env / GitHub secrets)")
    if not NOTIFY_EMAIL:
        raise RuntimeError("NOTIFY_EMAIL not set (check .env / GitHub secrets)")

    subject, body = _build_body(applied_changes, errors)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL
    msg.set_content(body)

    if applied_changes:
        _attach_docs(msg)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"[notify] sent: {subject}")


if __name__ == "__main__":
    send_summary([], [])
