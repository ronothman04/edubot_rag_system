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

  useEffect(() => {
    queueMicrotask(() => {
      setIsForgotPassword(false);
      setErrorMsg("");
      setFullName("");
      setPassword("");
    });
  }, [isLoginView]);

    //check if the email exists in the profiles table before allowing registration

  async function checkProfileExists(emailAddress) {
    const cleanEmail = emailAddress.trim().toLowerCase();

    const { data, error } = await supabase
      .from("profiles")
      .select("id")
      .eq("email", cleanEmail)
      .maybeSingle();

    if (error) {
      throw error;
    }

    return !!data;
  }
  

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

        toast.success("Login successfully");

        setUser(data.user);

        const role =
          data.user?.user_metadata?.role || data.user?.app_metadata?.role;

        setCurrentView(isAdminRole(role) ? "admin" : "chat");
        return;
      }

      const profileExists = await checkProfileExists(cleanEmail);

      if (profileExists) {
        throw new Error(duplicateSignupMessage());
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
    <div className="flex min-h-full flex-1 flex-col items-center justify-center overflow-y-auto bg-white px-4 py-16 transition-colors dark:bg-gray-900 md:py-6">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition-colors dark:border-gray-700 dark:bg-gray-800 sm:p-8">
        <h2 className="mb-6 text-center text-2xl font-bold text-gray-900 dark:text-white">
          {isForgotPassword
            ? "Reset Password"
            : isLoginView
            ? "Welcome Back"
            : "Create an Account"}
        </h2>

        {errorMsg && (
          <div className="mb-4 rounded-lg border border-red-100 bg-red-50 p-3 text-[13px] text-red-600 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {!isForgotPassword && !isLoginView && (
            <div>
              <label className="mb-1 block text-[13px] font-medium text-gray-700 dark:text-gray-300">
                Full Name
              </label>

              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2">
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
                  placeholder="Enter your full name"
                  className="w-full rounded-xl border border-gray-300 bg-white px-11 py-2 text-sm text-gray-900 transition-colors placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-[13px] font-medium text-gray-700 dark:text-gray-300">
              Email
            </label>

            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2">
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
                placeholder="Enter your email"
                className="w-full rounded-xl border border-gray-300 bg-white px-11 py-2 text-sm text-gray-900 transition-colors placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              />
            </div>
          </div>

          {!isForgotPassword && (
            <div>
              <label className="mb-1 block text-[13px] font-medium text-gray-700 dark:text-gray-300">
                Password
              </label>

              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2">
                  <LockIcon />
                </span>

                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setErrorMsg("");
                  }}
                  required
                  placeholder="Enter your password"
                  className="w-full rounded-xl border border-gray-300 bg-white px-11 py-2 text-sm text-gray-900 transition-colors placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
            </div>
          )}

          {!isForgotPassword && isLoginView && (
            <div className="-mt-2 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  setIsForgotPassword(true);
                  setErrorMsg("");
                  setPassword("");
                }}
                className="cursor-pointer text-[12px] text-gray-900 hover:underline focus:outline-none dark:text-white"
              >
                Forgot password?
              </button>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-2 w-full cursor-pointer rounded-xl bg-accent py-[10px] font-semibold text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading
              ? "Please wait..."
              : isForgotPassword
              ? "Send Reset Link"
              : isLoginView
              ? "Sign In"
              : "Sign Up"}
          </button>
        </form>

        <div className="mt-6 text-center text-[13px] text-gray-500 dark:text-gray-400">
          {isForgotPassword ? (
            <button
              type="button"
              onClick={() => {
                setIsForgotPassword(false);
                setErrorMsg("");
              }}
              className="cursor-pointer font-medium text-accent hover:underline focus:outline-none"
            >
              Back to Sign In
            </button>
          ) : (
            <>
              {isLoginView
                ? "Don't have an account? "
                : "Already have an account? "}

              <button
                type="button"
                onClick={() => {
                  setCurrentView(isLoginView ? "register" : "login");
                  setErrorMsg("");
                  setFullName("");
                  setPassword("");
                }}
                className="cursor-pointer font-medium text-accent hover:underline focus:outline-none"
              >
                {isLoginView ? "Sign up" : "Sign in"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function EmailIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-gray-400"
    >
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <path d="m22 6-10 7L2 6" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-gray-400"
    >
      <path d="M20 21a8 8 0 0 0-16 0" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-gray-400"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

export default Auth;
