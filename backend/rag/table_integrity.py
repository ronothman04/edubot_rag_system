"""
rag/table_integrity.py
Reusable structural-integrity validation for extracted tables.

Why this exists
---------------
PDF / website / OCR table extraction frequently produces *structurally broken*
Markdown tables: auto-named placeholder headers ("Column 4"), blank cells where
the extractor failed to align text, numeric columns merged onto one physical row,
and — because chunking can split a long table — header/separator rows detached
from the body rows. A live-index audit found this is systemic (≈1k chunks with
placeholder headers, ≈800 with blank-cell rows, ≈2.5k table-body chunks whose
header row was split into a neighbouring chunk).

When such a fragment is handed to the LLM as context, the model confidently
re-renders a *polished but fabricated* table: it invents acronym expansions,
guesses or dashes the missing cells, and mis-groups merged numeric columns.

This module is the single, general place that:
  1. parses Markdown table blocks out of arbitrary text,
  2. scores each table's structural reliability (no question-specific rules),
  3. rewrites low-confidence tables in *context* into plain "label: value" lines
     that carry only the cells actually present, plus an explicit incompleteness
     note — so the model can state the confirmed facts without re-gridding noise,
  4. detects an unreliable table in a *generated answer* for post-validation.

Nothing here is keyed to a specific document, acronym, code, or query. It keys
only on the *shape* of the extracted table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

# A header cell the extractor auto-generated because it could not read a real
# heading (pdfplumber/camelot emit "Column 1", "Column 2", …). Their presence is
# a strong signal the table structure was guessed, not read.
_PLACEHOLDER_HEADER_RE = re.compile(r"^column\s*\d+$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")


def _is_separator(line: str) -> bool:
    return bool(_SEPARATOR_RE.match(line.strip()))


def _split_row(line: str) -> List[str]:
    """Split one Markdown table line into trimmed cell strings."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _cell_has_content(cell: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9₹]", cell or ""))


@dataclass
class TableBlock:
    """A contiguous run of Markdown table lines found in some text."""

    start: int                       # line index of first table line (inclusive)
    end: int                         # line index after last table line (exclusive)
    rows: List[List[str]]            # parsed cell grid (separator rows removed)
    has_separator: bool              # was a |---|---| row present?
    raw: str = ""                    # original text of the block


@dataclass
class TableAssessment:
    reliable: bool
    confidence: float                # 0.0 – 1.0
    reasons: List[str] = field(default_factory=list)


def find_table_blocks(text: str) -> List[TableBlock]:
    """Return every contiguous Markdown table block in ``text``.

    A table block is a maximal run of consecutive lines that each look like a
    Markdown table row (start with "|" or are a |---| separator). Blank lines end
    a block — but a single blank line *between* two pipe runs is tolerated,
    because extraction often inserts one when a long cell wraps.
    """
    if not text or "|" not in text:
        return []

    lines = text.splitlines()
    blocks: List[TableBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        if not _looks_like_row(lines[i]):
            i += 1
            continue
        start = i
        j = i
        blank_run = 0
        last_row = i
        while j < n:
            ln = lines[j]
            if _looks_like_row(ln):
                last_row = j
                blank_run = 0
                j += 1
            elif ln.strip() == "" and blank_run == 0:
                blank_run = 1
                j += 1
            else:
                break
        block_lines = lines[start:last_row + 1]
        rows: List[List[str]] = []
        has_sep = False
        for bl in block_lines:
            if not _looks_like_row(bl):
                continue
            if _is_separator(bl):
                has_sep = True
                continue
            rows.append(_split_row(bl))
        if rows:
            blocks.append(
                TableBlock(
                    start=start,
                    end=last_row + 1,
                    rows=rows,
                    has_separator=has_sep,
                    raw="\n".join(block_lines),
                )
            )
        i = last_row + 1
    return blocks


def _looks_like_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def assess_table(block: TableBlock) -> TableAssessment:
    """Score a parsed table's structural reliability.

    A row is treated as reliable only when its cells align with a real header,
    required cells are filled, it is not a duplicated header, and it is not an
    obvious extraction artefact. The score aggregates those row-level signals
    plus table-level signals (placeholder headers, detached header, column-count
    consistency). Returns reliability + reasons; thresholds are intentionally
    lenient so genuinely-good tables are never degraded.
    """
    rows = block.rows
    reasons: List[str] = []
    if not rows:
        return TableAssessment(False, 0.0, ["no rows"])

    # Header = first non-empty row.
    header = rows[0]
    data_rows = rows[1:]
    n_cols = len(header)

    # 1. Placeholder ("Column N") headers → extractor guessed the structure.
    placeholder_headers = sum(1 for c in header if _PLACEHOLDER_HEADER_RE.match(c or ""))
    if n_cols and placeholder_headers / n_cols >= 0.4:
        reasons.append("placeholder_headers")

    # 2. Detached header: a multi-column body with no separator row usually means
    #    the real header/separator was split into an adjacent chunk.
    if not block.has_separator and n_cols >= 2:
        reasons.append("detached_header")

    # 3. Blank-cell density across data rows.
    if data_rows:
        total_cells = 0
        empty_cells = 0
        ragged = 0
        repeated_header = 0
        for r in data_rows:
            if len(r) != n_cols:
                ragged += 1
            total_cells += len(r)
            empty_cells += sum(1 for c in r if not _cell_has_content(c))
            if [c.lower() for c in r] == [c.lower() for c in header] and any(header):
                repeated_header += 1
        empty_ratio = empty_cells / total_cells if total_cells else 1.0
        if empty_ratio >= 0.35:
            reasons.append("blank_cells")
        if ragged / len(data_rows) >= 0.4:
            reasons.append("ragged_rows")
        if repeated_header:
            reasons.append("repeated_header_rows")
    else:
        reasons.append("no_data_rows")

    # 4. Effectively single-column (every data row has content in only one cell):
    #    the grid collapsed and column meaning was lost.
    if data_rows and n_cols >= 2:
        multi_col_rows = sum(
            1 for r in data_rows if sum(1 for c in r if _cell_has_content(c)) >= 2
        )
        if multi_col_rows == 0:
            reasons.append("single_column_collapse")

    # Confidence: start at 1.0, subtract per distinct structural defect.
    penalty = {
        "placeholder_headers": 0.5,
        "detached_header": 0.45,
        "blank_cells": 0.4,
        "ragged_rows": 0.3,
        "repeated_header_rows": 0.2,
        "single_column_collapse": 0.5,
        "no_data_rows": 0.6,
    }
    confidence = 1.0 - sum(penalty.get(r, 0.0) for r in set(reasons))
    confidence = max(0.0, min(1.0, confidence))
    reliable = confidence >= 0.6 and "placeholder_headers" not in reasons
    return TableAssessment(reliable, confidence, sorted(set(reasons)))


_INCOMPLETE_NOTE = (
    "[Note: the figures below were extracted from a table that did not parse "
    "cleanly. Some cells are missing or misaligned. Use ONLY the values clearly "
    "shown, present them as plain text (not a polished table), and say which "
    "details are not available rather than guessing or filling blanks.]"
)


def _degrade_block_to_text(block: TableBlock) -> str:
    """Render an unreliable table as plain text carrying only present cells.

    Drops the grid so the model is not tempted to reproduce a clean table from
    broken structure. Each row becomes a " - a | b | c" line with empty cells
    omitted; a leading note flags the incompleteness.
    """
    out_lines: List[str] = [_INCOMPLETE_NOTE]
    for r in block.rows:
        present = [c for c in r if _cell_has_content(c)]
        if not present:
            continue
        out_lines.append(" - " + " | ".join(present))
    return "\n".join(out_lines)


def sanitize_context_tables(text: str) -> Tuple[str, bool]:
    """Rewrite low-confidence Markdown tables in *context* into plain text.

    Returns ``(sanitized_text, changed)``. Reliable tables are left untouched, so
    valid fee/faculty/eligibility tables keep rendering as tables. Only tables
    that fail :func:`assess_table` are degraded. This runs at query time on the
    retrieved chunk text, so it needs no re-ingestion.
    """
    if not text:
        return text, False
    blocks = find_table_blocks(text)
    if not blocks:
        return text, False

    lines = text.splitlines()
    # Replace from the bottom up so earlier indices stay valid.
    changed = False
    for block in sorted(blocks, key=lambda b: b.start, reverse=True):
        assessment = assess_table(block)
        if assessment.reliable:
            continue
        replacement = _degrade_block_to_text(block).splitlines()
        lines[block.start:block.end] = replacement
        changed = True
    return "\n".join(lines), changed


def context_has_unreliable_table(text: str) -> bool:
    """True if any Markdown table in the text fails the integrity check."""
    return any(not assess_table(b).reliable for b in find_table_blocks(text))


_ANSWER_INCOMPLETE_NOTE = (
    "Some of these details could not be confirmed from the available college "
    "resources, so only the clearly stated values are shown below:"
)


def degrade_answer_tables(answer: str) -> str:
    """Backstop: rewrite any structurally-broken table in a generated answer.

    If the model still emits a malformed table despite the grounding rules, this
    replaces that table with a plain bulleted list of the cells that are actually
    present plus a user-facing note. Reliable tables are left exactly as written.
    """
    if not answer:
        return answer
    blocks = find_table_blocks(answer)
    if not blocks:
        return answer
    lines = answer.splitlines()
    for block in sorted(blocks, key=lambda b: b.start, reverse=True):
        a = assess_table(block)
        if not (
            "placeholder_headers" in a.reasons
            or "blank_cells" in a.reasons
            or "single_column_collapse" in a.reasons
        ):
            continue
        replacement = [_ANSWER_INCOMPLETE_NOTE]
        for r in block.rows:
            present = [c for c in r if _cell_has_content(c) and not _PLACEHOLDER_HEADER_RE.match(c)]
            if present:
                replacement.append("- " + " — ".join(present))
        lines[block.start:block.end] = replacement
    return "\n".join(lines)


def answer_table_is_unreliable(answer: str) -> bool:
    """Post-validation: did the model emit a structurally broken table?

    Conservative on purpose — only flags tables that leak placeholder headers or
    whose data rows are mostly empty, so well-formed answer tables are never
    touched.
    """
    for block in find_table_blocks(answer or ""):
        a = assess_table(block)
        if "placeholder_headers" in a.reasons or "blank_cells" in a.reasons or \
           "single_column_collapse" in a.reasons:
            return True
    return False
