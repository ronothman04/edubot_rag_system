# 📐 EduBot: Architecture & Technical Reference Guide

Deep-dive technical documentation for EduBot system architecture, design patterns, and optimization strategies.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Data Models & Schemas](#data-models--schemas)
3. [RAG Pipeline Deep Dive](#rag-pipeline-deep-dive)
4. [Document Processing Pipeline](#document-processing-pipeline)
5. [Performance Optimization](#performance-optimization)
6. [Security Architecture](#security-architecture)
7. [Scalability & Load Handling](#scalability--load-handling)
8. [Advanced Configuration](#advanced-configuration)
9. [API Reference](#api-reference)
10. [Database Query Patterns](#database-query-patterns)

---

## System Architecture

### 1.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  React 19 SPA (Vite)                                      │  │
│  │  - Chat Interface                                          │  │
│  │  - Admin Dashboard                                         │  │
│  │  - Document Management                                     │  │
│  │  - Analytics & Settings                                    │  │
│  │  State: Zustand/Context API                               │  │
│  │  Storage: LocalStorage (chat history), Supabase           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                      ↓ HTTP/REST ↑
          (JWT in Authorization header)
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY LAYER                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  FastAPI (Uvicorn)                                        │  │
│  │  - Request validation (Pydantic)                          │  │
│  │  - CORS middleware                                         │  │
│  │  - JWT authentication                                      │  │
│  │  - Rate limiting                                           │  │
│  │  - Error handling                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        ↓ ↓ ↓ ↓           ↓ ↓           ↓ ↓ ↓
┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌────────────┐
│  INGESTION   │ │ RAG/RETRIEVAL │ │  ANALYTICS   │ │ AUTH LAYER │
│  LAYER       │ │ LAYER         │ │ LAYER        │ │            │
├──────────────┤ ├───────────────┤ ├──────────────┤ ├────────────┤
│              │ │               │ │              │ │            │
│• PDF Parse   │ │• Vector Search│ │• Query Logs  │ │• Supabase  │
│• OCR         │ │• Reranking    │ │• User Acts   │ │• JWT Valid │
│• Clean Text  │ │• LLM Inference│ │• Metrics DB  │ │• RBAC      │
│• Chunk Texts │ │• Answer Build │ │• Reporting   │ │            │
│• Embed       │ │• Intent Guard │ │              │ │            │
│• Deduplicate │ │               │ │              │ │            │
│              │ │               │ │              │ │            │
└──────────────┘ └───────────────┘ └──────────────┘ └────────────┘
        ↓               ↓                ↓
┌─────────────────────────────────────────────────────────────────┐
│                 PERSISTENCE LAYER                               │
│  ┌──────────────────┐  ┌─────────────┐  ┌──────────────────┐   │
│  │  ChromaDB        │  │ Supabase    │  │ File System      │   │
│  │  - Vectors       │  │ - Auth      │  │ - Uploads        │   │
│  │  - Metadata      │  │ - Chat logs │  │ - Logs           │   │
│  │  - Chunks        │  │ - Analytics │  │ - Backups        │   │
│  └──────────────────┘  └─────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        ↓               ↓                ↓
┌─────────────────────────────────────────────────────────────────┐
│                 EXTERNAL SERVICES                               │
│  ┌──────────────────┐  ┌────────────────────────────────────┐   │
│  │  Ollama (Local)  │  │  ML Models                         │   │
│  │  - qwen2.5:3b    │  │  - SentenceTransformer (embeddings)│   │
│  └──────────────────┘  │  - Tesseract (OCR)                 │   │
│                        └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Dependencies

```
ingestion.py
  ├─ db.py
  ├─ embeddings.py
  │  └─ sentence_transformers.SentenceTransformer
  ├─ pdfplumber
  ├─ python-docx
  ├─ beautifulsoup4
  └─ trafilatura

rag.py
  ├─ db.py
  │  └─ chromadb
  ├─ embeddings.py
  ├─ llm.py
  │  └─ requests (to Ollama)
  └─ reranker.py (optional)

api.py
  ├─ ingestion.py
  ├─ rag.py
  ├─ db.py
  ├─ fastapi
  ├─ supabase (auth)
  └─ fastapi.middleware.CORSMiddleware
```

### 1.3 Data Flow: Chat Query to Response

```
User Types Query
    ↓
[1] VALIDATION LAYER
    ├─ Validate query length
    ├─ Check user authentication
    └─ Rate limiting check
    ↓
[2] INTENT DETECTION LAYER
    ├─ Check homework pattern
    ├─ Check out-of-scope pattern
    └─ If matched: return refusal message → [9]
    ↓
[3] QUERY ENCODING LAYER
    ├─ Add BGE prefix
    ├─ Encode with SentenceTransformer
    └─ Get vector embedding
    ↓
[4] RETRIEVAL LAYER
    ├─ Vector Search (top 100)
    ├─ Keyword Search (top 150)
    ├─ Merge & deduplicate
    └─ Results: 50-100 candidates
    ↓
[5] RERANKING LAYER (Optional)
    ├─ Cross-encoder scores
    ├─ Sort by relevance
    └─ Keep top 8
    ↓
[6] CONTEXT BUILDING LAYER
    ├─ Format chunk metadata
    ├─ Add document references
    ├─ Organize by section
    └─ Respect token limits (~14k chars)
    ↓
[7] SYSTEM PROMPT BUILDING LAYER
    ├─ Add document grounding rules
    ├─ Add citation format requirements
    └─ Prepare instructions
    ↓
[8] LLM INFERENCE LAYER
    ├─ Send to Ollama (local)
    ├─ Stream/wait for response
    └─ Parse markdown
    ↓
[9] RESPONSE PROCESSING LAYER
    ├─ Clean formatting
    ├─ Extract citations
    ├─ Flag confidence
    └─ Log to analytics
    ↓
SEND TO USER
```

---

## Data Models & Schemas

### 2.1 Chunk Schema (ChromaDB)

```python
# What's stored in ChromaDB per chunk:

chunk_record = {
    "id": "official_test_handbook_p1_c0_abc123def456",  # Deterministic ID
    
    # Core content
    "document": "Full chunk text content (up to 450 words)",
    
    # Vector embedding
    "embedding": [0.123, -0.456, 0.789, ...],  # 384-dim vector
    
    # Metadata (stored as JSON in ChromaDB)
    "metadata": {
        # Document Identity
        "filename": "test_handbook.txt",
        "source_filename": "test_handbook.txt",
        "file_type": "txt",
        "source_type": "uploaded_document",
        
        # Position
        "page": 1,
        "page_label": "1",
        "page_range": "1",
        "total_pages": 5,
        "chunk_index": 0,
        
        # Content Classification
        "section_title": "Admission Requirements",
        "heading_path": "Admission Requirements > Undergraduate",
        "chunk_type": "text",
        "is_toc": False,
        
        # Metrics
        "text_chars": 245,
        "word_count": 45,
        "char_start": 0,
        "char_end": 245,
        "text_hash": "abc123def456789",  # For dedup
        
        # Source Tracking
        "source_url": "",
        "found_on_url": "",
        "crawl_base_url": "",
        "source_pdf_filename": "",
        
        # Admin
        "doc_id": "doc_xyz789",
        "deleted": False,
        "status": "active",
        "scope": "official",
        "uploaded_by": "admin",
        "user_id": "admin",
        "session_id": "admin",
        "department": "general",
        "document_type": "handbook",
        "year": "2024",
        
        # Tables
        "tables_extracted": 0,
        "ocr_used": False,
    }
}
```

### 2.2 Chat Message Schema (Supabase)

```python
# Supabase chat_messages table structure:

{
    "id": "550e8400-e29b-41d4-a716-446655440000",  # UUID
    "session_id": "550e8400-e29b-41d4-a716-446655440001",  # FK
    "role": "user",  # "user" or "assistant"
    "content": "What are the admission requirements?",
    "created_at": "2024-01-15T10:30:00.000000+00:00"
}
```

### 2.3 Chat Session Schema

```python
{
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "user_id": "550e8400-e29b-41d4-a716-446655440002",  # FK to profiles
    "title": "Admission Requirements",
    "created_at": "2024-01-15T10:00:00.000000+00:00",
    "updated_at": "2024-01-15T10:30:00.000000+00:00"
}
```

### 2.4 Analytics Schema

```python
{
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "user_id": "550e8400-e29b-41d4-a716-446655440002",
    "query": "What are the admission requirements?",
    "response_time_ms": 3421,
    "chunks_retrieved": 5,
    "model_used": "qwen2.5:3b",
    "created_at": "2024-01-15T10:30:00.000000+00:00"
}
```

---

## RAG Pipeline Deep Dive

### 3.1 Retrieval Strategy: Hybrid Search

#### Vector Search Component

```python
def vector_search(query: str, top_k: int = 100) -> tuple[list, list, list]:
    """
    Semantic search using embeddings
    
    Returns:
        docs: list of chunk texts
        metas: list of metadata dicts
        distances: list of cosine distances (0=identical, 2=opposite)
    """
    
    # 1. Encode query
    query_vector = encode_query(query)  # 384-dim vector
    
    # 2. Search ChromaDB
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    # 3. Extract results
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]
    
    return docs, metas, distances
```

**Why Cosine Distance?**
- Normalized embeddings from SentenceTransformer
- Cosine distance perfect for high-dim vectors
- Range: 0 (identical) to 2 (opposite)
- Better than L2 for semantic similarity

#### Keyword Search Component

```python
def keyword_search(query: str, top_k: int = 150) -> tuple[list, list, list]:
    """
    Exact and fuzzy text matching
    
    Works when user searches domain-specific terms
    e.g., "GPA", "SAT", "CGPA", "hostel fee"
    """
    
    # Normalize query
    norm_query = normalize_text(query)  # lowercase, remove punct
    
    # Get all chunks
    all_results = collection.get(include=["documents", "metadatas"])
    
    # Scan for matches
    matched = []
    for doc, meta in zip(all_results["documents"], all_results["metadatas"]):
        norm_doc = normalize_text(doc)
        
        # Exact substring match
        if norm_query in norm_doc:
            score = 0.0  # Exact match = highest score
            matched.append((doc, meta, score))
        
        # Fuzzy match (difflib)
        else:
            # Check key terms
            query_terms = norm_query.split()
            for term in query_terms:
                if term in norm_doc:
                    score = 0.1  # Partial match
                    matched.append((doc, meta, score))
                    break
            
            # Fuzzy matching for misspellings
            else:
                close_match = get_close_matches(norm_query, [norm_doc], n=1, cutoff=0.6)
                if close_match:
                    score = 0.5  # Fuzzy match
                    matched.append((doc, meta, score))
    
    # Sort by score and return top_k
    matched.sort(key=lambda x: x[2])
    results = matched[:top_k]
    
    docs = [r[0] for r in results]
    metas = [r[1] for r in results]
    distances = [r[2] for r in results]
    
    return docs, metas, distances
```

#### Hybrid Merge Component

```python
def merge_retrieval_results(
    vector_docs, vector_metas, vector_dists,
    keyword_docs, keyword_metas, keyword_dists,
    top_n: int = 50
) -> tuple[list, list, list]:
    """
    Combine vector and keyword results intelligently
    """
    
    # Create merged index
    merged = {}  # chunk_id -> (doc, meta, best_distance)
    
    # Add vector results (weight: 1.0)
    for doc, meta, dist in zip(vector_docs, vector_metas, vector_dists):
        chunk_id = meta.get("chunk_index", hash(doc))
        merged[chunk_id] = (doc, meta, dist)
    
    # Add keyword results (weight: lower distance)
    for doc, meta, dist in zip(keyword_docs, keyword_metas, keyword_dists):
        chunk_id = meta.get("chunk_index", hash(doc))
        if chunk_id not in merged:
            merged[chunk_id] = (doc, meta, dist)
        else:
            # Keep better distance
            if dist < merged[chunk_id][2]:
                merged[chunk_id] = (doc, meta, dist)
    
    # Sort by distance and return top_n
    sorted_results = sorted(merged.values(), key=lambda x: x[2])[:top_n]
    
    docs = [r[0] for r in sorted_results]
    metas = [r[1] for r in sorted_results]
    dists = [r[2] for r in sorted_results]
    
    return docs, metas, dists
```

### 3.2 Reranking (Cross-Encoder)

#### Optional Cross-Encoder Reranking

```python
def rerank_with_cross_encoder(
    query: str,
    docs: list[str],
    metas: list[dict],
    dists: list[float],
    model_name: str = "cross-encoder/qnli-distilroberta-base",
    top_n: int = 8
) -> tuple[list, list, list]:
    """
    Use a cross-encoder model to re-rank retrieved documents
    
    Slower but more accurate than vector search alone
    Only use when accuracy matters more than speed
    """
    
    from sentence_transformers import CrossEncoder
    
    # Load cross-encoder
    reranker = CrossEncoder(model_name)
    
    # Prepare pairs (query, doc) for reranker
    pairs = [[query, doc] for doc in docs]
    
    # Score pairs
    scores = reranker.predict(pairs)  # Range: 0-1
    
    # Sort by score descending
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    
    # Return top_n
    reranked_docs = [docs[i] for i in sorted_indices[:top_n]]
    reranked_metas = [metas[i] for i in sorted_indices[:top_n]]
    reranked_dists = [1 - scores[i] for i in sorted_indices[:top_n]]  # Convert to distance
    
    return reranked_docs, reranked_metas, reranked_dists
```

**When to use reranking:**
- Queries where precision > recall matters
- Complex questions requiring deep understanding
- When user is dissatisfied with results

**When NOT to use:**
- Simple factual queries ("What is X?")
- Performance-critical applications
- Limited computational resources

### 3.3 Context Window Assembly

```python
def assemble_context(
    docs: list[str],
    metas: list[dict],
    max_chars: int = 14000
) -> str:
    """
    Assemble retrieval results into context window
    respecting token/char limits
    """
    
    lines = []
    total_chars = 0
    
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        # Build metadata header
        header = f"""
---
[Source {i}]
Document: {meta.get('filename', 'unknown')}
Page: {meta.get('page', '?')}
Section: {meta.get('section_title', 'general')}
"""
        if meta.get('source_url'):
            header += f"Source URL: {meta['source_url']}\n"
        
        # Add content
        content = f"\n{doc}"
        
        # Check length
        chunk_len = len(header) + len(content)
        if total_chars + chunk_len > max_chars:
            # Truncate this chunk
            remaining = max_chars - total_chars
            if remaining > 100:  # Only add if meaningful size
                content = content[:remaining]
                lines.append(header + content)
            break
        
        lines.append(header + content)
        total_chars += chunk_len
    
    return "\n".join(lines)
```

**Why limit context?**
- Ollama qwen2.5:3b: 4096 token context (≈ 14k chars)
- More context ≠ better quality
- Focus > confusion
- Respects model limits

### 3.4 Answer Generation with System Prompt

```python
def build_system_prompt(context: str, query: str) -> str:
    """
    Build the system prompt that guides LLM behavior
    """
    
    return f"""
You are an expert educational chatbot assistant for St. Anthony's College.

CRITICAL RULES (MUST FOLLOW):
1. Answer ONLY based on the provided college documents
2. If information is not in the documents, CLEARLY state: "I don't have this information in the available resources"
3. Always cite which document and page you're referencing
4. Be accurate, specific, and professional
5. For policy questions, note that the college should be contacted for definitive clarification
6. If the same question is asked differently, provide consistent information

FORMATTING RULES:
- Use markdown formatting
- Bold key information: **Important Detail**
- Use bullet points for lists
- Reference sources like: [See page X of {filename}]

DOCUMENT CONTEXT (from your knowledge base):
{context}

REMEMBER:
- You ONLY know what's in the documents above
- You are NOT a general knowledge assistant
- You CANNOT help with homework or assignments
- You CANNOT provide personal advice unrelated to college policies/procedures
- When unsure, ask for clarification before attempting to answer

Now answer the user's question based on the provided documents.
"""

def generate_answer(
    query: str,
    system_prompt: str,
    chat_history: list[dict] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024
) -> str:
    """
    Query local Ollama model for answer generation
    """
    
    import requests
    
    # Prepare messages
    messages = []
    
    # Add chat history if provided
    if chat_history:
        for msg in chat_history[-5:]:  # Last 5 messages for context
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Add current query
    messages.append({
        "role": "user",
        "content": query
    })
    
    # Query Ollama
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen2.5:3b",
            "messages": messages,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_k": 40,
                "top_p": 0.9,
                "num_predict": max_tokens,
            }
        },
        timeout=120
    )
    
    result = response.json()
    return result["message"]["content"]
```

---

## Document Processing Pipeline

### 4.1 Text Cleaning Algorithm

```python
def clean_loaded_text(text: str) -> str:
    """
    Comprehensive text cleaning for documents
    """
    
    if not text:
        return ""
    
    text = str(text)
    
    # Step 1: Remove null bytes and control characters
    text = text.replace("\x00", " ")
    
    # Step 2: Fix mixed-case institutional terms
    # Domain-specific: "anTi-Ragging" → "Anti-Ragging"
    text = repair_pdf_mixed_case_terms(text)
    
    # Step 3: Fix hyphenated breaks
    # "word-\nword" → "wordword"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    
    # Step 4: Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Step 5: Remove page number lines
    # Lines with only "1" or "- 5 -" or "Page 3 of 10"
    text = re.sub(
        r"^\s*(?:[-–]\s*)?\d+\s*(?:[-–]\s*)?$",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    
    # Step 6: Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    
    # Step 7: Collapse multiple newlines
    # Maximum 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Step 8: Remove spaces around newlines
    text = re.sub(r" *\n *", "\n", text)
    
    # Step 9: Final trim
    return text.strip()
```

### 4.2 Intelligent Chunking Algorithm

```python
def chunk_text(
    text: str,
    max_length: int = 450,      # words
    overlap: int = 100,          # words
    min_chunk_words: int = 8,
) -> list[str]:
    """
    Smart chunking that preserves document structure
    """
    
    # Preprocess
    text = clean_loaded_text(text)
    
    if not text or word_count(text) < min_chunk_words:
        return []
    
    # Phase 1: Split into logical blocks (respecting structure)
    blocks = split_text_blocks(text)
    
    # Phase 2: Recursive chunking with overlap
    chunks = []
    active_blocks = []
    
    for block in blocks:
        # If block is a heading and we have accumulated blocks, flush them
        if looks_like_section_heading(block.split('\n')[0]) and active_blocks:
            chunks.extend(flush_blocks(active_blocks, max_length, overlap))
            active_blocks = []
        
        # Accumulate block
        active_blocks.append(block)
    
    # Flush remaining blocks
    if active_blocks:
        chunks.extend(flush_blocks(active_blocks, max_length, overlap))
    
    return chunks


def flush_blocks(blocks, max_length, overlap):
    """Flush accumulated blocks into chunks"""
    chunks = []
    current = []
    current_words = 0
    
    for block in blocks:
        block_words = word_count(block)
        
        # If current chunk + block exceeds max, flush current
        if current and current_words + block_words > max_length:
            chunk_text = "\n\n".join(current)
            chunks.append(chunk_text)
            
            # Add overlap from previous chunk
            overlap_words = chunk_text.split()[-overlap:]
            current = [" ".join(overlap_words)] if overlap_words else []
            current_words = len(overlap_words)
        
        # Add block to current
        current.append(block)
        current_words += block_words
    
    # Flush final chunk
    if current:
        chunk_text = "\n\n".join(current)
        chunks.append(chunk_text)
    
    return chunks
```

---

## Performance Optimization

### 5.1 Embedding Performance

```python
# Current (CPU, batch_size=64):
# ~150 docs/min (100-word chunks)

# Optimizations:

# 1. GPU acceleration (if available)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    'BAAI/bge-small-en-v1.5',
    device='cuda' if torch.cuda.is_available() else 'cpu'
)

# 2. Batch encoding
embeddings = model.encode(
    texts,
    batch_size=256,  # Larger batches on GPU
    show_progress_bar=True
)

# 3. Faster model (trade-off: quality)
model = SentenceTransformer('all-MiniLM-L6-v2')  # 2x faster, comparable quality

# 4. Caching
embedding_cache = {}
def get_embedding(text):
    if text not in embedding_cache:
        embedding_cache[text] = model.encode([text])[0]
    return embedding_cache[text]
```

### 5.2 Retrieval Performance

```python
# Current (hybrid search):
# ~200ms per query (vector + keyword + merge)

# Optimizations:

# 1. Reduce candidates
RETRIEVAL_CANDIDATES = 50   # from 100
KEYWORD_CANDIDATES = 75     # from 150

# 2. Cache query embeddings (for repeated queries)
query_embedding_cache = {}
def get_query_embedding(query):
    key = hash(query)
    if key not in query_embedding_cache:
        query_embedding_cache[query] = encode_query(query)
    return query_embedding_cache[query]

# 3. Skip keyword search for semantic queries
if is_semantic_query(query):
    docs, metas, dists = vector_search(query, top_k=100)
else:
    # Hybrid search
    ...

# 4. Use approximate nearest neighbor (ANN) indices
# ChromaDB uses HNSW by default, which is already fast

# 5. Batch queries when possible
queries = ["query1", "query2", "query3"]
results = collection.query(
    query_embeddings=[encode_query(q) for q in queries],
    n_results=10
)
```

### 5.3 LLM Inference Performance

```python
# Current:
# ~2-5 seconds per response (qwen2.5:3b on CPU)

# Optimizations:

# 1. Reduce context window
MAX_CONTEXT_CHARS = 8000  # from 14000

# 2. Use faster model
# ollama pull phi:2.7b
# ollama pull neural-chat:7b

# 3. Reduce temperature (less creative = faster)
temperature = 0.1  # from 0.3

# 4. Limit output tokens
max_tokens = 512  # from 1024

# 5. Streaming responses (user sees partial answers)
response = stream_generate(query, max_tokens=512)
for chunk in response:
    print(chunk, end="", flush=True)

# 6. GPU acceleration
# Check: ollama list --gpu (shows GPU usage if enabled)
```

### 5.4 Database Query Performance

```sql
-- Add indices for common queries
CREATE INDEX idx_filename ON chunks(filename);
CREATE INDEX idx_source_url ON chunks(source_url);
CREATE INDEX idx_section_title ON chunks(section_title);
CREATE INDEX idx_scope_status ON chunks(scope, status);
CREATE INDEX idx_text_hash ON chunks(text_hash);

-- Composite index for common filters
CREATE INDEX idx_scope_filename ON chunks(scope, filename);
```

---

## Security Architecture

### 6.1 Authentication Flow

```
1. User Sign-Up
   ├─ Frontend sends email + password to Supabase
   ├─ Supabase creates auth.users record
   └─ Trigger fires → creates profiles record with role='student'

2. User Login
   ├─ Frontend sends credentials to Supabase
   ├─ Supabase returns JWT token (expires in 1 hour)
   └─ Frontend stores JWT in sessionStorage

3. API Request
   ├─ Frontend includes: Authorization: Bearer {JWT}
   ├─ Backend verifies JWT signature
   ├─ Backend extracts user_id from JWT
   └─ Backend checks user permissions

4. Token Refresh
   ├─ JWT expires after 1 hour
   ├─ Frontend uses refresh token to get new JWT
   ├─ Supabase returns new JWT (or 401 if refresh token expired)
   └─ User must re-login if both expired
```

### 6.2 Authorization Rules

```python
# Backend authorization checks (FastAPI dependencies):

def get_current_user(authorization: str = Header(None)):
    """Extract and verify JWT"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    
    token = authorization.split(" ")[1]
    user = supabase.auth.get_user(token)  # Verify JWT with Supabase
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return user


async def upload_document(
    file: UploadFile,
    current_user = Depends(get_current_user)
):
    """Only authenticated users can upload"""
    
    # Verify ownership
    if current_user.user_metadata['role'] not in ['admin', 'superadmin']:
        raise HTTPException(status_code=403, detail="Only admins can upload")
    
    # Process upload...


async def get_user_chats(
    current_user = Depends(get_current_user)
):
    """Users only see own chats"""
    
    chats = supabase.table("chat_sessions").select("*").eq(
        "user_id",
        current_user.id
    ).execute()
    
    return chats.data
```

### 6.3 Data Protection Measures

```python
# 1. Soft Deletes (recoverable)
def soft_delete_document(doc_id: str):
    collection.update(
        ids=[doc_id],
        metadatas=[{"deleted": True}]
    )

# 2. Text Hashing for Deduplication
def deduplicate_chunks(chunks):
    hashes = set()
    unique = []
    
    for chunk in chunks:
        h = compute_text_hash(chunk)
        if h not in hashes:
            hashes.add(h)
            unique.append(chunk)
    
    return unique

# 3. Audit Trail
def log_action(user_id, action, details):
    supabase.table("audit_logs").insert({
        "user_id": user_id,
        "action": action,
        "details": details,
        "timestamp": datetime.now().isoformat()
    })

# 4. PII Detection (optional)
def contains_pii(text: str) -> bool:
    """Detect potential personally identifiable info"""
    patterns = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',             # Credit card
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email (optional)
    ]
    
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    
    return False
```

---

## Scalability & Load Handling

### 7.1 Horizontal Scaling Strategy

```
Scenario: 10,000 concurrent users

Phase 1: Load Balancer
┌──────────────────────┐
│  Nginx Load Balancer │
└──────────┬───────────┘
         ↓ ↓ ↓
    ┌────┴─┬─┴────┐
    ↓      ↓      ↓
  API-1  API-2  API-3 (FastAPI instances)
    ↓      ↓      ↓
    └──────┬──────┘
           ↓
    ┌──────────────────┐
    │  Shared ChromaDB  │ (Single instance, shared storage)
    └──────────────────┘

Configuration:
- 3-5 API instances (scale based on CPU)
- Single ChromaDB (shared across instances)
- Shared file storage (NFS or S3)
```

### 7.2 Caching Strategy

```python
# Layer 1: Query Cache (in-memory)
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_vector_search(query: str, top_k: int = 8):
    return vector_search(query, top_k)

# Layer 2: Embedding Cache
embedding_cache = {}
def get_embedding_cached(text):
    if text not in embedding_cache:
        embedding_cache[text] = encode_query(text)
    return embedding_cache[text]

# Layer 3: Redis Cache (distributed)
import redis

cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_cached_response(query):
    key = f"response:{hash(query)}"
    
    cached = cache.get(key)
    if cached:
        return json.loads(cached)
    
    # Generate and cache
    response = ask(query)
    cache.setex(key, 3600, json.dumps(response))  # 1 hour TTL
    
    return response
```

### 7.3 Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/chat")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def chat(request: ChatRequest, current_user = Depends(get_current_user)):
    return ask(request.query)

# Per-user limits
@app.post("/upload")
@limiter.limit("50/day")  # 50 uploads per day per IP
async def upload_document(
    file: UploadFile,
    current_user = Depends(get_current_user)
):
    return ingest_file_bytes(file.file.read(), file.filename)
```

---

## Advanced Configuration

### 8.1 Custom Chunking Strategies

```python
# Strategy 1: Semantic Chunking (current)
# Chunks by document structure

# Strategy 2: Fixed-Size Sliding Window
def fixed_size_chunks(text, window_size=450, step_size=350):
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), step_size):
        chunk = " ".join(words[i:i + window_size])
        if len(chunk.split()) >= 8:
            chunks.append(chunk)
    
    return chunks

# Strategy 3: Paragraph-Based
def paragraph_chunks(text, max_paragraphs=3):
    paragraphs = text.split("\n\n")
    chunks = []
    current = []
    
    for para in paragraphs:
        current.append(para)
        if len(current) == max_paragraphs:
            chunks.append("\n\n".join(current))
            current = []
    
    if current:
        chunks.append("\n\n".join(current))
    
    return chunks

# Strategy 4: Sentence-Based
def sentence_chunks(text, max_sentences=10):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    
    for sent in sentences:
        current.append(sent)
        if len(current) == max_sentences:
            chunks.append(" ".join(current))
            current = []
    
    if current:
        chunks.append(" ".join(current))
    
    return chunks
```

### 8.2 Custom LLM Models

```python
# Current: Qwen2.5:3b
# Alternatives:

# Ultra-fast (speed > quality)
OLLAMA_MODEL = "phi:2.7b"      # ~500ms per response
OLLAMA_MODEL = "tinyllama:1.1b" # ~300ms per response

# Balanced (quality = speed)
OLLAMA_MODEL = "mistral:7b"      # ~2-3s per response
OLLAMA_MODEL = "neural-chat:7b"  # ~2-3s per response

# High-quality (quality > speed)
OLLAMA_MODEL = "llama2:13b"      # ~5-10s per response
OLLAMA_MODEL = "mistral:large"   # ~10-15s per response

# How to switch:
# 1. ollama pull new_model_name
# 2. Update OLLAMA_MODEL=new_model_name in .env
# 3. Restart backend: systemctl restart edubot-api
```

### 8.3 Custom Embedding Models

```python
# Current: BAAI/bge-small-en-v1.5 (384 dims)
# Alternatives:

# Faster embedding
EMBEDDING_MODEL = "all-MiniLM-L6-v2"      # 384 dims, very fast
EMBEDDING_MODEL = "all-MiniLM-L12-v2"     # 384 dims, fast

# Better quality
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"     # 768 dims, slower
EMBEDDING_MODEL = "bge-large-en-v1.5"        # 1024 dims, slowest

# Multilingual
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"     # For multiple languages
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"     # Larger multilingual

# How to switch:
# 1. Update EMBEDDING_MODEL=new_model in .env
# 2. DELETE backend/chroma_db/ (vectors incompatible)
# 3. Re-ingest all documents
# 4. Restart backend
```

---

## API Reference

### 9.1 Core Endpoints

#### Chat Endpoint

```
POST /chat
```

**Request:**
```json
{
  "query": "What are the admission requirements?",
  "history": [
    {"role": "user", "content": "Tell me about admissions"},
    {"role": "assistant", "content": "...response..."}
  ],
  "temperature": 0.3,
  "top_k": 8
}
```

**Response:**
```json
{
  "answer": "Based on the college handbook, undergraduate admission requirements...",
  "sources": [
    {
      "filename": "handbook.pdf",
      "page": 5,
      "section": "Admissions",
      "confidence": 0.95
    }
  ],
  "response_time_ms": 3421
}
```

#### Upload Document Endpoint

```
POST /upload
```

**Parameters:**
- `file` (multipart) - Document file
- `department` (string) - Department/category
- `document_type` (string) - Type of document
- `year` (string) - Academic year
- `scope` (string) - "official" or "personal"

**Response:**
```json
{
  "file": "handbook.pdf",
  "chunks_stored": 127,
  "pages_processed": 24,
  "status": "Ready for RAG search"
}
```

#### Website Crawl Endpoint

```
POST /crawl-website
```

**Request:**
```json
{
  "url": "https://college.edu",
  "max_pages": 50,
  "include_pdfs": true,
  "max_pdfs": 20,
  "department": "general"
}
```

**Response:**
```json
{
  "file": "https://college.edu",
  "chunks_stored": 245,
  "website_html_docs": 23,
  "website_pdf_docs": 5,
  "website_links_docs": 8,
  "status": "Ready for RAG search"
}
```

---

## Database Query Patterns

### 10.1 Common ChromaDB Queries

```python
from db import collection

# 1. Get all chunks for a document
docs = collection.get(
    where={"filename": {"$eq": "handbook.pdf"}},
    include=["documents", "metadatas"]
)

# 2. Get all chunks by document type
docs = collection.get(
    where={"document_type": {"$eq": "handbook"}},
    include=["documents", "metadatas"]
)

# 3. Get recent chunks
docs = collection.get(
    where={"scope": {"$eq": "official"}},
    order_by="created_at",
    include=["documents", "metadatas"]
)

# 4. Delete all chunks for a document
collection.delete(
    where={"filename": {"$eq": "old_handbook.pdf"}}
)

# 5. Soft delete chunks
collection.update(
    ids=[...],
    metadatas=[{"deleted": True}] * len(ids)
)

# 6. Count chunks
total = collection.count()
official = collection.count()  # (filtered internally)

# 7. Upsert/update metadata
collection.update(
    ids=["chunk_id_1", "chunk_id_2"],
    metadatas=[
        {"status": "archived"},
        {"status": "archived"}
    ]
)
```

### 10.2 Common Supabase Queries

```python
from supabase import create_client

supabase = create_client(url, key)

# 1. Get user profile
user = supabase.table("profiles").select("*").eq("id", user_id).execute()

# 2. Get user's chat sessions
sessions = supabase.table("chat_sessions") \
    .select("*") \
    .eq("user_id", user_id) \
    .order("created_at", desc=True) \
    .execute()

# 3. Get messages in session
messages = supabase.table("chat_messages") \
    .select("*") \
    .eq("session_id", session_id) \
    .order("created_at") \
    .execute()

# 4. Insert analytics record
supabase.table("analytics_queries").insert({
    "user_id": user_id,
    "query": query_text,
    "response_time_ms": 3421,
    "chunks_retrieved": 5,
    "model_used": "qwen2.5:3b"
}).execute()

# 5. Admin: Get all users
users = supabase.table("profiles").select("*").execute()

# 6. Admin: Change user role
supabase.table("profiles") \
    .update({"role": "admin"}) \
    .eq("id", user_id) \
    .execute()
```

---

**End of Technical Reference Guide** 📐

This guide provides deep architectural knowledge for production maintenance, optimization, and customization.
