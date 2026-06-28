import { useState, useEffect, useRef } from "react";
import {
  Globe, Loader2, CheckCircle2, AlertCircle, Play, Pause,
  XCircle, SkipForward, FileText, Layers, Activity, BookOpen,
  ChevronDown, ChevronUp, Trash2, Eye, RefreshCw, Clock,
  Link as LinkIcon, AlertTriangle, ListCollapse, Plus
} from "lucide-react";
import { supabase } from "../../supabaseClient";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function WebsiteCrawler({ onCrawlComplete, setCurrentView }) {
  // Form Config state
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(500);
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxPdfs, setMaxPdfs] = useState(200);
  const [includePdfs, setIncludePdfs] = useState(true);
  const [sameDomain, setSameDomain] = useState(true);
  const [department, setDepartment] = useState("general");
  const [year, setYear] = useState("general");

  // Crawl job monitoring state
  const [jobId, setJobId] = useState(null);
  const [jobProgress, setJobProgress] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [elapsedTime, setElapsedTime] = useState(0);

  // History state
  const [recentJobs, setRecentJobs] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyNotice, setHistoryNotice] = useState("");
  const [showAllHistory, setShowAllHistory] = useState(false);

  // Modal / Confirm dialog states
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobToDelete, setJobToDelete] = useState(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);

  const pollIntervalRef = useRef(null);
  const urlInputRef = useRef(null);

  // Fetch History on Mount
  const fetchRecentJobs = async () => {
    setLoadingHistory(true);
    setHistoryNotice("");
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const headers = {};
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      const response = await fetch(`${API_URL}/crawl/jobs`, { headers });
      if (!response.ok) {
        throw new Error("Failed to fetch crawl jobs list from backend");
      }
      const data = await response.json();
      setRecentJobs(data || []);
    } catch (err) {
      console.error("Failed to load crawl jobs:", err);
      setHistoryNotice("Could not load recent crawl jobs from the backend.");
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchRecentJobs();
  }, []);

  // Poll elapsed time for active crawls
  useEffect(() => {
    let timer;
    const isCrawlActive = jobProgress && ["queued", "pending", "running", "crawling", "processing", "chunking", "embedding", "paused"].includes(jobProgress.status);

    if (isCrawlActive && jobProgress?.started_at) {
      const startTime = new Date(jobProgress.started_at).getTime();
      timer = setInterval(() => {
        const seconds = Math.floor((Date.now() - startTime) / 1000);
        setElapsedTime(seconds >= 0 ? seconds : 0);
      }, 1000);
    } else {
      setElapsedTime(0);
    }
    return () => clearInterval(timer);
  }, [jobProgress?.status, jobProgress?.started_at]);

  const validateUrl = (value) => {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch {
      return false;
    }
  };

  // Stop polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const startPolling = (id) => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = setInterval(async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        const headers = {};
        if (session?.access_token) {
          headers["Authorization"] = `Bearer ${session.access_token}`;
        }

        const response = await fetch(`${API_URL}/crawl/status/${id}`, { headers });
        if (!response.ok) {
          throw new Error("Failed to fetch crawl status");
        }

        const progress = await response.json();
        setJobProgress(progress);

        // Terminal states
        if (
          progress.status === "completed" ||
          progress.status === "failed" ||
          progress.status === "cancelled"
        ) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          setLoading(false);

          if (progress.status === "completed") {
            onCrawlComplete?.(progress);
          }
          // Refresh list of jobs
          fetchRecentJobs();
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 1500);
  };

  const handleCrawl = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setJobProgress(null);
    setJobId(null);

    const cleanUrl = url.trim();

    if (!cleanUrl) {
      setError("Please enter a website URL.");
      return;
    }

    if (!validateUrl(cleanUrl)) {
      setError("Please enter a valid website URL starting with http:// or https://");
      return;
    }

    const pagesVal = Number(maxPages);
    if (isNaN(pagesVal) || pagesVal < 1 || pagesVal > 1000) {
      setError("Max pages must be a number between 1 and 1000.");
      return;
    }

    const depthVal = Number(maxDepth);
    if (isNaN(depthVal) || depthVal < 1 || depthVal > 5) {
      setError("Max depth must be a number between 1 and 5.");
      return;
    }

    try {
      setLoading(true);

      const { data: { session } } = await supabase.auth.getSession();
      const headers = { "Content-Type": "application/json" };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      const response = await fetch(`${API_URL}/crawl/start`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          url: cleanUrl,
          max_pages: Number(maxPages),
          max_pdfs: Number(maxPdfs),
          include_pdfs: includePdfs,
          same_domain_only: sameDomain,
          department,
          document_type: "website",
          year,
          max_depth: Number(maxDepth),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "Failed to start website crawl.");
      }

      setJobId(data.job_id);
      setJobProgress({
        job_id: data.job_id,
        status: "queued",
        url: cleanUrl,
        current_url: cleanUrl,
        current_stage: "queued",
        current_type: "page",
        pages_found: 0,
        pages_processed: 0,
        pdfs_found: 0,
        pdfs_processed: 0,
        documents_found: 0,
        documents_processed: 0,
        chunks_created: 0,
        skipped_urls: [],
        errors: [],
        started_at: new Date().toISOString(),
      });

      startPolling(data.job_id);
      fetchRecentJobs();
    } catch (err) {
      setError(err.message || "Something went wrong while starting the crawl.");
      setLoading(false);
    }
  };

  const handleControl = async (id, action) => {
    // Optimistically update status
    if (action === "cancel") {
      setJobProgress(prev => prev && prev.job_id === id ? { ...prev, status: "cancelled", finished_at: new Date().toISOString() } : prev);
      setRecentJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: "cancelled", finished_at: new Date().toISOString() } : j));
    } else if (action === "pause") {
      setJobProgress(prev => prev && prev.job_id === id ? { ...prev, status: "paused" } : prev);
      setRecentJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: "paused" } : j));
    } else if (action === "resume") {
      setJobProgress(prev => prev && prev.job_id === id ? { ...prev, status: "crawling" } : prev);
      setRecentJobs(prev => prev.map(j => j.job_id === id ? { ...j, status: "crawling" } : j));
    }

    try {
      const { data: { session } } = await supabase.auth.getSession();
      const headers = { "Content-Type": "application/json" };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      const response = await fetch(`${API_URL}/crawl/control/${id}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ action }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to execute control action.");
      }

      // Refresh data
      if (id === jobId) {
        startPolling(id);
      }
      fetchRecentJobs();
    } catch (err) {
      setError(err.message || "Failed to control crawl job.");
    }
  };

  const handleDeleteJob = async (id) => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const headers = {
        "Content-Type": "application/json"
      };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      const response = await fetch(`${API_URL}/crawl/${id}`, {
        method: "DELETE",
        headers
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to delete crawl job.");
      }

      setRecentJobs(prev => prev.filter(job => job.job_id !== id));
      setJobToDelete(null);
    } catch (err) {
      console.error("Failed to delete crawl job:", err);
      setError(err.message || "Failed to delete job entry.");
    }
  };

  const activeStatuses = ["crawling", "running", "processing", "chunking", "embedding", "pending", "queued", "paused", "in progress", "in_progress"];

  const handleClearHistory = async () => {
    setClearingHistory(true);
    setError("");
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const headers = { "Content-Type": "application/json" };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      // Only clear finished jobs so any running/paused crawl keeps going.
      const deletableJobs = recentJobs.filter(
        (job) => job?.job_id && !activeStatuses.includes(job.status?.toLowerCase())
      );

      await Promise.all(
        deletableJobs.map((job) =>
          fetch(`${API_URL}/crawl/${job.job_id}`, { method: "DELETE", headers }).catch(() => null)
        )
      );

      await fetchRecentJobs();
      setShowClearConfirm(false);
    } catch (err) {
      console.error("Failed to clear crawl history:", err);
      setError(err.message || "Failed to clear crawl history.");
    } finally {
      setClearingHistory(false);
    }
  };

  const handleReCrawl = (job) => {
    setUrl(job.url);
    setMaxPages(job.pages_found || 500);
    setMaxDepth(job.max_depth || 3);
    setMaxPdfs(job.max_pdfs || 200);
    setIncludePdfs((job.pdfs_found || 0) > 0 || true);
    setSameDomain(job.skipped_urls?.length > 0 || true);

    // Scroll smoothly to config form and focus
    if (urlInputRef.current) {
      urlInputRef.current.scrollIntoView({ behavior: "smooth" });
      urlInputRef.current.focus();
    }
  };

  const getStatusBadge = (status) => {
    let classes = "px-2 py-0.5 text-xs font-semibold rounded text-center uppercase tracking-wide border ";
    switch (status) {
      case "queued":
      case "pending":
        classes += "bg-amber-50 text-amber-800 dark:bg-amber-950/20 dark:text-amber-300 border-amber-200 dark:border-amber-900";
        break;
      case "running":
      case "crawling":
      case "processing":
      case "chunking":
      case "embedding":
      case "in progress":
      case "in_progress":
        classes += "bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-300 border-blue-200 dark:border-blue-900 animate-pulse";
        return <span className={classes}>In Progress</span>;
      case "paused":
        classes += "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-350 border-slate-200 dark:border-slate-700";
        break;
      case "completed":
        classes += "bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-300 border-green-200 dark:border-green-900";
        break;
      case "cancelled":
        classes += "bg-slate-100 text-slate-650 dark:bg-slate-800/20 dark:text-slate-400 border-slate-200 dark:border-slate-800";
        break;
      case "failed":
        classes += "bg-red-50 text-red-750 dark:bg-red-950/20 dark:text-red-350 border-red-150 dark:border-red-900";
        break;
      default:
        classes += "bg-slate-50 text-slate-700 dark:bg-slate-800 border-slate-200";
    }
    return <span className={classes}>{status || "unknown"}</span>;
  };

  const formatDate = (dateString) => {
    if (!dateString) return "—";
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true
    });
  };

  const formatElapsed = (totalSeconds) => {
    const s = Math.max(0, Number(totalSeconds) || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}h ${m}m ${sec}s`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  };

  const isCrawlActive = jobProgress && ["queued", "pending", "running", "crawling", "processing", "chunking", "embedding", "paused"].includes(jobProgress.status);

  // Status mapping - show active or fall back to most recent history job
  const activeOrLastJob = isCrawlActive ? jobProgress : (recentJobs.length > 0 ? recentJobs[0] : null);

  const pagesFound = Number(activeOrLastJob?.pages_found) || 0;
  const pagesProcessed = Number(activeOrLastJob?.pages_processed) || 0;
  const pdfsFound = Number(activeOrLastJob?.pdfs_found || activeOrLastJob?.["PDFs found"]) || 0;
  const pdfsProcessed = Number(activeOrLastJob?.pdfs_processed || activeOrLastJob?.["PDFs processed"]) || 0;
  const docsFound = Number(activeOrLastJob?.documents_found) || 0;
  const docsProcessed = Number(activeOrLastJob?.documents_processed) || 0;
  const chunksCreated = Number(activeOrLastJob?.chunks_created) || 0;
  const errorsCount = Number(activeOrLastJob?.pages_failed) || (Array.isArray(activeOrLastJob?.errors) ? activeOrLastJob.errors.length : 0);
  const currentUrl = activeOrLastJob?.current_url || activeOrLastJob?.url || "Idle";

  const rawPercent = pagesFound > 0 ? Math.min(100, Math.round((pagesProcessed / pagesFound) * 100)) : (activeOrLastJob?.status === "completed" ? 100 : 0);
  const progressPercent = isNaN(rawPercent) ? 0 : rawPercent;
  const pagesRemaining = Math.max(0, pagesFound - pagesProcessed);

  // SVG Circular chart params
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  // History slicing
  const visibleJobs = showAllHistory ? recentJobs : recentJobs.slice(0, 5);

  const handleNewCrawlClick = () => {
    setUrl("");
    setMaxPages(500);
    setMaxDepth(3);
    setIncludePdfs(true);
    setSameDomain(true);
    if (urlInputRef.current) {
      urlInputRef.current.scrollIntoView({ behavior: "smooth" });
      urlInputRef.current.focus();
    }
  };

  const renderRowActions = (job) => {
    const isActive = ["crawling", "running", "processing", "chunking", "embedding", "pending", "queued", "in progress", "in_progress"].includes(job.status?.toLowerCase());

    if (isActive) {
      return (
        <div className="flex justify-end gap-1.5">
          {job.status === "paused" ? (
            <button
              onClick={() => handleControl(job.job_id, "resume")}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-450"
              title="Resume Ingestion"
            >
              <Play size={13} />
            </button>
          ) : (
            <button
              onClick={() => handleControl(job.job_id, "pause")}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-150 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-450"
              title="Pause Ingestion"
            >
              <Pause size={13} />
            </button>
          )}

          <button
            onClick={() => handleControl(job.job_id, "cancel")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 hover:bg-red-50 text-red-650 dark:border-red-950 dark:hover:bg-red-950/30"
            title="Cancel Ingestion"
          >
            <XCircle size={13} />
          </button>
        </div>
      );
    }

    if (job.status === "failed") {
      return (
        <div className="flex justify-end gap-1.5">
          <button
            onClick={() => setSelectedJob(job)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500 dark:border-slate-800 dark:hover:bg-slate-900 dark:text-slate-450"
            title="View Details"
          >
            <Eye size={13} />
          </button>

          <button
            onClick={() => setJobToDelete(job.job_id)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-600 dark:border-red-950/45 dark:text-red-400"
            title="Delete Log"
          >
            <Trash2 size={13} />
          </button>
        </div>
      );
    }

    // Completed
    return (
      <div className="flex justify-end gap-1.5">
        <button
          onClick={() => setSelectedJob(job)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500 dark:border-slate-800 dark:hover:bg-slate-900 dark:text-slate-450"
          title="View Details"
        >
          <Eye size={13} />
        </button>

        <button
          onClick={() => handleReCrawl(job)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500 dark:border-slate-800 dark:hover:bg-slate-900 dark:text-slate-450"
          title="Re-run Crawl"
        >
          <RefreshCw size={12} />
        </button>

        <button
          onClick={() => setJobToDelete(job.job_id)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-600 dark:border-red-950/45 dark:text-red-400 dark:hover:bg-red-950/40"
          title="Delete Log"
        >
          <Trash2 size={13} />
        </button>
      </div>
    );
  };

  return (
    <div className="space-y-6 text-slate-800 dark:text-slate-250 select-none">

      {/* PAGE HEADER */}
      <div className="flex flex-col gap-4 border-b border-slate-100 dark:border-slate-800 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-inset ring-blue-100 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-900/50">
            <Globe size={20} />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
              Website Crawler / Ingestion
            </h1>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Crawl and ingest content from website links to expand EduBot&apos;s knowledge base.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleNewCrawlClick}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700"
        >
          <Plus size={15} />
          <span>New Crawl</span>
        </button>
      </div>

      {/* NEW CRAWL CONFIG CARD */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-5 flex items-center gap-2.5 border-b border-slate-100 pb-4 dark:border-slate-800/80">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            <Layers size={15} />
          </span>
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
              Crawl Configuration
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
              Set the target website and how deep the crawler should go.
            </p>
          </div>
        </div>

        <form onSubmit={handleCrawl} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-bold text-slate-500 dark:text-slate-400">
              Website URL
            </label>
            <div className="relative flex items-center">
              <span className="absolute left-3.5 text-slate-400">
                <LinkIcon size={14} />
              </span>
              <input
                ref={urlInputRef}
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.college.edu.in"
                autoComplete="off"
                className="w-full rounded-lg border border-slate-200 bg-white pl-10 pr-4 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-white"
                disabled={loading}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="mb-1 block text-xs font-bold text-slate-500 dark:text-slate-400">
                  Max Depth (1 - 5)
                </label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(e.target.value === "" ? "" : Number(e.target.value))}
                  disabled={loading}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-bold text-slate-500 dark:text-slate-400">
                  Max Pages (1-1000)
                </label>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={maxPages}
                  onChange={(e) => setMaxPages(e.target.value === "" ? "" : Number(e.target.value))}
                  disabled={loading}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-bold text-slate-500 dark:text-slate-400">
                  Max PDFs (1-1000)
                </label>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={maxPdfs}
                  onChange={(e) => setMaxPdfs(e.target.value === "" ? "" : Number(e.target.value))}
                  disabled={loading || !includePdfs}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-white disabled:opacity-50"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <label className="flex items-center gap-2.5 cursor-pointer rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2.5 transition hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={sameDomain}
                  onChange={(e) => setSameDomain(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600"
                  disabled={loading}
                />
                <span className="text-xs font-semibold text-slate-650 dark:text-slate-350">
                  Crawl entire website (internal links)
                </span>
              </label>

              <label className="flex items-center gap-2.5 cursor-pointer rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2.5 transition hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:border-slate-700">
                <input
                  type="checkbox"
                  checked={includePdfs}
                  onChange={(e) => setIncludePdfs(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600"
                  disabled={loading}
                />
                <span className="text-xs font-semibold text-slate-650 dark:text-slate-350">
                  Extract PDFs found on website
                </span>
              </label>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 dark:border-slate-800/80 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
              <Clock size={12} className="shrink-0" />
              Larger sites take longer to crawl and ingest.
            </p>
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-75 dark:bg-blue-600 dark:hover:bg-blue-700"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Ingesting...
                </>
              ) : (
                <>
                  <Globe size={14} />
                  Start Crawl
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/40 px-4 py-2.5 text-xs text-red-700 dark:border-red-900/30 dark:bg-red-950/10 dark:text-red-350">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span className="font-semibold">{error}</span>
            </div>
          )}

          {message && (
            <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-blue-200 bg-blue-50/40 px-4 py-2.5 text-xs text-blue-700 dark:border-blue-900/30 dark:bg-blue-950/10 dark:text-blue-350">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
              <span className="font-semibold">{message}</span>
            </div>
          )}
        </form>
      </div>

      {/* CURRENT CRAWL STATUS CARD */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-5 flex items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800/80">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <Activity size={15} />
            </span>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
              Crawl Status &amp; Progress
            </h2>
          </div>
          {isCrawlActive && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-600 dark:border-blue-900/40 dark:bg-blue-950/30 dark:text-blue-400">
              <Clock size={11} />
              {formatElapsed(elapsedTime)}
            </span>
          )}
        </div>

        <div className="flex flex-col md:flex-row items-center gap-6">
          {/* Radial Donut Progress Ring */}
          <div className="relative flex items-center justify-center w-28 h-28 shrink-0">
            <svg className="w-24 h-24 transform -rotate-90">
              <circle
                cx="48"
                cy="48"
                r={radius}
                className="stroke-slate-100 dark:stroke-slate-850"
                strokeWidth="7"
                fill="transparent"
              />
              <circle
                cx="48"
                cy="48"
                r={radius}
                className="stroke-blue-600 dark:stroke-blue-500 transition-all duration-500"
                strokeWidth="7"
                fill="transparent"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center">
              <span className="text-xl font-black text-slate-900 dark:text-white leading-none">
                {progressPercent}%
              </span>
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider mt-1.5">
                {isCrawlActive ? (activeOrLastJob?.status === "paused" ? "Paused" : "In Progress") : (activeOrLastJob?.status || "Idle")}
              </span>
            </div>
          </div>

          {/* Metrics Column */}
          <div className="flex-1 w-full space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5 dark:border-slate-800/70 dark:bg-slate-900/40">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                  <FileText size={12} /> Pages
                </span>
                <p className="mt-1 text-lg font-bold text-slate-850 dark:text-slate-100">{pagesProcessed} / {pagesFound}</p>
              </div>

              <div className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5 dark:border-slate-800/70 dark:bg-slate-900/40">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                  <BookOpen size={12} /> PDFs
                </span>
                <p className="mt-1 text-lg font-bold text-slate-850 dark:text-slate-100">{pdfsProcessed} / {pdfsFound}</p>
              </div>

              <div className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5 dark:border-slate-800/70 dark:bg-slate-900/40">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                  <FileText size={12} /> Docs
                </span>
                <p className="mt-1 text-lg font-bold text-slate-850 dark:text-slate-100">{docsProcessed} / {docsFound}</p>
              </div>

              <div className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5 dark:border-slate-800/70 dark:bg-slate-900/40">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                  <Layers size={12} /> Chunks
                </span>
                <p className="mt-1 text-lg font-bold text-slate-850 dark:text-slate-100">{chunksCreated}</p>
              </div>

              <div className={`rounded-lg border px-3 py-2.5 ${errorsCount > 0 ? "border-red-100 bg-red-50/50 dark:border-red-900/40 dark:bg-red-950/20" : "border-slate-100 bg-slate-50/60 dark:border-slate-800/70 dark:bg-slate-900/40"}`}>
                <span className={`flex items-center gap-1.5 text-[11px] font-semibold ${errorsCount > 0 ? "text-red-500" : "text-slate-400 dark:text-slate-500"}`}>
                  <AlertCircle size={12} /> Errors
                </span>
                <p className={`mt-1 text-lg font-bold ${errorsCount > 0 ? "text-red-500" : "text-slate-850 dark:text-slate-100"}`}>{errorsCount}</p>
              </div>
            </div>

            {/* Linear progress bar */}
            <div>
              <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                <span>Progress</span>
                <span>{pagesRemaining} pages remaining</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-850">
                <div
                  className="h-full rounded-full bg-blue-600 transition-all duration-500 dark:bg-blue-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            <div className="border-t border-slate-100 dark:border-slate-900 pt-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="min-w-0 flex-1">
                <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Current Page</span>
                <p className="mt-1 text-xs font-semibold text-blue-600 dark:text-blue-450 break-all select-all font-mono">
                  {currentUrl}
                </p>
              </div>
              {setCurrentView && (
                <div className="text-xs text-slate-500 dark:text-slate-400 shrink-0 self-start sm:self-center bg-blue-50/50 dark:bg-blue-950/10 border border-blue-100 dark:border-blue-900/30 rounded-lg px-3 py-1.5 flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                  <span>
                    Ingested PDFs/docs are saved in the{" "}
                    <button
                      type="button"
                      onClick={() => setCurrentView("admin-documents")}
                      className="text-blue-600 dark:text-blue-450 hover:underline font-bold cursor-pointer"
                    >
                      Documents
                    </button>{" "}
                    tab.
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Actions Column */}
          <div className="shrink-0 w-full md:w-auto flex flex-col sm:flex-row md:flex-col gap-2 justify-end items-end sm:items-center md:items-end">
            {isCrawlActive && (
              <div className="flex gap-2 w-full sm:w-auto">
                {activeOrLastJob.status === "paused" ? (
                  <button
                    onClick={() => handleControl(activeOrLastJob.job_id, "resume")}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-xs font-semibold text-blue-600 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-450 w-full sm:w-auto"
                    title="Resume Ingestion"
                  >
                    <Play size={13} />
                    <span>Resume</span>
                  </button>
                ) : (
                  <button
                    onClick={() => handleControl(activeOrLastJob.job_id, "pause")}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-350 dark:hover:bg-slate-900 w-full sm:w-auto"
                    title="Pause Ingestion"
                  >
                    <Pause size={13} />
                    <span>Pause</span>
                  </button>
                )}

                <button
                  onClick={() => handleControl(activeOrLastJob.job_id, "cancel")}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs font-semibold text-red-650 hover:bg-red-100 dark:border-red-950 dark:hover:bg-red-950/30 w-full sm:w-auto"
                  title="Cancel Ingestion"
                >
                  <XCircle size={13} />
                  <span>Stop</span>
                </button>
              </div>
            )}

            <button
              onClick={() => setSelectedJob(activeOrLastJob)}
              disabled={!activeOrLastJob}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900 w-full sm:w-auto"
            >
              <ListCollapse size={13} className="text-slate-500" />
              <span>View Details</span>
            </button>
          </div>
        </div>
      </div>

      {/* CRAWL HISTORY LOGS TABLE */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-5 flex items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800/80">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <Clock size={15} />
            </span>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
              Crawl History &amp; Logs
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchRecentJobs}
              disabled={loadingHistory}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-50 disabled:opacity-60 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
              title="Refresh history"
            >
              <RefreshCw size={12} className={loadingHistory ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>

            {recentJobs.length > 0 && (
              <button
                type="button"
                onClick={() => setShowClearConfirm(true)}
                disabled={clearingHistory}
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-[11px] font-semibold text-red-600 transition hover:bg-red-100 disabled:opacity-60 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50"
                title="Clear crawl history"
              >
                <Trash2 size={12} />
                <span>Clear all</span>
              </button>
            )}
          </div>
        </div>

        {historyNotice && (
          <div className="mb-4 rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs font-semibold text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/10 dark:text-amber-300">
            {historyNotice}
          </div>
        )}

        {loadingHistory && recentJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-slate-400">
            <Loader2 className="animate-spin text-blue-500 mb-2" size={20} />
            <p className="text-xs font-semibold">Loading logs from database...</p>
          </div>
        ) : recentJobs.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg">
            <Globe className="mx-auto text-slate-350 dark:text-slate-700 mb-1.5" size={28} />
            <p className="text-xs font-semibold text-slate-400">No logs stored yet.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="overflow-x-auto rounded-lg border border-slate-150 dark:border-slate-850">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:bg-slate-900/50 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Website</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-center">Pages</th>
                    <th className="px-4 py-3 text-center">PDFs/Docs</th>
                    <th className="px-4 py-3 text-center">Chunks</th>
                    <th className="px-4 py-3">Last Crawl</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-150 bg-white text-slate-700 dark:divide-slate-850 dark:bg-slate-950 dark:text-slate-350">
                  {visibleJobs.map((job, index) => {
                    if (!job) return null;
                    const key = job.job_id || `job-idx-${index}`;
                    const jobUrl = job.url || job.current_url || "";
                    return (
                      <tr key={key} className="align-middle hover:bg-slate-50/30 dark:hover:bg-slate-900/20">
                        <td className="px-4 py-3 max-w-xs truncate font-mono text-blue-600 dark:text-blue-450 hover:underline select-all">
                          {jobUrl ? (
                            <a href={jobUrl} target="_blank" rel="noreferrer" title={jobUrl}>
                              {jobUrl}
                            </a>
                          ) : (
                            <span className="text-slate-400 dark:text-slate-500 italic">No URL</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {getStatusBadge(job.status)}
                        </td>
                        <td className="px-4 py-3 text-center font-semibold text-slate-850 dark:text-slate-100">
                          {job.pages_processed ?? 0} / {job.pages_found ?? 0}
                        </td>
                        <td className="px-4 py-3 text-center font-semibold text-slate-850 dark:text-slate-100">
                          {(job.pdfs_processed ?? job["PDFs processed"] ?? 0) + (job.documents_processed ?? 0)} / {(job.pdfs_found ?? job["PDFs found"] ?? 0) + (job.documents_found ?? 0)}
                        </td>
                        <td className="px-4 py-3 text-center font-semibold text-slate-850 dark:text-slate-100">
                          {(job.chunks_created ?? 0).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                          {formatDate(job.last_crawl_timestamp || job.finished_at || job.started_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {renderRowActions(job)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {recentJobs.length > 5 && (
              <div className="flex justify-center pt-2">
                <button
                  onClick={() => setShowAllHistory(!showAllHistory)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:hover:text-slate-350 cursor-pointer"
                >
                  <span>{showAllHistory ? "View less" : "View all"}</span>
                  {showAllHistory ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* VIEW DETAILS MODAL */}
      {selectedJob && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm dark:bg-slate-950/80"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-150 pb-4 dark:border-slate-800">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">Crawl Job Ingestion details</h3>
                <p className="mt-0.5 text-[10px] text-slate-450 font-mono select-all break-all">{selectedJob.job_id}</p>
              </div>
              <button
                onClick={() => setSelectedJob(null)}
                className="text-slate-400 hover:text-slate-650 dark:text-slate-500 dark:hover:text-slate-350 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-4 max-h-[50vh] overflow-y-auto pr-1">
              <div className="grid gap-3 sm:grid-cols-2 text-xs">
                <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 dark:border-slate-800/60 dark:bg-slate-950/30">
                  <span className="text-[10px] text-slate-450 uppercase font-bold tracking-wide">Target Website URL</span>
                  <p className="mt-1 font-mono text-[11px] text-slate-700 dark:text-slate-300 break-all select-all">{selectedJob.url}</p>
                </div>

                <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 dark:border-slate-800/60 dark:bg-slate-950/30">
                  <span className="text-[10px] text-slate-450 uppercase font-bold tracking-wide">Crawl Status</span>
                  <div className="mt-1.5 flex">{getStatusBadge(selectedJob.status)}</div>
                </div>
              </div>

              {/* Counts metrics */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-xs border-y border-slate-100 py-3 dark:border-slate-800">
                <div className="text-center rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
                  <span className="text-slate-400 font-bold block uppercase text-[9px] tracking-wider">Pages</span>
                  <p className="mt-0.5 text-sm font-bold text-slate-800 dark:text-slate-200">
                    {selectedJob.pages_processed} / {selectedJob.pages_found}
                  </p>
                </div>
                <div className="text-center rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
                  <span className="text-slate-400 font-bold block uppercase text-[9px] tracking-wider">PDFs</span>
                  <p className="mt-0.5 text-sm font-bold text-slate-800 dark:text-slate-200">
                    {selectedJob.pdfs_processed} / {selectedJob.pdfs_found}
                  </p>
                </div>
                <div className="text-center rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
                  <span className="text-slate-400 font-bold block uppercase text-[9px] tracking-wider">Docs</span>
                  <p className="mt-0.5 text-sm font-bold text-slate-800 dark:text-slate-200">
                    {selectedJob.documents_processed} / {selectedJob.documents_found}
                  </p>
                </div>
                <div className="text-center rounded-lg bg-slate-50 p-2 dark:bg-slate-950">
                  <span className="text-slate-400 font-bold block uppercase text-[9px] tracking-wider">Chunks</span>
                  <p className="mt-0.5 text-sm font-bold text-slate-800 dark:text-slate-200">
                    {selectedJob.chunks_created}
                  </p>
                </div>
              </div>

              {/* Time stamps */}
              <div className="grid gap-3 sm:grid-cols-2 text-xs border-b border-slate-100 pb-3 dark:border-slate-800">
                <div>
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Crawl Start</span>
                  <p className="mt-0.5 text-slate-700 dark:text-slate-300 font-semibold">
                    {selectedJob.started_at ? new Date(selectedJob.started_at).toLocaleString() : "Unknown"}
                  </p>
                </div>
                <div>
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Crawl End</span>
                  <p className="mt-0.5 text-slate-700 dark:text-slate-300 font-semibold">
                    {selectedJob.finished_at ? new Date(selectedJob.finished_at).toLocaleString() : "Running..."}
                  </p>
                </div>
              </div>

              {/* Skipped URLs */}
              {selectedJob.skipped_urls?.length > 0 && (
                <div className="rounded-lg border border-slate-100 p-3 dark:border-slate-800 bg-slate-50/20 dark:bg-slate-950/20">
                  <h4 className="text-[10px] font-bold text-slate-450 uppercase tracking-wider mb-1.5">
                    Skipped Pages ({selectedJob.skipped_urls.length})
                  </h4>
                  <div className="max-h-20 overflow-y-auto space-y-0.5 text-[11px] text-slate-500 font-mono">
                    {selectedJob.skipped_urls.map((urlStr, idx) => (
                      <p key={idx} className="truncate select-all" title={urlStr}>• {urlStr}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Error messages */}
              {selectedJob.errors?.length > 0 ? (
                <div className="rounded-lg border border-red-150 p-3 bg-red-50/10 dark:border-red-900/30 dark:bg-red-950/10">
                  <h4 className="text-[10px] font-bold text-red-500 uppercase tracking-wider mb-1.5">
                    Errors &amp; Warnings ({selectedJob.errors.length})
                  </h4>
                  <div className="max-h-24 overflow-y-auto space-y-0.5 text-[11px] text-rose-600 dark:text-rose-450 font-mono">
                    {selectedJob.errors.map((errStr, idx) => (
                      <p key={idx}>• {errStr}</p>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-emerald-600 font-semibold rounded-lg border border-emerald-100 bg-emerald-50/10 p-3 dark:border-emerald-950/30 dark:bg-emerald-950/10">
                  <CheckCircle2 size={13} />
                  <span>Crawl session completed with no execution warnings.</span>
                </div>
              )}
            </div>

            <div className="mt-5 flex justify-end border-t border-slate-100 pt-3 dark:border-slate-800">
              <button
                onClick={() => setSelectedJob(null)}
                className="rounded-lg bg-slate-100 hover:bg-slate-200 px-4 py-1.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CONFIRM DELETE MODAL */}
      {jobToDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm dark:bg-slate-950/80"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-start gap-3.5">
              <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-red-50 text-red-650 dark:bg-red-950/20 dark:text-red-300">
                <AlertTriangle size={16} />
              </span>

              <div className="min-w-0">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">Delete Job History Entry?</h3>
                <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
                  This deletes the job log row. The indexed chunks inside ChromaDB will not be altered.
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2.5 border-t border-slate-150 pt-3 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setJobToDelete(null)}
                className="rounded-lg border border-slate-250 bg-white hover:bg-slate-50 px-3.5 py-1.5 text-xs font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-350"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() => handleDeleteJob(jobToDelete)}
                className="rounded-lg bg-red-600 hover:bg-red-750 px-3.5 py-1.5 text-xs font-semibold text-white transition-colors"
              >
                Delete Log
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CONFIRM CLEAR ALL HISTORY MODAL */}
      {showClearConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm dark:bg-slate-950/80"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-start gap-3.5">
              <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-red-50 text-red-650 dark:bg-red-950/20 dark:text-red-300">
                <AlertTriangle size={16} />
              </span>

              <div className="min-w-0">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">Clear Crawl History?</h3>
                <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
                  This removes all finished job logs from the list. Any in-progress crawl keeps running, and indexed chunks inside ChromaDB are not altered.
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2.5 border-t border-slate-150 pt-3 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowClearConfirm(false)}
                disabled={clearingHistory}
                className="rounded-lg border border-slate-250 bg-white hover:bg-slate-50 px-3.5 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-350"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleClearHistory}
                disabled={clearingHistory}
                className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 hover:bg-red-750 px-3.5 py-1.5 text-xs font-semibold text-white transition-colors disabled:opacity-60"
              >
                {clearingHistory ? (
                  <>
                    <Loader2 size={13} className="animate-spin" />
                    Clearing...
                  </>
                ) : (
                  "Clear all"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
