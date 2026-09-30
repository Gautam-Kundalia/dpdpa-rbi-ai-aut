"""
Document discovery — watches pages that LIST government documents (as opposed
to fetch_sources.py, which only re-checks four fixed URLs for edits) and
emails an alert when a brand-new DPDP-related document appears.

Why this exists, in plain words: Indian law changes are published as
brand-new, separate documents — never as silent edits to an old PDF. The
December 2025 corrigendum (G.S.R. 892(E)) fixing typos in the DPDP Rules is a
real example: it is its own document, and the original Rules PDF was never
touched. fetch_sources.py, which only re-hashes four known URLs, would never
have noticed it. This module fills that gap by watching pages that list
documents, remembering what has already been seen (discovered_documents),
and alerting on anything new.

ALERT-ONLY: this module never touches provisions or change_log. A brand-new
document has no prior version to diff against, and this project's rule that
legal text must come from a PDF through code (never typed or guessed) means a
human has to decide what, if anything, to apply — see scripts/ for the
one-off scripts that do that by hand, e.g. scripts/apply_rules_corrigendum_
2026-09-23.py.

NO AI: everything here is keyword matching and reading the first few pages of
a PDF with pypdf. Tests must never call the Anthropic API.

Sources (see docs/detection_coverage_2026-09-30.md for how each was found,
and what was tried and ruled out):
  - eGazette's "Search by Ministry" form, filtered to the Ministry of
    Electronics and Information Technology. This is a stateful ASP.NET web
    form (dropdown picks trigger a page reload each), so it's driven with
    Playwright (a real, invisible Chrome browser) rather than a plain HTTP
    request — confirmed to have no CAPTCHA anywhere in the flow. The search
    itself is scoped to one calendar month at a time, so this module queries
    the current month and the previous one every run (a rolling ~2-month
    window) — see the canary note below for why. Once a document's Gazette
    ID is known, its PDF lives at a permanent, session-free URL
    (https://egazette.gov.in/WriteReadData/<year>/<numeric id>.pdf) that a
    plain `requests.get` can fetch directly — no browser needed for that
    part. This is NOT "all items relevant": the Ministry publishes plenty of
    non-DPDP notices (e.g. a Hindi Advisory Committee resolution) alongside
    real DPDP ones, so keyword matching still decides what alerts.
  - MeitY's two document-list pages (data-protection-framework,
    documents/act-and-policies) were investigated and are NOT included here:
    a plain request gets a content-free JavaScript-shell page, and a real
    headless browser gets blocked outright (HTTP 403) by the site's own
    bot-detection — a genuine block, not something this project tries to
    get around. See the findings doc for the full account.

Canary (a tripwire that tells us the detector itself broke): eGazette's
search is month-scoped, so "0 items" is completely normal on the 1st of a
new month (nothing has been published yet) — comparing that against a
half-full previous month would falsely fire every month. To avoid that, this
module logs one discovery_run_log row PER MONTH QUERIED (the discovery_source
column holds a bucket key like 'egazette-meity:2026-09', not just the plain
source name), and only compares a month's count against that SAME month's
own most recent prior count — never across different months. A month with no
prior count yet (first time it's ever been queried, or its only prior count
was itself 0) is never flagged; a month whose count drops to 0 or below half
of its own last known count is.

Usage:
    from discover_documents import discover_all
    new_documents, baseline_notes = discover_all(conn, errors)

    # standalone, read-only preview against a COPY of the database:
    python src/discover_documents.py --dry-run --db var/db_copy.db
"""
from __future__ import annotations

import calendar
import io
import re
from datetime import date, datetime
from pathlib import Path

import requests
from pypdf import PdfReader

from classify_change import _is_mostly_hindi
from db import PROJECT_ROOT

USER_AGENT = "Mozilla/5.0 (compatible; DPDPAChangeMonitor/1.0)"

MAX_PDF_BYTES = 15 * 1024 * 1024
PDF_TIMEOUT = 60

EGAZETTE_MINISTRY_LABEL = "Ministry of Electronics and Information Technology"
EGAZETTE_BASE = "https://egazette.gov.in"

# egazette.gov.in is a genuinely slow-loading site — fetch_sources.py already
# bumped its own plain-HTTP timeout 30s -> 60s for this exact reason (see its
# TIMEOUT constant). Confirmed the hard way here too: a real production run
# on GitHub Actions timed out at the default 30s navigating to the home page,
# even though the same steps ran in a few seconds locally — a slower or
# colder network path from the CI runner, not a broken page. 60s mirrors
# fetch_sources.py's own number rather than picking a new one.
EGAZETTE_TIMEOUT_MS = 60_000

# A pause between months when the search window has been widened after an
# outage (audit finding M-12). Twelve months in a row is twelve form
# submissions against a government website; spacing them out is basic manners
# and keeps the load indistinguishable from a person clicking through.
EGAZETTE_MONTH_PAUSE_MS = 2_000

# The results page prints its own count, e.g. "Total No. of Gazettes : 5".
# Cross-checking the rows we scraped against that number is what turns a
# silently half-scraped page into a loud failure (audit finding M-6).
EGAZETTE_RESULT_COUNT_RE = re.compile(r"(\d+)")

# How stale the last successful discovery run has to be before the search
# window is widened from "this month and last month" to "everything since then"
# (audit finding M-12). 25 days rather than 30: the window is month-scoped, so
# by day 25 of an outage there is already a real chance a whole month has
# fallen out of it.
DISCOVERY_STALE_DAYS = 25

# Never search more than this many months in one run, however long the outage.
DISCOVERY_MAX_MONTHS = 12

# Case-insensitive; err on the side of too many alerts (a human reviews every
# alert — nothing here writes to the tracked database on its own).
KEYWORDS = [
    "data protection", "DPDP", "digital personal data", "personal data",
    "data fiduciary", "data principal", "G.S.R. 846", "G.S.R. 843",
    "corrigend", "consent manager", "Data Protection Board",
]

GAZETTE_ID_RE = re.compile(r"CG-DL-[A-Z]-(\d{2})(\d{2})(\d{4})-(\d+)")

# Stored in discovered_documents.text_excerpt for a new document whose PDF
# couldn't be downloaded/read, instead of a real excerpt (there is no
# separate "unreadable" column in the given schema). Used both to display
# "could not be read" instead of a snippet, and — on a retry after a failed
# email send — to tell an unreadable-but-relevant row apart from a
# perfectly-readable row that just never matched any keyword (both have no
# matched_keywords; only the marker says the first one was still meant to
# be alerted).
UNREADABLE_MARKER = "[could not be read]"


# --------------------------------------------------------------------------
# Keyword matching / PDF reading (shared by every source)
# --------------------------------------------------------------------------

def _match_keywords(*texts: str | None) -> list[str]:
    haystack = " ".join(t for t in texts if t).lower()
    return [kw for kw in KEYWORDS if kw.lower() in haystack]


# Trust file for egazette.gov.in (audit finding C-4, 30 Sep 2026).
#
# The old comment here — and the README, and the audit — said the site chains
# to a root that Windows trusts and certifi does not. That was measured on
# 30 Sep 2026 and is NOT what is wrong. The site now uses a Let's Encrypt
# certificate, and the actual fault is that the server does not send its
# INTERMEDIATE certificate at all. Windows copes because it silently fetches
# the missing intermediate itself; OpenSSL (which Python uses) does not, and
# reports "unable to get local issuer certificate".
#
# certs/egazette-chain.pem supplies the missing links, each one checked
# offline against certifi's own ISRG Root X1 before it was committed. See
# certs/README.md for the fingerprints and how to refresh it.
EGAZETTE_CHAIN_PEM = PROJECT_ROOT / "certs" / "egazette-chain.pem"


def _verify_arg(url: str):
    """What to pass to requests' verify= for this URL."""
    if "egazette.gov.in" in url and EGAZETTE_CHAIN_PEM.exists():
        return str(EGAZETTE_CHAIN_PEM)
    return True


def _download_pdf_bytes(url: str, tls_warnings: list[str] | None = None) -> bytes:
    """
    Download a PDF with TLS certificate checking ON.

    If the check fails for egazette.gov.in — which will happen the day Let's
    Encrypt issues that site's certificate from a different intermediate than
    the one pinned in certs/egazette-chain.pem — the download is retried
    unverified AND a warning is recorded, because this whole module is
    alert-only: it never writes to provisions or change_log, it only emails a
    link for a human to open. Losing the alert entirely would be worse than an
    unverified read of a public PDF. The warning is never swallowed: it goes
    into the run's error list and therefore into the email.
    """
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=PDF_TIMEOUT,
            verify=_verify_arg(url), stream=True,
        )
    except requests.exceptions.SSLError as exc:
        warning = (
            f"TLS certificate check FAILED for {url} ({exc}). Read it anyway, "
            f"unverified, because document discovery only ever raises an alert for a "
            f"human — but the excerpt below is NOT authenticated, so open the link "
            f"yourself. Fix: the pinned chain in certs/egazette-chain.pem is out of "
            f"date — see certs/README.md."
        )
        print(f"[discover_documents] WARNING: {warning}")
        if tls_warnings is not None:
            tls_warnings.append(warning)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=PDF_TIMEOUT,
            verify=False, stream=True,
        )
    resp.raise_for_status()
    content = resp.raw.read(MAX_PDF_BYTES + 1, decode_content=True)
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"PDF at {url} exceeds the {MAX_PDF_BYTES}-byte cap — refusing to read further")
    return content


def _extract_pdf_text(raw: bytes, max_pages: int = 3) -> str:
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])


def _english_excerpt(text: str, limit: int = 600) -> str:
    """First ~600 chars of the non-Hindi lines — reuses classify_change.py's
    Devanagari-share check so Gazette PDFs' bilingual text doesn't leave an
    unreadable Hindi excerpt in an email."""
    kept = [ln for ln in text.splitlines() if ln.strip() and not _is_mostly_hindi(ln)]
    return "\n".join(kept).strip()[:limit]


# --------------------------------------------------------------------------
# eGazette — "Search by Ministry" (Playwright; see module docstring)
# --------------------------------------------------------------------------

def _egazette_pdf_url(gazette_id: str) -> str | None:
    """'CG-DL-E-12122025-268455' -> 'https://egazette.gov.in/WriteReadData/2025/268455.pdf'.
    Verified against three independent real rows (see the findings doc)."""
    m = GAZETTE_ID_RE.match((gazette_id or "").strip())
    if not m:
        return None
    _day, _month, year, num = m.groups()
    return f"{EGAZETTE_BASE}/WriteReadData/{year}/{num}.pdf"


def _parse_egazette_date(text: str | None) -> str | None:
    """'11-Dec-2025' -> '2025-12-11'. Returns None if unparseable rather than
    raising — a bad date on one row must not lose the whole listing."""
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _current_and_previous_month(today: date) -> list[tuple[int, int, str]]:
    """[(year, month_number, month_name), ...] for today's month and the one
    before it — the rolling window this search covers on an ordinary day."""
    months = [(today.year, today.month)]
    prev_month = today.month - 1 or 12
    prev_year = today.year if today.month > 1 else today.year - 1
    months.append((prev_year, prev_month))
    return [(y, m, calendar.month_name[m]) for y, m in months]


def _months_between(start: date, end: date) -> list[tuple[int, int, str]]:
    """Every calendar month from `start` to `end` inclusive, oldest first."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month, calendar.month_name[month]))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def _last_successful_run(conn, source_name: str) -> date | None:
    """
    The most recent date this discovery source ran at all, from
    discovery_run_log. Returns None if it has never run.
    """
    if conn is None:
        return None
    row = conn.execute(
        "SELECT MAX(run_date) d FROM discovery_run_log WHERE discovery_source LIKE ?",
        (f"{source_name}%",),
    ).fetchone()
    if not row or not row["d"]:
        return None
    try:
        return datetime.strptime(row["d"], "%Y-%m-%d").date()
    except ValueError:
        return None


def _months_to_search(conn, today: date, source_name: str,
                      warnings: list[str] | None = None) -> list[tuple[int, int, str]]:
    """
    Which months to search this run.

    Normally the current month and the previous one, which is the widest
    window a two-month rolling search can cover. But this search is
    MONTH-SCOPED: if the job has not run for longer than a month, whole months
    have fallen out of that window and their documents would be missed
    permanently — there is no later run that ever looks at them again (audit
    finding M-12). So after an outage of more than DISCOVERY_STALE_DAYS the
    window is widened to cover everything since the last successful run,
    capped at DISCOVERY_MAX_MONTHS so a very long gap cannot turn into an
    unbounded crawl. Widening is always reported.
    """
    last_run = _last_successful_run(conn, source_name)
    if last_run is None:
        return _current_and_previous_month(today)

    gap_days = (today - last_run).days
    if gap_days <= DISCOVERY_STALE_DAYS:
        return _current_and_previous_month(today)

    months = _months_between(last_run, today)
    capped = False
    if len(months) > DISCOVERY_MAX_MONTHS:
        months = months[-DISCOVERY_MAX_MONTHS:]
        capped = True
    note = (
        f"document discovery for '{source_name}' last ran {gap_days} days ago "
        f"({last_run.isoformat()}), which is longer than its normal two-month search "
        f"window, so this run searched {len(months)} month(s) instead of 2 "
        f"({months[0][2]} {months[0][0]} to {months[-1][2]} {months[-1][0]})."
    )
    if capped:
        note += (f" The window was capped at {DISCOVERY_MAX_MONTHS} months — anything older "
                 f"than that has NOT been checked and needs a look by hand.")
    print(f"[discover_documents] {note}")
    if warnings is not None:
        warnings.append(note)
    return months


def _egazette_search_month(page, year: int, month_name: str) -> tuple[list[dict], int | None]:
    """
    Drive the 'Search by Ministry' form for one month/year. Returns
    (raw result rows, the total the page itself reported) — the second value is
    None if the count label could not be read.

    No CAPTCHA anywhere in this flow (confirmed by hand — see the findings
    doc); each dropdown pick reloads the page (ASP.NET postback), so each step
    waits for that navigation before the next.
    """
    # "commit" (not "load"/"networkidle"): waits only for the navigation's
    # response to start arriving, not for every page resource to finish. A
    # real production run still timed out at 60s waiting for "load", even
    # though this exact URL is already fetched successfully every day by
    # plain `requests` in fetch_sources.py — pointing at some slow or
    # never-finishing sub-resource on the page (an ad, a widget, a font),
    # not an unreachable site or connection. Every step after this waits
    # for a SPECIFIC element it actually needs next, rather than a generic
    # "page fully loaded" signal — Playwright's click()/select_option()
    # already auto-wait for their own target element, so this sidesteps
    # the slow-resource problem entirely instead of just giving it more time.
    page.goto(f"{EGAZETTE_BASE}/", timeout=EGAZETTE_TIMEOUT_MS, wait_until="commit")
    page.click("text=Search", timeout=EGAZETTE_TIMEOUT_MS)
    page.click("text=Search by Ministry", timeout=EGAZETTE_TIMEOUT_MS)
    page.wait_for_selector("#ddlMinistry", timeout=EGAZETTE_TIMEOUT_MS)

    with page.expect_navigation(timeout=EGAZETTE_TIMEOUT_MS, wait_until="domcontentloaded"):
        page.select_option("#ddlMinistry", label=EGAZETTE_MINISTRY_LABEL)
    with page.expect_navigation(timeout=EGAZETTE_TIMEOUT_MS, wait_until="domcontentloaded"):
        page.select_option("#ddlmonth", label=month_name)
    with page.expect_navigation(timeout=EGAZETTE_TIMEOUT_MS, wait_until="domcontentloaded"):
        page.select_option("#ddlyear", label=str(year))

    page.click("#ImgSubmitDetails", timeout=EGAZETTE_TIMEOUT_MS)
    # Wait for the actual results label, not a generic load signal — this is
    # the one DOM change that proves the postback's results rendered.
    page.wait_for_selector("#lbl_Result", timeout=EGAZETTE_TIMEOUT_MS)
    page.wait_for_timeout(1000)

    # The page states how many results it found ("Total No. of Gazettes : 5").
    # Read it, so a half-rendered or partly-scraped page is a loud failure
    # rather than a quietly short list (audit finding M-6).
    reported_total = None
    try:
        label = page.inner_text("#lbl_Result")
        match = EGAZETTE_RESULT_COUNT_RE.search(label or "")
        if match:
            reported_total = int(match.group(1))
    except Exception as exc:
        print(f"[discover_documents] could not read the results count label: {exc}")

    rows = page.eval_on_selector_all(
        '[id^="gvGazetteList_lbl_Subject_"]',
        """els => els.map(s => {
            const idx = s.id.split('_').pop();
            const get = (name) => {
                const el = document.getElementById(`gvGazetteList_lbl_${name}_${idx}`);
                return el ? el.textContent.trim() : null;
            };
            return {
                subject: get('Subject'),
                issueDate: get('IssueDate'),
                gazetteId: get('UGID'),
            };
        })""",
    )
    return rows, reported_total


def fetch_egazette_meity(conn=None, today: date | None = None) -> dict:
    """
    Search eGazette for MeitY notifications. Returns
    {"items": [...], "bucket_counts": {...}, "warnings": [...]}.

    Items are keyed by their permanent WriteReadData PDF URL (never the
    session-scoped search URL, which changes every run), deduplicated across
    the months queried. bucket_counts has one entry per month queried, for the
    canary. warnings are things a human should read but which must not stop the
    run — they are added to the day's error list by discover_all.

    Which months are searched depends on when this last ran successfully; see
    _months_to_search (audit finding M-12).
    """
    from playwright.sync_api import sync_playwright  # imported lazily so a

    # missing/blocked browser install only breaks this one source, not the
    # whole module — caught by discover_all's per-source try/except.

    today = today or date.today()
    items_by_url: dict[str, dict] = {}
    bucket_counts: dict[str, int] = {}
    warnings: list[str] = []
    months = _months_to_search(conn, today, "egazette-meity", warnings)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # ignore_https_errors stays ON here, deliberately, and it is the
            # one place in this project where certificate checking is off
            # (audit finding C-4). Two reasons: (1) this page is read for a
            # LIST of document titles and Gazette IDs only — it can produce an
            # alert for a human, never a change to stored legal text; (2)
            # giving headless Chromium an extra CA certificate needs an NSS
            # database on the CI runner, which is a lot of machinery for an
            # alert-only read. The PDF download below IS verified (see
            # _download_pdf_bytes). Open item: teach this step to use
            # certs/egazette-chain.pem too.
            page = browser.new_page(ignore_https_errors=True, user_agent=USER_AGENT)
            # Block image/font/stylesheet/media requests outright: two real
            # production runs hung waiting for a page to "settle" even with
            # a minimal wait_until, right after the document itself had
            # already committed — consistent with a slow-to-load,
            # functionally irrelevant sub-resource (this page only needs to
            # be readable for its text and form controls, not rendered
            # visually). Standard resource-blocking, not a fingerprint or
            # detection workaround — every other request type still goes
            # through untouched.
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "font", "stylesheet", "media")
                else route.continue_(),
            )
            for index, (year, month_num, month_name) in enumerate(months):
                if index and len(months) > 2:
                    # Politeness pause, only when the window has been widened.
                    page.wait_for_timeout(EGAZETTE_MONTH_PAUSE_MS)
                bucket_key = f"egazette-meity:{year:04d}-{month_num:02d}"
                rows, reported_total = _egazette_search_month(page, year, month_name)
                bucket_counts[bucket_key] = len(rows)

                # M-6: the page told us how many results it found. If we
                # scraped a different number, this month's listing cannot be
                # trusted, and a short listing looks exactly like "nothing new".
                if reported_total is not None and reported_total != len(rows):
                    raise RuntimeError(
                        f"eGazette said it found {reported_total} gazette(s) for "
                        f"{month_name} {year} but only {len(rows)} row(s) could be read "
                        f"from the page. Refusing to treat a partly-read listing as the "
                        f"whole month — a short list is indistinguishable from 'nothing new'."
                    )
                if reported_total is None:
                    warnings.append(
                        f"eGazette's results-count label could not be read for "
                        f"{month_name} {year}, so the {len(rows)} row(s) found could not be "
                        f"cross-checked against the page's own total. Worth a look if it "
                        f"keeps happening."
                    )

                for row in rows:
                    gazette_id = row.get("gazetteId")
                    if not gazette_id:
                        continue
                    url = _egazette_pdf_url(gazette_id)
                    if url is None:
                        # M-7: one badly-formatted ID used to throw away the
                        # whole day's listing. Keep every good row, and name the
                        # bad one for a human instead.
                        warnings.append(
                            f"eGazette row skipped for {month_name} {year}: its Gazette ID "
                            f"{gazette_id!r} is not in the expected "
                            f"CG-DL-<x>-DDMMYYYY-NNNNNN form, so no document link could be "
                            f"built. Subject: {row.get('subject')!r}. Please look this one up "
                            f"by hand on egazette.gov.in."
                        )
                        continue
                    items_by_url[url] = {
                        "title": row.get("subject") or gazette_id,
                        "url": url,
                        "published_date": _parse_egazette_date(row.get("issueDate")),
                    }
        finally:
            browser.close()

    return {
        "items": list(items_by_url.values()),
        "bucket_counts": bucket_counts,
        "warnings": warnings,
    }


DISCOVERY_SOURCES = [
    {
        "name": "egazette-meity",
        "fetch": fetch_egazette_meity,
        # Not all_items_relevant: MeitY's Gazette notices include plenty of
        # non-DPDP items (e.g. committee resolutions) — keywords decide.
        "all_items_relevant": False,
    },
]


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def _known_urls(conn, source: str) -> set[str]:
    rows = conn.execute(
        "SELECT url FROM discovered_documents WHERE discovery_source = ?", (source,)
    ).fetchall()
    return {r["url"] for r in rows}


def _store_document(conn, *, url, source, title, published_date, first_seen,
                     is_baseline, matched_keywords, text_excerpt, alerted) -> None:
    conn.execute(
        """INSERT INTO discovered_documents
           (url, discovery_source, title, published_date, first_seen_date,
            is_baseline, matched_keywords, text_excerpt, alerted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO NOTHING""",
        (
            url, source, title, published_date, first_seen, int(is_baseline),
            ",".join(matched_keywords) if matched_keywords else None,
            text_excerpt, int(alerted),
        ),
    )


def mark_alerted(conn, urls: list[str]) -> None:
    """Called by run_pipeline.py only after send_summary() has successfully
    sent the email containing these documents — a document is alerted=1 only
    once the alert genuinely went out, so a failed send is retried, never
    lost, next run."""
    if not urls:
        return
    conn.executemany("UPDATE discovered_documents SET alerted = 1 WHERE url = ?", [(u,) for u in urls])
    conn.commit()


def _source_has_ever_run(conn, source_name: str) -> bool:
    """Any row at all under this plain source name, regardless of date —
    deliberately not date-scoped (unlike _last_run_count, used for the
    canary), so that a second call on the same calendar day (a manual
    re-run, or simply how the test suite exercises this) is still
    recognised as 'already initialized' and doesn't re-baseline."""
    row = conn.execute(
        "SELECT 1 FROM discovery_run_log WHERE discovery_source = ? LIMIT 1", (source_name,)
    ).fetchone()
    return row is not None


def _last_run_count(conn, bucket_key: str, before_date: str) -> int | None:
    row = conn.execute(
        """SELECT items_found FROM discovery_run_log
           WHERE discovery_source = ? AND run_date < ?
           ORDER BY run_date DESC LIMIT 1""",
        (bucket_key, before_date),
    ).fetchone()
    return row["items_found"] if row else None


def _log_run(conn, bucket_key: str, run_date_str: str, count: int) -> None:
    conn.execute(
        """INSERT INTO discovery_run_log (discovery_source, run_date, items_found)
           VALUES (?, ?, ?)
           ON CONFLICT(discovery_source, run_date) DO UPDATE SET items_found = excluded.items_found""",
        (bucket_key, run_date_str, count),
    )


def _check_canary(conn, bucket_key: str, today_str: str, count: int, errors: list[str]) -> None:
    """See the module docstring's Canary section for why this compares a
    month-scoped bucket against its own history only, and why a bucket with
    no (or a zero) prior count is never flagged — a brand-new or
    just-started month is expected to be thin or empty."""
    prior = _last_run_count(conn, bucket_key, today_str)
    if not prior:
        return
    if count == 0 or count < prior * 0.5:
        errors.append(
            f"discovery source '{bucket_key}' returned {count} item(s) today, down from "
            f"{prior} previously — listing may have changed structure or failed to load"
        )


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def discover_all(conn, errors: list[str], dry_run: bool = False) -> tuple[list[dict], list[str]]:
    """
    Fetch every configured source, compare against what's already in
    discovered_documents, and return (new_documents, baseline_notes).

    First-ever run for a source: everything it lists is stored as baseline
    (is_baseline=1, alerted=1) and reported only as one line in
    baseline_notes — never as a per-document alert (otherwise the first run
    would flood an inbox with documents that were already there). Every run
    after that: a URL not already known is a new document — keyword-matched
    (or, for an all_items_relevant source, always relevant), PDF text read
    where possible, and returned for alerting; an unreadable new PDF is
    still returned for alerting (with unreadable=True), never dropped.

    dry_run=True performs every read and every check but writes nothing to
    `conn` — used by the --dry-run CLI mode below for a repeatable preview
    against a throwaway copy of the database.
    """
    new_documents: list[dict] = []
    baseline_notes: list[str] = []
    today_str = date.today().isoformat()

    for source in DISCOVERY_SOURCES:
        name = source["name"]
        try:
            # conn is passed so a source can look up when it last ran and widen
            # its own search window after an outage (audit M-12).
            result = source["fetch"](conn=conn)
        except Exception as exc:
            errors.append(f"discovery source '{name}' failed: {exc}")
            continue

        items = result["items"]
        bucket_counts = result["bucket_counts"]
        # Things worth a human's attention that must not stop the run: a
        # Gazette ID that could not be parsed, a results count that could not be
        # cross-checked, a widened search window (audit M-6, M-7, M-12).
        errors.extend(result.get("warnings") or [])

        for bucket_key, count in bucket_counts.items():
            _check_canary(conn, bucket_key, today_str, count, errors)
            if not dry_run:
                _log_run(conn, bucket_key, today_str, count)

        # "Has this source ever run before" is tracked under the source's
        # own plain name — deliberately NOT the same as "does
        # discovered_documents have any rows for it yet", because a
        # first-ever run that happens to find 0 items would otherwise look
        # "uninitialized" forever and silently re-baseline (swallowing
        # every future document as if it were old) on every subsequent run.
        # Namespaced so this can never collide with a real bucket key a
        # source reports in bucket_counts (some sources' bucket_counts use
        # the plain source name itself as their only key).
        init_bucket_key = f"{name}:__init__"
        already_initialized = _source_has_ever_run(conn, init_bucket_key)
        if not dry_run:
            _log_run(conn, init_bucket_key, today_str, len(items))
            conn.commit()

        if not already_initialized:
            if not dry_run:
                for item in items:
                    _store_document(
                        conn, url=item["url"], source=name, title=item["title"],
                        published_date=item.get("published_date"), first_seen=today_str,
                        is_baseline=True, matched_keywords=None, text_excerpt=None,
                        alerted=True,
                    )
                conn.commit()
            baseline_notes.append(f"baseline captured for {name}: {len(items)} document(s)")
            continue

        # Carry forward anything already stored but never successfully
        # alerted — a previous run found it and stored it, but the email
        # containing it failed to send (mark_alerted() only runs after a
        # successful send), so it must be offered again rather than lost.
        # Re-derive "was this meant to alert" from the stored columns
        # instead of re-fetching/re-reading the PDF a second time.
        for row in conn.execute(
            "SELECT url, title, published_date, matched_keywords, text_excerpt "
            "FROM discovered_documents WHERE discovery_source = ? AND alerted = 0 AND is_baseline = 0",
            (name,),
        ).fetchall():
            matched = row["matched_keywords"].split(",") if row["matched_keywords"] else []
            was_unreadable = row["text_excerpt"] == UNREADABLE_MARKER
            if not (source["all_items_relevant"] or matched or was_unreadable):
                continue  # stored, but genuinely never meant to alert — not a retry
            new_documents.append({
                "url": row["url"], "title": row["title"], "discovery_source": name,
                "published_date": row["published_date"], "matched_keywords": matched,
                "text_excerpt": None if was_unreadable else row["text_excerpt"],
                "unreadable": was_unreadable,
            })

        known = _known_urls(conn, name)
        for item in items:
            if item["url"] in known:
                continue

            matched = _match_keywords(item["title"], item["url"])
            excerpt = None
            unreadable = False
            if item["url"].lower().endswith(".pdf"):
                try:
                    # Any TLS problem is recorded in `errors`, so it reaches the
                    # email rather than only the log (see _download_pdf_bytes).
                    raw = _download_pdf_bytes(item["url"], tls_warnings=errors)
                    text = _extract_pdf_text(raw)
                    for kw in _match_keywords(text):
                        if kw not in matched:
                            matched.append(kw)
                    excerpt = _english_excerpt(text)
                except Exception as exc:
                    unreadable = True
                    print(f"[discover_documents] could not read new PDF {item['url']}: {exc}")

            should_alert = source["all_items_relevant"] or bool(matched) or unreadable

            if not dry_run:
                _store_document(
                    conn, url=item["url"], source=name, title=item["title"],
                    published_date=item.get("published_date"), first_seen=today_str,
                    is_baseline=False, matched_keywords=matched,
                    text_excerpt=UNREADABLE_MARKER if unreadable else excerpt,
                    alerted=False,
                )

            if should_alert:
                new_documents.append({
                    "url": item["url"],
                    "title": item["title"],
                    "discovery_source": name,
                    "published_date": item.get("published_date"),
                    "matched_keywords": matched,
                    "text_excerpt": excerpt,
                    "unreadable": unreadable,
                })

        if not dry_run:
            conn.commit()

    return new_documents, baseline_notes


def main() -> None:
    import argparse

    from db import get_connection, init_schema

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="write nothing, just report")
    parser.add_argument("--db", required=True, help="path to a COPY of the database — never the live db/dpdpa.db")
    args = parser.parse_args()

    conn = get_connection(Path(args.db))
    init_schema(conn)
    errors: list[str] = []
    new_documents, baseline_notes = discover_all(conn, errors, dry_run=args.dry_run)
    conn.close()

    for note in baseline_notes:
        print(f"[baseline] {note}")
    for doc in new_documents:
        print(f"[NEW] {doc['discovery_source']}: {doc['title']} -> {doc['url']}")
        if doc["unreadable"]:
            print("   (could not be read)")
        else:
            print(f"   keywords: {doc['matched_keywords']}")
            if doc["text_excerpt"]:
                print(f"   excerpt: {doc['text_excerpt'][:200]!r}...")
    for e in errors:
        print(f"[ERROR] {e}")
    if not new_documents and not baseline_notes and not errors:
        print("Nothing found.")


if __name__ == "__main__":
    main()
