"""
One-off data script (30 Sep 2026 audit fixes, finding C-3).

WHAT WENT WRONG, IN PLAIN WORDS
-------------------------------
The daily check does not send a whole document to the AI. It keeps a copy of
each page's text from the last time it looked ("the baseline", stored in the
`source_snapshot` table), compares today's text against that copy, and sends
only the lines that differ. That keeps the AI cost down and makes the result
easier to check.

Three of the watched sources had a baseline. **SRC-0001 — the DPDP Rules 2025
PDF, the single most important document this project tracks — did not.** It had
a fingerprint in `source_log` (so the project knew what the PDF looked like last
time) but no stored text to diff against.

Before 30 Sep 2026 that combination was silently harmless-looking and actually
dangerous: the moment MeitY published an amended Rules PDF, the code would have
found no baseline, decided "this must be the first time I have seen this page",
stored the amended text as the new baseline, made no AI call, and reported **"No
change detected"**. The real amendment would then never be noticed again, because
from the next run onward the amended text *is* the baseline. A regulatory-change
tracker would have missed the exact event it exists to catch, and the daily email
would have looked completely normal.

The code fix (in `src/fetch_sources.py` and `src/classify_change.py`) does two
things: a baseline is now written at the same moment a source is first recorded,
and a source that has history but no baseline is now treated as a data-integrity
fault — it raises an error naming this script instead of quietly moving on.
This script is the other half: it creates the missing baseline.

WHY THIS CANNOT JUST STORE TODAY'S TEXT
---------------------------------------
Storing today's text blindly is exactly the bug. If the PDF has *already*
changed since the last recorded fetch, today's text contains the amendment, and
storing it as "what it looked like before" would hide that amendment for good.

So this script refuses to guess. It fetches the document and compares its
fingerprint with the one already in `source_log`:

  * **Fingerprints match** — the document has not changed since the project last
    looked. Today's text is therefore genuinely the same text the missing
    baseline would have held, and it is safe to store. This is the expected case.
  * **Fingerprints differ** — the document HAS changed and nobody has classified
    that change. Writing a baseline now would bury it. The script refuses, says
    so plainly, and tells you what to do instead.

This script needs the internet (it fetches the real document), which is why it
is run by hand rather than being part of the daily job.

SAFETY
------
  * Dry run by default: it fetches and reports, and writes nothing.
  * `--apply` writes. `--db` points it at a copy so it can be proven first.
  * It only ever INSERTs a missing `source_snapshot` row. It never overwrites an
    existing baseline, never touches `provisions`, `change_log`, or any legal
    text, and never changes a fingerprint in `source_log`.

Usage:
    python scripts/backfill_source_snapshots_2026-09-30.py --dry-run   (default)
    python scripts/backfill_source_snapshots_2026-09-30.py --apply
    python scripts/backfill_source_snapshots_2026-09-30.py --apply --db var/copy.db
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from db import DB_PATH as DEFAULT_DB_PATH, get_connection, init_schema  # noqa: E402
from fetch_sources import SOURCES, _fetch_and_extract  # noqa: E402


def _missing_baselines(conn) -> list[dict]:
    """
    Sources that have history in `source_log` (a fingerprint from a past fetch)
    but no row in `source_snapshot`. These are the data-integrity fault C-3
    describes. A source with no fingerprint at all has genuinely never been
    fetched, and the ordinary daily run captures its baseline correctly — those
    are deliberately left alone.
    """
    by_url = {src["url"]: src for src in SOURCES}
    out = []
    rows = conn.execute(
        "SELECT s.document_id, s.source, s.url, s.content_hash, s.fetched_date "
        "FROM source_log s "
        "LEFT JOIN source_snapshot snap ON snap.document_id = s.document_id "
        "WHERE snap.document_id IS NULL ORDER BY s.document_id"
    ).fetchall()
    for r in rows:
        if r["url"] not in by_url:
            # Not watched any more (a retired page, a one-off PDF). It will
            # never be classified again, so it needs no baseline.
            continue
        if not r["content_hash"]:
            continue
        out.append({
            "document_id": r["document_id"],
            "source": r["source"],
            "url": r["url"],
            "kind": by_url[r["url"]]["kind"],
            "stored_hash": r["content_hash"],
            "fetched_date": r["fetched_date"],
        })
    return out


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
    init_schema(conn)

    missing = _missing_baselines(conn)
    if not missing:
        print("\nNothing to do: every watched source with history already has a "
              "baseline in source_snapshot.")
        conn.close()
        return 0

    print(f"\n{len(missing)} watched source(s) have history but no baseline:")
    for m in missing:
        print(f"  - {m['document_id']}  {m['source']}  {m['url'][:70]}")
        print(f"      last recorded fetch {m['fetched_date']}, "
              f"fingerprint {m['stored_hash'][:12]}...")

    today = date.today().isoformat()
    ready: list[tuple[dict, str, str]] = []
    blocked: list[str] = []

    for m in missing:
        print(f"\nFetching {m['document_id']} ({m['url']}) ...")
        # Deliberately NOT wrapped in a catch-all: if the fetch fails, this
        # script must stop with a real error rather than report a partial
        # success (the project's no-silent-failures rule).
        content_text, content_hash = _fetch_and_extract(m["url"], m["kind"])
        print(f"  fetched {len(content_text):,} characters, "
              f"fingerprint {content_hash[:12]}...")

        if content_hash == m["stored_hash"]:
            print("  MATCHES the recorded fingerprint — the document has not changed "
                  "since the project last looked, so this text is a safe baseline.")
            ready.append((m, content_text, content_hash))
        else:
            msg = (
                f"{m['document_id']} ({m['source']} — {m['url']}): the document has "
                f"CHANGED since the last recorded fetch on {m['fetched_date']} "
                f"(recorded fingerprint {m['stored_hash'][:12]}..., fetched today "
                f"{content_hash[:12]}...). A baseline was NOT written, on purpose: "
                f"storing today's text as 'what it looked like before' would hide that "
                f"change permanently, which is the very problem this script exists to "
                f"repair. What to do instead: compare the live document with the copies "
                f"in docs/full_text/ by hand, decide whether the difference is a real "
                f"amendment, and if it is, apply it the way the December 2025 "
                f"corrigendum was applied (a reviewed one-off script), then re-run this."
            )
            print(f"  REFUSED. {msg}")
            blocked.append(msg)

    if not args.apply:
        print(f"\nDry run complete. Nothing was written. "
              f"{len(ready)} baseline(s) would be created, {len(blocked)} refused. "
              f"Re-run with --apply to write.")
        conn.close()
        return 1 if blocked else 0

    for m, content_text, content_hash in ready:
        conn.execute(
            "INSERT INTO source_snapshot (document_id, content_hash, content_text, "
            "fetched_date) VALUES (?, ?, ?, ?)",
            (m["document_id"], content_hash, content_text, today),
        )
    conn.commit()

    # Prove it, rather than trusting the INSERT.
    for m, _text, content_hash in ready:
        row = conn.execute(
            "SELECT content_hash FROM source_snapshot WHERE document_id = ?",
            (m["document_id"],),
        ).fetchone()
        if not row or row["content_hash"] != content_hash:
            conn.close()
            raise RuntimeError(
                f"baseline for {m['document_id']} was not stored correctly. "
                f"Please investigate before re-running."
            )
        print(f"Baseline written for {m['document_id']}.")

    remaining = _missing_baselines(conn)
    print(f"\nApplied. {len(ready)} baseline(s) created; "
          f"{len(remaining)} watched source(s) still without one.")
    if blocked:
        print("\nSTILL NEEDS YOUR ATTENTION — these were refused, see above:")
        for msg in blocked:
            print(f"  - {msg}")
    conn.close()
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
