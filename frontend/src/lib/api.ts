// Relative -- requests are same-origin, proxied to the backend by the
// /api/[...path] route handler (works identically in dev and production).
const API_URL = "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Turns a failed response into a user-readable message: handles FastAPI's
// string `detail`, 422 validation-error lists, and non-JSON bodies (HTML
// error pages from a proxy/host) that would otherwise surface as raw
// status text.
async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string" && data.detail) return data.detail;
    if (Array.isArray(data.detail)) {
      const messages = data.detail
        .map((item: { msg?: unknown }) => (typeof item?.msg === "string" ? item.msg : ""))
        .filter(Boolean);
      if (messages.length) return messages.join(" ");
    }
  } catch {
    // no JSON body
  }
  if (response.status === 401) return "Your session has expired. Please sign in again.";
  if (response.status === 413) return "The file is too large.";
  if (response.status === 429) return "Too many requests. Please wait a moment and try again.";
  if (response.status >= 500) return "The server had a problem or is unreachable. Please try again shortly.";
  return response.statusText || "Request failed. Please try again.";
}

// fetch() rejects (instead of returning a response) when the server can't be
// reached at all; status 0 marks that case.
async function safeFetch(input: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await safeFetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export type User = {
  id: number;
  email: string;
  full_name: string;
  is_verified: boolean;
};

export type ResumeMetadata = {
  id: number;
  filename: string;
  created_at: string;
};

export type ScoredJobOut = {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  label: string;
  score: number;
  posted_at: string | null;
};

export type SearchResult = {
  keywords: string;
  fetched: number;
  enriched: number;
  pending: number;
  discovery_complete: boolean;
  can_continue: boolean;
  warnings: string[];
  rejected: Record<string, number>;
  timings: Record<string, number>;
  profile_reused: boolean;
  jobs_reused: boolean;
  profile: {
    name: string;
    skills: string[];
    primary_skills: string[];
    total_years_experience: number;
    locations: string[];
  };
  matches: ScoredJobOut[];
};

type MessageResponse = { message: string };

// A search runs as a background job on the server (it can take minutes, far
// longer than a single HTTP request survives); the client polls its status.
export type SearchJob = {
  id: string;
  status: "running" | "done" | "error";
  message: string;
  percent: number | null;
  result: SearchResult | null;
  error: string | null;
};

export const api = {
  signup: (email: string, password: string, fullName: string) =>
    request<User>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),
  login: (email: string, password: string, remember: boolean = true) =>
    request<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password, remember }) }),
  logout: () => request<MessageResponse>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  latestResume: () => request<ResumeMetadata | null>("/api/search/resumes"),
  resendVerification: () => request<MessageResponse>("/api/auth/resend-verification", { method: "POST" }),
  verifyEmail: (token: string) =>
    request<MessageResponse>(`/api/auth/verify-email?token=${encodeURIComponent(token)}`, { method: "POST" }),
  forgotPassword: (email: string) =>
    request<MessageResponse>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, password: string) =>
    request<MessageResponse>("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }),
  search: (form: FormData) => request<SearchResult>("/api/search", { method: "POST", body: form }),
  startSearch: (form: FormData) => request<{ job_id: string }>("/api/search/jobs", { method: "POST", body: form }),
  searchJob: (jobId: string) => request<SearchJob>(`/api/search/jobs/${encodeURIComponent(jobId)}`),
  activeSearchJob: () => request<SearchJob | null>("/api/search/jobs/active"),
};
