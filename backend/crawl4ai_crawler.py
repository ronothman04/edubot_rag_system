from __future__ import annotations
import asyncio
import os
import time
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from langchain_core.documents import Document

# Content exclusion filter — single source of truth lives in crawler.py.
# Re-exported here so this backend shares one copy of the rules (no drift).
from crawler import (
    is_excluded_url,
    EXCLUDED_URL_PATH_PATTERNS,
    EXCLUDED_FILENAME_KEYWORDS,
    PRESERVE_PDF_KEYWORDS,
)

CRAWL4AI_IMPORT_ERROR: str | None = None
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    CRAWL4AI_AVAILABLE = True
except Exception as _crawl4ai_import_error:  # noqa: BLE001 - report any import-time failure
    # Capture the real reason so the fallback log isn't a black box. The most
    # common cause is the server running with an interpreter that doesn't have
    # crawl4ai installed (e.g. system python instead of backend/.venv).
    CRAWL4AI_IMPORT_ERROR = f"{type(_crawl4ai_import_error).__name__}: {_crawl4ai_import_error}"
    CRAWL4AI_AVAILABLE = False
    class AsyncWebCrawler:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class CrawlerRunConfig:
        def __init__(self, *args, **kwargs): pass
    class CacheMode:
        BYPASS = "bypass"
    class PruningContentFilter:
        def __init__(self, *args, **kwargs): pass
    class DefaultMarkdownGenerator:
        def __init__(self, *args, **kwargs): pass


SKIP_PATTERNS = [
    "gallery", "galleries", "photo", "photos", "photogallery", "photo-gallery", 
    "image-gallery", "media-gallery", "faculty-profile", "faculty-profiles", 
    "images", "banners", "slideshows", "galleries", "photo-albums", 
    "staff-profile", "staff-profiles", "employee-profile", "employee-profiles", 
    "alumni", "event-archive", "events-archive", "past-events", "old-events"
]

KEEP_PATTERNS = [
    "admission", "admissions", "notice", "notices", "academic", "academics", 
    "department", "departments", "exam", "examination", "result", "results", 
    "scholarship", "tender", "downloads", "news", "announcement", "circular", 
    "recruitment"
]

def should_skip_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    lower_check = (parsed.path + "?" + parsed.query).lower()
    
    # 1. Check keep patterns first - if matched, do not skip
    for pattern in KEEP_PATTERNS:
        if pattern in lower_check:
            return False
            
    # 2. Check skip patterns
    for pattern in SKIP_PATTERNS:
        if pattern in lower_check:
            return True
            
    return False


async def crawl_with_crawl4ai(
    start_url: str,
    max_pages: int = 50,
    delay_seconds: float = 1.5,
    include_pdfs: bool = True,
    max_pdfs: int = 200,
    same_domain_only: bool = True,
    crawl_documents: bool = True,
    max_depth: int = 3,
    job_id: str | None = None,
) -> list[Document]:
    """
    Crawls a website using Crawl4AI with support for recursion, internal links constraint,
    JS execution/rendering, markdown pruning content filter, and concurrent page processing.
    """
    if not CRAWL4AI_AVAILABLE:
        raise ImportError("Crawl4AI is not available in the environment.")

    # Local imports to avoid circular dependencies
    from ingestion import (
        normalize_url, get_base_domain, is_same_domain, is_allowed_crawl_url,
        is_pdf_url, is_document_url, build_pdf_link_document,
        increment_crawl_job, is_supported_document_response,
        safe_document_filename_from_url, extract_clean_text_from_website_html,
        extract_visible_links_text_from_html, detect_section_title, detect_toc,
        word_count, MIN_CHUNK_WORDS, readable_website_source_name,
        update_crawl_job, wait_if_paused, check_crawl_cancelled,
        should_skip_current_page, should_skip_current_document,
        safe_pdf_filename_from_url,
        load_pdf_bytes, load_file_from_path, UPLOAD_DIR, REQUEST_TIMEOUT_SECONDS,
        metadata_year_value, metadata_date_value, fetch_with_ssl_fallback,
    )
    from crawler import extract_links
    import requests

    start_url = normalize_url(start_url)
    base_domain = get_base_domain(start_url)
    parsed_start = urlparse(start_url)
    base_domain_url = f"{parsed_start.scheme}://{parsed_start.netloc}"

    visited: set[str] = set()
    queued: set[str] = {start_url}
    queue: list[tuple[str, int]] = [(start_url, 0)]

    documents: list[Document] = []
    failed_pages: list[dict] = []
    pdf_found_on_urls: dict[str, str] = {}

    total_links_extracted = 0
    pdfs_loaded = 0
    docs_downloaded = 0
    pdf_links_recorded: set[str] = set()

    # Crawl statistics
    urls_skipped = 0
    urls_queued = 1  # start_url is queued initially
    urls_processed = 0

    from ingestion import create_robust_session, CRAWLER_HEADERS
    session = create_robust_session(CRAWLER_HEADERS)

    # robots.txt check
    from urllib.robotparser import RobotFileParser
    rp = RobotFileParser()
    rp.set_url(urljoin(start_url, "/robots.txt"))
    robots_ready = False
    try:
        rp.read()
        robots_ready = True
    except Exception:
        pass

    # Setup Crawl4AI Markdown Generator with Pruning Content Filter
    prune_filter = PruningContentFilter(
        threshold=0.45,
        threshold_type="fixed",
        min_word_threshold=10
    )
    md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)

    config = CrawlerRunConfig(
        markdown_generator=md_generator,
        cache_mode=CacheMode.BYPASS,
        page_timeout=30000,
        wait_for_images=False,
    )

    print(f"INFO  Crawl started: {start_url}")

    if job_id:
        update_crawl_job(
            job_id,
            url=start_url,
            status="crawling",
            pages_found=1,
            current_stage="queued",
            last_crawl_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )

    # Concurrent crawling batch size
    batch_size = 5

    async with AsyncWebCrawler() as crawler:
        while queue and len(visited) < max_pages:
            # Checkpoint: before each batch
            if job_id:
                try:
                    wait_if_paused(job_id)
                    check_crawl_cancelled(job_id)
                except ValueError as e:
                    print(f"WARNING  Crawl cancelled: {e}")
                    break

            # Dequeue batch
            batch = []
            while queue and len(batch) < batch_size and (len(visited) + len(batch)) < max_pages:
                url_tuple = queue.pop(0)
                url = normalize_url(url_tuple[0])
                depth = url_tuple[1]
                queued.discard(url)

                if url in visited:
                    continue

                if not is_allowed_crawl_url(url):
                    continue

                excluded, matched_pattern = is_excluded_url(url)
                if excluded:
                    print(f"[Crawler] Skipped excluded URL: {url}")
                    print(f'Reason: Matched exclusion pattern "{matched_pattern}"')
                    continue

                if robots_ready and not rp.can_fetch(CRAWLER_HEADERS.get("User-Agent"), url):
                    print(f"WARNING  Page skipped: {url} (Blocked by robots.txt)")
                    if job_id:
                        increment_crawl_job(job_id, {"pages_skipped": 1})
                    continue

                # Documents/PDFs are terminal content (not traversal hops), so the
                # page-depth limit must NOT drop them — otherwise PDFs/documents
                # discovered on the deepest allowed pages are never downloaded or
                # indexed, causing missing content. HTML pages keep the depth limit.
                if depth > max_depth and not (is_document_url(url) or is_pdf_url(url)):
                    continue

                if same_domain_only and not is_same_domain(url, base_domain):
                    continue

                batch.append((url, depth))

            if not batch:
                continue

            html_batch = []
            doc_batch = []
            for url, depth in batch:
                is_pdf_or_doc = is_document_url(url) or is_pdf_url(url)
                if is_pdf_or_doc:
                    doc_batch.append((url, depth))
                else:
                    html_batch.append((url, depth))

            # 1. Process HTML Pages concurrently
            if html_batch:
                urls_to_crawl = [u for u, _ in html_batch]
                for url, _ in html_batch:
                    print(f"INFO  Page discovered: {url}")
                    if job_id:
                        update_crawl_job(
                            job_id,
                            current_url=url,
                            current_type="page",
                            current_stage="fetching",
                            status="crawling"
                        )
                
                results = await crawler.arun_many(urls_to_crawl, config=config)

                # arun_many() returns results in COMPLETION order, not input
                # order, so zipping with html_batch paired each page's title and
                # content with another page's URL (the source of mismatched
                # source_url/title metadata, e.g. "Computer Science Department"
                # stamped with the Education department URL). Pair every result
                # to the page it ACTUALLY fetched via result.url instead.
                depth_by_url = {normalize_url(u): d for u, d in html_batch}
                # Mark every attempted URL visited up front so a redirect-changed
                # result.url can never let the input URL be re-queued.
                for _u, _ in html_batch:
                    visited.add(normalize_url(_u))

                for result in results:
                    result_url = (
                        getattr(result, "url", "")
                        or getattr(result, "redirected_url", "")
                        or ""
                    )
                    url = normalize_url(result_url) if result_url else ""
                    if not url:
                        continue
                    depth = depth_by_url.get(
                        url,
                        depth_by_url.get(
                            normalize_url(getattr(result, "redirected_url", "") or ""),
                            0,
                        ),
                    )
                    visited.add(url)
                    urls_processed += 1
                    
                    if not result.success:
                        print(f"ERROR  Crawl failed: {url} - {result.error_message}")
                        failed_pages.append({"url": url, "error": result.error_message})
                        if job_id:
                            update_crawl_job(job_id, errors=f"Failed to crawl {url}: {result.error_message}")
                            increment_crawl_job(job_id, {"pages_failed": 1})
                        continue

                    if job_id:
                        try:
                            wait_if_paused(job_id)
                            check_crawl_cancelled(job_id)
                        except ValueError as e:
                            print(f"WARNING  Crawl cancelled: {e}")
                            break

                    print(f"INFO  Page crawled: {url}")
                    if job_id:
                        update_crawl_job(job_id, current_stage="extracting")

                    try:
                        markdown_content = ""
                        if result.markdown and hasattr(result.markdown, "fit_markdown") and result.markdown.fit_markdown:
                            markdown_content = result.markdown.fit_markdown
                        elif result.markdown and isinstance(result.markdown, dict) and "fit_markdown" in result.markdown:
                            markdown_content = result.markdown["fit_markdown"]
                        else:
                            markdown_content = getattr(result, "markdown_v2", result).fit_markdown if hasattr(getattr(result, "markdown_v2", result), "fit_markdown") else result.markdown

                        if not markdown_content:
                            markdown_content = result.markdown
                    except Exception as e:
                        print(f"WARNING  Markdown extraction issue on {url}: {e}")
                        markdown_content = ""

                    # Coerce to str so .strip()/word_count below never crash on a
                    # MarkdownGenerationResult or other non-string object. The HTML
                    # extraction fallback recovers real text when this is not usable.
                    if not isinstance(markdown_content, str):
                        markdown_content = str(markdown_content or "")

                    print(f"INFO  Markdown generated: {url}")

                    page_title = ""
                    soup = BeautifulSoup(result.html or "", "lxml")
                    if soup.title:
                        page_title = soup.title.get_text(" ", strip=True)
                    if not page_title:
                        page_title = readable_website_source_name(url, "")

                    page_links, document_links = extract_links(result.html or "", url, base_domain_url)

                    combined_text = markdown_content.strip() if markdown_content else ""
                    # Fallback to HTML extraction if Crawl4AI markdown is empty or too short
                    if not combined_text or word_count(combined_text) < MIN_CHUNK_WORDS:
                        extracted_html_text = extract_clean_text_from_website_html(result.html or "", url)
                        if extracted_html_text and word_count(extracted_html_text) >= MIN_CHUNK_WORDS:
                            combined_text = extracted_html_text

                    if combined_text and word_count(combined_text) >= MIN_CHUNK_WORDS:
                        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        
                        doc_year = metadata_year_value(url, page_title, combined_text[:3000])
                        if doc_year and doc_year != "general":
                            try:
                                doc_year = int(doc_year)
                            except ValueError:
                                doc_year = 2026
                        else:
                            doc_year = 2026

                        doc_date = metadata_date_value({"source_url": url}, combined_text[:1000])
                        if not doc_date or doc_date == "general":
                            doc_date = "2026-06-12"

                        documents.append(
                            Document(
                                page_content=combined_text,
                                metadata={
                                    "filename": page_title,
                                    "source_filename": page_title,
                                    "source_url": url,
                                    "url": url,
                                    "title": page_title,
                                    "domain": base_domain,
                                    "source_type": "website",
                                    "source_url": url,
                                    "crawl_timestamp": timestamp,
                                    "crawl_method": "crawl4ai",
                                    "document_year": doc_year,
                                    "document_date": doc_date,
                                    "found_on_url": "",
                                    "crawl_base_url": start_url,
                                    "page": 1,
                                    "total_pages": 0,
                                    "file_type": "website",
                                    "section_title": detect_section_title(combined_text),
                                    "is_toc": detect_toc(combined_text),
                                    "scope": "official",
                                    "status": "active",
                                    "deleted": False,
                                },
                            )
                        )
                        if job_id:
                            increment_crawl_job(
                                job_id,
                                {"pages_processed": 1},
                                current_stage="completed",
                            )

                    links_text = extract_visible_links_text_from_html(result.html or "", url, base_domain)
                    if links_text and word_count(links_text) >= MIN_CHUNK_WORDS:
                        total_links_extracted += links_text.count("- ")
                        links_title = readable_website_source_name(url, "Website Links")
                        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        
                        doc_year = metadata_year_value(url, links_title, links_text[:3000])
                        if doc_year and doc_year != "general":
                            try:
                                doc_year = int(doc_year)
                            except ValueError:
                                doc_year = 2026
                        else:
                            doc_year = 2026

                        doc_date = metadata_date_value({"source_url": url}, links_text[:1000])
                        if not doc_date or doc_date == "general":
                            doc_date = "2026-06-12"

                        documents.append(
                            Document(
                                page_content=links_text,
                                metadata={
                                    "filename": links_title,
                                    "source_filename": links_title,
                                    "source_url": url,
                                    "url": url,
                                    "title": links_title,
                                    "domain": base_domain,
                                    "source_type": "website_links",
                                    "crawl_timestamp": timestamp,
                                    "crawl_method": "crawl4ai",
                                    "document_year": doc_year,
                                    "document_date": doc_date,
                                    "crawl_base_url": start_url,
                                    "file_type": "website_links",
                                    "section_title": "Website Links",
                                    "scope": "official",
                                    "status": "active",
                                    "deleted": False,
                                },
                            )
                        )

                    for link in page_links:
                        if link not in visited and link not in queued:
                            if should_skip_url(link):
                                print(f"[SKIP URL] {link}")
                                urls_skipped += 1
                                continue
                            queue.append((link, depth + 1))
                            queued.add(link)
                            urls_queued += 1
                            if job_id:
                                increment_crawl_job(job_id, {"pages_found": 1})

                    for doc_info in document_links:
                        doc_url = doc_info["url"]
                        if include_pdfs and doc_url not in pdf_links_recorded:
                            pdf_links_recorded.add(doc_url)
                            pdf_found_on_urls[doc_url] = url

                            pdf_doc = build_pdf_link_document(
                                pdf_url=doc_url,
                                pdf_title=doc_info["label"],
                                found_on_url=url,
                                start_url=start_url,
                                pdf_index=len(pdf_links_recorded),
                            )
                            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            pdf_doc.metadata.update({
                                "url": doc_url,
                                "title": doc_info["label"],
                                "domain": base_domain,
                                "crawl_timestamp": timestamp,
                                "crawl_method": "crawl4ai",
                                "source_url": doc_url,
                                # Normalize to strict pdf type for freshness-aware ranking
                                "source_type": "pdf",
                                "file_type": "pdf",
                                # Best-effort placeholders; actual extraction happens in PDF ingestion
                                "document_year": pdf_doc.metadata.get("document_year") if pdf_doc.metadata.get("document_year") and pdf_doc.metadata.get("document_year") != "general" else 2026,
                                "document_date": pdf_doc.metadata.get("document_date") if pdf_doc.metadata.get("document_date") and pdf_doc.metadata.get("document_date") != "general" else "2026-06-12",
                            })
                            documents.append(pdf_doc)

                            if job_id:
                                is_pdf = is_pdf_url(doc_url)
                                increment_crawl_job(
                                    job_id,
                                    {"pdfs_found" if is_pdf else "documents_found": 1},
                                )

                            if (
                                include_pdfs
                                and doc_url not in visited
                                and doc_url not in queued
                                and pdfs_loaded < max_pdfs
                            ):
                                if should_skip_url(doc_url):
                                    print(f"[SKIP URL] {doc_url}")
                                    urls_skipped += 1
                                    continue
                                queue.append((doc_url, depth + 1))
                                queued.add(doc_url)
                                urls_queued += 1

            # 2. Process PDFs / Documents
            if doc_batch and crawl_documents:
                for doc_url, depth in doc_batch:
                    visited.add(doc_url)
                    urls_processed += 1

                    if pdfs_loaded >= max_pdfs:
                        print(f"WARNING  Page skipped: {doc_url} (PDF limit reached)")
                        if job_id:
                            increment_crawl_job(job_id, {"pages_skipped": 1})
                        continue

                    if job_id:
                        try:
                            wait_if_paused(job_id)
                            check_crawl_cancelled(job_id)
                        except ValueError as e:
                            print(f"WARNING  Crawl cancelled: {e}")
                            break

                    is_pdf_doc = is_pdf_url(doc_url)
                    if job_id:
                        update_crawl_job(
                            job_id,
                            current_url=doc_url,
                            current_type="pdf" if is_pdf_doc else "document",
                            current_stage="fetching"
                        )

                    print(f"INFO  Page discovered: {doc_url}")

                    try:
                        # Size-capped + SSL-fallback fetch (shared with the legacy
                        # crawler) so an oversized file cannot exhaust memory.
                        response = fetch_with_ssl_fallback(session, doc_url, timeout=REQUEST_TIMEOUT_SECONDS)
                        # requests follows redirects, so mark the final resolved URL
                        # visited too — prevents a redundant re-fetch if that URL is
                        # later discovered as a link on another page.
                        final_url = normalize_url(getattr(response, "url", "") or "")
                        if final_url and final_url != doc_url:
                            visited.add(final_url)
                        content_type = response.headers.get("content-type", "").lower()
                        last_modified = response.headers.get("last-modified") or response.headers.get("Last-Modified")
                        extra_meta = {}
                        if last_modified:
                            extra_meta["last_modified"] = last_modified

                        if response.status_code != 200:
                            # Dead links (404/410) are expected on real websites and are
                            # not crawl failures — skip them quietly instead of flooding
                            # the error panel. Reserve "failed" for fetch errors that may
                            # indicate a real problem (auth, server errors, rate limits).
                            is_dead_link = response.status_code in (404, 410)
                            if is_dead_link:
                                print(f"WARNING  Broken link skipped: {doc_url} (HTTP {response.status_code})")
                                if job_id:
                                    increment_crawl_job(job_id, {"pages_skipped": 1})
                            else:
                                print(f"ERROR  Crawl failed: {doc_url} (HTTP {response.status_code})")
                                failed_pages.append({"url": doc_url, "error": f"HTTP {response.status_code}"})
                                if job_id:
                                    update_crawl_job(job_id, errors=f"Failed to fetch {doc_url} (HTTP {response.status_code})")
                                    increment_crawl_job(job_id, {"pages_failed": 1})
                            continue

                        print(f"INFO  Page crawled: {doc_url}")
                        if job_id:
                            update_crawl_job(job_id, current_stage="extracting")

                        parsed_doc = urlparse(doc_url)
                        doc_ext = os.path.splitext(parsed_doc.path)[1].lower()
                        is_img_doc = doc_ext in {".png", ".jpg", ".jpeg", ".webp"}

                        is_pdf_response = "application/pdf" in content_type or is_pdf_doc
                        if not is_pdf_response and not is_supported_document_response(doc_url, content_type):
                            if not is_img_doc:
                                print(f"WARNING  Page skipped: {doc_url} (unsupported document response: {content_type})")
                                if job_id:
                                    increment_crawl_job(job_id, {"pages_skipped": 1})
                                continue

                        pdfs_loaded += 1
                        doc_filename = (
                            safe_pdf_filename_from_url(doc_url, pdfs_loaded)
                            if is_pdf_response
                            else (os.path.basename(parsed_doc.path) or f"notice_{pdfs_loaded}{doc_ext}") if is_img_doc else safe_document_filename_from_url(doc_url, content_type, pdfs_loaded)
                        )
                        local_path = UPLOAD_DIR / doc_filename

                        if not local_path.exists():
                            with open(local_path, "wb") as f:
                                f.write(response.content)
                            docs_downloaded += 1

                        if job_id:
                            update_crawl_job(job_id, current_stage="ingesting")

                        if not is_pdf_response:
                            pdf_docs = load_file_from_path(str(local_path), job_id=job_id, extra_metadata=extra_meta)
                        else:
                            pdf_docs = load_pdf_bytes(
                                file_bytes=response.content,
                                filename=doc_filename,
                                job_id=job_id,
                                extra_metadata=extra_meta
                            )

                        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        for pdf_doc in pdf_docs:
                            found_on_url = pdf_found_on_urls.get(doc_url, "")
                            if is_pdf_response:
                                file_type = "website_pdf"
                            elif is_img_doc:
                                file_type = "website_image"
                            else:
                                file_type = "website_document"
                            
                            doc_year = pdf_doc.metadata.get("document_year")
                            if doc_year and doc_year != "general":
                                try:
                                    doc_year = int(doc_year)
                                except ValueError:
                                    doc_year = 2026
                            else:
                                doc_year = 2026

                            doc_date = pdf_doc.metadata.get("document_date")
                            if not doc_date or doc_date == "general":
                                doc_date = "2026-06-12"

                            pdf_doc.metadata.update({
                                "filename": doc_filename,
                                "source_filename": doc_filename,
                                "source_url": doc_url,
                                "url": doc_url,
                                "title": doc_filename,
                                "domain": base_domain,
                                "source_type": file_type,
                                "crawl_timestamp": timestamp,
                                "crawl_method": "crawl4ai",
                                "found_on_url": found_on_url,
                                "source_pdf_filename": doc_filename if is_pdf_response else "",
                                "crawl_base_url": start_url,
                                "file_type": file_type,
                                "pdf_title": doc_filename if is_pdf_response else "",
                                "scope": "official",
                                "status": "active",
                                "deleted": False,
                                "document_year": doc_year,
                                "document_date": doc_date,
                                "section_title": pdf_doc.metadata.get(
                                    "section_title",
                                    detect_section_title(pdf_doc.page_content)
                                )
                            })

                        documents.extend(pdf_docs)
                        print(f"INFO  Page crawled: {doc_url} | file: {doc_filename} | items: {len(pdf_docs)}")

                        if job_id:
                            increment_crawl_job(
                                job_id,
                                {"pdfs_processed" if is_pdf_response else "documents_processed": 1},
                                current_stage="completed",
                            )

                    except Exception as e:
                        print(f"ERROR  Crawl failed: {doc_url} - {e}")
                        failed_pages.append({"url": doc_url, "error": str(e)})
                        if job_id:
                            update_crawl_job(job_id, errors=f"Document extraction failed on {doc_url}: {e}")
                            increment_crawl_job(job_id, {"pages_failed": 1})

            await asyncio.sleep(delay_seconds)

    if not documents:
        raise ValueError(
            f"No readable website content found via Crawl4AI. Visited {len(visited)} pages."
        )

    # Sanitize and ensure metadata
    total_docs = len(documents)
    for i, doc in enumerate(documents, start=1):
        doc.metadata.setdefault("page", i)
        doc.metadata.setdefault("total_pages", total_docs)
        doc.metadata.setdefault("source_filename", start_url)
        doc.metadata.setdefault("filename", start_url)
        doc.metadata.setdefault("source_url", "")
        doc.metadata.setdefault("url", doc.metadata.get("source_url", ""))
        doc.metadata.setdefault("title", doc.metadata.get("filename", start_url))
        doc.metadata.setdefault("domain", base_domain)
        doc.metadata.setdefault("source_type", "website")
        doc.metadata.setdefault("crawl_timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        doc.metadata.setdefault("crawl_method", "crawl4ai")
        doc.metadata.setdefault("scope", "official")
        doc.metadata.setdefault("deleted", False)

    print("\nCrawl Summary")
    print("-------------")
    print(f"URLs Processed: {urls_processed}")
    print(f"URLs Queued: {urls_queued}")
    print(f"URLs Skipped: {urls_skipped}")
    print(f"PDFs Found: {len(pdf_links_recorded)}")
    print(f"Documents Created: {len(documents)}")

    return documents
