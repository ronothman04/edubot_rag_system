import { useEffect, useRef, useState } from "react";
import Message from "./Message";

const SUGGESTED_QUESTIONS = [
  "What admission requirements are there?",
  "How does the admission process work?",
  "What courses are available?",
  "What are the tuition fees?",
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
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.10),_transparent_30%),linear-gradient(180deg,_#f7f9fc_0%,_#eef3f8_100%)] dark:bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_24%),linear-gradient(180deg,_#08111f_0%,_#0f172a_52%,_#111827_100%)]">

      {/* ── Top bar ── */}
      <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/85 px-3 py-3 pl-14 backdrop-blur dark:border-white/[0.08] dark:bg-slate-900/80 sm:px-5 sm:pl-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Open navigation"
            className="hidden h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 6h16" />
              <path d="M4 12h16" />
              <path d="M4 18h16" />
            </svg>
          </button>
          <button className="hover:border-accent-soft hover:text-accent-strong dark:hover:text-accent-soft flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-[13px] font-medium text-slate-700 transition-colors dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-200">
            <span className="bg-accent h-2 w-2 flex-shrink-0 rounded-full" />
            <span className="truncate">Knowledge Assistant</span>
            <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {!user && (
            <>
              <button
                onClick={() => setCurrentView?.("login")}
                className="hover:border-accent-soft hover:text-accent-strong dark:hover:text-accent-soft rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-[13px] font-medium text-slate-700 shadow-sm transition-all cursor-pointer dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-200 sm:px-4"
              >
                Login
              </button>
              <button
                onClick={() => setCurrentView?.("register")}
                className="bg-accent hover:bg-accent-dark rounded-full px-3 py-1.5 text-[13px] font-medium text-white shadow-sm transition-colors cursor-pointer sm:px-4"
              >
                Sign Up
              </button>
            </>
          )}
        </div>
      </header>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 sm:py-6">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3">

          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex min-h-[52vh] flex-col items-center justify-center text-center">
              <div className="bg-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft mb-5 flex h-14 w-14 items-center justify-center rounded-[18px] shadow-inner">
                <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M22 10v6M2 10l10-5 10 5-10 5z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
                </svg>
              </div>

              <h1 className="mb-2 text-[22px] font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[26px]">
                How can I help you today?
              </h1>
              <p className="mb-6 max-w-sm text-[13.5px] leading-relaxed text-slate-500 dark:text-slate-400 sm:mb-8">
                Start with a focused prompt below or pick one of these common questions to explore the knowledge base.
              </p>

              <div className="grid w-full max-w-lg grid-cols-1 gap-3 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(q)}
                    className="hover:border-accent-soft hover:bg-accent-soft group rounded-2xl border border-slate-200 bg-white px-4 py-4 text-left text-[13.5px] leading-snug text-slate-700 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md cursor-pointer dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <span className="group-hover:text-accent block mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-400 transition-colors dark:text-slate-500">
                      Suggested prompt
                    </span>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, i) => (
            <div
              key={msg.id || i}
              className={`flex flex-col gap-1.5 py-2 group w-full ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <Message
                msg={msg}
                canEdit={msg.role === "user" && !loading}
                isEditing={editingIndex === i}
                onStartEdit={() => setEditingIndex(i)}
                onCancelEdit={() => setEditingIndex(null)}
                onEdit={(content) => {
                  setEditingIndex(null);
                  onEditMessage?.(i, content);
                }}
              />

              {/* Assistant actions */}
              {msg.role === "assistant" && (
                <div className="flex items-center gap-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5">
                  <button
                    onClick={() => handleCopy(msg.content, i)}
                    className="hover:text-accent hover:bg-accent-soft dark:hover:bg-accent-soft-dark flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11.5px] text-slate-400 transition-all cursor-pointer"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {copiedIndex === i ? "Copied!" : "Copy"}
                  </button>
                  <button
                    onClick={() => handleRegenerate(i)}
                    disabled={loading}
                    className="hover:text-accent hover:bg-accent-soft dark:hover:bg-accent-soft-dark flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11.5px] text-slate-400 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
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
            <div className="flex flex-col gap-1.5 items-start py-2 w-full">
              <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-slate-400 dark:text-slate-500 px-1">
                Assistant
              </span>
              <div className="flex items-center gap-1.5 px-5 py-4 bg-white dark:bg-slate-800 rounded-2xl rounded-bl-sm border border-slate-200 dark:border-slate-700 shadow-sm">
                {[0, 0.2, 0.4].map((d, i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce"
                    style={{ animationDelay: `${d}s`, opacity: 0.7 }}
                  />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input bar ── */}
      {/* <div className="flex-shrink-0 px-4 pb-4 pt-2 bg-white/70 dark:bg-slate-900/80 backdrop-blur border-t border-slate-200 dark:border-white/[0.08]">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/90 px-4 py-3 shadow-sm focus-within:border-sky-300 dark:focus-within:border-sky-700 focus-within:ring-2 focus-within:ring-sky-100 dark:focus-within:ring-sky-900/40 transition-all">
            <textarea
              ref={textareaRef}
              rows={1}
              value={draft}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Message Knowledge Assistant…"
              className="flex-1 resize-none bg-transparent text-[14.5px] leading-relaxed text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 outline-none max-h-40"
            />
            <button
              onClick={() => handleSend()}
              disabled={!draft.trim() || loading}
              className="w-[34px] h-[34px] rounded-xl bg-sky-600 flex items-center justify-center flex-shrink-0 hover:bg-sky-700 disabled:bg-slate-200 dark:disabled:bg-slate-700 disabled:cursor-not-allowed transition-all active:scale-95 cursor-pointer"
            >
              <svg className="w-[15px] h-[15px] text-white" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          <p className="text-center text-[11px] text-slate-400 dark:text-slate-500 mt-2.5">
            Knowledge Assistant can make mistakes. Verify important information.
          </p>
        </div>
      </div> */}

    </div>
  );
}

export default ChatWindow;
