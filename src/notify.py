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
from word_diff import change_snippet

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


def _regulatory_changes(applied_changes: list[dict]) -> list[dict]:
    """
    Only change_origin='regulatory' rows count as "changes" for the email
    (D1): our own data corrections are never reported here, since they
    aren't something the government did. apply_change.py currently only
    ever inserts 'regulatory' rows (everything run_pipeline.py applies came
    from an AI classification of a real source change), so this filter is
    a safety net, not a no-op — it's what keeps this email correct even
    after data-correction tooling starts sharing the same applied_changes
    shape.
    """
    return [c for c in applied_changes if c.get("change_origin", "regulatory") == "regulatory"]


def _build_body(
    applied_changes: list[dict],
    errors: list[str],
    sources_total: int = 0,
    sources_ok: int = 0,
) -> tuple[str, str]:
    today = date.today().isoformat()
    reg_changes = _regulatory_changes(applied_changes)
    n = len(reg_changes)

    if errors:
        subject = f"DPDP Monitor — {len(errors)} error(s) today ({today})" + (
            f", {n} change{'s' if n != 1 else ''} applied" if n else ""
        )
    elif n == 0:
        subject = f"DPDP Monitor — No changes detected today ({today})"
    else:
        subject = f"DPDP Monitor — {n} change{'s' if n != 1 else ''} applied today ({today})"

    if errors:
        # Must not read "No changes were detected" on an error day — that
        # reads as "everything's fine" when it isn't. Say what was actually
        # checked instead.
        lines = [f"{sources_ok} of {sources_total} source(s) checked successfully today."]
    elif n == 0:
        lines = ["No regulatory changes were detected across PIB, MeitY, or eGazette today."]
    else:
        lines = [f"{n} regulatory change{'s' if n != 1 else ''} applied today:\n"]

    if n:
        for c in reg_changes:
            old_snip, new_snip = change_snippet(c.get("old_full_text"), c.get("new_full_text"))
            ref = c.get("reference") or c.get("provision_id")
            lines.append(f'  - {ref}: "{old_snip}" → "{new_snip}"')

    if errors:
        lines.append(f"\n{len(errors)} error(s) during this run:")
        for e in errors:
            lines.append(f"  - {e}")

    if n:
        lines.append(
            "\nEach provision's plain-language summary (Current_Summary) is left as-is by this "
            "pipeline even when its text changes — it may need a human update to still read "
            "naturally against the new wording. Check Change_Log's Old/New_Value_Summary above "
            "for what actually changed."
        )
        lines.append("Updated Word docs and Excel tracker are attached to this email.")

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


def send_summary(
    applied_changes: list[dict],
    errors: list[str] | None = None,
    sources_total: int = 0,
    sources_ok: int = 0,
) -> None:
    errors = errors or []
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set (check .env / GitHub secrets)")
    if not NOTIFY_EMAIL:
        raise RuntimeError("NOTIFY_EMAIL not set (check .env / GitHub secrets)")

    subject, body = _build_body(applied_changes, errors, sources_total, sources_ok)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL
    msg.set_content(body)

    if _regulatory_changes(applied_changes):
        _attach_docs(msg)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"[notify] sent: {subject}")


if __name__ == "__main__":
    send_summary([], [])
