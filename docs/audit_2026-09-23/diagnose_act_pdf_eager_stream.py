"""
DRAFT diagnostic (audit 2026-09-23) — NOT run by the auditor; needs Gautam's
go-ahead because it spends Anthropic credit (~$0.05 for one call).

Question it answers: when the Act-PDF classification hits
stop_reason=max_tokens with an "empty" tool call, was the model really
writing nothing — or was it writing a large `changes` array that the API
was holding back?

Why the earlier wire-level diagnostic could not tell the difference:
Anthropic's docs say that without fine-grained tool streaming, "the API
buffers and validates each parameter value before streaming it back, so
nothing prints for a large parameter until Claude has finished generating
it" (platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming).
`report_changes` has exactly one top-level parameter (`changes`), so the
WHOLE output is one parameter value. If generation is cut off by
max_tokens before that value closes, the stream shows one empty delta and
then max_tokens — exactly what was observed. That is also what you would
see if the model were enumerating dozens of paraphrase-vs-PDF "Corrections".

This script re-runs the same production prompt once, with the tool marked
`eager_input_streaming: true` (plus the legacy beta header, harmless if
the feature is GA), and prints the partial JSON as it arrives.

Usage (from repo root, with ANTHROPIC_API_KEY in .env):
    python scripts/diagnose_act_pdf_eager_stream.py
"""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import anthropic  # noqa: E402
import requests  # noqa: E402

from classify_change import (  # noqa: E402
    ANTHROPIC_API_KEY, CHANGES_TOOL, CLAUDE_MODEL, SYSTEM_PROMPT,
    _build_user_prompt, _relevant_provisions,
)
from db import get_connection  # noqa: E402
from fetch_sources import SOURCES, FetchResult, USER_AGENT, _extract_text  # noqa: E402

ACT = next(s for s in SOURCES if "2024/06" in s["url"])


def main() -> None:
    raw = requests.get(ACT["url"], headers={"User-Agent": USER_AGENT}, timeout=60).content
    text = _extract_text(raw, "pdf")
    fr = FetchResult(ACT["source"], ACT["title"], ACT["url"], "SRC-DIAG", text, "diag", True)
    conn = get_connection()
    prompt = _build_user_prompt(fr, _relevant_provisions(conn, fr))
    conn.close()

    tool = copy.deepcopy(CHANGES_TOOL)
    tool["eager_input_streaming"] = True

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    partial = io.StringIO()
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "report_changes"},
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "fine-grained-tool-streaming-2025-05-14"},
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                partial.write(event.delta.partial_json)
        final = stream.get_final_message()

    out = partial.getvalue()
    print(f"stop_reason={final.stop_reason}  usage={final.usage}")
    print(f"partial tool JSON length: {len(out)} chars")
    print(f"'provision_id' occurrences so far: {out.count('provision_id')}")
    print(f"'change_type' values seen: "
          f"{[t for t in ('Correction', 'Clarification', 'Amendment', 'Repeal', 'New Provision') if t in out]}")
    print("--- first 3000 chars ---")
    print(out[:3000])


if __name__ == "__main__":
    main()
