import sys
import os
import unittest
import re

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from ingestion import chunk_text
from rag.intent import is_list_query
from rag.main import verify_faithfulness_logging


class TestRAGOptimizations(unittest.TestCase):
    def test_structure_aware_chunking_table(self):
        # A markdown table that would exceed a small MAX_CHARS_PER_CHUNK (e.g. 100)
        # but stays below 1.5x margin (150 chars).
        table_text = (
            "Here is the department fee details:\n\n"
            "| Sem | Admission Fee | Tuition Fee |\n"
            "| --- | ------------- | ----------- |\n"
            "| 1st | Rs. 5000      | Rs. 2000    |\n"
            "| 2nd | Rs. 4000      | Rs. 2000    |\n"
        )
        
        # We call chunk_text with a very small max_length
        chunks = chunk_text(table_text, max_length=120, overlap=20)
        
        # We verify that the table rows are kept together in a chunk
        # and not split mid-row.
        table_chunks = [c for c in chunks if "|" in c]
        self.assertTrue(len(table_chunks) >= 1)
        for chunk in table_chunks:
            # The header and rows should be intact
            self.assertIn("Sem | Admission Fee", chunk)
            self.assertIn("1st | Rs. 5000", chunk)
            self.assertIn("2nd | Rs. 4000", chunk)

    def test_list_query_intent_detection(self):
        # Queries that expect list/enumeration
        list_queries = [
            "list all departments",
            "show the list of pg courses",
            "enumerate all hostel rules",
            "what are the courses available",
        ]
        for q in list_queries:
            self.assertTrue(is_list_query(q), f"Query '{q}' should be classified as a list query")

        # Non-list queries
        normal_queries = [
            "who is the principal?",
            "when was the chemistry dept established?",
        ]
        for q in normal_queries:
            self.assertFalse(is_list_query(q), f"Query '{q}' should NOT be classified as a list query")

    def test_faithfulness_logging(self):
        # Test that the faithfulness check runs without errors
        answer = "The course code is MCA-CC-6000 and the fee is Rs 5000."
        context = "Master of Computer Applications (MCA) course code MCA-CC-6000 has a fee of Rs 5000."
        
        # This should log no warnings (both MCA-CC-6000 and 5000 are present)
        verify_faithfulness_logging(answer, context)
        
        # This has a hallucinated fee "6000" which is not in context
        hallucinated_answer = "The course code is MCA-CC-6000 and the fee is Rs 6000."
        verify_faithfulness_logging(hallucinated_answer, context)


if __name__ == "__main__":
    unittest.main()
