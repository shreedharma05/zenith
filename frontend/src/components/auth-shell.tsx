import Link from "next/link";

export function AuthShell({
  title,
  subtitle,
  footer,
  children,
}: {
  title: string;
  subtitle?: string;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-white">
      {/* Decorative gradient ribbon, purely cosmetic -- hidden below the card on small screens */}
      <div aria-hidden className="pointer-events-none absolute inset-0 z-0 hidden md:block">
        <div
          className="absolute right-[-15%] top-1/2 h-[170%] w-[55%] rounded-[45%] bg-gradient-to-b from-sky-400 via-orange-400 to-fuchsia-600 opacity-90 blur-2xl"
          style={{ transform: "translateY(-50%) rotate(24deg)" }}
        />
        <div
          className="absolute right-[8%] top-1/2 h-[150%] w-[36%] rounded-[45%] bg-gradient-to-b from-indigo-500 via-rose-500 to-orange-400 opacity-80 blur-2xl"
          style={{ transform: "translateY(-50%) rotate(16deg)" }}
        />
      </div>

      <Link href="/" className="absolute left-8 top-8 z-10 text-base font-bold tracking-tight text-slate-900">
        Zenith
      </Link>

      <div className="relative z-10 flex flex-1 items-center justify-center px-6 py-20">
        <div className="w-full max-w-sm">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_rgba(15,23,42,0.06)]">
            <div className="p-8">
              <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
              {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}
              <div className="mt-6">{children}</div>
            </div>
            {footer && (
              <div className="border-t border-slate-100 bg-slate-50/60 px-8 py-4 text-center text-sm text-slate-600">
                {footer}
              </div>
            )}
          </div>
          <p className="mt-6 text-center text-xs text-slate-400">
            © {new Date().getFullYear()} Zenith ·{" "}
            <Link href="/" className="hover:text-slate-600">
              Privacy &amp; terms
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
