import { useState, useEffect } from "react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";

function isAdminRole(role) {
  return role === "admin" || role === "super_admin";
}

function duplicateSignupMessage() {
  return "User already registered. Please login.";
}

function isExistingUserSignupResponse(data) {
  const identities = data?.user?.identities;
  return Array.isArray(identities) && identities.length === 0;
}

function Auth({ isLoginView, setCurrentView, setUser }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [isForgotPassword, setIsForgotPassword] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      setIsForgotPassword(false);
      setErrorMsg("");
      setFullName("");
      setPassword("");
      setShowPassword(false);
    });
  }, [isLoginView]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    setLoading(true);
    setErrorMsg("");

    const cleanEmail = email.trim().toLowerCase();
    const cleanPassword = password.trim();
    const cleanFullName = fullName.trim().replace(/\s+/g, " ");

    try {
      if (!cleanEmail) {
        throw new Error("Email is required.");
      }

      if (!isForgotPassword && !cleanPassword) {
        throw new Error("Password is required.");
      }

      if (!isForgotPassword && cleanPassword.length < 6) {
        throw new Error("Password must be at least 6 characters.");
      }

      if (!isLoginView && !isForgotPassword && !cleanFullName) {
        throw new Error("Full name is required.");
      }

      if (isForgotPassword) {
        const { error } = await supabase.auth.resetPasswordForEmail(
          cleanEmail,
          {
            redirectTo: window.location.origin,
          }
        );

        if (error) {
          throw error;
        }

        toast.success("Password reset instructions sent to your email.");
        setIsForgotPassword(false);
        return;
      }

      if (isLoginView) {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: cleanEmail,
          password: cleanPassword,
        });

        if (error) {
          throw new Error("Invalid email or password.");
        }

        toast.success("Logged in successfully");

        setUser(data.user);

        const role =
          data.user?.user_metadata?.role || data.user?.app_metadata?.role;

        setCurrentView(isAdminRole(role) ? "admin" : "chat");
        return;
      }

      const { data, error } = await supabase.auth.signUp({
        email: cleanEmail,
        password: cleanPassword,
        options: {
          data: {
            full_name: cleanFullName,
            role: "student",
          },
        },
      });

      if (error) {
        const message = error.message.toLowerCase();

        if (
          message.includes("already registered") ||
          message.includes("already exists") ||
          message.includes("user already")
        ) {
          throw new Error(duplicateSignupMessage());
        }

        throw error;
      }

      if (isExistingUserSignupResponse(data)) {
        throw new Error(duplicateSignupMessage());
      }

      if (data.user?.id) {
        const { error: profileError } = await supabase.from("profiles").upsert({
          id: data.user.id,
          email: cleanEmail,
          full_name: cleanFullName,
          role: "student",
        });

        if (profileError) {
          console.warn("Profile full name was not saved:", profileError.message);
        }
      }

      setFullName("");
      setEmail("");
      setPassword("");

      if (data.session) {
        toast.success("Registration successful! You are now logged in.");
        setUser(data.user);
        setCurrentView("chat");
      } else {
        toast.success("Registration successful! Please check your email to verify your account before logging in.");
        setCurrentView("login");
      }
    } catch (error) {
      let message = error.message || "Something went wrong.";

      const lowerMessage = message.toLowerCase();

      if (lowerMessage.includes("infinite recursion detected")) {
        message = "Account permission error. Please contact the administrator.";
      }

      if (
        lowerMessage.includes("already registered") ||
        lowerMessage.includes("already exists") ||
        lowerMessage.includes("user already")
      ) {
        message = duplicateSignupMessage();
      }

      if (
        lowerMessage.includes("invalid login credentials") ||
        lowerMessage.includes("invalid email or password")
      ) {
        message = "Invalid email or password.";
      }

      setErrorMsg(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-slate-50 dark:bg-slate-950 font-sans transition-colors">

      {/* LEFT SIDE: Branding Panel (Hidden on Mobile) */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-[#0f172a] p-12 text-white md:flex">

        {/* Brand/Logo Header */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent shadow-md">
            <GraduationCapIcon size={22} stroke="white" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white leading-none">EduBot</h1>
            <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400 font-semibold mt-0.5">College Information Assistant</p>
          </div>
        </div>

        {/* Hero Text */}
        <div className="relative z-10 my-auto max-w-sm space-y-8">
          <div className="space-y-4">
            <h2 className="text-4xl font-extrabold tracking-tight text-white leading-snug">
              Your assistant for{" "}
              <span className="text-accent">admissions and college information.</span>
            </h2>
            <p className="text-[15px] leading-relaxed text-slate-400">
              EduBot provides accurate, up-to-date answers about admissions, eligibility, applications, courses, fees, facilities, rules, and all official college information.
            </p>
          </div>

          <div className="space-y-5 pt-6 border-t border-slate-800">
            {/* Feature 1 */}
            <div className="flex items-start gap-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-accent">
                <GraduationCapIcon size={18} stroke="currentColor" strokeWidth={2} />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-100">Admission &amp; Eligibility Guidance</h4>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">Get clear information on eligibility criteria, admission process, important dates, and required documents.</p>
              </div>
            </div>

            {/* Feature 2 */}
            <div className="flex items-start gap-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-accent">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6" />
                  <path d="M16 13H8M16 17H8M10 9H8" />
                </svg>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-100">Programmes &amp; College Information</h4>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">Explore courses, departments, fees, facilities, hostel, rules, and campus services.</p>
              </div>
            </div>

            {/* Feature 3 */}
            <div className="flex items-start gap-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-accent">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-100">Official &amp; Verified Answers</h4>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">Answers are provided only from official college resources to ensure accuracy and reliability.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="relative z-10 text-xs text-slate-600">
          &copy; {new Date().getFullYear()} EduBot. All rights reserved.
        </div>
      </div>

      {/* RIGHT SIDE: Auth Card Container */}
      <div className="flex w-full items-center justify-center bg-slate-50 px-6 py-12 dark:bg-slate-950 md:w-1/2">
        <div className="w-full max-w-[400px] space-y-8 animate-slide-up">

          {/* Header Mobile Brand & Text */}
          <div className="text-center md:text-left">
            {/* Logo on mobile only */}
            <div className="flex items-center justify-center gap-2 md:hidden mb-6">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent">
                <GraduationCapIcon size={18} stroke="white" strokeWidth={2.5} />
              </div>
              <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">EduBot</span>
            </div>

            <h2 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {isForgotPassword
                ? "Reset Password"
                : isLoginView
                  ? "Welcome back"
                  : "Create account"}
            </h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
              {isForgotPassword
                ? "Enter your email to receive recovery instructions"
                : isLoginView
                  ? "Sign in to continue to your college information assistant"
                  : "Register with your full name to start learning"}
            </p>
          </div>

          {/* Form Card */}
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_8px_30px_rgb(0,0,0,0.02)] transition-colors dark:border-slate-800/80 dark:bg-slate-900 sm:p-8">

            {errorMsg && (
              <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-red-100 bg-red-50/50 p-3.5 text-xs text-red-600 dark:border-red-950/40 dark:bg-red-950/20 dark:text-red-400 animate-fade-in">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="shrink-0 mt-0.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="font-medium leading-relaxed">{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">

              {/* Full Name Field (Sign Up Only) */}
              {!isForgotPassword && !isLoginView && (
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Full Name
                  </label>
                  <div className="relative">
                    <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">
                      <UserIcon />
                    </span>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => {
                        setFullName(e.target.value);
                        setErrorMsg("");
                      }}
                      required
                      placeholder="e.g. John Doe"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-11 py-2.5 text-sm text-slate-900 transition-all placeholder:text-slate-400 hover:border-slate-300 focus:border-accent focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-800 dark:bg-slate-950 dark:text-white dark:placeholder:text-slate-600 dark:hover:border-slate-700 dark:focus:border-accent dark:focus:bg-slate-950"
                    />
                  </div>
                </div>
              )}

              {/* Email Field */}
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Email Address
                </label>
                <div className="relative">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">
                    <EmailIcon />
                  </span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setErrorMsg("");
                    }}
                    required
                    placeholder="you@college.edu"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-11 py-2.5 text-sm text-slate-900 transition-all placeholder:text-slate-400 hover:border-slate-300 focus:border-accent focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-800 dark:bg-slate-950 dark:text-white dark:placeholder:text-slate-600 dark:hover:border-slate-700 dark:focus:border-accent dark:focus:bg-slate-950"
                  />
                </div>
              </div>

              {/* Password Field */}
              {!isForgotPassword && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Password
                    </label>
                    {isLoginView && (
                      <button
                        type="button"
                        onClick={() => {
                          setIsForgotPassword(true);
                          setErrorMsg("");
                          setPassword("");
                        }}
                        className="cursor-pointer text-xs font-medium text-accent hover:text-accent-strong hover:underline focus:outline-none dark:text-accent-soft"
                      >
                        Forgot password?
                      </button>
                    )}
                  </div>
                  <div className="relative">
                    <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">
                      <LockIcon />
                    </span>
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        setErrorMsg("");
                      }}
                      required
                      placeholder="••••••••"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-11 py-2.5 text-sm text-slate-900 transition-all placeholder:text-slate-400 hover:border-slate-300 focus:border-accent focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-800 dark:bg-slate-950 dark:text-white dark:placeholder:text-slate-600 dark:hover:border-slate-700 dark:focus:border-accent dark:focus:bg-slate-950"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 cursor-pointer text-slate-400 hover:text-slate-600 focus:outline-none dark:hover:text-slate-200"
                    >
                      {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                    </button>
                  </div>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="mt-3 flex w-full cursor-pointer items-center justify-center rounded-xl bg-accent py-3 text-sm font-semibold text-white shadow-md shadow-accent-soft transition-all hover:bg-accent-dark active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <div className="flex items-center gap-2">
                    <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Please wait...</span>
                  </div>
                ) : isForgotPassword ? (
                  "Send Reset Link"
                ) : isLoginView ? (
                  "Sign In"
                ) : (
                  "Create Account"
                )}
              </button>
            </form>
          </div>

          {/* Toggle Views Footer */}
          <div className="text-center text-sm text-slate-500 dark:text-slate-400">
            {isForgotPassword ? (
              <button
                type="button"
                onClick={() => {
                  setIsForgotPassword(false);
                  setErrorMsg("");
                }}
                className="cursor-pointer font-semibold text-accent hover:underline focus:outline-none dark:text-accent-soft"
              >
                Back to Sign In
              </button>
            ) : (
              <>
                <span>
                  {isLoginView
                    ? "Don't have an account? "
                    : "Already have an account? "}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setCurrentView(isLoginView ? "register" : "login");
                    setErrorMsg("");
                    setFullName("");
                    setPassword("");
                  }}
                  className="cursor-pointer font-semibold text-accent hover:underline focus:outline-none dark:text-accent-soft"
                >
                  {isLoginView ? "Sign up" : "Sign in"}
                </button>
              </>
            )}
          </div>

        </div>
      </div>

    </div>
  );
}

function GraduationCapIcon({ size = 24, stroke = "currentColor", strokeWidth = 2 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 10v6" />
      <path d="M2 10l10-5 10 5-10 5z" />
      <path d="M6 12v5c0 1.657 2.686 3 6 3s6-1.343 6-3v-5" />
    </svg>
  );
}

function EmailIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <path d="m22 6-10 7L2 6" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20 21a8 8 0 0 0-16 0" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}

export default Auth;
