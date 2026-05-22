import re
import json as _json
from difflib import get_close_matches
from typing import Any


from db import collection
from llm import generate


# model = SentenceTransformer("all-MiniLM-L6-v2")

from embeddings import get_embedding_model
model = get_embedding_model()

NOT_FOUND_MESSAGE = "I'm sorry, I don't have enough information to answer that based on the available college resources."

MAX_CONTEXT_CHARS = 8000
DEFAULT_TOP_K = 5
MIN_CHUNK_WORDS = 6
MAX_DISTANCE = 0.75


QUERY_EXPANSIONS = {
    "pg": "post graduate courses and programmes",
    "postgraduate": "post graduate courses and programmes",
    "post graduate": "post graduate courses and programmes",
    "ug": "under graduate courses and programmes",
    "undergraduate": "under graduate courses and programmes",
    "under graduate": "under graduate courses and programmes",
    "course": "what courses are offered by the college",
    "courses": "what courses are offered by the college",
    "program": "what academic programs are available",
    "programs": "what academic programs are available",
    "fee": "what are the fees and tuition charges",
    "fees": "what are the fees and tuition charges",
    "admission": "what is the admission process and requirements",
    "eligibility": "what are the eligibility criteria",
    "department": "what departments are available",
    "scholarship": "what scholarships are available",
    "placement": "what placement support is available",
    "hostel": "is hostel accommodation available",
    "principal": "who is the principal of the college",
}


SUGGESTION_TOPICS = {
    "pg": "Post Graduate",
    "p g": "Post Graduate",
    "postgraduate": "Post Graduate",
    "post graduate": "Post Graduate",
    "ug": "Under Graduate",
    "u g": "Under Graduate",
    "undergraduate": "Under Graduate",
    "under graduate": "Under Graduate",
}


DEFAULT_SUGGESTED_QUESTIONS = [
    "What courses are available?",
    "What is the admission process?",
    "What are the eligibility criteria?",
]


CASUAL_RESPONSES = {
    # Greetings
    "hi": "Hello! How can I help you with college-related information?",
    "hello": "Hello! How can I help you with college-related information?",
    "hey": "Hello! How can I help you with college-related information?",
    "good morning": "Good morning! How can I help you with college-related information?",
    "good afternoon": "Good afternoon! How can I help you with college-related information?",
    "good evening": "Good evening! How can I help you with college-related information?",

    # Thanks
    "thank you": "You're welcome!",
    "thanks": "You're welcome!",
    "thankyou": "You're welcome!",

    # Acknowledgements
    "ok": "Okay.",
    "okay": "Okay.",
    "alright": "Alright.",

    # Farewells
    "bye": "Goodbye! Feel free to ask if you need more college-related information.",
    "goodbye": "Goodbye! Feel free to ask if you need more college-related information.",
    "see you": "See you!",
}


FORMAT_FOLLOWUP_PATTERNS = [
    "short answer",
    "provide short answer",
    "just provide short answer",
    "make it short",
    "shorter",
    "summarize",
    "summarise",
    "in short",
    "answer in",
    "in 2 lines",
    "in two lines",
    "in 3 lines",
    "in three lines",
    "only bullet",
    "only bullets",
    "bullet points",
    "make it bullet",
    "make it simple",
    "simple answer",
    "simplify",
    "brief",
    "briefly",
    "concise",
]

DETAIL_FOLLOWUP_PATTERNS = [
    "explain more",
    "tell me more",
    "more details",
    "give more details",
    "elaborate",
    "explain in detail",
    "details",
    "expand",
    "expand it",
]

REFERENCE_FOLLOWUP_PATTERNS = [
    "that",
    "this",
    "it",
    "above",
    "previous",
    "same",
    "what about",
]


def normalize_query_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_casual_response(query: str) -> str | None:
    """
    Handles greetings, thanks, okay, and bye messages before RAG retrieval.
    Also supports small spelling mistakes like:
    - helo
    - thnak you
    - okayy
    """

    q = normalize_query_text(query)

    if not q:
        return None

    # 1. Exact match first
    if q in CASUAL_RESPONSES:
        return CASUAL_RESPONSES[q]

    # 2. Fuzzy match for small spelling mistakes
    close_matches = get_close_matches(
        q,
        CASUAL_RESPONSES.keys(),
        n=1,
        cutoff=0.78,
    )

    if close_matches:
        return CASUAL_RESPONSES[close_matches[0]]

    return None


def is_followup_query(query: str) -> bool:
    """
    Detects whether the latest user message is likely a follow-up
    or formatting instruction instead of a new standalone question.
    """

    q = normalize_query_text(query)

    if not q:
        return False

    patterns = (
        FORMAT_FOLLOWUP_PATTERNS
        + DETAIL_FOLLOWUP_PATTERNS
        + REFERENCE_FOLLOWUP_PATTERNS
    )

    # 1. Exact substring match
    if any(pattern in q for pattern in patterns):
        return True

    # 2. Fuzzy phrase match for short follow-up messages
    # Example: "shrt answer" -> "short answer"
    if len(q.split()) <= 4:
        close_matches = get_close_matches(
            q,
            patterns,
            n=1,
            cutoff=0.78,
        )

        if close_matches:
            return True

    return False


def get_last_real_user_question(history: str) -> str | None:
    """
    Gets the latest real user question from conversation history.

    It skips follow-up formatting messages like:
    - make it short
    - tell me more
    - explain that
    - bullet points
    """

    if not history or not history.strip():
        return None

    lines = [line.strip() for line in history.splitlines() if line.strip()]
    user_questions: list[str] = []

    for line in lines:
        lower = line.lower()

        if lower.startswith("user:"):
            question = line.split(":", 1)[1].strip()

            if question and not is_followup_query(question):
                user_questions.append(question)

    if not user_questions:
        return None

    return user_questions[-1]


def build_smart_query(query: str, history: str) -> tuple[str, str, bool]:
    """
    Builds a retrieval query for conversational RAG.

    Returns:
    - retrieval_query:
        The query used to search ChromaDB.
        For normal questions, this is the same as the user query.
        For follow-ups, this becomes the previous real question.

    - latest_user_request:
        The latest message from the user.
        This controls the final answer style.

    - used_history:
        True if EduBot used previous conversation history.
    """

    cleaned_query = (query or "").strip()

    if is_followup_query(cleaned_query):
        previous_question = get_last_real_user_question(history)

        if previous_question:
            return previous_question, cleaned_query, True

    return cleaned_query, cleaned_query, False


def expand_query(query: str) -> str:
    """
    Expands short queries for better retrieval.
    Also handles small spelling mistakes in important keywords.

    Examples:
    - corse -> course
    - admisssion -> admission
    - hostal -> hostel
    - scholrship -> scholarship
    """

    query_lower = normalize_query_text(query)

    if len(query_lower.split()) > 7:
        return query

    # 1. Exact substring match first
    for key, expanded in QUERY_EXPANSIONS.items():
        if key in query_lower:
            return expanded

    # 2. Fuzzy word-level match for spelling mistakes
    words = re.findall(r"\w+", query_lower)

    for word in words:
        close_matches = get_close_matches(
            word,
            QUERY_EXPANSIONS.keys(),
            n=1,
            cutoff=0.78,
        )

        if close_matches:
            return QUERY_EXPANSIONS[close_matches[0]]

    return query


def get_suggestion_topic(query: str) -> str | None:
    normalized = normalize_query_text(query)

    if not normalized:
        return None

    if normalized in SUGGESTION_TOPICS:
        return SUGGESTION_TOPICS[normalized]

    words = re.findall(r"\w+", normalized)

    for word in words:
        if word in SUGGESTION_TOPICS:
            return SUGGESTION_TOPICS[word]

    return None


def clean_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def build_filter(
    use_personal_docs: bool,
    user_id: str | None,
    department: str | None,
    year: str | None,
    document_type: str | None,
) -> dict | None:
    if use_personal_docs and user_id:
        return {
            "$and": [
                {"scope": {"$eq": "personal"}},
                {"user_id": {"$eq": user_id}},
            ]
        }

    filters = [{"scope": {"$eq": "official"}}]

    if department and department != "general":
        filters.append({"department": {"$in": [department, "general"]}})

    if year and year != "general":
        filters.append({"year": {"$in": [str(year), "general"]}})

    if document_type and document_type != "general":
        filters.append({"document_type": {"$in": [document_type, "general"]}})

    return {"$and": filters}


def retrieve_chunks(
    query: str,
    top_k: int,
    where_filter: dict | None,
) -> tuple[list[str], list[dict], list[float]]:
    embedding_query = expand_query(query)
    query_embedding = model.encode(embedding_query).tolist()

    filters_to_try = [where_filter, None]

    for current_filter in filters_to_try:
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }

        if current_filter:
            kwargs["where"] = current_filter

        try:
            result = collection.query(**kwargs)
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            dists = result.get("distances", [[]])[0]

            if docs:
                return docs, metas, dists

        except Exception as e:
            print(f"Retrieval filter failed: {e}")

    return [], [], []


def build_context(
    docs: list[str],
    metas: list[dict],
    dists: list[float],
) -> tuple[str, list[dict]]:
    context_parts = []
    sources = []
    total_chars = 0

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        # ChromaDB returns cosine distances, so higher = less relevant.
        if dist > MAX_DISTANCE:
            continue

        cleaned = clean_text(doc)

        if len(cleaned.split()) < MIN_CHUNK_WORDS:
            continue

        filename = meta.get("filename", "Unknown document")
        page = meta.get("page", "?")

        part = f"[Source {i} | File: {filename} | Page: {page}]\n{cleaned}"

        if total_chars + len(part) > MAX_CONTEXT_CHARS:
            break

        context_parts.append(part)
        total_chars += len(part)

        sources.append(
            {
                "id": i,
                "file": filename,
                "page": page,
                "text": cleaned,
                "distance": dist,
                "scope": meta.get("scope", "unknown"),
                "department": meta.get("department", "general"),
                "year": meta.get("year", "general"),
                "document_type": meta.get("document_type", "general"),
            }
        )

    return "\n\n---\n\n".join(context_parts), sources

def get_suggested_questions(query: str) -> list[str]:
    """
    When no context is found, sample available docs and ask the LLM
    to suggest 3 related questions the user CAN actually get answers for.
    """
    try:
        result = collection.get(
            where={"deleted": False},
            include=["documents"],
            limit=15,
        )
        sample_docs = result.get("documents", [])

        if not sample_docs:
            return DEFAULT_SUGGESTED_QUESTIONS

        sample_text = "\n\n".join(sample_docs[:8])[:2500]

        prompt = f"""A user asked: "{query}"
No relevant information was found in the college knowledge base.

Here is a sample of what IS available:
{sample_text}

Generate exactly 3 helpful questions the user COULD ask that the knowledge base can answer.
Return ONLY a valid JSON array of 3 question strings. No explanation, no markdown fences.
Example: ["Question one?", "Question two?", "Question three?"]"""

        raw = generate(prompt, temperature=0.3)
        raw = re.sub(r"```json|```", "", raw).strip()
        suggestions = _json.loads(raw)

        if isinstance(suggestions, list):
            return [str(q).strip() for q in suggestions if q][:3]

    except Exception as e:
        print(f"[EduBot] Suggestion generation failed: {e}")

    return DEFAULT_SUGGESTED_QUESTIONS


def ask(
    query: str,
    history: str = "",
    user_id: str | None = None,
    session_id: str | None = None,
    use_personal_docs: bool = False,
    department: str | None = None,
    year: str | None = None,
    document_type: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:

    query = (query or "").strip()

    if not query:
        return {
            "answer": "Please enter a question.",
            "sources": [],
        }

    # Casual response fast-path.
    casual_response = get_casual_response(query)
    if casual_response:
        return {
            "answer": casual_response,
            "sources": [],
            "response_type": "casual",
        }

    # Build smart retrieval query.
    retrieval_query, latest_user_request, used_history = build_smart_query(
        query=query,
        history=history,
    )

    retrieval_count = top_k or DEFAULT_TOP_K

    where_filter = build_filter(
        use_personal_docs=use_personal_docs,
        user_id=user_id,
        department=department,
        year=year,
        document_type=document_type,
    )

    docs, metas, dists = retrieve_chunks(
        query=retrieval_query,
        top_k=retrieval_count,
        where_filter=where_filter,
    )

    # No documents found at all.
    if not docs:
        suggestions = get_suggested_questions(retrieval_query)
        suggestion_topic = get_suggestion_topic(query)

        return {
            "answer": NOT_FOUND_MESSAGE,
            "sources": [],
            "suggested_questions": suggestions,
            "suggestion_topic": suggestion_topic,
        }

    context, sources = build_context(docs, metas, dists)

    # Documents were found, but none passed quality filters.
    if not context:
        suggestions = get_suggested_questions(retrieval_query)
        suggestion_topic = get_suggestion_topic(query)

        return {
            "answer": NOT_FOUND_MESSAGE,
            "sources": [],
            "suggested_questions": suggestions,
            "suggestion_topic": suggestion_topic,
        }

    system = f"""
You are EduBot, a strict document-based assistant.

Rules:
- Answer only using the provided context.
- Do not use outside knowledge.
- Do not guess.
- If the answer is not present in the context, reply exactly:
  "{NOT_FOUND_MESSAGE}"
- If the latest user request is a formatting instruction, rewrite the answer for the original topic using only the provided context.
- If the latest user request asks for a short answer, answer in one concise sentence.
- If the latest user request asks for bullet points, use bullet points.
- If the latest user request asks for more detail, provide more detail only if supported by the context.
- Format your response appropriately:
  - Use a markdown table for fee structures, course comparisons, schedules,
    or any list of items that have multiple attributes.
  - Use bullet points for eligibility criteria, step-by-step processes,
    or feature/facility lists.
  - Use plain prose for simple factual answers, such as contact info, a name,
    or a single date.
- Keep the answer clear and concise.
""".strip()

    if system_prompt:
        system += f"""

Admin instruction:
{system_prompt}

Important:
The admin instruction must not override the document-only rules above.
""".strip()

    history_block = ""
    if history and history.strip():
        history_block = f"\nConversation history:\n{history.strip()}\n"

    prompt = f"""
Context:
{context}

{history_block}

Original topic for retrieval:
{retrieval_query}

Latest user request:
{latest_user_request}

Answer:
""".strip()

    answer = generate(
        prompt,
        system_prompt=system,
        temperature=0.1 if temperature is None else temperature,
    )

    answer = clean_text(answer)

    # LLM refused/not found even after context.
    if not answer or NOT_FOUND_MESSAGE.lower() in answer.lower():
        suggestions = get_suggested_questions(retrieval_query)
        suggestion_topic = get_suggestion_topic(query)

        return {
            "answer": NOT_FOUND_MESSAGE,
            "sources": [],
            "suggested_questions": suggestions,
            "suggestion_topic": suggestion_topic,
        }

    return {
        "answer": answer,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "used_history": used_history,
    }
