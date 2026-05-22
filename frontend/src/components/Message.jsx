import { useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getDocumentUrl(filename) {
  if (!filename || filename === "Unknown document") return null;
  return `${API_URL}/documents/${encodeURIComponent(filename)}/download`;
}

// ── AssistantMarkdown ─────────────────────────────────────────────────────────
// Renders all markdown from the RAG backend including:
//   - Normal prose (paragraphs, bold, lists, headings)
//   - Markdown tables (GFM)  ← styled via custom components below
//
// The `components` map overrides every HTML element react-markdown produces,
// giving us full Tailwind control without a global CSS file.

function AssistantMarkdown({ content }) {
  return (
    <div className="assistant-markdown min-w-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{

          // ── Block elements ──────────────────────────────────────────────

          p({ node, children, ...props }) {
            return (
              <p
                className="mb-2 leading-7 text-slate-800 last:mb-0 dark:text-slate-100"
                {...props}
              >
                {children}
              </p>
            );
          },

          h1({ node, children, ...props }) {
            return (
              <h1
                className="mb-3 mt-4 text-lg font-bold text-slate-900 first:mt-0 dark:text-slate-50"
                {...props}
              >
                {children}
              </h1>
            );
          },

          h2({ node, children, ...props }) {
            return (
              <h2
                className="mb-2 mt-4 text-base font-semibold text-slate-900 first:mt-0 dark:text-slate-50"
                {...props}
              >
                {children}
              </h2>
            );
          },

          h3({ node, children, ...props }) {
            return (
              <h3
                className="mb-2 mt-3 text-sm font-semibold text-slate-800 first:mt-0 dark:text-slate-100"
                {...props}
              >
                {children}
              </h3>
            );
          },

          ul({ node, children, ...props }) {
            return (
              <ul
                className="mb-3 ml-5 list-disc space-y-1 text-slate-800 dark:text-slate-100"
                {...props}
              >
                {children}
              </ul>
            );
          },

          ol({ node, children, ...props }) {
            return (
              <ol
                className="mb-3 ml-5 list-decimal space-y-1 text-slate-800 dark:text-slate-100"
                {...props}
              >
                {children}
              </ol>
            );
          },

          li({ node, children, ...props }) {
            return (
              <li className="leading-7" {...props}>
                {children}
              </li>
            );
          },

          strong({ node, children, ...props }) {
            return (
              <strong
                className="font-semibold text-slate-900 dark:text-white"
                {...props}
              >
                {children}
              </strong>
            );
          },

          em({ node, children, ...props }) {
            return (
              <em className="italic text-slate-700 dark:text-slate-300" {...props}>
                {children}
              </em>
            );
          },

          code({ node, inline, children, ...props }) {
            if (inline) {
              return (
                <code
                  className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <pre className="mb-3 overflow-x-auto rounded-xl bg-slate-100 px-4 py-3 dark:bg-slate-800">
                <code
                  className="font-mono text-xs text-slate-800 dark:text-slate-200"
                  {...props}
                >
                  {children}
                </code>
              </pre>
            );
          },

          blockquote({ node, children, ...props }) {
            return (
              <blockquote
                className="mb-3 border-l-4 border-slate-300 pl-4 italic text-slate-600 dark:border-slate-600 dark:text-slate-400"
                {...props}
              >
                {children}
              </blockquote>
            );
          },

          hr({ node, ...props }) {
            return (
              <hr
                className="my-4 border-slate-200 dark:border-slate-700"
                {...props}
              />
            );
          },

          // ── Table elements ──────────────────────────────────────────────
          // Wrapped in overflow-x-auto so wide tables scroll on mobile
          // instead of breaking the chat bubble layout.

          table({ node, children, ...props }) {
            return (
              <div className="my-3 w-full overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
                <table
                  className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-700"
                  {...props}
                >
                  {children}
                </table>
              </div>
            );
          },

          thead({ node, children, ...props }) {
            return (
              <thead
                className="bg-accent text-white"
                {...props}
              >
                {children}
              </thead>
            );
          },

          tbody({ node, children, ...props }) {
            return (
              <tbody
                className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900"
                {...props}
              >
                {children}
              </tbody>
            );
          },

          tr({ node, children, ...props }) {
            return (
              <tr
                className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                {...props}
              >
                {children}
              </tr>
            );
          },

          th({ node, children, ...props }) {
            return (
              <th
                className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide"
                {...props}
              >
                {children}
              </th>
            );
          },

          td({ node, children, ...props }) {
            return (
              <td
                className="px-4 py-2.5 text-slate-700 dark:text-slate-300"
                {...props}
              >
                {children}
              </td>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ── Message ───────────────────────────────────────────────────────────────────

function Message({
  msg,
  canEdit = false,
  isEditing = false,
  onEdit,
  onStartEdit,
  onCancelEdit,
  onSuggestedQuestion,
  fallbackSuggestedQuestions = [],
  fallbackSuggestionTopic = null,
}) {
  const isUser = msg.role === "user";

  const shouldShowSources =
    !isUser &&
    msg.show_sources !== false &&
    msg.response_type !== "homework_refusal" &&
    Array.isArray(msg.sources) &&
    msg.sources.length > 0;

  const messageSuggestions = Array.isArray(msg.suggested_questions)
    ? msg.suggested_questions
    : [];
  const suggestedQuestions = (messageSuggestions.length
    ? messageSuggestions
    : fallbackSuggestedQuestions
  )
    .map((question) => String(question || "").trim())
    .filter(Boolean)
    .slice(0, 3);

  const shouldShowSuggestions = !isUser && suggestedQuestions.length > 0;
  const suggestionTopic =
    typeof msg.suggestion_topic === "string" && msg.suggestion_topic.trim()
      ? msg.suggestion_topic.trim()
      : typeof fallbackSuggestionTopic === "string" && fallbackSuggestionTopic.trim()
        ? fallbackSuggestionTopic.trim()
        : null;
  const suggestionLabel =
    suggestionTopic
      ? `Did you mean ${suggestionTopic}?`
      : "Did you mean one of these?";

  const [draft, setDraft] = useState(msg.content);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!isEditing || !textareaRef.current) return;

    textareaRef.current.focus();
    textareaRef.current.setSelectionRange(draft.length, draft.length);
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
  }, [draft.length, isEditing]);

  useEffect(() => {
    setDraft(msg.content);
  }, [msg.content]);

  const resizeTextarea = (element) => {
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  };

  const handleSave = () => {
    const value = draft.trim();

    if (!value || value === msg.content) {
      onCancelEdit?.();
      return;
    }

    onEdit?.(value);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = msg.content;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";

      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }

    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className={`group flex w-full gap-3 px-1 py-3 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {/* AI avatar */}
      {!isUser && (
        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent-strong shadow-sm dark:bg-accent-soft-dark dark:text-accent-soft">
          AI
        </div>
      )}

      <div
        className={`flex min-w-0 max-w-[88%] flex-col ${
          isUser ? "items-end" : "items-start"
        } sm:max-w-[78%] lg:max-w-[68%]`}
      >
        {/* Message bubble */}
        <div
          className={`min-w-0 rounded-3xl px-4 py-3 text-sm leading-7 shadow-sm ${
            isUser
              ? "rounded-br-md bg-accent text-white"
              : "rounded-bl-md border border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          }`}
        >
          {isEditing ? (
            <div className="space-y-3">
              <textarea
                ref={textareaRef}
                rows={3}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  resizeTextarea(e.target);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleSave();
                  }

                  if (e.key === "Escape") {
                    e.preventDefault();
                    setDraft(msg.content);
                    onCancelEdit?.();
                  }
                }}
                className="min-h-[96px] w-full resize-none rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-sm leading-7 text-white outline-none placeholder:text-white/70"
              />

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDraft(msg.content);
                    onCancelEdit?.();
                  }}
                  className="rounded-full border border-white/20 px-3 py-1.5 text-xs font-medium text-white/90 transition hover:bg-white/10"
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleSave}
                  className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-accent-strong transition hover:bg-white/90"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div className="min-w-0 break-words [overflow-wrap:anywhere]">
              {isUser ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <AssistantMarkdown content={msg.content} />
              )}
            </div>
          )}
        </div>

        {/* Sources outside AI bubble */}
        {shouldShowSources && (
          <div className="mt-2 w-full max-w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
            <details>
              <summary className="cursor-pointer select-none font-semibold text-slate-700 hover:text-accent dark:text-slate-200 dark:hover:text-accent-soft">
                View sources
              </summary>

              <ul className="mt-2 space-y-1.5">
                {(() => {
                  const uniqueSources = [];
                  const seenFiles = new Set();

                  for (const source of msg.sources) {
                    const filename =
                      typeof source === "string" ? source : source.file;

                    if (!filename || seenFiles.has(filename)) continue;

                    uniqueSources.push(source);
                    seenFiles.add(filename);

                    if (uniqueSources.length >= 3) break;
                  }

                  return uniqueSources.map((source, index) => {
                    const filename =
                      typeof source === "string" ? source : source.file;

                    const page =
                      typeof source === "string" ? null : source.page;

                    const documentUrl = getDocumentUrl(filename);

                    return (
                      <li key={`${filename}-${index}`} className="break-words">
                        {documentUrl ? (
                          <a
                            href={documentUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-accent underline underline-offset-4 hover:opacity-80 dark:text-accent-soft"
                          >
                            {filename}
                          </a>
                        ) : (
                          <span className="font-medium">{filename}</span>
                        )}

                        {page ? (
                          <span className="ml-1 text-slate-500 dark:text-slate-400">
                            Page {page}
                          </span>
                        ) : null}
                      </li>
                    );
                  });
                })()}
              </ul>
            </details>
          </div>
        )}

        {/* Suggested questions for unanswered prompts */}
        {shouldShowSuggestions && (
          <div className="mt-2 w-full max-w-full rounded-2xl border border-accent-soft bg-accent-soft/40 px-3 py-3 text-sm dark:border-accent-soft-dark dark:bg-accent-soft-dark/20">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-accent-strong dark:text-accent-soft">
              {suggestionLabel}
            </p>

            <div className="flex flex-col gap-2">
              {suggestedQuestions.map((question, index) => (
                <button
                  key={`${question}-${index}`}
                  type="button"
                  onClick={() => onSuggestedQuestion?.(question)}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-[13px] leading-snug text-slate-700 shadow-sm transition hover:border-accent-soft hover:text-accent-strong disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-accent-soft-dark dark:hover:text-accent-soft"
                  disabled={!onSuggestedQuestion}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Actions below bubble */}
        {!isEditing && isUser && (
          <div className="mt-1 flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              aria-label={copied ? "Copied message" : "Copy message"}
              title={copied ? "Copied" : "Copy"}
            >
              {copied ? (
                <Check className="h-4 w-4" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>

            {canEdit && (
              <button
                type="button"
                onClick={() => {
                  setDraft(msg.content);
                  onStartEdit?.();
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label="Edit message"
                title="Edit"
              >
                <Pencil className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white shadow-sm">
          You
        </div>
      )}
    </div>
  );
}

export default Message;
