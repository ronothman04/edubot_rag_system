#!/usr/bin/env python3
"""
Golden-set evaluation harness for EduBot (audit §8).

Reports TWO metrics independently:
  * recall@k  — did a known-correct source appear in the top-k retrieved chunks
                (deterministic, no LLM call, no API cost).
  * answer    — (optional, --with-answers) did ask()'s answer contain the
                expected keywords / response_type. Costs one Groq call per
                question.

Web-sourced questions whose expected source is web content are SKIPPED for
recall when the index currently holds no web chunks (so a "fail" is never
charged to retrieval for missing data).

Usage:
    .venv/bin/python tests/run_golden_eval.py                # recall@k only
    .venv/bin/python tests/run_golden_eval.py --with-answers # + answer quality
    .venv/bin/python tests/run_golden_eval.py --k 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")


def index_has_web_content(min_chunks: int = 5) -> bool:
    """True only when the index holds a MEANINGFUL amount of web content.

    A small threshold avoids a single stray/mis-tagged chunk making web-sourced
    questions look retrievable when there is effectively no crawled content.
    """
    try:
        import db
        res = db.collection.get(include=["metadatas"])
        count = sum(
            1 for m in res.get("metadatas", [])
            if "website" in str((m or {}).get("source_type", "")).lower()
        )
        return count >= min_chunks
    except Exception as exc:
        print(f"[warn] could not inspect index for web content: {exc}")
        return False


def build_where_filter(query: str):
    """Mirror the production namespacing (rag/main.py Fix 1) so eval == runtime."""
    from rag.intent import extract_entities
    from rag.filters import build_filter
    from rag.config import KNOWN_DEPARTMENT_NAMES

    dept = extract_entities(query).get("department")
    eff = dept if (dept and str(dept).lower() in KNOWN_DEPARTMENT_NAMES) else None
    return build_filter(False, None, eff, None, None)


def retrieve_for_eval(query: str, k: int):
    """Run the same query transforms main.py uses, then retrieve_chunks."""
    from rag.query_expansion import (
        build_focused_retrieval_query,
        build_smart_query,
        build_smart_retrieval_query,
    )
    from rag.text_utils import normalize_query
    from rag.retrieval import retrieve_chunks

    rq_raw, _latest, _used = build_smart_query(query, "")
    emb = build_focused_retrieval_query(rq_raw)
    rq = normalize_query(build_smart_retrieval_query(rq_raw))
    return retrieve_chunks(
        query=rq, top_k=k, where_filter=build_where_filter(query),
        embedding_query=emb, original_query=query,
    )


def source_hit(metas, expected_any) -> bool:
    needles = [s.lower() for s in expected_any]
    for m in metas:
        m = m or {}
        hay = f"{m.get('filename', '')} {m.get('source_url', '')}".lower()
        if any(n in hay for n in needles):
            return True
    return False


def answer_ok(resp: dict, q: dict) -> tuple[bool, str]:
    answer = str(resp.get("answer", "") or "")
    al = answer.lower()

    exp_type = q.get("expected_response_type")
    if exp_type and resp.get("response_type") != exp_type:
        return False, f"response_type={resp.get('response_type')} != {exp_type}"

    any_kw = q.get("expected_keywords_any") or []
    if any_kw and not any(kw.lower() in al for kw in any_kw):
        return False, f"none of {any_kw} in answer"

    all_kw = q.get("expected_keywords_all") or []
    missing = [kw for kw in all_kw if kw.lower() not in al]
    if missing:
        return False, f"missing {missing}"

    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-answers", action="store_true", help="also call ask() and score answers")
    ap.add_argument("--k", type=int, default=None, help="recall@k cutoff (default from golden_set.json)")
    ap.add_argument("--strict", action="store_true", help="exit nonzero if recall@k < 0.8")
    args = ap.parse_args()

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)
    k = args.k or golden.get("k", 8)
    questions = golden["questions"]

    has_web = index_has_web_content()
    print(f"Index has web content: {has_web}   |   recall@{k}   |   with_answers={args.with_answers}\n")

    recall_eval = recall_hit = 0
    ans_eval = ans_pass = 0

    for q in questions:
        qid = q["id"]
        question = q["question"]

        # ---- recall@k (retrieval) ----
        rline = ""
        if q.get("retrieval_eval", True) and q.get("expected_source_any"):
            if q.get("requires_web") and not has_web:
                rline = "recall=SKIP (no web content in index)"
            else:
                try:
                    _docs, metas, _dists = retrieve_for_eval(question, k)
                    hit = source_hit(metas, q["expected_source_any"])
                    recall_eval += 1
                    recall_hit += int(hit)
                    got = [str((m or {}).get("filename", "")) for m in metas[:k]]
                    rline = f"recall={'HIT ' if hit else 'MISS'} top={got[:4]}"
                except Exception as exc:
                    rline = f"recall=ERROR {exc}"
        else:
            rline = "recall=n/a"

        # ---- answer quality (optional) ----
        aline = ""
        if args.with_answers:
            try:
                from rag import ask
                resp = ask(query=question)
                ok, why = answer_ok(resp, q)
                ans_eval += 1
                ans_pass += int(ok)
                aline = f"answer={'PASS' if ok else 'FAIL'} ({why})"
            except Exception as exc:
                aline = f"answer=ERROR {exc}"

        print(f"[{qid}] ({q.get('category')}) {question}")
        print(f"    {rline}")
        if aline:
            print(f"    {aline}")

    print("\n" + "=" * 70)
    if recall_eval:
        rec = recall_hit / recall_eval
        print(f"RECALL@{k}: {recall_hit}/{recall_eval} = {rec:.2%}")
    else:
        rec = None
        print("RECALL@k: no evaluable questions")
    if args.with_answers and ans_eval:
        print(f"ANSWER QUALITY: {ans_pass}/{ans_eval} = {ans_pass / ans_eval:.2%}")

    if args.strict and rec is not None and rec < 0.8:
        print("STRICT: recall below 0.8")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
