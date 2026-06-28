import sys
import os
import re

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from rag.text_utils import ABBREVIATION_MAP
from rag.intent import COURSE_ALIASES, PROGRAMME_SYNONYMS

query = "who is the faculty of BBA"
q_lower = query.lower()
words = re.findall(r"\b\w+\b", q_lower)

print("words:", words)
print("bba in words:", "bba" in words)
print("bba in COURSE_ALIASES:", "bba" in COURSE_ALIASES)
print("ABBREVIATION_MAP keys:", list(ABBREVIATION_MAP.keys()))
