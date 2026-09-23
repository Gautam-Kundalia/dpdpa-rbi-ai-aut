"""
Daily entrypoint: fetch_sources -> classify_change (changed sources only)
-> apply_change -> export_word/export_excel (only if something was applied)
-> notify (always).

Usage:
    python src/run_pipeline.py
"""
from __future__ import annotations

import subprocess
import sys

from datetime import date

from apply_change import apply
from classify_change import CLAUDE_MODEL, ClassificationFailed, classify
from db import get_connection, init_schema
from fetch_sources import fetch_all
from notify import send_summary


def main() -> int:
    conn = get_connection()
    init_schema(conn)

    changed_sources = fetch_all(conn)
    print(f"[run_pipeline] {len(changed_sources)} source(s) changed.")

    applied_changes: list[dict] = []
    errors: list[str] = []

    for fetch_result in changed_sources:
        try:
            classified = classify(fetch_result, conn)
        except ClassificationFailed as exc:
            errors.append(str(exc))
            continue
        except Exception as exc:
            errors.append(f"classify_change failed unexpectedly for {fetch_result.document_id} ({fetch_result.url}): {exc}")
            continue

        if not classified:
            conn.execute(
                "UPDATE source_log SET processing_status = 'No Change Detected' WHERE document_id = ?",
                (fetch_result.document_id,),
            )
            conn.commit()

        for change in classified:
            try:
                change_id = apply(change, fetch_result, conn, CLAUDE_MODEL)
                ref_row = conn.execute(
                    "SELECT reference FROM provisions WHERE provision_id = ?", (change["provision_id"],)
                ).fetchone()
                applied_changes.append({
                    **change,
                    "change_id": change_id,
                    "change_origin": "regulatory",
                    "reference": ref_row["reference"] if ref_row else change["provision_id"],
                })
                print(f"[run_pipeline] applied {change_id} -> {change['provision_id']} ({change['change_type']})")
            except Exception as exc:
                errors.append(f"apply_change failed for {change.get('provision_id')}: {exc}")

    today = date.today().isoformat()
    sources_total = conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE fetched_date = ?", (today,)
    ).fetchone()["c"]
    sources_ok = conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE fetched_date = ? AND processing_status != 'Error'",
        (today,),
    ).fetchone()["c"]

    conn.close()

    if applied_changes:
        print("[run_pipeline] regenerating docs (changes were applied)...")
        for script in ("export_word.py", "export_excel.py"):
            result = subprocess.run([sys.executable, f"src/{script}"], cwd=".")
            if result.returncode != 0:
                errors.append(f"{script} exited with code {result.returncode}")
    else:
        print("[run_pipeline] no changes applied — skipping doc regeneration.")

    try:
        send_summary(applied_changes, errors, sources_total, sources_ok)
    except Exception as exc:
        print(f"[run_pipeline] WARNING: notify failed: {exc}")
        errors.append(f"notify failed: {exc}")

    if errors:
        print(f"[run_pipeline] completed with {len(errors)} error(s).")
        return 1
    print("[run_pipeline] completed cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
