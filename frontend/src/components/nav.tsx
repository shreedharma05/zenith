"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { buttonClasses } from "@/components/ui";

export function Nav() {
  const { user, logout } = useAuth();
  return (
    <header className="sticky top-0 z-20 border-b border-slate-100 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-slate-900">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
          Zenith
        </Link>
        <nav className="hidden items-center gap-8 text-sm font-medium text-slate-600 md:flex">
          <Link href="/#how-it-works" className="hover:text-slate-900">
            How it works
          </Link>
        </nav>
        {user ? (
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className={buttonClasses("secondary")}>
              Dashboard
            </Link>
            <button onClick={() => logout()} className={buttonClasses("primary")}>
              Sign out
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Link href="/login" className={buttonClasses("secondary")}>
              Log in
            </Link>
            <Link href="/signup" className={buttonClasses("primary")}>
              Get started
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
