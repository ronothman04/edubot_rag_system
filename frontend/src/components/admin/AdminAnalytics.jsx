import { useEffect, useMemo, useState } from "react";
import { supabase } from "../../supabaseClient";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const CATEGORY_COLORS = {
  Courses: "#3b82f6",
  Admissions: "#22c55e",
  Fees: "#f59e0b",
  Hostel: "#8b5cf6",
  Faculty: "#ec4899",
  Others: "#94a3b8",
};

function getCategory(question = "", savedCategory = "") {
  if (savedCategory && savedCategory.trim()) return savedCategory;

  const text = question.toLowerCase();

  if (/(course|program|subject|class|bca|bcom|degree)/.test(text)) return "Courses";
  if (/(admission|apply|eligib|enroll|application)/.test(text)) return "Admissions";
  if (/(fee|tuition|scholarship|payment|cost)/.test(text)) return "Fees";
  if (/(hostel|accommodation|room|dorm)/.test(text)) return "Hostel";
  if (/(faculty|teacher|professor|principal|hod)/.test(text)) return "Faculty";

  return "Others";
}

function isAnswered(log) {
  if (typeof log.is_answered === "boolean") return log.is_answered;
  return Boolean(log.answer && log.answer.trim());
}

function getDayKey(date) {
  return date.toISOString().slice(0, 10);
}

function getDayLabel(date) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function buildDailyData(logs, days = 7) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const buckets = Array.from({ length: days }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (days - index - 1));

    return {
      key: getDayKey(date),
      day: getDayLabel(date),
      queries: 0,
      unanswered: 0,
    };
  });

  const lookup = new Map(buckets.map((item) => [item.key, item]));

  logs.forEach((log) => {
    if (!log.created_at) return;

    const date = new Date(log.created_at);
    if (Number.isNaN(date.getTime())) return;

    const key = getDayKey(date);
    const bucket = lookup.get(key);

    if (bucket) {
      bucket.queries += 1;

      if (!isAnswered(log)) {
        bucket.unanswered += 1;
      }
    }
  });

  return buckets;
}

function buildCategoryData(logs) {
  const counts = {};

  logs.forEach((log) => {
    const category = getCategory(log.question, log.category);
    counts[category] = (counts[category] || 0) + 1;
  });

  return Object.entries(counts)
    .map(([name, value]) => ({
      name,
      value,
      color: CATEGORY_COLORS[name] || CATEGORY_COLORS.Others,
    }))
    .sort((a, b) => b.value - a.value);
}

function buildTopicData(logs) {
  const topics = {};

  logs.forEach((log) => {
    const category = getCategory(log.question, log.category);
    topics[category] = (topics[category] || 0) + 1;
  });

  return Object.entries(topics)
    .map(([topic, count]) => ({ topic, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
}

function StatCard({ title, value, subtitle }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
      <p className="text-sm text-gray-600 dark:text-slate-400">{title}</p>
      <h2 className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">{value}</h2>
      <p className="mt-1 text-xs text-gray-500 dark:text-slate-500">{subtitle}</p>
    </div>
  );
}

function AdminAnalytics() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");

  const fetchAnalytics = async () => {
    setLoading(true);
    setNotice("");

    let result = await supabase
      .from("chat_logs")
      .select(
        "id, user_id, user_email, question, answer, category, is_answered, response_time_ms, created_at"
      )
      .order("created_at", { ascending: false })
      .limit(500);

    // Fallback if your table does not have category/is_answered/response_time_ms yet
    if (result.error && /category|is_answered|response_time_ms/i.test(result.error.message)) {
      result = await supabase
        .from("chat_logs")
        .select("id, user_id, user_email, question, answer, created_at")
        .order("created_at", { ascending: false })
        .limit(500);
    }

    if (result.error) {
      console.error(result.error.message);
      setLogs([]);
      setNotice('Could not load analytics. Make sure the "chat_logs" table exists in Supabase.');
    } else {
      setLogs(result.data || []);
    }

    setLoading(false);
  };

  useEffect(() => {
    fetchAnalytics();

    const channel = supabase
      .channel("admin-analytics-page")
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "chat_logs",
        },
        () => {
          fetchAnalytics();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const stats = useMemo(() => {
    const totalQueries = logs.length;
    const answered = logs.filter(isAnswered).length;
    const unanswered = totalQueries - answered;

    const activeUsers = new Set(
      logs.map((log) => log.user_id || log.user_email).filter(Boolean)
    ).size;

    const responseTimes = logs
      .map((log) => log.response_time_ms)
      .filter((value) => typeof value === "number");

    const averageResponseTime =
      responseTimes.length > 0
        ? Math.round(
            responseTimes.reduce((sum, value) => sum + value, 0) / responseTimes.length
          )
        : 0;

    return {
      totalQueries,
      answered,
      unanswered,
      activeUsers,
      averageResponseTime,
    };
  }, [logs]);

  const dailyData = useMemo(() => buildDailyData(logs), [logs]);
  const categoryData = useMemo(() => buildCategoryData(logs), [logs]);
  const topicData = useMemo(() => buildTopicData(logs), [logs]);
  const failedQuestions = useMemo(
    () => logs.filter((log) => !isAnswered(log)).slice(0, 8),
    [logs]
  );

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-950 dark:text-white sm:text-3xl">Analytics</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
              Detailed reports from Supabase chat activity.
            </p>
          </div>

          <button
            onClick={fetchAnalytics}
            className="bg-accent-soft-dark border-accent-soft text-accent-soft hover:bg-accent-soft rounded-xl border px-4 py-3 text-sm font-medium"
          >
            Refresh Analytics
          </button>
        </div>

        {notice && (
          <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-5 py-4 text-sm text-amber-100">
            {notice}
          </div>
        )}

        {loading ? (
          <p className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-500 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400">
            Loading analytics...
          </p>
        ) : (
          <>
            <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
              <StatCard
                title="Total Queries"
                value={stats.totalQueries}
                subtitle="Last 500 records"
              />
              <StatCard
                title="Answered"
                value={stats.answered}
                subtitle="Questions with valid answer"
              />
              <StatCard
                title="Unanswered"
                value={stats.unanswered}
                subtitle="Needs admin review"
              />
              <StatCard
                title="Active Users"
                value={stats.activeUsers}
                subtitle="Unique users in logs"
              />
              <StatCard
                title="Avg. Response"
                value={
                  stats.averageResponseTime
                    ? `${stats.averageResponseTime}ms`
                    : "N/A"
                }
                subtitle="Requires response_time_ms"
              />
            </section>

            <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1.4fr_0.8fr]">
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
                <div className="mb-5">
                  <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
                    Queries Per Day
                  </h2>
                  <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                    Daily query and unanswered trend.
                  </p>
                </div>

                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={dailyData}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="day" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" allowDecimals={false} />
                      <Tooltip
                        contentStyle={{
                          background: "#0f172a",
                          border: "1px solid #334155",
                          borderRadius: "12px",
                          color: "#fff",
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="queries"
                        stroke="#3b82f6"
                        strokeWidth={3}
                      />
                      <Line
                        type="monotone"
                        dataKey="unanswered"
                        stroke="#f59e0b"
                        strokeWidth={3}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
                <div className="mb-5">
                  <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
                    Queries by Category
                  </h2>
                  <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                    Topic distribution from student questions.
                  </p>
                </div>

                {categoryData.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-slate-400">
                    No category data available.
                  </p>
                ) : (
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={categoryData}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={75}
                          outerRadius={115}
                          paddingAngle={2}
                        >
                          {categoryData.map((entry) => (
                            <Cell key={entry.name} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "#0f172a",
                            border: "1px solid #334155",
                            borderRadius: "12px",
                            color: "#fff",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </section>

            <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
                <div className="mb-5">
                  <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
                    Most Asked Topics
                  </h2>
                  <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                    Highest frequency categories.
                  </p>
                </div>

                {topicData.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-slate-400">No topics yet.</p>
                ) : (
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={topicData} layout="vertical">
                        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                        <XAxis type="number" stroke="#94a3b8" allowDecimals={false} />
                        <YAxis
                          type="category"
                          dataKey="topic"
                          stroke="#94a3b8"
                          width={100}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "#0f172a",
                            border: "1px solid #334155",
                            borderRadius: "12px",
                            color: "#fff",
                          }}
                        />
                        <Bar dataKey="count" fill="#3b82f6" radius={[0, 8, 8, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
                <div className="mb-5">
                  <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
                    Unanswered Questions
                  </h2>
                  <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                    Questions where the assistant could not provide an answer.
                  </p>
                </div>

                {failedQuestions.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-slate-400">
                    No unanswered questions found.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {failedQuestions.map((log) => (
                      <div
                        key={log.id}
                        className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/60"
                      >
                        <p className="text-sm font-medium text-gray-900 dark:text-slate-200">
                          {log.question}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-slate-500">
                          {log.user_email || "Unknown user"} ·{" "}
                          {new Date(log.created_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

export default AdminAnalytics;
