import Link from "next/link";
import { Nav } from "@/components/nav";
import { Badge, buttonClasses } from "@/components/ui";

const STEPS = [
  { title: "Upload your resume", body: "PDF, DOCX, or plain text — parsed into a structured skills profile." },
  { title: "We search for you", body: "Real, live openings matched against your core stack and experience." },
  { title: "See why it fits", body: "Every match shows matched skills, gaps, and experience fit — no black box." },
];

export default function Home() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="relative overflow-hidden px-6 pb-32 pt-24 text-center">
          <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.15),_transparent_60%)]" />
          <div className="mx-auto max-w-3xl">
            <div className="mb-8 flex justify-center">
              <Badge>Now matching resumes to real openings</Badge>
            </div>
            <h1 className="text-5xl font-extrabold tracking-tight text-slate-900 sm:text-6xl">
              Your resume in —{" "}
              <span className="bg-gradient-to-r from-blue-600 to-violet-600 bg-clip-text text-transparent">
                the jobs worth applying to, out.
              </span>
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg text-slate-600">
              Zenith reads your resume, finds real openings that actually fit your skills and experience, and tells
              you exactly why — no more guessing which roles are worth your time.
            </p>
            <div className="mt-10 flex justify-center gap-4">
              <Link href="/signup" className={buttonClasses("primary")}>
                Get started free
              </Link>
              <Link href="/login" className={buttonClasses("secondary")}>
                Log in
              </Link>
            </div>
          </div>
        </section>
        <section id="how-it-works" className="mx-auto max-w-5xl px-6 pb-24">
          <div className="grid gap-6 sm:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.title} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-900">{step.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{step.body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
      <footer className="border-t border-slate-100 py-8 text-center text-sm text-slate-500">
        © {new Date().getFullYear()} Zenith. Part of the XLightHouse family.
      </footer>
    </>
  );
}

