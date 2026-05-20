import { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";

function AdminQueries() {
  const [chatLogs, setChatLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchQueries = async () => {
    setLoading(true);

    const { data, error } = await supabase
      .from("chat_logs")
      .select("id, user_email, question, answer, category, is_answered, created_at")
      .order("created_at", { ascending: false })
      .limit(100);

    if (error) {
      console.error(error.message);
      setChatLogs([]);
    } else {
      setChatLogs(data || []);
    }

    setLoading(false);
  };

  useEffect(() => {
    fetchQueries();
  }, []);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-950 dark:text-white sm:text-3xl">Student Queries</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
            Review questions asked by students.
          </p>
        </div>

        <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
          {loading ? (
            <p className="p-6 text-sm text-gray-500 dark:text-slate-400">Loading queries...</p>
          ) : chatLogs.length === 0 ? (
            <p className="p-6 text-sm text-gray-500 dark:text-slate-400">No queries found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] text-left text-sm">
                <thead className="bg-gray-100 text-gray-700 dark:bg-slate-950 dark:text-slate-300">
                  <tr>
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Question</th>
                    <th className="px-4 py-3">Category</th>
                    <th className="px-4 py-3">Answered</th>
                    <th className="px-4 py-3">Time</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 dark:divide-slate-800">
                  {chatLogs.map((log) => (
                    <tr key={log.id}>
                      <td className="px-4 py-4 text-gray-700 dark:text-slate-300">
                        {log.user_email || "Unknown"}
                      </td>
                      <td className="max-w-[420px] px-4 py-4 text-gray-900 dark:text-slate-200">
                        {log.question}
                      </td>
                      <td className="px-4 py-4 text-gray-700 dark:text-slate-300">
                        {log.category || "General"}
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-medium ${
                            log.is_answered === false
                              ? "bg-red-500/10 text-red-300"
                              : "bg-green-500/10 text-green-300"
                          }`}
                        >
                          {log.is_answered === false ? "No" : "Yes"}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-gray-500 dark:text-slate-400">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminQueries;
