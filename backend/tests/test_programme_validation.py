"""
tests/test_programme_validation.py

Grounded tests for the programme-availability / anti-hallucination layer and the
crawler depth fix. These tests exercise the deterministic logic only (no LLM, no
vector DB, no network), so they run fast and offline.

Run directly:    python tests/test_programme_validation.py
Or with pytest:  pytest tests/test_programme_validation.py
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from rag.intent import (  # noqa: E402
    detect_programme,
    programme_grounded_in_docs,
    is_programme_specific_query,
    is_programme_availability_query,
)
from rag.responses import programme_not_found_response  # noqa: E402
from ingestion import is_document_url, is_pdf_url  # noqa: E402


# --------------------------------------------------------------------------- #
# Test data: what the college actually offers (as it would appear in chunks).
# BCA / B.Tech / MBA are intentionally absent (not offered).
# --------------------------------------------------------------------------- #
OFFERED_DOCS = [
    "St. Anthony's College offers Bachelor of Arts (BA), Bachelor of Science (B.Sc.) "
    "and Bachelor of Commerce (B.Com.) under the undergraduate stream.",
    "Postgraduate programmes: Master of Arts (MA) and Master of Commerce (M.Com.).",
    "The college also runs a Bachelor of Business Administration (BBA) programme.",
    "Admission office: contact admissions@example.edu, phone 0364-2222222.",
    "Departments include Physics, Chemistry, Botany, Zoology, Commerce and English.",
]


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    assert cond, name


# --------------------------------------------------------------------------- #
# 1. Programme availability detection
# --------------------------------------------------------------------------- #
def test_programme_detection():
    check("BCA detected", detect_programme("I want admission in BCA") == "BCA")
    check("B.Tech (dotted) detected", detect_programme("Is B.Tech available?") == "BTech")
    check("MBA detected", detect_programme("Is MBA offered?") == "MBA")
    check("BBA detected", detect_programme("Is BBA available?") == "BBA")
    check("no false positive on generic list query",
          detect_programme("What undergraduate courses are available?") is None)
    check("no false positive on HOD query",
          detect_programme("Who is the HOD of Computer Science?") is None)


# --------------------------------------------------------------------------- #
# 2. Grounding against retrieved content (AVAILABLE vs NOT_AVAILABLE)
# --------------------------------------------------------------------------- #
def test_grounding():
    # AVAILABLE: programme present in retrieved docs
    check("BBA grounded (offered)", programme_grounded_in_docs("BBA", OFFERED_DOCS) is True)
    check("BA grounded via full form", programme_grounded_in_docs("BA", OFFERED_DOCS) is True)
    # NOT_AVAILABLE: programme absent from retrieved docs
    check("BCA NOT grounded", programme_grounded_in_docs("BCA", OFFERED_DOCS) is False)
    check("BTech NOT grounded", programme_grounded_in_docs("BTech", OFFERED_DOCS) is False)
    check("MBA NOT grounded", programme_grounded_in_docs("MBA", OFFERED_DOCS) is False)
    # NOT_FOUND_IN_DOCUMENTS: no docs at all
    check("empty docs => not grounded", programme_grounded_in_docs("BA", []) is False)


# --------------------------------------------------------------------------- #
# 3. Query-type classification
# --------------------------------------------------------------------------- #
def test_query_classification():
    check("admission query is programme-specific",
          is_programme_specific_query("How can I get admitted in BCA?"))
    check("availability query is programme-specific",
          is_programme_specific_query("Is B.Tech available?"))
    check("availability flagged", is_programme_availability_query("Is MBA offered?"))
    check("admission NOT flagged as availability",
          not is_programme_availability_query("How can I get admitted in BCA?"))


# --------------------------------------------------------------------------- #
# 4. Anti-hallucination response (admission flavor)
# --------------------------------------------------------------------------- #
def test_admission_response_is_grounded_refusal():
    r = programme_not_found_response("BCA", query="How can I get admitted in BCA?", availability=False)
    ans = r["answer"]
    check("response_type is programme_not_found", r["response_type"] == "programme_not_found")
    check("names the programme", "BCA" in ans)
    check("says could not find", ("could not find" in ans.lower()) or ("couldn't find" in ans.lower()))
    check("refuses admission advice",
          ("cannot verify admission" in ans.lower())
          or ("can't confirm any admission requirements" in ans.lower()))
    check("offers follow-ups", "You may ask:" in ans)
    # Must NOT fabricate admission details
    for leaked in ["eligibility criteria", "application fee is", "seats available", "last date"]:
        check(f"no fabricated detail: {leaked!r}", leaked.lower() not in ans.lower())


# --------------------------------------------------------------------------- #
# 5. Availability response (NOT_AVAILABLE flavor)
# --------------------------------------------------------------------------- #
def test_availability_response():
    r = programme_not_found_response("BTech", query="Is B.Tech available?", availability=True)
    ans = r["answer"]
    check("uses display name B.Tech", "B.Tech" in ans)
    check("says not listed/offered",
          ("not listed" in ans.lower())
          or ("doesn't appear" in ans.lower())
          or ("not offered" in ans.lower()))
    check("offers follow-ups", "You may ask:" in ans)


# --------------------------------------------------------------------------- #
# 6. Crawler depth fix: documents/PDFs must bypass the page-depth limit
#    (regression test for the missing-PDF-content bug).
# --------------------------------------------------------------------------- #
def _passes_depth_gate(url, depth, max_depth):
    """Mirror of the dequeue predicate in crawl4ai_crawler.py after the fix."""
    if depth > max_depth and not (is_document_url(url) or is_pdf_url(url)):
        return False
    return True


def test_crawler_depth_fix():
    max_depth = 3
    # HTML page beyond max depth is still dropped (unchanged behavior)
    check("deep html page dropped",
          _passes_depth_gate("https://x.edu/a/b/c/d/e", depth=4, max_depth=max_depth) is False)
    # PDF/doc beyond max depth is NOT dropped (the fix)
    check("deep pdf kept",
          _passes_depth_gate("https://x.edu/files/prospectus.pdf", depth=4, max_depth=max_depth) is True)
    check("deep doc (download.php) kept",
          _passes_depth_gate("https://x.edu/download.php?file=fees", depth=5, max_depth=max_depth) is True)
    # Within-depth pages always pass
    check("shallow page kept",
          _passes_depth_gate("https://x.edu/admission", depth=1, max_depth=max_depth) is True)


def main():
    tests = [
        test_programme_detection,
        test_grounding,
        test_query_classification,
        test_admission_response_is_grounded_refusal,
        test_availability_response,
        test_crawler_depth_fix,
    ]
    for t in tests:
        print(f"\n=== {t.__name__} ===")
        t()
    print("\nAll programme-validation & crawler-depth tests passed.")


if __name__ == "__main__":
    main()
