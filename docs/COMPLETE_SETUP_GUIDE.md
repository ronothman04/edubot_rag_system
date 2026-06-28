# 🚀 EduBot: Complete Setup & Deployment Guide

A comprehensive step-by-step guide for setting up EduBot from scratch to production.

---

## Table of Contents

1. [Prerequisites & Installation](#prerequisites--installation)
2. [Initial Setup](#initial-setup)
3. [Backend Configuration](#backend-configuration)
4. [Frontend Configuration](#frontend-configuration)
5. [Running Locally](#running-locally)
6. [First-Time Document Ingestion](#first-time-document-ingestion)
7. [Testing & Validation](#testing--validation)
8. [Production Deployment](#production-deployment)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites & Installation

### System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| **CPU** | 2 cores | 4+ cores |
| **RAM** | 4GB | 16GB+ |
| **Disk** | 20GB | 50GB+ |
| **OS** | macOS 11+, Ubuntu 20.04+, Windows 10+ (WSL2) | Latest LTS |

### Step 1: Install Base Tools

#### macOS

```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add Homebrew to PATH
(echo; echo 'eval "$(/opt/homebrew/bin/brew shellenv)"') >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Install dependencies
brew install python@3.11 node@20 tesseract git

# Verify installations
python3.11 --version    # Python 3.11.x
node --version          # v20.x.x
npm --version           # 10.x.x
tesseract --version     # tesseract 5.x.x
```

#### Ubuntu 22.04 LTS

```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    nodejs npm \
    tesseract-ocr libtesseract-dev \
    git curl build-essential

# Verify installations
python3.11 --version
node --version
npm --version
tesseract --version
```

#### Windows (WSL2)

```powershell
# Open PowerShell as Administrator
# Enable WSL2
wsl --install
wsl --set-default-version 2

# Then in WSL2 terminal (Ubuntu)
# Follow Ubuntu instructions above
```

### Step 2: Install Ollama

#### macOS

```bash
# Install Ollama
brew install ollama

# Start Ollama (runs in background)
brew services start ollama

# Pull the model
ollama pull qwen2.5:3b

# Verify
ollama list
# Output: qwen2.5:3b  latest  3b     6.4 GB
```

#### Ubuntu/Linux

```bash
# Download and run install script
curl https://ollama.ai/install.sh | sh

# Start service
sudo systemctl start ollama
sudo systemctl enable ollama

# Pull the model
ollama pull qwen2.5:3b

# Verify
ollama list
```

#### Windows

```powershell
# Download from https://ollama.ai/download
# Run installer
# Then in PowerShell:
ollama pull qwen2.5:3b

# Start Ollama service
ollama serve
```

**Verify Ollama is running:**
```bash
curl http://localhost:11434/api/version
# Output: {"version":"0.1.0"}
```

### Step 3: Setup Supabase

1. Navigate to https://supabase.com
2. Sign up for free account
3. Create new project:
   - Organization: Create new or select existing
   - Project name: "edubot" (or your preference)
   - Database password: Strong password
   - Region: Choose closest to you
   - Wait for project to initialize (~2 minutes)

4. Once created, go to **Project Settings → API**
5. Copy these values (save in a secure file):
   - **Project URL** → `SUPABASE_URL`
   - **service_role** secret key → `SUPABASE_SERVICE_ROLE_KEY`
   - **anon/public** key → `SUPABASE_ANON_KEY` (for frontend)

6. In SQL Editor, run the database schema setup (see Section: "Database Schema Setup" below)

---

## Initial Setup

### Step 1: Clone/Create Project

```bash
# Option A: If you have existing project
cd /path/to/existing/EduBot
git pull origin main

# Option B: Create new project from scratch
mkdir EduBot && cd EduBot
git init
```

### Step 2: Create Project Structure

```bash
# Create directory structure
mkdir -p backend frontend
cd backend && mkdir -p data/uploads chroma_db logs tests
cd ../frontend && mkdir -p src/{components,services,admin}
cd ..
```

### Step 3: Copy Files

If recreating project, copy from the professional prompt:
- Backend Python files (api.py, rag.py, ingestion.py, db.py, embeddings.py, llm.py, etc.)
- Frontend React components and assets
- Configuration files (requirements.txt, package.json, etc.)

---

## Backend Configuration

### Step 1: Create Python Virtual Environment

```bash
cd backend

# Create venv
python3.11 -m venv venv

# Activate
# macOS/Linux:
source venv/bin/activate

# Windows PowerShell:
# .\venv\Scripts\Activate.ps1

# Verify activation (should show (venv) in prompt)
which python
# Output: /path/to/EduBot/backend/venv/bin/python
```

### Step 2: Install Dependencies

```bash
# Upgrade pip, setuptools, wheel
pip install --upgrade pip setuptools wheel

# Install from requirements.txt
pip install -r requirements.txt

# Verify installation (no errors)
python -c "import fastapi, chromadb, sentence_transformers; print('✓ All imports successful')"
```

### Step 3: Download Embedding Model

```bash
# Download SentenceTransformer model (600MB, first run only)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

# This creates ~/.cache/huggingface/
# Verify
ls -la ~/.cache/huggingface/hub/ | grep bge-small
```

### Step 4: Create Backend Environment File

```bash
# Create .env
cat > .env << 'EOF'
# =============================================================================
# OLLAMA CONFIGURATION
# =============================================================================
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=4096

# =============================================================================
# SUPABASE CONFIGURATION
# =============================================================================
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_public_key_here

# =============================================================================
# FRONTEND CONFIGURATION
# =============================================================================
FRONTEND_URL=http://localhost:5173

# =============================================================================
# EMBEDDING MODEL
# =============================================================================
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# =============================================================================
# API CONFIGURATION
# =============================================================================
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000
ALLOWED_ORIGIN_REGEX=^https?://(localhost|127\.0\.0\.1):(5173|3000)$

# =============================================================================
# RAG CONFIGURATION (Optional, Tuning)
# =============================================================================
# RETRIEVAL_CANDIDATES=100
# KEYWORD_CANDIDATES=150
# DEFAULT_TOP_K=8
# MAX_CONTEXT_CHARS=14000
EOF
```

**Fill in the values:**
```bash
# Edit .env with your actual values
nano .env

# Or use sed (macOS/Linux)
sed -i '' 's/YOUR_PROJECT_REF/your-actual-project-ref/' .env
sed -i '' 's/your_service_role_key_here/actual_key_value/' .env
```

### Step 5: Verify Backend Setup

```bash
# Test imports
python -c "
from api import app
from rag import ask
from ingestion import ingest_file_bytes
from db import collection
print('✓ Backend modules load successfully')
"

# Check ChromaDB
python -c "
from db import collection
print(f'✓ ChromaDB ready. Current chunks: {collection.count()}')
"
```

---

## Frontend Configuration

### Step 1: Install Dependencies

```bash
cd frontend

# Install npm packages
npm install

# Verify (should show no errors, maybe some warnings)
npm list --depth=0
```

### Step 2: Create Frontend Environment File

```bash
# Create .env
cat > .env << 'EOF'
# Backend API URL
VITE_API_URL=http://localhost:8000

# Supabase Configuration
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_public_key_here

# Optional: Feature flags
VITE_ENABLE_ANALYTICS=true
VITE_ENABLE_ADMIN_PANEL=true
EOF
```

**Fill in the values:**
```bash
# Edit .env
nano .env

# Or use sed
sed -i '' 's/YOUR_PROJECT_REF/your-actual-project-ref/' .env
```

### Step 3: Verify Frontend Build

```bash
# Build test
npm run build

# Output should show:
# ✓ built in 2.34s

# Check dist folder
ls -la dist/
# Should contain index.html, assets/, etc.

# Clean up
rm -rf dist
```

---

## Database Schema Setup

### Create Supabase Tables

1. Go to **Supabase Dashboard → SQL Editor**
2. Click **New Query**
3. Run each SQL block below (or paste entire file)

#### Block 1: Profiles Table

```sql
-- Create profiles table with user roles
CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid NOT NULL PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email character varying(255) NOT NULL,
  full_name character varying(255),
  role character varying(50) NOT NULL DEFAULT 'student'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT role_check CHECK (
    role = ANY(ARRAY['student'::text, 'staff'::text, 'admin'::text, 'superadmin'::text])
  )
);

-- Create RLS policies
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Users can view own profile
CREATE POLICY "Users can view own profile" ON public.profiles
  FOR SELECT
  USING (auth.uid() = id);

-- Users can update own profile
CREATE POLICY "Users can update own profile" ON public.profiles
  FOR UPDATE
  USING (auth.uid() = id);

-- Admins can view all profiles
CREATE POLICY "Admins can view all profiles" ON public.profiles
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'superadmin')
    )
  );

-- Index for performance
CREATE INDEX idx_profiles_email ON public.profiles(email);
CREATE INDEX idx_profiles_role ON public.profiles(role);
```

#### Block 2: Chat Sessions Table

```sql
CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  title character varying(255),
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

-- Users can access own sessions
CREATE POLICY "Users can access own sessions" ON public.chat_sessions
  FOR SELECT
  USING (auth.uid() = user_id);

-- Users can create sessions
CREATE POLICY "Users can create own sessions" ON public.chat_sessions
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Users can update own sessions
CREATE POLICY "Users can update own sessions" ON public.chat_sessions
  FOR UPDATE
  USING (auth.uid() = user_id);

-- Users can delete own sessions
CREATE POLICY "Users can delete own sessions" ON public.chat_sessions
  FOR DELETE
  USING (auth.uid() = user_id);

CREATE INDEX idx_chat_sessions_user ON public.chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_created ON public.chat_sessions(created_at);
```

#### Block 3: Chat Messages Table

```sql
CREATE TABLE IF NOT EXISTS public.chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
  role character varying(50) NOT NULL,
  content text NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT role_check CHECK (role = ANY(ARRAY['user'::text, 'assistant'::text]))
);

ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Users can access own messages
CREATE POLICY "Users can access own messages" ON public.chat_messages
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.chat_sessions
      WHERE id = session_id AND user_id = auth.uid()
    )
  );

-- Users can insert messages
CREATE POLICY "Users can insert messages" ON public.chat_messages
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.chat_sessions
      WHERE id = session_id AND user_id = auth.uid()
    )
  );

CREATE INDEX idx_chat_messages_session ON public.chat_messages(session_id);
CREATE INDEX idx_chat_messages_created ON public.chat_messages(created_at);
```

#### Block 4: Analytics Table

```sql
CREATE TABLE IF NOT EXISTS public.analytics_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  query text,
  response_time_ms integer,
  chunks_retrieved integer,
  model_used character varying(100),
  created_at timestamp with time zone DEFAULT now()
);

-- No RLS needed for analytics (admin read-only)
CREATE INDEX idx_analytics_user_date ON public.analytics_queries(user_id, created_at);
CREATE INDEX idx_analytics_response_time ON public.analytics_queries(response_time_ms);
```

#### Block 5: Function - Create User on Signup

```sql
-- Auto-create profile when user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    'student'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();
```

---

## Running Locally

### Terminal 1: Start Ollama (if not running as service)

```bash
# macOS/Linux (if installed via brew or apt)
# Already running as service, verify:
curl http://localhost:11434/api/version

# Windows or manual start:
ollama serve

# Wait for output:
# Serving on 127.0.0.1:11434
```

### Terminal 2: Start Backend API

```bash
cd backend

# Activate venv (if not already active)
source venv/bin/activate

# Start uvicorn
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Wait for output:
# Uvicorn running on http://0.0.0.0:8000
# Press CTRL+C to quit
```

### Terminal 3: Start Frontend Dev Server

```bash
cd frontend

# Start Vite dev server
npm run dev

# Output:
# ➜  Local:   http://localhost:5173/
# ➜  press h to show help
```

### Test the Application

```bash
# 1. Open http://localhost:5173 in browser
# 2. You should see login screen
# 3. Create new account:
#    - Email: test@example.com
#    - Password: SecurePassword123!
# 4. Sign up and verify email (if required by Supabase)
# 5. You should see chat interface
```

**If you see errors, check:**
```bash
# Check backend is running
curl http://localhost:8000/health

# Check Ollama is running
curl http://localhost:11434/api/version

# Check frontend can reach backend
# Open DevTools (F12) → Network tab
# Make a chat request and verify API calls to http://localhost:8000
```

---

## First-Time Document Ingestion

### Prepare Test Documents

```bash
# Create data/uploads directory
mkdir -p backend/data/uploads

# Download sample PDF or use your own
# Place in backend/data/uploads/

# Example: Create a simple test document
cat > backend/data/uploads/test_handbook.txt << 'EOF'
# College Handbook 2024-2025

## Admission Requirements

### Undergraduate Admissions
- High school diploma or equivalent
- Minimum GPA: 3.0
- SAT scores (minimum 1100) or ACT (minimum 25)
- Application fee: $50

### Graduate Admissions
- Bachelor's degree from accredited institution
- Minimum GPA: 3.2
- GRE scores (varies by program)
- Application fee: $75

## Fee Structure

### Tuition Fees (Per Semester)
- Engineering: $8,500
- Business: $7,500
- Liberal Arts: $6,500
- Graduate Programs: $9,000 - $12,000

### Mandatory Fees
- Student Activity Fee: $300
- Library Fee: $100
- Technology Fee: $200
- Parking Permit: $50

## Hostel Facilities

On-campus hostel available for students.
- Single room: $2,000/month
- Shared room: $1,200/month
- Includes meal plan (breakfast and dinner)

## Contact Information

**Main Office**: +1-555-0123
**Email**: info@college.edu
**Website**: https://college.edu
**Address**: 123 University Lane, City, State 12345
EOF
```

### Ingest via API

#### Option 1: Using curl

```bash
# Get JWT token (use actual token from frontend login)
export TOKEN="your_jwt_token_here"

# Upload document
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@backend/data/uploads/test_handbook.txt" \
  -F "department=general" \
  -F "document_type=handbook" \
  -F "year=2024" \
  -F "scope=official"

# Response should be:
# {
#   "file": "test_handbook.txt",
#   "chunks_stored": 12,
#   "status": "Ready for RAG search"
# }
```

#### Option 2: Using Python CLI

```bash
cd backend
python3 << 'EOF'
from ingestion import ingest_file_path

result = ingest_file_path(
    file_path="data/uploads/test_handbook.txt",
    department="general",
    document_type="handbook",
    scope="official"
)

print("Ingestion Complete!")
print(f"  Chunks created: {result['chunks_stored']}")
print(f"  Pages processed: {result['pages_processed']}")
print(f"  Status: {result['status']}")
EOF
```

### Verify Ingestion

```bash
# Check ChromaDB contains data
python3 << 'EOF'
from db import collection

count = collection.count()
print(f"Total chunks in database: {count}")

# Get sample chunk
results = collection.get(limit=1, include=["documents", "metadatas"])
if results["documents"]:
    print(f"\nSample chunk preview:")
    print(results["documents"][0][:200])
EOF
```

### Test Chat with Document

1. Go to http://localhost:5173
2. Start new chat
3. Ask: "What are the admission requirements?"
4. You should get an answer from the document

---

## Testing & Validation

### Backend Tests

#### Test 1: Document Ingestion

```bash
cd backend
python3 -m pytest tests/test_ingestion.py -v
```

#### Test 2: RAG Pipeline

```bash
python3 << 'EOF'
from rag import ask

response = ask(
    query="What are the undergraduate admission requirements?",
    top_k=5,
    temperature=0.3
)

print("Query Response:")
print(f"Answer: {response['answer'][:300]}...")
print(f"Sources found: {len(response['sources'])}")

assert len(response['answer']) > 50, "Answer too short"
print("✓ RAG test passed")
EOF
```

#### Test 3: API Endpoints

```bash
# Health check
curl http://localhost:8000/health
# Response: {"status":"ok"}

# Chat endpoint (requires auth)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "What is the parking fee?"
  }'
```

### Frontend Tests

#### Test 1: Component Mount

```bash
cd frontend
npm run dev

# Open DevTools → Console
# Should see no errors
```

#### Test 2: Chat Flow

1. Go to http://localhost:5173
2. Login with test account
3. Start new chat
4. Send message: "Hello"
5. Should see response in ~5 seconds
6. Check DevTools Network → should see API calls

#### Test 3: Document Upload

1. Go to Admin Dashboard
2. Click "Upload Document"
3. Select a test PDF
4. Fill metadata
5. Click Upload
6. Should see success notification

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] `.env` files configured with production values
- [ ] Supabase project created and tables set up
- [ ] Ollama running with qwen2.5:3b model
- [ ] ChromaDB tested and working
- [ ] All tests passing
- [ ] Frontend builds successfully
- [ ] Security review completed
- [ ] Backup strategy in place

### Option 1: Deploy Backend to Linux Server (Ubuntu 22.04)

#### Step 1: Provision Server

```bash
# Get Ubuntu 22.04 LTS server from:
# - AWS EC2
# - DigitalOcean
# - Linode
# - Google Cloud
# - Azure
# etc.

# SSH into server
ssh ubuntu@your.server.ip
```

#### Step 2: Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    nodejs npm \
    tesseract-ocr libtesseract-dev \
    nginx \
    git curl build-essential \
    supervisor

# Install Ollama
curl https://ollama.ai/install.sh | sh
sudo systemctl start ollama
sudo systemctl enable ollama

# Pull model
ollama pull qwen2.5:3b
```

#### Step 3: Setup Project

```bash
cd /opt
sudo git clone https://github.com/yourorg/edubot.git
sudo chown -R ubuntu:ubuntu edubot

cd edubot/backend

# Setup Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# Download embedding model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

#### Step 4: Create SystemD Service

```bash
sudo cat > /etc/systemd/system/edubot-api.service << 'EOF'
[Unit]
Description=EduBot FastAPI Service
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/opt/edubot/backend
Environment="PATH=/opt/edubot/backend/venv/bin"
EnvironmentFile=/opt/edubot/backend/.env
ExecStart=/opt/edubot/backend/venv/bin/gunicorn \
  --workers 4 \
  --bind 127.0.0.1:8000 \
  --timeout 300 \
  --access-logfile /opt/edubot/backend/logs/access.log \
  --error-logfile /opt/edubot/backend/logs/error.log \
  api:app
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable edubot-api
sudo systemctl start edubot-api
sudo systemctl status edubot-api
```

#### Step 5: Configure Nginx Reverse Proxy

```bash
sudo cat > /etc/nginx/sites-available/edubot << 'EOF'
upstream edubot_api {
    server 127.0.0.1:8000;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# Main HTTPS server block
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL Certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # File size limit
    client_max_body_size 100M;

    # API proxy
    location /api/ {
        proxy_pass http://edubot_api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }

    # Catch-all (for frontend, if hosted on same server)
    location / {
        root /opt/edubot/frontend/dist;
        try_files $uri /index.html;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/edubot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### Step 6: Setup SSL Certificate

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### Option 2: Deploy Frontend to Vercel

```bash
cd frontend

# Install Vercel CLI
npm install -g vercel

# Deploy (first time)
vercel

# Deploy to production
vercel --prod

# Your frontend will be at https://your-project.vercel.app
```

### Option 3: Deploy Frontend to Netlify

```bash
cd frontend

# Build
npm run build

# Deploy using Netlify CLI
npm install -g netlify-cli
netlify deploy --prod --dir=dist

# Or push to GitHub and connect GitHub repo to Netlify
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Check all services
check_health() {
    echo "Checking services..."
    
    echo -n "Ollama: "
    curl -s http://localhost:11434/api/version > /dev/null && echo "✓" || echo "✗"
    
    echo -n "Backend API: "
    curl -s http://localhost:8000/health > /dev/null && echo "✓" || echo "✗"
    
    echo -n "Frontend: "
    curl -s http://localhost:5173 > /dev/null && echo "✓" || echo "✗"
    
    echo -n "ChromaDB: "
    python3 -c "from db import collection; print('✓' if collection.count() >= 0 else '✗')" 2>/dev/null || echo "✗"
}

check_health
```

### Log Monitoring

```bash
# Backend logs
tail -f backend/logs/error.log
tail -f backend/logs/access.log

# Ollama logs (Linux)
journalctl -u ollama -f

# Frontend (browser console)
# Open DevTools → Console tab
```

### Regular Backups

```bash
# Backup ChromaDB
backup_chromadb() {
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    tar -czf "chroma_backup_${TIMESTAMP}.tar.gz" backend/chroma_db/
    echo "✓ Backup saved: chroma_backup_${TIMESTAMP}.tar.gz"
}

# Backup Supabase
# Use Supabase Dashboard → Backups → Trigger backup

# Schedule daily backups
# Add to crontab: 0 2 * * * /path/to/backup_chromadb.sh
```

---

## Troubleshooting

### Issue: Ollama Not Responding

**Symptoms:** API calls timeout, "Connection refused" errors

**Solution:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# If not running:
# macOS:
brew services start ollama

# Linux:
sudo systemctl start ollama

# Windows:
ollama serve

# Check logs
ollama logs

# Restart Ollama
brew services restart ollama
```

### Issue: "Model not found" Error

**Symptoms:** LLM responses fail with "model not found"

**Solution:**
```bash
# List available models
ollama list

# Pull missing model
ollama pull qwen2.5:3b

# Verify it's available
ollama list | grep qwen2.5

# If still failing, update .env
# Make sure OLLAMA_MODEL=qwen2.5:3b
```

### Issue: ChromaDB Errors

**Symptoms:** "Collection not found" or "Database locked"

**Solution:**
```bash
# Check ChromaDB is initialized
python3 -c "from db import collection; print(f'OK: {collection.count()} chunks')"

# If corrupted, reset (WARNING: loses all vectors)
rm -rf backend/chroma_db/
# ChromaDB will recreate on next run

# Re-ingest documents
python3 << 'EOF'
from ingestion import ingest_folder
results = ingest_folder('backend/data/uploads')
for r in results:
    print(f"{r['file']}: {r.get('chunks_stored', 0)} chunks")
EOF
```

### Issue: Slow Retrieval

**Symptoms:** Chat responses take >10 seconds

**Solution:**
```python
# Reduce candidates (in backend/rag.py)
RETRIEVAL_CANDIDATES = 50      # from 100
KEYWORD_CANDIDATES = 75        # from 150
DEFAULT_TOP_K = 5              # from 8

# Or use faster embedding model
# EMBEDDING_MODEL="all-MiniLM-L6-v2"  # Fast but less accurate
```

### Issue: High Memory Usage

**Symptoms:** System running slow, OOM errors

**Solution:**
```bash
# Reduce Ollama context window (in backend/.env)
OLLAMA_NUM_CTX=2048  # from 4096

# Or use smaller LLM model
OLLAMA_MODEL=phi:2.7b  # Very fast, lower quality

# Check process memory
top -b -n1 | head -20
```

### Issue: CORS Errors in Frontend

**Symptoms:** Browser console shows "CORS policy" errors

**Solution:**
```bash
# In backend/.env, check ALLOWED_ORIGINS
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://your-domain.com

# Verify in api.py CORS middleware
# Should match your frontend URL

# Clear browser cache
# Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows/Linux)
```

---

## Support Resources

- **Documentation:** See `PROFESSIONAL_REBUILD_PROMPT.md`
- **API Reference:** `backend/api.py` docstrings
- **Database Schema:** SQL setup section above
- **Known Issues:** GitHub Issues page
- **Community:** Discussions board

---

**Setup Guide Complete!** 🎉

For questions or issues, refer to troubleshooting section or create an issue in the repository.
