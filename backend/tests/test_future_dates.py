"""
Regression tests for the dynamic future-dated-year policy (M-2).

Covered cases (per the M-2 brief):
  * legitimate future academic session -> kept
  * unsupported inferred future year   -> demoted
  * OCR / stray table number           -> demoted
  * filename-derived true year          -> extracted despite glued digits
  * conflicting date evidence (validity horizon) -> demoted, not treated as pub year
  * runtime-year boundary handling      -> boundary is exactly the runtime year

All boundaries are runtime-derived; tests use the live current year so they keep
passing in future years without edits.
"""
from __future__ import annotations

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from rag import future_dates as fd  # noqa: E402
from rag.freshness import document_year_for_freshness  # noqa: E402

CY = time.gmtime().tm_year
NEXT = CY + 1


class TestClassification:
    def test_legitimate_future_academic_session_kept(self):
        text = (
            f"STEPHEN HALL Boys Hostel PROSPECTUS {CY}-{NEXT} "
            f"St. Anthony's College Fees Structure ({CY}-{NEXT})"
        )
        meta = {"filename": "Prospectus_Boys_Hostel.pdf", "document_type": "prospectus"}
        v = fd.classify_future_year(NEXT, text, meta, CY)
        assert v["keep"] is True
        assert v["classification"] == "SUPPORTED_VALID"
        assert v["true_year"] == NEXT

    def test_unsupported_isolated_future_demoted(self):
        text = f"Reference line mentioning {NEXT} without any session context."
        v = fd.classify_future_year(NEXT, text, {"filename": "notes.pdf"}, CY)
        assert v["keep"] is False
        assert v["classification"] == "UNSUPPORTED_AMBIG"

    def test_ocr_table_number_demoted(self):
        text = f"UG [3 Years Program(s)] 1650 1506 3156 2334 784 38 192 {NEXT} 637 0 0 1582"
        v = fd.classify_future_year(NEXT, text, {"filename": "doc_2019Overall.pdf"}, CY)
        assert v["keep"] is False
        assert v["classification"] == "MALFORMED_OCR"
        assert v["true_year"] == 2019  # recovered from the glued filename

    def test_validity_horizon_demoted_not_pub_year(self):
        text = f"Does the institute have a valid NAAC Accreditation? Valid from 31-05-2022 Valid upto 30-05-{NEXT} CGPA 2.96"
        meta = {"filename": "AQAR_2023-2024.pdf", "title": "AQAR 2023-2024"}
        v = fd.classify_future_year(NEXT, text, meta, CY)
        assert v["keep"] is False
        assert v["true_year"] is not None and v["true_year"] <= CY

    def test_forward_reference_demoted(self):
        text = f"As we prepare for NAAC {NEXT}, the call before us is clear."
        v = fd.classify_future_year(NEXT, text, {"filename": "AC__2026_VOL_1.pdf"}, CY)
        assert v["keep"] is False
        assert v["true_year"] == 2026


class TestIdentifierYear:
    def test_glued_filename_years_recovered(self):
        assert fd.permissive_identifier_year("overall_2024.pdf") == 2024
        assert fd.permissive_identifier_year("doc_2019College.pdf") == 2019

    def test_future_and_packed_digits_ignored(self):
        # A future year and a digit-packed value must NOT be taken as identifier.
        assert fd.permissive_identifier_year(f"prospectus_{NEXT}.pdf", not_equal=NEXT) is None
        assert fd.permissive_identifier_year("value1922027here") is None

    def test_best_true_year_prefers_identifier_over_body(self):
        meta = {"filename": "overall_2024.pdf"}
        assert fd.best_true_year(NEXT, f"mentions {CY-5} and {NEXT}", meta, CY) == 2024

    def test_best_true_year_falls_back_to_non_future_body_year(self):
        assert fd.best_true_year(NEXT, f"published in {CY-1}", {}, CY) == CY - 1


class TestFreshnessGuard:
    def test_unsupported_future_year_not_boosted(self):
        meta = {"document_year": NEXT, "filename": "AQAR_2023-2024.pdf"}
        text = f"Valid upto 30-05-{NEXT}"
        # Guard replaces the future year with a non-future one (or None) — never NEXT.
        assert document_year_for_freshness(meta, text) != NEXT

    def test_supported_future_year_preserved(self):
        meta = {
            "document_year": NEXT,
            "filename": "Prospectus_Boys_Hostel.pdf",
            "document_type": "prospectus",
        }
        text = f"PROSPECTUS {CY}-{NEXT} Fees Structure ({CY}-{NEXT})"
        assert document_year_for_freshness(meta, text) == NEXT

    def test_audit_supported_flag_preserved(self):
        meta = {"document_year": NEXT, "document_year_audit": "supported",
                "filename": "x.pdf"}
        assert document_year_for_freshness(meta, "no session context here") == NEXT

    def test_runtime_boundary_current_year_not_demoted(self):
        # A year == runtime current year is NOT future, so it is left untouched.
        meta = {"document_year": CY, "filename": "notes.pdf"}
        assert document_year_for_freshness(meta, "isolated") == CY

    def test_runtime_boundary_dynamic(self):
        # future_year_is_supported keys off the runtime year passed in.
        session = f"prospectus {CY}-{NEXT}"
        meta = {"document_type": "prospectus", "filename": "p.pdf"}
        assert fd.future_year_is_supported(NEXT, session, meta, CY) is True
        # If the runtime year were far in the future, NEXT is no longer a current
        # session end, so it is not auto-supported by the session rule.
        assert fd.future_year_is_supported(NEXT, session, meta, CY + 10) is False
