import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")

client = Groq(api_key=GROQ_API_KEY)


def generate(user_prompt: str, system_prompt: str | None = None, temperature: float | None = None) -> str:
    """Send a prompt to Groq LLM with proper system/user message separation."""

    messages = []

    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt,
        })

    messages.append({
        "role": "user",
        "content": user_prompt,
    })

    final_temperature = 0.1 if temperature is None else max(0, min(float(temperature), 1))

    chat_completion = client.chat.completions.create(
        messages=messages,
        model=GROQ_MODEL,
        temperature=final_temperature,
        max_completion_tokens=1200,
    )

    return chat_completion.choices[0].message.content or ""