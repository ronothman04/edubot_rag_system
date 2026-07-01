# EduBot: System Audit & Recommended Optimizations

This document contains the official architectural audit and technical recommendations for the St. Anthony's College EduBot RAG system. These recommendations cover the retrieval pipeline, query processing, intent detection, caching layer, and data ingestion processes.

---

## 1. Freshness Score Calculation & Recency Calibration

### 1.1 Dynamic Year & Date Validation
* **Current Implementation**:
  In [freshness.py](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/freshness.py#L28-L32), year values are verified against a hardcoded range (`1900 <= year <= 2100`). The recency score uses `now_year - 100` as a baseline.
* **Gaps & Risks**:
  * Typos in crawled web pages or OCR transcriptions (e.g., `2099` instead of `2019`) can easily bypass the `2100` upper limit and get artificially boosted as "ultra-fresh" information.
  * In [freshness.py:L292](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/freshness.py#L292), the code uses `time.gmtime().tm_year` to dynamically fetch the current year, but the static range checks remain broad.
* **Recommendation**:
  Restrict the maximum valid document year to `current_year + 1` (allowing for upcoming prospectus releases) and the minimum reasonable year to `current_year - 15` for active policies. Any document outside this range should be demoted or assigned a fallback year.

### 1.2 Multi-Year Ranges & Span Calculations
* **Current Implementation**:
  [freshness.py:L59-L63](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/freshness.py#L59-L63) parses year ranges (e.g. "2024-25") and selects the maximum year (e.g., `2025`).
* **Gaps & Risks**:
  Selecting only the maximum year works well for single academic terms, but does not distinguish a short-term policy document from a multi-year prospectus. Furthermore, historical sections in documents that list older milestones (e.g., "Founded in 1934, expanded in 2020") can be mis-annotated with the maximum year (`2020`) for the entire chunk, leading to incorrect freshness boosts for historical content.
* **Recommendation**:
  Separate the chunk's *document year* (which should be set at ingestion for the entire document) from *mentions of years in text*. Chunks derived from historical sections should explicitly inherit a `historical` tag or keep their document-level year separate from in-text occurrences to prevent false recency boosting.

---

## 2. Authority Hierarchy Logic

### 2.1 Handling Multi-Document Conflicts within the Same Tier
* **Current Implementation**:
  When two documents in the same tier conflict, the system uses document year/date and crawl timestamp as tie-breakers (specified in [prompts.py / config.py](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/config.py#L127-L128)).
* **Gaps & Risks**:
  * If the year/date metadata is missing or identical, the system defaults to the crawl timestamp. However, crawl timestamps are subject to network delay and ingestion order rather than real document publication dates.
  * Relying on the LLM system prompt to choose the "latest" version ([config.py:L123-L128](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/config.py#L123-L128)) is non-deterministic. If conflicting chunks are sent to the context window, the LLM may merge or pick the wrong one.
* **Recommendation**:
  Implement a deterministic metadata-pre-filtering step in [retrieval.py](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/retrieval.py) that identifies duplicate/conflicting policies (e.g., matching on the same topic/section path across different years) and drops the older version from the candidate list entirely before generating context.

### 2.2 Granular Authority Levels
* **Current Implementation**:
  [authority.py](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/authority.py) uses three broad levels:
  * `2`: Tier 1 canonical document matching the query intent.
  * `1`: Tier 1 canonical document with a query that is authority-related but to a different topic.
  * `0`: Non-Tier-1 document or a Tier 1 doc on a query with no authority intent.
* **Gaps & Risks**:
  This coarse-grained model makes it difficult to separate intermediate-priority documents (like recent official student notices) from low-priority boilerplate pages (like crawled contact headers and external web links).
* **Recommendation**:
  Expand the authority levels to a 5-tier system:
  * `Tier 4 (Canonical Match)`: Prospectus / Handbook with exact intent matching.
  * `Tier 3 (Canonical General)`: General Prospectus / Handbook chunks.
  * `Tier 2 (Official Updates)`: Recent official circulars and verified notices.
  * `Tier 1 (General Content)`: Generic website pages and department descriptions.
  * `Tier 0 (Boilerplate/Links)`: Crawled navigation, link tables, and header/footer dumps.

---

## 3. Retrieval & Reranking Strategy

### 3.1 Cross-Encoder Latency Optimization
* **Current Implementation**:
  The system uses `BAAI/bge-reranker-base` locally on the server (running on CPU/MPS). It reranks a large set of candidates (up to 30 or 50) on every query.
* **Gaps & Risks**:
  Reranking 30+ chunks via a cross-encoder model on CPU is highly CPU-intensive and adds a latency overhead of 100ms to 400ms per query. This reduces backend concurrency and throughput under load.
* **Recommendation**:
  * Implement **Cascaded Retrieval**: Only run the cross-encoder reranker if the top vector distance is close to the threshold. If the vector distance of the top candidate is extremely high (e.g. > 1.8), skip reranking and return it immediately.
  * Reduce the reranker input size (`RERANKER_INPUT_K`) from `30`/`50` to `15` for standard queries.
  * Cache computed cross-encoder scores for similar query-passage pairs using a local cache.

### 3.2 Dynamic Ambiguity Classification
* **Current Implementation**:
  [main.py:L518-L523](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/rag/main.py#L518-L523) performs a hardcoded ambiguity check (`is_vague_college_question()`) when the reranker score falls below the confidence threshold.
* **Gaps & Risks**:
  Rule-based keyword lists for ambiguity detection are hard to maintain and prone to missing complex vague queries (e.g., "what are the details of the process?").
* **Recommendation**:
  Introduce a lightweight intent classifier model or use small-LLM prompting to classify query ambiguity in Stage 4/5, rather than relying on regex keyword lists.

---

## 4. Ingestion & Text Processing

### 4.1 OCR Casing & Text Re-assembly
* **Current Implementation**:
  OCR uses Tesseract via `pytesseract` to read image files, and text is cleaned in [ingestion.py](file:///Users/ebenezerjyrwa/Documents/EduBot_Production_Ready/backend/ingestion.py).
* **Gaps & Risks**:
  * OCR text often suffers from missing line break preservation, leading to words being concatenated (e.g. "applicationform" instead of "application form"). This directly breaks BM25 indexing and keyword matching.
  * OCR casing fixes (`fix_ocr_casing`) use heuristics that can sometimes lowercase proper nouns or institutional names (e.g. "St. Anthony's" to "st. anthony's").
* **Recommendation**:
  * Implement layout-aware OCR (e.g., using `easyocr` or layout parser models) to preserve column boundaries and word spaces.
  * Run a spelling correction and word segmentation pass (e.g., using `wordsegment` or symspell) on OCR text blocks before indexing.

### 4.2 PDF Ligature & Hyphenation Resolution
* **Current Implementation**:
  PDF parsing via `pdfplumber` extracts text, but does not always handle ligatures (e.g., "ﬁ", "ﬂ") and hyphens across lines.
* **Gaps & Risks**:
  If a keyword is written with ligatures (e.g., "diﬃcult") or hyphenated across a page break (e.g., "admis-\nsion"), keyword searches like BM25 will miss matches.
* **Recommendation**:
  Add a text normalization step during parsing to replace ligatures with their corresponding individual characters (e.g., `\uFB01` -> `fi`) and strip trailing hyphens when rebuilding lines.

---

## 5. Summary of System Strengths

Despite the gaps highlighted above, the EduBot codebase exhibits several robust architectural patterns:
1. **Department Namespacing (Fix 1)**: Properly scopes search queries to specific departments, preventing cross-department document pollution.
2. **SSRF/Domain Lock (Fix 2)**: Effectively locks the crawler to the target domain, protecting backend infrastructure from Server-Side Request Forgery and malicious off-domain crawl requests.
3. **Structured Pipeline Logging**: The 10-stage execution logs provide excellent execution transparency and metrics tracking.
4. **Resilient Local Fallbacks**: The system gracefully falls back to local scoring when the cross-encoder is unavailable, ensuring high uptime.
