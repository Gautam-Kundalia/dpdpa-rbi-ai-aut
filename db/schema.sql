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
    linked_change_ids           TEXT                   -- comma-separated change_ids produced from this doc
);

CREATE INDEX IF NOT EXISTS idx_change_log_provision ON change_log(provision_id);
CREATE INDEX IF NOT EXISTS idx_change_log_review_status ON change_log(review_status);
CREATE INDEX IF NOT EXISTS idx_provisions_review_status ON provisions(review_status);
CREATE INDEX IF NOT EXISTS idx_provisions_sort_order ON provisions(sort_order);
