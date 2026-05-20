import React, { useEffect, useState } from "react";
import { supabase } from "../../supabaseClient";
import { toast } from "react-hot-toast";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function AdminManagement({ user }) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [admins, setAdmins] = useState([]);
  const [invites, setInvites] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  async function fetchAdmins() {
    const { data, error } = await supabase
      .from("profiles")
      .select("id, email, role, created_at")
      .in("role", ["admin", "super_admin"])
      .order("created_at", { ascending: false });

    if (error) {
      console.error(error.message);
      return [];
    }

    return data || [];
  }

  async function fetchInvites() {
    const { data, error } = await supabase
      .from("admin_invites")
      .select("id, email, role, status, created_at")
      .eq("status", "pending")
      .order("created_at", { ascending: false });

    if (error) {
      console.error(error.message);
      return [];
    }

    return data || [];
  }

  async function fetchLogs() {
    const { data, error } = await supabase
      .from("admin_activity_logs")
      .select("id, action, target_email, created_at")
      .order("created_at", { ascending: false })
      .limit(10);

    if (error) {
      console.error(error.message);
      return [];
    }

    return data || [];
  }

  async function loadAdminManagement() {
    setLoading(true);

    const [adminsData, invitesData, logsData] = await Promise.all([
      fetchAdmins(),
      fetchInvites(),
      fetchLogs(),
    ]);

    setAdmins(adminsData);
    setInvites(invitesData);
    setLogs(logsData);

    setLoading(false);
  }

  useEffect(() => {
    loadAdminManagement();
  }, []);

  async function inviteAdmin() {
    if (!inviteEmail.trim()) {
      toast.error("Enter an email address.");
      return;
    }

    setInviting(true);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        throw new Error("You must be logged in to invite an admin.");
      }

      const res = await fetch(`${API_URL}/admin/invite-admin`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: "admin",
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || data.error || "Failed to invite admin.");
      }

      toast.success("Admin invite sent.");
      setInviteEmail("");
      loadAdminManagement();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setInviting(false);
    }
  }

  async function cancelInvite(inviteId) {
    const { error } = await supabase
      .from("admin_invites")
      .update({ status: "cancelled" })
      .eq("id", inviteId);

    if (error) {
      toast.error("Failed to cancel invite.");
      return;
    }

    toast.success("Invite cancelled.");
    loadAdminManagement();
  }

  async function removeAdmin(profileId) {
    const confirmRemove = window.confirm("Remove admin access for this user?");
    if (!confirmRemove) return;

    const { error } = await supabase
      .from("profiles")
      .update({ role: "student" })
      .eq("id", profileId);

    if (error) {
      toast.error("Failed to remove admin.");
      return;
    }

    toast.success("Admin access removed.");
    loadAdminManagement();
  }

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="rounded-3xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
          <p className="text-accent-soft text-xs font-semibold uppercase tracking-[0.24em]">
            Admin Management
          </p>

          <h1 className="mt-3 text-2xl font-bold text-gray-950 dark:text-white sm:text-3xl">
            Manage Administrators
          </h1>

          <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
            Invite new admins and control who can manage the RAG assistant.
          </p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
          <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
            Invite New Admin
          </h2>

          <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
            Enter an email address. The invited user will set their own password.
          </p>

          <div className="mt-5 flex flex-col gap-3 md:flex-row">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="teacher@example.com"
              className="focus:border-accent flex-1 rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:placeholder:text-slate-500"
            />

            <button
              onClick={inviteAdmin}
              disabled={inviting || !inviteEmail.trim()}
              className="bg-accent hover:bg-accent-dark rounded-xl px-5 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {inviting ? "Sending..." : "Send Invite"}
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
              Active Administrators
            </h2>

            <button
              onClick={loadAdminManagement}
              className="bg-accent-soft-dark border-accent-soft text-accent-soft hover:bg-accent-soft rounded-xl border px-4 py-2 text-sm font-medium"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <p className="text-sm text-gray-500 dark:text-slate-400">Loading admins...</p>
          ) : admins.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-slate-400">No admins found.</p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-slate-800">
              <div className="overflow-x-auto">
              <table className="min-w-[720px] text-left text-sm">
                <thead className="bg-gray-100 text-gray-700 dark:bg-slate-950 dark:text-slate-300">
                  <tr>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Joined</th>
                    <th className="px-4 py-3">Action</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 dark:divide-slate-800">
                  {admins.map((admin) => {
                    const isCurrentUser = admin.id === user?.id;

                    return (
                      <tr key={admin.id}>
                        <td className="px-4 py-4 text-gray-800 dark:text-slate-200">
                          {admin.email || "Unknown email"}

                          {isCurrentUser && (
                            <span className="bg-accent-soft-dark text-accent-soft ml-2 rounded-full px-2 py-1 text-xs">
                              You
                            </span>
                          )}
                        </td>

                        <td className="px-4 py-4">
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-medium ${
                              admin.role === "super_admin"
                                ? "bg-purple-500/10 text-purple-300"
                                : "bg-accent-soft-dark text-accent-soft"
                            }`}
                          >
                            {admin.role}
                          </span>
                        </td>

                        <td className="px-4 py-4 text-gray-500 dark:text-slate-400">
                          {admin.created_at
                            ? new Date(admin.created_at).toLocaleDateString()
                            : "Unknown"}
                        </td>

                        <td className="px-4 py-4">
                          {admin.role === "super_admin" || isCurrentUser ? (
                            <span className="text-xs text-gray-500 dark:text-slate-500">
                              Protected
                            </span>
                          ) : (
                            <button
                              onClick={() => removeAdmin(admin.id)}
                              className="rounded-lg bg-red-500/10 px-3 py-2 text-xs font-medium text-red-300 hover:bg-red-500/20"
                            >
                              Remove Admin
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
            <h2 className="text-xl font-semibold text-gray-950 dark:text-white">
              Pending Invitations
            </h2>

            {loading ? (
              <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">Loading invites...</p>
            ) : invites.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">
                No pending invites.
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                {invites.map((invite) => (
                  <div
                    key={invite.id}
                    className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/60 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {invite.email}
                      </p>

                      <p className="mt-1 text-xs text-gray-500 dark:text-slate-500">
                        Invited on{" "}
                        {new Date(invite.created_at).toLocaleString()}
                      </p>
                    </div>

                    <button
                      onClick={() => cancelInvite(invite.id)}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      Cancel
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
            <h2 className="text-xl font-semibold text-gray-950 dark:text-white">Activity Log</h2>

            {loading ? (
              <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">
                Loading activity...
              </p>
            ) : logs.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">
                No admin activity yet.
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                {logs.map((log) => (
                  <div
                    key={log.id}
                    className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/60"
                  >
                    <p className="text-sm text-gray-800 dark:text-slate-200">{log.action}</p>

                    <p className="mt-1 text-xs text-gray-500 dark:text-slate-500">
                      {log.target_email || "No target"} ·{" "}
                      {new Date(log.created_at).toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminManagement;
