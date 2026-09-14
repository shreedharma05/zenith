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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message: string = response.statusText;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(message, response.status);
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

export type StreamEvent =
  | { type: "progress"; message: string; percent: number | null }
  | { type: "done"; result: SearchResult }
  | { type: "error"; message: string };

// Manual SSE parsing (not EventSource) because EventSource can't send the
// POST body a resume file upload needs. Calls onEvent for each event as it
// arrives so the caller can show real, incremental progress.
async function searchStream(form: FormData, onEvent: (event: StreamEvent) => void): Promise<void> {
  const response = await fetch(`${API_URL}/api/search/stream`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok || !response.body) {
    let message = response.statusText || "Search failed to start.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(message, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      const jsonText = line.slice(5).trim();
      if (jsonText) onEvent(JSON.parse(jsonText) as StreamEvent);
    }
  }
}

export const api = {
  signup: (email: string, password: string, fullName: string) =>
    request<User>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<MessageResponse>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  resendVerification: () => request<MessageResponse>("/api/auth/resend-verification", { method: "POST" }),
  verifyEmail: (token: string) =>
    request<MessageResponse>(`/api/auth/verify-email?token=${encodeURIComponent(token)}`, { method: "POST" }),
  forgotPassword: (email: string) =>
    request<MessageResponse>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, password: string) =>
    request<MessageResponse>("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }),
  search: (form: FormData) => request<SearchResult>("/api/search", { method: "POST", body: form }),
  searchStream,
};
