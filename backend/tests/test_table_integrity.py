"""
Regression tests for the general table-integrity fix and the additive acronym
expansion. These lock in the behaviour that resolved the malformed "VTC course"
table answer WITHOUT any question-specific logic — every assertion below keys on
the *shape* of the data, not on a particular document, code, or query.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from rag.table_integrity import (
    find_table_blocks,
    assess_table,
    sanitize_context_tables,
    context_has_unreliable_table,
    answer_table_is_unreliable,
    degrade_answer_tables,
)
from rag.text_utils import normalize_query


# ── The exact extracted fragment that produced the bad answer ────────────────
MALFORMED_VTC = """| VTC: 367.1 | Beauty Care-III | 1 | 3 | 4 |
| VTC: 367.2 | Accessory Design-III | 1 | 3 | 4 |

| VTC: 368. | | | | |

| VTC: 369 | Others | | | |
| VTC:369.1 | Photography-III | | | |
| | | 1 | 3 | 4 |"""

PLACEHOLDER_TABLE = """| Course Code | Title | Credit Hours | Column 4 | Column 5 |
| --- | --- | --- | --- | --- |
| VTC: 369 | Others | | | |"""

GOOD_FEE_TABLE = """| Fee Category | Amount |
| --- | --- |
| Tuition Fee | 12000 |
| Library Fee | 1500 |
| Laboratory Fee | 2000 |"""

GOOD_FACULTY_TABLE = """| Name | Designation |
| --- | --- |
| Dr A Sharma | Professor |
| Dr B Roy | Assistant Professor |"""


def test_malformed_table_is_unreliable():
    blocks = find_table_blocks(MALFORMED_VTC)
    assert blocks, "should detect the table block"
    assert not assess_table(blocks[0]).reliable
    assert context_has_unreliable_table(MALFORMED_VTC)


def test_placeholder_headers_flagged():
    block = find_table_blocks(PLACEHOLDER_TABLE)[0]
    a = assess_table(block)
    assert not a.reliable
    assert "placeholder_headers" in a.reasons


def test_reliable_tables_are_preserved():
    for good in (GOOD_FEE_TABLE, GOOD_FACULTY_TABLE):
        block = find_table_blocks(good)[0]
        assert assess_table(block).reliable
        sanitized, changed = sanitize_context_tables(good)
        assert not changed
        assert sanitized == good  # untouched


def test_sanitize_degrades_only_broken_tables_in_mixed_text():
    mixed = GOOD_FEE_TABLE + "\n\nSome prose.\n\n" + MALFORMED_VTC
    sanitized, changed = sanitize_context_tables(mixed)
    assert changed
    # Good table survives verbatim.
    assert "| Tuition Fee | 12000 |" in sanitized
    # Broken table is degraded: incompleteness note present, no fabricated grid.
    assert "did not parse cleanly" in sanitized
    # Blank cells are dropped, not turned into dashes/guesses.
    assert "| | | | |" not in sanitized
    # The present values are retained as plain text.
    assert "Photography-III" in sanitized


def test_no_blank_cells_fabricated_into_dashes():
    sanitized, _ = sanitize_context_tables(MALFORMED_VTC)
    # The degraded text must not invent a credit value for VTC 368/369 rows.
    assert "VTC: 368." in sanitized
    # The "1 | 3 | 4" stray row stays as raw values, never attached to a course.
    assert "Photography-III | 1 | 3 | 4" not in sanitized


def test_answer_backstop_degrades_broken_answer_table():
    # Genuinely empty cells (the real failure mode) — NOT dashes, which can be a
    # legitimate "not applicable" marker (e.g. a syllabus with no practical hours).
    bad_answer = (
        "Here are the VTC courses:\n\n"
        "| Course Code | Title | Credit Hours |\n"
        "| --- | --- | --- |\n"
        "| VTC: 368 |  |  |\n"
        "| VTC: 368.1 |  |  |\n"
        "| VTC: 369.1 | Photography-III |  |\n"
    )
    assert answer_table_is_unreliable(bad_answer)
    fixed = degrade_answer_tables(bad_answer)
    assert "could not be confirmed" in fixed
    assert "| --- |" not in fixed  # grid removed


def test_legit_dashes_are_not_treated_as_broken():
    # A real syllabus table uses "-" to mean "no practical hours" — a valid value,
    # not a missing cell. It must stay a table.
    chem = (
        "| Course Code | Title | Theory | Practical | Total | Contact |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| CHE 350 | Inorganic Chemistry-II | 4 | - | 4 | 60 |\n"
        "| CHE 351 | Organic Chemistry-III | 4 | - | 4 | 60 |\n"
    )
    block = find_table_blocks(chem)[0]
    assert assess_table(block).reliable
    sanitized, changed = sanitize_context_tables(chem)
    assert not changed


def test_answer_backstop_leaves_good_tables_alone():
    good_answer = "Here is the fee structure:\n\n" + GOOD_FEE_TABLE
    assert not answer_table_is_unreliable(good_answer)
    assert degrade_answer_tables(good_answer) == good_answer


# ── Additive acronym expansion: exact token must survive ─────────────────────

def test_expansion_preserves_exact_acronym_token():
    norm = normalize_query("is there VTC course?")
    assert "vtc" in norm.split()                       # exact token kept for BM25
    assert "vocational" in norm                          # expansion still present


def test_expansion_preserves_exact_course_code():
    norm = normalize_query("MCA-CC-6000 syllabus")
    # The literal code tokens survive so exact-code retrieval can match.
    assert "mca" in norm.split()
    assert "cc" in norm.split()
    assert "6000" in norm.split()


def test_expansion_is_additive_not_destructive():
    norm = normalize_query("BCA eligibility")
    assert "bca" in norm.split()
    assert "bachelor of computer applications" in norm
