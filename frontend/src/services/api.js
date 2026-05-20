const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function sendMessage(query, history) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000); // 120s timeout for LLM

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
      throw new Error("The request timed out. The AI may be processing a large response — please try again.");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}
