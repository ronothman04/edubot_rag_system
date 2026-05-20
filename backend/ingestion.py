"""
ingestion.py - EduBot Document Ingestion Pipeline

Simple RAG-friendly ingestion flow:
1. Load text from supported files.
2. Clean extracted text.
3. Split into stable overlapping word chunks.
4. Batch-embed chunks.
5. Store chunks in ChromaDB with consistent metadata.

Public function signatures are unchanged.
"""

from db import collection
from embeddings import get_embedding_model

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader,
    Docx2txtLoader,
    UnstructuredHTMLLoader,
)

from PIL import Image
import pytesseract

import pdfplumber
import pandas as pd
import json
import re
import os
import io
import uuid


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".html",
    ".htm",
    ".csv",
    ".md",
    ".markdown",
    ".json",
    ".xlsx",
    ".xls",
    ".sql",
    ".dump",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

# Word-based chunks work better for semantic retrieval than character chunks.
CHUNK_SIZE = 450
CHUNK_OVERLAP = 80
MIN_CHUNK_WORDS = 8


# =============================================================================
# CLEANING + CHUNKING
# =============================================================================

def clean_loaded_text(text: str) -> str:
    """Clean extracted text from any source."""
    if not text:
        return ""

    text = text.replace("\x00", " ")

    # Fix PDF line-break hyphenation: "impor-\ntant" -> "important"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Remove standalone page-number lines.
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

    # Normalize whitespace.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def chunk_text(
    text: str,
    max_length: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into overlapping word chunks.

    max_length and overlap are word counts.
    This keeps chunks stable, avoids broken character slices, and improves RAG.
    """
    text = clean_loaded_text(text)
    if not text:
        return []

    words = text.split()

    if len(words) < MIN_CHUNK_WORDS:
        return []

    chunks: list[str] = []
    start = 0
    step = max(max_length - overlap, 1)

    while start < len(words):
        end = min(start + max_length, len(words))
        chunk = " ".join(words[start:end]).strip()

        if len(chunk.split()) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)

        if end >= len(words):
            break

        start += step

    return chunks


# =============================================================================
# HELPERS
# =============================================================================

def safe_id_text(value: str) -> str:
    """Make a safe string for ChromaDB chunk IDs."""
    value = str(value or "unknown").replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_\-.]", "_", value)


def normalize_metadata_value(value, default="general"):
    """Chroma metadata values must be str, int, float, or bool."""
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _table_to_text(table: list[list]) -> str:
    """Convert extracted table rows into retrieval-friendly text."""
    if not table:
        return ""

    rows = [[str(cell or "").strip() for cell in row] for row in table]
    rows = [row for row in rows if any(row)]

    if not rows:
        return ""

    headers = rows[0]
    output: list[str] = []

    if any(headers):
        output.append(" | ".join(cell for cell in headers if cell))

    for row in rows[1:]:
        if headers and len(headers) == len(row):
            parts = [
                f"{header}: {value}"
                for header, value in zip(headers, row)
                if header and value
            ]
        else:
            parts = [cell for cell in row if cell]

        if parts:
            output.append(" | ".join(parts))

    return "\n".join(output)


def _dataframe_to_text(df: pd.DataFrame) -> str:
    """Convert CSV/XLSX rows into self-describing text."""
    if df.empty:
        return ""

    rows: list[str] = []

    for row_index, row in df.iterrows():
        parts = [
            f"{column}: {row[column]}"
            for column in df.columns
            if pd.notna(row[column]) and str(row[column]).strip()
        ]

        if parts:
            rows.append(f"Row {row_index + 1}: " + " | ".join(parts))

    return clean_loaded_text("\n".join(rows))


# =============================================================================
# FILE LOADERS
# =============================================================================

def load_pdf_bytes(file_bytes: bytes, filename: str) -> list[Document]:
    """Load PDF text and tables using pdfplumber."""
    documents: list[Document] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total_pages = len(pdf.pages)

        for page_index, page in enumerate(pdf.pages, start=1):
            page_parts: list[str] = []

            prose = clean_loaded_text(page.extract_text() or "")
            if prose:
                page_parts.append(prose)

            for table in page.extract_tables() or []:
                table_text = clean_loaded_text(_table_to_text(table))
                if table_text:
                    page_parts.append(table_text)

            combined = clean_loaded_text("\n\n".join(page_parts))
            if not combined:
                continue

            documents.append(
                Document(
                    page_content=combined,
                    metadata={
                        "filename": filename,
                        "page": page_index,
                        "total_pages": total_pages,
                        "file_type": "pdf",
                    },
                )
            )

    return documents


def load_image_bytes(file_bytes: bytes, filename: str) -> list[Document]:
    """Extract text from image bytes using Tesseract OCR."""
    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    text = clean_loaded_text(pytesseract.image_to_string(image))

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata={
                "filename": filename,
                "page": 1,
                "total_pages": 1,
                "file_type": "image_ocr",
            },
        )
    ]


def load_docx_file(file_path: str) -> list[Document]:
    documents = Docx2txtLoader(file_path).load()

    for index, doc in enumerate(documents, start=1):
        doc.page_content = clean_loaded_text(doc.page_content)
        doc.metadata["page"] = doc.metadata.get("page", index)
        doc.metadata["file_type"] = "docx"

    return [doc for doc in documents if doc.page_content]


def load_txt_file(file_path: str) -> list[Document]:
    documents = TextLoader(file_path, encoding="utf-8").load()

    for index, doc in enumerate(documents, start=1):
        doc.page_content = clean_loaded_text(doc.page_content)
        doc.metadata["page"] = doc.metadata.get("page", index)
        doc.metadata["file_type"] = "txt"

    return [doc for doc in documents if doc.page_content]


def load_html_file(file_path: str) -> list[Document]:
    documents = UnstructuredHTMLLoader(file_path).load()

    for index, doc in enumerate(documents, start=1):
        doc.page_content = clean_loaded_text(doc.page_content)
        doc.metadata["page"] = doc.metadata.get("page", index)
        doc.metadata["file_type"] = "html"

    return [doc for doc in documents if doc.page_content]


def load_csv_file(file_path: str) -> list[Document]:
    text = _dataframe_to_text(pd.read_csv(file_path))

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata={
                "source": file_path,
                "filename": os.path.basename(file_path),
                "page": 1,
                "total_pages": 1,
                "file_type": "csv",
            },
        )
    ]


def load_markdown_file(file_path: str) -> list[Document]:
    documents = TextLoader(file_path, encoding="utf-8").load()

    for index, doc in enumerate(documents, start=1):
        doc.page_content = clean_loaded_text(doc.page_content)
        doc.metadata["page"] = doc.metadata.get("page", index)
        doc.metadata["file_type"] = "markdown"

    return [doc for doc in documents if doc.page_content]


def load_json_file(file_path: str) -> list[Document]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    text = clean_loaded_text(json.dumps(data, indent=2, ensure_ascii=False))

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata={
                "source": file_path,
                "filename": os.path.basename(file_path),
                "page": 1,
                "total_pages": 1,
                "file_type": "json",
            },
        )
    ]


def load_xlsx_file(file_path: str) -> list[Document]:
    documents: list[Document] = []
    excel_file = pd.ExcelFile(file_path)
    total_sheets = len(excel_file.sheet_names)

    for sheet_index, sheet_name in enumerate(excel_file.sheet_names, start=1):
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        text = _dataframe_to_text(df)

        if not text:
            continue

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file_path,
                    "filename": os.path.basename(file_path),
                    "page": sheet_index,
                    "total_pages": total_sheets,
                    "file_type": "xlsx",
                    "sheet_name": sheet_name,
                },
            )
        )

    return documents


def load_db_dump_file(file_path: str) -> list[Document]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = clean_loaded_text(f.read())

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata={
                "source": file_path,
                "filename": os.path.basename(file_path),
                "page": 1,
                "total_pages": 1,
                "file_type": "db_dump",
            },
        )
    ]


# =============================================================================
# FILE ROUTING
# =============================================================================

def load_file_from_path(file_path: str) -> list[Document]:
    """Load a local file based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    if ext == ".pdf":
        with open(file_path, "rb") as f:
            docs = load_pdf_bytes(f.read(), filename)

    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        with open(file_path, "rb") as f:
            docs = load_image_bytes(f.read(), filename)

    elif ext == ".docx":
        docs = load_docx_file(file_path)

    elif ext == ".txt":
        docs = load_txt_file(file_path)

    elif ext in {".html", ".htm"}:
        docs = load_html_file(file_path)

    elif ext == ".csv":
        docs = load_csv_file(file_path)

    elif ext in {".md", ".markdown"}:
        docs = load_markdown_file(file_path)

    elif ext == ".json":
        docs = load_json_file(file_path)

    elif ext in {".xlsx", ".xls"}:
        docs = load_xlsx_file(file_path)

    elif ext in {".sql", ".dump"}:
        docs = load_db_dump_file(file_path)

    else:
        docs = []

    for index, doc in enumerate(docs, start=1):
        doc.metadata["filename"] = filename
        doc.metadata["file_type"] = doc.metadata.get("file_type", ext.replace(".", ""))
        doc.metadata["page"] = doc.metadata.get("page", index)

    return docs


def load_file_from_bytes(file_bytes: bytes, filename: str) -> list[Document]:
    """Load an uploaded file from raw bytes."""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    if ext == ".pdf":
        return load_pdf_bytes(file_bytes, filename)

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return load_image_bytes(file_bytes, filename)

    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{safe_id_text(filename)}")

    try:
        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        documents = load_file_from_path(temp_path)

        for doc in documents:
            doc.metadata["filename"] = filename

        return documents

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# =============================================================================
# INGESTION
# =============================================================================

def ingest_documents(
    documents: list[Document],
    filename: str,
    session_id: str = None,
    user_id: str = None,
    department: str = "general",
    document_type: str = "general",
    year: str = "general",
    scope: str = "official",
) -> dict:
    """Chunk, embed, and store documents in ChromaDB."""
    model = get_embedding_model()

    scope = "personal" if str(scope).lower() == "personal" else "official"
    is_personal = scope == "personal"

    uploaded_by = "user" if is_personal else "admin"
    final_session_id = session_id or ("personal" if is_personal else "admin")
    final_user_id = user_id or ("personal" if is_personal else "admin")

    department = str(department or "general")
    document_type = str(document_type or "general")
    year = str(year or "general")

    if not is_personal:
        try:
            collection.delete(
                where={
                    "$and": [
                        {"filename": {"$eq": filename}},
                        {"scope": {"$eq": "official"}},
                    ]
                }
            )
        except Exception:
            collection.delete(where={"filename": filename})

    safe_filename = safe_id_text(filename)
    safe_user_id = safe_id_text(final_user_id)
    safe_session_id = safe_id_text(final_session_id)

    all_chunks: list[str] = []
    all_metadatas: list[dict] = []
    all_ids: list[str] = []

    total_text_chars = 0
    total_source_pages = 0

    for doc in documents:
        text = clean_loaded_text(doc.page_content)

        if not text:
            continue

        total_source_pages += 1
        total_text_chars += len(text)

        chunks = chunk_text(text)

        for chunk in chunks:
            if len(chunk.split()) < MIN_CHUNK_WORDS:
                continue

            chunk_index = len(all_chunks)

            metadata = {
                **{
                    key: normalize_metadata_value(value)
                    for key, value in doc.metadata.items()
                },
                "filename": filename,
                "page": normalize_metadata_value(doc.metadata.get("page", 1), 1),
                "file_type": normalize_metadata_value(
                    doc.metadata.get("file_type", "unknown"),
                    "unknown",
                ),
                "chunk_index": chunk_index,
                "deleted": False,
                "status": "active",
                "scope": scope,
                "uploaded_by": uploaded_by,
                "user_id": final_user_id,
                "session_id": final_session_id,
                "department": department,
                "document_type": document_type,
                "year": year,
            }

            if is_personal:
                chunk_id = (
                    f"personal_{safe_user_id}_{safe_session_id}_"
                    f"{safe_filename}_chunk_{chunk_index}"
                )
            else:
                chunk_id = f"official_{safe_filename}_chunk_{chunk_index}"

            all_chunks.append(chunk)
            all_metadatas.append(metadata)
            all_ids.append(chunk_id)

    if not all_chunks:
        raise ValueError(f"No readable text found in '{filename}'")

    all_embeddings = model.encode(
        all_chunks,
        show_progress_bar=False,
        batch_size=64,
    ).tolist()

    collection.upsert(
        documents=all_chunks,
        embeddings=all_embeddings,
        metadatas=all_metadatas,
        ids=all_ids,
    )

    numeric_page_counts = [
        int(doc.metadata["total_pages"])
        for doc in documents
        if str(doc.metadata.get("total_pages", "")).isdigit()
    ]

    total_pages = max(numeric_page_counts) if numeric_page_counts else len(documents)
    file_type = os.path.splitext(filename)[1].replace(".", "").upper() or "UNKNOWN"

    return {
        "file": filename,
        "type": file_type,
        "scope": scope,
        "uploaded_by": uploaded_by,
        "department": department,
        "document_type": document_type,
        "year": year,
        "pages_processed": total_pages,
        "text_extracted_chars": total_text_chars,
        "chunks_created": len(all_chunks),
        "chunks_stored": len(all_chunks),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "status": "Ready for RAG search",
    }


# =============================================================================
# PUBLIC ENTRY POINTS
# =============================================================================

def ingest_file_bytes(
    file_bytes: bytes,
    filename: str,
    session_id: str = None,
    user_id: str = None,
    department: str = "general",
    document_type: str = "general",
    year: str = "general",
    scope: str = "official",
) -> dict:
    documents = load_file_from_bytes(file_bytes, filename)
    return ingest_documents(
        documents=documents,
        filename=filename,
        session_id=session_id,
        user_id=user_id,
        department=department,
        document_type=document_type,
        year=year,
        scope=scope,
    )


def ingest_file_path(
    file_path: str,
    session_id: str = None,
    user_id: str = None,
    department: str = "general",
    document_type: str = "general",
    year: str = "general",
    scope: str = "official",
) -> dict:
    filename = os.path.basename(file_path)
    documents = load_file_from_path(file_path)
    return ingest_documents(
        documents=documents,
        filename=filename,
        session_id=session_id,
        user_id=user_id,
        department=department,
        document_type=document_type,
        year=year,
        scope=scope,
    )


def ingest_folder(
    folder_path: str = "data",
    department: str = "general",
    document_type: str = "general",
    year: str = "general",
    scope: str = "official",
) -> list[dict]:
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    results: list[dict] = []

    for root, _dirs, files in os.walk(folder_path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            file_path = os.path.join(root, filename)

            try:
                result = ingest_file_path(
                    file_path,
                    session_id=None,
                    user_id=None,
                    department=department,
                    document_type=document_type,
                    year=year,
                    scope=scope,
                )
                results.append(result)

            except Exception as e:
                results.append(
                    {
                        "file": filename,
                        "status": "Failed",
                        "error": str(e),
                    }
                )

    return results


if __name__ == "__main__":
    ingest_folder("data")