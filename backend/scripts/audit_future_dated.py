"""
audit_future_dated.py  (READ-ONLY diagnostic)

Audits chunks whose trusted document_year is in the FUTURE relative to the
runtime current year, and classifies each affected *document* by how well the
future year is supported by evidence. Read-only: never writes to the store.

A future year is NOT automatically wrong — it can be a legitimate academic
session, admission cycle, prospectus, deadline, or officially published
forward-looking validity period. This script gathers the evidence a human (or the
paired migration) needs to decide, using dynamic runtime-year boundaries.

Classification (per document):
  SUPPORTED_VALID     - future year appears in a session range (e.g. 2026-2027 /
                        2026-27) or beside forward-looking terms (admission,
                        prospectus, session, academic year, valid up to, approval,
                        w.e.f.) -> keep.
  INFERRED_CREDIBLE   - year is a session/identifier year on a prospectus/
                        admission-type doc, but without an explicit range -> keep.
  UNSUPPORTED_AMBIG   - future year only as an isolated number, no forward context,
                        on a document whose identity points to a different/older
                        year -> demote (no artificial freshness boost).
  MALFORMED_OCR       - future year is glued to other digits / implausible for an
                        obviously historical report -> demote.

Usage:
    python -m scripts.audit_future_dated            # human-readable report
    python -m scripts.audit_future_dated --json     # machine-readable
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# The classification logic is shared with the migration so both agree exactly.
from rag.future_dates import classify_future_year


def _context_windows(text: str, year: str, width: int = 90) -> list[str]:
    out = []
    for m in re.finditer(re.escape(year), text):
        s = max(0, m.start() - width)
        e = min(len(text), m.end() + width)
        snippet = re.sub(r"\s+", " ", text[s:e]).strip()
        out.append(snippet)
    return out


def _provenance(document_year: int, all_text: str, meta: dict) -> str:
    yr = str(document_year)
    prov = []
    for field in ("filename", "source_filename", "title", "pdf_title", "source_url",
                  "source_pdf_filename"):
        if yr in str(meta.get(field, "")):
            prov.append(field)
    if yr in str(meta.get("document_date", "")):
        prov.append("document_date")
    if yr in all_text and not prov:
        prov.append("body_text")
    return ",".join(prov) or "unknown"


def _classify(document_year: int, all_text: str, meta: dict, current_year: int):
    provenance = _provenance(document_year, all_text, meta)
    windows = _context_windows(all_text, str(document_year))
    verdict = classify_future_year(document_year, all_text, meta, current_year)
    return (
        verdict["classification"],
        verdict["confidence"],
        provenance,
        windows,
        verdict["true_year"],
        verdict["action"],
    )


def main() -> None:
    import logging
    logging.disable(logging.CRITICAL)
    from db import collection

    as_json = "--json" in sys.argv
    current_year = time.gmtime().tm_year
    got = collection.get(include=["documents", "metadatas"])

    # Group future-dated chunks by document identity (filename + source_url).
    docs: dict[tuple, dict] = {}
    for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        meta = meta or {}
        try:
            dy = int(meta.get("document_year"))
        except (TypeError, ValueError):
            continue
        if dy <= current_year:
            continue
        key = (str(meta.get("filename", "")), str(meta.get("source_url", "")), dy)
        entry = docs.setdefault(key, {"chunks": 0, "text": [], "meta": meta})
        entry["chunks"] += 1
        entry["text"].append(doc)

    report = []
    totals: dict[str, int] = {}
    for (filename, source_url, dy), entry in sorted(docs.items(), key=lambda x: -x[1]["chunks"]):
        all_text = "\n".join(entry["text"])
        cls, conf, prov, windows, id_year, action = _classify(
            dy, all_text, entry["meta"], current_year
        )
        totals[cls] = totals.get(cls, 0) + 1
        report.append({
            "document": filename,
            "source_url": source_url,
            "chunks": entry["chunks"],
            "extracted_year": dy,
            "provenance": prov,
            "identifier_year": id_year,
            "classification": cls,
            "confidence": conf,
            "proposed_action": action,
            "evidence": windows[:3],
        })

    if as_json:
        print(json.dumps({"current_year": current_year, "totals": totals, "documents": report}, indent=2))
        return

    print(f"=== Future-dated document audit (runtime year = {current_year}) ===")
    print(f"future-dated documents: {len(report)}   chunks: {sum(r['chunks'] for r in report)}")
    print(f"classification totals : {totals}\n")
    for r in report:
        print(f"- {r['document']}  [{r['classification']} / {r['confidence']}]")
        print(f"    chunks={r['chunks']}  extracted_year={r['extracted_year']}  "
              f"identifier_year={r['identifier_year']}  provenance={r['provenance']}")
        print(f"    action: {r['proposed_action']}")
        for w in r["evidence"]:
            print(f"    evidence: …{w}…")
        print()


if __name__ == "__main__":
    main()
