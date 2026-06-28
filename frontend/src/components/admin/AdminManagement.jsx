import { useEffect, useState } from "react";
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

  async function getAccessToken() {
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.access_token) {
      throw new Error("You must be logged in as an admin.");
    }

    return session.access_token;
  }

  async function adminRequest(path, options = {}) {
    const accessToken = await getAccessToken();
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(options.headers || {}),
      },
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || data.error || "Admin request failed.");
    }

    return data;
  }

  async function loadAdminManagement() {
    setLoading(true);

    try {
      const data = await adminRequest("/admin/management");
      setAdmins(data.admins || []);
      setInvites(data.invites || []);
      setLogs(data.logs || []);
    } catch (error) {
      toast.error(error.message || "Failed to load admin management.");
      setAdmins([]);
      setInvites([]);
      setLogs([]);
    } finally {
      setLoading(false);
    }
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
      const data = await adminRequest("/admin/invite-admin", {
        method: "POST",
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: "admin",
        }),
      });

      toast.success(data.message || "Admin invite sent.");
      setInviteEmail("");
      loadAdminManagement();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setInviting(false);
    }
  }

  async function cancelInvite(inviteId) {
    try {
      const data = await adminRequest(`/admin/invites/${inviteId}/cancel`, {
        method: "PATCH",
      });

      toast.success(data.message || "Invite cancelled.");
      loadAdminManagement();
    } catch (error) {
      toast.error(error.message || "Failed to cancel invite.");
    }
  }

  async function removeAdmin(profileId) {
    const confirmRemove = window.confirm("Remove admin access for this user?");
    if (!confirmRemove) return;

    try {
      const data = await adminRequest("/admin/remove-admin", {
        method: "PATCH",
        body: JSON.stringify({ profile_id: profileId }),
      });

      toast.success(data.message || "Admin access removed.");
      loadAdminManagement();
    } catch (error) {
      toast.error(error.message || "Failed to remove admin.");
    }
  }

  return (
    <div className="min-w-0 flex-1 overflow-y-auto bg-gray-50 px-3 pb-6 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-5 md:pt-6">
      <div className="mx-auto w-full max-w-6xl space-y-5">
        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 sm:p-6">
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

        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 sm:p-6">
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
              className="bg-accent hover:bg-accent-dark rounded-xl px-5 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 md:w-auto"
            >
              {inviting ? "Sending..." : "Send Invite"}
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 sm:p-6">
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
              <div className="w-full overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
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
                      <tr key={admin.id || admin.email}>
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
                              disabled={!admin.id}
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
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 sm:p-6">
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

          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60 sm:p-6">
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
