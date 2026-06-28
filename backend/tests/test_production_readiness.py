#!/usr/bin/env python3
"""
Comprehensive regression tests for EduBot production readiness.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.intent import (
    is_staff_query,
    extract_department_from_query,
    chunk_has_staff_evidence,
    chunk_looks_like_course_only,
    is_homework_or_assignment,
    is_clearly_out_of_scope,
    is_vague_college_question,
)
from rag.retrieval import filter_staff_docs
from rag.text_utils import normalize_query

def test_staff_detection():
    """Test staff query detection."""
    print("\n" + "=" * 80)
    print("STAFF QUERY DETECTION TESTS")
    print("=" * 80)
    
    staff_queries = [
        "teachers in computer science",
        "who are the teaching staff of computer science?",
        "faculty members in English",
        "staff in mathematics department",
        "professor contact details",
        "who teaches computer science?",
    ]
    
    for q in staff_queries:
        result = is_staff_query(q)
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} '{q}' -> is_staff_query: {result}")

def test_department_extraction():
    """Test department extraction."""
    print("\n" + "=" * 80)
    print("DEPARTMENT EXTRACTION TESTS")
    print("=" * 80)
    
    test_cases = [
        ("teachers in computer science", "computer science"),
        ("who are the teaching staff of computer science?", "computer science"),
        ("faculty members in English", "english"),
        ("staff in mathematics department", "mathematics"),
        ("professor contact details", None),
        ("bca course details", "bca"),
        ("mca faculty members", "mca"),
    ]
    
    for query, expected_dept in test_cases:
        result = extract_department_from_query(query)
        status = "✓ PASS" if result == expected_dept else "✗ FAIL"
        print(f"{status} '{query}' -> dept: {result} (expected: {expected_dept})")

def test_chunk_evidence():
    """Test staff evidence detection in chunks."""
    print("\n" + "=" * 80)
    print("CHUNK STAFF EVIDENCE TESTS")
    print("=" * 80)
    
    staff_chunks = [
        "Computer Science Department Faculty: Dr. John Smith (HOD), Prof. Jane Doe (Professor), Mr. Ram Kumar (Assistant Professor)",
        "Teaching staff: The department has 5 faculty members including the Head of Department.",
        "Name: Dr. Alice Johnson, Designation: Associate Professor, Department: Physics",
    ]
    
    course_only_chunks = [
        "Disciplines for FYUG programmes: Computer Science offers BCA and MCA",
        "Programme Structure: The course has 4 semesters with the following subject combinations",
        "Major Subject Selection: Students must choose one major subject from the following list",
        "Syllabus: The course syllabus covers the following topics in each semester",
    ]
    
    print("\nShould have staff evidence:")
    for chunk in staff_chunks:
        result = chunk_has_staff_evidence(chunk)
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} has_staff_evidence: {result}")
        print(f"   Preview: {chunk[:70]}...")
    
    print("\nShould be course-only:")
    for chunk in course_only_chunks:
        result = chunk_looks_like_course_only(chunk)
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} looks_like_course_only: {result}")
        print(f"   Preview: {chunk[:70]}...")

def test_staff_doc_filtering():
    """Test staff document filtering."""
    print("\n" + "=" * 80)
    print("STAFF DOC FILTERING TESTS")
    print("=" * 80)
    
    # Test 1: Staff query with mixed docs
    query = "teachers in computer science"
    docs = [
        "Computer Science Department Faculty: Dr. John Smith (HOD), Prof. Jane Doe (Professor), Mr. Ram Kumar (Assistant Professor)",
        "Disciplines for FYUG programmes: Computer Science offers BCA and MCA with various subject combinations",
        "Computer Science Department Head: Dr. John Smith is the HOD",
    ]
    metas = [{"page": 1}, {"page": 2}, {"page": 3}]
    dists = [0.1, 0.2, 0.15]
    
    filtered_docs, filtered_metas, filtered_dists = filter_staff_docs(query, docs, metas, dists)
    
    print(f"\nQuery: '{query}'")
    print(f"Original docs: {len(docs)}")
    print(f"After filtering: {len(filtered_docs)}")
    
    if len(filtered_docs) < len(docs):
        print("✓ PASS - Correctly filtered out course-only chunks")
    else:
        print("✗ FAIL - Should have filtered out at least one chunk")
    
    # Test 2: Non-staff query should pass through unchanged
    query2 = "what courses are available?"
    filtered_docs2, filtered_metas2, filtered_dists2 = filter_staff_docs(query2, docs, metas, dists)
    
    print(f"\nQuery: '{query2}'")
    print(f"Original docs: {len(docs)}")
    print(f"After filtering: {len(filtered_docs2)}")
    
    if len(filtered_docs2) == len(docs):
        print("✓ PASS - Non-staff query passed through unchanged")
    else:
        print("✗ FAIL - Non-staff queries should not be filtered")

def test_regression_scenarios():
    """Test comprehensive regression scenarios."""
    print("\n" + "=" * 80)
    print("REGRESSION TEST SCENARIOS")
    print("=" * 80)
    
    scenarios = [
        # (query, should_be_staff, should_be_homework, should_be_out_of_scope, description)
        ("teachers in computer science", True, False, False, "Valid staff query"),
        ("who are the teaching staff of computer science?", True, False, False, "Valid staff query with question"),
        ("what courses are offered in computer science?", False, False, False, "Course query, not staff"),
        ("Admission", False, False, False, "Vague college query"),
        ("What documents are required for admission?", False, False, False, "Valid admission query"),
        ("Am I eligible if I passed from another college?", False, False, False, "Personal situation query"),
        ("Who is the Prime Minister of India?", False, False, True, "Out-of-scope politics"),
        ("Write an essay on climate change", False, True, False, "Homework query (checked before out-of-scope)"),
        ("tell me a joke", False, False, True, "Out-of-scope entertainment"),
        ("cricket score today", False, False, True, "Out-of-scope sports"),
        ("Does the college have swimming classes?", False, False, False, "College resource query"),
    ]
    
    for query, exp_staff, exp_hw, exp_oos, desc in scenarios:
        is_hw = is_homework_or_assignment(query)
        is_oos = is_clearly_out_of_scope(query)
        is_stf = is_staff_query(query)
        is_vague = is_vague_college_question(query)
        
        staff_ok = is_stf == exp_staff
        hw_ok = is_hw == exp_hw
        oos_ok = is_oos == exp_oos
        all_ok = staff_ok and hw_ok and oos_ok
        
        status = "✓ PASS" if all_ok else "✗ FAIL"
        print(f"\n{status} {desc}")
        print(f"   Query: {query!r}")
        print(f"   is_staff={is_stf} (expected {exp_staff}) {'✓' if staff_ok else '✗'}")
        print(f"   is_homework={is_hw} (expected {exp_hw}) {'✓' if hw_ok else '✗'}")
        print(f"   is_out_of_scope={is_oos} (expected {exp_oos}) {'✓' if oos_ok else '✗'}")

def test_fee_clarification_fallbacks():
    """Test fee clarification and fallback responses."""
    print("\n" + "=" * 80)
    print("FEE CLARIFICATION FALLBACK TESTS")
    print("=" * 80)
    
    from rag.responses import smart_not_found_answer
    from rag.query_expansion import smart_clarification_response
    
    # Test case 1: Fee query WITH course (MCA) should NOT return clarification, and should have course-specific fallback
    q1 = "what is the fee structure for MCA"
    clar1 = smart_clarification_response(q1)
    ans1 = smart_not_found_answer(q1)
    
    print(f"Query: '{q1}'")
    print(f"  smart_clarification_response: {clar1}")
    print(f"  smart_not_found_answer: {ans1!r}")
    
    assert clar1 is None, "Should not return clarification for query with specific course!"
    assert "MCA" in ans1 or "Computer Applications" in ans1, "Should mention MCA or Computer Applications in the fallback response!"
    assert "could you mention the course" not in ans1.lower(), "Should not ask to mention the course!"
    print("✓ PASS - Fee query with course MCA handled correctly")
    
    # Test case 2: Fee query WITH subject/dept (Chemistry) should NOT return clarification, and should have subject-specific fallback
    q2 = "what is the fee structure for Chemistry"
    clar2 = smart_clarification_response(q2)
    ans2 = smart_not_found_answer(q2)
    
    print(f"Query: '{q2}'")
    print(f"  smart_clarification_response: {clar2}")
    print(f"  smart_not_found_answer: {ans2!r}")
    
    assert clar2 is None, "Should not return clarification for query with specific subject!"
    assert "Chemistry" in ans2, "Should mention Chemistry in the fallback response!"
    assert "could you mention the course" not in ans2.lower(), "Should not ask to mention the course!"
    print("✓ PASS - Fee query with subject Chemistry handled correctly")
    
    # Test case 3: Fee query WITHOUT course/subject should return clarification or generic fallback
    q3 = "what is the fee structure?"
    clar3 = smart_clarification_response(q3)
    ans3 = smart_not_found_answer(q3)
    
    print(f"Query: '{q3}'")
    print(f"  smart_clarification_response: {clar3.get('answer') if clar3 else None}")
    print(f"  smart_not_found_answer: {ans3!r}")
    
    assert clar3 is not None, "Should require clarification for generic fee query!"
    assert "could you mention the course" in ans3.lower(), "Should ask to mention the course!"
    print("✓ PASS - Generic fee query handled correctly")


def test_vague_question_classification():
    """Test vague question classification triggers only for truly vague queries."""
    print("\n" + "=" * 80)
    print("VAGUE QUESTION CLASSIFICATION TESTS")
    print("=" * 80)
    
    # These should be classified as vague (exactly in VAGUE_COLLEGE_PATTERNS or short phrases of vague terms)
    vague_queries = ["admission", "hostel", "fees", "for admission"]
    # These should NOT be classified as vague (contain structure, rules, dates, etc.)
    non_vague_queries = ["fee structure", "hostel rules", "admission dates", "admission procedure", "MCA fee"]
    
    for q in vague_queries:
        result = is_vague_college_question(q)
        print(f"Query: '{q}' -> is_vague: {result}")
        assert result is True, f"'{q}' should be classified as vague!"
        
    for q in non_vague_queries:
        result = is_vague_college_question(q)
        print(f"Query: '{q}' -> is_vague: {result}")
        assert result is False, f"'{q}' should NOT be classified as vague!"
        
    print("✓ PASS - Vague question classification functions correctly")


if __name__ == "__main__":
    test_staff_detection()
    test_department_extraction()
    test_chunk_evidence()
    test_staff_doc_filtering()
    test_regression_scenarios()
    test_fee_clarification_fallbacks()
    test_vague_question_classification()
    
    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80)
