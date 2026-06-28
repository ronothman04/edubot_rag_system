import sys
import os
import unittest
from datetime import datetime

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from crawl4ai_crawler import should_skip_url
from rag.freshness import parse_document_date_value, parse_document_date, parse_document_year


class TestCrawlerAndDateFixes(unittest.TestCase):
    def test_should_skip_url(self):
        # 1. Skip patterns
        self.assertTrue(should_skip_url("https://example.com/gallery/photos"))
        self.assertTrue(should_skip_url("https://example.com/staff-profile/john-doe"))
        self.assertTrue(should_skip_url("https://example.com/events-archive"))

        # 2. Keep patterns (should not skip even if it contains skip patterns)
        # e.g., contains 'admission' (keep) and 'gallery' (skip) -> keep takes priority
        self.assertFalse(should_skip_url("https://example.com/admission/gallery"))
        self.assertFalse(should_skip_url("https://example.com/notices/event-archive"))
        self.assertFalse(should_skip_url("https://example.com/news/faculty-profiles"))

        # 3. Regular URLs
        self.assertFalse(should_skip_url("https://example.com/about-us"))
        self.assertFalse(should_skip_url("https://example.com/courses/bca"))

    def test_parse_document_date_value(self):
        # PDF formats
        self.assertEqual(parse_document_date_value("D:20230612143000Z"), "2023-06-12")
        self.assertEqual(parse_document_date_value("20210825"), "2021-08-25")

        # HTTP Last-Modified formats
        self.assertEqual(parse_document_date_value("Wed, 21 Oct 2015 07:28:00 GMT"), "2015-10-21")
        self.assertEqual(parse_document_date_value("Mon, 01 Jan 2024 12:00:00 UTC"), "2024-01-01")

        # Standard formats
        self.assertEqual(parse_document_date_value("2022-04-15"), "2022-04-15")
        self.assertEqual(parse_document_date_value("12/31/2020"), "2020-12-31")

        # Invalid formats
        self.assertEqual(parse_document_date_value("not-a-date"), "")

    def test_parse_document_date(self):
        meta = {
            "ModDate": "D:20230612143000Z",
            "CreationDate": "20210825",
            "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"
        }
        # ModDate is prioritized because it is in the list of keys
        self.assertEqual(parse_document_date(meta), "2023-06-12")

        meta2 = {
            "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"
        }
        self.assertEqual(parse_document_date(meta2), "2015-10-21")

    def test_parse_document_year(self):
        # 1. Direct year
        meta = {"document_year": 2024}
        self.assertEqual(parse_document_year(meta), 2024)

        # 2. From parsed document_date
        meta_date = {"document_date": "2023-06-12"}
        self.assertEqual(parse_document_year(meta_date), 2023)

        # 3. From ModDate
        meta_mod = {"ModDate": "D:20220612143000Z"}
        self.assertEqual(parse_document_year(meta_mod), 2022)

        # 4. From CreationDate
        meta_create = {"CreationDate": "20200825"}
        self.assertEqual(parse_document_year(meta_create), 2020)

        # 5. From Last-Modified HTTP header
        meta_header = {"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"}
        self.assertEqual(parse_document_year(meta_header), 2015)


if __name__ == "__main__":
    unittest.main()
