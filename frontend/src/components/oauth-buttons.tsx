// Plain <a> navigations (not fetch calls) -- OAuth requires a real top-level
// redirect chain to the provider and back, which a fetch/XHR can't do.
const PROVIDERS = [
  {
    key: "google",
    label: "Continue with Google",
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
        <path fill="#4285F4" d="M23.49 12.27c0-.79-.07-1.54-.2-2.27H12v4.3h6.47c-.28 1.48-1.13 2.73-2.4 3.57v2.96h3.88c2.27-2.09 3.54-5.17 3.54-8.56Z" />
        <path fill="#34A853" d="M12 24c3.24 0 5.95-1.07 7.93-2.9l-3.88-2.96c-1.07.72-2.45 1.15-4.05 1.15-3.12 0-5.76-2.1-6.7-4.93H1.3v3.09C3.26 21.3 7.31 24 12 24Z" />
        <path fill="#FBBC05" d="M5.3 14.36A7.2 7.2 0 0 1 4.9 12c0-.82.14-1.62.4-2.36V6.55H1.3A11.98 11.98 0 0 0 0 12c0 1.93.46 3.76 1.3 5.45l4-3.09Z" />
        <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.94 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.3 6.55l4 3.09c.94-2.83 3.58-4.89 6.7-4.89Z" />
      </svg>
    ),
  },
  {
    key: "linkedin",
    label: "Continue with LinkedIn",
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="#0A66C2" aria-hidden="true">
        <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.38-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14ZM7.12 20.45H3.56V9h3.56v11.45Z" />
      </svg>
    ),
  },
] as const;

export function OAuthButtons() {
  return (
    <div className="mt-6 space-y-3">
      <div className="flex items-center gap-3 text-xs font-medium text-slate-400">
        <span className="h-px flex-1 bg-slate-200" /> Or continue with <span className="h-px flex-1 bg-slate-200" />
      </div>
      {PROVIDERS.map((provider) => (
        <a
          key={provider.key}
          href={`/api/auth/oauth/${provider.key}/start`}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          {provider.icon}
          {provider.label}
        </a>
      ))}
    </div>
  );
}
