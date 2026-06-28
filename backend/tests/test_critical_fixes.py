#!/usr/bin/env python3
"""
Regression tests for the four CRITICAL audit fixes.

Fix 1: Query-time department namespacing  (rag/main.py wiring -> filters.build_filter)
Fix 2: Crawler domain hard-lock + SSRF    (ingestion.is_domain_allowed/is_private_ip)
Fix 3: Authority de-inversion             (rag/freshness.source_priority)
Fix 4: History-aware response cache key    (rag/cache._response_cache_key)

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


if __name__ == "__main__":
    test_fix3_source_priority()
    test_fix4_cache_key()
    test_fix2_domain_lock()
    test_fix1_namespacing()

    print("\n" + "=" * 70)
    if failures:
        print(f"RESULT: {len(failures)} FAILED -> {failures}")
        sys.exit(1)
    print("RESULT: ALL CRITICAL-FIX TESTS PASSED")
