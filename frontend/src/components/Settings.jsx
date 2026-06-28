import { useState, useEffect } from "react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";
import { ACCENT_COLORS, applyAccentColor } from "../themeAccent";

const ACCENT_OPTIONS = ["blue", "purple", "green", "orange", "red"];

const SECTIONS = [
  {
    id: "profile",
    label: "Profile",
    icon: (
      <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5Z" />
    ),
  },
  {
    id: "appearance",
    label: "Appearance",
    icon: (
      <path d="M12 3a9 9 0 0 0 0 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.2 0-.8.7-1.5 1.5-1.5H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8Zm-5.5 9a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3Zm3-4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3Zm5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3Z" />
    ),
  },
  {
    id: "security",
    label: "Security",
    icon: (
      <path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5l-8-3Zm0 6a2 2 0 0 1 2 2c0 .7-.4 1.4-1 1.7V14a1 1 0 1 1-2 0v-2.3c-.6-.3-1-1-1-1.7a2 2 0 0 1 2-2Z" />
    ),
  },
];

export default function Settings({ setCurrentView, user, profileRole }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState("profile");

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
    profileRole === "admin" ||
    profileRole === "super_admin" ||
    user?.user_metadata?.role === "admin" ||
    user?.app_metadata?.role === "admin" ||
    user?.user_metadata?.role === "super_admin" ||
    user?.app_metadata?.role === "super_admin";

  // ── Business logic (unchanged): accent color persistence ──────────────────
  function saveAccentColor() {
    localStorage.setItem("accentColor", pendingAccentColor);
    applyAccentColor(pendingAccentColor);
    setAccentColor(pendingAccentColor);
    toast.success("Accent color applied to all pages!");
  }

  function cancelAccentColor() {
    setPendingAccentColor(accentColor);
  }

  // ── Business logic (unchanged): profile fetch ─────────────────────────────
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

  // ── Business logic (unchanged): profile + password update ─────────────────
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

    toast.success("Profile updated successfully!");
  }

  function resetProfileFields() {
    setProfile(originalProfile || { fullName: "", email: "", password: "" });
  }

  // ── Dirty tracking (UI only) ──────────────────────────────────────────────
  const nameDirty =
    !!originalProfile && profile.fullName !== originalProfile.fullName;
  const emailDirty =
    !!originalProfile && profile.email !== originalProfile.email;
  const passwordDirty = profile.password.trim() !== "";
  const accentDirty = pendingAccentColor !== accentColor;

  // Preserves the original `isDirty` rule that gates the profile save call.
  const isDirty =
    originalProfile &&
    (profile.fullName !== originalProfile.fullName ||
      profile.email !== originalProfile.email ||
      profile.password.trim() !== "");

  const hasUnsavedChanges = Boolean(isDirty) || accentDirty;

  const sectionDirty = {
    profile: nameDirty || emailDirty,
    appearance: accentDirty,
    security: passwordDirty,
  };

  const initials =
    (profile.fullName || profile.email)?.charAt(0).toUpperCase() || "U";

  // ── Unified save / discard (calls existing logic, no API changes) ─────────
  async function handleSaveAll() {
    if (isDirty) {
      await updateProfile();
    }
    if (pendingAccentColor !== accentColor) {
      saveAccentColor();
    }
  }

  function handleDiscardAll() {
    resetProfileFields();
    cancelAccentColor();
  }

  function scrollToSection(id) {
    setActiveSection(id);
    if (typeof document !== "undefined") {
      document
        .getElementById(`section-${id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <svg
            className="text-accent h-8 w-8 animate-spin"
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

  const inputClass =
    "w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent dark:border-gray-700 dark:bg-gray-900 dark:text-white";

  return (
    <div className="min-h-full w-full overflow-y-auto bg-gray-50 text-gray-900 transition-colors dark:bg-gray-900 dark:text-white">
      <div className="mx-auto max-w-6xl px-4 pb-32 pt-16 sm:px-6 md:pt-10">
        {/* ── Page header ── */}
        <div className="mb-8">
          <button
            onClick={() => setCurrentView(isAdmin ? "admin" : "chat")}
            className="hover:text-accent dark:hover:text-accent mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition dark:text-gray-400"
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 19l-7-7 7-7"
              />
            </svg>
            {isAdmin ? "Back to Admin Dashboard" : "Back to Chat"}
          </button>

          <p className="text-accent text-xs font-semibold uppercase tracking-[0.2em]">
            {isAdmin ? "Control Panel" : "User Preferences"}
          </p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-gray-950 dark:text-white sm:text-3xl">
            {isAdmin ? "Admin Settings" : "Settings"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500 dark:text-gray-400">
            {isAdmin
              ? "Manage your admin profile, dashboard accent color, and account security."
              : "Manage your account, appearance, and security preferences."}
          </p>
        </div>

        {/* ── Mobile section nav (horizontal pills) ── */}
        <nav
          aria-label="Settings sections"
          className="mb-6 flex gap-2 overflow-x-auto pb-1 lg:hidden"
        >
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => scrollToSection(section.id)}
              aria-current={activeSection === section.id ? "true" : undefined}
              className={`flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition ${
                activeSection === section.id
                  ? "border-accent bg-accent-soft text-accent-strong"
                  : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
              }`}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                {section.icon}
              </svg>
              {section.label}
              {sectionDirty[section.id] && (
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true" />
              )}
            </button>
          ))}
        </nav>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[220px_1fr]">
          {/* ── Desktop sticky sidebar nav ── */}
          <aside className="hidden lg:block">
            <nav aria-label="Settings sections" className="sticky top-10 space-y-1">
              {SECTIONS.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => scrollToSection(section.id)}
                  aria-current={activeSection === section.id ? "true" : undefined}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                    activeSection === section.id
                      ? "bg-accent-soft text-accent-strong"
                      : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                  }`}
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    {section.icon}
                  </svg>
                  <span className="flex-1 text-left">{section.label}</span>
                  {sectionDirty[section.id] && (
                    <span
                      className="h-2 w-2 rounded-full bg-amber-500"
                      aria-label="Unsaved changes"
                    />
                  )}
                </button>
              ))}
            </nav>
          </aside>

          {/* ── Section content ── */}
          <div className="min-w-0 space-y-6">
            {/* ════ Profile ════ */}
            <section
              id="section-profile"
              className="scroll-mt-10 rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800"
            >
              <div className="flex items-start gap-3 border-b border-gray-100 p-5 dark:border-gray-700/60 sm:p-6">
                <div className="bg-accent-soft text-accent-strong flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    {SECTIONS[0].icon}
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-950 dark:text-white">
                      Profile
                    </h2>
                    {sectionDirty.profile && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        Unsaved
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                    Your personal information and how others see you.
                  </p>
                </div>
              </div>

              <div className="space-y-6 p-5 sm:p-6">
                {/* Identity row */}
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                  <div className="bg-accent flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl text-2xl font-bold text-white shadow-md">
                    {initials}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-lg font-semibold text-gray-950 dark:text-white">
                      {profile.fullName || profile.email || "Guest"}
                    </p>
                    <p className="truncate text-sm text-gray-500 dark:text-gray-400">
                      {profile.email}
                    </p>
                    <span className="text-accent-strong border-accent-soft bg-accent-soft mt-2 inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold">
                      {isAdmin ? "Administrator" : "User"}
                    </span>
                  </div>
                </div>

                {/* Editable fields */}
                <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                  <div>
                    <label
                      htmlFor="settings-fullname"
                      className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      Full name
                    </label>
                    <input
                      id="settings-fullname"
                      type="text"
                      value={profile.fullName}
                      onChange={(e) =>
                        setProfile({ ...profile, fullName: e.target.value })
                      }
                      aria-describedby="settings-fullname-help"
                      className={inputClass}
                    />
                    <p
                      id="settings-fullname-help"
                      className="mt-1.5 text-xs text-gray-500 dark:text-gray-400"
                    >
                      Shown across the app and on your messages.
                    </p>
                  </div>

                  <div>
                    <label
                      htmlFor="settings-email"
                      className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      Email address
                    </label>
                    <input
                      id="settings-email"
                      type="email"
                      value={profile.email}
                      onChange={(e) =>
                        setProfile({ ...profile, email: e.target.value })
                      }
                      aria-describedby="settings-email-help"
                      className={inputClass}
                    />
                    <p
                      id="settings-email-help"
                      className="mt-1.5 text-xs text-gray-500 dark:text-gray-400"
                    >
                      Used for sign-in and important notifications.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* ════ Appearance ════ */}
            <section
              id="section-appearance"
              className="scroll-mt-10 rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800"
            >
              <div className="flex items-start gap-3 border-b border-gray-100 p-5 dark:border-gray-700/60 sm:p-6">
                <div className="bg-accent-soft text-accent-strong flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    {SECTIONS[1].icon}
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-950 dark:text-white">
                      Appearance
                    </h2>
                    {sectionDirty.appearance && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        Unsaved
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                    Customize the look and feel of the application.
                  </p>
                </div>
              </div>

              <div className="p-5 sm:p-6">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  Accent color
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Choose your preferred highlight color. Applies across every page.
                </p>

                <div className="mt-4 flex flex-wrap gap-3" role="group" aria-label="Accent color">
                  {ACCENT_OPTIONS.map((color) => {
                    const selected = pendingAccentColor === color;
                    return (
                      <button
                        key={color}
                        type="button"
                        onClick={() => setPendingAccentColor(color)}
                        aria-pressed={selected}
                        aria-label={`Accent color ${color}`}
                        title={color.charAt(0).toUpperCase() + color.slice(1)}
                        className={`flex h-9 w-9 items-center justify-center rounded-full transition focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2 dark:focus:ring-offset-gray-800 ${
                          selected
                            ? "scale-110 ring-2 ring-gray-400 ring-offset-2 dark:ring-offset-gray-800"
                            : "hover:scale-105"
                        }`}
                        style={{ backgroundColor: ACCENT_COLORS[color].light }}
                      >
                        {selected && (
                          <svg
                            className="h-4 w-4 text-white"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            aria-hidden="true"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2.5}
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>

            {/* ════ Security ════ */}
            <section
              id="section-security"
              className="scroll-mt-10 rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800"
            >
              <div className="flex items-start gap-3 border-b border-gray-100 p-5 dark:border-gray-700/60 sm:p-6">
                <div className="bg-accent-soft text-accent-strong flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    {SECTIONS[2].icon}
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-950 dark:text-white">
                      Security
                    </h2>
                    {sectionDirty.security && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        Unsaved
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                    Manage your password and account security.
                  </p>
                </div>
              </div>

              <div className="p-5 sm:p-6">
                <div className="max-w-md">
                  <label
                    htmlFor="settings-password"
                    className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    New password
                  </label>
                  <input
                    id="settings-password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Leave blank to keep current password"
                    value={profile.password}
                    onChange={(e) =>
                      setProfile({ ...profile, password: e.target.value })
                    }
                    aria-describedby="settings-password-help"
                    className={`${inputClass} placeholder:text-gray-400`}
                  />
                  <p
                    id="settings-password-help"
                    className="mt-1.5 text-xs text-gray-500 dark:text-gray-400"
                  >
                    Must be at least 6 characters. Leave empty if you don&apos;t want to change it.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>

      {/* ── Sticky unsaved-changes save bar ── */}
      {hasUnsavedChanges && (
        <div className="sticky bottom-0 z-20 border-t border-gray-200 bg-white/90 backdrop-blur dark:border-gray-700 dark:bg-gray-900/90">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              <span aria-live="polite">You have unsaved changes</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleDiscardAll}
                disabled={saving}
                className="rounded-xl border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
              >
                Discard
              </button>
              <button
                type="button"
                onClick={handleSaveAll}
                disabled={saving}
                className="bg-accent hover:bg-accent-dark inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving && (
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                )}
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
