from __future__ import annotations
import os
from pathlib import Path
from typing import Literal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# FIX 1: removed ingest_from_url — unused, /crawl-website uses ingest_website
# FIX 5: removed asyncio import — only used in dead endpoint
# FIX 6: removed ThreadPoolExecutor import — only used in dead endpoint
from db import collection, hard_delete_document
from ingestion import (
    SUPPORTED_EXTENSIONS,
    ingest_file_bytes,
    ingest_website,
    normalize_url,
    create_crawl_job,
    get_crawl_job,
    control_crawl_job,
    run_crawl_background,
    get_all_crawl_jobs,
    delete_crawl_job,
)
from rag import ask
from rag.debug import debug_search_chunks


load_dotenv()
load_dotenv(Path(__file__).resolve().parent / ".env")

app = FastAPI()

UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        f"{FRONTEND_URL},http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
ALLOWED_ORIGIN_REGEX = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1):5173$",
)

PROFILE_ID_COLUMNS = ("id", "uuid")

# Server-side hard caps for crawl jobs — prevent runaway crawls regardless of the
# limits a client requests. Overridable via env for larger official sites.
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "1000"))
MAX_CRAWL_PDFS = int(os.getenv("MAX_CRAWL_PDFS", "500"))
MAX_CRAWL_DEPTH = int(os.getenv("MAX_CRAWL_DEPTH", "6"))


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str | None = None
    question: str | None = None
    history: str | list[ChatHistoryMessage] | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    top_k: int | None = None


class InviteAdminRequest(BaseModel):
    email: str
    role: str = "admin"


class CompleteAdminInviteRequest(BaseModel):
    full_name: str | None = None


class RemoveAdminRequest(BaseModel):
    profile_id: str


class WebsiteCrawlRequest(BaseModel):
    url: str
    max_pages: int = 500
    max_pdfs: int = 200
    include_pdfs: bool = True
    department: str = "general"
    document_type: str = "website"
    year: str = "general"
    same_domain_only: bool = True
    max_depth: int = 3


class CrawlControlRequest(BaseModel):
    action: str


class WebsiteDeleteRequest(BaseModel):
    url: str


class DebugSearchRequest(BaseModel):
    query: str
    top_k: int = 10


def format_chat_history(history: str | list[ChatHistoryMessage] | None) -> str:
    if history is None:
        return ""
    if isinstance(history, str):
        return history
    return "\n".join(
        f"User: {m.content}" if m.role == "user" else f"Assistant: {m.content}"
        for m in history
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE ADMIN HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def require_supabase_config() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Supabase admin configuration is missing on the backend.",
        )


def require_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return authorization.removeprefix("Bearer ").strip()


def service_headers() -> dict[str, str]:
    require_supabase_config()
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def describe_response(response: requests.Response) -> str:
    detail = response.text.strip() or "Unknown upstream error."
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            body = response.json()
        except ValueError:
            return detail
        if isinstance(body, dict):
            detail = (
                body.get("message")
                or body.get("msg")
                or body.get("error_description")
                or body.get("error")
                or body.get("hint")
                or detail
            )
    return detail


def fetch_current_user(access_token: str) -> dict:
    try:
        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase auth request failed: {exc}",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail=describe_response(response))

    return response.json()


def fetch_profile_role(user_id: str) -> str | None:
    last_missing_column_error = None

    for profile_id_column in PROFILE_ID_COLUMNS:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={profile_id_column: f"eq.{user_id}", "select": "role"},
                headers=service_headers(),
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase profiles request failed: {exc}",
            ) from exc

        if response.status_code == 200:
            rows = response.json()
            if rows:
                return rows[0].get("role")
            continue

        detail = describe_response(response)
        if "column" in detail.lower() and profile_id_column in detail:
            last_missing_column_error = detail
            continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify admin role: {detail}",
        )

    if last_missing_column_error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify admin role: {last_missing_column_error}",
        )

    raise HTTPException(status_code=403, detail="Profile not found.")


def ensure_admin_access(authorization: str | None) -> dict:
    access_token = require_bearer_token(authorization)
    current_user = fetch_current_user(access_token)
    role = fetch_profile_role(current_user.get("id", ""))
    if role not in {"admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


def is_missing_column_error(detail: str, column: str) -> bool:
    return "column" in detail.lower() and column in detail


def fetch_profile_by_email(email: str) -> dict | None:
    last_missing_column_error = None

    for profile_id_column in PROFILE_ID_COLUMNS:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={
                    "email": f"eq.{email}",
                    "select": f"{profile_id_column},email,role",
                    "limit": "1",
                },
                headers=service_headers(),
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase profile lookup failed: {exc}",
            ) from exc

        if response.status_code == 200:
            rows = response.json()
            if not rows:
                return None
            profile = rows[0]
            profile["profile_id"] = profile.get(profile_id_column)
            profile["profile_id_column"] = profile_id_column
            return profile

        detail = describe_response(response)
        if is_missing_column_error(detail, profile_id_column):
            last_missing_column_error = detail
            continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {detail}",
        )

    if last_missing_column_error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {last_missing_column_error}",
        )

    return None


def fetch_admin_management_data() -> dict:
    last_missing_column_error = None
    admins = []

    for profile_id_column in PROFILE_ID_COLUMNS:
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={
                    "role": "in.(admin,super_admin)",
                    "select": f"{profile_id_column},email,role,created_at",
                    "order": "created_at.desc",
                },
                headers=service_headers(),
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase admins lookup failed: {exc}",
            ) from exc

        if response.status_code == 200:
            admins = [
                {
                    "id": row.get(profile_id_column),
                    "profile_id_column": profile_id_column,
                    "email": row.get("email"),
                    "role": row.get("role"),
                    "created_at": row.get("created_at"),
                }
                for row in response.json()
            ]
            break

        detail = describe_response(response)
        if is_missing_column_error(detail, profile_id_column):
            last_missing_column_error = detail
            continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed to load admins: {detail}",
        )
    else:
        if last_missing_column_error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load admins: {last_missing_column_error}",
            )

    try:
        invites_response = requests.get(
            f"{SUPABASE_URL}/rest/v1/admin_invites",
            params={
                "status": "eq.pending",
                "select": "id,email,role,status,created_at",
                "order": "created_at.desc",
            },
            headers=service_headers(),
            timeout=15,
        )
        logs_response = requests.get(
            f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
            params={
                "select": "id,action,target_email,created_at",
                "order": "created_at.desc",
                "limit": "10",
            },
            headers=service_headers(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase admin management lookup failed: {exc}",
        ) from exc

    if invites_response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load pending invites: {describe_response(invites_response)}",
        )
    if logs_response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load activity logs: {describe_response(logs_response)}",
        )

    return {
        "admins": admins,
        "invites": invites_response.json(),
        "logs": logs_response.json(),
    }


def patch_profile_role(profile_id: str, role: str) -> None:
    last_missing_column_error = None

    for profile_id_column in PROFILE_ID_COLUMNS:
        try:
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={profile_id_column: f"eq.{profile_id}"},
                headers={
                    **service_headers(),
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                json={"role": role},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase profile update failed: {exc}",
            ) from exc

        if response.status_code < 400:
            return

        detail = describe_response(response)
        if is_missing_column_error(detail, profile_id_column):
            last_missing_column_error = detail
            continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed to update profile role: {detail}",
        )

    if last_missing_column_error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update profile role: {last_missing_column_error}",
        )


def upsert_admin_profile(user_id: str, email: str, full_name: str) -> None:
    last_missing_column_error = None

    for profile_id_column in PROFILE_ID_COLUMNS:
        try:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers={
                    **service_headers(),
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=representation",
                },
                json={
                    profile_id_column: user_id,
                    "email": email,
                    "full_name": full_name,
                    "role": "admin",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase profile save failed: {exc}",
            ) from exc

        if response.status_code < 400:
            return

        detail = describe_response(response)
        if is_missing_column_error(detail, profile_id_column):
            last_missing_column_error = detail
            continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save admin profile: {detail}",
        )

    if last_missing_column_error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save admin profile: {last_missing_column_error}",
        )


def get_pending_admin_invite(email: str) -> dict | None:
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/admin_invites",
            params={
                "email": f"eq.{email}",
                "status": "eq.pending",
                "select": "id,email,role,status",
                "limit": "1",
            },
            headers=service_headers(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase invites lookup failed: {exc}",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing invites: {describe_response(response)}",
        )

    rows = response.json()
    return rows[0] if rows else None


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/auth/profile-role")
def get_profile_role(authorization: str | None = Header(default=None)):
    access_token = require_bearer_token(authorization)
    current_user = fetch_current_user(access_token)
    role = fetch_profile_role(current_user.get("id", ""))
    return {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
        "role": role,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CHAT ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        clean_query = (request.query or request.question or "").strip()
        if not clean_query:
            raise HTTPException(status_code=400, detail="Query is required.")

        history_text = format_chat_history(request.history)
        result = ask(
            query=clean_query,
            history=history_text,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            top_k=request.top_k,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT UPLOAD ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

# FIX 7 (SECURITY): added admin auth guard — was completely open before
@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    department: str = Form("general"),
    document_type: str = Form("general"),
    year: str = Form("general"),
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required.")

    filename = Path(file.filename).name
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported types: {supported}",
        )

    local_path = UPLOAD_DIR / filename

    try:
        file_bytes = await file.read()
        local_path.write_bytes(file_bytes)
        stats = ingest_file_bytes(
            file_bytes=file_bytes,
            filename=filename,
            department=(department or "general").strip().lower(),
            document_type=(document_type or "general").strip().lower(),
            year=(year or "general").strip(),
            scope="official",
        )
        return JSONResponse(
            content={
                "message": "Upload successful",
                "file": filename,
                "stats": stats,
            }
        )
    except Exception as exc:
        if local_path.exists():
            local_path.unlink()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSITE CRAWL ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

# FIX 8 (SECURITY): added admin auth guard — was completely open before
@app.post("/crawl-website")
def crawl_website_endpoint(
    request: WebsiteCrawlRequest,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    try:
        result = ingest_website(
            url=request.url,
            session_id=None,
            user_id=None,
            department=request.department,
            document_type=request.document_type,
            year=request.year,
            scope="official",
            # Clamp client-supplied limits to server-side caps (anti-runaway crawl).
            max_pages=min(request.max_pages, MAX_CRAWL_PAGES),
            include_pdfs=request.include_pdfs,
            max_pdfs=min(request.max_pdfs, MAX_CRAWL_PDFS),
            same_domain_only=request.same_domain_only,
            max_depth=min(request.max_depth, MAX_CRAWL_DEPTH),
        )
        return {
            "success": True,
            "message": result.get("message") or "Website crawled successfully.",
            "base_url": request.url,
            "pages_crawled": result.get("pages_processed", 0),
            "documents_downloaded": result.get("website_pdf_docs", 0),
            "chunks_added": result.get("chunks_stored", 0),
            "skipped_duplicates": result.get("duplicates_skipped", 0),
            "result": result, # Preserve full stats for UI
            "errors": [],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": f"Website crawling failed: {str(e)}",
                "errors": [str(e)]
            },
        )


@app.post("/crawl/start")
def crawl_start(
    request: WebsiteCrawlRequest,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    job_id = create_crawl_job()

    import threading
    t = threading.Thread(
        target=run_crawl_background,
        args=(
            job_id,
            request.url,
            request.department,
            request.document_type,
            request.year,
            # Clamp client-supplied limits to server-side caps (anti-runaway crawl).
            min(request.max_pages, MAX_CRAWL_PAGES),
            request.include_pdfs,
            min(request.max_pdfs, MAX_CRAWL_PDFS),
            request.same_domain_only,
            min(request.max_depth, MAX_CRAWL_DEPTH),
        ),
        daemon=True
    )
    t.start()

    return {
        "job_id": job_id,
        "status": "started"
    }


@app.get("/crawl/status/{job_id}")
def crawl_status(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)
    job = get_crawl_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found.")
    return job


@app.post("/crawl/control/{job_id}")
def crawl_control(
    job_id: str,
    request: CrawlControlRequest,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    action = request.action.strip()
    valid_actions = {"skip_current_page", "skip_current_document", "pause", "resume", "cancel"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    success = control_crawl_job(job_id, action)
    if not success:
        raise HTTPException(status_code=404, detail="Crawl job not found.")

    return {"success": True, "action": action}


@app.get("/crawl/jobs")
def list_crawl_jobs_endpoint(
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)
    return get_all_crawl_jobs()


@app.delete("/crawl/{job_id}")
def delete_crawl_job_endpoint(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)
    success = delete_crawl_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Crawl job not found.")
    return {"success": True}


@app.post("/admin/debug/search")
def admin_debug_search(
    request: DebugSearchRequest,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")

    try:
        return debug_search_chunks(query=query, top_k=request.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN INVITE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/invite-admin")
def invite_admin(
    payload: InviteAdminRequest,
    authorization: str | None = Header(default=None),
):
    current_user = ensure_admin_access(authorization)
    email = payload.email.strip().lower()
    role = (payload.role or "admin").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Only admin role can be invited from this route.",
        )

    profile = fetch_profile_by_email(email)

    if profile:
        if profile.get("role") == "admin":
            return {"message": "This user is already an admin.", "email": email}
        if profile.get("role") == "super_admin":
            return {"message": "This user is already a super admin.", "email": email}

        patch_profile_role(profile["profile_id"], "admin")

        try:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
                headers={**service_headers(), "Content-Type": "application/json"},
                json={
                    "action": "promote_existing_user_to_admin",
                    "target_email": email,
                    "performed_by": current_user.get("id"),
                },
                timeout=15,
            )
        except requests.RequestException:
            pass

        return {"message": "Existing user promoted to admin.", "email": email}

    try:
        existing_invite = requests.get(
            f"{SUPABASE_URL}/rest/v1/admin_invites",
            params={
                "email": f"eq.{email}",
                "status": "eq.pending",
                "select": "id,email",
                "limit": "1",
            },
            headers=service_headers(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase invites lookup failed: {exc}",
        ) from exc

    if existing_invite.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing invites: {describe_response(existing_invite)}",
        )
    if existing_invite.json():
        raise HTTPException(
            status_code=409,
            detail="A pending invite already exists for this email.",
        )

    try:
        invite_response = requests.post(
            f"{SUPABASE_URL}/auth/v1/invite",
            headers={**service_headers(), "Content-Type": "application/json"},
            json={
                "email": email,
                "data": {"role": "admin"},
                "redirect_to": f"{FRONTEND_URL}/set-password",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase invite request failed: {exc}",
        ) from exc

    if invite_response.status_code >= 400:
        detail = describe_response(invite_response)
        if "already been registered" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    "This email is already registered in Supabase Auth but no "
                    "profile row was found. Create/fix the profile row, then "
                    "promote the user."
                ),
            )
        raise HTTPException(status_code=invite_response.status_code, detail=detail)

    try:
        invite_record = requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_invites",
            headers={
                **service_headers(),
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json={
                "email": email,
                "role": "admin",
                "status": "pending",
                "invited_by": current_user.get("id"),
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase invite save failed: {exc}",
        ) from exc

    if invite_record.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=(
                "Invite email was sent, but saving the invite record failed: "
                f"{describe_response(invite_record)}"
            ),
        )

    try:
        activity_log = requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
            headers={**service_headers(), "Content-Type": "application/json"},
            json={
                "action": "invite_admin",
                "target_email": email,
                "performed_by": current_user.get("id"),
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase activity log request failed: {exc}",
        ) from exc

    if activity_log.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=(
                "Invite email was sent, but logging the action failed: "
                f"{describe_response(activity_log)}"
            ),
        )

    records = invite_record.json()
    return {
        "message": "Admin invite sent.",
        "invited_by": current_user.get("email"),
        "invite": records[0] if records else None,
    }


@app.get("/admin/management")
def get_admin_management(authorization: str | None = Header(default=None)):
    ensure_admin_access(authorization)
    return fetch_admin_management_data()


@app.patch("/admin/invites/{invite_id}/cancel")
def cancel_admin_invite(
    invite_id: str,
    authorization: str | None = Header(default=None),
):
    current_user = ensure_admin_access(authorization)

    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/admin_invites",
            params={"id": f"eq.{invite_id}"},
            headers={**service_headers(), "Content-Type": "application/json"},
            json={"status": "cancelled"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase invite cancel failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel invite: {describe_response(response)}",
        )

    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
            headers={**service_headers(), "Content-Type": "application/json"},
            json={
                "action": "cancel_admin_invite",
                "target_email": None,
                "performed_by": current_user.get("id"),
            },
            timeout=15,
        )
    except requests.RequestException:
        pass

    return {"message": "Invite cancelled."}


@app.patch("/admin/remove-admin")
def remove_admin(
    payload: RemoveAdminRequest,
    authorization: str | None = Header(default=None),
):
    current_user = ensure_admin_access(authorization)
    profile_id = payload.profile_id.strip()

    if not profile_id:
        raise HTTPException(status_code=400, detail="Profile id is required.")
    if profile_id == current_user.get("id"):
        raise HTTPException(
            status_code=400,
            detail="You cannot remove your own admin access.",
        )

    patch_profile_role(profile_id, "student")

    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
            headers={**service_headers(), "Content-Type": "application/json"},
            json={
                "action": "remove_admin_access",
                "target_email": None,
                "performed_by": current_user.get("id"),
            },
            timeout=15,
        )
    except requests.RequestException:
        pass

    return {"message": "Admin access removed."}


@app.post("/admin/complete-invite")
def complete_admin_invite(
    payload: CompleteAdminInviteRequest,
    authorization: str | None = Header(default=None),
):
    access_token = require_bearer_token(authorization)
    current_user = fetch_current_user(access_token)

    user_id = current_user.get("id")
    email = (current_user.get("email") or "").strip().lower()
    metadata = current_user.get("user_metadata") or {}

    if not user_id or not email:
        raise HTTPException(
            status_code=400,
            detail="Authenticated user is missing id or email.",
        )

    pending_invite = get_pending_admin_invite(email)
    if not pending_invite:
        raise HTTPException(
            status_code=403,
            detail="No pending admin invite found for this user.",
        )
    if pending_invite.get("role") != "admin":
        raise HTTPException(
            status_code=400,
            detail="Only admin invites can be completed here.",
        )

    full_name = (payload.full_name or metadata.get("full_name") or "").strip()
    upsert_admin_profile(user_id, email, full_name)

    if pending_invite:
        try:
            invite_update = requests.patch(
                f"{SUPABASE_URL}/rest/v1/admin_invites",
                params={"id": f"eq.{pending_invite['id']}"},
                headers={**service_headers(), "Content-Type": "application/json"},
                json={"status": "accepted"},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase invite update failed: {exc}",
            ) from exc

        if invite_update.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to mark invite accepted: {describe_response(invite_update)}",
            )

    return {"message": "Admin invite completed.", "email": email, "role": "admin"}


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT LIST / DOWNLOAD / DELETE
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/documents")
async def list_documents():
    try:
        results = collection.get(include=["metadatas"])
        vector_files = {
            metadata["filename"]
            for metadata in results.get("metadatas", [])
            if metadata and metadata.get("filename")
        }
        local_files = {
            path.name
            for path in UPLOAD_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        }
        filenames = sorted(vector_files | local_files)
        return JSONResponse(content={"documents": filenames})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/documents/{filename}/download")
async def download_document(filename: str):
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(
        path=file_path,
        filename=safe_name,
        content_disposition_type="inline",
    )


@app.delete("/documents/all")
async def delete_all_documents(
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    try:
        # Get all documents from ChromaDB with metadata to get filenames
        results = collection.get(include=["metadatas"])
        ids_to_delete = results.get("ids", [])
        metadatas = results.get("metadatas", [])
        deleted_count = 0

        # Collect all filenames to delete from local directory
        filenames_to_delete = set()
        for metadata in metadatas:
            if metadata and metadata.get("filename"):
                filenames_to_delete.add(metadata["filename"])

        # Delete all chunks from ChromaDB
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            deleted_count = len(ids_to_delete)

        # Delete all files from the uploads directory
        for file_path in UPLOAD_DIR.glob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

        return JSONResponse(
            content={
                "message": f"Successfully deleted all files",
                "deleted_count": deleted_count,
                "chunks_deleted": deleted_count,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)
    try:
        safe_name = Path(filename).name
        deleted_count = hard_delete_document(safe_name)
        local_path = UPLOAD_DIR / safe_name
        if local_path.exists():
            local_path.unlink()
        return JSONResponse(
            content={
                "message": f"Successfully deleted {safe_name}",
                "chunks_deleted": deleted_count,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/websites/delete")
def delete_website(
    request: WebsiteDeleteRequest,
    authorization: str | None = Header(default=None),
):
    ensure_admin_access(authorization)

    try:
        normalized_url = normalize_url(request.url)
        results = collection.get(
            where={
                "$and": [
                    {"filename": {"$eq": normalized_url}},
                    {"scope": {"$eq": "official"}},
                    {"document_type": {"$eq": "website"}},
                ]
            },
            include=[],
        )
        ids_to_delete = results.get("ids", [])
        deleted_count = 0
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            deleted_count = len(ids_to_delete)

        return JSONResponse(
            content={
                "message": f"Successfully deleted website: {normalized_url}",
                "url": normalized_url,
                "chunks_deleted": deleted_count,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.on_event("startup")
def startup_event():
    print("[EduBot Startup] Eagerly loading ML models...")
    try:
        from embeddings import get_embedding_model
        get_embedding_model()
    except Exception as e:
        print(f"[EduBot Startup] Warning: Failed to eager load embedding model: {e}")
        
    try:
        from reranker import _get_cross_encoder
        _get_cross_encoder()
    except Exception as e:
        print(f"[EduBot Startup] Warning: Failed to eager load cross-encoder model: {e}")

    # §7: BM25 index must be rebuilt on startup if ChromaDB collection has changed
    try:
        # NOTE: do not `from rag.bm25_index import _bm25_docs` here — that binds
        # the pre-load empty list, so the count reads 0 and every startup does a
        # full (multi-minute) rebuild. Read the state through the accessor.
        from rag.bm25_index import get_all_documents_and_metas, rebuild_bm25_index
        bm25_docs, _ = get_all_documents_and_metas()
        chroma_count = collection.count()
        bm25_count = len(bm25_docs)
        if chroma_count != bm25_count:
            print(f"[EduBot Startup] BM25 index stale (BM25={bm25_count}, ChromaDB={chroma_count}). Rebuilding...")
            rebuild_bm25_index()
        else:
            print(f"[EduBot Startup] BM25 index is fresh ({bm25_count} docs).")
    except Exception as e:
        print(f"[EduBot Startup] Warning: BM25 index check failed: {e}")
        try:
            from rag.bm25_index import rebuild_bm25_index
            rebuild_bm25_index()
        except Exception as e2:
            print(f"[EduBot Startup] Warning: BM25 rebuild also failed: {e2}")

    print("[EduBot Startup] ML models loading sequence finished.")

# Harmless reload trigger comment

