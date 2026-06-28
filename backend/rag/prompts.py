"""
rag/prompts.py
System and user prompt templates for St. Anthony's College EduBot.
Aligned with specification §4 — Generation Prompt Template.

The system-message content now lives in rag/config.py as EDUBOT_ANSWER_SYSTEM_PROMPT.
LLM_SYSTEM is kept as the public symbol (imported by main.py and responses.py) and
simply points at that constant — no call-site changes required.
"""

from .config import EDUBOT_ANSWER_SYSTEM_PROMPT

LLM_SYSTEM = EDUBOT_ANSWER_SYSTEM_PROMPT

USER_PROMPT_TEMPLATE = """\
Question: {query}

Context:
---
{context}
---
"""
