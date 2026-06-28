# 🎓 EduBot: Professional Project Reconstruction Prompt

**Complete System Prompt for Rebuilding EduBot from Scratch with Production-Grade Architecture**

---

## 📋 Executive Summary

**Project Name:** EduBot - Educational Institution Intelligent RAG Chatbot

**Objective:** Build a production-ready, full-stack document-grounded conversational AI system specifically designed for educational institutions (colleges/universities) to provide accurate, source-verified answers about institutional policies, procedures, courses, and resources.

**Core Purpose:**
- Enable students, parents, and staff to ask natural language questions about college documents
- Return answers **strictly grounded** in uploaded official documents
- Maintain complete audit trail and analytics
- Provide admin dashboard for document management and system monitoring

**Tech Stack:**
- **Frontend:** React 19 + Vite + TailwindCSS + Recharts (analytics)
- **Backend:** FastAPI (Python 3.10+)
- **Vector Database:** ChromaDB (persistent local storage)
- **LLM:** Ollama (local, privacy-first)
- **Embeddings:** SentenceTransformer (BAAI/bge-small-en-v1.5)
- **Authentication:** Supabase (auth, RBAC, analytics)
- **OCR:** Tesseract + Pillow
- **Document Parsing:** PDFPlumber, python-docx, pandas, BeautifulSoup4

---

## 🏗️ Part 1: Architecture & Design Principles

### 1.1 Core Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                            │
│ (React + Vite + TailwindCSS)                                 │
│ - Chat Interface                                              │
│ - Admin Dashboard                                             │
│ - Analytics & Insights                                        │
│ - Document Management                                         │
│ - User Settings & Auth                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓ REST API
┌─────────────────────────────────────────────────────────────┐
│               API ORCHESTRATION LAYER                         │
│ (FastAPI)                                                     │
│ - Request validation & routing                                │
│ - CORS & authentication middleware                            │
│ - File upload handling                                        │
│ - Response serialization                                      │
└─────────────────────────────────────────────────────────────┘
        ↓             ↓             ↓             ↓
┌──────────────┐ ┌───────────────┐ ┌────────────┐ ┌──────────┐
│ INGESTION    │ │ RAG PIPELINE  │ │ANALYTICS   │ │AUTH/RBAC │
│ LAYER        │ │ LAYER         │ │LAYER       │ │LAYER     │
├──────────────┤ ├───────────────┤ ├────────────┤ ├──────────┤
│• Document    │ │• Vector Search│ │• Chat logs │ │• Supabase│
│  Loading     │ │• Reranking    │ │• User acts │ │• JWT     │
│• Text Cleanup│ │• LLM Inference│ │• Analytics │ │• Roles   │
│• Chunking    │ │• Context Build│ │  queries   │ │• Profiles│
│• Embedding   │ │• Intent Guard │ │• Reporting │ │          │
│• Metadata    │ │• Answer Build │ │            │ │          │
└──────────────┘ └───────────────┘ └────────────┘ └──────────┘
        ↓             ↓             ↓             ↓
┌─────────────────────────────────────────────────────────────┐
│             PERSISTENCE & EXTERNAL SERVICES                  │
│ - ChromaDB (vector storage) │ Supabase (auth, logs)          │
│ - Ollama (LLM)              │ File System (uploads)          │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow Architecture

#### Document Ingestion Pipeline
```
User Uploads File / Crawls Website
        ↓
File Type Detection (PDF, DOCX, TXT, HTML, etc.)
        ↓
Load with Appropriate Parser
        ↓
Extract Text + Tables + OCR (if needed)
        ↓
Text Cleaning & Normalization
  - Remove headers/footers
  - Fix mixed-case terms
  - Remove page numbers
  - Normalize whitespace
        ↓
Intelligent Chunking with Metadata Context
  - Preserve section hierarchy
  - Detect document structure (headings, lists, tables)
  - Maintain heading paths for context
        ↓
Generate Chunk Metadata
  - Document info (filename, type, source)
  - Position info (page, section, heading path)
  - Content info (chunk type, word count, hash)
  - Administrative info (scope, user, timestamp)
        ↓
Encode Chunks with SentenceTransformer
  - Prefix query text with context
  - Batch encode for efficiency
  - Normalize embeddings
        ↓
Store in ChromaDB
  - Chunk ID (deterministic hash)
  - Vector embedding
  - Full metadata
  - Original chunk text
```

#### Query/Chat Pipeline
```
User Query (with optional chat history)
        ↓
Intent Classification & Guard
  - Homework detection (refuse)
  - Out-of-scope detection (decline)
  - Clarification needed (ask for details)
        ↓
Query Encoding (with search prefix)
        ↓
Hybrid Retrieval Strategy
  ├─ Vector Search (semantic)
  │  └─ Retrieve top 100 candidates
  │
  ├─ Keyword Search (exact/fuzzy matching)
  │  └─ Retrieve top 150 candidates
  │
  └─ De-duplicate & Combine
     └─ Merge results, preserve rankings
        ↓
Cross-Encoder Reranking (optional)
  - Score combined candidates
  - Re-rank by relevance
  - Keep top 8 for context
        ↓
Prepare Context Window
  - Organize chunks by heading path
  - Add metadata context (source, page)
  - Respect token limits (~14k chars for qwen2.5:3b)
        ↓
Generate System Prompt with Guidelines
  - Document-only grounding requirement
  - Format instructions (markdown)
  - Intent-specific handling
        ↓
Query Local Ollama LLM
  - System prompt + retrieval guidelines
  - Relevant chunks as context
  - User query
  - Optional chat history
        ↓
Parse LLM Response
  - Clean up formatting
  - Extract answer + citations
  - Flag confidence level
        ↓
Log to Analytics
  - Query + response
  - Retrieval statistics
  - LLM performance metrics
        ↓
Return to User
```

### 1.3 Key Design Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Vector DB** | ChromaDB (local) | Privacy, no external API calls, persistent, lightweight |
| **Embeddings** | SentenceTransformer (BGE-small) | Fast, accurate for retrieval, multilingual capable |
| **LLM** | Ollama (local) | Privacy, control, no API costs, can run offline |
| **LLM Model** | Qwen2.5:3b | Good balance: fast inference, decent quality, reasonable memory |
| **Chunking** | Intelligent semantic + rule-based | Preserves document structure, better context quality |
| **Metadata** | Rich, multi-layered | Enables filtering, debugging, analytics, audit trails |
| **Auth** | Supabase JWT | Industry standard, easy RBAC, built-in user management |

---

## 🔧 Part 2: Detailed Technical Specifications

### 2.1 Document Ingestion & Chunking Strategy

#### Supported File Types
- **Documents:** PDF, DOCX, TXT, HTML, CSV, Markdown, JSON, Excel, SQL dumps
- **Images:** PNG, JPG, JPEG, WEBP (OCR extraction)
- **Websites:** Full crawl with link extraction and PDF discovery

#### Text Cleaning Pipeline
```python
1. Remove null bytes & control characters
2. Repair mixed-case terms (domain-specific fixes)
3. Fix hyphenated word breaks across lines
4. Normalize line endings (CRLF → LF)
5. Remove standalone page numbers & "Page X of Y"
6. Collapse multiple spaces to single space
7. Collapse multiple newlines to max 2
8. Strip leading/trailing whitespace per line
```

#### Intelligent Chunking Algorithm

**Phase 1: Document Structure Detection**
- Identify headings (markdown, numbered, keyword-based)
- Detect tables (markdown tables, actual tables)
- Recognize lists (bullet, numbered)
- Identify section boundaries

**Phase 2: Block-Level Splitting**
- Split into logical blocks (paragraphs, tables, lists)
- Group semantically related blocks
- Detect content type per block (text, list, links, table, heading, PDF link)

**Phase 3: Recursive Chunking**
```
For each active block group:
  - If word_count < MIN_WORDS (8):
    Skip chunk
  
  - If word_count ≤ CHUNK_SIZE (450):
    Output single chunk
  
  - If word_count > CHUNK_SIZE:
    If is_table:
      Output table as-is (tables can exceed CHUNK_SIZE)
    Else:
      Split into overlapping windows:
      - Window size: CHUNK_SIZE (450 words)
      - Overlap: CHUNK_OVERLAP (100 words)
      - Step size: CHUNK_SIZE - CHUNK_OVERLAP (350 words)
```

**Phase 4: Heading Path Preservation**
- Build heading hierarchy from document structure
- Attach heading path to each chunk as metadata
- Example: "Admission > Eligibility > Engineering Programs"
- Enables context-aware filtering and answer building

#### Chunk Metadata Schema

```python
{
    # Document Identity
    "filename": str,                    # Original file name
    "source_filename": str,            # Copy of filename
    "file_type": str,                  # pdf, docx, txt, website, etc.
    "source_type": str,                # website_pdf, website_page, website_links, etc.
    
    # Position Information
    "page": int,                       # Page number (1-indexed)
    "page_label": str,                 # Custom page label if available
    "page_range": str,                 # "5-7" for multi-page chunks
    "total_pages": int,                # Total pages in source document
    "chunk_index": int,                # Position within document chunks
    
    # Content Classification
    "section_title": str,              # First-level section detected
    "heading_path": str,               # Full hierarchy "Section > SubSection > Part"
    "chunk_type": str,                 # text, table, list, heading, links, empty
    "table_title": str,                # Title extracted from table chunk
    "is_toc": bool,                    # Is this a table of contents
    
    # Content Metrics
    "text_chars": int,                 # Character count
    "word_count": int,                 # Word count
    "char_start": int,                 # Character offset in source
    "char_end": int,                   # Character end offset
    "text_hash": str,                  # SHA256 hash first 24 chars (deduplication)
    
    # Source Tracking
    "source_url": str,                 # For website crawls
    "found_on_url": str,               # Page where PDF link was found
    "crawl_base_url": str,             # Base URL of crawl
    "source_pdf_filename": str,        # For PDFs from website crawls
    "pdf_title": str,                  # Title of PDF if available
    
    # Administrative
    "doc_id": str,                     # Deterministic document ID (hash of filename + URL)
    "deleted": bool,                   # Soft delete flag
    "status": str,                     # "active" or other status
    "scope": str,                      # "official" or "personal"
    "uploaded_by": str,                # "admin" or "user"
    "user_id": str,                    # User who uploaded
    "session_id": str,                 # Session ID
    "department": str,                 # Department/category
    "document_type": str,              # Specific document classification
    "year": str,                       # Academic year
    
    # Technical
    "tables_extracted": int,           # Number of tables in page (PDF only)
    "ocr_used": bool,                  # Whether OCR was used
}
```

### 2.2 Embedding Strategy

#### Embedding Model
- **Model:** `BAAI/bge-small-en-v1.5` (SentenceTransformer)
- **Dimensions:** 384
- **Context Length:** 512 tokens max
- **Normalization:** L2 normalized for cosine similarity

#### Embedding Process
```python
# For ingestion (passages)
embedding = encode_texts(chunk_texts, batch_size=64)

# For retrieval (queries)
query_prefix = "Represent this sentence for searching relevant passages: "
prefixed_query = f"{query_prefix}{user_query}"
embedding = encode_query(prefixed_query)
```

#### Why This Model?
- Fast inference (suitable for batch encoding)
- Small footprint (easy deployment)
- Multilingual support
- Specifically trained for retrieval tasks
- Strong benchmark performance

### 2.3 Website Crawling & PDF Discovery

#### Crawling Strategy
1. **Initialization**
   - Start with base URL
   - Extract base domain for same-domain filtering
   - Initialize visited set, queue, and results list

2. **Page Crawling Loop**
   - Fetch page with proper headers
   - Parse HTML with BeautifulSoup + Trafilatura
   - Extract main content (text)
   - Extract and structure visible links
   - Discover new links for queue

3. **Link Processing**
   - Normalize URLs (remove fragments, optionally queries)
   - Validate domain (same-domain check)
   - Classify links:
     - **Document URLs:** PDFs, DOCX, Excel, etc.
     - **Regular URLs:** Regular web pages
     - **Blocked URLs:** Images, scripts, media, etc.

4. **Content Extraction**
   - **HTML pages:** Extract clean text using Trafilatura
   - **Links section:** Extract visible links with descriptions and URLs
   - **PDFs on pages:** Create "PDF link reference" documents
   - **PDFs in queue:** Download and ingest as full documents

5. **Document Creation**
   - Main page content → Document with metadata
   - Links section → Separate "website_links" document
   - PDF references → "website_document" documents (metadata-only)
   - PDF files → Full ingestion with pages and chunks

#### Smart Link Extraction
- **Priority headers:** "Quick links", "Downloads", "Resources", "Important", "Navigation"
- **Link types:** Regular links, PDF links (marked with [PDF] prefix)
- **Deduplication:** Track seen link combinations to avoid duplicates
- **Organization:** Group links by source header/section

#### Rate Limiting & Safety
- Configurable delay between requests (default 0.5s)
- Request timeout (25 seconds)
- Page limit (default 50, max 100)
- PDF limit (default 20, max 50)
- User-Agent header for identification
- Proper error handling and logging

### 2.4 RAG Pipeline - Retrieval & Answer Generation

#### Retrieval Process

**Step 1: Intent Classification**
```python
# Check query against patterns
if homework_pattern.matches(query):
    return HOMEWORK_REFUSAL  # "I can't help with homework"

if out_of_scope_pattern.matches(query):
    return OUT_OF_SCOPE_MESSAGE  # "I can only answer about college resources"

if needs_clarification_pattern.matches(query):
    return CLARIFICATION_MESSAGE  # "Please provide more details"
```

**Step 2: Hybrid Retrieval**

a) **Vector Search**
   ```
   - Encode query with BGE prefix
   - Search ChromaDB with cosine similarity
   - Retrieve top 100 candidates
   - Return docs, metadatas, distances
   ```

b) **Keyword Search**
   ```
   - Normalize query (lowercase, remove punctuation)
   - Scan all chunks for exact matches
   - Use difflib for fuzzy matching
   - Retrieve top 150 candidates
   - Return docs, metadatas with fake distances
   ```

c) **Merge & Deduplicate**
   ```
   - Combine vector and keyword results
   - Deduplicate by chunk ID
   - Preserve best distance score
   - Sort by relevance
   - Limit to top 50 before reranking
   ```

**Step 3: Cross-Encoder Reranking** (Optional)
```python
# If reranker available:
reranked_docs, reranked_metas, reranked_dists = rerank_chunks(
    query=query,
    docs=merged_docs,
    metas=merged_metas,
    dists=merged_dists,
    top_n=8
)
# Final result: top 8 most relevant chunks
```

**Step 4: Context Window Assembly**
```python
# Build organized context
context = []

for chunk, meta in zip(docs, metas):
    # Add metadata markers
    context.append(f"Document: {meta['filename']}")
    context.append(f"Page: {meta['page']}")
    context.append(f"Section: {meta['section_title']}")
    if meta.get('source_url'):
        context.append(f"Source: {meta['source_url']}")
    context.append("")  # Blank line
    context.append(chunk)  # Actual content
    context.append("---")  # Separator

# Join and respect context limit (~14,000 chars for qwen2.5:3b)
final_context = "\n".join(context)
if len(final_context) > MAX_CONTEXT_CHARS:
    # Truncate from end, preserve chunk boundaries
    final_context = truncate_to_boundary(final_context, MAX_CONTEXT_CHARS)
```

#### Answer Generation

**System Prompt Strategy**
```python
system_prompt = """
You are an expert educational institution chatbot assistant.

CRITICAL RULES:
1. ONLY answer based on the provided documents below
2. If information is not in the documents, say: "I don't have this information in the available resources"
3. Always cite which document and page you're referencing
4. If asked about something not covered, suggest where to find the answer

DOCUMENT CONTEXT:
{formatted_context}

REMEMBER:
- Be accurate and specific
- Reference document names and pages
- Admit when you don't know
- Suggest contacting the college for policy clarifications
"""
```

**LLM Parameters**
```python
parameters = {
    "model": "qwen2.5:3b",  # Local via Ollama
    "temperature": 0.3,     # Lower = more factual, less creative
    "top_k": 40,            # Reduce hallucinations
    "num_ctx": 4096,        # Context window limit
    "timeout": 120,         # Seconds
}
```

**Response Parsing**
```python
# Clean up response
- Remove markdown code blocks if present
- Fix OCR artifacts
- Normalize formatting
- Extract and highlight citations
```

### 2.5 Authentication & Authorization (Supabase)

#### User Roles
1. **Student** - Can only chat, view own history
2. **Staff/Faculty** - Can chat, view own history
3. **Admin** - Full access to documents, analytics, user management
4. **Superadmin** - System administration

#### Auth Flow
```
User Login
  ↓
Supabase JWT authentication
  ↓
Check role from `profiles` table
  ↓
Set access level in frontend state
  ↓
API calls include JWT in Authorization header
  ↓
Backend validates JWT + checks user_id for ownership
  ↓
Grant/deny access based on resource ownership + role
```

#### Key Tables
- **auth.users** - Supabase managed
- **profiles** - (id, email, full_name, role, created_at)
- **chat_sessions** - (id, user_id, title, created_at, updated_at)
- **chat_messages** - (id, session_id, role, content, created_at)
- **document_uploads** - (id, filename, uploader_id, uploaded_at, metadata)
- **analytics_queries** - (id, user_id, query, results_count, response_time_ms)

---

## 📦 Part 3: Technology Stack & Dependencies

### 3.1 Backend Requirements

```ini
# API Framework
fastapi==0.109.0
uvicorn==0.27.0
pydantic==2.5.0
email-validator==2.1.0

# Document Processing
pdfplumber==0.10.3
python-docx==1.0.1
pandas==2.1.3
openpyxl==3.11.0
xlrd==2.0.1
pypdf==4.0.1
docx2txt==0.8
unstructured==0.12.0

# Text Processing & NLP
langchain-core==0.1.0
langchain-community==0.0.0
langchain-text-splitters==0.0.0
langchain-chroma==0.1.0
sentence-transformers==2.2.2
beautifulsoup4==4.12.2
trafilatura==1.6.1
lxml==4.9.3

# Vector Database
chromadb==0.4.0

# LLM & ML
ollama==0.1.0

# OCR
pytesseract==0.3.10
Pillow==10.1.0

# Web
requests==2.31.0
urllib3==2.1.0

# Environment & Utilities
python-dotenv==1.0.0
```

### 3.2 Frontend Requirements

```json
{
  "dependencies": {
    "react": "^19.2.5",
    "react-dom": "^19.2.5",
    "@supabase/supabase-js": "^2.105.1",
    "react-hot-toast": "^2.6.0",
    "react-markdown": "^10.1.0",
    "remark-gfm": "^4.0.1",
    "lucide-react": "^1.14.0",
    "recharts": "^3.8.1"
  },
  "devDependencies": {
    "vite": "^8.0.10",
    "@vitejs/plugin-react": "^6.0.1",
    "tailwindcss": "^3.4.1",
    "postcss": "^8.5.13",
    "autoprefixer": "^10.5.0",
    "eslint": "^10.2.1"
  }
}
```

---

## 🚀 Part 4: Complete Step-by-Step Setup Guide

### 4.1 Prerequisites Installation

#### System Requirements
- macOS, Linux, or Windows (WSL2 recommended)
- Python 3.10 or newer
- Node.js 20+ and npm
- 8GB RAM minimum (16GB recommended)
- 20GB disk space for models and databases

#### Install Required Tools

**macOS:**
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 node@20 tesseract ollama

# Verify installations
python3 --version      # Should be 3.10+
node --version         # Should be 20+
npm --version          # Should be 9+
tesseract --version    # Tesseract version
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
sudo apt install -y nodejs npm
sudo apt install -y tesseract-ocr libtesseract-dev

# Ollama
curl https://ollama.ai/install.sh | sh
```

**Windows (WSL2):**
```powershell
# In WSL2 terminal
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
sudo apt install -y nodejs npm
sudo apt install -y tesseract-ocr

# Ollama: Install from https://ollama.ai/download
```

#### Setup Ollama

```bash
# Start Ollama service (runs in background)
ollama serve

# In another terminal, pull the model
ollama pull qwen2.5:3b

# Verify it's available
ollama list
# Should show: qwen2.5:3b
```

#### Setup Supabase Project

1. Go to https://supabase.com and create account
2. Create new project (any region)
3. Go to Project Settings → API
4. Copy:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`
   - `anon` key → `SUPABASE_ANON_KEY` (for frontend)

### 4.2 Project Setup

#### Clone/Open Project
```bash
# Navigate to project directory
cd /path/to/EduBot

# Or create new directory
mkdir EduBot && cd EduBot
```

#### Backend Setup

```bash
# Navigate to backend
cd backend

# Create Python virtual environment
python3.11 -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
# .\venv\Scripts\Activate.ps1

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# OR
cat > .env << 'EOF'
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=4096

# Supabase Configuration
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here

# Frontend Configuration
FRONTEND_URL=http://localhost:5173

# Embedding Model
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# API Configuration
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
EOF

# Download embedding model (first run only)
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

#### Frontend Setup

```bash
# Navigate to frontend (in new terminal)
cd frontend

# Install dependencies
npm install

# Create .env file
cat > .env << 'EOF'
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key_here
EOF

# Build frontend (optional, for production)
npm run build
```

### 4.3 Running the Application

#### Terminal 1: Start Ollama (if not running as service)
```bash
ollama serve
```

#### Terminal 2: Start FastAPI Backend
```bash
cd backend
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
Uvicorn running on http://0.0.0.0:8000
```

#### Terminal 3: Start React Frontend
```bash
cd frontend
npm run dev
```

Expected output:
```
VITE v5.0.0  ready in 300 ms

➜  Local:   http://localhost:5173/
➜  press h to show help
```

#### Verify Everything Works

1. Open http://localhost:5173 in browser
2. You should see login screen
3. Create account with Supabase authentication
4. Test uploading a document (backend/data/sample_pdf.pdf if available)
5. Try asking a question about the document

### 4.4 Database Setup & Migrations

#### ChromaDB (Automatic)
- ChromaDB automatically creates `chroma_db/` folder
- Creates `edubot_docs` collection on first run
- No manual setup needed

#### Supabase Schema

Run these SQL queries in Supabase SQL Editor:

```sql
-- Profiles table
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email VARCHAR(255) NOT NULL,
  full_name VARCHAR(255),
  role VARCHAR(50) DEFAULT 'student' CHECK (role IN ('student', 'staff', 'admin', 'superadmin')),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
  ON profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON profiles FOR UPDATE
  USING (auth.uid() = id);

-- Chat sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  title VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own sessions"
  ON chat_sessions FOR SELECT
  USING (auth.uid() = user_id);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role VARCHAR(50) CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own messages"
  ON chat_messages FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM chat_sessions
      WHERE id = chat_messages.session_id
      AND user_id = auth.uid()
    )
  );

-- Analytics table
CREATE TABLE IF NOT EXISTS analytics_queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
  query TEXT,
  response_time_ms INT,
  chunks_retrieved INT,
  model_used VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_analytics_user_date ON analytics_queries(user_id, created_at);
```

### 4.5 Ingestion Workflows

#### Workflow 1: Upload Single Document

```bash
# Via API (from frontend or curl)
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer {JWT_TOKEN}" \
  -F "file=@document.pdf" \
  -F "department=engineering" \
  -F "document_type=handbook" \
  -F "year=2024"

# Expected response
{
  "file": "document.pdf",
  "type": "PDF",
  "chunks_stored": 127,
  "pages_processed": 24,
  "status": "Ready for RAG search"
}
```

#### Workflow 2: Crawl Website

```bash
# Via API
curl -X POST http://localhost:8000/crawl-website \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {JWT_TOKEN}" \
  -d '{
    "url": "https://college.edu",
    "max_pages": 50,
    "include_pdfs": true,
    "max_pdfs": 20,
    "department": "general",
    "document_type": "website"
  }'

# Expected response
{
  "file": "https://college.edu",
  "chunks_stored": 245,
  "website_html_docs": 23,
  "website_pdf_docs": 5,
  "website_links_docs": 8,
  "status": "Ready for RAG search"
}
```

#### Workflow 3: Batch Folder Ingestion

```bash
# Place files in backend/data/uploads/
# Then via Python CLI:
python3 -c "
from ingestion import ingest_folder
results = ingest_folder('data/uploads', department='general')
for r in results:
    print(f\"{r['file']}: {r.get('status', 'Success')}\")
"
```

### 4.6 Testing the System

#### Test 1: Document Ingestion Test

```python
# backend/test_ingestion.py
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion import ingest_file_path

result = ingest_file_path(
    file_path="data/uploads/sample.pdf",
    department="general",
    document_type="handbook",
    scope="official"
)

print("Ingestion Result:")
print(f"  Chunks: {result['chunks_stored']}")
print(f"  Pages: {result['pages_processed']}")
print(f"  Status: {result['status']}")

assert result['chunks_stored'] > 0, "No chunks created!"
print("✓ Ingestion test passed")
```

Run:
```bash
cd backend
python3 test_ingestion.py
```

#### Test 2: RAG Query Test

```python
# backend/test_rag.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from rag import ask

response = ask(
    query="What are the admission requirements?",
    top_k=5,
    temperature=0.3
)

print("RAG Response:")
print(response['answer'])
print(f"Sources: {len(response['sources'])} documents")

assert len(response['answer']) > 20, "Answer too short!"
print("✓ RAG test passed")
```

#### Test 3: API Test

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test chat endpoint (requires auth)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer your_token_here" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the application deadlines?"
  }'
```

---

## 🔐 Part 5: Production Deployment Guide

### 5.1 Pre-Deployment Checklist

- [ ] Environment variables configured (.env files)
- [ ] Supabase project created and keys in place
- [ ] Ollama running with qwen2.5:3b model
- [ ] ChromaDB tested (contains sample data)
- [ ] Frontend built successfully (`npm run build`)
- [ ] Backend tests passing
- [ ] Security headers configured
- [ ] CORS settings reviewed
- [ ] Rate limiting configured
- [ ] Monitoring/logging setup

### 5.2 Backend Deployment (Linux Server)

```bash
# 1. Setup server (Ubuntu 22.04)
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv pip nodejs npm nginx
sudo apt install -y tesseract-ocr

# 2. Clone project
cd /opt
sudo git clone https://github.com/yourorg/edubot.git
sudo chown -R ubuntu:ubuntu edubot

# 3. Setup backend
cd edubot/backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# 4. Create systemd service
sudo cat > /etc/systemd/system/edubot-api.service << 'EOF'
[Unit]
Description=EduBot API Service
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/opt/edubot/backend
Environment="PATH=/opt/edubot/backend/venv/bin"
ExecStart=/opt/edubot/backend/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 --timeout 300 api:app
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# 5. Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable edubot-api
sudo systemctl start edubot-api

# 6. Configure Nginx as reverse proxy
sudo cat > /etc/nginx/sites-available/edubot << 'EOF'
upstream edubot_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 100M;

    location / {
        proxy_pass http://edubot_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/edubot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# 7. Setup SSL (Let's Encrypt)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 5.3 Frontend Deployment (Vercel/Netlify)

```bash
# 1. Build frontend
cd frontend
npm run build

# 2. Deploy to Vercel
npm install -g vercel
vercel --prod

# OR Netlify
npm install -g netlify-cli
netlify deploy --prod --dir=dist
```

### 5.4 Monitoring & Logging

```python
# backend/logging_setup.py
import logging
import json
from logging.handlers import RotatingFileHandler

# Setup structured logging
logger = logging.getLogger("edubot")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    "logs/edubot.log",
    maxBytes=10485760,  # 10MB
    backupCount=10
)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
```

---

## 📊 Part 6: Performance Optimization

### 6.1 Chunking Optimization

**Current Settings:**
- `CHUNK_SIZE = 450` words
- `CHUNK_OVERLAP = 100` words
- `MIN_CHUNK_WORDS = 8` words

**Optimization Tips:**
- Larger chunks (600-800 words): Better context but slower retrieval
- Smaller chunks (200-350 words): Faster retrieval but may lose context
- Adjust based on average query complexity

### 6.2 Embedding Optimization

**Model Selection:**
- Current: `BAAI/bge-small-en-v1.5` (384 dims, fast)
- Alternative: `BAAI/bge-base-en-v1.5` (768 dims, better quality but slower)
- Alternative: `all-MiniLM-L6-v2` (384 dims, very fast)

**Batch Encoding:**
```python
# Current: batch_size=64
# For GPU: increase to 256-512
# For CPU: keep at 32-64
```

### 6.3 Retrieval Optimization

**Hybrid Search Tuning:**
```python
RETRIEVAL_CANDIDATES = 100  # Increase for better recall
KEYWORD_CANDIDATES = 150    # Reduce for speed
DEFAULT_TOP_K = 8           # Balance quality vs context window
```

**Reranking:**
- Without reranker: Fast (good for user experience)
- With reranker: Better quality but 2-3x slower
- Use selectively (only for important queries)

### 6.4 Database Optimization

```sql
-- Create indices for common queries
CREATE INDEX idx_filename ON chunks(filename);
CREATE INDEX idx_source_url ON chunks(source_url);
CREATE INDEX idx_section_title ON chunks(section_title);
CREATE INDEX idx_scope_status ON chunks(scope, status);
CREATE INDEX idx_text_hash ON chunks(text_hash);
```

---

## 🛡️ Part 7: Security Best Practices

### 7.1 API Security
- JWT token validation on all endpoints
- CORS configured for specific origins only
- Rate limiting (100 requests/minute per IP)
- Input validation on all endpoints
- File upload size limits (100MB max)

### 7.2 Data Protection
- Soft delete pattern (never permanently delete user data)
- Audit trail for all document operations
- User isolation (users only see own chats)
- Encryption at rest (depends on deployment)

### 7.3 Model Safety
- Local LLM (no data sent to external services)
- Intent detection prevents homework help/off-topic
- System prompt enforces document-only grounding
- No personal information in system prompts

### 7.4 Environment Security
```bash
# Never commit .env files
echo ".env" >> .gitignore
echo "venv/" >> .gitignore
echo "chroma_db/" >> .gitignore
echo "__pycache__/" >> .gitignore

# Use environment variables in production
export SUPABASE_URL="..."
export SUPABASE_SERVICE_ROLE_KEY="..."
```

---

## 📈 Part 8: Quality Assurance & Testing

### 8.1 Unit Testing

```python
# backend/tests/test_ingestion.py
import pytest
from ingestion import chunk_text, clean_loaded_text, compute_text_hash

def test_clean_loaded_text():
    text = "Hello\r\n\r\n\r\nWorld"
    result = clean_loaded_text(text)
    assert "\n\n\n" not in result  # Max 2 newlines

def test_chunk_text():
    text = "word " * 600  # 600 words
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert 8 <= len(chunk.split()) <= 600

def test_compute_text_hash():
    hash1 = compute_text_hash("hello world")
    hash2 = compute_text_hash("hello world")
    assert hash1 == hash2  # Deterministic
```

### 8.2 Integration Testing

```python
# backend/tests/test_end_to_end.py
def test_document_ingestion_to_retrieval():
    # 1. Ingest document
    result = ingest_file_path("test_data/sample.pdf")
    assert result['chunks_stored'] > 0
    
    # 2. Query and retrieve
    response = ask("test query")
    assert len(response['sources']) > 0
```

### 8.3 Performance Testing

```bash
# Load test with ab (ApacheBench)
ab -n 1000 -c 10 http://localhost:8000/health

# Or use locust
pip install locust

cat > locustfile.py << 'EOF'
from locust import HttpUser, task

class ChatUser(HttpUser):
    @task
    def chat(self):
        self.client.post("/chat", json={"query": "test"})
EOF

locust -f locustfile.py --host=http://localhost:8000
```

---

## 🔄 Part 9: Maintenance & Operations

### 9.1 Regular Maintenance Tasks

**Daily:**
- Monitor API error logs
- Check Ollama service status
- Verify ChromaDB backups

**Weekly:**
- Review analytics dashboards
- Check storage usage
- Update documentation if needed

**Monthly:**
- Optimize ChromaDB collection
- Review and archive old chat histories
- Update dependencies (carefully)
- Test disaster recovery

### 9.2 Database Maintenance

```bash
# Backup ChromaDB
tar -czf chroma_db_backup_$(date +%Y%m%d).tar.gz backend/chroma_db/

# Clean old chat histories (>90 days)
python3 -c "
from db import collection
# Keep this as template for custom cleanup scripts
"

# Verify data integrity
python3 -c "
from db import collection
count = collection.count()
print(f'Total chunks: {count}')
"
```

### 9.3 Troubleshooting Guide

**Issue: Ollama not responding**
```bash
# Check if running
curl http://localhost:11434/api/version

# Restart
ollama serve

# Check logs (if running as service)
systemctl status ollama
```

**Issue: ChromaDB errors**
```bash
# Reset ChromaDB (WARNING: Deletes all vectors)
rm -rf backend/chroma_db/

# Will recreate on next run
```

**Issue: Slow retrieval**
```python
# Reduce candidates
RETRIEVAL_CANDIDATES = 50  # from 100
KEYWORD_CANDIDATES = 75    # from 150

# Or use faster embedding model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
```

---

## 📝 Part 10: Documentation & Knowledge Base

### 10.1 User Documentation

**For Students:**
1. How to ask questions
2. Interpreting answers
3. Reporting incorrect answers
4. Privacy & data handling

**For Admins:**
1. Uploading documents
2. Website crawling
3. User management
4. Analytics & reporting
5. Troubleshooting

### 10.2 Developer Documentation

1. API endpoint reference
2. Database schema
3. Authentication flow
4. Adding new document types
5. Customizing LLM behavior
6. Deploying updates

### 10.3 System Architecture Documentation

- Component diagrams
- Data flow diagrams
- Deployment architecture
- Disaster recovery plan

---

## 🎯 Part 11: Key Improvements Over Basic RAG

### Improvements Implemented

1. **Intelligent Chunking**
   - Preserves document structure
   - Maintains context hierarchy
   - Respects semantic boundaries

2. **Rich Metadata**
   - Enables filtering and faceting
   - Supports audit trails
   - Allows analytics

3. **Hybrid Retrieval**
   - Combines semantic + keyword search
   - Better recall for domain terms
   - Cross-encoder reranking for quality

4. **Document Safety**
   - Soft deletes (recoverable)
   - Deduplication (hashing)
   - Version tracking

5. **User Experience**
   - Role-based access
   - Personal vs official documents
   - Chat history preservation
   - Analytics & insights

6. **Production Ready**
   - Error handling throughout
   - Logging & monitoring
   - Security best practices
   - Scalable architecture

---

## 🚀 Quick Start Command Summary

```bash
# 1. Prerequisites
brew install python@3.11 node@20 tesseract ollama  # macOS
# OR apt install ... # Linux

# 2. Ollama
ollama serve &
ollama pull qwen2.5:3b

# 3. Backend
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "OLLAMA_BASE_URL=http://localhost:11434" > .env
# Add other env variables
uvicorn api:app --reload

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 5. Upload test document and chat!
# Open http://localhost:5173
```

---

## 📞 Support & Community

- GitHub Issues: Report bugs
- Discussions: Ask questions
- Email: support@edubot.edu
- Documentation: https://docs.edubot.edu

---

**End of Professional Rebuild Prompt**
