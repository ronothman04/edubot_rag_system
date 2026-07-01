"""
rag/config.py
Configuration constants and tuning values for EduBot RAG pipeline.
"""

import os

# Response messages
# NOTE: NOT_FOUND_MESSAGE does double duty — it is shown to users in deterministic
# short-circuit paths AND used as an exact-match sentinel (the LLM is instructed to
# reply with it verbatim, and main.py compares against it to route to the smart
# fallback). Keep it polite but concise so the model can reproduce it reliably.
NOT_FOUND_MESSAGE = (
    "I couldn't find this information in the available college resources. "
    "Please feel free to rephrase your question, or ask me about admissions, "
    "programmes, eligibility, departments, or campus facilities."
)

CLARIFICATION_MESSAGE = (
    "I'd be glad to help — I just need a little more detail to answer accurately "
    "from the available college resources.\n\n"
    "Could you mention the course or programme, your previous stream/course, your "
    "board or university, your marks/percentage, or your category if relevant?"
)

OUT_OF_SCOPE_MESSAGE = (
    "I'm here to help specifically with information about St. Anthony's College. "
    "I'd be happy to assist with questions on admissions, courses, fees, documents, "
    "hostel, attendance, examination rules, clubs, departments, faculty, or how to "
    "contact the college."
)

HOMEWORK_REFUSAL_MESSAGE = (
    "I'm not able to help with assignments or homework, but I'd be glad to assist "
    "you with anything about St. Anthony's College — such as admissions, programmes, "
    "eligibility, fees, or campus facilities."
)

# Programme availability (anti-hallucination). Shown when a user asks about a
# specific degree programme that does not appear in the retrieved college resources.
# {programme} is substituted with a human-friendly programme name (e.g. "B.Tech").
PROGRAMME_NOT_FOUND_MESSAGE = (
    "I couldn't find {programme} among the programmes listed in the available "
    "college resources, so it may not be offered here. I'd be happy to share the "
    "list of programmes the college does offer if that would help."
)

# Used when the user explicitly asks whether a programme is available/offered.
PROGRAMME_NOT_AVAILABLE_MESSAGE = (
    "Based on the available college resources, {programme} doesn't appear among the "
    "programmes offered by the college. I'd be glad to show you the programmes that "
    "are available so you can explore your options."
)

# Used when the user asks about admission/eligibility for an unverifiable programme.
PROGRAMME_ADMISSION_UNVERIFIED_SUFFIX = (
    " Because of that, I can't confirm any admission requirements for it from the "
    "available college resources."
)

# Follow-up prompts surfaced to the user when a programme cannot be verified (§ better UX).
PROGRAMME_FOLLOWUP_SUGGESTIONS = [
    "What undergraduate programmes are available?",
    "Show all science courses.",
    "Show all commerce courses.",
    "List all programmes offered by the college.",
]

# =============================================================================
# LLM ANSWER SYSTEM PROMPT
# =============================================================================
# Persona + grounding + structure prompt for the single answer-generation LLM call.
# Imported by rag/prompts.py as LLM_SYSTEM (the symbol name is preserved for all
# existing call-sites). The exact fallback phrase is embedded from NOT_FOUND_MESSAGE
# so the model's "reply exactly" sentinel always matches main.py's equality check.
EDUBOT_ANSWER_SYSTEM_PROMPT = f"""\
You are EduBot, the admission assistant for St. Anthony's College, Shillong.
Speak like a knowledgeable, approachable admission officer: warm, professional, and
friendly-but-formal. Be helpful and encouraging, never robotic or curt.

### GROUNDING (most important)
- Answer ONLY using the information in the CONTEXT provided with each question.
- Never invent or guess programmes, fees, dates, eligibility, requirements, names,
  designations, or procedures. If something is not in the CONTEXT, do not state it.
- Never mention internal system details to the user — chunks, embeddings,
  retrieval, "the context", or filenames/extensions (e.g. "Prospectus2026.pdf").
- If the CONTEXT does not contain the answer, do not improvise. Reply with exactly:
  "{NOT_FOUND_MESSAGE}"
- Do NOT introduce an acronym, abbreviation, or short form that is not written in
  the CONTEXT, and do NOT coin a new short form for an expanded phrase. If the
  CONTEXT shows only a long name, use the long name; if it shows only a short
  code/acronym, keep it as written. Never substitute a different abbreviation that
  merely looks similar.

### TABLES & INCOMPLETE STRUCTURED DATA
- Only present a Markdown table when the CONTEXT clearly contains complete, aligned
  rows that share the same columns. Do NOT build a table from rows that have empty
  cells, missing headers, placeholder headers, or values that are obviously
  misaligned or merged.
- When the CONTEXT marks extracted figures as incomplete or not cleanly parsed,
  report only the values that are clearly stated, in plain prose or a short list,
  and say plainly that some details are not available in the resources. Never fill
  a blank cell with a dash, a guess, or a value carried over from another row, and
  never split or regroup merged numbers to fabricate a column.

### SOURCES
- Do not include inline citations, document names, page numbers, source labels,
  URLs, or parenthetical references inside the body of your answer.
- At the very end of your response, on a new line, write the Source IDs you used in the format: Citations: [id1, id2, ...] (e.g., Citations: [1, 3]). Cite only the source IDs (using the ID from '[Source ID]') that directly support your answer.
- Continue grounding every factual statement in the supplied CONTEXT, but write
  the answer as clean prose without phrases such as "according to the handbook"
  or references such as "(College Handbook 2023-24, p. 48)".

### ACCURACY
- Quote figures, amounts, subject/course codes (e.g. MCA-CC-6000), names, designations,
  and dates exactly as they appear in the CONTEXT. Never alter, round, or approximate them.
- When the same person appears in abbreviated and full forms, use the fullest exact
  name and credentials supported by the current sources.
- You may use your own words for explanations and connecting text, but every name,
  code, date, and number must match the source exactly.

### PROGRAMMES
- Only discuss programmes that appear in the CONTEXT.
- If asked about a programme that is not present in the CONTEXT, politely explain that
  you can't verify it among the programmes in the available college resources, and offer
  to share the list of programmes the college does offer. Never fabricate admission
  details, eligibility, or fees for an unverified programme.
- Be extremely careful not to confuse Undergraduate (UG) and Postgraduate (PG) courses. Do not list a subject as a Postgraduate (PG) course (such as M.A. English) unless the context explicitly and specifically refers to it as a Postgraduate/Master course. Do not assume a Postgraduate (PG) version of a subject is offered simply because an Undergraduate (UG) version exists.

### AUTHORITY & CONFLICTS
- The CONTEXT sources are not equal in authority. When sources disagree on the
  same fact, prefer them in this order of authority:
  1. Prospectus (admissions, eligibility, programmes, courses, fees)
  2. College Handbook (academic rules, attendance, conduct, exams, scholarships,
     library, committees, regulations)
  3. Hostel Prospectus (hostel admission, fees, facilities, rules)
  4. Official notices and circulars
  5. Older or general documents
- Never merge conflicting values into one figure. If a newer official version
  supersedes an older one, use the latest; otherwise prefer the higher-authority
  source above. If genuine ambiguity remains, say the available resources contain
  differing information and cite both.
- Within the same authority tier, prefer the newest using document_year, then
  document_date, then crawl_timestamp.
- For a current/present role-holder question, explicit current-tenure evidence
  (for example, "2024–Present" or a newer "took over as Principal" statement)
  overrides an older handbook or committee table naming the previous holder.

### STYLE & STRUCTURE
- Lead with a direct answer to the question, then add the relevant supporting details,
  then close with a brief, helpful next step or an offer to help further.
- Be concise but complete — usually 3 to 6 sentences. Avoid abrupt one-line replies.
- Use short paragraphs, and bullet points for lists, so answers are easy to read.
- Maintain a courteous, welcoming tone throughout.
"""

# RAG tuning
RAG_MODE                 = "local"
RETRIEVAL_CANDIDATES     = 30       # §7: Vector candidates
KEYWORD_CANDIDATES       = 50       # §7: BM25 candidates
DEFAULT_TOP_K            = 5        # §7: Final context chunks
RERANK_TOP_N             = 10       # §7: Rerank top-N
MAX_CONTEXT_CHARS        = 8000     # §7: Max context chars
LIST_QUERY_CONTEXT_CHARS = 8000     # §7: Same limit for list queries
# Fee-structure queries must surface the WHOLE table (Common Fees + Software +
# Professional + Laboratory + Refundable + One-Time fees), which spans several
# consecutive prospectus pages (~8.5K chars) and competes with hostel/admission
# fee chunks. The default 8K budget truncates the later sections, so give these
# queries a wider window so no fee section is dropped mid-answer.
FEE_TABLE_CONTEXT_CHARS  = 18000    # §7: Wider budget for full fee structure
MAX_CHARS_PER_CHUNK      = 1500     # §5: Chunk size upper bound
MAX_CHARS_PER_LIST_CHUNK = 1500     # §5: Consistent chunk sizing
MAX_RELATED_CHUNKS       = 10
MIN_CHUNK_WORDS          = 6
MAX_DISTANCE             = 0.72
CONFIDENCE_THRESHOLD     = 0.25     # §7/§8: Below this → skip LLM
CHUNK_MARGIN_FACTOR      = 1.5      # Exceed limit by this factor to keep tables/lists intact
CHUNK_OVERLAP            = 150      # Default character overlap between adjacent chunks

# Phase 2 additions
METADATA_BOOST           = 0.15
MIN_RERANKER_SCORE       = 0.1
DEBUG                    = False
RERANKER_INPUT_K         = 10
RERANKER_OUTPUT_K        = 4


# Rate limiting (§9)
LLM_PROVIDER             = "groq"
MAX_RETRIES              = 1        # §9: Do NOT retry immediately on 429
RETRY_BASE_DELAY         = 20.0     # §9: Wait 20-30 seconds
RETRY_MAX_DELAY          = 30.0
REQUEST_TIMEOUT          = 60.0

# Feature flags
QUERY_EXPANSION_ENABLED  = False    # §2 Rule 2: No LLM query expansion unless True
DISABLE_SUGGESTED_QUESTIONS = True


# Cache TTLs (§8)
RESPONSE_CACHE_TTL       = 86400    # §8 Layer 1: 24 hours
RETRIEVAL_CACHE_TTL      = 3600     # §8 Layer 2: 1 hour

# Debug flags
PRINT_FINAL_CONTEXT      = False
DEBUG_RAG                = os.getenv("DEBUG_RAG", "false").lower() == "true"

# Misc
WEBSITE_FILE_TYPES       = {"website", "website_pdf", "website_document", "website_pdf_link", "website_links"}
KNOWN_DEPARTMENT_NAMES   = [
    "biochemistry", "biotechnology", "botany", "business administration", "chemistry",
    "commerce", "computer science", "economics", "education", "english",
    "environmental studies", "fishery science", "geology", "hindi", "history",
    "khasi", "mass media", "mathematics", "mizo", "music", "philosophy",
    "physics", "political science", "statistics", "value education", "zoology", "hospitality",
]

DEFAULT_SUGGESTED_QUESTIONS = [
    "What departments are available?",
    "What undergraduate degree programs are offered by the college?",
    "What postgraduate courses are available?",
]
