# EduBot Query Robustness Audit

Date: 2026-07-02

Checkpoint before changes: `41a0d809` (`checkpoint: before query robustness audit`)

## 1. Root Causes Identified

The regression was not caused by ingestion. The divergence started in query understanding and compounded in retrieval:

1. Semantically equivalent curriculum queries were normalized differently. Informal list phrasing such as `what subject are there for 1st sem MA Education?` kept noisy surface form, while direct syllabus phrasing became a strong retrieval query.
2. Semester variants (`1st sem`, `Sem I`, `semester 1`) were not normalized into a stable representation early enough.
3. Informal curriculum words such as `subject` were not consistently mapped into the same curriculum intent family as `syllabus`, `course`, `paper`, and `module`.
4. Dense retrieval used the conversational query too literally, so unrelated first-semester chunks from other programmes outranked the correct MA Education syllabus.
5. Reranking over-weighted local lexical overlap and could promote unrelated profile chunks or other semester tables unless the curriculum query was constrained more tightly.
6. Follow-up rewrites relied too much on generic distillation and could drop critical programme constraints in elliptical turns.
7. Cache identity did not fully reflect the semantic retrieval query, so changed query-understanding logic could reuse stale retrieval results.
8. Authority/gating logic could still admit wrong-but-similar evidence unless the chunk actually looked like curriculum structure for the requested programme/semester.

## 2. Files Inspected and Changed

Inspected across the pipeline:

- `backend/rag/main.py`
- `backend/rag/query_expansion.py`
- `backend/rag/text_utils.py`
- `backend/rag/intent.py`
- `backend/rag/retrieval.py`
- `backend/rag/authority.py`
- `backend/rag/cache.py`
- `backend/rag/context.py`
- `backend/rag/filters.py`
- `backend/api.py`
- `backend/tests/run_golden_eval.py`
- `backend/tests/run_table_regression.py`
- `backend/tests/test_critical_fixes.py`

Changed:

- `backend/rag/__init__.py`
- `backend/rag/authority.py`
- `backend/rag/cache.py`
- `backend/rag/intent.py`
- `backend/rag/main.py`
- `backend/rag/query_expansion.py`
- `backend/rag/retrieval.py`
- `backend/rag/text_utils.py`
- `backend/tests/run_golden_eval.py`
- `backend/tests/run_table_regression.py`
- `backend/tests/test_critical_fixes.py`
- `backend/tests/run_query_robustness_eval.py`
- `backend/tests/test_query_robustness.py`

## 3. Exact Logic and Configuration Changes

1. Added conservative query repair in `text_utils.py` for minor spelling noise in high-signal retrieval vocabulary without rewriting unknown names or codes.
2. Added semester normalization for ordinal, numeric, and Roman-numeral variants.
3. Expanded intent detection so `subject`, `course`, `paper`, `module`, `curriculum`, and `syllabus` converge on the same curriculum/list behavior when the rest of the query supports that interpretation.
4. Added focused semantic query construction in `query_expansion.py` so dense retrieval and reranking see a compact canonical query preserving programme, department, semester, level, year, document type, and output-type constraints.
5. Kept BM25 smart expansion, but aligned it with the focused curriculum representation instead of letting conversational noise dominate.
6. Made follow-up rewriting deterministic for common elliptical turns so prior constraints survive without depending on the LLM rewriter.
7. Tightened curriculum evidence gating in `retrieval.py` so accepted evidence must look like actual syllabus/course-structure content for the requested constraints.
8. Tightened staff-list filtering so roster/list questions prefer real handbook/department roster evidence over incidental mentions.
9. Adjusted authority routing so curriculum questions are not overridden by admissions-oriented sources when dedicated syllabus evidence exists.
10. Bumped cache schema/version so retrieval results generated under the previous semantic query behavior are not silently reused.
11. Added citation cleanup in `main.py` so invalid generated citation markers do not erase valid provenance already attached to the retrieved sources.

## 4. Before-and-After Retrieval Traces

Regression example used for tracing:

- Successful baseline query: `syllabus for MA education`
- Failed baseline query: `what subject are there for 1st sem MA Education?`

Before:

- `syllabus for MA education`
  - Department/entity extraction: `education`, `MA`
  - Dense top result: `MA_Education.pdf` page 1
  - Cross-encoder top score: `0.9599`
  - Correct chunk survived to final context
- `what subject are there for 1st sem MA Education?`
  - Department/entity extraction: also `education`, `MA`
  - BM25 correct syllabus only at ranks `9-10`
  - Dense top results were mostly unrelated commerce/faculty chunks
  - Cross-encoder promoted an unrelated faculty/profile chunk around score `0.6093`
  - Correct syllabus chunk scored `0.0254`, rank `6`, then lost due to later top-k/context selection

After:

- `syllabus for MA education`
  - Rewritten query: unchanged
  - Focused semantic query: `ma master of arts master of arts education postgraduate syllabus course structure syllabus master arts`
  - Intent: `courses`
  - Entities: `department=education`, `course=MA`
  - Top retrieved chunks:
    - `MA_Education.pdf` p1 `Structure of NEW MA Syllabus, 2022`
    - `MA_Education.pdf` p1 `Structure of NEW MA Syllabus, 2022`
    - `MA_Education.pdf` p2 `Course Learning Outcomes:`
    - `MA_Education.pdf` p11 `EDN-DSEC 503 CURRICULUM DEVELOPMENT AND INSTRUCTION`
- `what subject are there for 1st sem MA Education?`
  - Rewritten query: unchanged text, but understanding normalizes `1st sem` to `first semester`
  - Focused semantic query: `ma master of arts master of arts education postgraduate first semester syllabus course structure syllabus list subject first semester master arts`
  - Intent: `courses`
  - List detection: `True`
  - Entities: `department=education`, `course=MA`
  - Top retrieved chunk:
    - `MA_Education.pdf` p1 `Structure of NEW MA Syllabus, 2022`

Equivalent curriculum queries now converge before dense retrieval instead of diverging there.

## 5. Tests Added

- `backend/tests/test_query_robustness.py`
  - deterministic unit coverage for semester normalization, curriculum/list detection, conservative spelling repair, focused semantic query construction, and follow-up rewriting
- `backend/tests/run_query_robustness_eval.py`
  - live retrieval regression harness covering:
    - admissions
    - programmes and syllabus
    - departments and faculty
    - fees
    - hostel
    - attendance
    - examinations
    - scholarships
    - committees
    - facilities
    - policies
    - contact information
    - list questions
    - ambiguous questions
    - misspellings
    - abbreviations
    - paraphrases
    - multi-turn follow-ups
    - negative/out-of-scope cases

## 6. Complete Test Results

Final local verification on the modified code:

- `python3 -m pytest -q` from `backend/`: `114 passed, 2 warnings`
- `python3 tests/run_query_robustness_eval.py`: `36/36 = 100.00%`
- `python3 tests/run_golden_eval.py`: `RECALL@8 7/7 = 100.00%`
- `python3 tests/run_table_regression.py`:
  - Recall@1: `37/52 = 0.712`
  - Recall@3: `41/52 = 0.788`
  - Recall@5: `43/52 = 0.827`
  - Recall@10: `43/52 = 0.827`
  - MRR: `0.749`
  - Table-integrity rate: `21/21 = 1.000`
  - Absent questions surfacing any context source: `5/5`
- `python3 -m py_compile $(rg --files -g '*.py')`: passed
- `python3 -c "import rag, api, ingestion"`: passed
- API startup test:
  - `backend/.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8011`
  - `GET /openapi.json` returned `200 OK`

Not run:

- Live Groq answer-generation verification was blocked by the execution policy because it would send retrieved knowledge-base content to an external model provider. Retrieval, citations, context construction, and startup were verified locally.

## 7. Precision and Recall Impact

Baseline deterministic table-regression metrics before the fix:

- Recall@1: `32/52 = 0.615`
- Recall@3: `33/52 = 0.635`
- Recall@5: `36/52 = 0.692`
- Recall@10: `40/52 = 0.769`
- MRR: `0.647`
- Table-integrity: `21/21 = 1.000`

Final deterministic table-regression metrics after the fix:

- Recall@1: `37/52 = 0.712`  (`+0.097`)
- Recall@3: `41/52 = 0.788`  (`+0.153`)
- Recall@5: `43/52 = 0.827`  (`+0.135`)
- Recall@10: `43/52 = 0.827` (`+0.058`)
- MRR: `0.749` (`+0.102`)
- Table-integrity: unchanged at `1.000`

Existing successful baseline recall did not regress:

- Golden recall stayed `7/7 = 100.00%`

Precision notes:

- The fix did not broaden metadata filters indiscriminately.
- Confidence thresholds were not relaxed to force answers.
- Negative tests still returned `out_of_scope` / `programme_not_found` behavior in the robustness harness.
- Remaining `5/5` absent queries surfacing context indicates existing not-found precision work still remains outside this change set.

## 8. Regressions Found

During implementation I found two secondary regressions and fixed them before the final run:

1. Contact/location phrasing such as `where is college located` was over-distilled and lost location intent.
2. General schedule phrasing such as `when do classes commence` was being compressed too aggressively.

Both were corrected in the final focused-query and intent logic. No regression remained in the final robustness suite.

## 9. Remaining Known Failure Cases

These are still open system limitations, not introduced by this fix:

1. Some table-regression misses remain for specific IDs: `ac02`, `ac07`, `fa02`, `fa03`, `fa04`, `el03`, `cf01`, `mp03`, `ex01`.
2. Absent-question handling still surfaces some context (`5/5`) even when the final answer should be not-found. That is a precision issue in downstream relevance gating/fallback, not in the equivalence fix itself.
3. External answer-generation behavior with the live Groq model was not reverified in this run because data egress to the third-party model endpoint was blocked.
4. A reranker fallback path appeared in some evaluation runs under system Python; the production backend venv still loaded the intended cross-encoder during startup.

## 10. Risks and Rollback Instructions

Primary risks:

1. The focused semantic query is intentionally more opinionated; future edge cases could over-compress unusual long-form questions if new intents are added without matching tests.
2. Cache versioning will invalidate prior retrieval cache entries and may temporarily increase cold-query latency.
3. Curriculum/staff evidence gates are stricter; unsupported or weakly documented questions are now more likely to produce not-found instead of a loosely related answer, which is preferred but behaviorally different.

Rollback:

1. Full rollback to the pre-audit checkpoint:
   - `git restore --source 41a0d809 -- backend/rag backend/tests`
2. Selective rollback of only this audit’s touched files:
   - `git restore --source 41a0d809 -- backend/rag/__init__.py backend/rag/authority.py backend/rag/cache.py backend/rag/intent.py backend/rag/main.py backend/rag/query_expansion.py backend/rag/retrieval.py backend/rag/text_utils.py backend/tests/run_golden_eval.py backend/tests/run_table_regression.py backend/tests/test_critical_fixes.py backend/tests/run_query_robustness_eval.py backend/tests/test_query_robustness.py`

Current changed files in the working tree are limited to the audit implementation and tests listed above.
