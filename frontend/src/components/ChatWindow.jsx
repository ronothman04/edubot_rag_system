import { useEffect, useRef, useState } from "react";
import Message from "./Message";

const SUGGESTED_QUESTIONS = [
  "What is the minimum attendance required?",
  "How does the admission process work?",
  "What programmes are available in the college?",
  "What are the hostel rules?",
];

function ChatWindow({
  messages = [],
  loading,
  onSend,
  onEditMessage,
  onOpenSidebar,
}) {
  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const [editingIndex, setEditingIndex] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);

  // Scroll to the newest message when the list or loading state changes.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Follow the assistant's typewriter output: when content height grows AND the
  // user is already near the bottom, keep the latest text in view. Does not yank
  // the view if the user has scrolled up to read history.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distanceFromBottom < 120) {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    });

    observer.observe(container.firstElementChild ?? container);
    return () => observer.disconnect();
  }, []);

  const handleSend = (text) => {
    const value = text?.trim();
    if (!value || loading) return;
    onSend?.(value);
  };

  const handleCopy = async (content, index) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement("textarea");
      textarea.value = content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    }
  };

  const handleRegenerate = (index) => {
    // Find the user message right before this assistant message
    if (loading) return;
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i]?.role === "user") {
        onEditMessage?.(i, messages[i].content);
        return;
      }
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(37,99,235,0.06),_transparent_35%),linear-gradient(180deg,_#f8fafc_0%,_#f1f5f9_100%)] dark:bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.08),_transparent_28%),linear-gradient(180deg,_#030712_0%,_#090d16_50%,_#0f172a_100%)]">

      {/* ── Top bar ── */}
      <header className="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200/80 bg-white/70 px-4 backdrop-blur-md transition-colors dark:border-slate-800/80 dark:bg-slate-900/60 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Open navigation"
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900 md:hidden cursor-pointer"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M4 6h16" />
              <path d="M4 12h16" />
              <path d="M4 18h16" />
            </svg>
          </button>

          <div className="flex min-w-0 items-center">
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">AI Knowledge Assistant</p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
          </span>
          <span className="hidden sm:inline">Online</span>
        </div>
      </header>

      {/* ── Messages ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">

          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex min-h-[60dvh] flex-col items-center justify-center px-4 text-center animate-slide-up">
              <div className="relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent text-white shadow-lg shadow-accent-soft transition-transform duration-300 hover:scale-105">
                <svg className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 10v6" />
                  <path d="M2 10l10-5 10 5-10 5z" />
                  <path d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
                </svg>
              </div>

              <h1 className="mb-3 text-[26px] font-extrabold leading-tight tracking-tight text-slate-900 dark:text-white sm:text-[32px]">
                How can I help you today?
              </h1>
              <p className="mb-8 max-w-md text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                Ask about admissions, eligibility, fees, programmes, hostel rules, or pick a topic below to get started.
              </p>

              <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(q)}
                    className="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent cursor-pointer dark:border-slate-800/80 dark:bg-slate-900"
                  >
                    <div className="min-w-0">
                      <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400 transition-colors group-hover:text-accent dark:text-slate-500">
                        Suggested
                      </span>
                      <span className="block text-sm font-medium leading-snug text-slate-700 transition-colors group-hover:text-slate-900 dark:text-slate-200 dark:group-hover:text-white">
                        {q}
                      </span>
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="shrink-0 text-slate-300 transition-colors group-hover:text-accent dark:text-slate-600">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, i) => (
            <div
              key={msg.id || i}
              className={`group flex w-full flex-col gap-1 py-1 ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <Message
                msg={msg}
                isLatestAssistantMessage={
                  msg.role === "assistant" && i === messages.length - 1
                }
                canEdit={msg.role === "user" && !loading}
                isEditing={editingIndex === i}
                onStartEdit={() => setEditingIndex(i)}
                onCancelEdit={() => setEditingIndex(null)}
                onEdit={(content) => {
                  setEditingIndex(null);
                  onEditMessage?.(i, content);
                }}
                onSuggestedQuestion={handleSend}
              />

              {/* Assistant actions */}
              {msg.role === "assistant" && (
                <div className="mt-0.5 flex items-center gap-1.5 pl-11 pr-4 opacity-0 transition-opacity animate-fade-in group-hover:opacity-100">
                  <button
                    onClick={() => handleCopy(msg.content, i)}
                    className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-400 transition-all hover:bg-slate-200/60 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:hover:bg-slate-800 dark:hover:text-white cursor-pointer"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {copiedIndex === i ? "Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => handleRegenerate(i)}
                    disabled={loading}
                    className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-400 transition-all hover:bg-slate-200/60 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-white cursor-pointer"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Regenerate
                  </button>
                </div>
              )}
            </div>
          ))}

          {/* Loading */}
          {loading && (
            <div className="flex w-full flex-col items-start gap-1 py-2 pl-1">
              <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-slate-100 bg-white px-5 py-3 shadow-sm animate-pulse-soft dark:border-slate-800/80 dark:bg-slate-900">
                <span className="mr-1.5 text-xs font-semibold text-slate-400 dark:text-slate-500">Thinking</span>
                {[0, 0.2, 0.4].map((d, i) => (
                  <span
                    key={i}
                    className="h-1.5 w-1.5 rounded-full bg-accent animate-bounce"
                    style={{ animationDelay: `${d}s`, opacity: 0.8 }}
                  />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

    </div>
  );
}

export default ChatWindow;
