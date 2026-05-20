import { useState } from "react";
import { supabase } from "../supabaseClient";
import { toast } from "react-hot-toast";

function UpdatePassword({ setCurrentView }) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    const { error } = await supabase.auth.updateUser({ password });
    setLoading(false);

    if (error) {
      toast.error(error.message);
    } else {
      toast.success("Password updated successfully!");
      setCurrentView("chat"); // Take them back to chat after success
    }
  };

  return (
    <div className="flex min-h-full flex-1 flex-col items-center justify-center overflow-y-auto bg-white px-4 py-16 transition-colors dark:bg-gray-900 md:py-6">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition-colors dark:border-gray-700 dark:bg-gray-800 sm:p-8">
        <h2 className="text-2xl font-bold text-center mb-6 text-[#1e2a45] dark:text-white">
          Set New Password
        </h2>
        <p className="text-[13px] text-center text-gray-500 dark:text-gray-400 mb-6 -mt-4">
          Please enter your new password below.
        </p>
        
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-[13px] font-medium text-gray-700 dark:text-gray-300 mb-1">New Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="focus:ring-accent w-full rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm text-gray-900 transition-colors focus:outline-none focus:ring-2 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            />
          </div>
          
          <button type="submit" disabled={loading} className="bg-accent hover:bg-accent-dark mt-2 w-full rounded-xl py-[10px] font-semibold text-white transition-colors disabled:opacity-50 cursor-pointer">
            {loading ? "Updating..." : "Update Password"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default UpdatePassword;
