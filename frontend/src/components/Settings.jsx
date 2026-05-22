import { useState, useEffect } from "react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";
import { ACCENT_COLORS, applyAccentColor } from "../themeAccent";

export default function Settings({ setCurrentView, user }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isEditingProfile, setIsEditingProfile] = useState(false);

  const [profile, setProfile] = useState({
    fullName: "",
    email: "",
    password: "",
  });

  const [originalProfile, setOriginalProfile] = useState(null);

  const [accentColor, setAccentColor] = useState(() => {
    return localStorage.getItem("accentColor") || "blue";
  });

  const [pendingAccentColor, setPendingAccentColor] = useState(accentColor);

  const isAdmin =
    user?.user_metadata?.role === "admin" ||
    user?.app_metadata?.role === "admin" ||
    user?.user_metadata?.role === "super_admin" ||
    user?.app_metadata?.role === "super_admin";

  function saveAccentColor() {
    localStorage.setItem("accentColor", pendingAccentColor);
    applyAccentColor(pendingAccentColor);
    setAccentColor(pendingAccentColor);
    toast.success("Accent color applied to all pages!");
  }

  function cancelAccentColor() {
    setPendingAccentColor(accentColor);
  }

  async function getProfile() {
    setLoading(true);

    const {
      data: { user: authUser },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !authUser) {
      setLoading(false);
      return;
    }

    const { data, error: profileError } = await supabase
      .from("profiles")
      .select("email, full_name, role")
      .eq("id", authUser.id)
      .single();

    const mapped = {
      fullName: profileError
        ? authUser.user_metadata?.full_name || ""
        : data?.full_name || authUser.user_metadata?.full_name || "",
      email: profileError ? authUser.email : data?.email || authUser.email,
      password: "",
    };

    setProfile(mapped);
    setOriginalProfile(mapped);
    setLoading(false);
  }

  useEffect(() => {
    queueMicrotask(() => {
      getProfile();
    });
  }, []);

  useEffect(() => {
    localStorage.setItem("accentColor", accentColor);
    applyAccentColor(accentColor);
  }, [accentColor]);

  async function updateProfile() {
    setSaving(true);

    const {
      data: { user: authUser },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !authUser) {
      toast.error("User not found.");
      setSaving(false);
      return;
    }

    const cleanEmail = profile.email.trim();
    const cleanFullName = profile.fullName.trim().replace(/\s+/g, " ");

    if (!cleanEmail) {
      toast.error("Email address is required.");
      setSaving(false);
      return;
    }

    if (!cleanFullName) {
      toast.error("Full name is required.");
      setSaving(false);
      return;
    }

    if (profile.password.trim()) {
      if (profile.password.length < 6) {
        toast.error("Password must be at least 6 characters.");
        setSaving(false);
        return;
      }

      const { error: authError } = await supabase.auth.updateUser({
        password: profile.password,
      });

      if (authError) {
        toast.error("Error updating password: " + authError.message);
        setSaving(false);
        return;
      }
    }

    const { error: metadataError } = await supabase.auth.updateUser({
      data: {
        ...authUser.user_metadata,
        full_name: cleanFullName,
      },
    });

    if (metadataError) {
      toast.error("Error updating profile name: " + metadataError.message);
      setSaving(false);
      return;
    }

    const { error } = await supabase.from("profiles").upsert({
      id: authUser.id,
      email: cleanEmail,
      full_name: cleanFullName,
    });

    setSaving(false);

    if (error) {
      toast.error(error.message || "Failed to save settings.");
      return;
    }

    const updatedProfile = {
      fullName: cleanFullName,
      email: cleanEmail,
      password: "",
    };

    setProfile(updatedProfile);
    setOriginalProfile(updatedProfile);
    setIsEditingProfile(false);

    toast.success("Profile updated successfully!");
  }

  function cancelEditProfile() {
    setProfile(originalProfile || { fullName: "", email: "", password: "" });
    setIsEditingProfile(false);
  }

  const isDirty =
    originalProfile &&
    (profile.fullName !== originalProfile.fullName ||
      profile.email !== originalProfile.email ||
      profile.password.trim() !== "");

  const initials = (profile.fullName || profile.email)?.charAt(0).toUpperCase() || "U";

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <svg
            className="h-8 w-8 animate-spin text-accent"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />

            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>

          <p className="text-sm text-gray-500 dark:text-gray-400">
            Loading profile...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full w-full overflow-y-auto bg-gray-50 px-4 pb-8 pt-16 text-gray-900 transition-colors dark:bg-gray-900 dark:text-white sm:px-6 md:pt-8">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header */}
        <div className="rounded-[22px] border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800 sm:rounded-[28px] sm:p-7">
          <button
            onClick={() => setCurrentView(isAdmin ? "admin" : "chat")}
            className="mb-6 flex items-center gap-2 text-sm font-medium text-gray-500 transition hover:text-accent dark:text-gray-400 dark:hover:text-accent"
          >
            ← {isAdmin ? "Back to Admin Dashboard" : "Back to Chat"}
          </button>

          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            {isAdmin ? "Control Panel" : "User Preferences"}
          </p>

          <h1 className="mt-3 text-2xl font-bold text-gray-950 dark:text-white sm:text-3xl">
            {isAdmin ? "Admin Settings" : "Settings"}
          </h1>

          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500 dark:text-gray-400">
            {isAdmin
              ? "Manage admin profile, dashboard accent color, and control panel preferences."
              : "Manage your account, accent color, and chatbot preferences."}
          </p>
        </div>

        {/* Profile Card */}
        <div className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-5">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent text-2xl font-bold text-white shadow-lg">
                {initials}
              </div>

              <div>
                <h2 className="text-xl font-bold text-gray-950 dark:text-white">
                  {profile.fullName || profile.email || "Guest"}
                </h2>

                {profile.fullName && (
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    {profile.email}
                  </p>
                )}

                <span className="mt-2 inline-flex rounded-full border border-accent px-3 py-1 text-xs font-semibold text-accent">
                  {isAdmin ? "Administrator" : "User"}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="rounded-2xl border border-gray-100 bg-gray-50 px-5 py-3 dark:border-gray-700 dark:bg-gray-900">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Email Address
                </p>

                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                  {profile.email}
                </p>
              </div>

              <button
                onClick={() =>
                  isEditingProfile
                    ? cancelEditProfile()
                    : setIsEditingProfile(true)
                }
                className="rounded-2xl border border-gray-200 px-5 py-3 text-sm font-semibold text-gray-700 transition hover:border-accent hover:text-accent dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                {isEditingProfile ? "Cancel" : "Edit Profile"}
              </button>
            </div>
          </div>
        </div>

        {/* Edit Profile Form */}
        {isEditingProfile && (
          <div className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="text-lg font-bold text-gray-950 dark:text-white">
              Edit Profile
            </h3>

            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Update your profile name, email address, or password.
            </p>

            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Full Name
                </label>

                <input
                  type="text"
                  value={profile.fullName}
                  onChange={(e) =>
                    setProfile({ ...profile, fullName: e.target.value })
                  }
                  className="w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Email Address
                </label>

                <input
                  type="email"
                  value={profile.email}
                  onChange={(e) =>
                    setProfile({ ...profile, email: e.target.value })
                  }
                  className="w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                />
              </div>

              <div>
                {/* <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  New Password
                </label>

                <input
                  type="password"
                  placeholder="Leave blank to keep current password"
                  value={profile.password}
                  onChange={(e) =>
                    setProfile({ ...profile, password: e.target.value })
                  }
                  className="w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-accent focus:ring-4 focus:ring-accent dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                /> */}
              </div>
            </div>

            <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                onClick={cancelEditProfile}
                disabled={saving}
                className="rounded-2xl border border-gray-200 px-5 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                Cancel
              </button>

              <button
                onClick={updateProfile}
                disabled={!isDirty || saving}
                className={`rounded-2xl px-5 py-3 text-sm font-semibold text-white transition ${
                  isDirty
                    ? "bg-accent hover:opacity-90"
                    : "cursor-not-allowed bg-gray-300 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                }`}
              >
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        )}

        {/* Appearance */}
        <div className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="text-lg font-bold text-gray-950 dark:text-white">
            Appearance
          </h3>

          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Customize the look and feel of the application.
          </p>

          <div className="mt-6">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">
              Accent Color
            </p>

            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Choose your preferred highlight color.
            </p>

            <div className="mt-4 flex flex-wrap gap-3">
              {["blue", "purple", "green", "orange", "red"].map((color) => (
                <button
                  key={color}
                  type="button"
                  onClick={() => setPendingAccentColor(color)}
                  className={`flex h-8 w-8 items-center justify-center rounded-full transition ${
                    pendingAccentColor === color
                      ? "scale-110 ring-2 ring-gray-400 ring-offset-2 dark:ring-offset-gray-800"
                      : "hover:scale-105"
                  }`}
                  style={{ backgroundColor: ACCENT_COLORS[color].light }}
                  title={color}
                >
                  {pendingAccentColor === color && (
                    <svg
                      className="h-4 w-4 text-white"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                </button>
              ))}
            </div>

            {pendingAccentColor !== accentColor && (
              <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <button
                  onClick={cancelAccentColor}
                  className="rounded-2xl border border-gray-200 px-5 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>

                <button
                  onClick={saveAccentColor}
                  className="rounded-2xl bg-accent px-5 py-3 text-sm font-semibold text-white transition hover:opacity-90"
                >
                  Apply to All Pages
                </button>
              </div>
            )}
          </div>
        </div>

     

        
      </div>
    </div>
  );
}
