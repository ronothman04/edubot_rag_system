import { useEffect, useState } from "react";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";
import { useTheme } from "../useTheme";

function isAdminRole(role) {
  return role === "admin" || role === "super_admin";
}

function formatConversationTime(value) {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function getFirstName(value) {
  return value?.trim().split(/\s+/)[0] || "";
}

function Sidebar({
  setMessages,
  setHistory,
  setCurrentView,
  currentView,
  conversations = [],
  currentConversationId,
  onSelectConversation,
  onDeleteConversation,
  onNewChat,
  user,
  isOpen = false,
  onClose,
}) {
  const [loggingOut, setLoggingOut] = useState(false);
  const [profileFullName, setProfileFullName] = useState("");
  const [openConversationMenuId, setOpenConversationMenuId] = useState(null);
  const { theme, toggleTheme } = useTheme();

  const isDarkMode = theme === "dark";
  const metadataFullName = user?.user_metadata?.full_name || user?.user_metadata?.name || "";
  const displayName =
    getFirstName(profileFullName || metadataFullName) ||
    (user?.email ? user.email.split("@")[0] : "Guest");
  const initial = displayName.charAt(0).toUpperCase();

  const isAdmin = isAdminRole(user?.user_metadata?.role) || isAdminRole(user?.app_metadata?.role);

  const navigateTo = (view) => {
    setCurrentView(view);
    onClose?.();
  };

  const handleSelectConversation = (conversationId) => {
    setOpenConversationMenuId(null);
    onSelectConversation?.(conversationId);
  };

  const handleDeleteConversation = async (conversationId) => {
    if (!user?.id) return;

    const toastId = toast.loading("Deleting chat...");

    try {
      await onDeleteConversation?.(conversationId);
      setOpenConversationMenuId(null);
      toast.success("Chat deleted", { id: toastId });
    } catch (error) {
      console.error("Failed to delete chat:", error);
      toast.error("Failed to delete chat", { id: toastId });
    }
  };

  useEffect(() => {
    if (!user?.id) {
      queueMicrotask(() => {
        setProfileFullName("");
      });
      return;
    }

    let ignore = false;

    async function loadProfileName() {
      const { data, error } = await supabase
        .from("profiles")
        .select("full_name")
        .eq("id", user.id)
        .maybeSingle();

      if (ignore) return;

      if (error) {
        console.warn("Failed to load profile full name:", error.message);
        setProfileFullName("");
        return;
      }

      setProfileFullName(data?.full_name || "");
    }

    loadProfileName();

    return () => {
      ignore = true;
    };
  }, [user?.id]);

  const handleLogout = async () => {
    if (loggingOut) return;

    setLoggingOut(true);
    const toastId = toast.loading("Logging out...");

    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;

      setMessages([]);
      setHistory("");
      setCurrentView("login");
      onClose?.();

      toast.success("Logged out successfully", { id: toastId });
    } catch (err) {
      console.error("Logout failed:", err.message);
      toast.error("Logout failed", { id: toastId });
    } finally {
      setLoggingOut(false);
    }
  };

  const adminNavItems = [
    {
      label: "Dashboard",
      view: "admin",
      icon: <DashboardIcon />,
    },
    {
      label: "Documents",
      view: "admin-documents",
      icon: <DocumentIcon />,
    },
    {
      label: "AI Chat Test",
      view: "admin-test",
      icon: <BotIcon />,
    },
   
    {
      label: "History",
      view: "admin-history",
      icon: <HistoryIcon />,
    },
    {
      label: "Analytics",
      view: "admin-analytics",
      icon: <AnalyticsIcon />,
    },
    {
      label: "Admin Management",
      view: "admin-management",
      icon: <AdminIcon />,
    },
  ];

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex w-[min(82vw,270px)] shrink-0 flex-col border-r transition-transform duration-200 md:static md:z-auto md:w-[270px] md:translate-x-0 ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      } ${
        isAdmin
          ? "bg-slate-50 dark:bg-slate-950 border-slate-400 dark:border-slate-600"
          : "bg-gray-50 dark:bg-gray-900 border-gray-400 dark:border-gray-600"
      }`}
    >
      {/* ===== Top Logo ===== */}
      <div className="flex items-center justify-between px-4 py-[14px] border-b border-gray-200 dark:border-gray-800 transition-colors">
        <div className="flex items-center gap-[10px]">
          <div
            className={`w-10 h-10 flex items-center justify-center rounded-[12px] ${
              isAdmin
                ? "bg-accent shadow-accent-soft"
                : "bg-accent"
            }`}
          >
            <GraduationIcon />
          </div>

          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-white m-0">
              {isAdmin ? "EduBot Admin" : "EduBot"}
            </p>
            <p className="text-[11px] text-gray-500 dark:text-gray-400 m-0">
              {isAdmin ? "RAG Control Panel" : "AI Assistant"}
            </p>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white md:hidden"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>

      {/* ===== New Chat ===== */}
      {!isAdmin && (
  <div className="px-4 pt-[14px] pb-2">
    <button
      onClick={() => {
        onNewChat?.();
      }}
      className="bg-accent border-accent hover:bg-accent-dark w-full rounded-xl py-[9px] text-[13px] font-medium flex items-center justify-center gap-1 border text-white transition-colors cursor-pointer"    >
      <span className="text-white">+</span> New Chat
    </button>
  </div>
)}

      {/* ===== Admin Navigation ===== */}
      {isAdmin && (
        <div className="px-4 pt-2 pb-3">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[10px] font-bold tracking-[0.08em] text-gray-500 dark:text-gray-500">
              ADMIN
            </p>

            <span className="bg-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft rounded-full px-2 py-1 text-[10px] font-semibold">
              LIVE
            </span>
          </div>

          <div className="space-y-2">
            {adminNavItems.map((item) => {
              const isActive = currentView === item.view;

              return (
                <button
                  key={item.label}
                  onClick={() => navigateTo(item.view)}
                    className={`w-full rounded-xl px-3 py-[10px] text-left text-[13px] font-medium flex items-center gap-3 transition-all cursor-pointer ${
                    isActive
                      ? "bg-accent hover:bg-accent-dark text-white shadow-accent-soft"
                      : "hover:border-accent-soft hover:bg-accent-soft hover:text-accent-strong dark:hover:bg-accent-soft-dark dark:hover:text-accent-soft border border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                      isActive
                        ? "bg-white/15 text-white"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-900 dark:text-gray-400"
                    }`}
                  >
                    {item.icon}
                  </span>

                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          <div className="bg-accent-soft border-accent-soft dark:bg-accent-soft-dark mt-4 rounded-2xl border p-4">
            <p className="text-accent-strong dark:text-accent-soft text-[13px] font-semibold">
              Realtime Analytics
            </p>
            <p className="text-accent-strong dark:text-accent-soft mt-1 text-[11px] leading-5 opacity-80">
              Reads Supabase chat logs, users, and document activity.
            </p>
          </div>
        </div>
      )}

      {/* ===== Recent - only for normal users ===== */}
      {user &&!isAdmin &&(
        <div className="px-4 pt-2">
          <p className="text-[10px] font-bold tracking-[0.08em] text-gray-500 dark:text-gray-500">
            RECENT
          </p>

          <div className="mt-3 space-y-2">
            {conversations.length === 0 ? (
              <p className="text-[13px] text-gray-400 dark:text-gray-400">
                No chats yet
              </p>
            ) : (
              conversations.map((conversation) => {
                const isActive =
                  currentView === "chat" && currentConversationId === conversation.id;

                return (
                  <div
                    key={conversation.id}
                    className={`group relative rounded-2xl border transition-all ${
                      isActive
                        ? "bg-accent-soft border-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft"
                        : "hover:border-accent-soft hover:bg-accent-soft dark:hover:bg-accent-soft-dark border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => handleSelectConversation(conversation.id)}
                      className="w-full rounded-2xl px-3 py-3 pr-10 text-left cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="line-clamp-2 text-[13px] font-medium leading-5">
                          {conversation.title || "New Chat"}
                        </span>
                        <span className="shrink-0 text-[10px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                          {formatConversationTime(conversation.updatedAt)}
                        </span>
                      </div>
                    </button>

                    <button
                      type="button"
                      aria-label="Open chat options"
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenConversationMenuId((currentId) =>
                          currentId === conversation.id ? null : conversation.id,
                        );
                      }}
                      className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-lg text-gray-500 transition hover:bg-white hover:text-gray-900 focus:opacity-100 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white ${
                        openConversationMenuId === conversation.id
                          ? "opacity-100"
                          : "opacity-0 group-hover:opacity-100"
                      }`}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>

                    {openConversationMenuId === conversation.id && (
                      <div className="absolute right-2 top-10 z-10 min-w-[140px] rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-700 dark:bg-gray-800">
                        <button
                          type="button"
                          onClick={async (event) => {
                            event.stopPropagation();
                            await handleDeleteConversation(conversation.id);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12px] font-medium text-red-600 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete chat
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ===== Bottom ===== */}
      <div className="mt-auto p-4">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="w-full bg-white dark:bg-gray-800 rounded-xl px-[14px] py-[10px] 
          flex justify-between items-center mb-3
          border border-gray-200 dark:border-gray-700
          hover:border-accent hover:bg-gray-50 dark:hover:bg-gray-700
          transition-all duration-200 cursor-pointer group"
        >
          <span className="group-hover:text-accent text-[11px] font-bold text-gray-500 transition-colors dark:text-gray-300">
            {isDarkMode ? "LIGHT MODE" : "DARK MODE"}
          </span>

          {isDarkMode ? <SunIcon /> : <MoonIcon />}
        </button>

        {/* Settings */}
        {user && (
          <button
          onClick={() => navigateTo("settings")}
          className="w-full bg-white dark:bg-gray-800 rounded-xl px-[14px] py-[10px] 
          flex justify-between items-center mb-[14px]
          border border-gray-200 dark:border-gray-700
          hover:border-accent hover:bg-gray-50 dark:hover:bg-gray-700
          transition-all duration-200 group cursor-pointer"
        >
          <span className="group-hover:text-accent text-[11px] font-bold text-gray-500 transition-colors dark:text-gray-300">
            SETTINGS
          </span>

          <SettingsIcon />
        </button>
        )}
        

        {/* User Row */}
        <div className="flex items-center gap-[10px]">
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold ${
              isAdmin
                ? "bg-accent"
                : "bg-accent"
            }`}
          >
            {initial}
          </div>

          <div className="min-w-0 flex-1">
            <span
              className="block text-[13px] font-medium truncate text-gray-900 dark:text-gray-200"
              title={profileFullName || metadataFullName || user?.email || "Guest"}
            >
              {displayName}
            </span>

            {isAdmin && (
              <span className="text-accent text-[10px] font-semibold">
                ADMIN
              </span>
            )}
          </div>

          {user && (
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              title="Logout"
              aria-label="Logout"
              className="w-[34px] h-[34px] flex items-center justify-center rounded-lg transition-colors disabled:opacity-50 cursor-pointer bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              <LogoutIcon />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}

function GraduationIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="2"
    >
      <path d="M22 10v6" />
      <path d="M2 10l10-5 10 5-10 5z" />
      <path d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
    </svg>
  );
}

function DashboardIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
      <path d="M10 9H8" />
    </svg>
  );
}

function BotIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="8" width="18" height="12" rx="2" />
      <path d="M12 2v6" />
      <path d="M8 13h.01" />
      <path d="M16 13h.01" />
      <path d="M9 17h6" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function AnalyticsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 3v18h18" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-accent"
      strokeWidth="2"
    >
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-accent"
      strokeWidth="2"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-gray-400 group-hover:text-accent transition-colors"
      strokeWidth="2"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 .6 1.65 1.65 0 0 0-.38 1.06V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-.6-1 1.65 1.65 0 0 0-1.06-.38H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-.6A1.65 1.65 0 0 0 10.38 3V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.38.36.72.6 1 .31.34.69.5 1.06.5H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z" />
    </svg>
  );
}
function AdminIcon() {
  return (
    <svg
  width="16"
  height="16"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  strokeWidth="2"
  strokeLinecap="round"
  strokeLinejoin="round"
>
  <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" />
  <path d="M4 21c0-4 3.5-7 8-7" />


  <path d="M20 13s-1.5-1-4-1-4 1-4 1v3c0 3 2 5 4 6 2-1 4-3 4-6z" />


  <path d="M15.5 17l1.5 1.5 3-3" />
</svg>
  );
}

function LogoutIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-gray-500 dark:text-gray-400"
      strokeWidth="2"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

export default Sidebar;
