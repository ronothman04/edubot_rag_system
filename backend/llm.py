from __future__ import annotations
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

# Gemini Direct Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "700"))
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", os.getenv("OLLAMA_TIMEOUT", "60")))

# Optional OpenRouter settings. Keep LLM_PROVIDER set to "groq" unless using OpenRouter.
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "700"))
OPENROUTER_TIMEOUT = int(os.getenv("OPENROUTER_TIMEOUT", os.getenv("OLLAMA_TIMEOUT", "60")))

# Anthropic Direct Settings
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))
ANTHROPIC_TIMEOUT = int(os.getenv("ANTHROPIC_TIMEOUT", os.getenv("OLLAMA_TIMEOUT", "60")))

if LLM_PROVIDER == "groq":
    ACTIVE_MODEL = GROQ_MODEL
elif LLM_PROVIDER == "openrouter":
    ACTIVE_MODEL = OPENROUTER_MODEL
elif LLM_PROVIDER == "gemini":
    ACTIVE_MODEL = GEMINI_MODEL
elif LLM_PROVIDER == "anthropic":
    ACTIVE_MODEL = ANTHROPIC_MODEL
else:
    ACTIVE_MODEL = OLLAMA_MODEL

print(f"[EduBot] LLM provider: {LLM_PROVIDER}")
print(f"[EduBot] LLM model   : {ACTIVE_MODEL}")


def _clamp_temperature(temperature: float | None) -> float:
    if temperature is None:
        return 0.0

    return max(0.0, min(float(temperature), 1.0))


def _messages(user_prompt: str, system_prompt: str | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": user_prompt})
    return messages


import time

def call_llm_with_retry(call_fn, *args, **kwargs):
    """
    Wraps any LLM API call with exponential backoff on rate-limit (429) and server (5xx) errors.
    """
    import random
    try:
        from rag.config import MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY
    except ImportError:
        MAX_RETRIES = 3
        RETRY_BASE_DELAY = 2.0
        RETRY_MAX_DELAY = 16.0

    delay = RETRY_BASE_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call_fn(*args, **kwargs)
        except Exception as e:
            err = str(e).lower()
            status_code = None
            if hasattr(e, "response") and e.response is not None:
                status_code = getattr(e.response, "status_code", None)
            
            is_rate_limit = "429" in err or "rate limit" in err or "too many requests" in err or status_code == 429
            is_5xx = any(f"{code}" in err for code in [500, 502, 503, 504]) or (status_code is not None and 500 <= status_code < 600)
            is_last_attempt = attempt == MAX_RETRIES

            should_retry = is_rate_limit or is_5xx

            if should_retry:
                error_type = "Rate limit" if is_rate_limit else "Server error"
                print(f"[LLM] Limit/Error reached: {error_type} hit (attempt {attempt}/{MAX_RETRIES}). Error: {e}")

            if should_retry and not is_last_attempt:
                # Respect Retry-After header if present
                retry_after_val = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            # Add a very small jitter to Retry-After just to spread out thundering herds
                            retry_after_val = float(retry_after) + random.uniform(0.1, 1.0)
                        except ValueError:
                            pass
                
                if retry_after_val is not None:
                    wait = retry_after_val
                    print(f"[LLM] Respecting Retry-After header. Waiting {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                else:
                    # Exponential backoff with randomized jitter
                    jitter = random.uniform(0.0, 5.0)
                    wait = min(delay, RETRY_MAX_DELAY) + jitter
                    print(f"[LLM] Retrying in {wait:.1f}s (backoff={delay:.1f}s, jitter={jitter:.1f}s, attempt {attempt}/{MAX_RETRIES})")
                    delay *= 2

                time.sleep(wait)
            else:
                raise

def generate(
    user_prompt: str,
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> str:
    final_temperature = _clamp_temperature(temperature)

    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("Groq API key is missing. Set GROQ_API_KEY in backend/.env.")

        try:
            def _groq_call():
                resp = requests.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": GROQ_MODEL,
                        "messages": _messages(user_prompt, system_prompt),
                        "temperature": final_temperature,
                        "max_tokens": GROQ_MAX_TOKENS,
                    },
                    timeout=GROQ_TIMEOUT,
                )
                resp.raise_for_status()
                return resp

            response = call_llm_with_retry(_groq_call)
        except requests.RequestException as exc:
            print(
                "[EduBot] Groq request failed. Check GROQ_API_KEY "
                f"and model {GROQ_MODEL}. Error: {exc}"
            )
            raise RuntimeError("Groq LLM request failed.") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""

        if choices and choices[0].get("finish_reason") == "length":
            print("[EduBot] Warning: Groq LLM generation reached output token limit (finish_reason: length)")

        message = choices[0].get("message") or {}
        return message.get("content") or ""

    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing in backend/.env")

        # Simple direct API call to Gemini (v1beta)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instruction: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow those instructions precisely."}]})

        contents.append({"role": "user", "parts": [{"text": user_prompt}]})

        try:
            def _gemini_call():
                resp = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": contents,
                        "generationConfig": {
                            "temperature": final_temperature,
                            "maxOutputTokens": OPENROUTER_MAX_TOKENS,
                        }
                    },
                    timeout=OPENROUTER_TIMEOUT
                )
                resp.raise_for_status()
                return resp

            response = call_llm_with_retry(_gemini_call)
            data = response.json()
            try:
                candidate = data['candidates'][0]
                finish_reason = candidate.get('finishReason')
                if finish_reason and finish_reason != "STOP":
                    print(f"[EduBot] Warning: Gemini generation reached limit/stopped early (finishReason: {finish_reason})")
            except (KeyError, IndexError):
                pass
            return data['candidates'][0]['content']['parts'][0]['text']
        except (requests.RequestException, KeyError, IndexError) as exc:
            print(f"[EduBot] Gemini API failed: {exc}")
            if LLM_PROVIDER == "gemini":
                 raise RuntimeError("Gemini direct LLM request failed.") from exc
            # Fallback happens if we return empty/raise further
            return ""

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("Anthropic API key is missing. Set ANTHROPIC_API_KEY in backend/.env.")

        try:
            def _anthropic_call():
                payload = {
                    "model": ANTHROPIC_MODEL,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": final_temperature,
                    "max_tokens": ANTHROPIC_MAX_TOKENS,
                }
                if system_prompt:
                    payload["system"] = system_prompt

                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=ANTHROPIC_TIMEOUT,
                )
                resp.raise_for_status()
                return resp

            response = call_llm_with_retry(_anthropic_call)
        except requests.RequestException as exc:
            print(
                "[EduBot] Anthropic request failed. Check ANTHROPIC_API_KEY "
                f"and model {ANTHROPIC_MODEL}. Error: {exc}"
            )
            raise RuntimeError("Anthropic LLM request failed.") from exc

        data = response.json()
        content_list = data.get("content") or []
        if not content_list:
            return ""

        text_parts = [block.get("text", "") for block in content_list if block.get("type") == "text"]
        return "".join(text_parts)

    if LLM_PROVIDER == "openrouter":
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OpenRouter API key is missing. Set OPENROUTER_API_KEY in backend/.env.")

        try:
            def _openrouter_call():
                resp = requests.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:5173",
                        "X-Title": "EduBot",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": _messages(user_prompt, system_prompt),
                        "temperature": final_temperature,
                        "max_tokens": OPENROUTER_MAX_TOKENS,
                    },
                    timeout=OPENROUTER_TIMEOUT,
                )
                resp.raise_for_status()
                return resp

            response = call_llm_with_retry(_openrouter_call)
        except requests.RequestException as exc:
            print(
                "[EduBot] OpenRouter request failed. Check OPENROUTER_API_KEY "
                f"and model {OPENROUTER_MODEL}. Error: {exc}"
            )
            raise RuntimeError("OpenRouter LLM request failed.") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""

        if choices and choices[0].get("finish_reason") == "length":
            print("[EduBot] Warning: OpenRouter LLM generation reached output token limit (finish_reason: length)")

        message = choices[0].get("message") or {}
        return message.get("content") or ""

    try:
        def _ollama_call():
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": _messages(user_prompt, system_prompt),
                    "stream": False,
                    "options": {
                        "temperature": final_temperature,
                        "num_ctx": OLLAMA_NUM_CTX,
                        "repeat_penalty": 1.1,
                    },
                },
                timeout=OLLAMA_TIMEOUT,
            )
            resp.raise_for_status()
            return resp

        response = call_llm_with_retry(_ollama_call)
    except requests.RequestException as exc:
        print(
            "[EduBot] Ollama request failed. Is Ollama running at "
            f"{OLLAMA_BASE_URL} with model {OLLAMA_MODEL}? Error: {exc}"
        )
        raise RuntimeError("Ollama local LLM request failed.") from exc

    data = response.json()
    message = data.get("message") or {}
    return message.get("content") or data.get("response") or ""
