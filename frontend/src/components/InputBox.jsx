import { useRef, useState, useEffect } from "react";

function getSpeechRecognitionSupportMessage() {
  const userAgent = window.navigator?.userAgent || "";
  const platform = window.navigator?.platform || "";
  const isIos =
    /iPad|iPhone|iPod/.test(userAgent) ||
    (platform === "MacIntel" && window.navigator?.maxTouchPoints > 1);
  const isLocalhost = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);

  if (!window.isSecureContext && !isLocalhost) {
    return "Voice input needs HTTPS on mobile browsers. Open the app with HTTPS, or test it on localhost.";
  }

  if (isIos) {
    return "Voice input is not available in Chrome on iPhone/iPad because iOS does not expose browser speech recognition here. Please type your question or use keyboard dictation.";
  }

  return "Voice input is not available in this browser. Please use Android Chrome/Edge over HTTPS, or type your question.";
}

function InputBox({ onSend, loading, disabled = false }) {
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);
  const textareaRef = useRef(null);

  const adjustHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    }
  };

  useEffect(() => {
    adjustHeight();
  }, [input]);

  const handleSend = () => {
    if (!input.trim() || loading || disabled) return;

    onSend(input);
    setInput("");
  };

  const startListening = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert(getSpeechRecognitionSupportMessage());
      return;
    }

    const recognition = new SpeechRecognition();

    recognition.lang = "en-IN"; // You can change to "en-US"
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      setListening(true);
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;

      setInput((prev) => {
        const space = prev.trim() ? " " : "";
        return prev + space + transcript;
      });
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);

      if (event.error === "not-allowed") {
        alert("Microphone permission denied. Please allow microphone access.");
      } else if (event.error === "service-not-allowed") {
        alert("Speech recognition is blocked by the browser. Use HTTPS and check microphone/speech permissions.");
      } else {
        alert("Microphone error: " + event.error);
      }

      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }

    setListening(false);
  };

  const toggleMic = () => {
    if (disabled || loading) return;

    if (listening) {
      stopListening();
    } else {
      startListening();
    }
  };

  return (
    <div className="border-t border-slate-200/80 bg-white/95 px-2 py-2 backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-950/95 sm:px-3 lg:px-4">
      <div className="w-full">
        <div className="flex items-end gap-2 rounded-[22px] border border-slate-200 bg-white p-2 shadow-[0_16px_40px_rgba(15,23,42,0.08)] transition-colors dark:border-slate-700 dark:bg-slate-900 dark:shadow-[0_16px_40px_rgba(2,6,23,0.35)] sm:gap-3 sm:rounded-[25px] sm:p-2.5">
          <div className="flex-1">
            <textarea
              ref={textareaRef}
              rows={1}
              className="max-h-40 min-h-[46px] w-full resize-none bg-transparent px-2 py-3 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400 dark:text-white sm:min-h-[50px]"
              value={input}
              placeholder={
                listening
                  ? "Listening... speak now"
                  : "Ask EduBot your questions..."
              }
              disabled={disabled}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
          </div>

          {/* Microphone Button */}
          <button
            type="button"
            onClick={toggleMic}
            disabled={loading || disabled}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
              listening
                ? "bg-red-600 hover:bg-red-700"
                : "bg-slate-700 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600"
            }`}
            aria-label={listening ? "Stop microphone" : "Start microphone"}
            title={listening ? "Stop microphone" : "Start microphone"}
          >
            {listening ? (
              // Mic Off Icon
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="2" y1="2" x2="22" y2="22" />
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
                <path d="M15 9.34V5a3 3 0 0 0-5.94-.6" />
                <path d="M17 16.95A7 7 0 0 1 5 12" />
                <path d="M19 10v2a7 7 0 0 1-.11 1.23" />
                <line x1="12" y1="19" x2="12" y2="22" />
                <line x1="8" y1="22" x2="16" y2="22" />
              </svg>
            ) : (
              // Mic Icon
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </button>

          {/* Send Button */}
          <button
            type="button"
            onClick={handleSend}
            disabled={loading || disabled || !input.trim()}
            className="bg-accent hover:bg-accent-dark flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send message"
            title="Send message"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M22 2 11 13" />
              <path d="m22 2-7 20-4-9-9-4Z" />
            </svg>
          </button>
        </div>

        {listening && (
          <p className="mt-2 px-2 text-xs font-medium text-red-500">
            Listening... speak now
          </p>
        )}
      </div>
    </div>
  );
}

export default InputBox;
