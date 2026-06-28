#!/usr/bin/env python3
"""
Regression tests for the three MEDIUM audit fixes.

#9  Near-duplicate dedup (SimHash + digit-signature guard)  -> ingestion
#10 section_title reliability (skip contact/address boilerplate) -> ingestion
#12 Conflict surfacing (provenance/dates in context header)  -> rag/context

Pure-function tests — no ML models / no network.
    .venv/bin/python tests/test_medium_fixes.py
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# ── #9 Near-duplicate dedup ───────────────────────────────────────────────────
def test_near_dup():
    print("\n=== #9 near-duplicate dedup (SimHash + digit guard) ===")
    from ingestion import _simhash, _hamming, _digit_signature, SIMHASH_NEAR_DUP_MAX_HAMMING

    a = "The college library is open from 9 am to 5 pm on all working days."
    a_reordered = "  The   college library is open   from 9 am to 5 pm on all working days.  "
    b = "Admission to the MCA programme requires a bachelor degree in any discipline."

    check("identical text -> hamming 0", _hamming(_simhash(a), _simhash(a)) == 0)
    check("whitespace variant is near-dup (hamming <= threshold)",
          _hamming(_simhash(a), _simhash(a_reordered)) <= SIMHASH_NEAR_DUP_MAX_HAMMING)
    check("unrelated text is NOT near-dup",
          _hamming(_simhash(a), _simhash(b)) > SIMHASH_NEAR_DUP_MAX_HAMMING)

    # Digit-signature guard: same wording, different numbers must NOT be merged.
    fee_a = "Tuition fee for the programme is Rs 5000 per semester."
    fee_b = "Tuition fee for the programme is Rs 6000 per semester."
    check("differing numbers -> different digit signature (never merged)",
          _digit_signature(fee_a) != _digit_signature(fee_b))
    check("same numbers -> same digit signature",
          _digit_signature("Rs 5000 fee") == _digit_signature("fee Rs 5000"))

    # Simulate the bucketed loop guard end-to-end.
    def would_skip(new_text, kept_texts):
        buckets = {}
        for t in kept_texts:
            buckets.setdefault(_digit_signature(t), []).append(_simhash(t))
        sig = _digit_signature(new_text)
        sh = _simhash(new_text)
        return any(_hamming(sh, k) <= SIMHASH_NEAR_DUP_MAX_HAMMING for k in buckets.get(sig, []))

    check("loop: whitespace near-dup is skipped", would_skip(a_reordered, [a]))
    check("loop: different-fee chunk is KEPT (not skipped)", not would_skip(fee_b, [fee_a]))
    check("loop: unrelated chunk is KEPT", not would_skip(b, [a]))


# ── #10 section_title reliability ─────────────────────────────────────────────
def test_section_title():
    print("\n=== #10 detect_section_title skips boilerplate ===")
    from ingestion import detect_section_title

    # Real heading buried below the address/contact masthead.
    buried = (
        "Bomfyle Road, Shillong, Meghalaya-793001\n"
        "Phone: 0364-2211000  Fax: 0364-2210000\n"
        "Profile of the College\n"
        "The institution was established to provide quality education.\n"
    )
    title = detect_section_title(buried)
    check("picks the real heading, not the address/phone line",
          "profile" in title.lower())
    check("does not return a phone/fax line",
          "phone" not in title.lower() and "fax" not in title.lower())

    # Keyword heading preferred over an address line.
    fees = (
        "St. Anthony's College, Shillong\n"
        "Fee Structure for Undergraduate Programmes\n"
        "The fees are payable each semester.\n"
    )
    check("keyword heading chosen", "fee" in detect_section_title(fees).lower())

    # An address-only top line should not be chosen as the section title.
    addr_first = (
        "Bomfyle Road, Shillong\n"
        "Admission Procedure\n"
        "Apply online through the portal.\n"
    )
    check("admission heading chosen over address",
          "admission" in detect_section_title(addr_first).lower())


# ── #12 Conflict surfacing (provenance in context header) ─────────────────────
def test_context_provenance():
    print("\n=== #12 context header carries provenance/dates ===")
    from rag.context import build_context

    query = "What is the admission fee?"
    doc = (
        "The admission fee for the programme is payable at the time of enrolment "
        "and is collected once at the start of the first semester."
    )
    meta = {
        "filename": "Prospectus2026.pdf",
        "page": 3,
        "source_type": "pdf",
        "document_year": 2026,
        "document_date": "2026-06-12",
        "section_title": "Fees",
    }
    context, sources = build_context(query, [doc], [meta], [0.12])
    check("context built (chunk not dropped)", bool(context))
    check("header shows source Year", "Year: 2026" in context)
    check("header shows source Type", "Type: pdf" in context)
    check("header shows source Date", "Date: 2026-06-12" in context)


if __name__ == "__main__":
    test_near_dup()
    test_section_title()
    test_context_provenance()

    print("\n" + "=" * 70)
    if failures:
        print(f"RESULT: {len(failures)} FAILED -> {failures}")
        sys.exit(1)
    print("RESULT: ALL MEDIUM-FIX TESTS PASSED")
