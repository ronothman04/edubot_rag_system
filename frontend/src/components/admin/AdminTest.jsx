import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  Download,
  FileText,
  Link,
  Send,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DEFAULT_SYSTEM_PROMPT =
  "You are an academic advisor bot. Only use the provided documents to answer questions. If the answer isn't in the context, state that you don't know.";

function formatTime(value = new Date()) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function getDocumentName(doc) {
  if (typeof doc === "string") return doc;

  return doc?.filename || doc?.file || doc?.name || "Unknown document";
}

function getDocumentChunks(doc) {
  if (typeof doc === "string") return null;

  return doc?.chunks || doc?.chunk_count || doc?.total_chunks || null;
}

function getDocumentType(filename = "") {
  const extension = filename.split(".").pop()?.toLowerCase();

  if (extension === "pdf") {
    return {
      label: "PDF",
      tone: "bg-red-50 text-red-500 dark:bg-red-500/10 dark:text-red-300",
    };
  }

  if (["doc", "docx"].includes(extension)) {
    return {
      label: "DOC",
      tone: "bg-blue-50 text-blue-500 dark:bg-blue-500/10 dark:text-blue-300",
    };
  }

  if (["html", "htm"].includes(extension)) {
    return {
      label: "WEB",
      tone: "bg-amber-50 text-amber-500 dark:bg-amber-500/10 dark:text-amber-300",
    };
  }

  if (["txt", "md"].includes(extension)) {
    return {
      label: "TXT",
      tone: "bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-300",
    };
  }

  if (["csv", "xlsx", "xls"].includes(extension)) {
    return {
      label: "DATA",
      tone: "bg-purple-50 text-purple-500 dark:bg-purple-500/10 dark:text-purple-300",
    };
  }

  return {
    label: "DOC",
    tone: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300",
  };
}

function sourceLabel(source) {
  if (!source) return "Unknown source";

  const file = source.file || source.filename || "Unknown source";

  return source.page && source.page !== "?"
    ? `${file} (Page ${source.page})`
    : file;
}

function MarkdownMessage({ content, isUser }) {
  if (isUser) {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  return (
    <div className="space-y-4 text-base leading-8">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mt-2 text-2xl font-black leading-tight text-slate-950 dark:text-white">
              {children}
            </h1>
          ),

          h2: ({ children }) => (
            <h2 className="mt-5 text-xl font-black leading-tight text-slate-900 dark:text-white">
              {children}
            </h2>
          ),

          h3: ({ children }) => (
            <h3 className="mt-4 text-lg font-bold leading-tight text-slate-800 dark:text-slate-100">
              {children}
            </h3>
          ),

          p: ({ children }) => (
            <p className="my-3 leading-8 text-slate-700 dark:text-slate-200">
              {children}
            </p>
          ),

          strong: ({ children }) => (
            <strong className="font-black text-slate-950 dark:text-white">
              {children}
            </strong>
          ),

          em: ({ children }) => (
            <em className="italic text-slate-700 dark:text-slate-200">
              {children}
            </em>
          ),

          ul: ({ children }) => (
            <ul className="my-3 list-disc space-y-2 pl-6 text-slate-700 dark:text-slate-200">
              {children}
            </ul>
          ),

          ol: ({ children }) => (
            <ol className="my-3 list-decimal space-y-2 pl-6 text-slate-700 dark:text-slate-200">
              {children}
            </ol>
          ),

          li: ({ children }) => <li className="leading-7">{children}</li>,

          blockquote: ({ children }) => (
            <blockquote className="my-4 border-l-4 border-blue-400 bg-blue-50 px-4 py-3 italic text-slate-700 dark:bg-blue-500/10 dark:text-slate-200">
              {children}
            </blockquote>
          ),

          table: ({ children }) => (
            <div className="my-5 w-full overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
              <table className="w-full border-collapse text-left text-sm">
                {children}
              </table>
            </div>
          ),

          thead: ({ children }) => (
            <thead className="bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white">
              {children}
            </thead>
          ),

          tbody: ({ children }) => (
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {children}
            </tbody>
          ),

          tr: ({ children }) => (
            <tr className="even:bg-slate-50 dark:even:bg-slate-800/40">
              {children}
            </tr>
          ),

          th: ({ children }) => (
            <th className="border-r border-slate-200 px-4 py-3 font-black last:border-r-0 dark:border-slate-700">
              {children}
            </th>
          ),

          td: ({ children }) => (
            <td className="border-r border-slate-200 px-4 py-3 align-top last:border-r-0 dark:border-slate-700">
              {children}
            </td>
          ),

          code: ({ inline, children, ...props }) =>
            inline ? (
              <code
                className="rounded-md bg-slate-100 px-1.5 py-0.5 text-sm font-bold text-blue-700 dark:bg-slate-800 dark:text-blue-300"
                {...props}
              >
                {children}
              </code>
            ) : (
              <code
                className="block overflow-x-auto whitespace-pre rounded-xl bg-slate-950 p-4 text-sm leading-7 text-slate-100"
                {...props}
              >
                {children}
              </code>
            ),

          pre: ({ children }) => <pre className="my-4">{children}</pre>,

          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-bold text-blue-600 underline underline-offset-4 hover:text-blue-500"
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function AdminTest() {
  const [query, setQuery] = useState("");

  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I'm ready to test the RAG system. Ask me anything about the documents in your vector store.",
      time: formatTime(),
      sources: [],
    },
  ]);

  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT);
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);

  const [temperature, setTemperature] = useState(0.3);
  const [topK, setTopK] = useState(3);

  const latestAnswer = useMemo(
    () =>
      [...messages]
        .reverse()
        .find(
          (message) =>
            message.role === "assistant" && message.id !== "welcome",
        ),
    [messages],
  );

  const fetchDocuments = async () => {
    setDocumentsLoading(true);

    try {
      const res = await fetch(`${API_URL}/documents`);

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        throw new Error(data?.detail || "Failed to fetch documents");
      }

      setDocuments(data?.documents || []);
    } catch (error) {
      console.error("Failed to load active documents:", error);
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleTestQuery = async (e) => {
    e.preventDefault();

    const cleanQuery = query.trim();

    if (!cleanQuery || loading) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: cleanQuery,
      time: formatTime(),
      sources: [],
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuery("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          query: cleanQuery,
          question: cleanQuery,
          history: "",
          system_prompt: systemPrompt,
          temperature,
          top_k: topK,
        }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        throw new Error(data?.detail || "Query failed");
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: data?.answer || "No answer received.",
          time: formatTime(),
          sources: data?.sources || [],
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content: `Error: ${error.message}`,
          time: formatTime(),
          sources: [],
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content:
          "Hello! I'm ready to test the RAG system. Ask me anything about the documents in your vector store.",
        time: formatTime(),
        sources: [],
      },
    ]);
  };

  const exportResults = () => {
    const text = messages
      .map((message) => {
        const sender =
          message.role === "user" ? "You" : "EduBot Assistant";

        const sources =
          message.sources?.length > 0
            ? `\nSources:\n${message.sources
                .map((source, index) => `${index + 1}. ${sourceLabel(source)}`)
                .join("\n")}`
            : "";

        return `${sender} (${message.time})\n${message.content}${sources}`;
      })
      .join("\n\n----------------------\n\n");

    const blob = new Blob([text], {
      type: "text/plain;charset=utf-8",
    });

    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = "edubot-ai-chat-test.txt";
    link.click();

    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden bg-slate-50 text-slate-900 dark:bg-[#020817] dark:text-slate-100">
      <div className="flex h-[105.3%] w-[105.3%] origin-top-left scale-[0.95] flex-col overflow-hidden">
        <header className="flex flex-col gap-4 border-b border-slate-200 bg-white px-5 py-5 dark:border-slate-800 dark:bg-slate-950/70 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-normal text-slate-950 dark:text-white">
              AI Chat Test
            </h1>

            <p className="mt-1 text-base font-medium text-slate-500 dark:text-slate-400">
              Test how your RAG assistant answers using uploaded documents.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={exportResults}
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-bold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900"
            >
              <Download className="h-4 w-4" />
              Export Results
            </button>

            <button
              type="button"
              onClick={clearChat}
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-bold text-red-600 transition hover:bg-red-50 dark:hover:bg-red-500/10"
            >
              <Trash2 className="h-4 w-4" />
              Clear Chat
            </button>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_340px]">
          <main className="flex min-h-0 flex-col overflow-hidden border-slate-200 dark:border-slate-800 lg:border-r">
            <div className="flex-1 space-y-8 overflow-y-auto px-5 py-8 sm:px-8 lg:px-10">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={`flex flex-col ${
                    message.role === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <div
                    className={`max-w-3xl rounded-[22px] px-6 py-5 text-base leading-8 shadow-sm ${
                      message.role === "user"
                        ? "bg-blue-600 text-white"
                        : message.isError
                          ? "border border-red-200 bg-red-50 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200"
                          : "border border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                    }`}
                  >
                    <MarkdownMessage
                      content={message.content}
                      isUser={message.role === "user"}
                    />

                    {message.sources?.length ? (
                      <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
                        <div className="mb-3 flex flex-wrap items-center gap-5 text-xs font-black uppercase tracking-[0.12em] text-slate-400">
                          <span>
                            Sources Found:{" "}
                            <span className="text-emerald-500">
                              {message.sources.length}
                            </span>
                          </span>
                        </div>

                        <p className="mb-3 text-xs font-black uppercase tracking-[0.12em] text-slate-400">
                          Sources:
                        </p>

                        <div className="flex flex-wrap gap-2">
                          {message.sources.slice(0, 3).map((source, index) => (
                            <span
                              key={`${sourceLabel(source)}-${index}`}
                              className="inline-flex max-w-full items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-600 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-200"
                            >
                              <Link className="h-4 w-4 flex-none" />

                              <span className="truncate">
                                {sourceLabel(source)}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-2 flex items-center gap-2 px-3 text-xs font-semibold text-slate-400">
                    {message.role === "user" ? "You" : "EduBot Assistant"}
                    <span>-</span>
                    {message.time}
                  </div>
                </article>
              ))}

              {loading ? (
                <div className="flex items-start">
                  <div className="rounded-[22px] border border-slate-200 bg-white px-6 py-5 text-sm font-semibold text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                    EduBot Assistant is checking the uploaded documents...
                  </div>
                </div>
              ) : null}
            </div>

            <form
              onSubmit={handleTestQuery}
              className="bg-gradient-to-t from-slate-50 via-slate-50 px-5 pb-8 pt-4 dark:from-[#020817] dark:via-[#020817] sm:px-8 lg:px-10"
            >
              <div className="mx-auto flex max-w-4xl flex-col gap-4 rounded-[22px] border border-slate-200 bg-white p-4 shadow-lg shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-900 dark:shadow-none sm:flex-row sm:items-end">
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ask a question to test the RAG performance..."
                  className="min-h-[72px] flex-1 resize-none border-0 bg-transparent px-2 py-3 text-base font-medium text-slate-800 outline-none placeholder:text-slate-400 dark:text-white dark:placeholder:text-slate-500"
                />

                <button
                  type="submit"
                  disabled={loading || !query.trim()}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-blue-600 px-7 text-base font-bold text-white shadow-lg shadow-blue-600/25 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading ? "Testing..." : "Ask AI"}
                  <Send className="h-5 w-5" />
                </button>
              </div>
            </form>
          </main>

          <aside className="hidden overflow-y-auto bg-white px-7 py-8 dark:bg-slate-950/70 lg:block">
            <section>
              <div className="mb-5 flex items-center justify-between">
                <h2 className="text-sm font-black uppercase tracking-[0.18em] text-slate-400">
                  System Prompt
                </h2>

                <button
                  type="button"
                  onClick={() => setIsEditingPrompt((prev) => !prev)}
                  className="text-sm font-bold text-blue-600 transition hover:text-blue-500"
                >
                  {isEditingPrompt ? "Save" : "Edit"}
                </button>
              </div>

              {isEditingPrompt ? (
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  className="min-h-[180px] w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm font-medium leading-7 text-slate-700 outline-none transition focus:border-blue-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                />
              ) : (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm font-medium italic leading-7 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                  "{systemPrompt}"
                </div>
              )}
            </section>

            <section className="mt-10">
              <div className="mb-6 flex items-center justify-between">
                <h2 className="text-sm font-black uppercase tracking-[0.18em] text-slate-400">
                  Active Context
                </h2>

                <span className="rounded-md bg-emerald-100 px-3 py-1 text-xs font-black text-emerald-700">
                  {documents.length} Documents
                </span>
              </div>

              <div className="space-y-5">
                {documents.slice(0, 4).map((doc, index) => {
                  const filename = getDocumentName(doc);
                  const chunks = getDocumentChunks(doc);
                  const type = getDocumentType(filename);

                  return (
                    <div
                      key={`${filename}-${index}`}
                      className="flex items-center gap-4"
                    >
                      <span
                        className={`flex h-10 w-10 flex-none items-center justify-center rounded-lg ${type.tone}`}
                      >
                        <FileText className="h-5 w-5" />
                      </span>

                      <div className="min-w-0">
                        <p className="truncate text-sm font-black text-slate-700 dark:text-slate-100">
                          {filename}
                        </p>

                        <p className="text-xs font-semibold text-slate-400">
                          {chunks
                            ? `${chunks} chunks indexed`
                            : "Active knowledge source"}
                        </p>
                      </div>
                    </div>
                  );
                })}

                {documents.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-slate-300 px-4 py-5 text-sm font-semibold text-slate-400 dark:border-slate-700">
                    {documentsLoading
                      ? "Loading active documents..."
                      : "No documents are active yet."}
                  </p>
                ) : null}
              </div>

              <button
                type="button"
                onClick={fetchDocuments}
                disabled={documentsLoading}
                className="mt-6 flex h-11 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 text-sm font-bold text-slate-400 transition hover:border-blue-300 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
              >
                {documentsLoading ? "Refreshing..." : "+ Refresh Documents"}
              </button>
            </section>

            <section className="mt-10">
              <div className="mb-6 flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-slate-400" />

                <h2 className="text-sm font-black uppercase tracking-[0.18em] text-slate-400">
                  Hyperparameters
                </h2>
              </div>

              <div className="space-y-7">
                <div>
                  <div className="mb-3 flex justify-between text-sm font-bold text-slate-700 dark:text-slate-200">
                    <span>Temperature</span>

                    <span className="text-blue-600">
                      {temperature.toFixed(1)}
                    </span>
                  </div>

                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={temperature}
                    onChange={(e) => setTemperature(Number(e.target.value))}
                    className="w-full accent-blue-600"
                  />

                  <p className="mt-2 text-xs font-medium leading-5 text-slate-400">
                    Lower values are more strict and factual. For RAG, 0.2 to
                    0.3 is recommended.
                  </p>
                </div>

                <div>
                  <div className="mb-3 flex justify-between text-sm font-bold text-slate-700 dark:text-slate-200">
                    <span>Top-K Retrieval</span>

                    <span className="text-blue-600">{topK}</span>
                  </div>

                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="1"
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                    className="w-full accent-blue-600"
                  />

                  <p className="mt-2 text-xs font-medium leading-5 text-slate-400">
                    Controls how many document chunks are retrieved before
                    answering.
                  </p>
                </div>
              </div>
            </section>

            {latestAnswer ? (
              <section className="mt-10 rounded-2xl border border-blue-100 bg-blue-50 p-5 dark:border-blue-500/20 dark:bg-blue-500/10">
                <div className="mb-3 flex items-center gap-2 text-sm font-black text-blue-700 dark:text-blue-200">
                  <Bot className="h-4 w-4" />
                  Latest Test
                </div>

                <p className="line-clamp-4 text-sm font-medium leading-6 text-blue-900 dark:text-blue-100">
                  {latestAnswer.content}
                </p>
              </section>
            ) : null}
          </aside>
        </div>
      </div>
    </div>
  );
}

export default AdminTest;