"use client";

import { useEffect } from "react";

// Full-screen, click-blocking overlay shown while a search request is in
// flight. Message and percent are driven by real Server-Sent Events from the
// backend (zenith/workflow.py's progress callback) -- not a simulated timer
// -- so each stage is shown once, in order, and the percentage reflects
// actual discovered/enriched counts wherever the backend knows them.
export function LoadingOverlay({
  active,
  message,
  percent,
}: {
  active: boolean;
  message: string;
  percent: number | null;
}) {
  useEffect(() => {
    if (!active) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [active]);

  if (!active) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-white/70 backdrop-blur-sm"
      role="alert"
      aria-live="polite"
      aria-busy="true"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="flex w-full max-w-sm flex-col items-center gap-6 rounded-3xl border border-slate-200 bg-white px-10 py-12 text-center shadow-xl">
        <div className="relative flex h-16 w-16 items-center justify-center">
          <div className="absolute inset-0 rounded-full border-4 border-slate-100" />
          <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-blue-600 border-r-violet-600" />
          {percent !== null && <span className="text-sm font-bold text-slate-900">{percent}%</span>}
        </div>
        <div>
          <p key={message} className="zx-fade-in text-base font-semibold text-slate-900">
            {message}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            This can take a little while for uncapped searches — hang tight.
          </p>
        </div>
        <div className="h-1.5 w-48 overflow-hidden rounded-full bg-slate-100">
          {percent !== null ? (
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-600 to-violet-600 transition-all duration-500 ease-out"
              style={{ width: `${percent}%` }}
            />
          ) : (
            <div className="zx-indeterminate h-full w-1/3 rounded-full bg-gradient-to-r from-blue-600 to-violet-600" />
          )}
        </div>
      </div>
    </div>
  );
}

