"""
Word-level diff shared by export_word.py (docx highlighting) and notify.py
(email before/after snippets), so the two always agree on what "the words
that changed" means for a given regulatory change.
"""
from __future__ import annotations

import difflib
import re


def diff_words(old_words: list[str], new_words: list[str], min_common: int = 2):
    """
    Word-level diff between two token lists. Returns a list of
    (words, style) tuples, style in {'equal', 'delete', 'insert'}, with a
    'delete' segment always emitted immediately before its corresponding
    'insert' segment (removed words shown inline just before the text that
    replaced them).

    A matching block shorter than `min_common` words is NOT trusted as
    "unchanged" and is folded into the surrounding changed region instead.
    This matters for phrase-level corrections like corrigendum G.S.R.
    892(E)'s "of this Gazette" -> "in the Official Gazette": both phrases
    happen to share the single word "Gazette", but treating that lone
    coincidental match as "unchanged" would highlight only "in the
    Official" and strike only "of this", splitting the word "Gazette" away
    from the phrase it belongs to. Requiring at least 2 matching words
    before trusting a block as genuinely unchanged avoids that, while
    still correctly isolating a real single-word insertion like Rule
    23(1)'s "given in such" -> "given in such order" (3 unchanged words is
    a trustworthy match) down to just the new word "order".
    """
    sm = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    segments = []
    pending_old, pending_new = [], []

    def flush():
        if pending_old:
            segments.append((pending_old[:], "delete"))
            pending_old.clear()
        if pending_new:
            segments.append((pending_new[:], "insert"))
            pending_new.clear()

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" and (i2 - i1) >= min_common:
            flush()
            segments.append((new_words[j1:j2], "equal"))
        elif tag == "equal":
            pending_old.extend(old_words[i1:i2])
            pending_new.extend(new_words[j1:j2])
        elif tag == "replace":
            pending_old.extend(old_words[i1:i2])
            pending_new.extend(new_words[j1:j2])
        elif tag == "delete":
            pending_old.extend(old_words[i1:i2])
        elif tag == "insert":
            pending_new.extend(new_words[j1:j2])
    flush()
    return segments


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"\S+", text or "")


def change_snippet(old_full_text: str, new_full_text: str, context_words: int = 4) -> tuple[str, str]:
    """
    Short before/after snippet of just the changed words plus a little
    context, e.g. old_full_text="given in such", new_full_text="given in
    such order" -> ("…given in such", "…given in such order"). Used for
    the notification email, where showing the whole clause would bury the
    one word that actually changed.
    """
    old_words = tokenize_words(old_full_text)
    new_words = tokenize_words(new_full_text)
    segments = diff_words(old_words, new_words)

    old_flat: list[tuple[str, bool]] = []
    new_flat: list[tuple[str, bool]] = []
    for words, style in segments:
        if style == "equal":
            old_flat.extend((w, False) for w in words)
            new_flat.extend((w, False) for w in words)
        elif style == "delete":
            old_flat.extend((w, True) for w in words)
        elif style == "insert":
            new_flat.extend((w, True) for w in words)

    def render_side(flat):
        if not flat:
            return ""
        if not any(changed for _, changed in flat):
            return " ".join(w for w, _ in flat)
        changed_idxs = [i for i, (_, c) in enumerate(flat) if c]
        first, last = changed_idxs[0], changed_idxs[-1]
        start = max(0, first - context_words)
        end = min(len(flat), last + 1 + context_words)
        text = " ".join(w for w, _ in flat[start:end])
        if start > 0:
            text = "…" + text
        if end < len(flat):
            text = text + "…"
        return text

    return render_side(old_flat), render_side(new_flat)
