#!/usr/bin/env python3
"""
Tier-1 knowledge-hierarchy priority test.

For each question in tier1_priority_set.json, run the SAME retrieval path the
production code and the golden-eval harness use, then assert the top-ranked
retrieved source is one of the expected canonical (Tier 1) documents — i.e. the
Prospectus / Handbook / Hostel Prospectus is surfaced BEFORE any notice,
circular, report or other secondary document.

Deterministic (no LLM call, no API cost). Run from backend/:
    .venv/bin/python tests/test_tier1_priority.py
    .venv/bin/python tests/test_tier1_priority.py --topk   # accept Tier1 in top-k
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_golden_eval import retrieve_for_eval  # reuse the production query path

SET_PATH = os.path.join(os.path.dirname(__file__), "tier1_priority_set.json")


def _filename(meta) -> str:
    return str((meta or {}).get("filename", ""))


def main() -> int:
    accept_topk = "--topk" in sys.argv
    with open(SET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    k = data.get("k", 5)
    questions = data["questions"]

    passed = 0
    failures: list[str] = []

    for q in questions:
        qid = q["id"]
        question = q["question"]
        expected = [e.lower() for e in q["expected_top_any"]]
        try:
            _docs, metas, _dists = retrieve_for_eval(question, k)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{qid}] ERROR {exc}")
            continue

        names = [_filename(m) for m in metas]
        top = names[0] if names else ""
        top_hit = any(e in top.lower() for e in expected)
        anyk_hit = any(any(e in n.lower() for e in expected) for n in names[:k])
        ok = anyk_hit if accept_topk else top_hit

        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {qid:<26} top={top!r}")
        if ok:
            passed += 1
        else:
            failures.append(f"[{qid}] expected {expected} as {'in top-k' if accept_topk else 'top-1'}; got top={top!r} topk={names[:k]}")

    total = len(questions)
    print("\n" + "=" * 70)
    print(f"TIER-1 PRIORITY ({'top-k' if accept_topk else 'top-1'}): {passed}/{total} = {passed / total:.2%}")
    if failures:
        print("\nFailures:")
        for line in failures:
            print("  " + line)
        return 1
    print("RESULT: ALL TIER-1 PRIORITY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
