import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Jobs
export const getJobs = (params?: Record<string, unknown>) =>
  api.get("/jobs", { params }).then((r) => r.data);
export const getJob = (id: number) => api.get(`/jobs/${id}`).then((r) => r.data);
export const updateJobStatus = (id: number, status: string) =>
  api.patch(`/jobs/${id}/status`, null, { params: { status } }).then((r) => r.data);
export const triggerSearch = () =>
  api.post("/jobs/search/trigger").then((r) => r.data);
export const getJobStats = () => api.get("/jobs/stats/summary").then((r) => r.data);

// Emails
export const getEmails = (params?: Record<string, unknown>) =>
  api.get("/emails", { params }).then((r) => r.data);
export const getEmail = (id: number) => api.get(`/emails/${id}`).then((r) => r.data);
export const updateEmail = (id: number, data: Record<string, unknown>) =>
  api.patch(`/emails/${id}`, data).then((r) => r.data);
export const sendEmail = (id: number, overrides?: Record<string, unknown>) =>
  api.post(`/emails/${id}/send`, overrides || {}).then((r) => r.data);
export const createDraftEmail = (data: Record<string, unknown>) =>
  api.post("/emails/draft", data).then((r) => r.data);
export const deleteEmail = (id: number) =>
  api.delete(`/emails/${id}`).then((r) => r.data);

// Applications
export const getApplications = (params?: Record<string, unknown>) =>
  api.get("/applications", { params }).then((r) => r.data);
export const updateApplication = (id: number, data: Record<string, unknown>) =>
  api.patch(`/applications/${id}`, data).then((r) => r.data);
export const getPipelineStats = () =>
  api.get("/applications/stats/pipeline").then((r) => r.data);

// Settings
export const getProfile = () => api.get("/settings/profile").then((r) => r.data);
export const updateProfile = (data: Record<string, unknown>) =>
  api.put("/settings/profile", data).then((r) => r.data);
export const getPreferences = () =>
  api.get("/settings/preferences").then((r) => r.data);
export const updatePreferences = (data: Record<string, unknown>) =>
  api.put("/settings/preferences", data).then((r) => r.data);

// Resume upload: use fetch directly so the browser sets the correct multipart boundary
export const uploadResume = (file: File): Promise<Record<string, unknown>> => {
  const form = new FormData();
  form.append("file", file);
  return fetch("/api/settings/resume", { method: "POST", body: form })
    .then(async (r) => {
      if (!r.ok) {
        const text = await r.text();
        throw new Error(text || `Upload failed: ${r.status}`);
      }
      return r.json() as Promise<Record<string, unknown>>;
    });
};

// Dashboard
export const getDashboard = () => api.get("/dashboard").then((r) => r.data);

// API status / usage tracker
export const getApiStatus = () => api.get("/settings/api-status").then((r) => r.data);

// Bulk apply from URL
export const bulkApplyFromUrl = (url: string, dry_run = false) =>
  api.post("/jobs/bulk-apply", { url, dry_run }).then((r) => r.data);

// Auto-apply via Playwright
export const autoApplyJob = (jobId: number) =>
  api.post(`/jobs/auto-apply/${jobId}`).then((r) => r.data);

// Link verification
export const verifyLinks = () =>
  api.post("/jobs/verify-links").then((r) => r.data);


// Referrals: details, forum discovery, drafted posts
export const getReferralProfile = () => api.get("/referrals/profile").then((r) => r.data);
export const updateReferralProfile = (data: Record<string, unknown>) =>
  api.put("/referrals/profile", data).then((r) => r.data);
export const resetReferralProfileToResume = () =>
  api.post("/referrals/profile/use-resume").then((r) => r.data);
export const getReferralPlatforms = () => api.get("/referrals/platforms").then((r) => r.data);
export const openPlatformLogin = (platform: string) =>
  api.post(`/referrals/login/${platform}`).then((r) => r.data);
export const finishPlatformLogin = () => api.post("/referrals/login-done").then((r) => r.data);
export const discoverReferralThreads = (platforms?: string[]) =>
  api.post("/referrals/discover", { platforms }).then((r) => r.data);
export const composeOpenToWork = (platforms?: string[]) =>
  api.post("/referrals/compose", { platforms }).then((r) => r.data);
export const getForumPosts = (status?: string) =>
  api.get("/referrals/posts", { params: { status } }).then((r) => r.data);
export const updateForumPost = (id: number, data: Record<string, unknown>) =>
  api.patch(`/referrals/posts/${id}`, data).then((r) => r.data);
export const approveForumPost = (id: number) =>
  api.post(`/referrals/posts/${id}/approve`).then((r) => r.data);
