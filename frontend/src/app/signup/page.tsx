"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { LoadingOverlay } from "@/components/loading-overlay";
import { OAuthButtons } from "@/components/oauth-buttons";
import { Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function SignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api.signup(email, password, fullName);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthShell title="Check your inbox" subtitle={`We sent a verification link to ${email}.`}>
        <p className="text-sm text-slate-600">
          Click the link in that email to activate your account, then{" "}
          <Link href="/login" className="font-semibold text-[#635bff]">
            log in
          </Link>
          .
        </p>
      </AuthShell>
    );
  }

  return (
    <>
      <LoadingOverlay active={submitting} message="Creating your account..." percent={null} />
      <AuthShell
        title="Create your account"
        footer={
          <>
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-[#635bff]">
              Log in
            </Link>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="full-name" className="mb-1.5 block text-sm font-medium text-slate-700">
              Full name
            </label>
            <Input id="full-name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          </div>
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
              Email
            </label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
              Password
            </label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              placeholder="Min 8 characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Creating account…" : "Create account"}
          </Button>
        </form>
        <OAuthButtons />
      </AuthShell>
    </>
  );
}
