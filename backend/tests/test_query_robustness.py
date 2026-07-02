"""Deterministic regressions for general query understanding and provenance."""

from __future__ import annotations

from unittest.mock import patch

from rag.intent import detect_query_intents, is_list_query, is_eligibility_query, is_exam_query
from rag.main import resolve_answer_citations
from rag.query_expansion import (
    build_focused_retrieval_query,
    build_smart_query,
    extract_query_constraints,
)
from rag.retrieval import _curriculum_evidence_matches, _extract_exact_codes
from rag.text_utils import normalize_query


def test_semester_forms_are_canonical_and_constraints_survive():
    variants = ["first semester", "semester 1", "Sem I", "1st sem"]
    for variant in variants:
        query = f"what papers are in {variant} MA Education"
        normalized = normalize_query(query)
        constraints = extract_query_constraints(query)
        assert "first semester" in normalized
        assert constraints["programme"] == "MA"
        assert constraints["department"] == "education"
        assert constraints["semester"] == "first"
        assert constraints["document_type"] == "syllabus"


def test_curriculum_synonyms_share_intent_and_canonical_semantics():
    variants = [
        "syllabus for MA Education",
        "what subjects are there for first semester MA Education",
        "MA Education semester 1 course list",
        "papers in Sem I of MA Education",
        "first semester MA Education modules",
        "MA Education curriculum for 1st sem",
    ]
    focused = [build_focused_retrieval_query(query) for query in variants]
    for query, semantic_query in zip(variants, focused):
        assert detect_query_intents(query)[0] == "courses"
        assert "ma" in semantic_query
        assert "education" in semantic_query
        assert "syllabus course structure" in semantic_query
    assert is_list_query(variants[1])
    assert is_list_query(variants[2])


def test_conservative_spelling_repair_preserves_unknown_entities_and_codes():
    normalized = normalize_query(
        "elgibility and syllbus for BCA in the educaton departmnt CSC-352"
    )
    assert "eligibility" in normalized
    assert "syllabus" in normalized
    assert "education" in normalized
    assert "department" in normalized
    assert "bca" in normalized
    assert "csc 352" in normalized

    # A name/unknown entity is not in the intent vocabulary and must survive.
    assert "nongkynrih" in normalize_query("Nongkynrih contact")


def test_common_requested_concepts_normalize_without_entity_loss():
    cases = {
        "HOD of Commerce": ("commerce", "head of department"),
        "charges for BCA": ("bca", "fee structure charges"),
        "residence rules": ("residence", "hostel accommodation"),
        "faculty in Physics": ("physics", "faculty teaching staff"),
        "how can I reach the college office?": ("reach", "contact information"),
        "list the campus amenities": ("amenities", "campus facilities amenities"),
        "how many classes must students attend?": ("classes", "attendance requirements"),
    }
    for query, expected in cases.items():
        focused = build_focused_retrieval_query(query)
        assert expected[0] in focused
        assert expected[1] in focused


def test_eligibility_and_exact_code_signals_are_not_misrouted():
    query = "qualifying examination for commerce"
    assert is_eligibility_query(query)
    assert not is_exam_query(query)
    assert "qualifying examination" in build_focused_retrieval_query(query)

    code_query = "MCA-CC-6000"
    assert _extract_exact_codes(code_query) == ["mcacc6000"]
    focused = build_focused_retrieval_query(code_query)
    assert "mca cc 6000" in focused


def test_vocational_training_list_queries_keep_list_and_vtc_signal():
    query = "what vocational training courses are offered"
    assert is_list_query(query)
    focused = build_focused_retrieval_query(query)
    assert "vtc" in focused
    assert "vocational training course" in focused
    assert "paper" in focused


def test_followups_resolve_deterministically_and_standalone_queries_do_not_rewrite():
    history = (
        "User: Tell me about MA Education\n"
        "Assistant: It is a postgraduate programme."
    )
    with patch("llm.generate") as generate:
        rewritten, latest, used = build_smart_query("what about the fees?", history)
        assert used is True
        assert latest == "what about the fees?"
        assert "fees" in rewritten.lower()
        assert "ma" in rewritten.lower()
        assert "education" in rewritten.lower()
        generate.assert_not_called()

        standalone = "what facilities does the college provide"
        rewritten, _latest, used = build_smart_query(standalone, history)
        assert rewritten == standalone
        assert used is False
        generate.assert_not_called()


def test_incomplete_role_followup_inherits_department_without_llm():
    history = (
        "User: tell me about the Department of Commerce\n"
        "Assistant: The department offers undergraduate programmes."
    )
    with patch("llm.generate") as generate:
        rewritten, _latest, used = build_smart_query(
            "who is the head of department", history
        )
    assert used is True
    assert "commerce" in rewritten.lower()
    generate.assert_not_called()


def test_curriculum_evidence_gate_rejects_profile_keyword_collision():
    query = "what subject are there for 1st sem MA Education?"
    profile = (
        "Academic Profile. Educational Subject Year of Passing University. "
        "Assistant Professor in the Department of Education."
    )
    syllabus = (
        "Department of Education. Structure of NEW MA Syllabus. FIRST SEMESTER. "
        "Course Code EDN-CC 500 Philosophical Foundations of Education."
    )
    assert not _curriculum_evidence_matches(
        query, profile, {"filename": "faculty_profile.pdf", "department": "education"}
    )
    assert _curriculum_evidence_matches(
        query, syllabus, {"filename": "MA_Education.pdf", "department": "education"}
    )


def test_current_principal_resolves_to_most_recent_tenure_not_stale_majority():
    """The current principal is elected by tenure ordinal ("Nth Principal"), so a
    former principal named across many stale documents can never win the vote."""
    from rag.answer_builders import resolve_current_principal, build_current_principal_answer

    name = resolve_current_principal()
    if name is None:
        # No tenure evidence in the corpus (e.g. empty index) -> nothing to assert.
        return
    lowered = name.lower()
    # The former (8th) principal must not be returned for a current-principal query.
    assert "longley" not in lowered and "albert" not in lowered

    for query in ("Who is the current principal?", "Who is the principal of the college?"):
        answer = build_current_principal_answer(query, "")
        assert answer and name in answer
        assert "longley" not in answer.lower()

    # A *vice* principal question must never be hijacked by the principal builder.
    assert build_current_principal_answer("Who is the vice principal?", "") is None


def test_course_token_grounding_uses_unexpanded_surface_form():
    """The eligibility grounding gate must match un-expanded course tokens.

    normalize_query fuses synonyms into one multi-word string ("MA" ->
    "ma master of arts") that never appears verbatim in a document; grounding a
    specific-course eligibility query against that fused string wrongly forced a
    not-found. normalize_text must stay un-expanded so the gate can match."""
    from rag.text_utils import normalize_text

    assert normalize_query("MA") == "ma master of arts"
    assert normalize_text("MA") == "ma"
    assert normalize_text("MA Education") == "ma education"
    # The subject discriminator (present verbatim in eligibility chunks) grounds it.
    chunk = normalize_text("M.A. (Education). Please ensure from the eligibility criteria given")
    assert "education" in chunk


def test_citation_resolution_keeps_only_valid_cited_sources():
    sources = [
        {"id": 1, "file": "one.pdf", "page": 1},
        {"id": 2, "file": "two.pdf", "page": 2},
    ]
    answer, cited = resolve_answer_citations(
        "Grounded answer.\nCitations: [2, 999]", sources
    )
    assert "Citations:" not in answer
    assert cited == [sources[1]]

    # An entirely invalid model citation must not erase valid provenance.
    _answer, retained = resolve_answer_citations("Answer. Citations: [999]", sources)
    assert retained == sources
