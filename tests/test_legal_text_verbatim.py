"""
A PERMANENT guard against paraphrase creeping back into the legal text.

What it actually does (this docstring was wrong until 30 Sep 2026 — audit
findings C-1 and C-2, and §6 claims 1 and 2):

Act table (48 `DPDPA-*` rows)
    Invokes scripts/rebuild_act_verbatim_2026-09-23.py in its default
    dry-run mode (which never writes to the database). Since 30 Sep 2026
    that script's checks C1/C2/C4 read each provision's `full_text` FROM
    THE DATABASE and compare it against the hash-verified official PDF.
    Before that date they read the PDF-derived text on both sides, so they
    compared the PDF to itself and could not fail (C-1).

Rules table (31 `DPDPR-*` rows)
    Its own idempotent check: every provision's stored `full_text`
    (paragraph by paragraph; table cells individually), normalized, must be
    a contiguous substring of a fresh extraction of the Rules PDF's English
    half (pages 24-41). Where it is not, the piece must still match the PDF
    IN WORD ORDER with every difference confined to punctuation or spacing.
    Until 30 Sep 2026 the fallback was "at least 97% of this piece's words
    appear SOMEWHERE in the PDF", which legal text satisfies from its own
    vocabulary — a `shall` -> `may` swap passed (C-2).

Known, reviewed differences live in `_KNOWN_EXCEPTIONS` as exact pairs:
the specific text the database really holds, the text the PDF really has,
the reason, and the audit finding ID. An exception only applies when the
database still holds that exact string — so when the one-off data-fix
scripts restore the official wording, the exception simply stops applying
and the ordinary exact match takes over. No exception can hide a NEW
problem.

Negative tests ("mutation tests") sit alongside every positive one: they
corrupt one thing and require the guard to notice. A guard with no test
that makes it fail is not evidence of anything — that is how C-1 survived
for a week with a green test suite.
"""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

# Both PDF libraries are hard requirements for this file: without them every
# test here fails for an environment reason that looks like a data problem
# (audit I-7 — 32 mysterious failures on a machine with no PDF tooling).
# Skip loudly and once instead.
pytest.importorskip("pymupdf", reason="PyMuPDF is needed to read the Rules PDF (pip install pymupdf)")
pytest.importorskip("pdfplumber", reason="pdfplumber is needed to read the Act PDF (pip install pdfplumber)")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_module(path: Path, name: str):
    """scripts/*.py filenames have hyphens (not valid Python module names
    for a plain `import`), so load them by file path instead."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_act_rebuild = _load_module(REPO_ROOT / "scripts" / "rebuild_act_verbatim_2026-09-23.py", "act_rebuild")
normalize = _act_rebuild.normalize

ACT_REBUILD_SCRIPT = REPO_ROOT / "scripts" / "rebuild_act_verbatim_2026-09-23.py"
RULES_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "DPDP_Rules_2025_official_2026-09-23.pdf"
RULES_PDF_SHA256 = "eabc7d05e013144615d78ddc0e8b9c9aac1920e814f4fad38ce6560951f5aa08"
CORRIGENDUM_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "GSR892E_Rules_corrigendum_official.pdf"
CORRIGENDUM_PDF_SHA256 = "8f8d9526b511801889f8ae022b6d7c5db449283e90fe32792e5896314b32f994"
LIVE_DB_PATH = REPO_ROOT / "db" / "dpdpa.db"


# --------------------------------------------------------------------------
# Act table: the (idempotent) rebuild script's own dry-run checks, which now
# read the database
# --------------------------------------------------------------------------

def _run_act_check(db_path: Path, out_dir: Path) -> subprocess.CompletedProcess:
    """
    Run the rebuild script's checks against `db_path`, writing its two report
    files into `out_dir`. Nothing tracked by git is touched — the script used
    to write them into the repo and the old test repaired that with
    `git checkout --`, which is not something a test should ever do (L-6).
    """
    return subprocess.run(
        [sys.executable, str(ACT_REBUILD_SCRIPT), "--db", str(db_path), "--out-dir", str(out_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )


def test_act_table_passes_verbatim_checks_c1_to_c5(tmp_path):
    """
    Re-extracts the Act PDF (hash-verified), re-runs checks C1-C5 against the
    48 DPDPA-* rows' `full_text` as committed in db/dpdpa.db, and exits
    non-zero if anything no longer matches verbatim. No database writes.
    """
    # A COPY, never the tracked file. The script calls init_schema(), which
    # applies the additive column migrations — harmless, but it would leave
    # db/dpdpa.db modified in the working tree every time the tests ran, and
    # that file belongs to the daily bot.
    db_copy = tmp_path / "committed.db"
    shutil.copy2(LIVE_DB_PATH, db_copy)
    result = _run_act_check(db_copy, tmp_path)
    assert result.returncode == 0, (
        f"Act verbatim check failed (exit {result.returncode}):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "All checks C1-C5 passed" in result.stdout, result.stdout


# Each entry: (a name for the test id, the provision to corrupt, the text to
# find, the text to put there instead). Both of these are the exact
# corruptions the 30 Sep 2026 audit showed the old check passing.
ACT_MUTATIONS = [
    (
        "nonsense_replaces_section_33",
        "DPDPA-S33",
        None,   # replace the whole row
        "**Section 33 - Penalties**\n\n"
        "There are no penalties under this Act. Nothing here is real legal text.",
    ),
    (
        "significant_becomes_insignificant",
        "DPDPA-S33",
        "is significant",
        "is insignificant",
    ),
]


@pytest.mark.parametrize(
    "provision_id, find, replace_with",
    [(pid, find, rep) for _name, pid, find, rep in ACT_MUTATIONS],
    ids=[name for name, _pid, _f, _r in ACT_MUTATIONS],
)
def test_act_check_fails_when_the_database_text_is_corrupted(tmp_path, provision_id, find, replace_with):
    """
    NEGATIVE test (this is the C-1 regression test). Corrupt one Act row in a
    throwaway copy of the database and require the check to fail. Before
    30 Sep 2026 both of these corruptions passed, because the check never
    read the database at all.
    """
    db_copy = tmp_path / "mutated.db"
    shutil.copy2(LIVE_DB_PATH, db_copy)
    conn = sqlite3.connect(db_copy)
    current = conn.execute(
        "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
    ).fetchone()[0]
    if find is None:
        new_text = replace_with
    else:
        assert find in current, f"{find!r} is no longer in {provision_id} — update this test"
        new_text = current.replace(find, replace_with, 1)
    conn.execute(
        "UPDATE provisions SET full_text = ? WHERE provision_id = ?", (new_text, provision_id)
    )
    conn.commit()
    conn.close()

    result = _run_act_check(db_copy, tmp_path / "out")
    assert result.returncode != 0, (
        "the Act verbatim check PASSED on a corrupted database — the guard is not "
        f"reading provisions.full_text:\n{result.stdout[-3000:]}"
    )


# --------------------------------------------------------------------------
# Rules table: standalone idempotent check against the official PDF
# --------------------------------------------------------------------------

def _verify_source_hashes():
    for path, expected in [(RULES_PDF, RULES_PDF_SHA256), (CORRIGENDUM_PDF, CORRIGENDUM_PDF_SHA256)]:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"{path.name} hash mismatch: {actual}"


def _extract_rules_english_text() -> str:
    """
    Pages 24-41 (1-indexed) — the English half of the bilingual Gazette
    PDF — with each page's running header/masthead lines stripped before
    joining. Needed because a provision's text can span a page break (e.g.
    Rule 3(c) continues from page 24 onto page 25): without stripping,
    the page 25 header text ("[भाग II—खण्ड 3(i)]", "भारत का राजपत्र :
    असाधारण", the bare page number — alternating with the English-language
    equivalent on even pages) would sit in the middle of what is, in the
    actual typeset document, one continuous clause.
    """
    import pymupdf
    header_line_re = re.compile(
        r"^\s*(\d+\s*)?$"                                    # bare page number (or blank)
        r"|^\s*THE GAZETTE OF INDIA\s*:\s*EXTRAORDINARY\s*$"
        r"|^\s*\[PART II\S*SEC\. 3\(i\)\]\s*$"
        r"|^\s*\[भाग.*\]\s*$"
        r"|^\s*भारत का रा.पत्र.*$"
        r"|^\s*MINISTRY OF ELECTRONICS AND INFORMATION TECHNOLOGY\s*$",
    )
    doc = pymupdf.open(RULES_PDF)
    pages = []
    for i in range(23, 41):
        lines = doc[i].get_text().split("\n")
        # Only strip from the TOP of the page (a handful of leading lines) —
        # never mid-page, where these same words could legitimately appear
        # as part of the actual clause text.
        cut = 0
        for j, line in enumerate(lines[:6]):
            if header_line_re.match(line):
                cut = j + 1
            elif line.strip():
                break
        pages.append("\n".join(lines[cut:]))
    return "\n".join(pages)


def _rules_provisions():
    conn = sqlite3.connect(LIVE_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT provision_id, full_text FROM provisions WHERE provision_id LIKE 'DPDPR-%' ORDER BY provision_id"
    ).fetchall()
    conn.close()
    return [(r["provision_id"], r["full_text"]) for r in rows]


def _normalize_rules(text: str) -> str:
    """
    Whitespace / quote / dash canonicalization only — never a word change.
    Applied to BOTH sides (the stored text and the PDF extraction), so it can
    never hide a difference in wording, only in typesetting.

    normalize() (from the Act rebuild script) strips whitespace before
    ",.;:)]" but not before an em/en-dash — the Rules PDF's own
    typesetting glues a dash directly onto the preceding word ("shall—",
    no space) at a line-wrap, while this database's text (from the
    original, unrelated Rules seeding work) has a space before it
    ("shall —"). Same wording, same dash — just spacing PyMuPDF's kerning
    heuristic doesn't preserve identically either way. Strip it here
    rather than in the shared normalize(), to avoid touching the already-
    verified Act check's behaviour.
    """
    text = normalize(text)
    text = re.sub(r"\*", "", text)  # normalize() only strips ** (bold), not single-* (italic)
    text = re.sub(r"\s+(-)", r"\1", text)
    # PyMuPDF's kerning heuristic occasionally drops the space after a
    # comma entirely ("rule,it may" for "rule, it may") — a PDF-extraction
    # artifact, not a wording difference. Insert it back before a letter.
    text = re.sub(r"(,)(?=[A-Za-z])", r"\1 ", text)
    # Same artifact after a closing bracket: the Gazette prints
    # "(5) Any matter", PyMuPDF sometimes reads "(5)Any matter".
    text = re.sub(r"(\))(?=[A-Za-z])", r"\1 ", text)
    # A compound word hyphenated across a line-wrap ("non-\nadherence")
    # sometimes keeps a stray space after the hyphen once flattened to one
    # line ("non- adherence") instead of joining cleanly. Narrowly scoped
    # to lowercase-hyphen-lowercase so a genuine dash used as punctuation
    # (different capitalization/spacing pattern) isn't affected.
    text = re.sub(r"([a-z])-\s+([a-z])", r"\1-\2", text)
    return text


# Corrigendum G.S.R. 892(E) of 10 Dec 2025 corrected eight phrases in the
# Rules. MeitY never re-published the Rules PDF, so the archived PDF this
# check reads still prints the UNCORRECTED wording, while the database
# (correctly) holds the corrected wording. Each pair is (what the database
# says, what the PDF says) and is reverted before matching. All five distinct
# substitutions are listed; items (v)(a)/(v)(b) affect the Fourth Schedule
# only and are handled as scoped exceptions below instead, because the
# strings involved are too short to substitute document-wide safely.
_CORRIGENDUM_REVERSIONS = [
    ("in the Official Gazette", "of this Gazette"),      # item (i)(a) and (i)(b)
    ("Departments", "Department"),                        # item (ii)
    ("given in such order", "given in such"),             # item (iii)
    ("every body", "everybody"),                          # item (iv)(a)
    ("(18 of 2013)", "(18 or 2013)"),                     # item (iv)(b)
]

# Reviewed, documented differences between the stored text and the official
# PDF. Each entry is:
#   (exact text the DATABASE holds, exact text the PDF holds, why, finding ID)
# The exception applies ONLY while the database still holds that exact string.
# Once a one-off data-fix script restores the official wording the exception
# silently stops applying and the ordinary exact match passes — no test edit
# needed, and no way for an exception to mask a new problem.
#
# "TO BE REMOVED BY" names the script that makes the entry obsolete.
_KNOWN_EXCEPTIONS: dict[str, list[tuple[str, str, str, str]]] = {
    # ---- pre-existing single-character differences (not yet corrected) ----
    "DPDPR-R10": [
        ("(21 of 2000).", "(21 of 2000);",
         "Rule 10(2)(c) ends with a full stop in the database; the Gazette prints a "
         "semicolon before the following Illustration.", "audit M-11 / pre-existing"),
    ],
    "DPDPR-SCH1": [
        ("The Consent Manager- (a) shall", "The Consent Manager:- (a) shall",
         "First Schedule Part B item 4's lead-in drops the Gazette's colon.",
         "audit M-11 / pre-existing"),
    ],
    # ---- Fourth Schedule Note: corrigendum item (v), applied to the text but
    # ---- not present in the archived pre-corrigendum PDF ----
    "DPDPR-SCH4": [
        ("(35 of 2019);", "(35 of 2019).",
         "Corrigendum item (v)(a) turned the full stop ending item (a) into a semicolon.",
         "audit H-5 (corrigendum item (v)(a))"),
        ('(b) "allied healthcare', '(a) "allied healthcare',
         "Corrigendum item (v)(b) relabelled the Note's items; the PDF prints two items "
         "both labelled (a), which is the printing defect the corrigendum fixed.",
         "audit H-5 (corrigendum item (v)(b))"),
        ('(c) "clinical establishment"', '(b) "clinical establishment"',
         "Corrigendum item (v)(b) relabelling.", "audit H-5 (corrigendum item (v)(b))"),
        ('(d) "educational institution"', '(c) "educational institution"',
         "Corrigendum item (v)(b) relabelling.", "audit H-5 (corrigendum item (v)(b))"),
        ('(e) "healthcare professional"', '(d) "healthcare professional"',
         "Corrigendum item (v)(b) relabelling.", "audit H-5 (corrigendum item (v)(b))"),
        ('(f) "health services"', '(e) "health services"',
         "Corrigendum item (v)(b) relabelling.", "audit H-5 (corrigendum item (v)(b))"),
        ('(g) "mental health', '(f) "mental health',
         "Corrigendum item (v)(b) relabelling.", "audit H-5 (corrigendum item (v)(b))"),
    ],
    # ---- Fifth/Sixth Schedule: the Gazette prints a separator dash after each
    # ---- numbered paragraph heading ("1. Salary.-"); the database drops it.
    # ---- TO BE REMOVED BY scripts/restore_verbatim_wording_2026-09-30.py
    "DPDPR-SCH5": [
        ("1. Salary.", "1. Salary.-", "heading separator dash dropped", "audit M-11"),
        ("2. Provident Fund.", "2. Provident Fund.-", "heading separator dash dropped", "audit M-11"),
        ("3. Pension and gratuity.", "3. Pension and gratuity.-",
         "heading separator dash dropped", "audit M-11"),
        ("4. Travelling allowance. (1)", "4. Travelling allowance.-(1)",
         "heading separator dash dropped", "audit M-11"),
        ("5. Medical assistance.", "5. Medical assistance.-",
         "heading separator dash dropped", "audit M-11"),
        ("6. Leave.", "6. Leave.-", "heading separator dash dropped", "audit M-11"),
        ("7. Leave travel concession. (1)", "7. Leave travel concession.-(1)",
         "heading separator dash dropped", "audit M-11"),
        ("8. Other terms and conditions of service.", "8. Other terms and conditions of service.-",
         "heading separator dash dropped", "audit M-11"),
        ("matrix, namely:", "matrix, namely:-",
         "run-in separator dash dropped before a list", "audit M-11"),
        ("draw, namely:", "draw, namely:-",
         "run-in separator dash dropped before a list", "audit M-11"),
    ],
    "DPDPR-SCH6": [
        ("1. Classes of officials.", "1. Classes of officials.-",
         "heading separator dash dropped", "audit M-11"),
        ("2. Gratuity.", "2. Gratuity.-", "heading separator dash dropped", "audit M-11"),
        ("3. Travelling allowance.", "3. Travelling allowance.-",
         "heading separator dash dropped", "audit M-11"),
        ("4. Medical assistance.", "4. Medical assistance.-",
         "heading separator dash dropped", "audit M-11"),
        ("5. Leave.", "5. Leave.-", "heading separator dash dropped", "audit M-11"),
        ("6. Leave travel concession.", "6. Leave travel concession.-",
         "heading separator dash dropped", "audit M-11"),
        ("7. Other terms and conditions of service.", "7. Other terms and conditions of service.-",
         "heading separator dash dropped", "audit M-11"),
    ],
    # ---- the one real paraphrase left in the corpus ----
    # ---- TO BE REMOVED BY scripts/restore_verbatim_wording_2026-09-30.py
    "DPDPR-SCH7": [
        ("Data Principal for: (i) performance",
         "Data Principal for the following purposes, namely:- (i) performance",
         "Seventh Schedule, second row: five words of enacted text "
         '("the following purposes, namely") were replaced by a colon. This is a '
         "paraphrase inside provisions.full_text, which this project forbids.",
         "audit H-7"),
    ],
}

# Second gate on the fallback: how close, in order, the stored text must be to
# the closest region of the PDF. Deliberately NOT the only gate — see
# _ordered_match's docstring for why a similarity ratio alone is not enough.
ORDERED_RATIO_MIN = 0.995


def _word_runs(text: str) -> list[str]:
    """
    The words in `text`, with all punctuation and spacing thrown away but every
    word boundary kept: "Fund.-" and "Fund." both give ["Fund"], while
    "six months" gives ["six", "months"] and "sixmonths" gives ["sixmonths"].

    Keeping the boundaries is the whole point. Simply deleting punctuation and
    comparing the result would treat "six months" and "sixmonths" as identical,
    which would let a deleted space — or any regrouping of words — through.
    """
    return re.findall(r"[0-9A-Za-z]+", text)


def _ordered_match(needle: str, haystack: str) -> tuple[bool, float, str | None]:
    """
    Does `needle` appear in `haystack` in the same WORD ORDER, with every
    difference confined to punctuation or spacing?

    Two independent gates, both of which must pass:

    1. **Word order.** Align the two word-by-word and require every difference
       to vanish once punctuation and spacing are ignored, WITHOUT losing word
       boundaries (see _word_runs). This is the gate that catches a changed
       meaning — "shall" -> "may", "six months" -> "six years", a dropped
       clause, two words swapped, a deleted space — at any passage length.
    2. **Ordered similarity >= 99.5%** against the closest region of the PDF,
       as a backstop against a match that has drifted.

    Gate 2 on its own is not enough, which is why gate 1 exists: one word
    swapped inside a 1,000-character clause still scores about 99.6%
    similarity, and inside a 2,000-character clause about 99.8%.

    Returns (passed, ratio, reason-if-failed).
    """
    if not needle:
        return True, 1.0, None

    # Locate the region of the PDF this piece belongs to, with padding so the
    # alignment has room at both ends.
    pad = 120
    anchor = difflib.SequenceMatcher(None, haystack, needle, autojunk=False)
    m = anchor.find_longest_match(0, len(haystack), 0, len(needle))
    if m.size == 0:
        return False, 0.0, "no comparable region found in the source PDF at all"
    start = max(0, m.a - m.b - pad)
    region = haystack[start:start + len(needle) + 2 * pad]

    pdf_words, db_words = region.split(), needle.split()
    ops = difflib.SequenceMatcher(None, pdf_words, db_words, autojunk=False).get_opcodes()
    # The region is padded on purpose, so the first and last opcodes are
    # normally "delete" — that is the surrounding PDF context, not a
    # difference. Drop those two, and keep where the piece really aligns.
    if ops and ops[0][0] == "delete" and ops[0][3] == 0:
        ops = ops[1:]
    if ops and ops[-1][0] == "delete" and ops[-1][4] == len(db_words):
        ops = ops[:-1]
    if not ops:
        return False, 0.0, "no comparable region found in the source PDF at all"

    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        pdf_part = " ".join(pdf_words[i1:i2])
        db_part = " ".join(db_words[j1:j2])
        if _word_runs(pdf_part) != _word_runs(db_part):
            return (
                False, 0.0,
                f"word difference — the PDF has {pdf_part[:90]!r} where the database "
                f"has {db_part[:90]!r}",
            )

    # The ordered-similarity backstop is measured against the span of the PDF
    # the piece actually aligns to, not the padded region — otherwise the
    # padding alone would push a perfectly good piece under the threshold.
    # `lo` skips any leading context that was not stripped above.
    lo = ops[0][1] if ops[0][0] != "delete" or ops[0][3] != 0 else ops[0][2]
    tight_region = " ".join(pdf_words[lo:ops[-1][2]])
    ratio = difflib.SequenceMatcher(None, tight_region, needle, autojunk=False).ratio()
    if ratio < ORDERED_RATIO_MIN:
        return (
            False, ratio,
            f"only {ratio:.3%} ordered similarity to the closest region of the PDF "
            f"(need at least {ORDERED_RATIO_MIN:.1%})",
        )
    return True, ratio, None


def check_rules_piece(label: str, provision_id: str, text: str, base_pdf_norm: str) -> str | None:
    """
    Returns None if this piece of stored text is verbatim against the Rules
    PDF, otherwise a one-line explanation of what differs.

    Tried in order, most strict first:
      1. exact normalized substring of the PDF;
      2. the same after applying this provision's reviewed exceptions;
      3. the same after reverting corrigendum G.S.R. 892(E) (the archived PDF
         pre-dates it);
      4. ordered word-level match with punctuation-only differences.
    """
    norm = _normalize_rules(text)
    if not norm:
        return None

    candidates: list[str] = [norm]

    with_exceptions = norm
    used_exception = False
    for db_text, pdf_text, _reason, _finding in _KNOWN_EXCEPTIONS.get(provision_id, []):
        if db_text in with_exceptions:
            with_exceptions = with_exceptions.replace(db_text, pdf_text)
            used_exception = True
    if used_exception:
        candidates.append(with_exceptions)

    for candidate in list(candidates):
        reverted = candidate
        changed = False
        for new, old in _CORRIGENDUM_REVERSIONS:
            if new in reverted:
                reverted = reverted.replace(new, old)
                changed = True
        if changed:
            candidates.append(reverted)

    for candidate in candidates:
        if candidate in base_pdf_norm:
            return None

    best_ratio, best_reason = -1.0, "not found in the source PDF text"
    for candidate in candidates:
        ok, ratio, reason = _ordered_match(candidate, base_pdf_norm)
        if ok:
            return None
        if ratio > best_ratio:
            best_ratio, best_reason = ratio, reason
    return f"{label}: {best_reason} — stored text begins {norm[:120]!r}"


def rules_pieces(full_text: str) -> list[tuple[str, str]]:
    """
    Split a provision's stored text into independently checkable pieces.
    Returns (kind, text) where kind is 'para' or 'table cell'.
    """
    pieces: list[tuple[str, str]] = []
    for block in (full_text or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("*"):
            # A markdown heading/subtitle block (e.g. "**Second Schedule**
            # *(see rules 5(1) and 16)*") — this tracker's own presentational
            # annotations, not positioned in the PDF the way body text is.
            continue
        if block.startswith("|"):
            # Markdown table: check each non-trivial cell independently — the
            # PDF extracts a table column-by-column, not row-by-row, so the
            # table's own shape won't appear in the PDF text even though every
            # cell's wording does.
            for line in block.split("\n"):
                if re.match(r"^\s*\|?\s*-+\s*(\|\s*-+\s*)*\|?\s*$", line):
                    continue  # separator row
                for cell in line.strip().strip("|").split("|"):
                    cell = cell.strip()
                    if len(cell) < 8:  # skip trivial/short cells (numbers, dashes)
                        continue
                    pieces.append(("table cell", cell))
        else:
            pieces.append(("para", block))
    return pieces


def check_rules_provision(provision_id: str, full_text: str, base_pdf_norm: str) -> list[str]:
    errors = []
    for kind, piece in rules_pieces(full_text):
        label = provision_id if kind == "para" else f"{provision_id} {kind}"
        err = check_rules_piece(label, provision_id, piece, base_pdf_norm)
        if err:
            errors.append(err)
    return errors


@pytest.fixture(scope="module")
def rules_pdf_text() -> str:
    """The Rules PDF's English half, extracted and normalized once for the
    whole module (it was previously re-extracted for all 31 rows)."""
    _verify_source_hashes()
    return _normalize_rules(_extract_rules_english_text())


@pytest.mark.parametrize(
    "provision_id, full_text", _rules_provisions(),
    ids=[pid for pid, _ in _rules_provisions()],
)
def test_rules_row_matches_pdf_verbatim(provision_id, full_text, rules_pdf_text):
    """
    This row's stored text (paragraph by paragraph; table cells individually),
    normalized, must be a contiguous substring of a fresh extraction of the
    Rules PDF's English half — or match it in word order with only
    punctuation differing, or match after a reviewed exception or a
    G.S.R. 892(E) reversion. See check_rules_piece.
    """
    errors = check_rules_provision(provision_id, full_text, rules_pdf_text)
    assert errors == [], "\n".join(errors)


# Mutations that reverse or materially change the meaning of a rule. Every one
# of these PASSED the old 97%-word-coverage check, because legal text reuses
# its own vocabulary — that was audit finding C-2.
RULES_MUTATIONS = [
    ("mandatory_becomes_discretionary", "DPDPR-R19", "shall be", "may be"),
    ("six_months_becomes_six_years", "DPDPR-R19", "six months", "six years"),
    ("conflict_of_interest_ban_becomes_permission", "DPDPR-R19",
     "shall not participate in or vote on", "may participate in and vote on"),
    # Deliberately inside the longest block in the corpus (~1,650 characters).
    # A similarity-ratio check alone would score this about 99.8% and let it
    # through; the word-order gate catches it regardless of length.
    ("word_swap_inside_a_very_long_block", "DPDPR-SCH5",
     "The authority competent to sanction leave shall be",
     "The authority competent to sanction leave may be"),
]


@pytest.mark.parametrize(
    "provision_id, find, replace_with",
    [(pid, find, rep) for _name, pid, find, rep in RULES_MUTATIONS],
    ids=[name for name, _p, _f, _r in RULES_MUTATIONS],
)
def test_rules_check_fails_on_a_meaning_changing_word_swap(
    provision_id, find, replace_with, rules_pdf_text
):
    """
    NEGATIVE test (this is the C-2 regression test). Swap one word in a stored
    provision and require the guard to report it.
    """
    stored = dict(_rules_provisions())[provision_id]
    assert find in stored, f"{find!r} is no longer in {provision_id} — update this test"
    mutated = stored.replace(find, replace_with, 1)

    assert check_rules_provision(provision_id, stored, rules_pdf_text) == [], \
        "the unmutated row should pass — the mutation test proves nothing otherwise"
    errors = check_rules_provision(provision_id, mutated, rules_pdf_text)
    assert errors != [], (
        f"the guard PASSED {provision_id} with {find!r} changed to {replace_with!r} — "
        "a meaning-changing word swap is exactly what it must catch"
    )


def test_a_deleted_space_is_caught(rules_pdf_text):
    """
    NEGATIVE test for the word-boundary hole. Deleting a space merges two words
    into one. If the guard only compared "the letters with punctuation removed",
    this would pass — the letters are identical.
    """
    stored = dict(_rules_provisions())["DPDPR-R19"]
    assert "six months" in stored
    mutated = stored.replace("six months", "sixmonths", 1)
    assert check_rules_provision("DPDPR-R19", mutated, rules_pdf_text) != []


def test_two_words_swapped_round_is_caught(rules_pdf_text):
    """NEGATIVE test: reordering words must be caught, not just changing them."""
    stored = dict(_rules_provisions())["DPDPR-R19"]
    assert "the quorum for its meetings" in stored
    mutated = stored.replace("the quorum for its meetings", "the quorum its for meetings", 1)
    assert check_rules_provision("DPDPR-R19", mutated, rules_pdf_text) != []


def test_the_ordered_fallback_accepts_punctuation_only_noise():
    """
    Directly exercises the fallback path. Today every known difference is an
    explicit reviewed exception, so nothing in the real database reaches this
    code — which is exactly why it needs its own test rather than being dead
    code nobody notices is broken.
    """
    haystack = ("some earlier text 1. Salary.- (1) The Chairperson shall be entitled to "
                "receive a consolidated salary of rupees four lakh fifty thousand per month. "
                "some later text")
    # The stored form drops the Gazette's separator dash — punctuation only.
    needle = ("1. Salary. (1) The Chairperson shall be entitled to receive a consolidated "
              "salary of rupees four lakh fifty thousand per month.")
    ok, ratio, reason = _ordered_match(needle, haystack)
    assert ok, f"punctuation-only difference was rejected: {reason} (ratio {ratio})"


def test_the_ordered_fallback_rejects_a_word_swap_in_a_long_passage():
    """
    The reason the word-order gate exists rather than a similarity ratio alone:
    at this length a single swapped word still scores well above 99.5%.
    """
    filler = "and the said provisions shall apply accordingly in every such case. " * 20
    haystack = "preamble " + filler + "the Chairperson shall be entitled to receive it. tail"
    needle = filler + "the Chairperson may be entitled to receive it."
    ok, ratio, reason = _ordered_match(needle, haystack)
    assert not ok, f"a shall->may swap passed with ratio {ratio:.5f}"
    assert "word difference" in (reason or "")
    # And prove the ratio alone would have waved it through.
    plain_ratio = difflib.SequenceMatcher(
        None, haystack[len("preamble "):len("preamble ") + len(needle)], needle, autojunk=False
    ).ratio()
    assert plain_ratio > ORDERED_RATIO_MIN, (
        f"the point of this test is that similarity alone is not enough; it scored "
        f"{plain_ratio:.5f}"
    )


def test_a_dropped_clause_is_caught(rules_pdf_text):
    """NEGATIVE test: removing words entirely must also be caught, not just
    swapping them."""
    stored = dict(_rules_provisions())["DPDPR-R19"]
    mutated = stored.replace("One-third of the membership of the Board shall be the quorum",
                              "the quorum", 1)
    assert mutated != stored
    assert check_rules_provision("DPDPR-R19", mutated, rules_pdf_text) != []


def test_a_known_exception_only_applies_to_its_own_exact_text(rules_pdf_text):
    """
    The point of the exception format: an exception is keyed to the exact
    string the database holds today. Change that string to something else and
    the exception stops applying, so the guard fails instead of waving it
    through. This is what stops a documented exception from hiding a new
    problem in the same place.
    """
    stored = dict(_rules_provisions())["DPDPR-SCH7"]
    assert "Data Principal for: (i) performance" in _normalize_rules(stored)
    # Same shape as the H-7 exception, different (invented) wording.
    mutated = stored.replace("of a Data Principal for:", "of a Data Principal only for:", 1)
    assert mutated != stored
    assert check_rules_provision("DPDPR-SCH7", mutated, rules_pdf_text) != []


def test_every_known_exception_is_still_needed():
    """
    Housekeeping: an exception whose database text no longer exists is dead
    weight and should be deleted (which is what happens once a data-fix
    script restores the official wording). This test names the ones that have
    become obsolete so nobody has to go looking.
    """
    stored_by_id = dict(_rules_provisions())
    stale = []
    for provision_id, entries in _KNOWN_EXCEPTIONS.items():
        norm_all = " \n ".join(
            _normalize_rules(piece) for _kind, piece in rules_pieces(stored_by_id.get(provision_id, ""))
        )
        for db_text, _pdf_text, _reason, finding in entries:
            if db_text not in norm_all:
                stale.append(f"{provision_id}: {db_text!r} ({finding})")
    assert stale == [], (
        "these reviewed exceptions no longer match anything in the database — the "
        "wording has been corrected, so delete them from _KNOWN_EXCEPTIONS:\n"
        + "\n".join(stale)
    )
