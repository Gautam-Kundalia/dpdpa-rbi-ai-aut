"""
Phase 8: a PERMANENT guard against paraphrase creeping back into the
legal text. Runs the same mechanical checks the verbatim-rebuild scripts
used (C1: contiguous substring of the primary PDF extraction; C2: cross-
checked against a second, independent PDF library; C3: >=99.5% word
coverage; C4: fabrication blacklist; C5: spot-checked facts) against the
COMMITTED database and the stored, hash-verified source PDFs.

Deliberately reuses each rebuild script's own check logic (by invoking it
in its default --dry-run mode, which never writes to the database) rather
than re-implementing the checks here — the guard is only as good as
staying identical to what was actually verified when the text was written.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Even in its default dry-run mode, the rebuild script regenerates these two
# tracked files as a "preview" side effect (no DB write). Content-wise this
# is harmless (re-running against an already-correct DB just reproduces the
# same verbatim JSON, and collapses the review doc's per-row diffs since
# there's no more old-vs-new delta to show) — but it would otherwise leave
# the working tree dirty after every test run and risks someone
# accidentally committing over the richer historical review doc. Restore
# both via git checkout after the check runs, regardless of outcome.
_SIDE_EFFECT_FILES = [
    "data/act_verbatim_2026-09-23.json",
    "docs/act_verbatim_rebuild_2026-09-23.md",
]


@pytest.fixture
def restore_rebuild_side_effects():
    yield
    subprocess.run(["git", "checkout", "--"] + _SIDE_EFFECT_FILES, cwd=REPO_ROOT)


def test_act_table_passes_verbatim_checks_c1_to_c5(restore_rebuild_side_effects):
    """
    Runs scripts/rebuild_act_verbatim_2026-09-23.py in its default dry-run
    mode: re-extracts the Act PDF (hash-verified), re-runs checks C1-C5
    against the 48 DPDPA-* rows currently committed in db/dpdpa.db, and
    exits non-zero if anything no longer matches verbatim. No DB writes.
    """
    result = subprocess.run(
        [sys.executable, "scripts/rebuild_act_verbatim_2026-09-23.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        f"Act verbatim check failed (exit {result.returncode}):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "All checks C1-C5 passed" in result.stdout, result.stdout
