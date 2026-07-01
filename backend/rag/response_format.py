from __future__ import annotations

"""
rag/response_format.py
Response-format classification stage for St. Anthony's College EduBot.

Runs AFTER retrieval and reranking but BEFORE final answer generation. Looks at
the user's question together with the *final retrieved and reranked* context and
decides the most appropriate presentation format for the answer:

    paragraph | bullets | numbered_list | table | mixed

The classifier is deterministic (no extra LLM call) so it adds no latency and
never hallucinates. It returns a structured decision:

    {
        "format": "paragraph | bullets | numbered_list | table | mixed",
        "reason": "Brief explanation of why the format was selected",
        "columns": ["Only populated when format is table/mixed"],
    }

`build_format_instruction()` turns that decision into a short instruction block
that is appended to the system prompt. The instruction is advisory and always
re-states the grounding rules (never invent rows/columns, fall back to prose for
a single record, etc.) so the format choice can never override grounding.
"""

import re
from typing import Any, Dict, List, Optional, Sequence

from .config import KNOWN_DEPARTMENT_NAMES
from .scoring import _person_name_regex
from .text_utils import normalize_text


# ── Signal detectors ─────────────────────────────────────────────────────────

_COMPARISON_MARKERS = (
    "compare", "comparison", "versus", " vs ", " vs.", "vs ",
    "difference between", "differences between", "differ", "better option",
    "which is better", "pros and cons",
)

# Words that ask for a flat collection of unstructured points (no shared columns).
_BULLET_QUERY_MARKERS = (
    "documents", "document", "facilities", "facility", "features", "feature",
    "benefits", "benefit", "responsibilities", "requirements", "requirement",
    "amenities", "options", "rules", "guidelines", "what do i need",
    "what is needed", "what is required", "things needed",
)

_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*[\d,]+|\b\d{3,}(?:[.,]\d+)?\s*(?:/-|/ -|per\s+annum|p\.?a\.?)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?[\s./-]+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"(?:[\s./-]+\d{2,4})?\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.IGNORECASE,
)
_DESIGNATION_RE = re.compile(
    r"\b(?:designation|head of department|hod|professor|asst\.?\s*professor|"
    r"associate professor|assistant professor|lecturer|principal|vice[\s-]?principal|"
    r"coordinator|warden|superintendent|chairman|secretary|convenor|convener|member)\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"\b\d\s*(?:year|yr|semester|sem|month)s?\b", re.IGNORECASE
)
# Whole-word match so "show" does not register the substring "how", etc.
_EXPLANATION_RE = re.compile(
    r"\b(?:explain|why|describe|how)\b|tell me about", re.IGNORECASE
)


def _count_distinct(matches: Sequence[str]) -> int:
    return len({normalize_text(m) for m in matches if m and m.strip()})


def _count_departments(context: str) -> int:
    norm = normalize_text(context)
    return sum(1 for dept in KNOWN_DEPARTMENT_NAMES if dept in norm)


def _count_person_names(context: str) -> int:
    try:
        names = re.findall(_person_name_regex(), context or "")
    except re.error:
        return 0
    return _count_distinct(names)


def _is_comparison_query(q_norm: str) -> bool:
    return any(marker in f" {q_norm} " for marker in _COMPARISON_MARKERS)


def _wants_bullets(q_norm: str) -> bool:
    return any(marker in q_norm for marker in _BULLET_QUERY_MARKERS)


# ── Table-scenario detection ─────────────────────────────────────────────────
#
# Each scenario returns the suggested column headers when the *context* actually
# contains two or more records that share those fields. Returning None means the
# scenario does not apply or the context lacks enough structured records.

def _table_scenario(
    q_norm: str,
    context: str,
    all_intents: Sequence[str],
) -> Optional[List[str]]:
    intents = set(all_intents)

    # Departments and their heads.
    if ("department" in intents or "department" in q_norm or "departments" in q_norm) and (
        "head" in q_norm or "hod" in q_norm or "heads" in q_norm
    ):
        if _count_departments(context) >= 2 and _count_person_names(context) >= 2:
            return ["Department", "Head of Department"]

    # Faculty / staff directories.
    if "staff" in intents and (
        any(w in q_norm for w in ("list", "all", "faculty", "teachers", "members", "staff", "directory"))
    ):
        if _count_person_names(context) >= 2 and len(_DESIGNATION_RE.findall(context)) >= 2:
            cols = ["Name", "Designation"]
            if _count_departments(context) >= 2:
                cols.append("Department")
            return cols

    # Committee / cell members.
    if "committee" in intents:
        if _count_person_names(context) >= 2 and len(_DESIGNATION_RE.findall(context)) >= 2:
            return ["Name", "Designation"]

    # Fee structure with multiple categories.
    if "fees" in intents:
        if len(_AMOUNT_RE.findall(context)) >= 3:
            return ["Fee Category", "Amount"]

    # Courses / programmes with durations.
    if ("courses" in intents or "programme" in intents) and (
        "duration" in q_norm or len(_DURATION_RE.findall(context)) >= 2
    ):
        if len(_DURATION_RE.findall(context)) >= 2:
            return ["Programme", "Duration"]

    # Admission dates / deadlines.
    if ("date" in q_norm or "deadline" in q_norm or "schedule" in q_norm or "timeline" in q_norm):
        if _count_distinct(_DATE_RE.findall(context)) >= 2:
            return ["Event", "Date"]

    # Eligibility across multiple programmes.
    if "eligibility" in intents and (
        "programmes" in q_norm or "programs" in q_norm or "courses" in q_norm or "all" in q_norm
    ):
        if len(_DURATION_RE.findall(context)) >= 2 or _count_departments(context) >= 3:
            return ["Programme", "Eligibility"]

    return None


# ── Public classifier ────────────────────────────────────────────────────────

def classify_response_format(
    query: str,
    context: str,
    *,
    all_intents: Sequence[str],
    is_procedural: bool = False,
    is_person_lookup: bool = False,
    is_list: bool = False,
) -> Dict[str, Any]:
    """Decide the best presentation format from the query and final context.

    The decision is grounded in the retrieved/reranked context, not just the
    query wording: table formats are only selected when the context actually
    holds two or more records that share the relevant fields.
    """
    q_norm = normalize_text(query)
    ctx = context or ""

    # 1. Single-person / single-fact lookup → paragraph.
    if is_person_lookup and not is_list:
        return {
            "format": "paragraph",
            "reason": "Single-fact / person lookup answered in a sentence or two.",
            "columns": [],
        }

    # 2. Sequential procedure → numbered list.
    if is_procedural:
        return {
            "format": "numbered_list",
            "reason": "Procedural question; steps must be presented in order.",
            "columns": [],
        }

    # 3. Comparison → table (fall back to bullets if context is thin).
    if _is_comparison_query(q_norm):
        return {
            "format": "table",
            "reason": "Comparison request; a table aligns the items being compared.",
            "columns": [],
        }

    # 4. Multiple structured records sharing fields → table.
    columns = _table_scenario(q_norm, ctx, all_intents)
    if columns:
        # When the query also asks for explanation, lead with a sentence + table.
        wants_explanation = bool(_EXPLANATION_RE.search(q_norm))
        if wants_explanation:
            return {
                "format": "mixed",
                "reason": "Multiple shared-field records plus an explanatory ask.",
                "columns": columns,
            }
        return {
            "format": "table",
            "reason": "Context holds several records sharing common fields.",
            "columns": columns,
        }

    # 5. Flat collection of unstructured points → bullets.
    if _wants_bullets(q_norm):
        return {
            "format": "bullets",
            "reason": "Several related points without shared columns.",
            "columns": [],
        }

    # 6. General listing intent → bullets.
    if is_list:
        return {
            "format": "bullets",
            "reason": "Listing request without consistent tabular fields.",
            "columns": [],
        }

    # 7. Default → paragraph; let the model expand naturally.
    return {
        "format": "paragraph",
        "reason": "Direct answer best expressed as concise prose.",
        "columns": [],
    }


# ── Prompt instruction builder ───────────────────────────────────────────────

_COMMON_GROUNDING = (
    "Use ONLY values present in the CONTEXT — never invent rows, columns, names, "
    "dates, fees, or figures to fill a format. If the CONTEXT does not actually "
    "contain enough information for the chosen format, fall back to clear prose."
)


def build_format_instruction(decision: Dict[str, Any]) -> str:
    """Render the format decision as a system-prompt instruction block."""
    fmt = decision.get("format", "paragraph")
    columns = decision.get("columns") or []

    if fmt == "table":
        col_hint = (
            f" Suggested columns: {', '.join(columns)} — but only include a column "
            "if the CONTEXT supports it; drop any column you cannot fill from the CONTEXT."
            if columns
            else " Choose short, clear column headings supported by the CONTEXT."
        )
        body = (
            "Present the answer as a Markdown table.{col}\n"
            "- Only build the table if the CONTEXT has TWO OR MORE records; for a "
            "single record, answer in a short paragraph instead.\n"
            "- Keep headings short; do not create an excessively wide table.\n"
            "- Use \"Not specified\" for a missing cell only when necessary; never "
            "guess a value.\n"
            "- Preserve names, dates, fees, designations, and programme titles exactly.\n"
            "- Add one short introductory sentence before the table when helpful."
        ).format(col=col_hint)
    elif fmt == "mixed":
        col_hint = (
            f" Suggested table columns: {', '.join(columns)} (drop any the CONTEXT cannot fill)."
            if columns
            else ""
        )
        body = (
            "Lead with one or two sentences of explanation, then present the "
            "structured records as a Markdown table.{col}\n"
            "- Only build the table if the CONTEXT has TWO OR MORE records.\n"
            "- Keep headings short; preserve names, dates, fees, and titles exactly.\n"
            "- Never invent rows or columns to pad the table."
        ).format(col=col_hint)
    elif fmt == "bullets":
        body = (
            "Present the answer as a short Markdown bullet list, one point per line. "
            "Keep each bullet concise. Add a brief lead-in sentence if it helps."
        )
    elif fmt == "numbered_list":
        body = (
            "Present the answer as a numbered Markdown list with the steps in the "
            "exact order required. One step per line; keep each step actionable."
        )
    else:  # paragraph
        body = (
            "Answer in clear, concise prose (usually two to four sentences). Do not "
            "force a table or list when a direct paragraph answers the question."
        )

    return (
        "Response format (decided from the retrieved context):\n"
        f"- {body}\n"
        f"- {_COMMON_GROUNDING}"
    )
