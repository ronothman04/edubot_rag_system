import { useState, useEffect, useRef } from "react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import InputBox from "./components/InputBox";
import Settings from "./components/Settings";
import Auth from "./components/Auth";
import UpdatePassword from "./components/UpdatePassword";
import AdminDashboard from "./components/AdminDashboard";
import AdminDocuments from "./components/admin/AdminDocuments";
import WebsiteCrawler from "./components/admin/AdminWebCrawl";
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


const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const CHAT_STORAGE_PREFIX = "chat_history:";
const ACTIVE_CHAT_SESSION_PREFIX = "active_chat_session:";

function getChatStorageKey(userId) {
  return `${CHAT_STORAGE_PREFIX}${userId}`;
}

function getActiveChatSessionKey(userId) {
  return `${ACTIVE_CHAT_SESSION_PREFIX}${userId}`;
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

function readActiveChatSessionId(userId) {
  if (!userId || typeof window === "undefined") return null;

  try {
    return window.sessionStorage.getItem(getActiveChatSessionKey(userId));
  } catch {
    return null;
  }
}

function writeActiveChatSessionId(userId, conversationId) {
  if (!userId || typeof window === "undefined") return;

  try {
    const key = getActiveChatSessionKey(userId);

    if (conversationId) {
      window.sessionStorage.setItem(key, conversationId);
    } else {
      window.sessionStorage.removeItem(key);
    }
  } catch {
    // Chat history persistence should keep working even if sessionStorage is unavailable.
  }
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

async function fetchProfileRole(session) {
  if (!session?.access_token || !session?.user?.id) return null;

  try {
    const response = await fetch(`${API_URL}/auth/profile-role`, {
      headers: {
        Authorization: `Bearer ${session.access_token}`,
      },
    });

    const data = await response.json().catch(() => ({}));

    if (response.ok) {
      return data.role || null;
    }

    console.warn(data.detail || data.error || "Failed to load profile role.");
  } catch (error) {
    console.warn("Failed to load profile role:", error.message);
  }

  const { data, error } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", session.user.id)
    .maybeSingle();

  if (error) {
    console.warn("Failed to load profile role:", error.message);
    return null;
  }

  return data?.role || null;
}

const AUTH_VIEWS = new Set(["login", "register", "update-password", "set-password"]);
const ADMIN_VIEWS = new Set([
  "admin",
  "admin-documents",
  "admin-crawl",
  "admin-test",
  "admin-queries",
  "admin-analytics",
  "admin-management",
  "admin-history",
  "admin-faqs",
]);

function getAuthenticatedView(currentView, role) {
  if (currentView === "set-password" || currentView === "update-password") {
    return currentView;
  }

  if (isAdminRole(role)) {
    return ADMIN_VIEWS.has(currentView) || currentView === "settings" ? currentView : "admin";
  }

  return AUTH_VIEWS.has(currentView) || ADMIN_VIEWS.has(currentView) ? "chat" : currentView;
}

function getViewFromPath() {
  if (typeof window === "undefined") return null;

  const pathView = window.location.pathname.replace(/^\/+/, "").replace(/\/+$/, "");
  return AUTH_VIEWS.has(pathView) || ADMIN_VIEWS.has(pathView) || pathView === "settings"
    ? pathView
    : null;
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
  const [sessionLoading, setSessionLoading] = useState(true);
  const [currentView, setCurrentView] = useState(() => getViewFromPath() || "login");
  const [user, setUser] = useState(null);
  const [profileRole, setProfileRole] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window !== "undefined") {
      return window.localStorage.getItem("sidebar_collapsed") === "true";
    }
    return false;
  });
  const abortControllerRef = useRef(null);

  const isAdminUser =
    isAdminRole(profileRole) ||
    isAdminRole(user?.user_metadata?.role) ||
    isAdminRole(user?.app_metadata?.role);
  const userId = user?.id ?? null;

  const handleToggleSidebarCollapse = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem("sidebar_collapsed", String(next));
      return next;
    });
  };

  useEffect(() => {
    applyStoredAccentColor();

    let ignore = false;

    async function applySession(session) {
      const authUser = session?.user ?? null;
      const pathView = getViewFromPath();

      if (!authUser) {
        if (!ignore) {
          setUser(null);
          setProfileRole(null);
          setCurrentView(pathView && AUTH_VIEWS.has(pathView) ? pathView : "login");
        }
        return;
      }

      const roleFromProfile = await fetchProfileRole(session);
      const role =
        roleFromProfile || authUser.user_metadata?.role || authUser.app_metadata?.role;

      if (!ignore) {
        setUser(authUser);
        setProfileRole(roleFromProfile);
        setCurrentView((view) => getAuthenticatedView(pathView || view, role));
      }
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      applySession(session).finally(() => {
        if (!ignore) {
          setSessionLoading(false);
        }
      });
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (_event === 'PASSWORD_RECOVERY') {
        setUser(session?.user ?? null);
        setCurrentView("update-password");
      } else if (_event === 'SIGNED_IN') {
        // Always start with a blank chat on login, not the last active conversation.
        if (session?.user?.id) {
          writeActiveChatSessionId(session.user.id, null);
        }
        applySession(session).finally(() => {
          if (!ignore) {
            setSessionLoading(false);
          }
        });
      } else if (_event === 'SIGNED_OUT') {
        setUser(null);
        setProfileRole(null);
        setCurrentView("login");
        setMessages([]);
        setHistory("");
        setConversations([]);
        setCurrentConversationId(null);
        setSessionLoading(false);
      }
    });

    return () => {
      ignore = true;
      subscription.unsubscribe();
    };
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
    const activeSessionConversationId = readActiveChatSessionId(userId);
    const activeConversation = storedChats.conversations.find(
      (conversation) => conversation.id === activeSessionConversationId,
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

  // Auth Guard: if not loading, check if unauthenticated user is trying to access chat/settings/admin views.
  useEffect(() => {
    if (sessionLoading) return;
    if (!user) {
      const pathView = getViewFromPath();
      if (AUTH_VIEWS.has(currentView)) {
        return;
      }
      if (!pathView || !AUTH_VIEWS.has(pathView)) {
        setCurrentView("login");
      }
    }
  }, [user, sessionLoading, currentView]);

  const openConversation = (conversationId) => {
    const selectedConversation = conversations.find(
      (conversation) => conversation.id === conversationId,
    );

    if (!selectedConversation) return;

    setCurrentConversationId(selectedConversation.id);
    writeActiveChatSessionId(userId, selectedConversation.id);
    setMessages(selectedConversation.messages);
    setHistory(buildHistoryFromMessages(selectedConversation.messages));
    setCurrentView("chat");
    setIsSidebarOpen(false);
  };

  const startNewChat = () => {
    setMessages([]);
    setHistory("");
    setCurrentConversationId(null);
    writeActiveChatSessionId(userId, null);
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
        writeActiveChatSessionId(userId, null);
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
    writeActiveChatSessionId(userId, conversationId);
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

    const baseMessages =
      replaceFromIndex === null ? messages : messages.slice(0, replaceFromIndex);
    const baseHistory = buildHistoryFromMessages(baseMessages);
    const userMsg = { role: "user", content: input };
    const pendingMessages = [...baseMessages, userMsg];
    setMessages(pendingMessages);
    setHistory(baseHistory);

    // Set up a fresh abort controller so the user can stop this generation.
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);

    try {
      const data = await sendMessage(input, baseHistory, { signal: controller.signal });

      const botMsg = {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        suggested_questions: data.suggested_questions,
        suggestion_topic: data.suggestion_topic,
        response_type: data.response_type,
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
      // User-initiated stop: leave the existing messages as-is (the user's
      // message stays visible) and don't surface an error bubble.
      if (error?.name === "AbortError") {
        return;
      }

      const errorText = error?.message || "Something went wrong. Please try again.";
      const failedMessages = [
        ...pendingMessages,
        { role: "assistant", content: `⚠️ ${errorText}` },
      ];
      setMessages(failedMessages);
      setHistory(buildHistoryFromMessages(failedMessages));
      persistConversationMessages(failedMessages);
    } finally {
      abortControllerRef.current = null;
      setLoading(false);
    }
  };

  const handleStop = () => {
    // Abort the in-flight request and instantly clear the loading state so the
    // UI reverts to the Send button right away.
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setLoading(false);
  };

  const handleSend = (input) => submitMessage(input);

  const handleEditMessage = (index, content) =>
    submitMessage(content, { replaceFromIndex: index });

  if (sessionLoading) {
    return (
      <div className="flex h-dvh w-screen items-center justify-center bg-gray-50 dark:bg-slate-950 transition-colors">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-[var(--accent-color)] dark:border-slate-800" style={{ borderTopColor: 'var(--accent-color, #2563eb)' }}></div>
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400 animate-pulse">Loading EduBot...</p>
        </div>
      </div>
    );
  }

  const isAuthView = AUTH_VIEWS.has(currentView);

  return (
    <div className="flex h-dvh overflow-hidden bg-gray-50 transition-colors dark:bg-slate-900 dark:text-slate-100">
      <Toaster />
      {isSidebarOpen && !isAuthView && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-sm md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      {!isAuthView && (
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
          profileRole={profileRole}
          isOpen={isSidebarOpen}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleSidebarCollapse}
          onClose={() => setIsSidebarOpen(false)}
        />
      )}
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {currentView !== "login" && currentView !== "register" && currentView !== "update-password" && currentView !== "set-password" && currentView !== "chat" && (
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
        )}
        {currentView === "settings" ? (
          <Settings setCurrentView={setCurrentView} user={user} profileRole={profileRole} />
        ) : currentView === "admin" ? (
          <AdminDashboard user={user} />

        ) : currentView === "admin-documents" ? (
          <AdminDocuments user={user} />

        ) : currentView === "admin-crawl" ? (
          <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-8 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-8">
            <div className="mx-auto max-w-6xl">
              <WebsiteCrawler onCrawlComplete={() => {}} setCurrentView={setCurrentView} />
            </div>
          </div>

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
              onStop={handleStop}
              loading={loading}
              disabled={false}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default App;
