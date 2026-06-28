import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from crawl4ai_crawler import should_skip_url

def test_should_skip_url():
    # Test cases that should be skipped
    assert should_skip_url("https://college.edu/gallery") is True
    assert should_skip_url("https://college.edu/galleries/campus") is True
    assert should_skip_url("https://college.edu/photo") is True
    assert should_skip_url("https://college.edu/faculty-profile/john-doe") is True
    assert should_skip_url("https://college.edu/staff-profiles") is True
    assert should_skip_url("https://college.edu/alumni/directory") is True
    assert should_skip_url("https://college.edu/events/past-events") is True

    # Test cases that should NOT be skipped (Keep patterns)
    assert should_skip_url("https://college.edu/admissions") is False
    assert should_skip_url("https://college.edu/admission/fees") is False
    assert should_skip_url("https://college.edu/notice/exam-schedule") is False
    assert should_skip_url("https://college.edu/academics/departments") is False
    assert should_skip_url("https://college.edu/exam/results") is False
    assert should_skip_url("https://college.edu/news/announcement") is False

    # Mixed cases (Both skip and keep pattern present - keep pattern should override)
    assert should_skip_url("https://college.edu/academics/faculty-profiles") is False  # contains academics (keep) and faculty-profiles (skip)
    assert should_skip_url("https://college.edu/notices/past-events") is False  # contains notices (keep) and past-events (skip)
    assert should_skip_url("https://college.edu/admissions/gallery") is False  # contains admissions (keep) and gallery (skip)

    print("✓ URL filtering tests passed successfully!")

if __name__ == "__main__":
    test_should_skip_url()
