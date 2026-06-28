# EduBot

EduBot is a React + FastAPI RAG chatbot for asking questions about uploaded college documents. The backend handles document ingestion, OCR, embeddings, ChromaDB vector search, local Ollama LLM responses, and Supabase admin/auth integration. The frontend provides the chat UI, authentication, admin dashboard, document upload, analytics, and settings.

## Project Structure

```text
EduBot-final(OCR)/
├── backend/                 # FastAPI API, RAG, OCR, ChromaDB, Ollama integration
│   ├── api.py               # Main backend API
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Backend environment template
│   └── data/uploads/        # Uploaded documents, created at runtime
├── frontend/                # React + Vite app
│   ├── src/                 # Frontend source code
│   ├── package.json         # Frontend dependencies and scripts
│   └── .env.example         # Frontend environment template
└── DOCUMENTATION.md         # Additional project documentation
```

## Prerequisites

Install these before running the project:

- Python 3.10 or newer
- Node.js 20 or newer
- npm
- Tesseract OCR
- Ollama running locally with the configured model
- A Supabase project with anon and service role keys

Install Tesseract:

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt update
sudo apt install tesseract-ocr

# Windows
# Install from: https://github.com/UB-Mannheim/tesseract/wiki
```

## 1. Clone or Open the Project

```bash
cd "/Users/ebenezerjyrwa/Desktop/EduBot-final(OCR)"
```

If you are on another machine, replace the path with your project folder.

## 2. Backend Setup

Open a terminal from the project root, then run:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install Python requirements:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Create the backend environment file:

```bash
cp .env.example .env
```

Edit `backend/.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=4096
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
FRONTEND_URL=http://localhost:5173
```

Notes:

- Ollama must be running before chat responses can be generated.
- `OLLAMA_MODEL` must be pulled locally, for example `ollama pull llama3.2:3b`.
- `SUPABASE_SERVICE_ROLE_KEY` must stay private. Do not expose it in the frontend.
- `FRONTEND_URL` must match the Vite dev server URL so CORS works.

Run the backend:

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

The backend should now be available at:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

## 3. Frontend Setup

Open a second terminal from the project root:

```bash
cd frontend
npm install
```

Create the frontend environment file:

```bash
cp .env.example .env
```

Edit `frontend/.env`:

```env
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key_here
VITE_API_URL=http://localhost:8000
```

Run the frontend:

```bash
npm run dev
```

The app should be available at:

```text
http://localhost:5173
```

## 4. Running the Full Project

Use two terminals.

Terminal 1, backend:

```bash
cd backend
source venv/bin/activate
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2, frontend:

```bash
cd frontend
npm run dev
```

Then open:

```text
http://localhost:5173
```

## 5. Build for Production

Frontend production build:

```bash
cd frontend
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

## 6. Verify Installation

Backend health check:

```bash
curl http://localhost:8000/docs
```

Frontend check:

```bash
cd frontend
npm run build
```

Optional lint check:

```bash
cd frontend
npm run lint
```

## 7. Uploading Documents

Run both backend and frontend, then use the admin document upload page in the frontend.

Supported document types include:

```text
.pdf, .docx, .txt, .html, .htm, .csv, .md, .markdown, .json,
.xlsx, .xls, .sql, .dump, .png, .jpg, .jpeg, .webp
```

Uploaded files are stored locally under:

```text
backend/data/uploads/
```

Vector embeddings are stored locally in:

```text
backend/chroma_db/
```

These folders are runtime data and are ignored by Git.

## 8. Common Issues

### Ollama request failed

Make sure Ollama is running and the configured model is available:

```bash
ollama serve
ollama pull llama3.2:3b
```

Restart the backend after changing `.env`.

### Frontend cannot connect to backend

Check that the backend is running on port `8000` and that `frontend/.env` has:

```env
VITE_API_URL=http://localhost:8000
```

Also confirm `backend/.env` has:

```env
FRONTEND_URL=http://localhost:5173
```

### OCR does not work

Make sure Tesseract is installed and available from the terminal:

```bash
tesseract --version
```

### First document upload or first chat is slow

The backend may download the embedding model the first time it runs. Keep the backend terminal open and wait for the download to finish.

### Supabase admin actions fail

Check these backend variables:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
```

Also confirm the Supabase tables and roles expected by the app exist, including `profiles`, `admin_invites`, and `admin_activity_logs`.

## 9. Optional Streamlit UI

`backend/app.py` is an older Streamlit chat UI. The main project uses the React frontend. To run the Streamlit UI separately, install Streamlit:

```bash
cd backend
source venv/bin/activate
pip install streamlit
streamlit run app.py
```

Keep the FastAPI backend running at `http://localhost:8000` while using it.

## 10. Useful Commands

```bash
# Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

## Security Notes

- Never commit real `.env` files.
- Keep the Supabase service role key only in `backend/.env`.
- If keys were shared publicly, rotate them in Supabase and any other affected services.
