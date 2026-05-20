import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  RefreshCw,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function AdminDocuments() {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [uploadPercent, setUploadPercent] = useState(0);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_URL}/documents`);

      if (!res.ok) {
        throw new Error("Failed to fetch documents");
      }

      const data = await res.json();
      setDocuments(data.documents || []);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load documents");
    }
  };

  useEffect(() => {
    queueMicrotask(() => {
      fetchDocuments();
    });
  }, []);

  const uploadFileWithProgress = (formData) =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadPercent(Math.min(percent, 100));
      };

      xhr.onload = () => {
        let data;

        try {
          data = JSON.parse(xhr.responseText || "{}");
        } catch {
          data = {};
        }

        if (xhr.status >= 200 && xhr.status < 300) {
          setUploadPercent(100);
          resolve(data);
          return;
        }

        reject(new Error(data.detail || data.message || "Upload failed"));
      };

      xhr.onerror = () => reject(new Error("Upload failed. Please check your connection."));
      xhr.onabort = () => reject(new Error("Upload cancelled"));
      xhr.open("POST", `${API_URL}/upload`);
      xhr.send(formData);
    });

  const handleSelectedFile = async (file) => {
    if (!file) return;

    setUploading(true);
    setUploadName(file.name);
    setUploadPercent(0);
    setUploadSummary(null);
    const toastId = toast.loading(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const data = await uploadFileWithProgress(formData);
      toast.success(data.message || "Upload successful", { id: toastId });
      setUploadSummary(data.stats || null);
      fetchDocuments();
    } catch (error) {
      toast.error(error.message, { id: toastId });
    } finally {
      setUploading(false);
      setUploadName("");
      setUploadPercent(0);
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    handleSelectedFile(file);
    e.target.value = null;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (uploading) return;
    handleSelectedFile(e.dataTransfer.files[0]);
  };

  const formatNumber = (value) => {
    if (typeof value !== "number") return value ?? "0";
    return value.toLocaleString();
  };

  const uploadSummaryRows = uploadSummary
    ? [
        ["File", uploadSummary.file],
        ["Type", uploadSummary.type],
        ["Pages processed", formatNumber(uploadSummary.pages_processed)],
        ["Text extracted", `${formatNumber(uploadSummary.text_extracted)} characters`],
        ["Chunks created", formatNumber(uploadSummary.chunks_created)],
        ["Chunks stored in ChromaDB", formatNumber(uploadSummary.chunks_stored)],
        ["Status", uploadSummary.status],
      ]
    : [];

  const confirmDelete = async () => {
    if (!deleteTarget) return;

    const filename = deleteTarget;
    setDeleting(true);
    const toastId = toast.loading(`Deleting ${filename}...`);

    try {
      const res = await fetch(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Delete failed");
      }

      toast.success("Document deleted", { id: toastId });
      fetchDocuments();
      setDeleteTarget(null);
    } catch (error) {
      toast.error(error.message, { id: toastId });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 px-4 pb-8 pt-16 text-gray-900 dark:bg-[#020817] dark:text-slate-100 sm:px-6 md:pt-8">
      <div className="mx-auto max-w-6xl space-y-7">
        <div className="flex flex-col gap-4 border-b border-gray-200 pb-7 dark:border-slate-800/80 sm:flex-row sm:items-center sm:justify-between ">
          <div>
            <h1 className="flex flex-col text-2xl font-bold tracking-normal text-gray-950 dark:text-slate-50 sm:text-4xl ">
              Upload Knowledge Base Documents
            </h1>
            <p className="mt-3 max-w-3xl text-sm font-medium text-gray-600 dark:text-slate-400 sm:text-base">
              Add new materials to EduBot&apos;s central repository. Supported formats are
              automatically indexed and chunked.
            </p>
          </div>

          <button
            type="button"
            onClick={fetchDocuments}
            className="flex items-center justify-center gap-2 rounded-xl border border-accent-soft bg-white px-5 py-2.5 text-sm font-medium text-accent-strong transition hover:bg-accent-soft dark:bg-accent-soft-dark dark:text-accent-soft dark:hover:bg-accent-soft dark:hover:text-white"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
        </div>

        <label
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          className={`flex min-h-[310px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition  ${
            uploading
              ? "border-accent-soft bg-accent-soft/50 dark:border-indigo-300/50 dark:bg-slate-900/70"
              : "border-gray-300 bg-white hover:border-accent-soft hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900/60 dark:hover:border-indigo-300/70 dark:hover:bg-slate-900"
          }`}
        >
          <input
            type="file"
            accept=".pdf,.docx,.txt,.html,.htm,.csv,.md,.markdown,.json,.xlsx,.xls,.sql,.dump,.png,.jpg,.jpeg,.webp"
            onChange={handleFileUpload}
            disabled={uploading}
            className="sr-only"
          />
          <span className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-accent-soft text-accent-strong dark:bg-slate-950 dark:text-indigo-200 sm:h-20 sm:w-20">
            <UploadCloud className="h-9 w-9" />
          </span>
          <span className="text-xl font-bold text-gray-950 dark:text-slate-100 sm:text-2xl">
            {uploading ? "Uploading document..." : "Click to upload or drag and drop"}
          </span>
          <span className="mt-3 text-base font-medium text-gray-500 dark:text-slate-400 ">
            PDF, DOCX, TXT, CSV, XLSX, images and more supported.
          </span>
        </label>

        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800/80">
          <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <h2 className="text-xl font-bold text-gray-950 dark:text-slate-100 sm:text-2xl">Active Uploads</h2>
            {uploading ? (
              <span className="text-sm font-semibold text-accent-strong dark:text-indigo-200">
                {uploadPercent < 100 ? `${uploadPercent}% uploaded` : "Processing"}
              </span>
            ) : null}
          </div>

          {uploading ? (
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-950/50">
              <div className="flex items-center gap-4">
                <FileText className="h-6 w-6 flex-none text-gray-500 dark:text-slate-300" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                    <p className="truncate text-base font-bold text-gray-950 dark:text-slate-100">{uploadName}</p>
                    <p className="text-sm font-semibold text-gray-600 dark:text-slate-300">
                      {uploadPercent < 100 ? `${uploadPercent}%` : "Processing"}
                    </p>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-slate-800">
                    <div
                      className="h-full rounded-full bg-accent transition-all duration-200 dark:bg-indigo-300"
                      style={{ width: `${uploadPercent}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <p className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-4 text-sm font-medium text-gray-500 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-400">
              No active uploads.
            </p>
          )}
        </div>

        {uploadSummary ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 shadow-sm dark:border-emerald-400/20 dark:bg-emerald-500/10">
            <div className="mb-5 flex items-center gap-3">
              <CheckCircle2 className="h-6 w-6 flex-none text-emerald-600 dark:text-emerald-300" />
              <h2 className="text-xl font-bold text-gray-950 dark:text-slate-100">Upload successful</h2>
            </div>

            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              {uploadSummaryRows.map(([label, value]) => (
                <div
                  key={label}
                  className="flex flex-col gap-1 rounded-lg border border-emerald-200/80 bg-white px-4 py-3 dark:border-emerald-400/15 dark:bg-slate-950/40"
                >
                  <dt className="font-semibold text-gray-500 dark:text-slate-400">{label}</dt>
                  <dd className="break-words font-bold text-gray-950 dark:text-slate-100">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}

        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
          <div className="flex flex-col gap-2 border-b border-gray-200 bg-gray-100 px-4 py-5 dark:border-slate-700 dark:bg-[#211f28] sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <h2 className="text-xl font-bold text-gray-950 dark:text-slate-100 sm:text-2xl">Uploaded Documents</h2>
            <span className="text-sm font-semibold text-accent-strong dark:text-indigo-200">{documents.length} files</span>
          </div>

          {documents.length === 0 ? (
            <p className="px-6 py-7 text-sm font-medium text-gray-500 dark:text-slate-400">
              No documents uploaded yet.
            </p>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-slate-700">
              {documents.map((doc) => (
                <div
                  key={doc}
                  className="flex flex-col gap-4 bg-white px-4 py-5 dark:bg-slate-900/70 sm:flex-row sm:items-center sm:justify-between sm:px-6"
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <CheckCircle2 className="h-5 w-5 flex-none text-emerald-600 dark:text-emerald-300" />
                    <div className="min-w-0">
                      <p className="truncate text-base font-bold text-gray-950 dark:text-slate-100">{doc}</p>
                      <p className="text-sm font-semibold text-gray-500 dark:text-slate-400">Ready</p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setDeleteTarget(doc)}
                    className="inline-flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600 transition hover:bg-red-100 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200 dark:hover:bg-red-500/20"
                    aria-label={`Delete ${doc}`}
                    title="Delete document"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {deleteTarget ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm dark:bg-slate-950/75"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-document-title"
        >
          <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-200">
                  <AlertTriangle className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <h2 id="delete-document-title" className="text-xl font-bold text-gray-950 dark:text-slate-100">
                    Are you sure you want to delete?
                  </h2>
                  <p className="mt-2 break-words text-sm font-medium text-gray-500 dark:text-slate-400">
                    {deleteTarget}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                aria-label="Close delete confirmation"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-bold text-gray-700 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={deleting}
                className="rounded-lg bg-red-500 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {deleting ? "Deleting..." : "Yes"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default AdminDocuments;
