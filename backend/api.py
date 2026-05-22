import os
from pathlib import Path
from typing import Literal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from db import collection
from ingestion import SUPPORTED_EXTENSIONS, ingest_file_bytes
from rag import ask


load_dotenv()
load_dotenv(".env")

app = FastAPI()

UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Try multiple possible ID column names for flexibility
PROFILE_ID_COLUMNS = ("id", "uuid")


# CORS for React
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],  # not "*"
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


def format_chat_history(history: str | list[ChatHistoryMessage] | None) -> str:
    if history is None:
        return ""

    if isinstance(history, str):
        return history

    return "\n".join(
        [
            f"User: {message.content}"
            if message.role == "user"
            else f"Assistant: {message.content}"
            for message in history
        ]
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
                params={
                    profile_id_column: f"eq.{user_id}",
                    "select": "role",
                },
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

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
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

        # Default scope is official in your corrected ingestion.py
        stats = ingest_file_bytes(
            file_bytes=file_bytes,
            filename=filename,
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
# ADMIN INVITE ENDPOINT
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

    # Only allow normal admin invitation from this route.
    # Do not allow creating super_admin from the UI.
    if role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Only admin role can be invited from this route.",
        )

    # 1. Check if this email already exists in profiles.
    # If yes, promote the existing user instead of sending invite.
    try:
        existing_profile = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={
                "email": f"eq.{email}",
                "select": "id,email,role",
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

    if existing_profile.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {describe_response(existing_profile)}",
        )

    existing_profile_rows = existing_profile.json()

    if existing_profile_rows:
        profile = existing_profile_rows[0]

        if profile.get("role") == "admin":
            return {
                "message": "This user is already an admin.",
                "email": email,
            }

        if profile.get("role") == "super_admin":
            return {
                "message": "This user is already a super admin.",
                "email": email,
            }

        try:
            promote_response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={
                    "id": f"eq.{profile['id']}",
                },
                headers={
                    **service_headers(),
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                json={
                    "role": "admin",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase promote request failed: {exc}",
            ) from exc

        if promote_response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to promote existing user: {describe_response(promote_response)}",
            )

        try:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
                headers={
                    **service_headers(),
                    "Content-Type": "application/json",
                },
                json={
                    "action": "promote_existing_user_to_admin",
                    "target_email": email,
                    "performed_by": current_user.get("id"),
                },
                timeout=15,
            )
        except requests.RequestException:
            pass

        return {
            "message": "Existing user promoted to admin.",
            "email": email,
        }

    # 2. If the email does not exist in profiles, check duplicate pending invite.
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

    # 3. Send invite email for a brand-new user.
    try:
        invite_response = requests.post(
            f"{SUPABASE_URL}/auth/v1/invite",
            headers={
                **service_headers(),
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "data": {
                    "role": "admin",
                },
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

        raise HTTPException(
            status_code=invite_response.status_code,
            detail=detail,
        )

    # 4. Save invite record.
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

    # 5. Save activity log.
    try:
        activity_log = requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_activity_logs",
            headers={
                **service_headers(),
                "Content-Type": "application/json",
            },
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


@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    try:
        safe_name = Path(filename).name

        collection.delete(where={"filename": safe_name})

        local_path = UPLOAD_DIR / safe_name

        if local_path.exists():
            local_path.unlink()

        return JSONResponse(
            content={
                "message": f"Successfully deleted {safe_name}",
            }
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
