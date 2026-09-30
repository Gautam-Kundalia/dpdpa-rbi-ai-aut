-- DPDP Rules Regulatory Change Tracker — SQLite schema
-- This is the source of truth. Master_Provisions/Change_Log/Source_Log in the
-- Excel workbook, and DPDP_Rules_2025.docx / DPDP_Act_2023.docx, are all
-- generated FROM these tables (see src/export_excel.py, src/export_word.py).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS provisions (
    provision_id       TEXT PRIMARY KEY,          -- e.g. 'DPDPR-R8.3'
    instrument_type    TEXT NOT NULL CHECK (instrument_type IN
                        ('Act Section','Rule','Sub-Rule','Schedule','Notification','Board Order')),
    reference           TEXT NOT NULL,             -- e.g. 'Rule 8(3)'
    topic_category      TEXT,                      -- e.g. 'Retention & Erasure'
    current_summary      TEXT,                      -- plain-language summary, NOT full clause text
    full_text             TEXT,                      -- verbatim clause text (markdown-lite: **bold**, blank-line
                                                       -- separated paragraphs, '|'-delimited tables)
    full_text_path        TEXT,                      -- relative path to the consolidated docx, e.g.
                                                       -- 'docs/DPDP_Rules_2025.docx'
    full_text_anchor       TEXT,                      -- bookmark name within that docx
    sort_order              INTEGER,                   -- controls ordering in the generated docx
    status                TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN
                        ('Active','Draft','Superseded','Repealed')),
    effective_date        TEXT,                      -- ISO date
    last_updated_date     TEXT,                      -- ISO date
    source_document       TEXT,
    source_url            TEXT,
    confidence_score       REAL,                      -- 0.0–1.0, agent's confidence in this row
    review_status          TEXT NOT NULL DEFAULT 'Pending Review' CHECK (review_status IN
                        ('Confirmed','Pending Review','Rejected')),
    reviewed_by             TEXT,
    review_date             TEXT,
    latest_change_id        TEXT,                     -- FK-ish pointer to change_log.change_id
    notes                    TEXT
);

CREATE TABLE IF NOT EXISTS change_log (
    change_id           TEXT PRIMARY KEY,          -- e.g. 'CHG-0001'
    detected_timestamp  TEXT NOT NULL,             -- ISO datetime
    provision_id        TEXT NOT NULL REFERENCES provisions(provision_id),
    change_type         TEXT NOT NULL CHECK (change_type IN
                        ('New Provision','Amendment','Repeal','Clarification','Correction')),
    old_value_summary    TEXT,
    new_value_summary    TEXT,
    old_full_text          TEXT,                     -- verbatim prior clause text, for change_type != 'New Provision'
    new_full_text          TEXT,                     -- verbatim new clause text
    source_document       TEXT,
    source_url            TEXT,
    detected_by            TEXT,                     -- e.g. 'agent:openrouter/<model>'
    change_origin           TEXT CHECK (change_origin IN
                        ('baseline','regulatory','data_correction')),
                                                       -- 'regulatory' = the government actually changed the
                                                       -- law/rules; 'data_correction' = we fixed our own data
                                                       -- (typo, paraphrase, omission); 'baseline' = initial seed
                                                       -- load. Only 'regulatory' rows are ever highlighted.
    confidence_score        REAL,
    review_status            TEXT NOT NULL DEFAULT 'Pending Review' CHECK (review_status IN
                        ('Pending Review','Approved','Rejected','Modified')),
    reviewed_by               TEXT,
    review_date               TEXT,
    applied_to_master          TEXT NOT NULL DEFAULT 'N' CHECK (applied_to_master IN ('Y','N')),
    notes                      TEXT
);

CREATE TABLE IF NOT EXISTS source_log (
    document_id         TEXT PRIMARY KEY,          -- e.g. 'SRC-0001'
    source               TEXT NOT NULL CHECK (source IN
                        ('MeitY','eGazette','PIB','Data Protection Board','Other')),
    title                 TEXT,
    url                    TEXT NOT NULL UNIQUE,
    published_date          TEXT,
    fetched_date             TEXT,
    content_hash              TEXT,                  -- sha256 of fetched content, for change detection
    processing_status         TEXT NOT NULL DEFAULT 'New' CHECK (processing_status IN
                        ('New','Processed','No Change Detected','Error')),
    linked_change_ids           TEXT,                  -- comma-separated change_ids produced from this doc
    watched                      INTEGER NOT NULL DEFAULT 1,
                                                       -- 1 = still being checked every day; 0 = kept only for
                                                       -- its linked_change_ids history (a URL that was
                                                       -- one-off, superseded or retired). The Excel
                                                       -- Source_Log sheet shows only watched = 1 rows,
                                                       -- because it says it shows "what is being watched
                                                       -- right now" (audit M-5).
    error_signature               TEXT,                 -- a short, stable label for the CURRENT fetch problem
    error_streak_days              INTEGER NOT NULL DEFAULT 0,
                                                       -- how many consecutive days that same problem has
                                                       -- happened. Used so a source that has been down for
                                                       -- a week stops dominating the email subject line
                                                       -- every day, while still appearing in the body
                                                       -- (audit M-3). Reset to 0 on any successful fetch.
    error_streak_last_date          TEXT                -- the date the streak was last counted, so two runs
                                                       -- on the same day do not count twice
);

CREATE TABLE IF NOT EXISTS source_snapshot (
    document_id         TEXT PRIMARY KEY REFERENCES source_log(document_id),
    content_hash          TEXT,                  -- matches source_log.content_hash as of this snapshot
    content_text           TEXT,                  -- the extracted text as classify_change.py last saw it
    fetched_date             TEXT                   -- ISO date this snapshot was taken
);
-- Holds the text from the last SUCCESSFULLY CLASSIFIED fetch of each source
-- (not just the last fetch) — classify_change.py diffs the new fetch
-- against this instead of re-sending the whole document to the model every
-- time. Deliberately not updated when classification fails, so a retried
-- run diffs against the same known-good baseline as the failed run did.

CREATE TABLE IF NOT EXISTS discovered_documents (
    url               TEXT PRIMARY KEY,
    discovery_source  TEXT NOT NULL,      -- e.g. 'egazette-meity'
    title             TEXT,
    published_date    TEXT,
    first_seen_date   TEXT NOT NULL,      -- ISO date
    is_baseline       INTEGER NOT NULL DEFAULT 0,   -- 1 = already listed when we first started watching
    matched_keywords  TEXT,
    text_excerpt      TEXT,               -- first ~600 chars, English only
    alerted           INTEGER NOT NULL DEFAULT 0    -- 1 only after an email containing it was sent
);
-- Alert-only document discovery (30 Sep 2026): watches pages that LIST documents
-- (as opposed to fetch_sources.py's fixed four URLs, which only notice edits to
-- documents already known) and emails when a brand-new one appears. Never writes
-- to provisions/change_log — a human decides what to apply. See
-- src/discover_documents.py and docs/detection_coverage_2026-09-30.md.

CREATE TABLE IF NOT EXISTS discovery_run_log (
    discovery_source  TEXT NOT NULL,      -- may be a month-scoped bucket key, e.g.
                                           -- 'egazette-meity:2026-09', for sources whose
                                           -- listing is itself month-scoped — see
                                           -- src/discover_documents.py's canary logic
    run_date          TEXT NOT NULL,
    items_found       INTEGER NOT NULL,
    PRIMARY KEY (discovery_source, run_date)
);

CREATE INDEX IF NOT EXISTS idx_change_log_provision ON change_log(provision_id);
CREATE INDEX IF NOT EXISTS idx_change_log_review_status ON change_log(review_status);
CREATE INDEX IF NOT EXISTS idx_provisions_review_status ON provisions(review_status);
CREATE INDEX IF NOT EXISTS idx_provisions_sort_order ON provisions(sort_order);
