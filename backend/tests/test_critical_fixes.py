#!/usr/bin/env python3
"""
Regression tests for critical retrieval and security fixes.

Fix 1: Query-time department namespacing  (rag/main.py wiring -> filters.build_filter)
Fix 2: Crawler domain hard-lock + SSRF    (ingestion.is_domain_allowed/is_private_ip)
Fix 3: Authority de-inversion             (rag/freshness.source_priority)
Fix 4: History-aware response cache key    (rag/cache._response_cache_key)
Fix 5: College-history retrieval grounding (rag/retrieval.py)
Fix 6: Current role-holder freshness + clean answer text

Pure-function tests only — no ML models / no network. Run:
    .venv/bin/python tests/test_critical_fixes.py
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

failures = []


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        failures.append(name)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 3 — Authority de-inversion
# ──────────────────────────────────────────────────────────────────────────────
def test_fix3_source_priority():
    print("\n=== Fix 3: source_priority authority tiers ===")
    from rag.freshness import source_priority

    pdf = source_priority({"source_type": "pdf", "file_type": "pdf"})
    website = source_priority({"source_type": "website", "file_type": "website"})
    links = source_priority({"source_type": "website_links", "file_type": "website_links"})
    upload_docx = source_priority({"source_type": "upload", "file_type": "docx"})

    # Official PDF must no longer rank BELOW website nav/links (the audited inversion).
    check("pdf is top authority (100)", pdf == 100)
    check("official website co-equal with pdf", website == pdf)
    check("uploaded doc no longer bottom (was 25)", upload_docx == 100)
    check("website_links (nav boilerplate) demoted below official docs", links < pdf)
    check("website_links strictly low (<=20)", links <= 20)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 4 — History-aware response cache key
# ──────────────────────────────────────────────────────────────────────────────
def test_fix4_cache_key():
    print("\n=== Fix 4: response cache key includes conversation context ===")
    from rag.cache import _response_cache_key

    q = "what about the fees?"
    h1 = {"history": "User: tell me about the hostel\nAssistant: ok"}
    h2 = {"history": "User: tell me about MCA\nAssistant: ok"}

    # Same vague follow-up in two different conversations must NOT collide.
    check("follow-up keys differ across conversations",
          _response_cache_key(q, h1) != _response_cache_key(q, h2))

    # Standalone question (no history) keeps a stable, shareable key.
    check("no-history key is stable / shareable",
          _response_cache_key("what are the fees", None)
          == _response_cache_key("what are the fees", {"history": ""}))

    # A no-history question and the same text mid-conversation are correctly distinct.
    check("history presence changes the key",
          _response_cache_key(q, None) != _response_cache_key(q, h1))


# ──────────────────────────────────────────────────────────────────────────────
# Fix 2 — Crawler domain hard-lock + SSRF hardening
# ──────────────────────────────────────────────────────────────────────────────
def test_fix2_domain_lock():
    print("\n=== Fix 2: crawler domain hard-lock ===")
    from ingestion import (
        is_domain_allowed,
        is_private_ip,
        is_allowed_crawl_url,
        ingest_website,
    )

    check("official domain allowed", is_domain_allowed("https://anthonys.ac.in/admissions"))
    check("subdomain allowed", is_domain_allowed("https://admissions.anthonys.ac.in/x"))
    check("off-domain blocked", not is_domain_allowed("https://evil.com/page"))
    check("path-spoofed host blocked", not is_domain_allowed("https://evil.com/anthonys.ac.in"))
    check("suffix-spoofed host blocked", not is_domain_allowed("https://notanthonys.ac.in.evil.com/"))

    check("cloud metadata IP blocked (SSRF)", is_private_ip("http://169.254.169.254/latest/meta-data"))
    check("loopback blocked", is_private_ip("http://127.0.0.1/"))
    check("localhost blocked", is_private_ip("http://localhost/"))
    check("rfc1918 blocked", is_private_ip("http://192.168.1.10/"))
    check("public college host not flagged private", not is_private_ip("https://anthonys.ac.in/"))
    check("no IPv6 false-positive on 'fc...' hostname", not is_private_ip("https://fcollege.com/"))

    check("is_allowed_crawl_url permits college page", is_allowed_crawl_url("https://anthonys.ac.in/notices"))
    check("is_allowed_crawl_url blocks off-domain page", not is_allowed_crawl_url("https://evil.com/notices"))

    raised = False
    try:
        ingest_website("https://evil.com/")
    except ValueError:
        raised = True
    except Exception as exc:  # any other error means it got past the guard
        print(f"   (unexpected non-ValueError before guard: {type(exc).__name__})")
    check("ingest_website refuses off-domain start url", raised)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 1 — Query-time department namespacing building blocks
# ──────────────────────────────────────────────────────────────────────────────
def test_fix1_namespacing():
    print("\n=== Fix 1: department namespacing ===")
    from rag.intent import extract_department_from_query
    from rag.filters import build_filter
    from rag.config import KNOWN_DEPARTMENT_NAMES

    dept = extract_department_from_query("who are the teaching staff of chemistry?")
    check("department detected from query", dept == "chemistry")
    check("detected department is a known department", str(dept).lower() in KNOWN_DEPARTMENT_NAMES)

    wf = build_filter(False, None, dept, None, None)
    # Expect {"department": {"$in": ["chemistry", "general"]}}
    in_list = (wf or {}).get("department", {}).get("$in", [])
    check("filter scopes to detected department", "chemistry" in in_list)
    check("filter keeps 'general' eligible (recall not starved)", "general" in in_list)

    # A generic query must NOT trigger a department namespace.
    generic = extract_department_from_query("what are the college fees")
    check("generic query yields no department namespace",
          not (generic and str(generic).lower() in KNOWN_DEPARTMENT_NAMES))


# ──────────────────────────────────────────────────────────────────────────────
# Fix 5 — College-history queries must reject literal but unrelated matches
# ──────────────────────────────────────────────────────────────────────────────
def test_fix5_college_history_grounding():
    print("\n=== Fix 5: college-history retrieval grounding ===")
    from rag.retrieval import _is_college_history_query, _has_college_history_evidence

    query = "Can you give a short history of the college?"
    check("institutional-history query detected", _is_college_history_query(query))
    check(
        "crawled college history page accepted",
        _has_college_history_evidence(
            "Fr. Joseph Bacchiarello started the college in 1934.",
            {"source_url": "https://anthonys.ac.in/pages/college/history.php"},
        ),
    )
    check(
        "unrelated literal 'A Short History' match rejected",
        not _has_college_history_evidence(
            "A Short History of English Poetry, Trinity Press.",
            {"filename": "dob_AddedBooks-2016.pdf"},
        ),
    )
    check(
        "History-department request remains distinct",
        not _is_college_history_query("Show the History department syllabus"),
    )


def test_fix6_current_role_and_inline_citations():
    print("\n=== Fix 6: current role evidence and separate sources ===")
    from rag.answer_builders import build_current_principal_answer
    from rag.scoring import current_role_evidence_score
    from rag.text_utils import postprocess_answer

    query = "Who is the present principal of the college?"
    current = (
        "Fr. Arcadius took over as the 9th Principal of the college in June, 2024."
    )
    old_table = (
        "Dr. Br. Albert Longley Dkhar | Principal / Chairman | Examination Committee"
    )
    check(
        "explicit current-tenure evidence outranks an older designation table",
        current_role_evidence_score(query, current)
        > current_role_evidence_score(query, old_table),
    )

    cleaned = postprocess_answer(
        "The present principal is Fr. Arcadius Puwein "
        "(College Handbook 2023-24, p. 48, 58, 55)."
    )
    check("inline document/page citation removed", "p. 48" not in cleaned and "Handbook" not in cleaned)
    check("answer fact remains after citation removal", "Fr. Arcadius Puwein" in cleaned)

    attribution_cleaned = postprocess_answer(
        "Fr. Arcadius is the present principal, as mentioned in the college history page."
    )
    check("inline source-attribution clause removed", "mentioned in" not in attribution_cleaned)

    principal_answer = build_current_principal_answer(
        query,
        "Fr. Arcadius Puwein SDB, PhD Principal of St. Anthony's College",
    )
    check(
        "current principal builder uses the full supported name",
        principal_answer == "The present principal of St. Anthony's College is Fr. Arcadius Puwein SDB, PhD.",
    )


def test_fix7_followup_word_boundaries():
    print("\n=== Fix 7: follow-up reference markers use word boundaries ===")
    from rag.query_expansion import build_smart_query, is_followup_query
    from unittest.mock import patch

    query = "what facilities does the college provide"
    history = "User: why should I take admission?\nAssistant: Previous admission answer"
    with patch("llm.generate", return_value=query):
        retrieval_query, _latest, used_history = build_smart_query(query, history)

    check("facilities is a standalone topic, not an 'it' follow-up", not is_followup_query(query))
    check("standalone facilities query is preserved", retrieval_query == query)
    check("unrelated conversation history is not used", used_history is False)
    check("real 'what about it' reference remains a follow-up", is_followup_query("what about it"))


def test_fix8_followup_topic_resolution():
    print("\n=== Fix 8: follow-up topic resolution via LLM query rewriting ===")
    from rag.query_expansion import build_smart_query
    from unittest.mock import patch

    query = "who is the head of department"
    history = "User: tell me about the Department of commerce\nAssistant: The Commerce department was established in 1948."

    with patch("llm.generate", return_value="who is the head of the Commerce department") as mock_gen:
        retrieval_query, latest, used_history = build_smart_query(query, history)
        
        check("retrieval query incorporates department context", "Commerce" in retrieval_query)
        check("retrieval query is rewritten correctly", retrieval_query == "who is the head of the Commerce department")
        check("used_history is flagged as True", used_history is True)
        check("mock_gen was called", mock_gen.called)


if __name__ == "__main__":
    test_fix3_source_priority()
    test_fix4_cache_key()
    test_fix2_domain_lock()
    test_fix1_namespacing()
    test_fix5_college_history_grounding()
    test_fix6_current_role_and_inline_citations()
    test_fix7_followup_word_boundaries()
    test_fix8_followup_topic_resolution()

    print("\n" + "=" * 70)
    if failures:
        print(f"RESULT: {len(failures)} FAILED -> {failures}")
        sys.exit(1)
    print("RESULT: ALL CRITICAL-FIX TESTS PASSED")
