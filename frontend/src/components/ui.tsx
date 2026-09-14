import { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes } from "react";

export function buttonClasses(variant: "primary" | "secondary" = "primary"): string {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed";
  if (variant === "primary") {
    return `${base} bg-gradient-to-r from-blue-600 to-violet-600 text-white shadow-lg shadow-blue-600/20 hover:opacity-90`;
  }
  return `${base} border border-slate-200 bg-white text-slate-900 hover:bg-slate-50`;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" };

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return <button className={`${buttonClasses(variant)} ${className}`} {...props} />;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return (
    <input
      {...rest}
      className={`w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 ${className}`}
    />
  );
}

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-3xl border border-slate-200 bg-white p-8 shadow-sm ${className}`} {...props} />;
}

export function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-4 py-1 text-xs font-medium text-slate-600 shadow-sm backdrop-blur">
      {children}
    </span>
  );
}
