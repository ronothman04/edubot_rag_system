# EduBot Technology Report

## 1. Project Overview

EduBot is a full-stack retrieval-augmented generation (RAG) chatbot for college information. Administrators can upload documents or crawl websites, the backend extracts and indexes their content, and users ask questions through a web chat interface. The application also includes authentication, role-based administration, analytics, document management, and crawl-job management.

This report is based on the current source code and dependency manifests, primarily `frontend/package.json`, `backend/requirements.txt`, `backend/api.py`, and the modules under `backend/rag/`.

## 2. Architecture at a Glance

```text
React browser application
        |
        | HTTP/JSON + bearer tokens
        v
FastAPI backend
        |-----------------------> Supabase Auth/PostgREST
        |
        +--> document and website ingestion
        |        +--> LangChain loaders/splitters
        |        +--> PDF, Office, HTML, and OCR tooling
        |
        +--> Sentence Transformers embeddings
        +--> ChromaDB vector index + BM25 keyword index
        +--> cross-encoder/custom reranking
        +--> configurable LLM provider
                 (Ollama by default; cloud providers optional)
```

## 3. Frontend Technologies

| Technology | Role in the project |
|---|---|
| JavaScript (ES modules) and JSX | Frontend implementation language and component syntax. |
| React 19 | Component-based user interface, hooks, state, and lifecycle management. |
| React DOM 19 | Mounts the React application in the browser. |
| Vite 8 | Development server, React build tooling, and production bundling. |
| Tailwind CSS 3 | Utility-first styling, responsive layouts, and class-based dark mode. |
| PostCSS and Autoprefixer | CSS processing and browser-prefix generation. |
| Supabase JavaScript SDK | Browser-side authentication, session management, and access to Supabase tables. |
| React Markdown + remark-gfm | Renders assistant responses as Markdown with GitHub-Flavored Markdown support. |
| Recharts | Charts in the administration analytics interface. |
| Lucide React | Icons used throughout the chat and administration interfaces. |
| React Hot Toast | In-app success and error notifications. |
| Browser Web APIs | `fetch`, `localStorage`, and `sessionStorage` are used for API calls and local chat/UI persistence. |
| ESLint | JavaScript and React static analysis, including Hooks and Fast Refresh rules. |

The frontend is a single-page application with custom view and URL-path handling in `App.jsx`; no separate routing library is declared. Its main feature areas are chat, authentication/password flows, settings, document administration, website crawling, query history, analytics, testing, and administrator management.

Frontend configuration is supplied through Vite environment variables:

- `VITE_API_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

## 4. Backend Technologies

### Core API

| Technology | Role in the project |
|---|---|
| Python | Backend and RAG implementation language. The project documentation requires Python 3.10+, while `backend/start.sh` is designed around the project's Python 3.11 virtual environment. |
| FastAPI | REST API framework for chat, uploads, crawling, authentication/role checks, document management, and admin operations. |
| Uvicorn | ASGI development/runtime server, installed through `fastapi[all]`. |
| Pydantic | Request model definition and validation through FastAPI. |
| python-dotenv | Loads backend configuration and secrets from `.env`. |
| Requests | HTTP client for LLM providers, Supabase REST/Auth endpoints, and web content. |
| FastAPI CORS middleware | Permits the configured frontend origins to call the backend. |

The principal backend entry point is `backend/api.py`. The API exposes chat, file upload, website crawl/job control, document management, search debugging, profile-role, and administrator-management endpoints.

### RAG, Search, and AI

| Technology | Role in the project |
|---|---|
| Sentence Transformers | Generates dense text/query embeddings and provides the optional local cross-encoder reranker. |
| `BAAI/bge-base-en-v1.5` | Default embedding model configured in `backend/embeddings.py`. |
| `BAAI/bge-reranker-base` | Default local cross-encoder model configured in `backend/reranker.py`. |
| ChromaDB | Persistent local vector database using a cosine-distance collection. |
| Rank BM25 | Maintains a local BM25 keyword index for hybrid retrieval. |
| Custom Python RAG modules | Query normalization/expansion, intent recognition, filters, hybrid retrieval, metadata and authority scoring, freshness resolution, context construction, answer builders, suggestions, and response caching. |
| PyTorch | Runtime device detection and model execution dependency, installed transitively with Sentence Transformers. Embeddings are currently explicitly loaded on CPU; the reranker can select CPU, CUDA, or Apple MPS. |

The retrieval design is hybrid rather than vector-only: ChromaDB semantic matches and BM25/keyword candidates are merged, scored, filtered, deduplicated, and optionally reranked before context is sent to an LLM.

### LLM Providers

`backend/llm.py` implements direct HTTP integrations with several configurable providers:

| Provider | Status in the code |
|---|---|
| Ollama | Default provider; default model is `llama3.2:3b`. |
| Groq | Optional OpenAI-compatible cloud provider. |
| Google Gemini | Optional direct Gemini API integration. |
| OpenRouter | Optional OpenAI-compatible provider. |
| Anthropic | Optional direct Anthropic API integration. |

The selected provider is controlled by `LLM_PROVIDER` and provider-specific environment variables. The code also implements retry/backoff behavior for rate limits and server failures.

### Document Ingestion and OCR

| Technology | Role in the project |
|---|---|
| LangChain Core, Community, and Text Splitters | Common document objects, loaders, and recursive chunking. |
| pdfplumber and pypdf | PDF text and table/content extraction. |
| docx2txt and python-docx | Microsoft Word document extraction/processing. |
| pandas, openpyxl, and xlrd | CSV and Excel ingestion. |
| Unstructured | HTML and general unstructured-document loading support. |
| Pillow + pytesseract | Image preprocessing and OCR via the external Tesseract engine. |
| JSON/text loaders and custom parsers | Support for text, Markdown, JSON, SQL/dump, HTML, and related upload formats. |

Uploaded source files are stored locally under `backend/data/uploads/`, while vector data is persisted under `backend/chroma_db/`.

### Website Crawling

| Technology | Role in the project |
|---|---|
| Crawl4AI 0.8.9 | Primary asynchronous website crawler and Markdown/content extraction pipeline. |
| Playwright 1.60 + Chromium | Browser automation and JavaScript-rendered page support used by Crawl4AI. |
| Trafilatura | Main-text extraction and part of the legacy/fallback crawler. |
| Beautiful Soup 4 | HTML parsing and link/content inspection. |
| lxml and lxml_html_clean | HTML parsing and cleanup. |
| urllib/urllib3 | URL handling, robots.txt processing, and lower-level HTTP support. |

The crawler supports recursive same-domain crawling, PDF discovery, crawl limits, background jobs, pause/resume/cancel controls, and fallback extraction when Crawl4AI fails.

### Authentication and Application Data

| Technology | Role in the project |
|---|---|
| Supabase Auth | User registration, sign-in, password recovery/update, sessions, and invitation flows. |
| Supabase PostgREST/database | Profiles, roles, admin invitations, activity logs, and frontend analytics/history data. |
| Supabase service-role REST calls | Server-side token validation and protected administrator operations. |
| JSON and pickle files | Local crawl-job state, response/retrieval caches, and the BM25 index. |

This project therefore has two distinct persistence layers: Supabase for user/application records and local ChromaDB/files for the RAG knowledge base and caches.

## 5. Testing and Development Tooling

- Backend tests use both `pytest` and Python's built-in `unittest`, with additional golden-set evaluation scripts for RAG quality.
- Frontend quality checks use ESLint.
- npm and `package-lock.json` provide reproducible frontend dependency installation.
- Python dependencies are listed in `backend/requirements.txt`, but most are not version-pinned.
- `backend/start.sh` launches Uvicorn from the project virtual environment and verifies that Crawl4AI is importable.
- FastAPI automatically provides OpenAPI/Swagger documentation at `/docs` while the backend is running.

## 6. Important Dependency Observations

- `backend/app.py` is an older Streamlit UI, but Streamlit is commented out in `backend/requirements.txt`. The active documented frontend is the React application and the active backend entry point is `backend/api.py`.
- Pillow is imported conditionally by the ingestion pipeline and directly by `backend/ocr.py`, but it is not explicitly listed in `backend/requirements.txt`.
- `pytest` is used by backend tests but is not explicitly listed in the requirements file.
- The backend requirements are largely unpinned, whereas the frontend records exact resolved versions in `package-lock.json`. Pinning production Python dependencies would improve reproducibility.
- No container definition, CI workflow, or production reverse-proxy configuration is present in the inspected project tree; deployment infrastructure is therefore not defined by this repository snapshot.

## 7. Technology Stack Summary

| Layer | Main technologies |
|---|---|
| Frontend | React 19, JavaScript/JSX, Vite 8, Tailwind CSS 3 |
| UI libraries | Lucide React, React Hot Toast, React Markdown, Recharts |
| Backend API | Python, FastAPI, Uvicorn, Pydantic |
| Authentication/data | Supabase Auth, Supabase JavaScript SDK, Supabase REST/PostgREST |
| RAG/search | Sentence Transformers, ChromaDB, BM25, custom hybrid retrieval/reranking |
| Default local AI | Ollama with `llama3.2:3b` |
| Optional cloud AI | Groq, Gemini, OpenRouter, Anthropic |
| Ingestion | LangChain, pdfplumber, pypdf, pandas, Office loaders, Unstructured |
| OCR | Tesseract, pytesseract, Pillow |
| Crawling | Crawl4AI, Playwright/Chromium, Trafilatura, Beautiful Soup, lxml |
| Testing/tooling | pytest, unittest, ESLint, npm, Python virtual environment |

## 8. Conclusion

EduBot successfully demonstrates the application of Artificial Intelligence and Retrieval-Augmented Generation (RAG) to improve access to educational information. By combining semantic search with Large Language Models (LLMs), the system provides accurate, context-aware, and reliable responses based on official institutional resources. Unlike traditional keyword-based search systems, EduBot understands the intent behind user queries and retrieves the most relevant information from institutional documents and websites.

The system enhances the overall user experience for students, parents, faculty, and visitors by providing instant assistance while reducing the workload of administrative staff. Its administrative portal enables efficient document management and website crawling, ensuring that the knowledge base remains up to date. Overall, EduBot offers a scalable, efficient, and intelligent solution for educational institutions seeking to modernize their information services through AI-powered automation.
