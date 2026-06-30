#!/usr/bin/env python3
import sys
import os
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from langchain_core.documents import Document
from ingestion import load_website, ingest_documents
from db import collection

# Mock Crawl4AI Result structure
class MockMarkdownGroup:
    def __init__(self, fit_markdown):
        self.fit_markdown = fit_markdown


class MockCrawlResult:
    def __init__(self, url, markdown_text, html_text, success=True, error_message=""):
        self.url = url
        self.success = success
        self.error_message = error_message
        self.html = html_text
        self.markdown = MockMarkdownGroup(markdown_text)


def test_crawl_metadata_preservation():
    """Test that Crawl4AI output documents contain the correct metadata fields."""
    print("\nTEST: Crawl4AI Metadata Preservation")
    
    mock_html = "<html><head><title>Test Admissions Page</title></head><body><h1>Admissions Info</h1></body></html>"
    mock_md = "# Admissions Info\n\nSome official admissions content."
    mock_url = "https://anthonys.ac.in/admissions"
    
    # Mock AsyncWebCrawler
    mock_crawler_inst = MagicMock()
    mock_crawler_inst.__aenter__ = AsyncMock(return_value=mock_crawler_inst)
    mock_crawler_inst.__aexit__ = AsyncMock()
    mock_crawler_inst.arun_many = AsyncMock(return_value=[
        MockCrawlResult(mock_url, mock_md, mock_html)
    ])
    
    with patch("crawl4ai_crawler.AsyncWebCrawler", return_value=mock_crawler_inst), \
         patch("crawl4ai_crawler.CRAWL4AI_AVAILABLE", True):
        
        from crawl4ai_crawler import crawl_with_crawl4ai
        
        docs = asyncio.run(crawl_with_crawl4ai(
            start_url="https://anthonys.ac.in/admissions",
            max_pages=1,
            include_pdfs=False,
            same_domain_only=True,
            crawl_documents=False
        ))
        
        assert len(docs) > 0, "No documents returned from crawl"
        doc = docs[0]
        
        # Verify specific required metadata fields
        print(f"  Metadata received: {doc.metadata}")
        assert doc.metadata["url"] == mock_url
        assert "Admissions" in doc.metadata["title"]
        assert doc.metadata["domain"] == "anthonys.ac.in"
        assert doc.metadata["source_type"] == "website"
        assert doc.metadata["crawl_method"] == "crawl4ai"
        assert "crawl_timestamp" in doc.metadata
        assert doc.metadata["document_year"] == 2026
        assert doc.metadata["document_date"] == "2026-06-12"
        print("✓ PASS - All required metadata fields are preserved correctly")


def test_crawl_recursion_and_duplicates():
    """Test that recursive crawling handles limits and duplicates correctly."""
    print("\nTEST: Crawl4AI Recursion and Duplicate URL Handling")
    
    # We want to crawl starting from pageA. PageA has a link to PageB. PageB has a link back to PageA (circular).
    pages = {
        "https://anthonys.ac.in/pageA": {
            "html": "<html><body><h1>Page A</h1><a href='/pageB'>Link B</a></body></html>",
            "md": "# Page A\n\nLink to B."
        },
        "https://anthonys.ac.in/pageB": {
            "html": "<html><body><h1>Page B</h1><a href='/pageA'>Link A</a></body></html>",
            "md": "# Page B\n\nLink to A."
        }
    }
    
    async def mock_arun_many(urls, config=None):
        results = []
        for url in urls:
            if url in pages:
                results.append(MockCrawlResult(url, pages[url]["md"], pages[url]["html"]))
            else:
                results.append(MockCrawlResult(url, "", "", success=False, error_message="404"))
        return results

    mock_crawler_inst = MagicMock()
    mock_crawler_inst.__aenter__ = AsyncMock(return_value=mock_crawler_inst)
    mock_crawler_inst.__aexit__ = AsyncMock()
    mock_crawler_inst.arun_many = mock_arun_many
    
    with patch("crawl4ai_crawler.AsyncWebCrawler", return_value=mock_crawler_inst), \
         patch("crawl4ai_crawler.CRAWL4AI_AVAILABLE", True):
        
        from crawl4ai_crawler import crawl_with_crawl4ai
        
        docs = asyncio.run(crawl_with_crawl4ai(
            start_url="https://anthonys.ac.in/pageA",
            max_pages=5, # plenty of limit
            include_pdfs=False,
            same_domain_only=True,
            crawl_documents=False,
            max_depth=3
        ))
        
        # Verify that both pageA and pageB were visited, but recursion stopped due to duplicate/visited checks
        visited_urls = {d.metadata["url"] for d in docs if d.metadata["file_type"] == "website"}
        print(f"  Visited URLs during recursion: {visited_urls}")
        assert "https://anthonys.ac.in/pageA" in visited_urls
        assert "https://anthonys.ac.in/pageB" in visited_urls
        assert len(visited_urls) == 2, f"Expected exactly 2 pages, got {len(visited_urls)}"
        print("✓ PASS - Recursion and duplicates handled correctly without infinite loops")


def test_crawl_failure_fallback():
    """Test that if Crawl4AI fails, the ingestion system falls back to the legacy crawler."""
    print("\nTEST: Ingestion Crawler Fallback")
    
    # Mock AsyncWebCrawler to raise Exception
    mock_crawler_inst = MagicMock()
    mock_crawler_inst.__aenter__ = AsyncMock(side_effect=Exception("Playwright connection refused"))
    
    # Mock the legacy crawler so we don't do real HTTP requests during fallback
    fallback_docs = [
        Document(
            page_content="Fallback admissions page content",
            metadata={"source_url": "https://anthonys.ac.in/admissions", "filename": "Legacy Admissions"}
        )
    ]
    
    with patch("crawl4ai_crawler.AsyncWebCrawler", return_value=mock_crawler_inst), \
         patch("ingestion.load_website_legacy", return_value=fallback_docs) as mock_legacy:
        
        docs = load_website(
            start_url="https://anthonys.ac.in/admissions",
            max_pages=1,
            include_pdfs=False
        )
        
        # Verify fallback was triggered and returned fallback documents
        assert mock_legacy.called, "Fallback to legacy crawler was not triggered"
        assert len(docs) == 1
        assert docs[0].page_content == "Fallback admissions page content"
        print("✓ PASS - System successfully falls back to legacy crawler on Crawl4AI exceptions")


def test_chroma_insertion():
    """Test that crawled documents are successfully chunked and stored in ChromaDB."""
    print("\nTEST: Ingestion Pipeline & ChromaDB Insertion")
    
    mock_docs = [
        Document(
            page_content="Admissions at St. Anthonys College require a high school diploma. Fee structures are available online.",
            metadata={
                "url": "https://anthonys.ac.in/admissions",
                "title": "Admissions St. Anthonys",
                "domain": "anthonys.ac.in",
                "source_type": "website",
                "crawl_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "crawl_method": "crawl4ai",
                "filename": "Admissions St. Anthonys",
                "file_type": "website"
            }
        )
    ]
    
    # Clean up old chunks for this file if any
    try:
        collection.delete(where={"filename": {"$eq": "Admissions St. Anthonys"}})
    except Exception:
        pass
        
    result = ingest_documents(
        documents=mock_docs,
        filename="https://anthonys.ac.in/admissions",
        scope="official",
        document_type="website"
    )

    try:
        print(f"  Ingestion result: {result}")
        assert result["chunks_stored"] > 0, "No chunks stored in vector database"

        # Read from database to confirm chunk metadata fields are correct
        query_result = collection.get(
            where={"filename": {"$eq": "Admissions St. Anthonys"}},
            include=["metadatas"]
        )

        metas = query_result.get("metadatas", [])
        assert len(metas) > 0, "No metadata returned from ChromaDB check"
        meta = metas[0]
        print(f"  Retrieved chunk metadata: {meta}")

        assert meta["url"] == "https://anthonys.ac.in/admissions"
        assert meta["domain"] == "anthonys.ac.in"
        assert meta["source_type"] == "website"
        assert meta["crawl_method"] == "crawl4ai"
        assert "crawl_timestamp" in meta
        # Honest dates (ingestion audit Fix B): an undated crawled page must NOT be
        # stamped with a fabricated current-year/date. With no year derivable from
        # the page identifiers, document_year stays the honest "general" sentinel
        # and document_date stays empty, so freshness ranking gives it no false
        # recency boost. A crawl timestamp is recorded separately (above).
        assert meta["document_year"] == "general"
        assert meta["document_date"] == ""
        print("✓ PASS - Crawled page stored with honest (non-fabricated) date metadata")
    finally:
        # Teardown: this test writes into the real ChromaDB collection, so remove
        # the synthetic chunk and rebuild the BM25 index to leave the database
        # exactly as it was. Without this, the mock "Admissions St. Anthonys"
        # chunk lingers in production and can surface as a phantom source.
        try:
            collection.delete(where={"filename": {"$eq": "Admissions St. Anthonys"}})
            from rag.bm25_index import rebuild_bm25_index
            rebuild_bm25_index()
            print("  Teardown: removed test chunk and rebuilt BM25 index")
        except Exception as cleanup_err:
            print(f"  Teardown warning: failed to remove test chunk: {cleanup_err}")


if __name__ == "__main__":
    print("=" * 80)
    print("CRAWL4AI INTEGRATION AND FALLBACK TESTS")
    print("=" * 80)
    
    test_crawl_metadata_preservation()
    test_crawl_recursion_and_duplicates()
    test_crawl_failure_fallback()
    test_chroma_insertion()
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 80)
