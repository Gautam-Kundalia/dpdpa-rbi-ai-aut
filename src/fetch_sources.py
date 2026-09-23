"""
Fetch current content from the three DPDP sources (PIB, MeitY, eGazette),
hash it, and compare against the last-seen hash in source_log to detect
change. Downstream (classify_change.py) only runs on sources that changed.

Trust order: PIB (early-warning trigger) -> MeitY (working copy) ->
eGazette (authoritative confirmation).

Source endpoints, and why:
  - PIB: https://www.pib.gov.in/RssMain.aspx?ModId=6&Mid=0&reg=3&lang=1 —
    PIB's own "all releases" RSS feed, explicitly parameterised to English
    (lang=1) and PIB Delhi/national (reg=3). Confirmed by hand: a plain GET
    (no cookies, no session) returns real XML with English press-release
    titles. This replaced the earlier approach of hashing the allRel.aspx
    HTML listing — the audit found that page can silently serve Hindi
    depending on the client's apparent locale/language, with no way to
    confirm from outside what language GitHub Actions' server would see;
    lang=1 on the RSS feed removes that ambiguity by making the language an
    explicit request parameter instead of an inferred default. Structured
    titles are also easier for the classifier to work with than scraped
    page text. PIB's per-ministry filter (a separate, older ASP.NET
    postback form) still has no stable GET/query-string form, so this
    feed — like the old page — covers all ministries; classify_change.py's
    keyword pre-filter is what decides DPDP relevance, same as before.
  - MeitY: the two known static PDF paths (Rules, Act) already used by the
    seed scripts. These are direct file URLs — the most reliable of the
    three sources. (23 Sep 2026: looked for a MeitY page listing DPDP
    documents to watch for new notifications/corrigenda, per the audit's
    §1.4 finding that new Gazette notices aren't visible to any current
    source. Two candidates — meity.gov.in/data-protection-framework and
    meity.gov.in/documents/act-and-policies — both confirmed to list DPDP
    documents, but both are Next.js single-page apps: a plain GET returns
    only a ~3KB script-loading shell with no document data, and the
    Next.js /_next/data/<buildId>/*.json pattern also returns that same
    shell rather than real JSON, meaning the document list is fetched
    client-side by JS after page load, not by any request this pipeline
    can make. No stable GET-able endpoint found within the 45-minute
    time-box for this; not adding either page as a source rather than
    guessing at one. See CHANGELOG for the full account.)
  - eGazette (egazette.gov.in): confirmed reachable, but its real notification
    search (SearchMenu.aspx) is a session-scoped ASP.NET form (URLs carry a
    per-session "(S(...))" token, submission is postback+viewstate, no plain
    GET/query-string search was found). That was not something to safely
    automate against a production government site without deeper, ongoing
    verification. As a stopgap we hash the public home page
    (https://egazette.gov.in/) as a coarse "did anything change" signal.
    This is weaker than the other sources — flagged here and in the
    project brief as needing follow-up once a stable search endpoint is
    confirmed.

Usage:
    python src/fetch_sources.py          # run standalone, prints what changed
    from fetch_sources import fetch_all  # used by run_pipeline.py
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import date

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from db import get_connection, init_schema, next_id

USER_AGENT = "Mozilla/5.0 (compatible; DPDPAChangeMonitor/1.0)"
TIMEOUT = 30

SOURCES = [
    {
        "source": "PIB",
        "title": "PIB — All Press Releases RSS (English, national)",
        "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Mid=0&reg=3&lang=1",
        "kind": "rss",
    },
    {
        "source": "MeitY",
        "title": "DPDP Rules, 2025 — MeitY PDF (G.S.R. 846(E))",
        "url": "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf",
        "kind": "pdf",
    },
    {
        "source": "MeitY",
        "title": "DPDP Act, 2023 — MeitY PDF",
        "url": "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf",
        "kind": "pdf",
    },
    {
        "source": "eGazette",
        "title": "eGazette — Home (best-effort; no stable search endpoint confirmed)",
        "url": "https://egazette.gov.in/",
        "kind": "html",
    },
]


@dataclass
class FetchResult:
    source: str
    title: str
    url: str
    document_id: str
    content_text: str
    content_hash: str
    changed: bool
    prior_hash: str | None = None  # restored by run_pipeline if classification fails,
                                    # so the change is retried next run instead of lost


def _extract_text(raw: bytes, kind: str) -> str:
    if kind == "pdf":
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if kind == "rss":
        soup = BeautifulSoup(raw, "xml")
        # Only the per-release <title> text — not <link> (a PRID isn't
        # useful signal by itself) and not the channel-level title/
        # description (constant, would never change and adds nothing).
        return "\n".join(item.title.get_text(strip=True) for item in soup.find_all("item") if item.title)
    soup = BeautifulSoup(raw, "html.parser")
    # Strip <script>/<style> — analytics/tracking snippets embed request-
    # specific tokens that change on every fetch, which would make the
    # content hash flap on pure noise instead of real page-content changes.
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _fetch_raw(url: str) -> bytes:
    # egazette.gov.in serves a cert chain that Windows trusts (via its own
    # cert store) but that certifi's CA bundle does not — verified by hand
    # via a raw TLS handshake (hostname matches, no MITM indication). It's
    # public, read-only gazette content with no credentials involved, so we
    # skip verification for this one known-problematic host rather than
    # weakening TLS checks for every source.
    verify = "egazette.gov.in" not in url
    if not verify:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, verify=verify)
    resp.raise_for_status()
    return resp.content


def _existing_row(conn, url: str):
    return conn.execute(
        "SELECT document_id, content_hash FROM source_log WHERE url = ?", (url,)
    ).fetchone()


def _upsert_source_log(conn, *, url, source, title, published_date, fetched_date,
                        content_hash, processing_status) -> str:
    """
    source_log.url is UNIQUE (one row per source URL, not a per-fetch
    history) — update the existing row for this URL if there is one,
    otherwise insert a new one.
    """
    existing = _existing_row(conn, url)
    if existing:
        doc_id = existing["document_id"]
        conn.execute(
            """UPDATE source_log
               SET source = ?, title = ?, published_date = ?, fetched_date = ?,
                   content_hash = ?, processing_status = ?
               WHERE document_id = ?""",
            (source, title, published_date, fetched_date, content_hash, processing_status, doc_id),
        )
    else:
        doc_id = next_id(conn, "source_log", "document_id", "SRC")
        conn.execute(
            """INSERT INTO source_log
               (document_id, source, title, url, published_date, fetched_date,
                content_hash, processing_status, linked_change_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (doc_id, source, title, url, published_date, fetched_date, content_hash, processing_status),
        )
    conn.commit()
    return doc_id


def fetch_all(conn=None, fetch_errors: list[str] | None = None) -> list[FetchResult]:
    """
    Fetch every configured source. For each: hash it, compare to the last
    known hash for that URL, and insert a source_log row.

    Returns only the sources whose content changed (or were seen for the
    first time) — these are the ones classify_change.py should look at.
    Sources that failed to fetch get processing_status='Error' and are
    skipped (not included in the return list); one source's fetch failure
    must not block the others. If `fetch_errors` is passed, each download
    failure is appended to it so run_pipeline.py's exit code and email
    reflect the failure (previously these were silent: printed but never
    surfaced, so a broken source could fail for days with a green run).
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
        init_schema(conn)

    changed: list[FetchResult] = []
    today = date.today().isoformat()

    for src in SOURCES:
        url = src["url"]
        try:
            raw = _fetch_raw(url)
            text = _extract_text(raw, src["kind"])
            # Hash the extracted/cleaned text, not raw bytes — raw PDF bytes
            # and raw HTML can churn from irrelevant noise (PDF regeneration
            # metadata, analytics script tokens) even when the substantive
            # content is unchanged.
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except Exception as exc:
            # Keep the last good hash on a fetch failure, don't blank it —
            # writing NULL here made the *next successful* fetch look like a
            # "change" and re-trigger classification of content that never
            # actually changed.
            existing_before_error = _existing_row(conn, url)
            last_good_hash = existing_before_error["content_hash"] if existing_before_error else None
            _upsert_source_log(
                conn, url=url, source=src["source"], title=src["title"],
                published_date=None, fetched_date=today,
                content_hash=last_good_hash, processing_status="Error",
            )
            print(f"[fetch_sources] ERROR fetching {src['source']} ({url}): {exc}")
            if fetch_errors is not None:
                fetch_errors.append(f"fetch failed for {src['source']} ({url}): {exc}")
            continue

        existing = _existing_row(conn, url)
        prior_hash = existing["content_hash"] if existing else None
        is_changed = prior_hash != content_hash

        doc_id = _upsert_source_log(
            conn, url=url, source=src["source"], title=src["title"],
            published_date=None, fetched_date=today,
            content_hash=content_hash,
            processing_status="New" if is_changed else "No Change Detected",
        )

        if is_changed:
            changed.append(
                FetchResult(
                    source=src["source"],
                    title=src["title"],
                    url=url,
                    document_id=doc_id,
                    content_text=text,
                    content_hash=content_hash,
                    changed=True,
                    prior_hash=prior_hash,
                )
            )
        print(
            f"[fetch_sources] {src['source']}: {'CHANGED' if is_changed else 'no change'} "
            f"({url}) -> {doc_id}"
        )

    if owns_conn:
        conn.close()

    return changed


if __name__ == "__main__":
    results = fetch_all()
    if results:
        print(f"\n{len(results)} source(s) changed:")
        for r in results:
            print(f"  - {r.source}: {r.title} ({r.document_id})")
    else:
        print("\nNo source changes detected.")
