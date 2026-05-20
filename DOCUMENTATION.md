
# EduBot Project Documentation

## 1. Project Overview

EduBot is a college-focused RAG chatbot system. It allows users to ask questions about uploaded college documents and receive answers based only on those documents.

The project has two main parts:

- Frontend: React + Vite web app
- Backend: FastAPI Python API with RAG, OCR, document ingestion, Groq LLM, and ChromaDB vector storage

The system also uses Supabase for:

- User authentication
- Student/admin roles
- Chat analytics
- Admin invites
- Activity logs

## 2. Repository Structure

```text
EduBot-final(OCR)/
├── backend/
│   ├── api.py                 # Main FastAPI API
│   ├── app.py                 # Older Streamlit chat UI
│   ├── rag.py                 # RAG retrieval and answer generation
│   ├── ingestion.py           # Document loading, OCR, chunking, embedding
│   ├── db.py                  # ChromaDB setup and helpers
│   ├── embeddings.py          # SentenceTransformer embedding model
│   ├── llm.py                 # Groq LLM client
│   ├── requirements.txt       # Python dependencies
│   ├── .env                   # Backend environment variables
│   ├── data/uploads/          # Uploaded source documents
│   ├── chroma_db/             # Local ChromaDB vector database
│   └── venv/                  # Existing Python virtual environment
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main app routing/state
│   │   ├── main.jsx           # React entry point
│   │   ├── supabaseClient.js  # Supabase frontend client
│   │   ├── services/
│   │   │   ├── api.js         # Backend chat API calls
│   │   │   └── chatAnalytics.js
│   │   └── components/
│   │       ├── Auth.jsx
│   │       ├── ChatWindow.jsx
│   │       ├── InputBox.jsx
│   │       ├── Message.jsx
│   │       ├── Sidebar.jsx
│   │       ├── Settings.jsx
│   │       ├── AdminDashboard.jsx
│   │       └── admin/
│   │           ├── AdminDocuments.jsx
│   │           ├── AdminQueries.jsx
│   │           ├── AdminAnalytics.jsx
│   │           ├── AdminManagement.jsx
│   │           ├── AdminHistory.jsx
│   │           └── AdminTest.jsx
│   ├── package.json           # Frontend dependencies/scripts
│   ├── package-lock.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── .env                   # Frontend environment variables
│   ├── node_modules/          # Installed frontend packages
│   └── dist/                  # Built frontend output
│
└── Dcouments/                 # Test document packs and sample files
```

## 3. Installed / Existing Items

The current project already contains:

- `frontend/node_modules/`
- `frontend/package-lock.json`
- `backend/venv/`
- `backend/chroma_db/`
- `backend/data/uploads/`
- Built frontend output in `frontend/dist/`
- Sample college documents under `Dcouments/`
- Backend and frontend `.env` files

Important: the `.env` files contain real API keys/tokens. These should be treated as secrets and should not be committed publicly. If this project is shared, rotate those keys.

## 4. Frontend Documentation

### Frontend Stack

- React `19`
- Vite `8`
- Tailwind CSS `3`
- Supabase JS client
- Lucide React icons
- React Hot Toast
- React Markdown
- Recharts
- Remark GFM

### Main Frontend Features

- User login/register with Supabase
- Password reset/update flow
- Guest chat with 5-message limit
- Authenticated student chat
- Local chat history per user using `localStorage`
- Admin dashboard
- Admin document upload/delete UI
- Admin query review
- Admin analytics charts
- Admin management/invite page
- Theme/accent settings

### Frontend Scripts

Run from `frontend/`:

```bash
npm install
npm run dev
npm run build
npm run preview
npm run lint
```

### Frontend Environment Variables

Required in `frontend/.env`:

```env
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
VITE_API_URL=http://localhost:8000
```

### Frontend API Usage

The frontend calls the backend through:

```js
VITE_API_URL || "http://localhost:8000"
```

Main API service:

```text
frontend/src/services/api.js
```

It sends chat requests to:

```text
POST /chat
```

Payload:

```json
{
  "query": "student question",
  "history": "previous conversation history"
}
```

## 5. Backend Documentation

### Backend Stack

- FastAPI
- Uvicorn
- ChromaDB
- SentenceTransformers
- Groq API
- LangChain document loaders
- pdfplumber
- pandas
- openpyxl / xlrd
- docx2txt
- pytesseract
- Pillow
- Supabase REST/Auth API through `requests`

### Backend Dependencies

Listed in `backend/requirements.txt`:

```text
pdfplumber
sentence-transformers
chromadb
requests
fastapi[all]
email-validator
groq
python-dotenv
pandas
openpyxl
xlrd
pypdf
docx2txt
unstructured
langchain-core
langchain-community
langchain-text-splitters
langchain-chroma
pytesseract
```

### System Requirements

Besides Python packages, the backend also needs:

- Python environment
- Node.js/npm for frontend
- Tesseract OCR installed on the operating system
- Internet access on first model download
- Groq API key
- Supabase project

For OCR, `pytesseract` is only the Python wrapper. The actual Tesseract binary must also be installed.

### Backend Environment Variables

Required in `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
FRONTEND_URL=http://localhost:5173
```

### Backend Start Command

Run from `backend/` so ChromaDB uses the correct local path:

```bash
source venv/bin/activate
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

If setting up fresh:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 6. Backend API Endpoints

### `POST /chat`

Used by the chatbot.

Request:

```json
{
  "query": "What courses are offered?",
  "history": "User: ...\nAssistant: ..."
}
```

Alternative field:

```json
{
  "question": "What courses are offered?"
}
```

Response:

```json
{
  "answer": "answer text",
  "sources": [],
  "retrieval_query": "expanded/retrieval query",
  "used_history": false
}
```

### `POST /upload`

Uploads and indexes a document.

Form data:

```text
file=<uploaded file>
```

Supported file types:

```text
.pdf
.docx
.txt
.html
.htm
.csv
.md
.markdown
.json
.xlsx
.xls
.sql
.dump
.png
.jpg
.jpeg
.webp
```

Response includes ingestion stats:

```json
{
  "message": "Upload successful",
  "file": "document.pdf",
  "stats": {
    "chunks_created": 10,
    "chunks_stored": 10,
    "status": "Ready for RAG search"
  }
}
```

### `GET /documents`

Returns indexed/uploaded documents.

```json
{
  "documents": ["file1.pdf", "file2.docx"]
}
```

### `GET /documents/{filename}/download`

Downloads or previews the original uploaded document.

### `DELETE /documents/{filename}`

Deletes document chunks from ChromaDB and removes the local uploaded file.

### `POST /admin/invite-admin`

Invites or promotes an admin user.

Requires:

```text
Authorization: Bearer <supabase_user_access_token>
```

Request:

```json
{
  "email": "admin@example.com",
  "role": "admin"
}
```

Only users with `admin` or `super_admin` role can use this endpoint.

## 7. RAG Pipeline

The RAG pipeline is implemented mainly in:

```text
backend/rag.py
backend/ingestion.py
backend/db.py
backend/llm.py
backend/embeddings.py
```

### Ingestion Flow

1. Admin uploads a file from the frontend.
2. Backend saves it to `backend/data/uploads/`.
3. Backend extracts text depending on file type.
4. Images are processed with Tesseract OCR.
5. Text is cleaned.
6. Text is split into word chunks.
7. Chunks are embedded using `all-MiniLM-L6-v2`.
8. Chunks and metadata are stored in ChromaDB.

Chunk settings:

```text
CHUNK_SIZE = 450 words
CHUNK_OVERLAP = 80 words
MIN_CHUNK_WORDS = 8
```

### Retrieval Flow

1. User sends a question.
2. Backend checks for casual messages like `hi`, `thanks`, `bye`.
3. Short queries are expanded for better search.
4. SentenceTransformer creates a query embedding.
5. ChromaDB searches relevant chunks.
6. Low-quality chunks are filtered by cosine distance.
7. Context is sent to Groq.
8. Groq returns a document-only answer.

### Embedding Model

```text
all-MiniLM-L6-v2
```

Used in both ingestion and retrieval.

### Vector Database

ChromaDB collection:

```text
edubot_docs
```

Storage path:

```text
backend/chroma_db/
```

The collection uses cosine distance:

```python
metadata={"hnsw:space": "cosine"}
```

## 8. LLM Configuration

LLM provider:

```text
Groq
```

Default model:

```text
llama-3.1-8b-instant
```

Configured in:

```text
backend/llm.py
```

The backend enforces strict document-based answering. If the answer is not found in the provided context, EduBot responds:

```text
I'm sorry, I don't have enough information to answer that based on the available college resources.
```

## 9. Supabase Usage

### Frontend Supabase

Used for:

- Auth login/register
- Password recovery
- User session tracking
- Reading/writing chat logs
- Reading admin data

### Backend Supabase

Used for:

- Verifying admin access
- Inviting admins
- Promoting existing users to admin
- Writing admin activity logs

### Required Supabase Tables

The code expects these tables:

```text
profiles
chat_logs
admin_invites
admin_activity_logs
```

### Expected `profiles` Columns

```text
id or uuid
email
full_name
role
created_at
```

Roles used:

```text
student
admin
super_admin
```

### Expected `chat_logs` Columns

Minimum:

```text
id
user_id
user_email
question
answer
created_at
```

Optional columns used by analytics:

```text
conversation_id
category
is_answered
response_time_ms
```

### Expected `admin_invites` Columns

```text
id
email
role
status
invited_by
created_at
```

### Expected `admin_activity_logs` Columns

```text
id
action
target_email
performed_by
created_at
```

## 10. User Roles and Access

### Guest User

- Can access chat
- Limited to 5 user messages
- Prompted to log in after limit

### Student User

- Can log in/register
- Can chat with EduBot
- Chat conversations are stored in browser localStorage
- Chat analytics are saved to Supabase `chat_logs`

### Admin / Super Admin

- Redirected to admin views
- Can upload/delete documents
- Can view queries
- Can view analytics
- Can manage admins
- Can invite new admins
- Can clear chat history if Supabase permissions allow

## 11. Document Upload and Supported Formats

Supported uploads:

```text
PDF
DOCX
TXT
HTML
CSV
Markdown
JSON
Excel XLSX/XLS
SQL/DUMP
PNG/JPG/JPEG/WEBP images
```

Extraction methods:

- PDF: `pdfplumber`
- DOCX: `docx2txt`
- TXT/Markdown: text loader
- HTML: unstructured HTML loader
- CSV/Excel: pandas
- JSON: JSON parser
- Images: Tesseract OCR

## 12. Running the Project Locally

### Terminal 1: Backend

```bash
cd backend
source venv/bin/activate
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Backend URL:

```text
http://localhost:8000
```

### Terminal 2: Frontend

```bash
cd frontend
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## 13. Build for Production

Frontend build:

```bash
cd frontend
npm run build
```

Preview build:

```bash
npm run preview
```

Backend production run example:

```bash
cd backend
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000
```

## 14. Important Notes

- Run the backend from the `backend/` directory so ChromaDB uses `backend/chroma_db`.
- The first run may download the SentenceTransformer model.
- OCR requires system-level Tesseract installation.
- Supabase service role key must only be used on the backend.
- Do not expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code.
- Current CORS allows all origins with `allow_origins=["*"]`; restrict this in production.
- The existing `.env` files contain secrets and should be protected or rotated before sharing publicly.

## 15. Main Data Flow

```text
User question
   ↓
React frontend
   ↓
POST /chat
   ↓
FastAPI backend
   ↓
RAG query processing
   ↓
SentenceTransformer query embedding
   ↓
ChromaDB vector search
   ↓
Relevant document chunks
   ↓
Groq LLM
   ↓
Document-grounded answer
   ↓
Frontend displays answer and sources
```

## 16. Admin Document Flow

```text
Admin selects document
   ↓
Frontend uploads to POST /upload
   ↓
Backend saves original file
   ↓
Text/OCR extraction
   ↓
Chunking
   ↓
Embedding
   ↓
ChromaDB upsert
   ↓
Document becomes searchable in chat
```

## 17. Security Recommendations

Before deployment:

- Rotate exposed API keys if the repository was shared.
- Keep `.env` files out of Git.
- Restrict backend CORS to the frontend domain.
- Keep Supabase service role key backend-only.
- Add backend authentication checks to upload/delete document endpoints if admins only should access them.
- Review Supabase Row Level Security policies.
- Add file size limits for uploads.
- Add rate limiting for `/chat`.

## 18. Testing Checklist

Backend:

```bash
cd backend
source venv/bin/activate
uvicorn api:app --reload --port 8000
```

Test:

- `POST /chat`
- `POST /upload`
- `GET /documents`
- `DELETE /documents/{filename}`

Frontend:

```bash
cd frontend
npm run dev
npm run build
npm run lint
```

Manual checks:

- Login
- Register
- Chat as guest
- Chat as user
- Admin document upload
- Admin document delete
- Admin analytics
- Admin invite
```

One important issue I noticed while documenting: your environment files currently contain real-looking Supabase and Groq secrets. Treat them as compromised if this project has been shared, and rotate them before deployment.