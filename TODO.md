# TODO: Freshness-Aware Retrieval for EduBot

## Plan (approved)
1. Wire freshness ranking into retrieval
   - Update `backend/rag/retrieval.py` to call `freshness_rank_items()` after reranking / before final selection.

2. Enforce source priority rules
   - Ensure `source_priority()` aligns with spec (website > pdf) and is used in ranking.

3. Update Crawl4AI ingestion metadata consistency
   - Update `backend/crawl4ai_crawler.py` HTML page metadata to include `document_year` and `document_date` and to use required fields consistently.

4. Normalize website PDF chunks
   - Ensure downloaded website PDFs set `source_type: "pdf"` (not `website_document`) and include `source_url`, `document_year`, `document_date`, `crawl_timestamp`, `title`.

5. Update prompt for conflicts
   - Update `backend/rag/prompts.py` system prompt with the conflict-resolution freshness instruction.

6. Deterministic conflict resolution helper
   - Add a helper (likely in `backend/rag/answer_builders.py` or `backend/rag/main.py`) to detect conflicting role-holder values and select newest; tag ambiguity when needed.

7. Migration/backfill strategy
   - Add a migration script to backfill missing metadata for existing Chroma vectors, where possible.

8. Tests
   - Add tests covering old-vs-new resolution for Principal (and a non-current query case).

## Progress tracking
- [x] Step 1: Wire freshness ranking into retrieval (`backend/rag/retrieval.py`)
- [ ] Step 2: Verify/enforce source priority rule usage
- [x] Step 3: Update Crawl4AI page metadata (`backend/crawl4ai_crawler.py`)
- [x] Step 4: Normalize website PDF chunks metadata (`backend/crawl4ai_crawler.py` + helpers)
- [x] Step 5: Update prompt (`backend/rag/prompts.py`)
- [ ] Step 6: Add deterministic conflict resolution helper
- [ ] Step 7: Add migration/backfill script
- [x] Step 8: Add tests


