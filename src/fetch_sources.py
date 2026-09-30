"""
Fetch current content from the three DPDP sources (PIB, MeitY, eGazette),
hash it, and compare against the last-seen hash in source_log to detect
change. Downstream (classify_change.py) only runs on sources that changed.

Trust order (corrected 30 Sep 2026, audit finding C-4). Only the official
MeitY PDF of an instrument may change that instrument stored text:
  - MeitY DPDP Rules PDF  -> may amend DPDPR-* rows
  - MeitY DPDP Act PDF    -> may amend DPDPA-* rows
  - PIB RSS               -> ALERT ONLY, never an applied change, no AI call
  - eGazette home page    -> RETIRED, no longer fetched here at all
The earlier wording called the eGazette home page "authoritative
confirmation". It was never that: it is a rotating list of truncated subject
lines from every ministry. See MAY_AMEND_RULES below.

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
    guessing at one. Revisited 30 Sep 2026 with a real headless browser
    (Playwright, confirmed installable/working on this project's dev
    machine) — both pages return HTTP 403 "Access Denied" even from a
    completely standard Chrome fingerprint, i.e. a WAF blocking automated
    browser traffic outright, not a missing-JavaScript problem. A genuine
    block, not pursued further per this project's rule against trying to
    get around one. See docs/detection_coverage_2026-09-30.md for the full
    account and CHANGELOG for the original 23 Sep finding.)
  - eGazette (egazette.gov.in): confirmed reachable, but its real notification
    search (SearchMenu.aspx) is a session-scoped ASP.NET form (URLs carry a
    per-session "(S(...))" token, submission is postback+viewstate, no plain
    GET/query-string search was found). That was not something to safely
    automate against a production government site without deeper, ongoing
    verification. As a stopgap we hash the public home page
    (https://egazette.gov.in/) as a coarse "did anything change" signal.
    This is weaker than the other sources — flagged here and in the
    project brief as needing follow-up once a stable search endpoint is
    confirmed. (30 Sep 2026: that follow-up happened, but not here — this
    module still only hashes the home page for its own edit-detection job.
    A separate module, src/discover_documents.py, now drives eGazette's
    real "Search by Ministry" form with a headless browser to catch
    brand-new documents — a different job from this module's "did one of
    four known URLs change" check. See that module's docstring and
    docs/detection_coverage_2026-09-30.md.)

Usage:
    python src/fetch_sources.py          # run standalone, prints what changed
    from fetch_sources import fetch_all  # used by run_pipeline.py
"""
from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass
from datetime import date

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from db import get_connection, init_schema, next_id

USER_AGENT = "Mozilla/5.0 (compatible; DPDPAChangeMonitor/1.0)"
# Bumped from 30 -> 60 seconds on 2026-09-24: egazette.gov.in was confirmed
# (by manually opening it in a browser) to be a slow-loading but genuinely
# working site, not a dead one. A 30s timeout was hitting a real, working
# page mid-load. 60s gives it room without letting one very slow source
# stall a run for an unbounded amount of time. If timeouts keep happening
# even at 60s, the next step is a short retry-with-backoff, not a further
# blind increase.
TIMEOUT = 60

# One retry, after a short pause, before calling a fetch a failure (audit
# finding M-3). e-Gazette in particular failed on roughly 30% of recorded
# production days, which made error emails routine — and a routine error email
# is one nobody reads, which is how the important one gets missed. The comment
# on TIMEOUT above already said "the next step is a short retry-with-backoff,
# not a further blind increase"; this is that step. Deliberately ONE retry: the
# job runs once a day, so a source that is genuinely down stays down, and there
# is no value in hammering a government website.
FETCH_RETRIES = 1
FETCH_RETRY_WAIT_SECONDS = 8

# ==========================================================================
# WHICH SOURCE IS ALLOWED TO CHANGE WHICH LAW  (audit finding C-4)
# ==========================================================================
# "may_amend" lists the provision_id prefixes a source is permitted to change.
# An empty list means the source can never produce an applied change at all —
# it can only raise an alert for a human to look at.
#
# Why this exists: the two verbatim checks in classify_change.py require
# new_full_text to appear in the FETCHED CONTENT. That is exactly the text
# whoever controls the page controls. So before 30 Sep 2026, any watched page
# that happened to carry something shaped like an amendment notice could have
# its wording written into the legal text — the audit demonstrated this
# end-to-end with the real production model, using a forged notice appended to
# the e-Gazette home page. The model behaved correctly; the system simply had
# no way to tell a real Gazette notification from text that merely appears on
# a Gazette web page.
#
# The rule is deliberately narrow and fails CLOSED: a URL that is not listed
# here gets an empty list, so anything added in future is alert-only until
# somebody deliberately grants it authority. It is enforced twice — in
# classify_change.classify() and again in apply_change.apply() — so a mistake
# in one place cannot undo the other.
MAY_AMEND_RULES = ["DPDPR-"]    # the DPDP Rules, 2025
MAY_AMEND_ACT = ["DPDPA-"]      # the DPDP Act, 2023
ALERT_ONLY: list[str] = []      # can never change stored legal text

SOURCES = [
    {
        "source": "PIB",
        "title": "PIB — All Press Releases RSS (English, national)",
        "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Mid=0&reg=3&lang=1",
        "kind": "rss",
        # A press release is not a legal instrument. PIB is a coincidence
        # detector: it can say that something DPDP-shaped happened, never what
        # the law now says. Alert-only, and no AI call at all — see
        # classify_change.classify().
        "may_amend": ALERT_ONLY,
    },
    {
        "source": "MeitY",
        "title": "DPDP Rules, 2025 — MeitY PDF (G.S.R. 846(E))",
        "url": "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf",
        "kind": "pdf",
        "may_amend": MAY_AMEND_RULES,
    },
    {
        "source": "MeitY",
        "title": "DPDP Act, 2023 — MeitY PDF",
        "url": "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf",
        "kind": "pdf",
        "may_amend": MAY_AMEND_ACT,
    },
]

# Retired 30 Sep 2026 (audit findings C-4 and M-4). The e-Gazette home page is
# no longer fetched or classified here. Reasons, in order of weight:
#   1. Its content could reach provisions.full_text, and it is the one source
#      whose TLS certificate this code could not verify (see _fetch_raw).
#   2. It changed on 20 of 23 recorded production runs and produced a real
#      change on none of them — a 100% false-positive rate that also cost an
#      AI call every single day.
#   3. Its real job — noticing a brand-new Gazette document — is now done
#      properly by src/discover_documents.py, which drives e-Gazette own
#      "Search by Ministry" form and only ever raises an alert.
# The row stays in source_log (it carries linked_change_ids history); the
# one-off script scripts/mark_unwatched_sources_2026-09-30.py sets its
# watched flag to 0 so it stops appearing as "being watched right now".
RETIRED_SOURCES = [
    {
        "source": "eGazette",
        "title": "eGazette — Home (RETIRED 30 Sep 2026; replaced by discover_documents.py)",
        "url": "https://egazette.gov.in/",
        "kind": "html",
        "may_amend": ALERT_ONLY,
    },
]

# Everything this project has ever watched, for authority lookups only. Never
# iterated for fetching — only SOURCES is.
ALL_KNOWN_SOURCES = SOURCES + RETIRED_SOURCES


def may_amend(url: str) -> list[str]:
    """
    Which provision_id prefixes the source at `url` is allowed to change.
    Fails closed: an unknown URL gets an empty list, i.e. alert-only.
    """
    for src in ALL_KNOWN_SOURCES:
        if src["url"] == url:
            return list(src.get("may_amend") or [])
    return []


def is_authorised(url: str, provision_id: str) -> bool:
    """True only if the source at `url` may change `provision_id`."""
    return any((provision_id or "").startswith(prefix) for prefix in may_amend(url))


def authority_refusal(url: str, source: str, provision_id: str) -> str:
    """The one plain-language sentence used wherever a refusal is reported."""
    allowed = may_amend(url)
    allowed_text = ", ".join(f"{prefix}*" for prefix in allowed) if allowed else "nothing at all"
    return (
        f"REFUSED: {source} ({url}) is not allowed to change {provision_id}. "
        f"That source may change {allowed_text}. This is the source-authority rule "
        f"(audit finding C-4): a change is only trusted when it comes from the official "
        f"document for that instrument, not from any page that happens to mention it. "
        f"Nothing was written. Please check the source by hand."
    )


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
    # TLS certificate checking is ON for every source here, with no exception
    # (audit finding C-4). Until 30 Sep 2026 this function passed
    # verify=False for egazette.gov.in, whose certificate chains to a root
    # Windows trusts but the certifi bundle does not. That was the one source
    # whose text could reach provisions.full_text without being
    # authenticated. It is no longer fetched here at all (see
    # RETIRED_SOURCES), so the exception is simply gone. If a future source
    # has the same certificate problem, supply the missing root CA
    # explicitly — verify="certs/<name>.pem" — rather than switching
    # verification off.
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _fetch_and_extract(url: str, kind: str) -> tuple[str, str]:
    """
    Download and extract one source's text, retrying once after a short pause.
    Returns (text, sha256-of-text). Raises the LAST exception if every attempt
    failed, so the caller still reports a real failure.
    """
    last_error: Exception | None = None
    for attempt in range(FETCH_RETRIES + 1):
        try:
            text = _extract_text(_fetch_raw(url), kind)
            # Hash the extracted/cleaned text, not raw bytes — raw PDF bytes
            # and raw HTML can churn from irrelevant noise (PDF regeneration
            # metadata, analytics script tokens) even when the substantive
            # content is unchanged.
            return text, hashlib.sha256(text.encode("utf-8")).hexdigest()
        except Exception as exc:
            last_error = exc
            if attempt < FETCH_RETRIES:
                print(f"[fetch_sources] attempt {attempt + 1} failed for {url} ({exc}); "
                      f"waiting {FETCH_RETRY_WAIT_SECONDS}s and trying once more.")
                time.sleep(FETCH_RETRY_WAIT_SECONDS)
    raise last_error


def _error_signature(url: str, exc: Exception) -> str:
    """
    A short, stable label for "this same problem again": the source and the kind
    of failure, never the full message (which often carries a changing timestamp
    or port number and would make every day look like a brand-new problem).
    """
    return f"{url}|{type(exc).__name__}"


def _record_error_streak(conn, document_id: str, signature: str, today: str) -> int:
    """
    Count how many consecutive DAYS this same problem has happened, and return
    that count. 1 means "new today". Two runs on the same day do not count twice.
    """
    row = conn.execute(
        "SELECT error_signature, error_streak_days, error_streak_last_date "
        "FROM source_log WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        days = 1
    elif row["error_signature"] != signature:
        days = 1                      # a different problem: start counting again
    elif row["error_streak_last_date"] == today:
        days = row["error_streak_days"] or 1    # already counted today
    else:
        days = (row["error_streak_days"] or 0) + 1
    conn.execute(
        "UPDATE source_log SET error_signature = ?, error_streak_days = ?, "
        "error_streak_last_date = ? WHERE document_id = ?",
        (signature, days, today, document_id),
    )
    conn.commit()
    return days


def _clear_error_streak(conn, document_id: str) -> None:
    conn.execute(
        "UPDATE source_log SET error_signature = NULL, error_streak_days = 0, "
        "error_streak_last_date = NULL WHERE document_id = ?",
        (document_id,),
    )
    conn.commit()


def _existing_row(conn, url: str):
    return conn.execute(
        "SELECT document_id, content_hash FROM source_log WHERE url = ?", (url,)
    ).fetchone()


def _upsert_source_log(conn, *, url, source, title, published_date, fetched_date,
                        content_hash, processing_status, content_text=None) -> str:
    """
    source_log.url is UNIQUE (one row per source URL, not a per-fetch
    history) — update the existing row for this URL if there is one,
    otherwise insert a new one.

    When a row is INSERTED for the first time and we have the text in hand,
    the matching source_snapshot row is written in the same step (audit
    finding C-3). A "snapshot" is simply the text as we last saw it, and it
    is what classify_change.py diffs the next fetch against. Before this
    fix, the snapshot was only created the first time a source's content
    CHANGED — and because classify_change.py treats "no snapshot" as "first
    sighting, store it and report nothing", the first real change to a
    source added to source_log outside a classify() run was stored as the
    new baseline and never reported. SRC-0001 (the DPDP Rules PDF) was in
    exactly that state, so its next amendment was guaranteed to be lost.
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
        if content_text is not None:
            # Same transaction as the INSERT above, so a source can never
            # exist in source_log without a diff baseline. Not written on the
            # fetch-failure path, where content_text is None (there is no
            # text to snapshot, and pretending otherwise would bake a
            # failure in as the baseline).
            conn.execute(
                "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(document_id) DO NOTHING",
                (doc_id, content_hash, content_text, fetched_date),
            )
    conn.commit()
    return doc_id


def fetch_all(conn=None, fetch_errors: list[str] | None = None,
              repeated_errors: list[str] | None = None) -> list[FetchResult]:
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
            text, content_hash = _fetch_and_extract(url, src["kind"])
        except Exception as exc:
            # Keep the last good hash on a fetch failure, don't blank it —
            # writing NULL here made the *next successful* fetch look like a
            # "change" and re-trigger classification of content that never
            # actually changed.
            existing_before_error = _existing_row(conn, url)
            last_good_hash = existing_before_error["content_hash"] if existing_before_error else None
            doc_id = _upsert_source_log(
                conn, url=url, source=src["source"], title=src["title"],
                published_date=None, fetched_date=today,
                content_hash=last_good_hash, processing_status="Error",
            )
            days = _record_error_streak(conn, doc_id, _error_signature(url, exc), today)
            print(f"[fetch_sources] ERROR fetching {src['source']} ({url}): {exc} "
                  f"(day {days} of this same problem)")
            if fetch_errors is not None:
                suffix = f" [same problem for {days} days running]" if days > 1 else ""
                message = f"fetch failed for {src['source']} ({url}): {exc}{suffix}"
                fetch_errors.append(message)
                # Day 1 is news. Day 3 and beyond is news again, because by then
                # it is not going to fix itself. Days in between are still in the
                # email body, just not shouted about on the subject line
                # (audit M-3).
                if repeated_errors is not None and 1 < days < 3:
                    repeated_errors.append(message)
            continue

        existing = _existing_row(conn, url)
        prior_hash = existing["content_hash"] if existing else None
        is_changed = prior_hash != content_hash

        doc_id = _upsert_source_log(
            conn, url=url, source=src["source"], title=src["title"],
            published_date=None, fetched_date=today,
            content_hash=content_hash,
            processing_status="New" if is_changed else "No Change Detected",
            content_text=text,
        )
        _clear_error_streak(conn, doc_id)

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
