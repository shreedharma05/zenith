import { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes } from "react";

export function buttonClasses(variant: "primary" | "secondary" = "primary"): string {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed";
  if (variant === "primary") {
    return `${base} bg-[#635bff] text-white shadow-sm hover:bg-[#564fe0]`;
  }
  return `${base} border border-slate-200 bg-white text-slate-700 hover:bg-slate-50`;
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
      className={`w-full rounded-lg border border-slate-200 bg-[#f7f7fb] px-3.5 py-2.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-[#635bff] focus:bg-white focus:ring-2 focus:ring-[#635bff]/20 ${className}`}
    />
  );
}

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-2xl border border-slate-200 bg-white p-8 shadow-sm ${className}`} {...props} />;
}

export function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-4 py-1 text-xs font-medium text-slate-600 shadow-sm backdrop-blur">
      {children}
    </span>
  );
}
