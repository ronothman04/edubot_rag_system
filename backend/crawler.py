from __future__ import annotations
import io
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

try:
    import pdfplumber
except Exception:
    pdfplumber = None


HEADERS = {
    "User-Agent": "Mozilla/5.0 (EduBot Crawler; College Knowledge Assistant)",
}

BLOCKED_EXTENSIONS = (
    ".css", ".js", ".svg",
    ".mp4", ".mp3",
    ".zip", ".rar", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff",
)

DOCUMENT_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx",
)


def normalize_url(url: str, keep_query: bool = False) -> str:
    parsed = urlparse(str(url or "").strip())

    if keep_query:
        clean = parsed._replace(fragment="")
    else:
        clean = parsed._replace(fragment="", query="")

    return clean.geturl().rstrip("/")


def get_domain(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def same_domain(url: str, base_domain: str) -> bool:
    parsed = urlparse(normalize_url(url))
    base = urlparse(base_domain)
    return parsed.scheme in {"http", "https"} and parsed.netloc == base.netloc


def is_allowed_url(url: str) -> bool:
    lower = str(url or "").lower().strip()

    if not lower:
        return False

    if lower.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False

    if any(lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
        return False

    return lower.startswith(("http://", "https://"))


def looks_like_document_url(url: str) -> bool:
    lower = str(url or "").lower().strip()
    parsed = urlparse(lower)
    path = parsed.path

    if any(path.endswith(ext) for ext in DOCUMENT_EXTENSIONS):
        return True

    if any(ext in lower for ext in DOCUMENT_EXTENSIONS):
        return True

    document_markers = (
        "download.php",
        "file=",
        "doc=",
        "pdf=",
        "attachment",
        "uploads",
        "resources",
    )
    if any(marker in lower for marker in document_markers):
        return True

    return False


# =============================================================================
# CONTENT EXCLUSION FILTER (student-facing scope)
# =============================================================================
# EduBot should index only student-facing content. The lists below are the
# single source of truth for the exclusion filter; crawl4ai_crawler.py imports
# is_excluded_url from this module so both crawler backends share one copy.
#
# Matching rules (see is_excluded_url):
#   - URL path patterns match on path *segments*, not word substrings, so
#     "/research/" is excluded but "/admission-research-guide.pdf" is not.
#   - Filename keywords apply only to document/PDF URLs and match whole words
#     or hyphenated compounds, so "research-journal.pdf" is excluded but
#     "admission-brochure.pdf" is not.
#   - PRESERVE_PDF_KEYWORDS always win for document/PDF URLs, so admission
#     brochures, prospectus, fee structures, syllabi, notices, etc. are never
#     dropped even when their name is otherwise ambiguous.
EXCLUDED_URL_PATH_PATTERNS = [
    "/research/", "/journals/", "/journal/", "/publication/", "/publications/",
    "/peerreview/", "/peer-reviewed/", "/conference/", "/proceedings/", "/magazine/",
    "/magazines/", "/newsletter/", "/newsletters/", "/archive/", "/archives/",
    "/repository/", "/resources/mdl/research/", "PeerReviewedResearchJournal",
]

# Whole-word (or hyphenated-compound) filename keywords. Plural variants are
# included so e.g. "journals.pdf" is caught alongside "journal.pdf".
EXCLUDED_FILENAME_KEYWORDS = [
    "research", "journal", "journals", "publication", "publications",
    "proceedings", "magazine", "magazines", "newsletter", "newsletters",
    "archive", "archives", "peerreview", "peer-reviewed",
]

# Student-facing document types that must never be skipped, even if their name
# also contains an excluded keyword (e.g. "admission-research-guide.pdf").
PRESERVE_PDF_KEYWORDS = [
    "prospectus", "brochure", "handbook", "syllabus", "syllabi",
    "timetable", "time-table", "fee", "fees", "regulation", "regulations",
    "academic", "examination", "exam", "form", "forms",
    "notice", "notices", "circular", "circulars", "admission", "admissions",
]

_FILENAME_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _filename_stem_and_tokens(url: str) -> tuple[str, set[str]]:
    """Return (lowercased filename stem, whole-word token set) for a URL.

    Query values are folded in so document URLs of the form "?file=research.pdf"
    are still tokenised correctly.
    """
    parsed = urlparse(str(url or "").lower())
    basename = os.path.basename(parsed.path)
    stem = os.path.splitext(basename)[0]
    query_text = parsed.query.replace("=", " ").replace("&", " ")
    tokens = {t for t in _FILENAME_TOKEN_RE.split(f"{stem} {query_text}") if t}
    return stem, tokens


def is_excluded_url(url: str) -> tuple[bool, str | None]:
    """Decide whether a URL is out of scope for EduBot's student-facing index.

    Returns (excluded, matched_pattern). matched_pattern is the rule that fired
    (for logging); it is None when the URL is allowed. This is a read-only
    predicate with no side effects, safe to call before any download.
    """
    if not url:
        return False, None

    parsed = urlparse(str(url).lower())
    # Guarantee leading/trailing slashes so patterns match on segment boundaries
    # rather than substrings of a word: "/research" -> "/research/".
    norm_path = "/" + parsed.path.strip("/") + "/"

    is_document = looks_like_document_url(url)
    stem, tokens = _filename_stem_and_tokens(url)

    # 1. Preserve-list wins for documents/PDFs, even if the name is ambiguous.
    if is_document:
        for kw in PRESERVE_PDF_KEYWORDS:
            if "-" in kw:
                if kw in stem:
                    return False, None
            elif kw in tokens:
                return False, None

    # 2. URL path-segment exclusion (applies to pages and documents alike).
    for pattern in EXCLUDED_URL_PATH_PATTERNS:
        pl = pattern.lower()
        if "/" in pl:
            seg = "/" + pl.strip("/") + "/"
            if seg in norm_path:
                return True, pattern
        elif pl in norm_path:  # bare token, e.g. PeerReviewedResearchJournal
            return True, pattern

    # 3. Filename keyword exclusion (documents/PDFs only — these are "file name"
    #    rules, so they must not reject ordinary HTML pages).
    if is_document:
        for kw in EXCLUDED_FILENAME_KEYWORDS:
            if "-" in kw:
                if kw in stem:
                    return True, kw
            elif kw in tokens:
                return True, kw

    return False, None


def clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def dedupe_lines(text: str) -> str:
    output = []
    seen = set()

    for line in str(text or "").splitlines():
        cleaned = clean_line(line)
        if not cleaned:
            if output and output[-1]:
                output.append("")
            continue

        key = cleaned.lower()
        if key in seen:
            continue

        seen.add(key)
        output.append(cleaned)

    while output and not output[-1]:
        output.pop()

    return "\n".join(output)


def is_hidden_element(tag) -> bool:
    if not getattr(tag, "attrs", None):
        return False

    if tag.has_attr("hidden"):
        return True

    if str(tag.get("aria-hidden", "")).lower() == "true":
        return True

    style = str(tag.get("style", "")).replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True

    return False


def extract_all_visible_text(html: str, url: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "canvas"]):
        tag.decompose()

    for tag in soup.find_all(is_hidden_element):
        tag.decompose()

    lines = []
    content_tags = (
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "span", "div", "section", "article",
        "li", "ul", "ol",
        "table", "tr", "td", "th",
        "button",
        "a",
        "nav", "menu", "footer",
    )

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        lines.append(f"Page title: {title}")
    lines.append(f"Source page: {url}")

    for tag in soup.find_all(content_tags):
        text = clean_line(tag.get_text(" ", strip=True))
        if not text:
            continue

        if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            lines.append("")
            lines.append(text)
            continue

        if tag.name == "a":
            href = tag.get("href", "")
            href_abs = normalize_url(urljoin(url, href), keep_query=looks_like_document_url(href))
            if href_abs and is_allowed_url(href_abs):
                lines.append(f"- {text}: {href_abs}")
            else:
                lines.append(f"- {text}")
            continue

        if tag.name == "button":
            lines.append(f"Button: {text}")
            continue

        if tag.name == "li":
            lines.append(f"- {text}")
            continue

        lines.append(text)

    return dedupe_lines("\n".join(lines))


def nearest_section_heading(tag) -> str:
    heading_tags = ["h1", "h2", "h3", "h4", "h5", "h6"]

    for parent in [tag.parent, *list(tag.parents)]:
        if not parent or getattr(parent, "name", None) in {"html", "body"}:
            break

        heading = parent.find(heading_tags)
        if heading:
            text = clean_line(heading.get_text(" ", strip=True))
            if text:
                return text

        parent_text = clean_line(parent.get_text(" ", strip=True))
        if parent_text and len(parent_text.split()) <= 8:
            return parent_text

    previous_heading = tag.find_previous(heading_tags)
    if previous_heading:
        return clean_line(previous_heading.get_text(" ", strip=True))

    return "General"


def extract_structured_links_as_text(html: str, url: str, base_domain: str) -> tuple[str, int, int]:
    soup = BeautifulSoup(html or "", "lxml")
    grouped_links: dict[str, list[str]] = {}
    seen = set()
    link_count = 0
    document_count = 0

    for tag in soup.find_all("a", href=True):
        label = clean_line(tag.get_text(" ", strip=True))
        href_raw = urljoin(url, tag["href"])
        is_doc = looks_like_document_url(href_raw)
        href = normalize_url(href_raw, keep_query=is_doc)

        if not label:
            label = href.split("/")[-1] or href

        if not is_allowed_url(href):
            continue

        if not same_domain(href, base_domain):
            continue

        key = f"{label}|{href}"
        if key in seen:
            continue

        seen.add(key)
        link_count += 1
        section = nearest_section_heading(tag)
        suffix = " [DOCUMENT]" if is_doc else ""
        grouped_links.setdefault(section, []).append(f"- {label}{suffix}: {href}")

        if is_doc:
            document_count += 1

    if not grouped_links:
        return "", 0, 0

    lines = ["Website links found on this page:"]
    for section, links in grouped_links.items():
        lines.append(f"Section: {section}")
        lines.extend(links)

    return "\n".join(lines), link_count, document_count


def extract_page_text(html: str, url: str) -> str | None:
    text = trafilatura.extract(
        html,
        url=url,
        include_tables=True,
        include_links=False,
        include_comments=False,
        no_fallback=False,
    )

    if text and text.strip():
        return text.strip()

    return None


def extract_visible_links_as_text(html: str, url: str, base_domain: str) -> str:
    links_text, _link_count, _document_count = extract_structured_links_as_text(
        html, url, base_domain,
    )
    return links_text


def extract_links(html: str, url: str, base_domain: str) -> tuple[list[str], list[dict]]:
    soup = BeautifulSoup(html or "", "lxml")

    page_links = []
    document_links = []
    seen_pages = set()
    seen_docs = set()

    for tag in soup.find_all("a", href=True):
        raw_href = urljoin(url, tag["href"])
        is_doc = looks_like_document_url(raw_href)
        full_url = normalize_url(raw_href, keep_query=is_doc)

        if not is_allowed_url(full_url):
            continue

        if not same_domain(full_url, base_domain):
            continue

        label = tag.get_text(" ", strip=True) or full_url.split("/")[-1] or "Document"

        if is_doc:
            if full_url not in seen_docs:
                document_links.append({
                    "url": full_url,
                    "label": label,
                    "found_on": url,
                })
                seen_docs.add(full_url)
        else:
            if full_url not in seen_pages:
                page_links.append(full_url)
                seen_pages.add(full_url)

    return page_links, document_links


def extract_pdf_text(content: bytes) -> str:
    if not pdfplumber:
        return ""

    output = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = clean_line(page.extract_text() or "")
            if text:
                output.append(f"Page {index}\n{text}")

    return "\n\n".join(output)


def extract_document_text(content: bytes, content_type: str, url: str) -> str:
    lower_url = str(url or "").lower()
    lower_type = str(content_type or "").lower()

    if ".pdf" in lower_url or "application/pdf" in lower_type:
        return extract_pdf_text(content)

    if (
        "text/" in lower_type
        or lower_url.endswith((".txt", ".csv", ".md"))
        or "json" in lower_type
    ):
        for encoding in ("utf-8", "latin-1"):
            try:
                return content.decode(encoding, errors="ignore")
            except Exception:
                continue

    return ""


def fetch_document_record(doc: dict, start_url: str) -> dict:
    doc_url = doc.get("url", "")
    title = doc.get("label", "")
    found_on = doc.get("found_on", "")
    file_type = "pdf" if ".pdf" in doc_url.lower() or "pdf=" in doc_url.lower() else "document"
    source_type = "website_pdf" if file_type == "pdf" else "website_document"
    text = ""
    downloaded = False
    extracted_content = False

    try:
        response = requests.get(doc_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        downloaded = True
        extracted = extract_document_text(
            response.content,
            response.headers.get("content-type", ""),
            doc_url,
        )
        if extracted:
            extracted_content = True
            text = (
                "Document downloaded from official website.\n"
                f"Title: {title}\n"
                f"URL: {doc_url}\n"
                f"Found on page: {found_on}\n\n"
                f"{dedupe_lines(extracted)}"
            )
    except Exception as e:
        print(f"[crawler] Failed to download document {doc_url}: {e}")

    if not text:
        text = (
            "Document found on official website.\n"
            f"Title: {title}\n"
            f"URL: {doc_url}\n"
            f"Found on page: {found_on}"
        )

    return {
        "url": doc_url,
        "text": text,
        "type": "document" if extracted_content else "document_link",
        "source": "website",
        "source_type": source_type,
        "file_type": file_type,
        "source_url": doc_url,
        "found_on_url": found_on,
        "crawl_base_url": start_url,
        "found_on": found_on,
        "title": title,
        "downloaded": downloaded,
        "extracted_content": extracted_content,
        "scope": "official",
        "status": "active",
        "deleted": False,
    }


def crawl_website(
    start_url: str,
    max_pages: int = 500,
    max_documents: int = 300,
    crawl_documents: bool = True,
    delay: float = 0.5,
) -> list[dict]:
    start_url = normalize_url(start_url)
    parsed = urlparse(start_url)

    if not parsed.scheme.startswith("http") or not parsed.netloc:
        raise ValueError("Invalid website URL.")

    base_domain = get_domain(start_url)

    page_queue: list[str] = [start_url]
    queued_pages: set[str] = {start_url}
    visited_pages: set[str] = set()

    discovered_documents: dict[str, dict] = {}

    results: list[dict] = []

    print(f"[crawler] Starting crawl: {start_url}")
    print(f"[crawler] Base domain: {base_domain}")

    while page_queue and len(visited_pages) < max_pages:
        url = normalize_url(page_queue.pop(0))
        queued_pages.discard(url)

        if url in visited_pages:
            continue

        if not is_allowed_url(url):
            continue

        excluded, matched_pattern = is_excluded_url(url)
        if excluded:
            print(f"[Crawler] Skipped excluded URL: {url}")
            print(f'Reason: Matched exclusion pattern "{matched_pattern}"')
            continue

        if not same_domain(url, base_domain):
            continue

        visited_pages.add(url)

        print(f"[crawler] Page ({len(visited_pages)}/{max_pages}): {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"[crawler] Failed to fetch page {url}: {e}")
            continue

        content_type = resp.headers.get("content-type", "").lower()

        if "text/html" not in content_type:
            continue

        main_text = extract_page_text(resp.text, url)
        visible_text = extract_all_visible_text(resp.text, url)
        links_text, link_count, document_link_count = extract_structured_links_as_text(
            resp.text, url, base_domain,
        )

        print(
            "[crawler] Extracted:",
            f"url={url}",
            f"main_text_len={len(main_text or '')}",
            f"visible_text_len={len(visible_text or '')}",
            f"links={link_count}",
            f"document_links={document_link_count}",
        )

        combined_text_parts = []

        if main_text:
            combined_text_parts.append(main_text.strip())

        if visible_text:
            combined_text_parts.append(visible_text.strip())

        if links_text:
            combined_text_parts.append(links_text.strip())

        combined_text = dedupe_lines("\n\n".join(combined_text_parts))

        if combined_text and len(combined_text.strip()) > 100:
            results.append({
                "url": url,
                "text": combined_text.strip(),
                "type": "webpage",
                "source": "website",
                "source_type": "website_page",
                "file_type": "website",
                "source_url": url,
                "found_on_url": "",
                "crawl_base_url": start_url,
                "scope": "official",
                "status": "active",
                "deleted": False,
            })

        page_links, document_links = extract_links(resp.text, url, base_domain)

        for link in page_links:
            if link not in visited_pages and link not in queued_pages:
                page_queue.append(link)
                queued_pages.add(link)

        if crawl_documents:
            for doc in document_links:
                doc_url = doc["url"]

                if len(discovered_documents) >= max_documents:
                    continue

                if doc_url not in discovered_documents:
                    discovered_documents[doc_url] = doc

        time.sleep(delay)

    if crawl_documents:
        for doc_url, doc in discovered_documents.items():
            results.append(fetch_document_record(doc, start_url))

    print(f"[crawler] Done.")
    print(f"[crawler] HTML pages visited: {len(visited_pages)}")
    print(f"[crawler] Documents discovered: {len(discovered_documents)}")
    print(f"[crawler] Items collected: {len(results)}")

    return results
