#!/usr/bin/env python3
"""
Test script to verify intent guard changes.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.intent import (
    is_college_related,
    is_clearly_out_of_scope,
    is_homework_or_assignment,
)
from rag.text_utils import normalize_query

def test_queries():
    test_cases = [
        # Should NOT be out-of-scope (college-related)
        ("teachers in computer science", False, "college"),
        ("faculty in computer science", False, "college"),
        ("what are the teachers in cs", False, "college"),
        ("computer science faculty", False, "college"),
        ("staff in mathematics department", False, "college"),
        ("professor contact details", False, "college"),
        
        # Should be out-of-scope (clearly unrelated)
        ("Who is the Prime Minister of India?", True, "politics"),
        ("what is the weather today", True, "weather"),
        ("tell me a joke", True, "entertainment"),
        ("cricket score today", True, "sports"),
        ("What is the bitcoin price", True, "finance"),
        
        # Should be caught as homework
        ("write an essay on climate change", None, "homework"),
    ]
    
    print("=" * 80)
    print("INTENT GUARD TEST RESULTS")
    print("=" * 80)
    
    for query, expected_out_of_scope, category in test_cases:
        normalized = normalize_query(query)
        is_hw = is_homework_or_assignment(query)
        is_college = is_college_related(query)
        is_oos = is_clearly_out_of_scope(query)
        
        if category == "homework":
            status = "✓ PASS" if is_hw else "✗ FAIL"
            print(f"\n{status} [HOMEWORK] {query!r}")
            print(f"   is_homework_or_assignment: {is_hw}")
        else:
            status = "✓ PASS" if is_oos == expected_out_of_scope else "✗ FAIL"
            print(f"\n{status} [{category.upper()}] {query!r}")
            print(f"   normalized: {normalized!r}")
            print(f"   is_college_related: {is_college}")
            print(f"   is_clearly_out_of_scope: {is_oos} (expected: {expected_out_of_scope})")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_queries()
