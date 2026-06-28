import pytest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.text_utils import normalize_query
from rag.intent import is_course_query
from rag.main import is_genuinely_ambiguous


def test_vtc_abbreviation_expansion():
    q = "what VTC course are there"
    normalized = normalize_query(q)
    assert "vocational education and training course" in normalized.lower()


def test_vtc_intent_detection():
    # VTC should be recognized as a course query
    assert is_course_query("what VTC are there") is True
    assert is_course_query("what vocational training courses are there") is True


def test_genuinely_ambiguous_check():
    # Specific queries should NOT be genuinely ambiguous
    assert is_genuinely_ambiguous("what VTC course are there") is False
    assert is_genuinely_ambiguous("MCA eligibility") is False
    assert is_genuinely_ambiguous("BCA admission rules") is False
    
    # Generic queries should be genuinely ambiguous
    assert is_genuinely_ambiguous("what courses are there") is True
    assert is_genuinely_ambiguous("admission") is True


def test_bba_and_department_handling():
    from rag.intent import extract_department_from_query, detect_query_intents
    
    # 1. Abbreviation expansion
    assert "bachelor of business administration" in normalize_query("faculty of BBA")
    assert "bachelor of commerce" in normalize_query("BCom syllabus")
    
    # 2. Department term detection
    assert extract_department_from_query("who is the HOD of BBA") == "business administration"
    assert extract_department_from_query("commerce department faculty") == "commerce"
    
    # 3. Intent detection
    assert "department" in detect_query_intents("how many departments are there")
    
    # 4. Genuinely ambiguous check for specific topic keywords
    assert is_genuinely_ambiguous("how many departments are there?") is False
    assert is_genuinely_ambiguous("BBA faculty") is False
    assert is_genuinely_ambiguous("what is the fee?") is False

