"""
rag/text_utils.py
Pure text, regex, and cleaning utility functions for EduBot RAG.
Imports nothing from other rag/* modules.
"""

import re
from typing import Any


from functools import lru_cache


# Latin typographic ligatures, emitted as single code points by PDF text
# extraction (and occasionally OCR/HTML). Left in place they break keyword and
# BM25 matching — "diﬃcult"/"oﬃce" never match a user's "difficult"/"office".
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",  # ſt (long-s t)
    "ﬆ": "st",
}
_LIGATURE_RE = re.compile("|".join(map(re.escape, _LIGATURES)))


def normalize_ligatures(text: str) -> str:
    """Replace Latin typographic ligatures (e.g. "ﬁ", "ﬂ") with their ASCII
    letter equivalents so keyword/BM25 matching sees ordinary words."""
    if not text:
        return text
    return _LIGATURE_RE.sub(lambda m: _LIGATURES[m.group(0)], text)


@lru_cache(maxsize=4096)
def normalize_text(text: str) -> str:
    """Normalize general text by cleaning whitespace and replacing common typos."""
    text = normalize_ligatures(text or "").lower()
    text = re.sub(r"\bcommitee\b", "committee", text)
    text = re.sub(r"\bcommitte\b", "committee", text)
    text = re.sub(r"\bcomittee\b", "committee", text)
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9\s@._%₹/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_query_text(text: str) -> str:
    """Alias for normalize_text."""
    return normalize_text(text)


ABBREVIATION_MAP = {
    "VTC": "Vocational Education and Training Course",
    "MCA": "Master of Computer Applications",
    "BCA": "Bachelor of Computer Applications",
    "BBA": "Bachelor of Business Administration",
    "MBA": "Master of Business Administration",
    "BSc": "Bachelor of Science",
    "BA":  "Bachelor of Arts",
    "MA":  "Master of Arts",
    "MSc": "Master of Science",
    "BCom": "Bachelor of Commerce",
    "MCom": "Master of Commerce",
    "HOD": "Head of Department",
    "IQAC": "Internal Quality Assurance Cell",
    "NAAC": "National Assessment and Accreditation Council",
    "UGC": "University Grants Commission",
    "NEHU": "North Eastern Hill University",
}


@lru_cache(maxsize=512)
def normalize_query(query: str) -> str:
    """Normalize user search queries, expanding common abbreviations.

    Expansion is *additive*: the original acronym / code token is preserved and
    the expansion is appended, rather than substituted in place. Substituting it
    away (the previous behaviour) destroyed exact-match signal \u2014 e.g.
    "MCA-CC-6000" became "master of computer applications cc 6000" and "VTC"
    disappeared entirely, so BM25 could no longer match the literal code/acronym
    the user typed against codes like "VTC: 369.1". Keeping both terms gives the
    dense path the expansion while the lexical path keeps the exact token, which
    is what exact code/acronym queries depend on (see project requirement: prefer
    exact acronym/code/title matches when available).
    """
    query = str(query or "")
    query = query.replace("'", "'").replace("\u201c", '"').replace("\u201d", '"')

    appended_expansions: list[str] = []
    for abbr, expansion in ABBREVIATION_MAP.items():
        if re.search(rf"\b{re.escape(abbr)}\b", query, flags=re.IGNORECASE):
            appended_expansions.append(expansion)
    if appended_expansions:
        query = query + " " + " ".join(appended_expansions)

    query = re.sub(r"\bstephan\s+hall\b", "Stephen Hall", query, flags=re.IGNORECASE)
    query = re.sub(r"\bdept\b", "department", query, flags=re.IGNORECASE)
    query = re.sub(r"\binfo\b", "information", query, flags=re.IGNORECASE)
    query = re.sub(r"\bexam\b", "examination", query, flags=re.IGNORECASE)
    query = re.sub(r"\bpg\b", "postgraduate", query, flags=re.IGNORECASE)
    query = re.sub(r"\bug\b", "undergraduate", query, flags=re.IGNORECASE)
    return normalize_text(query)


def clean_text(text: str) -> str:
    """Clean consecutive newlines and extra spaces from text."""
    text = text or ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def content_without_context_header(document: str) -> str:
    """
    Strip the context-prefix lines prepended by ingest_documents():
      Document: … | Page: … | Section: …
      Source URL: …
    and the [Source N | File: … | Page: … | Chunk: …] header from build_context().
    """
    text = document or ""
    lines = text.splitlines()
    while lines and re.match(
        r"^\s*(document|source\s+url|page|section|file|chunk)\s*[:|]",
        lines[0],
        flags=re.IGNORECASE,
    ):
        lines.pop(0)
    # Also strip the [Source N | ...] bracket header added in build_context
    while lines and re.match(r"^\s*\[Source\s+\d+\s*\|", lines[0], flags=re.IGNORECASE):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip() or text


def filename_title_hint(filename: str) -> str:
    """Turn a stored filename into a human-readable title hint.

    e.g. "doc_About.pdf" -> "doc About", "EL.pdf" -> "EL". Used so that
    lexical/rerank scoring can match query terms against the document name.
    """
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", str(filename or "").strip())
    stem = stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", stem).strip()


def rerank_text(document: str, meta: dict | None) -> str:
    """Augment a chunk body with its section title + filename for scoring.

    The discriminating signal for many queries (e.g. the heading "Profile of the
    College") lives only in the dense embedding and in `section_title` metadata —
    NOT in the raw chunk body that BM25, keyword_score, and the cross-encoder
    reranker operate on. Prepending it here (sourced entirely from existing
    metadata) lets those stages see the title without any re-ingestion.
    """
    body = content_without_context_header(document or "")
    meta = meta or {}
    section = str(meta.get("section_title") or meta.get("section") or "").strip()
    filename = str(meta.get("filename") or "").strip()

    prefix_parts: list[str] = []
    if section and section.lower() not in ("general", "unknown"):
        prefix_parts.append(section)
    stem = filename_title_hint(filename)
    if stem:
        prefix_parts.append(stem)

    if not prefix_parts:
        return body
    return f"{' — '.join(prefix_parts)}\n{body}"


# Leading conversational openers stripped from the *embedding* query so a verbose
# natural-language question ("Can you give a brief description of …") distills to
# its salient phrase ("… profile of the college"), which embeds far more sharply.
_QUERY_FILLER_LEADS = [
    r"can you(\s+please)?",
    r"could you(\s+please)?",
    r"would you(\s+please)?",
    r"will you(\s+please)?",
    r"please",
    r"kindly",
    r"i\s+(?:would\s+like|want|need|wish)\s+to\s+know(?:\s+about)?",
    r"i\s+(?:would\s+like|want|need)",
    r"let\s+me\s+know(?:\s+about)?",
    r"do\s+you\s+know(?:\s+about)?",
    r"may\s+i\s+know(?:\s+about)?",
    r"tell\s+me(?:\s+something)?(?:\s+about)?",
    r"give\s+(?:me|us)?(?:\s+a|\s+an|\s+the)?",
    r"show\s+me(?:\s+the)?",
    r"provide(?:\s+me)?(?:\s+with)?(?:\s+a|\s+an|\s+the)?",
    r"share(?:\s+with\s+me)?(?:\s+a|\s+an|\s+the)?",
]

# Filler descriptors removed anywhere (e.g. "a brief description of", "short profile").
_QUERY_FILLER_PHRASE = re.compile(
    r"\b(?:a|an|the)?\s*(?:brief|short|quick|small|little|general|detailed)\s+"
    r"(?:description|profile|overview|summary|idea|note|account|details?|information|info)"
    r"(?:\s+(?:of|about|on|regarding))?\b",
    flags=re.IGNORECASE,
)
_QUERY_FILLER_LEADS_RE = re.compile(
    r"^\s*(?:" + "|".join(_QUERY_FILLER_LEADS) + r")\b\s*", flags=re.IGNORECASE
)


def distill_embedding_query(query: str) -> str:
    """Strip conversational filler to produce a tight query for dense retrieval.

    Used ONLY for the embedding/vector path — the keyword/BM25 path keeps its
    expansion. Falls back to the original text if distillation would leave too
    little signal, so it can never make a query worse than the input.
    """
    text = str(query or "").strip()
    if not text:
        return text

    distilled = re.sub(r"\s*/\s*", " ", text)  # normalise "description / profile"
    # Alternately remove descriptor filler and peel leading conversational openers
    # until stable — each removal can expose the next (e.g. "can you" then "give").
    for _ in range(5):
        before = distilled
        distilled = _QUERY_FILLER_PHRASE.sub(" ", distilled)
        distilled = re.sub(r"^[\s/,:;.\-]+", "", distilled)
        distilled = _QUERY_FILLER_LEADS_RE.sub("", distilled)
        distilled = re.sub(r"\s+", " ", distilled).strip()
        if distilled == before:
            break
    distilled = re.sub(r"\s+", " ", distilled).strip(" ?.!,;:")

    # Guard: keep the original if distillation stripped too much.
    if len(distilled.split()) < 2:
        return text
    return distilled


@lru_cache(maxsize=1024)
def _important_words_cached(text: str) -> tuple[str, ...]:
    stopwords = {
        "what", "which", "who", "where", "when", "why", "how", "are", "is",
        "was", "were", "the", "a", "an", "of", "to", "in", "on", "for",
        "and", "or", "there", "available", "list", "show", "tell", "me",
        "about", "know", "like", "would", "i", "please", "give", "details",
        "detail", "all", "can", "could", "should", "does", "do", "did", "college",
        "you", "your", "we", "us",
    }
    words = re.findall(r"\w+|[\w.-]+@[\w.-]+", normalize_text(text))
    return tuple(w for w in words if len(w) > 2 and w not in stopwords)


def important_words(text: str) -> list[str]:
    """Extract important words from text, filtering out common stopwords."""
    return list(_important_words_cached(text))


def to_plain_embedding_list(embedding: Any) -> list:
    """Ensure embedding is a list representation (convert numpy array if necessary)."""
    if hasattr(embedding, "tolist"):
        return embedding.tolist()
    return embedding


def answer_has_empty_table(answer: str) -> bool:
    """Check if the answer contains a markdown table structure with no data rows."""
    if not answer:
        return False
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if not table_lines:
        return False
    sep_index = None
    for idx, line in enumerate(table_lines):
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", line):
            sep_index = idx
            break
    if sep_index is None:
        return False
    data_rows = table_lines[sep_index + 1:]
    if not data_rows:
        return True
    meaningful = [r for r in data_rows if re.search(r"[a-zA-Z0-9]", r.replace("|", "").replace("-", "").strip())]
    return len(meaningful) == 0


def fix_ocr_casing(text: str) -> str:
    """Correct character casing anomalies introduced by OCR systems."""
    if not text:
        return text
    replacements = {
        "CERTiFiCa TE": "Certificate", "CERTiFiCaTE": "Certificate", "CERTiFiCa": "Certifica",
        "CoURSES": "Courses", "CoURSE": "Course", "APPLICATIOns": "Applications",
        "PROGRAMMEs": "Programmes", "ORIENtED": "Oriented", "APPROvED": "Approved",
        "CoMMiTTee": "Committee", "CoMMiTTees": "Committees",
        "coMMiTTee": "committee", "coMMiTTees": "committees",
        "awarD": "Award", "aDMission": "Admission",
        "anTi - ragging": "Anti-Ragging", "anTi-ragging": "Anti-Ragging", "anti - ragging": "Anti-Ragging",
        "MoniToring": "Monitoring", "CanTeen": "Canteen",
        "DeparTMenT": "Department", "DeparTMenTs": "Departments",
        "PrinCipal": "Principal", "Vice PrinCipal": "Vice Principal",
        "CoorDinaTor": "Coordinator", "Co-orDinaTor": "Coordinator",
        "AssisTanT CoorDinaTor": "Assistant Coordinator",
        "ChairMan": "Chairman", "Vice ChairMan": "Vice Chairman",
        "MeMber": "Member", "MeMbers": "Members",
        "DesignaTion": "Designation", "NaMe": "Name",
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    text = re.sub(r"\banti\s*-\s*ragging\b", "Anti-Ragging", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[A-Za-z])[ \t]+-[ \t]+(?=[A-Za-z])", "-", text)
    return text


def remove_answer_metadata(answer: str) -> str:
    """Strip source metadata and inline citations; sources render separately in the UI."""
    if not answer:
        return answer
    lines = []
    for line in answer.splitlines():
        if re.match(r"^\s*(document|file|page|section|chunk|source|source url|url)\s*:", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^\s*\[Source\s+\d+\s*\|", line, flags=re.IGNORECASE):
            continue
        lines.append(line)
    answer = "\n".join(lines)
    answer = re.sub(r"(?i)\bDocument:\s*[^\n]+", "", answer)
    answer = re.sub(r"(?i)\bPage:\s*\d+", "", answer)
    answer = re.sub(r"(?i)\bSection:\s*[^\n]+", "", answer)
    answer = re.sub(r"(?i)\bSource URL:\s*\S+", "", answer)
    answer = re.sub(r"(?i)\bURL:\s*https?://\S+", "", answer)
    page_ref = r"pp?\.\s*\d+(?:\s*(?:[-–,]|and)\s*\d+)*"
    answer = re.sub(
        rf"(?i)\s*(?:according to|as (?:stated|noted|mentioned) in)\s+(?:the\s+)?[^,.;\n()]{{1,100}}\s*\({page_ref}\)\s*,?",
        "",
        answer,
    )
    answer = re.sub(
        rf"(?i)\s*\((?:[^()\n]{{1,120}},\s*)?{page_ref}\)",
        "",
        answer,
    )
    attribution = r"(?:according to|as (?:stated|noted|mentioned|listed|described) in)"
    answer = re.sub(
        rf"(?im)^\s*{attribution}\s+[^,.;\n]+,\s*",
        "",
        answer,
    )
    answer = re.sub(
        rf"(?i),?\s+{attribution}\s+[^,.;\n]+(?=[.;])",
        "",
        answer,
    )
    return answer


def postprocess_answer(
    answer: str,
    # Keep this default in sync with rag.config.NOT_FOUND_MESSAGE so the empty-table
    # fallback still matches main.py's exact-match routing to the smart not-found path.
    not_found_msg: str = (
        "I couldn't find this information in the available college resources. "
        "Please feel free to rephrase your question, or ask me about admissions, "
        "programmes, eligibility, departments, or campus facilities."
    )
) -> str:
    """Format and clean the generated answer, returning a fallback message if it has an empty table."""
    answer = remove_answer_metadata(answer)
    answer = clean_text(answer)
    answer = fix_ocr_casing(answer)
    if answer_has_empty_table(answer):
        return not_found_msg
    return answer.strip()


def is_deleted_metadata_value(value: Any) -> bool:
    """Check if the metadata 'deleted' field evaluates to True."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "deleted"}
    return False


def is_active_metadata_value(value: Any) -> bool:
    """Check if the metadata 'status' field evaluates to active (not deleted/inactive/archived)."""
    if value is None:
        return True
    return str(value).strip().lower() not in {"deleted", "inactive", "archived"}
