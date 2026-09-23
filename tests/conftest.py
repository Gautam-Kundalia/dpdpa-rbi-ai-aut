"""
Shared pytest fixtures. Every fixture here uses an isolated, throwaway
SQLite file under pytest's tmp_path — never db/dpdpa.db. Tests must not
import db.get_connection() with no arguments and must not rely on the
live database's contents.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest

import db as db_module


@pytest.fixture
def conn(tmp_path):
    """A fresh, schema-initialized SQLite connection backed by a temp file."""
    db_path = tmp_path / "test.db"
    connection = db_module.get_connection(db_path)
    db_module.init_schema(connection)
    yield connection
    connection.close()


def seed_provision(conn, **overrides):
    """Insert a minimal valid provisions row; override any column via kwargs."""
    row = {
        "provision_id": "DPDPR-R23",
        "instrument_type": "Rule",
        "reference": "Rule 23(1)",
        "topic_category": "Appeals",
        "current_summary": "Appeals process summary.",
        "full_text": "given in such order.",
        "full_text_path": "docs/DPDP_Rules_2025.docx",
        "full_text_anchor": "DPDPR_R23",
        "sort_order": 1,
        "status": "Active",
        "effective_date": "2025-11-13",
        "last_updated_date": "2025-11-13",
        "source_document": "seed",
        "source_url": "seed",
        "confidence_score": 1.0,
        "review_status": "Confirmed",
        "reviewed_by": "auto",
        "review_date": "2025-11-13",
        "latest_change_id": None,
        "notes": "seed",
    }
    row.update(overrides)
    conn.execute(
        f"INSERT INTO provisions ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
        list(row.values()),
    )
    conn.commit()
    return row


def seed_source_log(conn, **overrides):
    row = {
        "document_id": "SRC-0099",
        "source": "MeitY",
        "title": "test source",
        "url": "http://example.test/doc.pdf",
        "published_date": "2026-09-23",
        "fetched_date": "2026-09-23",
        "content_hash": "h1",
        "processing_status": "New",
        "linked_change_ids": None,
    }
    row.update(overrides)
    conn.execute(
        f"INSERT INTO source_log ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
        list(row.values()),
    )
    conn.commit()
    return row


class FakeFetchResult:
    """Minimal stand-in for fetch_sources.FetchResult, for tests that don't
    need the real dataclass (avoids importing requests/bs4/pypdf machinery
    where it's not needed)."""

    def __init__(self, *, source="MeitY", title="test", url="http://example.test/doc.pdf",
                 document_id="SRC-0099", content_text="", content_hash="h1",
                 changed=True, prior_hash=None):
        self.source = source
        self.title = title
        self.url = url
        self.document_id = document_id
        self.content_text = content_text
        self.content_hash = content_hash
        self.changed = changed
        self.prior_hash = prior_hash
