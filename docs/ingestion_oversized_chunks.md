# Oversized chunks (embedding token cap) — RESOLVED

_Last reviewed: 2026-07-01_

## Status: 0 chunks over the 512-token embedding cap

`BAAI/bge-base-en-v1.5` has a hard **512-token** input cap and SentenceTransformer
truncates anything longer *silently*. Two distinct causes of over-cap embedding
text have now been eliminated, so the actual embedding text of every one of the
14,753 chunks fits within 512 tokens (verify read-only with
`python -m scripts.list_oversized_chunks`).

## Cause 1 — oversized chunk *body* (historical, already fixed)

Long table/list/paragraph bodies (~8% of chunks, 1,117 at the time) exceeded the
cap. Fixed forward at ingest by `ingestion.split_chunks_for_embedding`, and the
existing backlog was re-split by `scripts/resplit_oversized_chunks.py`
(1,117 → 2,368 pieces). An atomic body with no usable separator near the boundary
used to be hard-capped (its tail decoded away); it is now covered by overlapping
**token windows** (`ingestion._token_window_split`) so every token is embedded.

## Cause 2 — oversized *header* (the residual 28, fixed 2026-07-01)

After Cause 1, **28 chunks** still measured 513–581 tokens. Diagnosis showed the
overflow was **entirely the header, not the body**: every one of the 28 had a
body ≤ 464 tokens (within budget) but a `Title/Source/Section` header of
**51–119 tokens** — far over the 48-token reserve — from very long document
titles/headings (e.g. `College_Handbook_2023_24.pdf`, AQAR reports, some faculty
profiles). Splitting the body could not help because the body already fit.

Fix:
- Forward: `ingestion.build_embedding_text(chunk, meta)` is now the single source
  of truth for the embedded text and **caps the header at the 48-token reserve**.
  For a normal (short-header) chunk it returns byte-for-byte the old text, so the
  vast majority of embeddings are unchanged.
- Backlog: `scripts/reembed_oversized_header_chunks.py` re-embedded the 28
  affected chunks **in place** (same id / document / metadata, corrected vector
  only), dry-run-capable, snapshot-backed, idempotent, bounded.

## Verification (2026-07-01)

```
python -m scripts.list_oversized_chunks     # chunks over budget: 0 / 14753
```

- Chroma chunk count unchanged: 14,753 (in-place re-embed, no adds/deletes).
- BM25 ↔ Chroma still fully consistent (0 missing, 0 stale) — BM25 indexes the
  document text, which did not change.
- Full backend suite: 91 passed (incl. `TestEmbeddingTokenBudget` cases for the
  header cap and token-window coverage).

## Rollback

A snapshot is taken automatically before `--apply`
(`backend/data/backups/<ts>_reembed_oversized_header_chunks`). Restore with
`scripts/migration_snapshot.py`. The migration is also self-healing: re-running it
after a partial run only re-embeds whatever is still over cap.
