import { useEffect, useState, useRef } from "react";
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
  profileRole,
  isOpen = false,
  isCollapsed = false,
  onToggleCollapse,
  onClose,
}) {
  const [loggingOut, setLoggingOut] = useState(false);
  const [profileFullName, setProfileFullName] = useState("");
  const [openConversationMenuId, setOpenConversationMenuId] = useState(null);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const profileMenuRef = useRef(null);

  useEffect(() => {
    if (!isCollapsed) {
      setShowProfileMenu(false);
    }
  }, [isCollapsed]);

  useEffect(() => {
    if (!showProfileMenu) return;

    function handleOutsideClick(event) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setShowProfileMenu(false);
      }
    }

    document.addEventListener("click", handleOutsideClick);
    return () => {
      document.removeEventListener("click", handleOutsideClick);
    };
  }, [showProfileMenu]);

  const { theme, toggleTheme } = useTheme();

  const isDarkMode = theme === "dark";
  const metadataFullName = user?.user_metadata?.full_name || user?.user_metadata?.name || "";
  const displayName =
    getFirstName(profileFullName || metadataFullName) ||
    (user?.email ? user.email.split("@")[0] : "");
  const initial = displayName.charAt(0).toUpperCase() || "?";

  const isAdmin =
    isAdminRole(profileRole) ||
    isAdminRole(user?.user_metadata?.role) ||
    isAdminRole(user?.app_metadata?.role);

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
      label: "Website Crawl",
      view: "admin-crawl",
      icon: <CrawlIcon />,
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
      className={`fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-r transition-all duration-300 ease-in-out md:relative md:translate-x-0 ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      } ${
        isCollapsed ? "md:w-[68px]" : "md:w-[270px]"
      } w-[270px] ${
        isAdmin
          ? "bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800/65"
          : "bg-gray-50 dark:bg-slate-900 border-slate-200 dark:border-slate-800/65"
      }`}
    >
      {/* Floating Collapse/Expand Toggle Button for Desktop */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="hidden md:flex absolute top-5 -right-3 z-50 h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-800 active:scale-95 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-300 cursor-pointer"
        aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <svg
          className={`w-3 h-3 transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* ===== Top Logo ===== */}
      <div className="flex items-center justify-between px-4 py-[14px] border-b border-gray-200/80 dark:border-slate-800/65 transition-colors">
        <div className={`flex items-center gap-[10px] ${isCollapsed ? "w-full justify-center" : ""}`}>
          <div
            className="w-9 h-9 flex items-center justify-center rounded-[10px] bg-accent shrink-0 shadow-sm transition-transform duration-200 hover:scale-105"
          >
            <GraduationIcon />
          </div>

          <div className={`transition-all duration-300 ${isCollapsed ? "md:opacity-0 md:max-w-0 md:overflow-hidden" : "opacity-100"}`}>
            <p className="text-sm font-semibold text-gray-900 dark:text-white m-0 tracking-tight whitespace-nowrap">
              {isAdmin ? "EduBot Admin" : "EduBot"}
            </p>
            <p className="text-[11px] text-gray-500 dark:text-gray-400 m-0 whitespace-nowrap">
              {isAdmin ? "RAG Control Panel" : "AI Assistant"}
            </p>
          </div>
        </div>

        {/* Mobile Close Button */}
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
        <div className={`px-4 pt-[14px] pb-2 transition-all ${isCollapsed ? "md:px-0 md:flex md:justify-center" : "md:px-4"}`}>
          <button
            onClick={onNewChat}
            data-tooltip={isCollapsed ? "New Chat" : undefined}
            className={`bg-accent border-accent hover:bg-accent-dark w-full rounded-xl py-2.5 text-[13px] font-medium flex items-center justify-center gap-1.5 border text-white transition-all duration-200 cursor-pointer shadow-sm active:scale-[0.98] ${
              isCollapsed ? "md:w-9 md:h-9 md:p-0 md:rounded-[10px]" : ""
            }`}
          >
            <span className="text-white text-base font-semibold leading-none">+</span> 
            <span className={isCollapsed ? "md:hidden" : ""}>New Chat</span>
          </button>
        </div>
      )}

      {/* ===== Scrollable Content ===== */}
      <div className="flex-1 overflow-y-auto min-h-0 py-2 scrollbar-thin">
        {/* ===== Admin Navigation ===== */}
        {isAdmin && (
          <div className={`pt-2 pb-3 transition-all ${isCollapsed ? "px-0" : "px-4"}`}>
            <div className={`mb-3 flex items-center justify-between ${isCollapsed ? "justify-center" : ""}`}>
              <p className={`text-[10px] font-bold tracking-[0.08em] text-gray-400 dark:text-slate-500 ${isCollapsed ? "md:hidden" : ""}`}>
                ADMIN
              </p>
              {!isCollapsed && (
                <span className="bg-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft rounded-full px-2 py-0.5 text-[10px] font-semibold">
                  LIVE
                </span>
              )}
            </div>

            <div className={`space-y-1.5 ${isCollapsed ? "flex flex-col items-center" : ""}`}>
              {adminNavItems.map((item) => {
                const isActive = currentView === item.view;

                return (
                  <button
                    key={item.label}
                    onClick={() => navigateTo(item.view)}
                    data-tooltip={isCollapsed ? item.label : undefined}
                    className={`text-left text-[13px] font-medium flex items-center transition-all cursor-pointer ${
                      isCollapsed 
                        ? "w-9 h-9 justify-center rounded-[10px] p-0" 
                        : "w-full rounded-xl p-2 gap-3"
                    } ${
                      isActive
                        ? "bg-accent text-white shadow-accent-soft"
                        : "hover:bg-gray-100 dark:hover:bg-slate-800 bg-transparent text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    <span
                      className={`flex shrink-0 items-center justify-center rounded-lg ${
                        isCollapsed 
                          ? "h-9 w-9 bg-transparent" 
                          : "h-8 w-8 bg-gray-200/50 dark:bg-slate-800/80"
                      } ${
                        isActive
                          ? "text-white"
                          : "text-gray-500 dark:text-gray-400"
                      }`}
                    >
                      {item.icon}
                    </span>

                    <span className={isCollapsed ? "md:hidden" : ""}>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ===== Recent Chats - only for normal users ===== */}
        {user && !isAdmin && (
          <div className={`pt-2 transition-all ${isCollapsed ? "px-0" : "px-4"}`}>
            <p className={`text-[10px] font-bold tracking-[0.08em] text-gray-400 dark:text-slate-500 mb-3 ${isCollapsed ? "md:hidden text-center" : ""}`}>
              RECENT CHATS
            </p>

            <div className={`space-y-1.5 ${isCollapsed ? "flex flex-col items-center" : ""}`}>
              {conversations.length === 0 ? (
                <p className={`text-[13px] text-gray-400 dark:text-gray-500 text-center ${isCollapsed ? "md:hidden" : ""}`}>
                  No chats yet
                </p>
              ) : (
                conversations.map((conversation) => {
                  const isActive =
                    currentView === "chat" && currentConversationId === conversation.id;

                  return (
                    <div
                      key={conversation.id}
                      data-tooltip={isCollapsed ? (conversation.title || "New Chat") : undefined}
                      className={`group relative transition-all duration-200 ${
                        isCollapsed 
                          ? "w-9 h-9 flex items-center justify-center rounded-[10px]" 
                          : "rounded-xl border w-full"
                      } ${
                        isActive
                          ? isCollapsed
                            ? "bg-accent-soft text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft"
                            : "bg-accent-soft border-accent-soft/30 text-accent-strong dark:bg-accent-soft-dark dark:text-accent-soft"
                          : isCollapsed
                            ? "hover:bg-slate-100 dark:hover:bg-slate-800/40 text-gray-700 dark:text-gray-300"
                            : "hover:border-slate-200 dark:hover:border-slate-800 hover:bg-slate-100/50 dark:hover:bg-slate-800/40 border-transparent text-gray-700 dark:text-gray-300"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => handleSelectConversation(conversation.id)}
                        className={`text-left cursor-pointer ${
                          isCollapsed 
                            ? "w-9 h-9 flex items-center justify-center p-0 rounded-[10px]" 
                            : "w-full rounded-xl py-2.5 pl-3 pr-10"
                        }`}
                      >
                        {isCollapsed ? (
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-gray-500 dark:text-gray-400 group-hover:text-accent transition-colors">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                          </svg>
                        ) : (
                          <div className="flex items-start justify-between gap-2">
                            <span className="line-clamp-1 text-[13px] font-medium leading-5 flex-1 pr-1">
                              {conversation.title || "New Chat"}
                            </span>
                            <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500 pt-0.5">
                              {formatConversationTime(conversation.updatedAt)}
                            </span>
                          </div>
                        )}
                      </button>

                      {!isCollapsed && (
                        <button
                          type="button"
                          aria-label="Open chat options"
                          onClick={(event) => {
                            event.stopPropagation();
                            setOpenConversationMenuId((currentId) =>
                              currentId === conversation.id ? null : conversation.id,
                            );
                          }}
                          className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:bg-white hover:text-gray-700 dark:hover:bg-slate-800 transition-opacity focus:opacity-100 ${
                            openConversationMenuId === conversation.id
                              ? "opacity-100"
                              : "opacity-0 group-hover:opacity-100"
                          }`}
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      )}

                      {openConversationMenuId === conversation.id && !isCollapsed && (
                        <div className="absolute right-2 top-9 z-10 min-w-[130px] rounded-xl border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-800 dark:bg-slate-900 animate-fade-in">
                          <button
                            type="button"
                            onClick={async (event) => {
                              event.stopPropagation();
                              await handleDeleteConversation(conversation.id);
                            }}
                            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/20 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
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
      </div>

      {/* ===== Bottom Section ===== */}
      <div className="mt-auto p-3 border-t border-gray-200/50 dark:border-slate-800/40 flex flex-col items-center gap-2">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          data-tooltip={isCollapsed ? (isDarkMode ? "Light Mode" : "Dark Mode") : undefined}
          className={`bg-white dark:bg-slate-900 rounded-xl py-2.5 
          flex items-center border border-gray-200 dark:border-slate-800
          hover:border-accent hover:bg-gray-50/50 dark:hover:bg-slate-800/50
          transition-all duration-200 cursor-pointer group ${
            isCollapsed 
              ? "w-9 h-9 justify-center p-0 border-transparent dark:bg-transparent shadow-none" 
              : "w-full justify-between px-3 mb-1"
          }`}
        >
          <span className={`group-hover:text-accent text-[10px] font-bold tracking-wider text-gray-500 transition-colors dark:text-gray-400 ${
            isCollapsed ? "md:hidden" : ""
          }`}>
            {isDarkMode ? "LIGHT MODE" : "DARK MODE"}
          </span>

          <span className="flex shrink-0 items-center justify-center">
            {isDarkMode ? <SunIcon /> : <MoonIcon />}
          </span>
        </button>

        {/* Settings */}
        {user && (
          <button
            onClick={() => navigateTo("settings")}
            data-tooltip={isCollapsed ? "Settings" : undefined}
            className={`bg-white dark:bg-slate-900 rounded-xl py-2.5 
            flex items-center border border-gray-200 dark:border-slate-800
            hover:border-accent hover:bg-gray-50/50 dark:hover:bg-slate-800/50
            transition-all duration-200 group cursor-pointer ${
              isCollapsed 
                ? "w-9 h-9 justify-center p-0 border-transparent dark:bg-transparent shadow-none" 
                : "w-full justify-between px-3 mb-1"
            }`}
          >
            <span className={`group-hover:text-accent text-[10px] font-bold tracking-wider text-gray-500 transition-colors dark:text-gray-400 ${
              isCollapsed ? "md:hidden" : ""
            }`}>
              SETTINGS
            </span>

            <span className="flex shrink-0 items-center justify-center">
              <SettingsIcon />
            </span>
          </button>
        )}

        {/* User Profile Card */}
        <div 
          ref={profileMenuRef}
          className={`flex items-center gap-[10px] relative ${
            isCollapsed ? "w-9 h-9 justify-center pt-0" : "w-full pt-1.5"
          }`}
        >
          {isCollapsed ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setShowProfileMenu((prev) => !prev);
              }}
              data-tooltip={!showProfileMenu ? displayName : undefined}
              className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold bg-accent shrink-0 shadow-sm transition-transform duration-200 hover:scale-105 select-none cursor-pointer"
            >
              {initial}
            </button>
          ) : (
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold bg-accent shrink-0 shadow-sm transition-transform duration-200 hover:scale-105 select-none"
            >
              {initial}
            </div>
          )}

          {!isCollapsed && (
            <div className="min-w-0 flex-1">
              <span
                className="block text-[13px] font-medium truncate text-gray-900 dark:text-gray-200"
                title={profileFullName || metadataFullName || user?.email || ""}
              >
                {displayName}
              </span>

              {isAdmin && (
                <span className="text-accent text-[10px] font-semibold tracking-wide">
                  ADMIN
                </span>
              )}
            </div>
          )}

          {user && !isCollapsed && (
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              title="Logout"
              aria-label="Logout"
              className="w-[34px] h-[34px] flex items-center justify-center rounded-lg transition-colors disabled:opacity-50 cursor-pointer bg-gray-100 hover:bg-gray-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-gray-200/50 dark:border-slate-800/40 text-gray-500 dark:text-gray-400 shrink-0"
            >
              <LogoutIcon />
            </button>
          )}

          {isCollapsed && showProfileMenu && (
            <div className="absolute left-12 bottom-0 z-50 min-w-[120px] rounded-xl border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-800 dark:bg-slate-900 animate-fade-in">
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/20 transition-colors cursor-pointer"
              >
                <LogoutIcon />
                <span>Logout</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function GraduationIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 10v6" />
      <path d="M2 10l10-5 10 5-10 5z" />
      <path d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
    </svg>
  );
}

// Fixed stroke width and styling for standard view icons to look refined
function DashboardIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
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
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
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
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function AnalyticsIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
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
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-accent"
      strokeWidth="2.5"
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
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-accent"
      strokeWidth="2.5"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="text-gray-400 group-hover:text-accent transition-colors"
      strokeWidth="2.5"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 .6 1.65 1.65 0 0 0-.38 1.06V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-.6-1 1.65 1.65 0 0 0-1.06-.38H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-.6A1.65 1.65 0 0 0 10.38 3V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.38.36.72.6 1 .31.34.69.5 1.06.5H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z" />
    </svg>
  );
}

function AdminIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
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
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      className="transition-colors group-hover:text-red-500"
      strokeWidth="2.5"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function CrawlIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
      <path d="M2 12h20" />
    </svg>
  );
}

export default Sidebar;
