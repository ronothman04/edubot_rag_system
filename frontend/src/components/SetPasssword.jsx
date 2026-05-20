import { useState } from "react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";

function UpdatePassword({ setCurrentView }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const handleUpdatePassword = async (e) => {
    e.preventDefault();

    if (!password.trim()) {
      toast.error("Enter a new password.");
      return;
    }

    if (password.length < 6) {
      toast.error("Password must be at least 6 characters.");
      return;
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    setSaving(true);

    try {
      const { error } = await supabase.auth.updateUser({
        password,
      });

      if (error) throw error;

      toast.success("Password set successfully. Please log in.");

      await supabase.auth.signOut();
      setCurrentView("login");
    } catch (error) {
      toast.error(error.message || "Failed to set password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-1 items-center justify-center bg-[#020817] px-4 text-slate-100">
      <form
        onSubmit={handleUpdatePassword}
        className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl"
      >
        <div className="mb-6">
          <div className="bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-2xl">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2"
            >
              <path d="M12 17h.01" />
              <path d="M8 11V8a4 4 0 0 1 8 0v3" />
              <rect x="5" y="11" width="14" height="10" rx="2" />
            </svg>
          </div>

          <h1 className="text-2xl font-bold text-white">Set Your Password</h1>

          <p className="mt-2 text-sm leading-6 text-slate-400">
            Create a password to activate your admin account.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300">
              New Password
            </label>

            <input
              type="password"
              placeholder="Enter new password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="focus:border-accent w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300">
              Confirm Password
            </label>

            <input
              type="password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="focus:border-accent w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
          </div>

          <button
            type="submit"
            disabled={saving}
            className="bg-accent hover:bg-accent-dark w-full rounded-xl px-5 py-3 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving..." : "Set Password"}
          </button>
        </div>

        <button
          type="button"
          onClick={() => setCurrentView("login")}
          className="mt-5 w-full text-sm text-slate-400 transition hover:text-white"
        >
          Back to login
        </button>
      </form>
    </div>
  );
}

export default UpdatePassword;
