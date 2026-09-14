"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AuthShell } from "@/components/auth-shell";
import { api, ApiError } from "@/lib/api";

function VerifyEmailStatus() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("Verifying your email…");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This verification link is missing its token.");
      return;
    }
    api
      .verifyEmail(token)
      .then((response) => {
        setStatus("success");
        setMessage(response.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "This verification link is invalid or has expired.");
      });
  }, [token]);

  return (
    <div className="space-y-4 text-sm">
      <p className={status === "error" ? "text-red-600" : "text-slate-700"}>{message}</p>
      {status === "success" && (
        <Link href="/login" className="font-semibold text-blue-600">
          Continue to login →
        </Link>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <AuthShell title="Verify your email">
      <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
        <VerifyEmailStatus />
      </Suspense>
    </AuthShell>
  );
}
