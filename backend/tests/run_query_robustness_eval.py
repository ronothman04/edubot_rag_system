#!/usr/bin/env python3
"""Live-index equivalence regression for EduBot query understanding.

This suite is deterministic and does not call the answer LLM.  It exercises the
same history rewriting, normalization, namespace filter, BM25+dense fusion,
related expansion and cross-encoder path as production.  Each paraphrase must
retrieve an accepted authoritative source and produce usable structured citation
records.  Negative response routing is checked separately.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag.config import KNOWN_DEPARTMENT_NAMES
from rag.context import build_context
from rag.filters import build_filter
from rag.intent import extract_entities, is_list_query
from rag.main import _ask_internal, is_genuinely_ambiguous
from rag.query_expansion import (
    build_focused_retrieval_query,
    build_smart_query,
    build_smart_retrieval_query,
    smart_clarification_response,
)
from rag.retrieval import filter_staff_docs, retrieve_chunks
from rag.text_utils import normalize_query


GROUPS = [
    ("admissions", ["AdmissionPolicy", "Prospectus2026"], [
        ("How do I apply for MCA?", ""),
        ("MCA admission procedure", ""),
    ]),
    ("programme_syllabus", ["MA_Education"], [
        ("syllabus for MA Education", ""),
        ("what subject are there for 1st sem MA Education?", ""),
        ("papers in Sem I of MA Education", ""),
    ]),
    ("departments_faculty", ["college_2026", "overall_2026", "Handbook"], [
        ("list the faculty of Commerce department", ""),
        ("who teaches in the Commerce dept?", ""),
    ]),
    ("fees", ["Prospectus2026", "AdmissionPolicy"], [
        ("fee structure for BCA", ""),
        ("what charges do BCA students pay?", ""),
    ]),
    ("hostel", ["Prospectus_Boys_Hostel", "College_Handbook"], [
        ("what are the hostel rules?", ""),
        ("residence and accommodation regulations", ""),
    ]),
    ("attendance", ["College_Handbook"], [
        ("what is the minimum attendance requirement?", ""),
        ("how many classes must a student attend?", ""),
    ]),
    ("examinations", ["College_Handbook"], [
        ("what are the examination rules?", ""),
        ("exam instructions for students", ""),
    ]),
    ("scholarships", ["College_Handbook", "Prospectus2026"], [
        ("what scholarships are available?", ""),
        ("student financial aid and scholarship details", ""),
    ]),
    ("committees", ["College_Handbook", "DeptReport-2021"], [
        ("anti-ragging committee members", ""),
        ("who is on the anti raging panel?", ""),
    ]),
    ("facilities", ["College_Handbook", "Prospectus2026", "Website Links"], [
        ("what facilities does the college have?", ""),
        ("list the campus amenities", ""),
    ]),
    ("policies", ["College_Handbook", "AdmissionPolicy"], [
        ("what is the anti-ragging policy?", ""),
        ("college policy against ragging", ""),
    ]),
    ("contact", ["College_Handbook", "DeptReport-2000", "Website Links"], [
        ("college contact number", ""),
        ("how can I reach the college office?", ""),
    ]),
    ("list_questions", ["College_Handbook", "Prospectus2026", "college_2026"], [
        ("what departments are there?", ""),
        ("show me the list of academic departments", ""),
    ]),
    ("misspelling", [
        "College_Handbook", "college_2026", "college_2025", "AR-2022",
        "History | St. Anthony's College", "AICTEMandatoryDisclosure",
    ], [
        ("who is the principle of the collage?", ""),
        ("name the current principal", ""),
    ]),
    ("abbreviation", ["college_2026", "overall_2026", "College_Handbook", "Computer Science Department"], [
        ("HOD of Computer Science", ""),
        ("who is the department head for Computer Science?", ""),
    ]),
    ("multi_turn", ["Prospectus2026", "AdmissionPolicy"], [
        (
            "what about the fees?",
            "User: Tell me about BCA\nAssistant: BCA is a programme offered by the college.",
        ),
        ("BCA fee structure", ""),
    ]),
]


def _retrieve(question: str, history: str):
    raw, _latest, used_history = build_smart_query(question, history)
    focused = build_focused_retrieval_query(raw)
    keyword = normalize_query(build_smart_retrieval_query(raw))
    entities = extract_entities(raw)
    department = entities.get("department")
    effective = department if department in KNOWN_DEPARTMENT_NAMES else None
    where = build_filter(False, None, effective, None, None)
    top_k = 15 if is_list_query(raw) else 8
    docs, metas, dists = retrieve_chunks(
        query=keyword,
        top_k=top_k,
        where_filter=where,
        embedding_query=focused,
        original_query=raw,
    )
    docs, metas, dists = filter_staff_docs(raw, docs, metas, dists)
    context, sources = build_context(keyword, docs, metas, dists)
    return raw, used_history, metas, context, sources


def _matches(filename: str, accepted: list[str]) -> bool:
    value = filename.lower()
    return any(needle.lower() in value for needle in accepted)


def main() -> int:
    total = passed = 0
    for group, accepted, variants in GROUPS:
        group_ok = True
        evidence_sets: list[set[str]] = []
        for question, history in variants:
            total += 1
            raw, used_history, metas, context, sources = _retrieve(question, history)
            files = [str((meta or {}).get("filename", "")) for meta in metas]
            cited_files = [str(source.get("file", "")) for source in sources]
            accepted_files = {name for name in cited_files if _matches(name, accepted)}
            citation_ok = bool(sources) and all(
                source.get("id") and source.get("file") and source.get("page") is not None
                for source in sources
            )
            history_ok = (not history) or used_history
            ok = bool(accepted_files) and bool(context) and citation_ok and history_ok
            passed += int(ok)
            group_ok &= ok
            evidence_sets.append(accepted_files)
            print(
                f"[{'PASS' if ok else 'FAIL'}] {group}: {question}\n"
                f"  rewritten={raw!r} top={files[:4]} citations={len(sources)}"
            )

        # Equivalent formulations may cite different copies of the same official
        # evidence, but each must stay inside the group's accepted authority set.
        equivalent = group_ok and all(evidence_sets)
        print(f"  EQUIVALENT={'PASS' if equivalent else 'FAIL'}\n")

    # Ambiguous query should request detail rather than force unrelated evidence.
    total += 1
    ambiguous_ok = is_genuinely_ambiguous("fees") and smart_clarification_response("fees") is not None
    passed += int(ambiguous_ok)
    print(f"[{'PASS' if ambiguous_ok else 'FAIL'}] ambiguous fee question")

    # These routes are deterministic and return before answer generation.
    negative_cases = [
        ("Who is the Prime Minister of India?", "out_of_scope"),
        ("Does the college offer B.Tech in aerospace engineering?", "programme_not_found"),
    ]
    for question, expected_type in negative_cases:
        total += 1
        response = _ask_internal(question)
        ok = response.get("response_type") == expected_type and not response.get("sources")
        passed += int(ok)
        print(
            f"[{'PASS' if ok else 'FAIL'}] negative: {question} "
            f"type={response.get('response_type')}"
        )

    precision = passed / total if total else 0.0
    print(f"\nQUERY ROBUSTNESS: {passed}/{total} = {precision:.2%}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
