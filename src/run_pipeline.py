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

from datetime import date, datetime, timezone
from pathlib import Path

from apply_change import apply
from classify_change import CLAUDE_MODEL, ClassificationFailed, classify
from db import DB_PATH, PROJECT_ROOT, get_connection, init_schema
from discover_documents import discover_all, mark_alerted
from fetch_sources import fetch_all
from notify import send_summary


# "Is this run finished?" marker (audit finding M-14).
#
# The daily GitHub Actions job commits db/dpdpa.db, docs/*.docx and
# data/*.xlsx back to the repository with `if: always()`, which means it
# committed even when the run had been killed half way through — leaving a
# database that no longer matched the documents beside it. This file is deleted
# at the start of every run and written only once the database work and any
# needed document regeneration have both finished, so the commit step can ask
# "did this run actually get to the end?" instead of committing regardless.
#
# Not in git: var/ is ignored. A missing file means "no" — which is the safe
# answer.
COMPLETE_MARKER = PROJECT_ROOT / "var" / "pipeline_complete"


def _clear_complete_marker() -> None:
    COMPLETE_MARKER.unlink(missing_ok=True)


def _write_complete_marker(applied: int, exported: list[str]) -> None:
    COMPLETE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    COMPLETE_MARKER.write_text(
        f"finished {datetime.now(timezone.utc).isoformat()}\n"
        f"changes applied: {applied}\n"
        f"documents regenerated: {', '.join(exported) if exported else 'none needed'}\n",
        encoding="utf-8",
    )
    print(f"[run_pipeline] wrote {COMPLETE_MARKER} — this run reached the end, so its "
           f"results are safe to commit.")


def _database_path(conn) -> Path:
    """
    The file this connection is actually open on, asked of SQLite itself rather
    than assumed. Used to refuse to overwrite the tracked Word/Excel documents
    from anything other than the real database.
    """
    for _seq, name, filename in conn.execute("PRAGMA database_list").fetchall():
        if name == "main":
            return Path(filename).resolve() if filename else Path()
    return Path()


def _read_snapshot(conn, document_id: str) -> dict | None:
    """
    The stored baseline for one source, or None if it has none. "Baseline"
    means the text as the classifier last saw it; see db/schema.sql's
    source_snapshot table.
    """
    row = conn.execute(
        "SELECT content_hash, content_text, fetched_date FROM source_snapshot "
        "WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def _restore_after_failed_apply(conn, fetch_result, prior_snapshot: dict | None) -> None:
    """
    Undo the two things that would otherwise make a refused change invisible
    forever: the source's fingerprint in source_log, and its baseline in
    source_snapshot. Both are put back exactly as they were before classify()
    ran, and the source is marked Error so the run's own summary shows it.
    """
    conn.execute(
        "UPDATE source_log SET content_hash = ?, processing_status = 'Error' "
        "WHERE document_id = ?",
        (fetch_result.prior_hash, fetch_result.document_id),
    )
    if prior_snapshot is None:
        # There was no baseline before this run, so there must not be one after
        # it either — leaving today's text behind would make tomorrow's diff
        # empty, which is the exact failure this is guarding against.
        conn.execute(
            "DELETE FROM source_snapshot WHERE document_id = ?", (fetch_result.document_id,)
        )
    else:
        conn.execute(
            "UPDATE source_snapshot SET content_hash = ?, content_text = ?, fetched_date = ? "
            "WHERE document_id = ?",
            (prior_snapshot["content_hash"], prior_snapshot["content_text"],
             prior_snapshot["fetched_date"], fetch_result.document_id),
        )
    conn.commit()


def main() -> int:
    # Delete the "finished" marker first. If this run dies anywhere before the
    # end, the marker stays missing and the workflow commits nothing.
    _clear_complete_marker()

    conn = get_connection()
    init_schema(conn)
    # Which database are we actually on? A test (or a dry run against a copy)
    # patches get_connection to hand back a throwaway file, and in that case the
    # tracked Word/Excel documents must NOT be regenerated — see below.
    db_path = _database_path(conn)
    exports_done: list[str] = []

    applied_changes: list[dict] = []
    errors: list[str] = []
    # Two softer channels than `errors`, both of which end up in the email:
    #   baseline_notes — "this is the first time we have seen X" (normal)
    #   alerts         — "a human should go and look at this" (not an error,
    #                    but not nothing either). See notify.send_summary.
    baseline_notes: list[str] = []
    alerts: list[str] = []
    # Errors that are simply yesterday's error again. Still reported in full;
    # just not shouted about on the subject line (audit M-3).
    repeated_errors: list[str] = []

    changed_sources = fetch_all(conn, fetch_errors=errors, repeated_errors=repeated_errors)
    print(f"[run_pipeline] {len(changed_sources)} source(s) changed.")

    for fetch_result in changed_sources:
        # Remember the baseline BEFORE classify() advances it, so an apply
        # failure can put it back (audit finding H-2). Without this, a change
        # that apply_change deliberately REFUSES is reported once and then
        # becomes permanently invisible: the fingerprint and the baseline have
        # both moved on, so tomorrow's run sees no change and never looks at
        # that content again. The safety refusal turned a detected change into
        # an undetectable one.
        prior_snapshot = _read_snapshot(conn, fetch_result.document_id)

        try:
            classified = classify(fetch_result, conn, baseline_notes=baseline_notes,
                                   alerts=alerts, errors=errors)
        except Exception as exc:
            if isinstance(exc, ClassificationFailed):
                errors.append(str(exc))
            else:
                errors.append(
                    f"classify_change failed unexpectedly for {fetch_result.document_id} "
                    f"({fetch_result.url}): {exc}"
                )
            # Put the previous hash back so tomorrow's run sees this source as
            # still changed and retries it. Without this, a single failed day
            # silently and permanently drops the change (the new hash is
            # already stored in source_log, so the next run would report "no
            # change" and never look at it again).
            conn.execute(
                "UPDATE source_log SET content_hash = ? WHERE document_id = ?",
                (fetch_result.prior_hash, fetch_result.document_id),
            )
            conn.commit()
            continue

        if not classified:
            conn.execute(
                "UPDATE source_log SET processing_status = 'No Change Detected' WHERE document_id = ?",
                (fetch_result.document_id,),
            )
            conn.commit()

        all_applied = True
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
                all_applied = False

        if not all_applied:
            # Roll the whole per-source unit of work back to where it started,
            # so tomorrow's run sees this source as still changed and tries
            # again (audit finding H-2).
            #
            # Changes that DID apply are deliberately kept. apply_change writes
            # each change in its own transaction, and un-writing one would mean
            # reversing a span edit in provisions.full_text — more risk than
            # leaving it. Re-processing is safe because apply_change refuses
            # unless old_full_text appears in the current text exactly once, so
            # an already-applied change cannot be applied a second time: it
            # matches zero times and is refused. (Proved by
            # test_reprocessing_after_a_partial_failure_does_not_duplicate.)
            _restore_after_failed_apply(conn, fetch_result, prior_snapshot)
            print(f"[run_pipeline] rolled {fetch_result.document_id} back "
                  f"(fingerprint and baseline) so the next run retries it.")

    new_documents: list[dict] = []
    try:
        new_documents, discovery_baseline_notes = discover_all(conn, errors)
        baseline_notes.extend(discovery_baseline_notes)
    except Exception as exc:
        # A discovery failure must never stop the existing fetch -> classify
        # -> apply flow — it's a separate, additive layer (see
        # discover_documents.py). Surfaced here, not swallowed.
        errors.append(f"document discovery failed unexpectedly: {exc}")

    today = date.today().isoformat()
    sources_total = conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE fetched_date = ?", (today,)
    ).fetchone()["c"]
    sources_ok = conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE fetched_date = ? AND processing_status != 'Error'",
        (today,),
    ).fetchone()["c"]

    if applied_changes and db_path == DB_PATH:
        print("[run_pipeline] regenerating docs (changes were applied)...")
        for script in ("export_word.py", "export_excel.py"):
            result = subprocess.run([sys.executable, f"src/{script}"], cwd=str(PROJECT_ROOT))
            if result.returncode != 0:
                errors.append(f"{script} exited with code {result.returncode}")
            else:
                exports_done.append(script)
    elif applied_changes:
        # Pointed at some other database (a test, or a dry run against a copy).
        # export_word.py and export_excel.py always read the tracked database
        # and always write the tracked docs/ and data/ files, so running them
        # here would overwrite real documents from unrelated data. Say so out
        # loud rather than doing it quietly.
        print(f"[run_pipeline] NOT regenerating documents: running against {db_path}, "
               f"not {DB_PATH}. The Word and Excel files are only ever rebuilt from "
               f"the real database.")
    else:
        print("[run_pipeline] no changes applied — skipping doc regeneration.")

    # The database work and any needed document regeneration are both done. A
    # failure to SEND the email (below) does not make the results unsafe to
    # commit, and neither does an unreachable source — those are recorded as
    # errors and the exit code reflects them. What must not be committed is a
    # half-finished run, and by here the run is not half-finished.
    exports_needed = bool(applied_changes) and db_path == DB_PATH
    if exports_needed and len(exports_done) < 2:
        print("[run_pipeline] NOT writing the completion marker: documents were due to be "
               "regenerated and at least one export failed, so the database and the "
               "documents may not agree. Nothing will be committed; tomorrow redoes the work.")
    else:
        _write_complete_marker(len(applied_changes), exports_done)

    try:
        send_summary(applied_changes, errors, sources_total, sources_ok,
                      new_documents=new_documents, baseline_notes=baseline_notes,
                      source_alerts=alerts, repeated_errors=repeated_errors)
        if new_documents:
            # Only mark alerted=1 once the email that contains them has
            # actually been sent — if send_summary raised above, this line
            # never runs, so a failed send is retried (re-alerted) next run
            # instead of being silently marked as sent.
            #
            # Uses the run's OWN connection (audit finding M-13). It used to
            # open a second one on the hard-coded default database path, which
            # meant that pointing run_pipeline at a test database still wrote
            # to the real one.
            mark_alerted(conn, [d["url"] for d in new_documents])
    except Exception as exc:
        print(f"[run_pipeline] WARNING: notify failed: {exc}")
        errors.append(f"notify failed: {exc}")

    conn.close()

    if errors:
        print(f"[run_pipeline] completed with {len(errors)} error(s).")
        return 1
    print("[run_pipeline] completed cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
