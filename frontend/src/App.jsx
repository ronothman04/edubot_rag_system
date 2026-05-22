import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import InputBox from "./components/InputBox";
import Settings from "./components/Settings";
import Auth from "./components/Auth";
import UpdatePassword from "./components/UpdatePassword";
import AdminDashboard from "./components/AdminDashboard";
import AdminDocuments from "./components/admin/AdminDocuments";
import AdminQueries from "./components/admin/AdminQueries";
import AdminAnalytics from "./components/admin/AdminAnalytics";
import AdminTest from "./components/admin/AdminTest";
import AdminManagement from "./components/admin/AdminManagement";
import AdminHistory from "./components/admin/AdminHistory";
import SetPassword from "./components/SetPasssword";


import { sendMessage } from "./services/api";
import { deleteChatActivity, logChatActivity } from "./services/chatAnalytics";
import { supabase } from "./supabaseClient";
import { Toaster } from "react-hot-toast";
import { applyAccentColor } from "./themeAccent";

const CHAT_STORAGE_PREFIX = "chat_history:";

function getChatStorageKey(userId) {
  return `${CHAT_STORAGE_PREFIX}${userId}`;
}

function createConversationTitle(messages) {
  const firstUserMessage = messages.find((message) => message.role === "user");
  if (!firstUserMessage?.content) return "New Chat";
  const trimmed = firstUserMessage.content.trim();
  return trimmed.length > 40 ? `${trimmed.slice(0, 40)}...` : trimmed;
}

function createConversationId() {
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeStoredChats(value) {
  if (!value || typeof value !== "object") {
    return { activeConversationId: null, conversations: [] };
  }

  const conversations = Array.isArray(value.conversations)
    ? value.conversations.filter(
        (conversation) =>
          conversation &&
          typeof conversation.id === "string" &&
          Array.isArray(conversation.messages),
      )
    : [];

  return {
    activeConversationId:
      typeof value.activeConversationId === "string" ? value.activeConversationId : null,
    conversations,
  };
}

function readStoredChats(userId) {
  if (!userId || typeof window === "undefined") {
    return { activeConversationId: null, conversations: [] };
  }

  try {
    const raw = window.localStorage.getItem(getChatStorageKey(userId));
    return normalizeStoredChats(raw ? JSON.parse(raw) : null);
  } catch {
    return { activeConversationId: null, conversations: [] };
  }
}

function writeStoredChats(userId, payload) {
  if (!userId || typeof window === "undefined") return;
  window.localStorage.setItem(getChatStorageKey(userId), JSON.stringify(payload));
}


function buildHistoryFromMessages(messages) {
  let nextHistory = "";

  for (let index = 0; index < messages.length; index += 1) {
    const current = messages[index];
    const next = messages[index + 1];

    if (current?.role === "user" && next?.role === "assistant") {
      nextHistory += `\nUser: ${current.content}\nAssistant: ${next.content}`;
      index += 1;
    }
  }

  return nextHistory;
}

function isAdminRole(role) {
  return role === "admin" || role === "super_admin";
}

const AUTH_VIEWS = new Set(["login", "register", "update-password", "set-password"]);
const ADMIN_VIEWS = new Set([
  "admin",
  "admin-documents",
  "admin-test",
  "admin-queries",
  "admin-analytics",
  "admin-management",
  "admin-history",
  "admin-faqs",
]);

function getAuthenticatedView(currentView, role) {
  if (isAdminRole(role)) {
    return ADMIN_VIEWS.has(currentView) || currentView === "settings" ? currentView : "admin";
  }

  return AUTH_VIEWS.has(currentView) || ADMIN_VIEWS.has(currentView) ? "chat" : currentView;
}

function applyStoredAccentColor() {
  if (typeof window === "undefined") return;

  const accentColor = window.localStorage.getItem("accentColor") || "blue";
  applyAccentColor(accentColor);
}

function App() {
  const [messages, setMessages] = useState([]);
  const [, setHistory] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentView, setCurrentView] = useState("chat");
  const [user, setUser] = useState(null);
  const [showGuestLimitModal, setShowGuestLimitModal] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const isAdminUser =
    isAdminRole(user?.user_metadata?.role) || isAdminRole(user?.app_metadata?.role);
  const userId = user?.id ?? null;

  const guestMessageCount = user ? 0 : messages.filter((message) => message.role === "user").length;
  const guestLimitReached = !user && guestMessageCount >= 5;

  useEffect(() => {
    if (guestLimitReached) {
      setShowGuestLimitModal(true);
    }
  }, [guestLimitReached]);

  useEffect(() => {
    applyStoredAccentColor();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      
      const role = session?.user?.user_metadata?.role || session?.user?.app_metadata?.role;
      if (isAdminRole(role)) {
        setCurrentView((view) => getAuthenticatedView(view, role));
      } else if (!session?.user) {
        setCurrentView("login");
      } else {
        setCurrentView((view) => getAuthenticatedView(view, role));
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      
      if (_event === 'PASSWORD_RECOVERY') {
        setCurrentView("update-password");
      } else if (_event === 'SIGNED_IN') {
        const role = session?.user?.user_metadata?.role || session?.user?.app_metadata?.role;
        setCurrentView((view) => getAuthenticatedView(view, role));
      } else if (_event === 'SIGNED_OUT') {
        setCurrentView("login");
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const shouldUseStoredChats = userId && !isAdminUser;

    if (!shouldUseStoredChats) {
      setMessages([]);
      setHistory("");
      setConversations([]);
      setCurrentConversationId(null);
      return;
    }

    const storedChats = readStoredChats(userId);
    const activeConversation = storedChats.conversations.find(
      (conversation) => conversation.id === storedChats.activeConversationId,
    );

    setConversations(storedChats.conversations);
    setCurrentConversationId(activeConversation?.id ?? null);
    setMessages(activeConversation?.messages ?? []);
    setHistory(buildHistoryFromMessages(activeConversation?.messages ?? []));
  }, [userId, isAdminUser]);

  useEffect(() => {
    if (!userId || isAdminUser) return;

    writeStoredChats(userId, {
      activeConversationId: currentConversationId,
      conversations,
    });
  }, [conversations, currentConversationId, userId, isAdminUser]);

  const openConversation = (conversationId) => {
    const selectedConversation = conversations.find(
      (conversation) => conversation.id === conversationId,
    );

    if (!selectedConversation) return;

    setCurrentConversationId(selectedConversation.id);
    setMessages(selectedConversation.messages);
    setHistory(buildHistoryFromMessages(selectedConversation.messages));
    setCurrentView("chat");
    setIsSidebarOpen(false);
  };

  const startNewChat = () => {
    setMessages([]);
    setHistory("");
    setCurrentConversationId(null);
    setCurrentView("chat");
    setIsSidebarOpen(false);
  };

  const deleteConversation = async (conversationId) => {
    if (!user || isAdminUser) return;

    const conversationToDelete = conversations.find(
      (conversation) => conversation.id === conversationId,
    );

    setConversations((prev) => {
      const nextConversations = prev.filter(
        (conversation) => conversation.id !== conversationId,
      );

      if (currentConversationId === conversationId) {
        setCurrentConversationId(null);
        setMessages([]);
        setHistory("");
      }

      return nextConversations;
    });

    await deleteChatActivity({
      user,
      conversation: conversationToDelete,
    });
  };

  const persistConversationMessages = (nextMessages) => {
    if (!user || isAdminUser) return;

    const timestamp = new Date().toISOString();
    const conversationId = currentConversationId ?? createConversationId();
    const nextConversation = {
      id: conversationId,
      title: createConversationTitle(nextMessages),
      updatedAt: timestamp,
      messages: nextMessages,
    };

    setCurrentConversationId(conversationId);
    setConversations((prev) => {
      const withoutCurrent = prev.filter((conversation) => conversation.id !== conversationId);
      return [nextConversation, ...withoutCurrent].sort(
        (left, right) => new Date(right.updatedAt) - new Date(left.updatedAt),
      );
    });

    return conversationId;
  };

  const submitMessage = async (input, options = {}) => {
    const { replaceFromIndex = null } = options;
    if (!input.trim()) return;

    if (replaceFromIndex === null && guestLimitReached) {
      setShowGuestLimitModal(true);
      return;
    }

    const baseMessages =
      replaceFromIndex === null ? messages : messages.slice(0, replaceFromIndex);
    const baseHistory = buildHistoryFromMessages(baseMessages);
    const userMsg = { role: "user", content: input };
    const pendingMessages = [...baseMessages, userMsg];
    setMessages(pendingMessages);
    setHistory(baseHistory);

    setLoading(true);

    try {
      const data = await sendMessage(input, baseHistory);

      const botMsg = {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        suggested_questions: data.suggested_questions,
        suggestion_topic: data.suggestion_topic,
      };

      const completedMessages = [...pendingMessages, botMsg];
      setMessages(completedMessages);
      setHistory(baseHistory + `\nUser: ${input}\nAssistant: ${data.answer}`);
      const conversationId = persistConversationMessages(completedMessages);
      await logChatActivity({
        user,
        question: input,
        answer: data.answer,
        conversationId,
      });
    } catch (error) {
      const errorText = error?.message || "Something went wrong. Please try again.";
      const failedMessages = [
        ...pendingMessages,
        { role: "assistant", content: `⚠️ ${errorText}` },
      ];
      setMessages(failedMessages);
      setHistory(buildHistoryFromMessages(failedMessages));
      persistConversationMessages(failedMessages);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = (input) => submitMessage(input);

  const handleEditMessage = (index, content) =>
    submitMessage(content, { replaceFromIndex: index });

  return (
    <div className="flex h-dvh overflow-hidden bg-gray-50 transition-colors dark:bg-slate-900 dark:text-slate-100">
      <Toaster />
      {isSidebarOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-sm md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      <Sidebar
        setMessages={setMessages}
        setHistory={setHistory}
        setCurrentView={setCurrentView}
        currentView={currentView}
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={openConversation}
        onDeleteConversation={deleteConversation}
        onNewChat={startNewChat}
        user={user}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />
     <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
  <button
    type="button"
    aria-label="Open navigation"
    onClick={() => setIsSidebarOpen(true)}
    className="fixed left-3 top-3 z-20 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/95 text-slate-700 shadow-sm backdrop-blur transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-100 dark:hover:bg-slate-800 md:hidden"
  >
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </svg>
  </button>
  {currentView === "settings" ? (
<Settings setCurrentView={setCurrentView} user={user} />
  ) : currentView === "admin" ? (
    <AdminDashboard user={user} />

  ) : currentView === "admin-documents" ? (
    <AdminDocuments user={user} />

  ) : currentView === "admin-test" ? (
    <AdminTest user={user} />

  ) : currentView === "admin-queries" ? (
    <AdminQueries user={user} />

  ) : currentView === "admin-analytics" ? (
    <AdminAnalytics user={user} />

  ) : currentView === "admin-management" ? (
    <AdminManagement user={user} />

  ) : currentView === "admin-history" ? (
    <AdminHistory user={user} />

  ) : currentView === "admin-faqs" ? (
    <AdminDashboard user={user} /> /* FAQs not implemented yet – fallback to dashboard */

  ) : currentView === "update-password" ? (
    <UpdatePassword setCurrentView={setCurrentView} />

  ) : currentView === "set-password" ? (
    <SetPassword setCurrentView={setCurrentView} />

  ) : currentView === "login" || currentView === "register" ? (
    <Auth
      isLoginView={currentView === "login"}
      setCurrentView={setCurrentView}
      setUser={setUser}
    />

  ) : (
    <>
      <ChatWindow
        messages={messages}
        loading={loading}
        onSend={handleSend}
        onEditMessage={handleEditMessage}
        setCurrentView={setCurrentView}
        user={user}
        onOpenSidebar={() => setIsSidebarOpen(true)}
      />

      <InputBox
        onSend={handleSend}
        loading={loading}
        disabled={guestLimitReached}
      />
    </>
  )}
</div>

      {showGuestLimitModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-[28px] border border-white/10 bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="bg-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft mb-4 flex h-12 w-12 items-center justify-center rounded-2xl">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 9v4" />
                <path d="M12 17h.01" />
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
              </svg>
            </div>
            <h3 className="text-2xl font-semibold text-slate-900 dark:text-white">
              Guest limit reached
            </h3>
            <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
              You have reached a 5 message limit. Please login to continue.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <button
                onClick={() => {
                  setShowGuestLimitModal(false);
                  setCurrentView("login");
                }}
                className="bg-accent hover:bg-accent-dark rounded-full px-5 py-2.5 text-sm font-medium text-white transition-colors cursor-pointer"
              >
                Login
              </button>
              <button
                onClick={() => {
                  setShowGuestLimitModal(false);
                  setCurrentView("register");
                }}
                className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 cursor-pointer dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Sign Up
              </button>
              <button
                onClick={() => setShowGuestLimitModal(false)}
                className="rounded-full px-5 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:text-slate-700 cursor-pointer dark:text-slate-400 dark:hover:text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
