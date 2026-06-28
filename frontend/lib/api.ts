// Typed fetch client to the Graphy AI FastAPI backend.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Sent only when the backend gate is enabled (GRAPHY_API_KEY set).
// Configure NEXT_PUBLIC_API_KEY to match; omitted entirely when unset.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

function authHeaders(base: Record<string, string> = {}): Record<string, string> {
  return API_KEY ? { ...base, "X-API-Key": API_KEY } : base;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-json error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}${path}`, { cache: "no-store", headers: authHeaders() }),
  );
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }),
  );
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }),
  );
}

export interface Health {
  status: string;
  app: string;
  llm_provider: string;
  gemini_key_set: boolean;
  embed_backend: string;
}

export interface Resume {
  id: number;
  filename: string;
  parsed_profile: ParsedProfile | null;
  created_at: string;
}

export interface ParsedProfile {
  summary?: string;
  skills?: { name: string; category?: string }[];
  experience?: { title?: string; company?: string; start?: string; end?: string; bullets?: string[] }[];
  projects?: { name?: string; description?: string; technologies?: string[] }[];
  education?: { degree?: string; institution?: string; year?: string }[];
}

export interface Job {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  opportunity_type: string;
  description: string | null;
  url: string | null;
  created_at: string;
}

export interface Match {
  id: number;
  job_id: number;
  score: number;
  skill_overlap: string[] | null;
  missing_skills: string[] | null;
  recommendation: string | null;
  breakdown: {
    semantic: number;
    skill_overlap_ratio: number;
    llm_fit: number;
    weights: Record<string, number>;
  } | null;
}

export interface ResumeVersion {
  id: number;
  resume_id: number;
  job_id: number | null;
  label: string;
  content: string;
  fact_trace: Record<string, string> | null;
  stripped_claims: string[] | null;
  created_at: string;
}

// --- Phase 1 calls ---
export const uploadResume = (form: FormData) =>
  apiUpload<Resume>("/resumes/upload", form);
export const listResumes = () => apiGet<Resume[]>("/resumes");
export const createJob = (job: Partial<Job> & { title: string; description: string }) =>
  apiPost<Job>("/jobs", job);
export const listJobs = () => apiGet<Job[]>("/jobs");
export const matchResume = (resumeId: number, jobId: number) =>
  apiPost<Match>(`/resumes/${resumeId}/match?job_id=${jobId}`);
export const tailorResume = (resumeId: number, jobId: number, label: string) =>
  apiPost<ResumeVersion>(`/resumes/${resumeId}/tailor`, { job_id: jobId, label });

// --- GitHub analysis ---
export interface SkillGraph {
  languages?: string[];
  frameworks?: string[];
  libraries?: string[];
  tools?: string[];
  domains?: string[];
}

export interface GithubProfile {
  id: number;
  username: string;
  languages: Record<string, number> | null;
  skill_graph: SkillGraph | null;
}

export interface GithubProject {
  id: number;
  name: string;
  description: string | null;
  primary_language: string | null;
  topics: string[] | null;
  technologies: string[] | null;
  category: string | null;
}

export interface GithubAnalysis {
  profile: GithubProfile;
  projects: GithubProject[];
  repo_count: number;
}

export const discoverJobs = (input: { url?: string; query?: string }) =>
  apiPost<Job[]>("/jobs/discover", input);

export const analyzeGithub = () => apiPost<GithubAnalysis>("/github/analyze");
export const getGithubProfile = () => apiGet<GithubProfile | null>("/github/profile");
export const getGithubProjects = () => apiGet<GithubProject[]>("/github/projects");

// --- Phase 3: applications (human-in-the-loop apply pipeline) ---
export type ApplicationStatus =
  | "pending_approval"
  | "approved"
  | "rejected"
  | "prepared"
  | "submitted"
  | "confirmed"
  | "interview"
  | "offer"
  | "closed";

export interface Application {
  id: number;
  job_id: number;
  resume_version_id: number | null;
  cover_letter_id: number | null;
  status: ApplicationStatus;
  submitted_at: string | null;
  created_at: string;
}

export interface ApplicationLog {
  id: number;
  event: string;
  detail: string | null;
  created_at: string;
}

export interface ApplicationEvidence {
  id: number;
  kind: string; // "screenshot" | "payload"
  file_path: string | null;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface ApplicationDetail extends Application {
  logs: ApplicationLog[];
  evidence: ApplicationEvidence[];
}

export const listResumeVersions = (resumeId: number) =>
  apiGet<ResumeVersion[]>(`/resumes/${resumeId}/versions`);

export const createApplication = (input: {
  job_id: number;
  resume_version_id?: number | null;
  cover_letter_id?: number | null;
}) => apiPost<Application>("/applications", input);

export const listApplications = () => apiGet<Application[]>("/applications");
export const pendingApplications = () =>
  apiGet<Application[]>("/applications/pending");
export const getApplication = (id: number) =>
  apiGet<ApplicationDetail>(`/applications/${id}`);
export const approveApplication = (id: number) =>
  apiPost<Application>(`/applications/${id}/approve`);
export const rejectApplication = (id: number) =>
  apiPost<Application>(`/applications/${id}/reject`);

// submit=false → navigate, fill, upload & screenshot only (no real submission).
// submit=true  → also click the page's submit button (real, after approval).
export const submitApplication = (
  id: number,
  body: { submit: boolean; name?: string; email?: string; phone?: string },
) => apiPost<ApplicationDetail>(`/applications/${id}/submit`, body);

// Direct URL to an evidence file (screenshot). Works in local mode where the
// API-key gate is off; an <img src> can't send the X-API-Key header.
export const evidenceFileUrl = (appId: number, evidenceId: number) =>
  `${API_BASE}/applications/${appId}/evidence/${evidenceId}/file`;

// --- Phase 4: cover letters ---
export interface CoverLetter {
  id: number;
  job_id: number | null;
  content: string;
  fact_trace: Record<string, string> | null;
  created_at: string;
  stripped_claims: string[] | null;
}

export const writeCoverLetter = (resumeId: number, jobId: number) =>
  apiPost<CoverLetter>(`/resumes/${resumeId}/cover-letter`, { job_id: jobId });

// --- Phase 4: notifications (Gmail-fed inbox) ---
export interface AppNotification {
  id: number;
  application_id: number | null;
  kind: string; // confirmation | interview | rejection | recruiter
  subject: string | null;
  body: string | null;
  read: boolean;
  created_at: string;
}

export interface GmailSync {
  configured: boolean;
  reason: string | null;
  scanned: number;
  created: number;
  updated: number;
}

export const listNotifications = () =>
  apiGet<AppNotification[]>("/notifications");
export const gmailStatus = () => apiGet<GmailSync>("/notifications/gmail/status");
export const syncGmail = () => apiPost<GmailSync>("/notifications/sync");
export const markNotificationRead = (id: number) =>
  apiPost<AppNotification>(`/notifications/${id}/read`);

// --- Phase 4: dashboard analytics ---
export interface MatchBucket {
  label: string;
  count: number;
}

export interface ActivityItem {
  application_id: number | null;
  event: string;
  detail: string | null;
  created_at: string;
}

export interface DashboardSummary {
  totals: Record<string, number>;
  by_status: Record<string, number>;
  response_rate: number;
  match_distribution: MatchBucket[];
  library: Record<string, number>;
  unread_notifications: number;
  github_analyzed: boolean;
  recent_activity: ActivityItem[];
}

export const getDashboardSummary = () =>
  apiGet<DashboardSummary>("/dashboard/summary");
