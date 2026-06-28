import pytest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from rag.freshness import freshness_rank_items


def test_current_principal_prefers_newer_website_over_pdf():
    # Simulated retrieved candidates (doc text + metadata + dist placeholder)
    # Newer website chunk should be preferred.
    query = "Who is the current principal?"

    items = [
        (
            "Principal: Br. Albert\n",  # older pdf
            {
                "source_type": "pdf",
                "document_year": 2023,
                "document_date": None,
                "crawl_timestamp": "2023-06-01T00:00:00Z",
                "source_url": "https://example.com/annual-report-2023.pdf",
                "title": "Annual Report 2023",
            },
            0.1,
        ),
        (
            "Principal: Fr. Archedius\n",  # newer website page
            {
                "source_type": "website",
                "document_year": 2026,
                "document_date": None,
                "crawl_timestamp": "2026-01-10T00:00:00Z",
                "source_url": "https://anthonys.ac.in/administration",
                "title": "Current Administration 2026",
            },
            0.2,
        ),
    ]

    ranked = freshness_rank_items(query, items)
    assert ranked[0][0].startswith("Principal: Fr. Archedius")


def test_non_current_query_not_overly_biased_to_freshness():
    query = "Who is the principal?"  # not explicitly current

    items = [
        (
            "Principal: Br. Albert\n",
            {
                "source_type": "pdf",
                "document_year": 2023,
                "document_date": None,
                "crawl_timestamp": "2023-06-01T00:00:00Z",
                "source_url": "https://example.com/annual-report-2023.pdf",
                "title": "Annual Report 2023",
            },
            0.05,
        ),
        (
            "Principal: Fr. Archedius\n",
            {
                "source_type": "website",
                "document_year": 2026,
                "document_date": None,
                "crawl_timestamp": "2026-01-10T00:00:00Z",
                "source_url": "https://anthonys.ac.in/administration",
                "title": "Current Administration 2026",
            },
            0.9,
        ),
    ]

    ranked = freshness_rank_items(query, items)
    # With non-current query, semantic relevance band should dominate.
    assert ranked[0][0].startswith("Principal: Br. Albert")

