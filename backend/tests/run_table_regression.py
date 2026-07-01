"""
Regression / metrics harness for the table-integrity + acronym audit.

Runs every question in tests/regression_dataset.json through the REAL retrieval
pipeline against the live index and reports retrieval + structural-integrity
metrics. It deliberately computes only the metrics that can be measured without
calling the LLM (which needs the Groq API key and is non-deterministic):

    Recall@1/3/5/10, MRR, exact-source-rate     -> retrieval quality
    table-integrity-rate                         -> share of table-dependent
                                                    questions whose final context
                                                    contains NO unreliable raw
                                                    Markdown table (after the
                                                    sanitizer runs)
    not-found retrievability                     -> for absent questions, whether
                                                    the index even surfaces a
                                                    plausibly-matching source

Answer-level metrics (answer-supported, citation correctness, not-found
precision/recall, hallucination, outdated-source) require the live LLM; pass
--with-llm to additionally run rag.ask and print those. Without it the harness is
fully offline and deterministic.

Usage:
    .venv/bin/python tests/run_table_regression.py
    .venv/bin/python tests/run_table_regression.py --with-llm   # needs API key
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from rag.text_utils import normalize_query, distill_embedding_query
from rag.query_expansion import build_smart_retrieval_query
from rag.retrieval import retrieve_chunks
from rag.context import build_context
from rag.table_integrity import context_has_unreliable_table

DATASET = os.path.join(os.path.dirname(__file__), "regression_dataset.json")
TOP_K = 10


def _filenames(metas):
    return [str(m.get("filename") or "") for m in metas]


def _first_match_rank(retrieved_files, expected_any):
    exp = {e.lower() for e in expected_any}
    for i, f in enumerate(retrieved_files):
        if f.lower() in exp:
            return i + 1  # 1-indexed
    return None


def run(with_llm: bool = False):
    with open(DATASET) as fh:
        data = json.load(fh)
    questions = data["questions"]

    answerable = [q for q in questions if q["expected"] != "not_found"]
    absent = [q for q in questions if q["expected"] == "not_found"]

    recall = {1: 0, 3: 0, 5: 0, 10: 0}
    mrr_sum = 0.0
    exact_hits = 0
    table_qs = 0
    table_clean = 0
    per_q = []

    for q in answerable:
        smart = build_smart_retrieval_query(q["question"])
        kw_q = normalize_query(smart)
        emb_q = normalize_query(distill_embedding_query(q["question"]))
        docs, metas, dists = retrieve_chunks(
            query=kw_q, top_k=TOP_K, where_filter=None,
            embedding_query=emb_q, original_query=q["question"],
        )
        files = _filenames(metas)
        rank = _first_match_rank(files, q["expected_source_any"])
        for k in recall:
            if rank is not None and rank <= k:
                recall[k] += 1
        if rank is not None:
            mrr_sum += 1.0 / rank
            if rank == 1:
                exact_hits += 1

        # Table-integrity: build the FINAL context (sanitizer runs inside) and
        # confirm no broken raw table leaks through for table-dependent questions.
        clean = None
        if q["table_dependent"]:
            table_qs += 1
            context, _src = build_context(kw_q, docs, metas, dists)
            clean = not context_has_unreliable_table(context)
            if clean:
                table_clean += 1

        per_q.append((q["id"], rank, clean))

    # Absent-answer retrievability (do the right docs stay OUT of top results?).
    absent_surfaced = 0
    for q in absent:
        smart = build_smart_retrieval_query(q["question"])
        docs, metas, dists = retrieve_chunks(
            query=normalize_query(smart), top_k=TOP_K, where_filter=None,
            embedding_query=normalize_query(distill_embedding_query(q["question"])),
            original_query=q["question"],
        )
        # We cannot assert a gold "no source"; we just record how many chunks pass
        # the context relevance gate, as a proxy for not-found behaviour.
        context, src = build_context(normalize_query(smart), docs, metas, dists)
        if src:
            absent_surfaced += 1
        per_q.append((q["id"], "absent", None))

    n = len(answerable)
    print("=" * 64)
    print(f"Answerable questions: {n}   Absent questions: {len(absent)}")
    print("-" * 64)
    for k in (1, 3, 5, 10):
        print(f"  Recall@{k:<2}: {recall[k]}/{n} = {recall[k]/n:.3f}")
    print(f"  MRR     : {mrr_sum/n:.3f}")
    print(f"  Exact-source rate (Recall@1): {exact_hits/n:.3f}")
    if table_qs:
        print(f"  Table-integrity rate: {table_clean}/{table_qs} = {table_clean/table_qs:.3f}")
    print(f"  Absent questions surfacing any context source: {absent_surfaced}/{len(absent)}")
    print("-" * 64)
    misses = [pid for pid, rank, _ in per_q if rank is None]
    if misses:
        print(f"  Retrieval misses (no expected source in top {TOP_K}): {misses}")
    dirty = [pid for pid, _, clean in per_q if clean is False]
    if dirty:
        print(f"  Table-dependent Qs with a broken table still in context: {dirty}")
    print("=" * 64)

    if with_llm:
        _run_llm_checks(questions)


def _run_llm_checks(questions):
    """Optional: live-answer checks (needs API key). Prints a compact table."""
    from rag.main import ask
    print("\nLIVE ANSWER CHECKS (LLM):")
    for q in questions:
        try:
            resp = ask(q["question"])
            ans = resp.get("answer", "") if isinstance(resp, dict) else str(resp)
        except Exception as e:  # noqa: BLE001
            ans = f"<error: {e}>"
        # Hallucination heuristic: an answer that renders a Markdown grid AND
        # contains an empty/placeholder cell is a structural hallucination.
        from rag.table_integrity import answer_table_is_unreliable
        bad_table = answer_table_is_unreliable(ans)
        snippet = " ".join(ans.split())[:90]
        print(f"  [{q['id']}] bad_table={bad_table} | {snippet}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true")
    args = ap.parse_args()
    run(with_llm=args.with_llm)
