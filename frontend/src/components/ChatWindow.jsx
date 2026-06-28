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
  setCurrentView,
  user,
  onOpenSidebar,
}) {
  const bottomRef = useRef(null);
  const [editingIndex, setEditingIndex] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

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
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-200 bg-white/70 px-4 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/60 transition-colors sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Open navigation"
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900 md:hidden cursor-pointer"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M4 6h16" />
              <path d="M4 12h16" />
              <path d="M4 18h16" />
            </svg>
          </button>

          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 transition-colors">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span className="truncate">EduBot AI Knowledge Base</span>
          </div>
        </div>
      </header>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">

          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex min-h-[65vh] flex-col items-center justify-center text-center animate-slide-up px-4">
              <div className="relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-md shadow-blue-500/10 transition-transform duration-300 hover:scale-105">
                <svg className="w-9 h-9 text-white" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M22 10v6M2 10l10-5 10 5-10 5z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
                </svg>
              </div>

              <h1 className="mb-3 text-[24px] font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-[32px] leading-tight">
                How can I help you today?
              </h1>
              <p className="mb-8 max-w-md text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                Ask questions about admission requirements, required documents, or select a topic below to get started.
              </p>

              <div className="grid w-full max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(q)}
                    className="group rounded-2xl border border-slate-200/80 bg-white p-5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-500/35 hover:shadow-md cursor-pointer dark:border-slate-800/80 dark:bg-slate-900 dark:hover:border-blue-500/30"
                  >
                    <span className="block mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 group-hover:text-blue-500 dark:text-slate-500 transition-colors">
                      Suggested Topic
                    </span>
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-200 leading-snug group-hover:text-slate-900 dark:group-hover:text-white">
                      {q}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, i) => (
            <div
              key={msg.id || i}
              className={`flex flex-col gap-1 py-1 group w-full ${msg.role === "user" ? "items-end" : "items-start"}`}
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
                <div className="flex items-center gap-1.5 pl-11 pr-4 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 animate-fade-in">
                  <button
                    onClick={() => handleCopy(msg.content, i)}
                    className="hover:text-slate-800 hover:bg-slate-200/60 dark:hover:text-white dark:hover:bg-slate-800 flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition-all cursor-pointer font-medium"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {copiedIndex === i ? "Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => handleRegenerate(i)}
                    disabled={loading}
                    className="hover:text-slate-800 hover:bg-slate-200/60 dark:hover:text-white dark:hover:bg-slate-800 flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
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
            <div className="flex flex-col gap-1 items-start py-2 w-full pl-1">
              <div className="flex items-center gap-2 px-12 py-3 bg-white dark:bg-slate-900 rounded-2xl rounded-bl-sm border border-slate-100 dark:border-slate-800/80 shadow-sm animate-pulse-soft">
                <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 mr-1.5">Thinking</span>
                {[0, 0.2, 0.4].map((d, i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-blue-500 dark:bg-blue-400 animate-bounce"
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
