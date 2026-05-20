import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import { supabase } from "../supabaseClient";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatDate(value) {
  if (!value) return "Unknown";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";

  return date.toLocaleString();
}

function formatShortDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(value);
}

function formatRelativeTime(value) {
  if (!value) return "Unknown";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";

  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  if (Math.abs(diffMinutes) < 60) {
    return formatter.format(diffMinutes, "minute");
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return formatter.format(diffHours, "hour");
  }

  const diffDays = Math.round(diffHours / 24);
  return formatter.format(diffDays, "day");
}

function truncateText(value, maxLength = 100) {
  if (!value) return "";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}

function getCategory(question = "") {
  const normalized = question.toLowerCase();

  if (/(course|program|subject|class|bca|bcom|degree)/.test(normalized)) return "Courses";
  if (/(admission|apply|eligib|enroll|application)/.test(normalized)) return "Admissions";
  if (/(fee|tuition|scholarship|payment|cost)/.test(normalized)) return "Fees";
  if (/(hostel|accommodation|room|dorm)/.test(normalized)) return "Hostel";

  return "Others";
}

function buildDailySeries(chatLogs, days = 7) {
  const end = new Date();
  end.setHours(0, 0, 0, 0);

  const buckets = Array.from({ length: days }, (_, index) => {
    const date = new Date(end);
    date.setDate(end.getDate() - (days - index - 1));
    return {
      key: date.toISOString().slice(0, 10),
      label: formatShortDate(date),
      value: 0,
    };
  });

  const lookup = new Map(buckets.map((item) => [item.key, item]));

  chatLogs.forEach((log) => {
    if (!log.created_at) return;
    const key = new Date(log.created_at).toISOString().slice(0, 10);
    const bucket = lookup.get(key);
    if (bucket) bucket.value += 1;
  });

  return buckets;
}

function buildCategorySeries(chatLogs) {
  const counts = chatLogs.reduce((acc, log) => {
    const category = getCategory(log.question);
    acc[category] = (acc[category] || 0) + 1;
    return acc;
  }, {});

  const palette = {
    Courses: "#3b82f6",
    Admissions: "#4ade80",
    Fees: "#fbbf24",
    Hostel: "#8b5cf6",
    Others: "#94a3b8",
  };

  return Object.entries(counts)
    .map(([label, value]) => ({
      label,
      value,
      color: palette[label] || "#94a3b8",
    }))
    .sort((a, b) => b.value - a.value);
}

function buildLinePath(values, width, height, padding) {
  if (!values.length) return "";

  const maxValue = Math.max(...values, 1);
  return values
    .map((value, index) => {
      const x =
        padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
      const y =
        height - padding - (value / maxValue) * Math.max(height - padding * 2, 1);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function polarToCartesian(cx, cy, radius, angleInDegrees) {
  const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(angleInRadians),
    y: cy + radius * Math.sin(angleInRadians),
  };
}

function describeArc(cx, cy, radius, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function StatIcon({ type }) {
  const className = "h-5 w-5 text-white";

  if (type === "documents") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
        <path d="M7 3h7l5 5v13H7z" />
        <path d="M14 3v6h6" />
        <path d="M10 13h4" />
        <path d="M10 17h4" />
      </svg>
    );
  }

  if (type === "queries") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
        <path d="M8 10h8" />
        <path d="M8 14h5" />
        <path d="M6 5h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-4l-4 3v-3H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z" />
      </svg>
    );
  }

  if (type === "unanswered") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 9a2.5 2.5 0 1 1 4.27 1.77c-.85.84-1.52 1.39-1.52 2.73" />
        <path d="M12 17h.01" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="4" />
      <path d="M20 8v6" />
      <path d="M23 11h-6" />
    </svg>
  );
}

function AdminDashboard({ user }) {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [testResponse, setTestResponse] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [analyticsNotice, setAnalyticsNotice] = useState("");
  const [profiles, setProfiles] = useState([]);
  const [chatLogs, setChatLogs] = useState([]);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_URL}/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  };

  const fetchAnalytics = async () => {
    setAnalyticsLoading(true);
    setAnalyticsNotice("");

    try {
      const [{ data: profileData, error: profileError }, { data: chatData, error: chatError }] =
        await Promise.all([
          supabase.from("profiles").select("uuid, email"),
          supabase
            .from("chat_logs")
            .select("id, user_id, user_email, question, answer, created_at")
            .order("created_at", { ascending: false })
            .limit(50),
        ]);

      if (profileError) {
        console.warn("Failed to load profiles:", profileError.message);
      } else {
        setProfiles(profileData || []);
      }

      if (chatError) {
        console.warn("Failed to load chat analytics:", chatError.message);
        setChatLogs([]);
        setAnalyticsNotice(
          'Chat analytics table not available yet. Create a "chat_logs" table in Supabase to see user chat activity here.'
        );
      } else {
        setChatLogs(chatData || []);
      }
    } catch (error) {
      console.error("Failed to fetch analytics:", error);
      setAnalyticsNotice("Failed to load analytics data.");
    } finally {
      setAnalyticsLoading(false);
    }
  };

  useEffect(() => {
    queueMicrotask(() => {
      fetchDocuments();
      fetchAnalytics();
    });
  }, []);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    const toastId = toast.loading(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || "Upload successful", { id: toastId });
        fetchDocuments();
      } else {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Upload failed");
      }
    } catch (error) {
      toast.error(`Error: ${error.message}`, { id: toastId });
    } finally {
      setUploading(false);
      e.target.value = null;
    }
  };

  const handleDelete = async (filename) => {
    const toastId = toast.loading(`Deleting ${filename}...`);
    try {
      const res = await fetch(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      });

      if (res.ok) {
        toast.success("Deleted successfully", { id: toastId });
        fetchDocuments();
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to delete document");
      }
    } catch (error) {
      toast.error(error.message, { id: toastId });
    }
  };

  const handleTestQuery = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsQuerying(true);
    setTestResponse("");
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, history: "" }),
      });

      if (res.ok) {
        const data = await res.json();
        setTestResponse(data.answer || "No response received");
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || "Query failed");
      }
    } catch (error) {
      setTestResponse(`Error: ${error.message}`);
    } finally {
      setIsQuerying(false);
    }
  };

  const totalUsers = profiles.length;
  const totalQueries = chatLogs.length;
  const activeUsers = new Set(
    chatLogs.map((log) => log.user_id || log.user_email).filter(Boolean)
  ).size;
  const unansweredCount = chatLogs.filter((log) => !log.answer || !log.answer.trim()).length;

  const dailySeries = buildDailySeries(chatLogs);
  const totalThisWeek = dailySeries.reduce((sum, item) => sum + item.value, 0);
  const averagePerDay = totalThisWeek ? (totalThisWeek / dailySeries.length).toFixed(1) : "0.0";
  const categorySeries = buildCategorySeries(chatLogs);
  const totalCategories = categorySeries.reduce((sum, item) => sum + item.value, 0);
  const linePath = buildLinePath(
    dailySeries.map((item) => item.value),
    640,
    250,
    28
  );

  const analyticsCards = [
    {
      label: "Total Documents",
      value: documents.length,
      accent: "from-blue-500 to-blue-400",
      icon: "documents",
      note: "Knowledge base uploaded",
    },
    {
      label: "Total Queries",
      value: totalQueries,
      accent: "from-emerald-500 to-emerald-400",
      icon: "queries",
      note: "Retrieved from Supabase",
    },
    {
      label: "Unanswered Questions",
      value: unansweredCount,
      accent: "from-amber-400 to-orange-400",
      icon: "unanswered",
      note: "Needs review",
    },
    {
      label: "Active Users",
      value: activeUsers || totalUsers,
      accent: "from-violet-500 to-fuchsia-400",
      icon: "users",
      note: `${totalUsers} registered users`,
    },
  ];

  const recentQuestions = chatLogs.slice(0, 5);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="relative overflow-hidden rounded-[22px] border border-gray-200 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.08),_transparent_32%),linear-gradient(180deg,#ffffff,#f8fafc)] p-4 shadow-sm dark:border-white/10 dark:bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))] dark:shadow-[0_24px_80px_rgba(2,6,23,0.55)] sm:rounded-[28px] sm:p-6">
          <div className="absolute inset-0 bg-[linear-gradient(120deg,transparent,rgba(15,23,42,0.03),transparent)] dark:bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.03),transparent)]" />
          <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-accent-soft text-xs font-semibold uppercase tracking-[0.24em] opacity-80">
                Analytics Overview
              </p>
              <h1 className="mt-3 text-2xl font-semibold tracking-tight text-gray-950 dark:text-white sm:text-4xl">
                Dashboard
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-gray-600 dark:text-slate-300">
                Welcome back, {user?.email?.split("@")[0] || "Admin"}. This layout keeps the
                existing dashboard logic and reads analytics from Supabase.
              </p>
            </div>

            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
              <div className="rounded-2xl border border-gray-200 bg-white/90 px-4 py-3 text-sm text-gray-700 backdrop-blur dark:border-white/10 dark:bg-white/5 dark:text-slate-200">
                <div className="text-xs uppercase tracking-[0.22em] text-gray-500 dark:text-slate-400">Admin</div>
                <div className="mt-1 font-medium text-gray-950 dark:text-white">{user?.email || "Unknown"}</div>
              </div>
              <button
                onClick={fetchAnalytics}
                className="bg-accent-soft-dark border-accent-soft text-accent-soft hover:bg-accent-soft cursor-pointer rounded-2xl border px-4 py-3 text-sm font-medium transition"
              >
                Refresh analytics
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {analyticsCards.map((card) => (
            <div
              key={card.label}
              className="rounded-[24px] border border-gray-200 bg-white p-5 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/[0.03] dark:shadow-[0_16px_50px_rgba(15,23,42,0.28)]"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-gray-600 dark:text-slate-400">{card.label}</p>
                  <p className="mt-3 text-4xl font-semibold tracking-tight text-gray-950 dark:text-white">
                    {analyticsLoading ? "--" : card.value}
                  </p>
                  <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">{card.note}</p>
                </div>
                <div
                  className={`flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br ${card.accent} shadow-lg shadow-slate-950/30`}
                >
                  <StatIcon type={card.icon} />
                </div>
              </div>
            </div>
          ))}
        </div>

        {analyticsNotice && (
          <div className="rounded-[22px] border border-amber-400/20 bg-amber-400/10 px-5 py-4 text-sm text-amber-100">
            {analyticsNotice}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.3fr_0.7fr]">
          <div className="rounded-[22px] border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:rounded-[28px] sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Query Analytics</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                  Last 7 days of activity from `chat_logs`.
                </p>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-2 text-sm text-gray-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                This week
              </div>
            </div>

            {analyticsLoading ? (
              <p className="mt-8 text-sm text-gray-500 dark:text-slate-400">Loading analytics...</p>
            ) : (
              <>
                <div className="mt-8">
                  <svg viewBox="0 0 640 250" className="h-[260px] w-full">
                    {[0, 1, 2, 3].map((step) => {
                      const y = 28 + step * 58;
                      return (
                        <line
                          key={step}
                          x1="28"
                          y1={y}
                          x2="612"
                          y2={y}
                          stroke="rgba(148,163,184,0.12)"
                        />
                      );
                    })}

                    {dailySeries.map((item, index) => {
                      const x = 28 + (index * (640 - 56)) / Math.max(dailySeries.length - 1, 1);
                      return (
                        <text
                          key={item.label}
                          x={x}
                          y="238"
                          fill="rgba(148,163,184,0.9)"
                          fontSize="12"
                          textAnchor="middle"
                        >
                          {item.label}
                        </text>
                      );
                    })}

                    <path d={linePath} fill="none" stroke="var(--accent-color)" strokeWidth="3" strokeLinecap="round" />

                    {dailySeries.map((item, index) => {
                      const maxValue = Math.max(...dailySeries.map((entry) => entry.value), 1);
                      const x = 28 + (index * (640 - 56)) / Math.max(dailySeries.length - 1, 1);
                      const y = 250 - 28 - (item.value / maxValue) * (250 - 56);

                      return (
                        <g key={item.key}>
                          <circle cx={x} cy={y} r="5" fill="var(--accent-color)" />
                          <text x={x} y={y - 12} fill="currentColor" fontSize="12" textAnchor="middle" className="text-gray-600 dark:text-slate-200">
                            {item.value}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-4 border-t border-gray-200 pt-4 text-sm dark:border-white/10">
                  <div>
                    <p className="text-gray-600 dark:text-slate-400">Total Queries</p>
                    <p className="text-accent-soft mt-1 text-2xl font-semibold">{totalThisWeek}</p>
                  </div>
                  <div>
                    <p className="text-gray-600 dark:text-slate-400">Average per day</p>
                    <p className="text-accent-soft mt-1 text-2xl font-semibold">{averagePerDay}</p>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="rounded-[22px] border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:rounded-[28px] sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Queries by Category</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">Keyword-based grouping from user questions.</p>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-2 text-sm text-gray-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                Supabase
              </div>
            </div>

            {analyticsLoading ? (
              <p className="mt-8 text-sm text-gray-500 dark:text-slate-400">Loading categories...</p>
            ) : totalCategories === 0 ? (
              <p className="mt-8 text-sm text-gray-500 dark:text-slate-400">No tracked questions yet.</p>
            ) : (
              <div className="mt-8 grid gap-6 lg:grid-cols-[260px_1fr] xl:grid-cols-1">
                <div className="mx-auto flex w-full max-w-[260px] items-center justify-center">
                  <svg viewBox="0 0 220 220" className="h-[220px] w-[220px]">
                    <circle cx="110" cy="110" r="72" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="26" />
                    {categorySeries.reduce(
                      (acc, item) => {
                        const startAngle = acc.angle;
                        const sweep = (item.value / totalCategories) * 360;
                        const endAngle = startAngle + sweep;

                        acc.paths.push(
                          <path
                            key={item.label}
                            d={describeArc(110, 110, 72, startAngle, endAngle)}
                            fill="none"
                            stroke={item.color}
                            strokeWidth="26"
                            strokeLinecap="butt"
                          />
                        );
                        acc.angle = endAngle;
                        return acc;
                      },
                      { angle: 0, paths: [] }
                    ).paths}
                    <text x="110" y="104" textAnchor="middle" fill="currentColor" fontSize="34" fontWeight="600" className="text-gray-950 dark:text-white">
                      {totalCategories}
                    </text>
                    <text x="110" y="128" textAnchor="middle" fill="#94a3b8" fontSize="15">
                      Total
                    </text>
                  </svg>
                </div>

                <div className="space-y-3">
                  {categorySeries.map((item) => {
                    const percent = ((item.value / totalCategories) * 100).toFixed(1);
                    return (
                      <div key={item.label} className="flex items-center gap-3">
                        <span
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: item.color }}
                        />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-slate-200">{item.label}</p>
                          <p className="text-sm text-gray-600 dark:text-slate-400">
                            {item.value} ({percent}%)
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[22px] border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:rounded-[28px] sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Recent Student Questions</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">Most recent queries.</p>
              </div>
              <div className="text-accent-soft text-sm">{totalQueries} total</div>
            </div>

            <div className="mt-6 space-y-3">
              {analyticsLoading ? (
                <p className="text-sm text-gray-500 dark:text-slate-400">Loading recent questions...</p>
              ) : recentQuestions.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-slate-400">No recent questions yet.</p>
              ) : (
                recentQuestions.map((log) => {
                  const name = log.user_email || "Unknown user";
                  const initial = name.charAt(0).toUpperCase();
                  return (
                    <div
                      key={log.id}
                      className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-white/8 dark:bg-slate-950/30 sm:flex-row sm:items-start sm:gap-4"
                    >
                      <div className="bg-accent flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white">
                        {initial}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                          {truncateText(log.question, 140)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">{name}</p>
                      </div>
                      <div className="shrink-0 text-xs text-gray-500 dark:text-slate-400">
                        {formatRelativeTime(log.created_at)}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="rounded-[22px] border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:rounded-[28px] sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Top Asked Topics</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">Simple category ranking from stored questions.</p>
              </div>
              <div className="text-accent-soft text-sm">Live</div>
            </div>

            <div className="mt-6 space-y-4">
              {analyticsLoading ? (
                <p className="text-sm text-gray-500 dark:text-slate-400">Loading topics...</p>
              ) : categorySeries.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-slate-400">No topics available yet.</p>
              ) : (
                categorySeries.map((item) => {
                  const width = totalCategories ? (item.value / totalCategories) * 100 : 0;
                  return (
                    <div key={item.label}>
                      <div className="mb-2 flex items-center justify-between text-sm">
                        <span className="text-gray-900 dark:text-slate-200">{item.label}</span>
                        <span className="text-gray-600 dark:text-slate-400">{item.value}</span>
                      </div>
                      <div className="h-3 overflow-hidden rounded-full bg-gray-200 dark:bg-slate-800">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${width}%`, backgroundColor: item.color }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
          {/* not needed */}
        {/* <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold text-white">Document Management</h2>
                <p className="mt-1 text-sm text-slate-400">Upload or remove documents without changing the backend flow.</p>
              </div>
              <div className="text-sm text-slate-400">{documents.length} files</div>
            </div>

            <div className="mt-6 rounded-2xl border border-dashed border-white/15 bg-slate-950/30 p-4">
              <label className="mb-3 block text-sm font-medium text-slate-200">
                Upload New Document (PDF)
              </label>
              <input
                type="file"
                accept="application/pdf"
                onChange={handleFileUpload}
                disabled={uploading}
                className="block w-full cursor-pointer rounded-xl border border-white/10 bg-slate-900/80 text-sm text-slate-300 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-500/15 file:px-4 file:py-2 file:font-medium file:text-blue-200"
              />
            </div>

            <div className="mt-5 space-y-3">
              {documents.length === 0 ? (
                <p className="text-sm text-slate-400">No documents found in ChromaDB.</p>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc}
                    className="flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-slate-950/30 px-4 py-3"
                  >
                    <p className="truncate text-sm text-slate-200">{doc}</p>
                    <button
                      onClick={() => handleDelete(doc)}
                      className="cursor-pointer rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 transition hover:bg-red-500/20"
                    >
                      Delete
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
              <h2 className="text-xl font-semibold text-white">RAG Playground</h2>
              <p className="mt-1 text-sm text-slate-400">
                Test the assistant against the uploaded knowledge base.
              </p>

              <form onSubmit={handleTestQuery} className="mt-6 flex flex-col gap-3">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Test a query against your uploaded documents..."
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-blue-400/50"
                />
                <button
                  type="submit"
                  disabled={isQuerying || !query.trim()}
                  className="cursor-pointer rounded-2xl bg-blue-500 px-5 py-3 text-sm font-medium text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isQuerying ? "Testing..." : "Send Query"}
                </button>
              </form>

              {testResponse && (
                <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Model Response
                  </p>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                    {testResponse}
                  </p>
                </div>
              )}
            </div>

            <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
              <h2 className="text-xl font-semibold text-white">Tracked Users</h2>
              <p className="mt-1 text-sm text-slate-400">User list from the `profiles` table.</p>

              <div className="mt-5 space-y-3">
                {analyticsLoading ? (
                  <p className="text-sm text-slate-400">Loading users...</p>
                ) : profiles.length === 0 ? (
                  <p className="text-sm text-slate-400">No users found.</p>
                ) : (
                  profiles.slice(0, 6).map((profile) => (
                    <div
                      key={profile.uuid || profile.email}
                      className="rounded-2xl border border-white/8 bg-slate-950/30 px-4 py-3"
                    >
                      <p className="truncate text-sm font-medium text-white">
                        {profile.email || "Unknown email"}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        ID: {truncateText(profile.uuid || "Unknown", 18)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div> */}

       
      </div>
    </div>
  );
}

export default AdminDashboard;
