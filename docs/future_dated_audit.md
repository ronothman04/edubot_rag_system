# Future-dated document_year audit & policy (M-2)

_Last reviewed: 2026-07-01_

## Problem

`freshness.py` turns `document_year` into a recency boost. A `document_year` in
the **future** relative to the runtime year gets the maximum boost, so a
mis-dated chunk can outrank a genuinely current document within the same
relevance/authority/source band (amplified for "latest/current" queries).

At audit time 46 chunks across 16 document-entries carried `document_year` =
runtime_year+1. Root cause: ingestion sets `document_year = max(years found in
filename / date / first 3000 chars of body)`, which conflates the publication
year with three things that are **not** publication years:

| kind | example evidence |
|---|---|
| validity / expiry horizon | "Valid upto 30-05-2027", AICTE "Approval Process Handbook 2024-25 to 2027" |
| forward reference | "as we prepare for NAAC 2027", "Ph.D … Expected 2027" |
| stray table number | "… 192 **2027** 637 …" (a statistical value) |

Only genuine current-session documents ("PROSPECTUS 2026-2027", "Fees Structure
(2026-2027)") legitimately carry a future year.

## Policy (dynamic — no hardcoded years)

Single source of truth: `rag/future_dates.py`. All boundaries derive from the
runtime year, so the policy stays valid in future years with no code changes.

- **Keep** a future year only when the document is forward-looking (prospectus /
  admission / hostel_prospectus, or already audited "supported") **and** carries
  a current academic-session range whose lower bound is the current/near-current
  year.
- **Demote** validity/expiry horizons, forward references, and table numbers to
  the document's best non-future year (identifier/date year, else newest
  non-future body year, else `general`).
- The original value is preserved in `document_year_original`, and the decision
  in `document_year_audit` (`supported` or `demoted:<class>`).

Two enforcement layers:
1. **Query-time forward guard** (`freshness.document_year_for_freshness`): an
   unsupported future trusted year never earns a recency boost — it is replaced
   by the best non-future year (or none). Protects NEW ingests automatically.
2. **Stored-data correction** (migration below): fixes the existing corpus so
   BM25, context, and any other consumer see the honest year too.

## Audit & migration (read-only + document-scope, metadata-only)

```bash
python -m scripts.audit_future_dated            # read-only classification report
python -m scripts.migrate_future_dated          # dry-run correction plan
python -m scripts.migrate_future_dated --apply  # snapshot + apply
```

The migration updates metadata via `collection.update` — **embeddings,
documents, and chunk IDs are unchanged; no re-ingestion**. It is dry-run capable,
snapshot-backed, bounded (batched), resumable (each document independent), and
idempotent (a corrected chunk is no longer future-dated, so a re-run skips it).

## Applied result (2026-07-01)

- Classified 16 future-dated document-entries: **3 SUPPORTED_VALID (kept, 7
  chunks)**, 11 UNSUPPORTED_AMBIG, 2 MALFORMED_OCR (**39 chunks demoted**).
- Demote targets (all ≤ runtime year): 2019×10, 2023×6, 2024×4, 2025×10, 2026×9.
- Future-dated chunks: **46 → 7** (only the genuine 2026-2027 hostel prospectus).
- Chroma chunk count unchanged (14,753); BM25 rebuilt; BM25↔Chroma 0 missing / 0
  stale. Full backend suite: **105 passed**; golden Recall@8 7/7.
- Ranking impact (within a band, "current/latest" query): a mis-dated report went
  from `fresh ≈ 2027*100 + 7500` (outranking a real 2026 doc) to its true year,
  now ranking **below** genuinely current documents; the real prospectus keeps 2027.
- Snapshot: `backend/data/backups/20260701T164600Z_migrate_future_dated`.

## Rollback

Restore the snapshot via `scripts/migration_snapshot.py`. The correction is also
reversible per chunk from `document_year_original`.

## Limitations

- A couple of demote targets came from a metadata field carrying a slightly newer
  (but still non-future) session year (e.g. an AQAR 2023-24 → 2025); this removes
  the artificial *future* boost, though the recovered year may be one session off.
- Classification is heuristic; it errs toward demotion (an unsupported future year
  loses only a freshness boost — the full text remains retrievable and readable).
