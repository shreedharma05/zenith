"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, SearchResult } from "@/lib/api";
import { Button, Card } from "@/components/ui";
import { LoadingOverlay } from "@/components/loading-overlay";

const TIME_OPTIONS: Record<string, string> = {
  "Past 24 hours": "r86400",
  "Past 3 days": "r259200",
  "Past week": "r604800",
  "Past month": "r2592000",
  "Any time": "",
};

const LABEL_STYLES: Record<string, string> = {
  "Strong match": "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Good match": "bg-blue-50 text-blue-700 border-blue-200",
  "Worth a look": "bg-amber-50 text-amber-700 border-amber-200",
  "Experience unverified": "bg-slate-100 text-slate-600 border-slate-200",
};

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [locations, setLocations] = useState("Chennai, Bengaluru");
  const [timeLabel, setTimeLabel] = useState("Past week");
  const [includeRemote, setIncludeRemote] = useState(true);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progressMessage, setProgressMessage] = useState("Starting search…");
  const [progressPercent, setProgressPercent] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [resendState, setResendState] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  async function runSearch(event?: React.FormEvent) {
    event?.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a resume file first.");
      return;
    }
    setBusy(true);
    setError("");
    setProgressMessage("Starting search…");
    setProgressPercent(null);
    try {
      const form = new FormData();
      form.append("resume", file);
      form.append("locations", locations);
      form.append("time_posted", TIME_OPTIONS[timeLabel]);
      form.append("include_remote", String(includeRemote));
      form.append("force_refresh", String(forceRefresh));
      let streamError: string | null = null;
      await api.searchStream(form, (streamEvent) => {
        if (streamEvent.type === "progress") {
          setProgressMessage(streamEvent.message);
          setProgressPercent(streamEvent.percent);
        } else if (streamEvent.type === "done") {
          setProgressPercent(100);
          setResult(streamEvent.result);
        } else {
          streamError = streamEvent.message;
        }
      });
      if (streamError) throw new ApiError(streamError, 0);
      setForceRefresh(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  async function resendVerification() {
    setResendState("Sending…");
    try {
      const response = await api.resendVerification();
      setResendState(response.message);
    } catch {
      setResendState("Could not send verification email. Try again shortly.");
    }
  }

  if (loading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-slate-500">Loading…</div>;
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <LoadingOverlay active={busy} message={progressMessage} percent={progressPercent} />
      <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Find your matching jobs</h1>
      <p className="mt-2 text-slate-600">Upload your resume and Zenith will surface real, currently open roles that fit.</p>

      {!user.is_verified && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <span>Verify your email to run searches. Check your inbox for the link.</span>
          <div className="flex items-center gap-3">
            {resendState && <span className="text-xs text-amber-700">{resendState}</span>}
            <button onClick={resendVerification} className="font-semibold underline">
              Resend email
            </button>
          </div>
        </div>
      )}

      <Card className="mt-8">
        <form onSubmit={runSearch} className="space-y-5">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Resume (PDF, DOCX or TXT)</label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-full file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-700"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Preferred locations</label>
              <input
                value={locations}
                onChange={(event) => setLocations(event.target.value)}
                placeholder="Chennai, Bengaluru"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Posted within</label>
              <select
                value={timeLabel}
                onChange={(event) => setTimeLabel(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              >
                {Object.keys(TIME_OPTIONS).map((label) => (
                  <option key={label}>{label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-sm text-slate-600">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeRemote}
                onChange={(event) => setIncludeRemote(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Include remote
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={forceRefresh}
                onChange={(event) => setForceRefresh(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Force refresh (ignore cache)
            </label>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={busy || !user.is_verified} className="w-full sm:w-auto">
            {busy ? "Searching…" : "Find matching jobs"}
          </Button>
        </form>
      </Card>

      {result && (
        <div className="mt-10 space-y-6">
          <div className="grid gap-4 sm:grid-cols-4">
            <Stat label="Discovered" value={result.fetched} />
            <Stat label="Described" value={result.enriched} />
            <Stat label="Pending analysis" value={result.pending} />
            <Stat label="Matches" value={result.matches.length} />
          </div>

          {!result.discovery_complete && (
            <p className="rounded-2xl border border-blue-200 bg-blue-50 px-5 py-3 text-sm text-blue-800">
              Discovery paused before scanning every page of results — LinkedIn may have more listings.
            </p>
          )}

          {result.can_continue && (
            <Button variant="secondary" onClick={() => runSearch()} disabled={busy}>
              {busy ? "Continuing…" : "Continue search (fetch more)"}
            </Button>
          )}

          {result.warnings.map((warning) => (
            <p key={warning} className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800">
              {warning}
            </p>
          ))}

          <Card>
            <p className="text-sm text-slate-600">
              Search keyword: <span className="font-semibold text-slate-900">{result.keywords}</span> · Core stack:{" "}
              <span className="font-semibold text-slate-900">{result.profile.primary_skills.join(", ") || "—"}</span> ·
              Experience: <span className="font-semibold text-slate-900">{result.profile.total_years_experience}y</span>
            </p>
            {Object.keys(result.rejected).length > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Rejected:{" "}
                {Object.entries(result.rejected)
                  .map(([reason, count]) => `${reason}: ${count}`)
                  .join(" / ")}
              </p>
            )}
          </Card>

          <div className="space-y-4">
            {result.matches.length === 0 && (
              <p className="rounded-2xl border border-slate-200 bg-white px-5 py-8 text-center text-slate-500">
                No verified core-stack matches yet. Check the rejection breakdown above or widen your date range.
              </p>
            )}
            {result.matches.map((job) => (
              <Card key={job.id} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h3 className="text-lg font-semibold text-slate-900">{job.title}</h3>
                    <span
                      className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${
                        LABEL_STYLES[job.label] ?? "border-slate-200 bg-slate-100 text-slate-600"
                      }`}
                    >
                      {job.label}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    {job.company} · {job.location}
                  </p>
                </div>
                <a href={job.url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-blue-600 hover:underline">
                  View listing →
                </a>
              </Card>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-5 text-center">
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
    </Card>
  );
}
