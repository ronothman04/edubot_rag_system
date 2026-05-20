import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import { AlertTriangle, RefreshCw, Trash2, X } from "lucide-react";
import { supabase } from "../../supabaseClient";

function formatDate(value) {
  if (!value) return "Unknown";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";

  return date.toLocaleString();
}

function truncateText(value, maxLength = 100) {
  if (!value) return "";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}

function AdminHistory() {
  const [chatLogs, setChatLogs] = useState([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [analyticsNotice, setAnalyticsNotice] = useState("");
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);

  const fetchHistory = async () => {
    setAnalyticsLoading(true);
    setAnalyticsNotice("");

    const { data, error } = await supabase
      .from("chat_logs")
      .select("id, user_email, question, answer, created_at")
      .order("created_at", { ascending: false })
      .limit(100);

    if (error) {
      console.error(error.message);
      setChatLogs([]);
      setAnalyticsNotice('Could not load activity. Make sure the "chat_logs" table exists in Supabase.');
    } else {
      setChatLogs(data || []);
    }

    setAnalyticsLoading(false);
  };

  useEffect(() => {
    queueMicrotask(() => {
      fetchHistory();
    });
  }, []);

  const clearHistory = async () => {
    setClearingHistory(true);
    setAnalyticsNotice("");
    const toastId = toast.loading("Clearing chat history...");

    const { error } = await supabase.from("chat_logs").delete().not("id", "is", null);

    if (error) {
      console.error(error.message);
      setAnalyticsNotice("Could not clear history. Check Supabase delete permissions for chat_logs.");
      toast.error("Failed to clear history", { id: toastId });
    } else {
      setChatLogs([]);
      setClearConfirmOpen(false);
      toast.success("History cleared", { id: toastId });
    }

    setClearingHistory(false);
  };

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-950 dark:text-white sm:text-3xl">History</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
              Detailed Supabase activity log for verification and admin review.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={fetchHistory}
              disabled={analyticsLoading || clearingHistory}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-accent-soft bg-white px-4 py-3 text-sm font-medium text-accent-strong transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-60 dark:bg-accent-soft-dark dark:text-accent-soft dark:hover:bg-accent-soft dark:hover:text-white"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </button>
            <button
              type="button"
              onClick={() => setClearConfirmOpen(true)}
              disabled={analyticsLoading || clearingHistory || chatLogs.length === 0}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-600 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200 dark:hover:bg-red-500/20"
            >
              <Trash2 className="h-4 w-4" />
              <span>Clear History</span>
            </button>
          </div>
        </div>

        {analyticsNotice && (
          <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-5 py-4 text-sm text-amber-100">
            {analyticsNotice}
          </div>
        )}

        <div className="rounded-[22px] border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:rounded-[28px] sm:p-6">
          <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Raw Activity</h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
            Recent chat questions and responses stored in Supabase.
          </p>

          {analyticsLoading ? (
            <p className="mt-6 text-sm text-gray-500 dark:text-slate-400">Loading activity...</p>
          ) : chatLogs.length === 0 ? (
            <p className="mt-6 text-sm text-gray-500 dark:text-slate-400">No tracked chat activity yet.</p>
          ) : (
            <div className="mt-6 overflow-hidden rounded-2xl border border-gray-200 dark:border-white/10">
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-gray-100 text-gray-700 dark:bg-slate-900/80 dark:text-slate-300">
                    <tr>
                      <th className="px-4 py-3 font-medium">User</th>
                      <th className="px-4 py-3 font-medium">Question</th>
                      <th className="px-4 py-3 font-medium">Answer</th>
                      <th className="px-4 py-3 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white text-gray-800 dark:divide-white/5 dark:bg-slate-950/40 dark:text-slate-200">
                    {chatLogs.map((log) => (
                      <tr key={log.id} className="align-top">
                        <td className="px-4 py-4">{log.user_email || "Unknown user"}</td>
                        <td className="px-4 py-4">{truncateText(log.question, 90)}</td>
                        <td className="px-4 py-4">{truncateText(log.answer, 120)}</td>
                        <td className="px-4 py-4 text-gray-500 dark:text-slate-400">{formatDate(log.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>

      {clearConfirmOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm dark:bg-slate-950/75"
          role="dialog"
          aria-modal="true"
          aria-labelledby="clear-history-title"
        >
          <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-200">
                  <AlertTriangle className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <h2 id="clear-history-title" className="text-xl font-bold text-gray-950 dark:text-slate-100">
                    Clear all chat history?
                  </h2>
                  <p className="mt-2 text-sm font-medium text-gray-500 dark:text-slate-400">
                    This permanently deletes all rows currently stored in the Supabase chat_logs table.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setClearConfirmOpen(false)}
                disabled={clearingHistory}
                className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                aria-label="Close clear history confirmation"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setClearConfirmOpen(false)}
                disabled={clearingHistory}
                className="rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-bold text-gray-700 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={clearHistory}
                disabled={clearingHistory}
                className="rounded-lg bg-red-500 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {clearingHistory ? "Clearing..." : "Clear History"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default AdminHistory;
