#!/usr/bin/env python3
"""
Regression tests for the ingestion-pipeline audit fixes.

Fix A (CRITICAL): a partial/limited recrawl must NOT delete chunks of pages it
                  did not revisit (ingestion.ingest_documents orphan pruning).
Fix B (CRITICAL): unknown publication dates stay honest ("general"/"") instead
                  of a fabricated current-year stamp
                  (scripts.backfill_document_dates helpers + ingest behaviour).
Fix C (HIGH):     oversized chunks are split so embeddings are not truncated
                  (ingestion.split_chunks_for_embedding).
Fix D (HIGH):     short chunks holding a contact/fee/%/role are preserved
                  (ingestion.is_valuable_short_chunk).
Fix E (MED sec):  crawl downloads are size-capped
                  (ingestion._read_response_with_size_cap).

Run:  .venv/bin/python -m pytest tests/test_ingestion_audit_fixes.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import ingestion


# ---------------------------------------------------------------------------
# Fix D — high-value short chunks survive the MIN_CHUNK_WORDS floor
# ---------------------------------------------------------------------------
class TestValuableShortChunks:
    @pytest.mark.parametrize("text", [
        "Phone: 0364-2211226",
        "Email: principal@anthonys.ac.in",
        "Tuition Fee: Rs. 25000",
        "Attendance: 75%",
        "Principal: Dr. John Doe",
        "Warden - Fr. Thomas",
        "₹ 12,500",
    ])
    def test_valuable_short_chunks_kept(self, text):
        assert ingestion.is_valuable_short_chunk(text) is True

    @pytest.mark.parametrize("text", [
        "see below",
        "click here",
        "next page",
        "",
    ])
    def test_plain_short_chunks_not_flagged(self, text):
        assert ingestion.is_valuable_short_chunk(text) is False

    def test_chunk_text_keeps_short_contact_record(self):
        # A standalone 2-word contact line would be dropped by MIN_CHUNK_WORDS=6
        # without the exemption.
        chunks = ingestion.chunk_text("Phone: 0364-2211226")
        assert any("0364-2211226" in c for c in chunks)

    def test_chunk_text_still_drops_noise(self):
        assert ingestion.chunk_text("ok then") == []  # 2 plain words, no value


# ---------------------------------------------------------------------------
# Fix C — oversized chunks split to fit the embedding token budget
# ---------------------------------------------------------------------------
class TestEmbeddingTokenBudget:
    def test_no_chunk_exceeds_budget_after_split(self):
        try:
            from embeddings import get_embedding_model
            model = get_embedding_model()
            tokenizer = model.tokenizer
            budget = int(getattr(model, "max_seq_length", 512) or 512)
        except Exception:
            pytest.skip("embedding model not available locally")

        # ~1200 tokens of dense list content (well over the 512 cap).
        big = "\n".join(f"- Faculty member number {i} teaches subject {i}" for i in range(220))
        before = len(tokenizer.encode(big, add_special_tokens=True))
        assert before > budget  # precondition: genuinely oversized

        out = ingestion.split_chunks_for_embedding([big])
        assert len(out) >= 2
        reserve = ingestion._EMBED_HEADER_TOKEN_RESERVE
        for piece in out:
            assert len(tokenizer.encode(piece, add_special_tokens=True)) <= budget - reserve + 1

    def test_small_chunks_unchanged(self):
        small = ["short clean passage of text", "another small passage here"]
        assert ingestion.split_chunks_for_embedding(small) == small

    def test_atomic_dense_blob_is_windowed_not_truncated(self):
        """M-4: a single dense unit with no separator near the 512 boundary must
        be covered by overlapping token windows (every piece under budget) — not
        hard-capped, which silently dropped the tail from the embedding."""
        try:
            from embeddings import get_embedding_model
            model = get_embedding_model()
            tokenizer = model.tokenizer
            budget = int(getattr(model, "max_seq_length", 512) or 512)
        except Exception:
            pytest.skip("embedding model not available locally")

        # One continuous line, no whitespace the separator splitter can use.
        blob = "".join(f"token{i}." for i in range(900))
        before = len(tokenizer.encode(blob, add_special_tokens=True))
        assert before > budget  # precondition: genuinely oversized and atomic

        out = ingestion.split_chunks_for_embedding([blob])
        assert len(out) >= 2  # was 1 (hard-cap drop) before the fix
        reserve = ingestion._EMBED_HEADER_TOKEN_RESERVE
        for piece in out:
            assert len(tokenizer.encode(piece, add_special_tokens=True)) <= budget - reserve + 1

        # Full coverage: the last part of the blob survives in some window
        # (the old hard cap dropped exactly this tail).
        assert "token899" in "".join(out)

    def test_long_header_capped_so_full_embedding_text_fits(self):
        """M-4 real root cause: for 28 chunks the header (long title/heading) was
        51-119 tokens (>48 reserve), so the full embedding text exceeded 512 and
        the BODY tail was truncated even though the body fit. build_embedding_text
        must cap the header so the full text stays within the model cap."""
        try:
            from embeddings import get_embedding_model
            model = get_embedding_model()
            tokenizer = model.tokenizer
            cap = int(getattr(model, "max_seq_length", 512) or 512)
        except Exception:
            pytest.skip("embedding model not available locally")

        reserve = ingestion._EMBED_HEADER_TOKEN_RESERVE
        meta = {
            "title": "Programme " * 60,   # pathologically long header fields
            "filename": "College_Handbook_2023_24.pdf",
            "heading": "Rules and Regulations " * 20,
        }
        # Header alone must be capped to the reserve (this is the fix's contract).
        header_only = ingestion.build_embedding_text("", meta)
        header_tokens = len(tokenizer.encode(header_only, add_special_tokens=False))
        assert header_tokens <= reserve, f"header {header_tokens} tok exceeds reserve {reserve}"

        # With a body already under the body budget, the full text fits the cap —
        # and the body tail is NOT dropped.
        body = " ".join(f"clause{i}" for i in range(150))  # comfortably < cap-reserve
        assert len(tokenizer.encode(body, add_special_tokens=True)) <= cap - reserve
        emb = ingestion.build_embedding_text(body, meta)
        total = len(tokenizer.encode(emb, add_special_tokens=True))
        assert total <= cap, f"embedding text {total} tok exceeds cap {cap}"
        assert "clause149" in emb  # tail preserved

    def test_short_header_unchanged(self):
        meta = {"title": "Fees", "filename": "prospectus.pdf", "heading": "Tuition"}
        emb = ingestion.build_embedding_text("the annual fee is 5000", meta)
        assert emb == (
            "Title: Fees\nSource: prospectus.pdf\nSection: Tuition\n\n"
            "the annual fee is 5000"
        )

    def test_token_window_split_covers_all_tokens(self):
        try:
            from embeddings import get_embedding_model
            tokenizer = get_embedding_model().tokenizer
        except Exception:
            pytest.skip("embedding model not available locally")
        text = " ".join(f"w{i}" for i in range(1500))
        pieces = ingestion._token_window_split(text, tokenizer, budget=200)
        assert len(pieces) >= 2
        for piece in pieces:
            assert len(tokenizer.encode(piece, add_special_tokens=False)) <= 200
        # first and last tokens both represented
        joined = " ".join(pieces)
        assert "w0" in joined and "w1499" in joined


# ---------------------------------------------------------------------------
# Fix E — download size cap
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, body: bytes, content_length=None):
        self._body = body
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    @property
    def content(self):
        return self._content

    def close(self):
        self.closed = True


class TestDownloadSizeCap:
    def test_rejects_oversized_by_content_length(self, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_DOWNLOAD_BYTES", 1000)
        resp = _FakeResp(b"x" * 10, content_length=5000)
        with pytest.raises(ValueError):
            ingestion._read_response_with_size_cap(resp, "http://x/y.pdf")
        assert resp.closed

    def test_rejects_oversized_by_streamed_bytes(self, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_DOWNLOAD_BYTES", 1000)
        resp = _FakeResp(b"x" * 5000)  # no Content-Length header
        with pytest.raises(ValueError):
            ingestion._read_response_with_size_cap(resp, "http://x/y.pdf")

    def test_accepts_within_cap(self, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_DOWNLOAD_BYTES", 1_000_000)
        resp = _FakeResp(b"hello world", content_length=11)
        out = ingestion._read_response_with_size_cap(resp, "http://x/y.pdf")
        assert out.content == b"hello world"


# ---------------------------------------------------------------------------
# Fix B — honest dates (backfill helpers)
# ---------------------------------------------------------------------------
class TestHonestDates:
    def test_old_doc_year_recovered_from_filename(self):
        from scripts.backfill_document_dates import _corrected
        meta = {"document_year": "2026", "document_date": "2026-06-12",
                "filename": "doc_AR-2019.pdf", "title": "Annual Report 2019"}
        changes = _corrected(meta)
        assert changes["document_year"] == 2019
        assert changes["document_date"] == ""  # fabricated date cleared

    def test_undated_doc_becomes_general(self):
        from scripts.backfill_document_dates import _corrected
        meta = {"document_year": "2026", "document_date": "2026-06-12",
                "filename": "untitled_notice.pdf", "title": "Notice"}
        changes = _corrected(meta)
        assert changes["document_year"] == "general"
        assert changes["document_date"] == ""

    def test_genuine_2026_preserved(self):
        from scripts.backfill_document_dates import _corrected
        meta = {"document_year": "2026", "document_date": "2026-06-12",
                "filename": "Prospectus2026.pdf", "title": "Prospectus 2026"}
        changes = _corrected(meta)
        # Year re-derives to 2026 (no change); only the fake date is cleared.
        assert changes is not None
        assert "document_year" not in changes
        assert changes["document_date"] == ""

    def test_real_year_not_touched(self):
        from scripts.backfill_document_dates import _corrected
        meta = {"document_year": "2018", "document_date": "2018-03-01",
                "filename": "x.pdf"}
        assert _corrected(meta) is None


# ---------------------------------------------------------------------------
# Fix A — partial recrawl must not delete unvisited pages' chunks
# ---------------------------------------------------------------------------
class _FakeCollection:
    """Minimal in-memory stand-in for the Chroma collection used by ingest."""
    def __init__(self):
        self.store: dict[str, dict] = {}  # id -> {"document","metadata"}

    def get(self, ids=None, where=None, include=None, limit=None, offset=None):
        items = list(self.store.items())
        if ids is not None:
            items = [(i, v) for i, v in items if i in set(ids)]
        if where:
            (field, cond), = where.items()
            want = cond["$eq"]
            items = [(i, v) for i, v in items if v["metadata"].get(field) == want]
        return {
            "ids": [i for i, _ in items],
            "documents": [v["document"] for _, v in items],
            "metadatas": [v["metadata"] for _, v in items],
        }

    def upsert(self, documents, embeddings, metadatas, ids):
        for d, m, i in zip(documents, metadatas, ids):
            self.store[i] = {"document": d, "metadata": m}

    def delete(self, ids):
        for i in ids:
            self.store.pop(i, None)

    def count(self):
        return len(self.store)


def _mk_doc(url, text):
    from langchain_core.documents import Document
    return Document(page_content=text, metadata={
        "filename": url, "source_filename": url, "source_url": url,
        "title": url, "page": 1, "total_pages": 1,
        "file_type": "website", "source_type": "website_page",
    })


@pytest.fixture
def fake_ingest(monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr(ingestion, "collection", fake)
    # add_chunks writes straight into the fake collection (bypass real db/embeddings).
    def fake_add_chunks(chunks, filename, embeddings, metadatas, ids, **kw):
        fake.upsert(documents=chunks, embeddings=embeddings, metadatas=metadatas, ids=ids)
        return len(chunks)
    monkeypatch.setattr(ingestion, "add_chunks", fake_add_chunks)
    monkeypatch.setattr(ingestion, "encode_texts", lambda texts, **kw: [[0.0] for _ in texts])
    monkeypatch.setattr(ingestion, "rebuild_bm25_index", lambda *a, **k: None)
    monkeypatch.setattr(ingestion, "split_chunks_for_embedding", lambda chunks: chunks)
    monkeypatch.setattr(ingestion, "should_cancel", lambda job_id: False)
    import rag.cache as cache
    monkeypatch.setattr(cache, "invalidate_on_ingestion", lambda: None)
    return fake


class TestPartialRecrawlNoDataLoss:
    SITE = "https://anthonys.ac.in"
    LONG = "This is a sufficiently long page body about the department and its programmes offered."

    def _crawl(self, urls):
        return [_mk_doc(u, f"{u} {self.LONG}") for u in urls]

    def test_full_then_partial_recrawl_preserves_unvisited(self, fake_ingest):
        pages = [f"{self.SITE}/p{i}" for i in range(5)]

        # 1) Full crawl: all 5 pages stored.
        ingestion.ingest_documents(self._crawl(pages), filename=self.SITE,
                                   crawl_base_url=self.SITE, scope="official")
        stored_urls = {v["metadata"]["source_url"] for v in fake_ingest.store.values()}
        assert stored_urls == set(pages)

        # 2) Partial recrawl: only 2 of the 5 pages returned this run.
        ingestion.ingest_documents(self._crawl(pages[:2]), filename=self.SITE,
                                   crawl_base_url=self.SITE, scope="official")
        stored_urls = {v["metadata"]["source_url"] for v in fake_ingest.store.values()}
        # CRITICAL: the 3 unvisited pages must still be present.
        assert stored_urls == set(pages), f"data loss: {set(pages) - stored_urls} were deleted"

    def test_revisited_page_with_removed_content_is_pruned(self, fake_ingest):
        pages = [f"{self.SITE}/p{i}" for i in range(3)]
        ingestion.ingest_documents(self._crawl(pages), filename=self.SITE,
                                   crawl_base_url=self.SITE, scope="official")

        # Recrawl p0 with changed content; p1/p2 not revisited.
        changed = [_mk_doc(pages[0], f"{pages[0]} Completely different replacement content about admissions here.")]
        ingestion.ingest_documents(changed, filename=self.SITE,
                                   crawl_base_url=self.SITE, scope="official")
        by_url = {}
        for v in fake_ingest.store.values():
            by_url.setdefault(v["metadata"]["source_url"], []).append(v["document"])
        # p1 and p2 preserved; p0 now reflects only the new content.
        assert set(by_url) == set(pages)
        assert all("different replacement content" in d for d in by_url[pages[0]])
        assert not any("department and its programmes" in d for d in by_url[pages[0]])


# ---------------------------------------------------------------------------
# Issue 1 — PDF table double-extraction
# ---------------------------------------------------------------------------
class _FakeTable:
    def __init__(self, bbox, rows):
        self.bbox = bbox
        self._rows = rows

    def extract(self):
        return self._rows


class _FakeFilteredPage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdfPage:
    """Mimics the pdfplumber surface used by _extract_prose_and_tables."""
    def __init__(self, full_text, filtered_text, tables):
        self._full = full_text
        self._filtered = filtered_text
        self._tables = tables

    def find_tables(self):
        return self._tables

    def extract_text(self):
        return self._full

    def filter(self, fn):
        return _FakeFilteredPage(self._filtered)


class TestPdfTableNoDoubleExtraction:
    def test_table_text_not_duplicated_in_prose(self):
        table = _FakeTable(bbox=(0, 100, 200, 160), rows=[["Fee", "Amount"], ["Tuition", "25000"]])
        # extract_text() (full) contains the flattened table cells; the filtered
        # page (table region removed) contains only the heading prose.
        page = _FakePdfPage(
            full_text="Fee Structure\nFee Amount Tuition 25000",
            filtered_text="Fee Structure",
            tables=[table],
        )
        prose, tables, n = ingestion._extract_prose_and_tables(page)
        assert n == 1
        assert prose == "Fee Structure"          # table cells NOT in prose
        assert "Tuition" not in prose             # no duplication
        assert any("Tuition" in t and "25000" in t for t in tables)  # table kept once

    def test_no_tables_returns_plain_prose(self):
        page = _FakePdfPage("Just prose here", "", tables=[])
        prose, tables, n = ingestion._extract_prose_and_tables(page)
        assert prose == "Just prose here"
        assert tables == [] and n == 0


# ---------------------------------------------------------------------------
# Issue 5 — parser memory-safety limits are configured
# ---------------------------------------------------------------------------
class TestParserSafetyLimits:
    def test_pdf_page_cap_defined(self):
        assert isinstance(ingestion.MAX_PDF_PAGES, int) and ingestion.MAX_PDF_PAGES > 0

    def test_pil_decompression_bomb_cap_set(self):
        try:
            from PIL import Image
        except Exception:
            pytest.skip("PIL not available")
        assert Image.MAX_IMAGE_PIXELS is not None and Image.MAX_IMAGE_PIXELS <= 200_000_000


# ---------------------------------------------------------------------------
# Issue 2 — programme-page URL recovery (title -> path, pool-gated)
# ---------------------------------------------------------------------------
class TestProgrammeUrlRecovery:
    def test_title_to_path(self):
        from scripts.repair_crawl_url_pairing import _prgm_path_from_title as p
        assert p("B.A. Economics | St. Anthony's College") == "ug/ba/prgm_ug_ba_economics"
        assert p("B.Sc. Botany | St. Anthony's College") == "ug/bsc/prgm_ug_bsc_botany"
        assert p("M.C.A. - Master of Computer Applications | x") == "pg/prgm_pg_mca"
        assert p("B.B.A. - Bachelor of Business Administration | x") == "ug/bba/prgm_ug_bba"
        assert p("B.A. Mass Communication & Video Production | x") == "ug/ba/prgm_ug_ba_mcvp"
        assert p("M.Sc. Biotechnology | x") == "pg/prgm_pg_msc_biotechnology"

    def test_pool_gated_fix_applied(self):
        from scripts.repair_crawl_url_pairing import _correct_url_for
        pool = {"dept": set(), "prgm": {"ug/ba/prgm_ug_ba_economics"}}
        meta = {
            "source_url": "https://anthonys.ac.in/pages/programmes/ug/ba/prgm_ug_ba_english.php",
            "filename": "B.A. Economics | St. Anthony's College",
        }
        old, new = _correct_url_for(meta, pool)
        assert new.endswith("/ug/ba/prgm_ug_ba_economics.php")

    def test_uncrawled_target_is_not_fabricated(self):
        from scripts.repair_crawl_url_pairing import _correct_url_for
        # B.Sc. Computer Science's real page was never crawled -> must be skipped.
        pool = {"dept": set(), "prgm": {"ug/bsc/prgm_ug_bsc_botany"}}
        meta = {
            "source_url": "https://anthonys.ac.in/pages/programmes/ug/bsc/prgm_ug_bsc_botany.php",
            "filename": "B.Sc. Computer Science | St. Anthony's College",
        }
        assert _correct_url_for(meta, pool) is None


# ---------------------------------------------------------------------------
# Issue 3 — dedup hash ignores volatile classification metadata
# ---------------------------------------------------------------------------
class TestDedupHashStability:
    SITE = "https://anthonys.ac.in/p1"
    BODY = "A sufficiently long page body about the programmes and admissions offered here."

    def test_metadata_only_change_does_not_reembed(self, fake_ingest, monkeypatch):
        calls = {"n": 0}

        def counting_encode(texts, **kw):
            calls["n"] += len(texts)
            return [[0.0] for _ in texts]

        monkeypatch.setattr(ingestion, "encode_texts", counting_encode)
        doc = [_mk_doc(self.SITE, self.BODY)]

        ingestion.ingest_documents(doc, filename=self.SITE, crawl_base_url=self.SITE,
                                   scope="official", department="general")
        ids_first = set(fake_ingest.store)
        embeds_first = calls["n"]
        assert embeds_first > 0 and ids_first

        calls["n"] = 0
        # Re-ingest identical content but with a different department/document_type.
        ingestion.ingest_documents(doc, filename=self.SITE, crawl_base_url=self.SITE,
                                   scope="official", department="science",
                                   document_type="report")
        ids_second = set(fake_ingest.store)

        assert ids_second == ids_first, "ids changed on metadata-only re-ingest (churn)"
        assert calls["n"] == 0, "content re-embedded despite unchanged text"

    def test_different_source_same_text_not_collapsed(self, fake_ingest):
        # Identical text from two different pages must remain two distinct chunks.
        ingestion.ingest_documents([_mk_doc(self.SITE + "/a", self.BODY)],
                                   filename=self.SITE, crawl_base_url=self.SITE, scope="official")
        ingestion.ingest_documents([_mk_doc(self.SITE + "/b", self.BODY)],
                                   filename=self.SITE, crawl_base_url=self.SITE, scope="official")
        urls = {v["metadata"]["source_url"] for v in fake_ingest.store.values()}
        assert {self.SITE + "/a", self.SITE + "/b"} <= urls


# ---------------------------------------------------------------------------
# Follow-up Task 2 — ZIP-expansion (decompression-bomb) protection
# ---------------------------------------------------------------------------
import zipfile


def _make_zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return str(path)


class TestZipArchiveSafety:
    def test_normal_archive_passes(self, tmp_path):
        z = _make_zip(tmp_path / "ok.docx", [("word/document.xml", b"<xml>hello</xml>")])
        ingestion.validate_zip_archive_safety(z)  # no raise

    def test_too_many_members(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_MEMBERS", 5)
        z = _make_zip(tmp_path / "many.xlsx", [(f"f{i}.xml", b"x") for i in range(10)])
        with pytest.raises(ValueError, match="member"):
            ingestion.validate_zip_archive_safety(z)

    def test_member_too_large(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_MEMBER_BYTES", 1000)
        z = _make_zip(tmp_path / "big.docx", [("word/document.xml", b"\0" * 5000)])
        with pytest.raises(ValueError, match="per-member"):
            ingestion.validate_zip_archive_safety(z)

    def test_total_size_exceeded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_MEMBER_BYTES", 10_000_000)
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_TOTAL_BYTES", 1500)
        z = _make_zip(tmp_path / "tot.xlsx",
                      [("a.xml", b"\0" * 1000), ("b.xml", b"\0" * 1000)])
        with pytest.raises(ValueError, match="total uncompressed"):
            ingestion.validate_zip_archive_safety(z)

    def test_compression_ratio_bomb(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingestion, "_ARCHIVE_RATIO_MIN_BYTES", 1000)
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_COMPRESSION_RATIO", 20.0)
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_MEMBER_BYTES", 50_000_000)
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_TOTAL_BYTES", 50_000_000)
        # 2MB of zeros compresses to a few KB -> very high ratio.
        z = _make_zip(tmp_path / "bomb.docx", [("word/document.xml", b"\0" * (2 * 1024 * 1024))])
        with pytest.raises(ValueError, match="compression ratio"):
            ingestion.validate_zip_archive_safety(z)

    def test_non_zip_file_ignored(self, tmp_path):
        p = tmp_path / "notzip.docx"
        p.write_bytes(b"this is not a zip archive")
        ingestion.validate_zip_archive_safety(str(p))  # no raise; loader handles it

    def test_docx_loader_rejects_bomb(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingestion, "MAX_ARCHIVE_MEMBER_BYTES", 1000)
        z = _make_zip(tmp_path / "x.docx", [("word/document.xml", b"\0" * 5000)])
        with pytest.raises(ValueError):
            ingestion.load_docx_file(z)


# ---------------------------------------------------------------------------
# Follow-up Task 3 — migration snapshot mechanism
# ---------------------------------------------------------------------------
class TestMigrationSnapshot:
    def test_create_and_list_snapshot(self, tmp_path, monkeypatch):
        import scripts.migration_snapshot as ms
        chroma = tmp_path / "chroma_db"
        chroma.mkdir()
        (chroma / "chroma.sqlite3").write_bytes(b"fake-db")
        data = tmp_path / "data"
        data.mkdir()
        (data / "bm25_index.pkl").write_bytes(b"fake-bm25")
        monkeypatch.setattr(ms, "CHROMA_DIR", str(chroma))
        monkeypatch.setattr(ms, "BM25_PATH", str(data / "bm25_index.pkl"))
        monkeypatch.setattr(ms, "BACKUPS_DIR", str(tmp_path / "backups"))

        dest = ms.create_snapshot("unit_test")
        assert dest and os.path.isdir(dest)
        assert os.path.isfile(os.path.join(dest, "chroma_db", "chroma.sqlite3"))
        assert os.path.isfile(os.path.join(dest, "data", "bm25_index.pkl"))
        assert any("unit_test" in s for s in ms.list_snapshots())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
