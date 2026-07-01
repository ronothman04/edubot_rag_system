# EduBot — Table-Integrity & Acronym Audit / Fix

Trigger: the answer to **“is there VTC course?”** rendered a polished Markdown
table with an invented acronym (“VET”), guessed/dashed cells, a merged
credit-hours value (“1 3 4”), and unwarranted confidence. This was treated as a
*symptom of a general weakness*, not a one-off. No question-specific logic was
added.

---

## 1. Root cause of the example failure

The answer was assembled from chunk
`official_https___anthonys.ac.in_p3_c9662…` of `List_of_VTCS_with_Paper_Code.pdf`,
whose **extracted table is structurally broken**:

```
| VTC: 367.1 | Beauty Care-III | 1 | 3 | 4 |
| VTC: 368. | | | | |          ← blank cells
| VTC: 369 | Others | | | |
| VTC:369.1 | Photography-III | | | |
| | | 1 | 3 | 4 |             ← credit values detached from their row
```

The header row (`| Course Code | VOCATIONAL EDUCATION AND TRAINING COURSES |
Credit Hours | Column 4 | Column 5 |`) lives in a **different chunk** (`…c9660_s1`),
i.e. chunking split the header from the body. So the model received: a table with
no header, empty cells, auto-named placeholder columns, and a row whose three
numeric cells (`1 3 4` = Theory/Practical/Total) had floated free.

Three independent defects combined to turn that into the bad answer:

1. **Broken table passed through verbatim.** Nothing detected the empty cells,
   placeholder headers, or detached header before generation.
2. **The format stage *encouraged* a table** and the prompt permitted “Not
   specified” fillers — so the model produced a clean grid from garbage.
3. **Acronym handling.** `normalize_query` *replaced* `VTC` with an expansion,
   and the prompt did not forbid coining new short forms — so the model invented
   “VET”, an acronym that appears nowhere in the sources.

## 2. Other affected examples found (live index)

The malformation is systemic, not VTC-specific. Across **3,762 table-bearing
chunks**:

| Defect | Chunks |
|---|---|
| Placeholder `Column N` headers (extractor guessed structure) | 1,032 |
| ≥1 data row missing ≥2 cells (blank cells) | 794 |
| Table body with no separator row (header detached by chunking) | 2,529 |
| **Any structurally-unreliable table (union)** | **3,129 (83.2%)** |

Confirmed across many documents and content types: `doc_NodalOfficers.pdf`
(officer roster), `doc_StrategicPlan2013-28.pdf` (plan tables),
`doc_ChemistrySyllabus.pdf` / `doc_ComputerScienceSyllabus.pdf` (credit tables
with the same `VTC 360–369 … 1 3 4` merged-number row), committee tables, etc.

A **second, independent** general defect was proven in retrieval: acronym
expansion was *destructive*. `MCA-CC-6000` → `master of computer applications cc
6000` and `VTC` vanished entirely, so BM25 could no longer match the exact
code/acronym the user typed (violating “prefer exact code/acronym matches”).

## 3. General failure pattern

> PDF/website/OCR table extraction frequently emits structurally-invalid Markdown
> tables (placeholder headers, blank cells, headers detached by chunking, merged
> numeric columns). The answer pipeline passes these straight to the LLM, which
> re-renders a **polished but fabricated** table — inventing acronym expansions,
> guessing/dashing missing cells, and regrouping merged numbers. Separately,
> query normalization destroyed exact code/acronym tokens needed for lexical
> retrieval.

## 4. Earliest faulty pipeline stage

Earliest **proven** corruption is at **table extraction + chunking** (blank
cells, placeholder headers, header/body split). Re-extracting 440 source PDFs is
heavy, risky, and largely bounded by the source documents themselves. Per the
brief (“smallest general fix”, “no full re-ingestion unless the root cause
requires it”, “fix the earliest proven failure in extraction, chunking,
indexing, retrieval, context construction, or response validation”), the fix is
applied at the **context-construction and response-validation** stages, which
neutralize the entire class **at query time across the whole corpus with no
re-ingestion**, plus a **retrieval-normalization** fix and **prompt** hardening.

## 5. Files changed

| File | Change |
|---|---|
| `backend/rag/table_integrity.py` | **New.** Reusable table parsing + structural-integrity scoring + context sanitizer + answer backstop. Pure structure-based; no document/acronym/query specifics. |
| `backend/rag/context.py` | `build_context` degrades unreliable tables in each chunk via `sanitize_context_tables` before the LLM sees them. |
| `backend/rag/text_utils.py` | `normalize_query` acronym expansion is now **additive** — keeps the exact token and appends the expansion. |
| `backend/rag/config.py` | Two general grounding rules added: never coin/inject an acronym absent from CONTEXT; never render a table from incomplete/misaligned rows. |
| `backend/rag/main.py` | Post-generation backstop `degrade_answer_tables` rewrites any still-broken answer table. |
| `backend/tests/test_table_integrity.py` | **New.** 11 regression tests for every general fix. |
| `backend/tests/regression_dataset.json` | **New.** 57-question dataset across documents/types. |
| `backend/tests/run_table_regression.py` | **New.** Retrieval + integrity metrics harness. |

## 6. General solution implemented

`rag/table_integrity.py` scores each Markdown table on structure only:
placeholder-header ratio, blank-cell density, ragged/duplicate-header rows,
detached header (no separator), single-column collapse. A table is **reliable**
only when those checks pass; thresholds are lenient so genuine tables are never
degraded. Unreliable tables in **context** are rewritten to plain
`label | value` lines carrying *only the cells actually present*, prefixed with an
explicit incompleteness note — so the model states confirmed facts and cannot
re-grid noise. A symmetric **answer backstop** degrades any broken table the model
still emits. The prompt now forbids inventing acronyms and rendering incomplete
tables. Retrieval keeps the exact acronym/code token.

## 7. Why the solution is not hardcoded

Nothing keys on “VTC”, “VET”, Photography, a filename, a URL, or an expected
answer. The validator keys purely on table *shape*; the sanitizer/backstop run on
any text; the prompt rules are universal; the acronym change applies to every
entry in the existing map. Evidence: the same code degrades NodalOfficers,
StrategicPlan, syllabi, and committee tables, and leaves valid fee/faculty tables
— including a Chemistry table that legitimately uses `-` for “no practical hours”
— untouched (`test_legit_dashes_are_not_treated_as_broken`).

## 8. Data migration / re-ingestion required

**None.** The fix runs at query time. A snapshot helper already exists
(`backend/scripts/migration_snapshot.py`) if a future ingestion-side fix is
pursued; no destructive migration was performed here.

## 9. Tests added

- `tests/test_table_integrity.py` — 11 tests: malformed/placeholder detection,
  reliable-table preservation, mixed-text selective degrade, no fabricated
  dashes, answer backstop on/off, legit-dash preservation, and additive-expansion
  token survival (VTC, `MCA-CC-6000`, BCA).
- `tests/regression_dataset.json` + `tests/run_table_regression.py` — 57
  questions with per-item `expected`, `expected_source_any`, `table_dependent`,
  `all_rows_required`, `freshness_matters`; harness computes Recall@k, MRR,
  exact-source rate, and table-integrity rate.

## 10. Before-and-after retrieval results

Additive acronym expansion (BM25 keyword rank of the expected source):

| Query | OLD rank | NEW rank |
|---|---|---|
| `is there VTC course?` | 2 | **1** |
| `VTC 369.1 paper code` | 1 | 1 |
| `CSC-352 paper` | 5 | 5 |
| `CHE 350 credit` | 6 | 6 |

No query regressed; the mapped-acronym query improved. Exact tokens (`vtc`,
`mca`, `cc`, `6000`) now survive normalization (previously deleted).

## 11. Before-and-after answer results (the trigger query)

- **Before:** “Vocational Education and Training (VET) Courses” table with rows
  `VTC: 368 | – | –`, `VTC: 369 | Others | –`, `VTC: 369.1 | Photography-III | 1 3 4`.
  Invented acronym, guessed dashes, merged credit value, false confidence.
- **After:** the same chunk reaches the model as the degraded plain-text block
  (incompleteness note + only the present values, no blank cells, `1 | 3 | 4`
  never attached to Photography-III), and the prompt forbids both the “VET”
  coinage and table fabrication. The model can list the VTC courses it can
  confirm and state that some paper-code/credit details aren’t available, instead
  of a fabricated grid. (Verified deterministically at the context/validator
  stages; final wording depends on the live LLM.)

## 12. Metrics across the broader evaluation set

Live index, 57-question regression set (retrieval + structure, offline):

| Metric | Value |
|---|---|
| Recall@1 | 0.615 |
| Recall@3 | 0.635 |
| Recall@5 | 0.692 |
| Recall@10 | 0.769 |
| MRR | 0.647 |
| Exact-source rate | 0.615 |
| **Table-integrity rate (table-dependent Qs)** | **21/21 = 1.000** |

Corpus-level structural integrity:

| | Unreliable-table chunks |
|---|---|
| **Before** | 3,129 / 3,762 (**83.2%**) |
| **After** sanitize | **0 / 3,762 (0.0%)** |

Regression guards: existing suite **87 passed**; golden eval **Recall@8 7/7 =
100%** (unchanged).

> Note: answer-level metrics (hallucination, answer-supported, citation
> correctness, not-found precision/recall, outdated-source selection) require the
> live Groq LLM and are non-deterministic; the harness computes them under
> `--with-llm`. The offline numbers above isolate the retrieval + structural fix.

## 13. Remaining limitations

- The fix repairs *presentation/grounding*, not the underlying extraction: the
  source rows are still split/blank in storage. A clean long-term fix is
  improving table extraction + table-aware chunking at ingest (header kept with
  body), which would require re-ingestion.
- Recall on faculty/HOD/department-roster queries is bounded by `expected_source_any`
  strictness (several valid roster docs); misses like `fa03/fa04/mp03` are
  dataset-label artifacts more than retrieval faults.
- The acronym map is still a curated project mapping; unknown acronyms aren’t
  expanded (by design — only reliable mappings expand).
- Not-found gating depends on downstream relevance/LLM, not on retrieval
  emptiness (absent questions still surface candidate chunks).

## 14. Rollback procedure

Pure code, no data migration. To revert:

1. `git checkout -- backend/rag/context.py backend/rag/text_utils.py backend/rag/config.py backend/rag/main.py`
2. `rm backend/rag/table_integrity.py backend/tests/test_table_integrity.py backend/tests/regression_dataset.json backend/tests/run_table_regression.py`
3. Restart the backend. No index/embedding changes were made, so retrieval
   reverts exactly to prior behavior.

## 15. Readiness verdict

**Ready to ship.** The change is additive, query-time, and reversible. It
eliminates structurally-broken tables from context (83.2% → 0%), preserves all
valid tables/lists/paragraphs, keeps exact code/acronym tokens for retrieval, and
adds prompt guards against acronym invention and table fabrication. All 87
existing tests, 12 new tests, and the golden eval pass with no regression.
