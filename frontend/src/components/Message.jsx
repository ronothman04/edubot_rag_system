import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getDocumentUrl(filename, page) {
  if (!filename || filename === "Unknown document") return null;

  const baseUrl = `${API_URL}/documents/${encodeURIComponent(filename)}/download`;

  if (page && filename.toLowerCase().endsWith(".pdf")) {
    return `${baseUrl}#page=${encodeURIComponent(page)}`;
  }

  return baseUrl;
}

function getSourceHref(source) {
  if (source?.source_url?.startsWith("http")) return source.source_url;
  if (source?.found_on_url?.startsWith("http")) return source.found_on_url;
  if (source?.download_url) return source.download_url;
  const file = typeof source === "string" ? source : source?.file || source?.filename;
  if (typeof file === "string" && file.startsWith("http")) return file;
  return null;
}

function getSourceFile(source) {
  return typeof source === "string" ? source : source?.file || source?.filename;
}

function getSourcePage(source) {
  if (!source || typeof source === "string") return null;
  return source.page_label || source.page || null;
}

function isWebsiteSource(source, filename) {
  const sourceType = String(source?.source_type || "");
  const fileType = String(source?.file_type || "");
  const file = String(filename || "");

  const isDocFile = /\.(pdf|docx|doc|xlsx|xls|txt|csv|odt|ods|png|jpg|jpeg)$/i.test(file);
  if (isDocFile) {
    return false;
  }

  if (sourceType === "uploaded_document") {
    return false;
  }

  return (
    sourceType.startsWith("website") ||
    fileType === "website" ||
    fileType === "website_links" ||
    file.startsWith("http://") ||
    file.startsWith("https://")
  );
}

function getSourceLabel(source, filename, page) {
  const sourceType = String(source?.source_type || "");
  const fileType = String(source?.file_type || "");
  const section = String(source?.section_title || "").trim();
  const pdfName = String(source?.source_pdf_filename || "").trim();
  const file = String(filename || "").trim();

  const isDocFile = /\.(pdf|docx|doc|xlsx|xls|txt|csv)$/i.test(file);
  if (sourceType === "uploaded_document" || isDocFile) {
    const cleanFile = file.replace(/^[a-f0-9]{32}_/, "");
    return cleanFile;
  }

  if (sourceType === "website_page" || fileType === "website" || fileType === "website_links") {
    const title = section && section.toLowerCase() !== "general" ? section : file || "Website source";
    return `${title} - Website Page`;
  }

  if (sourceType === "website_pdf" || sourceType === "website_document" || fileType === "website_pdf" || fileType === "website_document") {
    return `${pdfName || file || "Website document"} - Document`;
  }

  if (file) {
    return file;
  }

  return "Source link not available";
}

// Stateful CodeBlock component with dynamic Copy button & language header
function CodeBlock({ children, className }) {
  const [copied, setCopied] = useState(false);
  const codeText = String(children).replace(/\n$/, "");
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn("Failed to copy code block:", err);
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-900 shadow-sm dark:border-slate-800">
      <div className="flex items-center justify-between bg-slate-800/80 px-4 py-1.5 text-xs text-slate-350 dark:bg-slate-900 select-none">
        <span className="font-semibold uppercase tracking-wider">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition-colors cursor-pointer"
        >
          {copied ? (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>Copied</span>
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      
      <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed">
        <code className="font-mono text-slate-200">{codeText}</code>
      </pre>
    </div>
  );
}

// ── AssistantMarkdown ─────────────────────────────────────────────────────────
function AssistantMarkdown({ content }) {
  return (
    <div className="assistant-markdown min-w-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
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
              <em
                className="italic text-slate-700 dark:text-slate-300"
                {...props}
              >
                {children}
              </em>
            );
          },

          a({ node, children, ...props }) {
            return (
              <a
                {...props}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-accent underline underline-offset-4 hover:opacity-80 dark:text-accent-soft"
              >
                {children}
              </a>
            );
          },

          code({ node, inline, className, children, ...props }) {
            if (inline) {
              return (
                <code
                  className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs font-semibold text-slate-800 dark:bg-slate-800 dark:text-slate-200"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return <CodeBlock className={className}>{children}</CodeBlock>;
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
              <thead className="bg-accent text-white" {...props}>
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

// ── TypingAssistantMarkdown ───────────────────────────────────────────────────
function TypingAssistantMarkdown({ content, speed = 10, onDone }) {
  const [displayedContent, setDisplayedContent] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const onDoneRef = useRef(onDone);

  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!content) {
      setDisplayedContent("");
      setIsTyping(false);
      onDoneRef.current?.();
      return;
    }

    let index = 0;
    let cancelled = false;

    setDisplayedContent("");
    setIsTyping(true);

    const interval = window.setInterval(() => {
      if (cancelled) return;

      index += 1;
      setDisplayedContent(content.slice(0, index));

      if (index >= content.length) {
        window.clearInterval(interval);
        setIsTyping(false);
        onDoneRef.current?.();
      }
    }, speed);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [content, speed]);

  return (
    <div className="relative">
      <AssistantMarkdown content={displayedContent} />

      {isTyping && (
        <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-slate-500 align-middle dark:bg-slate-350" />
      )}
    </div>
  );
}

// ── Message ───────────────────────────────────────────────────────────────────
function Message({
  msg,
  canEdit = false,
  isEditing = false,
  isLatestAssistantMessage = false,
  onEdit,
  onStartEdit,
  onCancelEdit,
  onSuggestedQuestion,
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

  const suggestedQuestions = messageSuggestions
    .map((question) => String(question || "").trim())
    .filter(Boolean)
    .slice(0, 3);

  const shouldShowSuggestions =
    !isUser &&
    msg.response_type !== "not_found" &&
    suggestedQuestions.length > 0;

  const suggestionTopic =
    typeof msg.suggestion_topic === "string" && msg.suggestion_topic.trim()
      ? msg.suggestion_topic.trim()
      : null;

  const suggestionLabel = suggestionTopic
    ? `Did you mean: ${suggestionTopic}?`
    : "Suggested Questions:";

  const [draft, setDraft] = useState(msg.content);
  const [copied, setCopied] = useState(false);
  const [typingDone, setTypingDone] = useState(
    isUser || !isLatestAssistantMessage
  );

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

  useEffect(() => {
    setTypingDone(isUser || !isLatestAssistantMessage);
  }, [isUser, isLatestAssistantMessage, msg.content]);

  const handleTypingDone = useCallback(() => {
    setTypingDone(true);
  }, []);

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
      className={`flex w-full gap-3 py-3 select-text ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {/* AI Avatar */}
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-[10px] font-bold text-white shadow-sm transition-transform duration-200 hover:scale-105 select-none">
          AI
        </div>
      )}

      <div
        className={`flex min-w-0 max-w-[88%] flex-col ${
          isUser ? "items-end" : "items-start"
        } sm:max-w-[80%]`}
      >
        {/* Message bubble */}
        <div
          className={`min-w-0 rounded-2xl px-4 py-3 text-[14px] leading-7 shadow-sm transition-colors ${
            isUser
              ? "rounded-tr-none bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-blue-500/5"
              : "rounded-tl-none border border-slate-200 bg-white text-slate-800 dark:border-slate-800/80 dark:bg-slate-900 dark:text-slate-100"
          }`}
        >
          {isEditing ? (
            <div className="space-y-3 min-w-[280px] sm:min-w-[400px]">
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
                className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:bg-white dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:bg-slate-950"
              />

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDraft(msg.content);
                    onCancelEdit?.();
                  }}
                  className="rounded-lg border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 cursor-pointer"
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleSave}
                  className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-blue-700 cursor-pointer shadow-sm shadow-blue-500/10"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div className="min-w-0 break-words [overflow-wrap:anywhere]">
              {isUser ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : isLatestAssistantMessage ? (
                <TypingAssistantMarkdown
                  content={msg.content}
                  speed={10}
                  onDone={handleTypingDone}
                />
              ) : (
                <AssistantMarkdown content={msg.content} />
              )}
            </div>
          )}
        </div>

        {/* Sources rendered as Grid Cards */}
        {typingDone && shouldShowSources && (
          <div className="mt-3 w-full max-w-full space-y-2 animate-fade-in select-none">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 pl-1">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-500">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <span>Sources & References</span>
            </div>
            
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {(() => {
                const uniqueSources = [];
                const seenSources = new Set();

                for (const source of msg.sources) {
                  const filename = getSourceFile(source);
                  const page = getSourcePage(source);
                  const sourceHref = getSourceHref(source);
                  const sourceKey =
                    sourceHref ||
                    `${filename || "unknown"}:${page || "unknown"}`;

                  if ((!filename && !sourceHref) || seenSources.has(sourceKey)) continue;

                  uniqueSources.push(source);
                  seenSources.add(sourceKey);

                  if (uniqueSources.length >= 4) break;
                }

                return uniqueSources.map((source, index) => {
                  const filename = getSourceFile(source);
                  const page = getSourcePage(source);
                  const sourceHref = getSourceHref(source);
                  const documentUrl =
                    sourceHref ||
                    (isWebsiteSource(source, filename)
                      ? null
                      : getDocumentUrl(filename, page));
                  const displayLabel = getSourceLabel(source, filename, page);

                  const cardContent = (
                    <div className="flex h-full items-start gap-2.5 rounded-xl border border-slate-250 bg-white p-3 shadow-sm hover:border-blue-500/35 hover:shadow dark:border-slate-800/80 dark:bg-slate-900 transition-all duration-200">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-50/80 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
                        {isWebsiteSource(source, filename) ? (
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <circle cx="12" cy="12" r="10" />
                            <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
                            <path d="M2 12h20" />
                          </svg>
                        ) : (
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                          </svg>
                        )}
                      </div>
                      
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <p className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
                          {displayLabel}
                        </p>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">
                            {isWebsiteSource(source, filename) ? "Website page" : "Document reference"}
                          </span>
                          {page && (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-655 dark:bg-slate-800 dark:text-slate-350">
                              Page {page}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );

                  if (documentUrl) {
                    return (
                      <a
                        key={`${documentUrl || filename || "source"}-${page || index}`}
                        href={documentUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block h-full cursor-pointer hover:no-underline"
                      >
                        {cardContent}
                      </a>
                    );
                  }

                  return (
                    <div key={`${filename || "source"}-${page || index}`} className="block h-full">
                      {cardContent}
                    </div>
                  );
                });
              })()}
            </div>
          </div>
        )}

        {/* Suggested questions styled as neat horizontal clickable cards */}
        {typingDone && shouldShowSuggestions && (
          <div className="mt-3 w-full max-w-full space-y-2 animate-fade-in">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 pl-1 select-none">
              {suggestionLabel}
            </p>

            <div className="flex flex-col gap-2">
              {suggestedQuestions.map((question, index) => (
                <button
                  key={`${question}-${index}`}
                  type="button"
                  onClick={() => onSuggestedQuestion?.(question)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-left text-xs font-semibold text-slate-700 hover:text-blue-600 hover:border-blue-500/35 hover:shadow-sm transition-all duration-200 cursor-pointer dark:border-slate-800/80 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-white flex items-center justify-between gap-3 group"
                  disabled={!onSuggestedQuestion}
                >
                  <span className="truncate">{question}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-slate-400 group-hover:text-blue-500 transition-colors shrink-0">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Action icons below message bubble */}
        {!isEditing && isUser && (
          <div className="mt-1 flex items-center gap-1.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100 select-none pr-1">
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-200/50 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-250 cursor-pointer"
              aria-label={copied ? "Copied message" : "Copy message"}
              title={copied ? "Copied" : "Copy"}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </button>

            {canEdit && (
              <button
                type="button"
                onClick={() => {
                  setDraft(msg.content);
                  onStartEdit?.();
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-200/50 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-250 cursor-pointer"
                aria-label="Edit message"
                title="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-200 text-[10px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-350 shadow-sm select-none">
          You
        </div>
      )}
    </div>
  );
}

export default Message;
