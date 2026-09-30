"""
One-off data script (30 Sep 2026 audit fixes, findings M-5 and C-4).

WHAT THIS DOES, IN PLAIN WORDS
------------------------------
The `source_log` table is meant to answer one question: "which web pages is
this project watching right now?" It had drifted away from that. It holds seven
rows, but only three of them are still being checked every day. The other four
are leftovers:

  * SRC-0003 and SRC-0006 — one-off Gazette/MeitY PDFs that were fetched by
    hand during an earlier audit. They were never part of the daily round.
  * SRC-0004 — PIB's HTML "all releases" page. Replaced by SRC-0007 (the RSS
    feed) because the HTML page could silently serve Hindi.
  * SRC-0005 — the e-Gazette home page. Retired on 30 Sep 2026 (audit finding
    C-4): its text could reach the stored legal text even though nothing on
    that page is a legal instrument, and it reported "changed" on 20 of 23
    recorded production days while producing a real change on none of them —
    so it also cost an AI call every single day for nothing. Its real job,
    noticing a brand-new Gazette document, is now done properly by
    `src/discover_documents.py`, which only ever raises an alert.

None of these rows is deleted. They carry `linked_change_ids` — the history of
which changes came from where — and deleting them would throw that away. They
are instead marked `watched = 0`, which is a flag meaning "kept for history,
not checked any more". The Excel tracker's Source_Log sheet shows only
`watched = 1` rows, so after this runs that sheet finally matches its own
description.

"Migration" in this project means adding a new column with a default so old
copies of the database still open — `src/db.py` adds `watched` that way, which
is why this script calls `init_schema()` first.

SAFETY
------
  * Dry run by default: it prints what it would do and writes nothing.
  * `--apply` writes. `--db` points it at a copy so it can be proven first.
  * It never touches `provisions`, `change_log`, or any legal text.
  * It only ever sets `watched = 0` for a URL that is NOT in the live
    `SOURCES` list, so it cannot switch off a source that is genuinely being
    watched — even if this file is run twice or run after `SOURCES` changes.

Usage:
    python scripts/mark_unwatched_sources_2026-09-30.py --dry-run   (default)
    python scripts/mark_unwatched_sources_2026-09-30.py --apply
    python scripts/mark_unwatched_sources_2026-09-30.py --apply --db var/copy.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from db import DB_PATH as DEFAULT_DB_PATH, get_connection, init_schema  # noqa: E402
from fetch_sources import SOURCES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write; without this the script only reports")
    ap.add_argument("--db", default=None,
                    help="database file to work on (default: the project's own)")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else Path(DEFAULT_DB_PATH)
    if not db_path.exists():
        print(f"ERROR: no database at {db_path}")
        return 1

    print(f"Database: {db_path}")
    conn = get_connection(str(db_path))
    # Adds the `watched` column if this is an older copy. Additive only: every
    # existing row gets the default 1 ("still watched"), so nothing is lost.
    init_schema(conn)

    live_urls = {src["url"] for src in SOURCES}
    print(f"\nStill watched every day ({len(live_urls)} source(s)):")
    for url in sorted(live_urls):
        print(f"  - {url}")

    rows = conn.execute(
        "SELECT document_id, source, title, url, watched FROM source_log ORDER BY document_id"
    ).fetchall()

    to_retire = [r for r in rows if r["url"] not in live_urls and r["watched"] != 0]
    already = [r for r in rows if r["url"] not in live_urls and r["watched"] == 0]

    print(f"\n{len(rows)} row(s) in source_log.")
    if already:
        print(f"{len(already)} already marked watched = 0 — leaving alone:")
        for r in already:
            print(f"  - {r['document_id']}  {r['source']}")

    if not to_retire:
        print("\nNothing to do: every row that is no longer watched is already "
              "marked watched = 0.")
        conn.close()
        return 0

    print(f"\n{len(to_retire)} row(s) would be marked watched = 0 "
          f"(kept for history, no longer checked):")
    for r in to_retire:
        print(f"  - {r['document_id']}  {r['source']:9s}  {r['url'][:70]}")
        print(f"      {r['title']}")

    if not args.apply:
        print("\nDry run complete. Nothing was written. "
              "Re-run with --apply to write changes.")
        conn.close()
        return 0

    for r in to_retire:
        conn.execute(
            "UPDATE source_log SET watched = 0 WHERE document_id = ?",
            (r["document_id"],),
        )
    conn.commit()

    # Read back and prove it, rather than trusting that the UPDATE did what it
    # said. A script that reports success without checking is how a silent
    # failure gets in.
    still_wrong = [
        r["document_id"] for r in conn.execute(
            "SELECT document_id, url, watched FROM source_log"
        ).fetchall()
        if r["url"] not in live_urls and r["watched"] != 0
    ]
    if still_wrong:
        conn.close()
        raise RuntimeError(
            f"these rows should now be watched = 0 but are not: {still_wrong}. "
            f"Nothing else was changed; please investigate before re-running."
        )

    watched_now = conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE watched = 1"
    ).fetchone()["c"]
    print(f"\nApplied. {len(to_retire)} row(s) marked watched = 0. "
          f"source_log now reports {watched_now} watched source(s).")
    print("Next: regenerate the Excel tracker (python src/export_excel.py) so its "
          "Source_Log sheet matches. On the platform branch, do NOT commit the "
          "Excel file — the daily bot owns it.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
