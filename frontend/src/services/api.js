const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function sendMessage(query, history, { signal } = {}) {
  // Internal controller drives the actual fetch. It can be aborted by either the
  // request timeout OR an external caller-supplied signal (e.g. a Stop button).
  const controller = new AbortController();
  let timedOut = false;

  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 120000); // 120s timeout for LLM

  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", onExternalAbort);
    }
  }

  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, history }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Request failed (${response.status})`);
    }

    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      // Timeout aborts surface a friendly message; user-initiated aborts are
      // re-thrown unchanged so the caller can detect and silently ignore them.
      if (timedOut) {
        throw new Error(
          "The request timed out. The AI may be processing a large response — please try again.",
          { cause: error },
        );
      }
      throw error;
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
    if (signal) signal.removeEventListener("abort", onExternalAbort);
  }
}
