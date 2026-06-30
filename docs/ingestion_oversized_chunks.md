# Known oversized chunks (embedding token cap)

_Last reviewed: 2026-06-30_

## Summary

The embedding model (`BAAI/bge-base-en-v1.5`) has a hard **512-token** input cap;
SentenceTransformer truncates anything longer. The ingestion pipeline now splits
oversized chunks at ingest time (`ingestion.split_chunks_for_embedding`) and a
one-off migration (`scripts/resplit_oversized_chunks.py`) re-split the existing
backlog: **1117 oversized chunks → 2368 budget-sized pieces**.

After that migration, **28 chunks still exceed 512 tokens** (≈0.2% of ~14,750).
They are intentionally left as-is.

## Why these remain

The re-split helper only divides a chunk when splitting actually yields multiple
smaller pieces. The remaining chunks are *single, dense units* — one continuous
paragraph, one table, or one list with no usable split point near the 512-token
boundary — so splitting either produces one piece again or would cut mid-sentence
/ mid-row.

Crucially, the overflow is **small**: every remaining chunk is in the
**513–581 token** range, i.e. **1–69 tokens (≤13%) over** the cap. Only that small
tail is dropped from the *embedding vector*; the **full text is still stored** and
remains fully searchable via BM25 and visible to the cross-encoder reranker and
the LLM. So the practical retrieval impact is minimal.

## Composition (28 chunks)

| dimension | breakdown |
|---|---|
| chunk_type | text 22, table 4, list 2 |
| source_type | website_pdf 26, website 2 |
| token range | 513–581 (≤13% over the 512 cap) |
| dominant source | `College_Handbook_2023_24.pdf` (dense policy prose), AQAR reports, a few faculty profiles |

Regenerate the exact current list any time (read-only):

```bash
python -m scripts.list_oversized_chunks
```

## Decision: do not force-split further

Per the maintainers' direction, we do **not** add aggressive sub-512 splitting
logic solely to eliminate these, because:

1. The benefit is marginal — only a ≤13% tail of 28 chunks is missing from the
   vector, and those chunks are still retrievable lexically and readable in full.
2. Hard mid-sentence / mid-row splitting risks degrading retrieval quality and
   citation cleanliness across the *whole* corpus for a tiny edge case.

## If this ever needs to change

Safer options than aggressive splitting, in order of preference:

1. Raise the header reserve only for these chunk types, or drop the
   `Title/Source/Section` header for chunks already near the cap (recovers
   ~25–48 tokens of body for free).
2. Move to an embedding model with a larger context window (e.g. a long-context
   BGE/E5 variant) — requires a full re-embed, so weigh accordingly.
3. Sentence-aware splitting that only triggers above the budget and never cuts
   inside a table row.

None of these are warranted by the current, negligible impact.
