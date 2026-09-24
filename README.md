# Zenith — AI Job Matching

Zenith reads a candidate's resume, searches LinkedIn's logged-out job listings,
and returns matches scored on real skill overlap, experience fit, and title
relevance — with the evidence for every match shown, not a black-box score.

It's a two-part app:

- **`frontend/`** — Next.js client: signup/login/email verification, resume
  upload, live search progress, and results.
- **`backend/`** — FastAPI service: auth (email/password, JWT cookies,
  Postgres), and the search API that wraps the core matching engine.
- **`zenith/`** — the framework-agnostic matching engine (resume parsing,
  LLM-based profile extraction, LinkedIn scraping, scoring) used by the backend.

---

## Features

- Resume parsing (PDF / DOCX / TXT)
- Skill and experience extraction via an LLM (OpenAI or local Ollama), with a
  deterministic offline fallback if no LLM is reachable
- LinkedIn guest search — no LinkedIn account credentials involved
- Resumable, incremental search: discovery (finding job cards) and enrichment
  (fetching descriptions) are separate phases that survive interruptions and
  rate limits; a "Continue search" action picks up exactly where it left off
- Real, live search progress (Server-Sent Events) — not a simulated loader
- Match scoring: skills, years of experience, title/role discipline, location
- Sorted **Strong match**, **Good match**, **Worth a look**, then **Experience
  unverified**; ties broken by skill coverage, then newest posting
- Per-job acceptance criteria: matched/missing skills, experience fit,
  required-skill evidence excerpted from the actual job description

---

## Local development

Requires **Docker Desktop** and **Node.js 18+**.

### 1. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Notes |
| --- | --- | --- |
| `ZENITH_LLM_PROVIDER` | yes | `openai` (recommended) or `ollama` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | if using OpenAI | |
| `OLLAMA_HOST` / `ZENITH_MODEL` | if using Ollama | point at any reachable Ollama server |
| `AUTH_SECRET_KEY` | yes | generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | yes | Postgres connection string (e.g. [Neon](https://neon.tech), free tier); defaults to a local SQLite file if unset |
| `FRONTEND_URL` | yes | used for CORS and email links, e.g. `http://localhost:3000` |
| `COOKIE_SECURE` | yes | `false` for local HTTP dev, `true` once served over HTTPS |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | for real email | any SMTP relay (Resend, SendGrid, Gmail App Password); if left blank, verification/reset emails are logged to the backend console instead of sent — handy for local dev |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_OBJECT_BUCKET` | yes for resume persistence | Cloudflare R2 S3 credentials and bucket. Resume versions use unique object keys managed by the application. `R2_ENDPOINT_URL` is optional and defaults to the account endpoint. |

### 2. Start the backend

```bash
docker compose up -d zenith-api
```

This builds the image, applies database migrations (`create_all` on startup),
and serves the API at <http://localhost:8000>. Check `docker compose logs -f
zenith-api`.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend proxies all `/api/*` calls to the
backend through its own route handler (`frontend/src/app/api/[...path]/route.ts`,
pointed at `BACKEND_URL` in `frontend/.env.local`), so the browser only ever
talks to one origin — this keeps the auth cookie first-party even once
frontend and backend are deployed on two different hosts.

---

## Deployment

- **Frontend**: deploy `frontend/` to [Vercel](https://vercel.com) (set the
  project's root directory to `frontend`). Set `BACKEND_URL` to your deployed
  backend's URL.
- **Backend**: needs a persistent server (not serverless) since a search can
  run for minutes — a small VM (e.g. Oracle Cloud's Always Free tier) running
  `docker compose up -d zenith-api`, or a managed container host like
  Render/Fly.io. An optional `caddy` Compose service (`docker compose --profile
  prod up -d caddy zenith-api`) gets you free auto-TLS via
  [sslip.io](https://sslip.io) if you don't have a domain yet.
- **Database**: [Neon](https://neon.tech) (serverless Postgres, free tier) or
  any Postgres instance. The engine uses `pool_pre_ping` to survive providers
  that silently close idle connections.
- **Email**: any SMTP relay. Resend/SendGrid require a verified sender/domain
  before they'll deliver to arbitrary recipients; a dedicated Gmail account +
  App Password works with zero setup as a stopgap (capped at ~500/day).

Set `AUTH_SECRET_KEY` to a freshly generated value and `COOKIE_SECURE=true` in
production — never reuse the local dev secret.

---

## Configuration reference

Core matching engine settings (pacing, cache TTLs, default locations) live in
[zenith/config.py](zenith/config.py). Web/auth settings live in
[backend/config.py](backend/config.py).

---

## Notes & limits

- Zenith uses LinkedIn's **logged-out guest** job endpoints — it never touches
  LinkedIn account credentials. Requests are deliberately paced (a shared,
  process-wide limiter, not per-worker) to avoid tripping LinkedIn's rate
  limiting; making this faster/more concurrent has been tried and made things
  worse, not better. On a 403/429, the process backs off for at least five
  minutes (or longer if `Retry-After` says so) and the search surfaces a
  partial-results warning rather than failing outright.
- Discovery and enrichment are independently resumable: a rate limit or a
  large result set never discards what's already been found. Each search call
  enriches only the top ~60 best-title-matching pending jobs before
  returning, so results come back promptly; running the search again (or
  clicking "Continue search") fetches more without repeating finished work.
- If no LLM is reachable, Zenith falls back to a deterministic keyword parser
  so the app still works, at lower profile-extraction quality.
- Search-result pages are cached 30 minutes; job descriptions 24 hours.
  Force-refresh bypasses the job cache, not the resume/profile cache.
- Core skills are checked against a job's required sections and work
  statements, not just anywhere in the text — an optional/"nice to have"
  mention can't qualify a match. Conflicting core languages, missing
  mandatory languages, and role-discipline mismatches (e.g. a QA posting
  incidentally mentioning a language) are all rejected.
- Numeric experience minimums must not exceed the resume's actual experience;
  there's no invented allowance. Postings without a stated minimum are
  labelled "Experience unverified" rather than assumed to fit.
- Resume input is capped at 12,000 characters for the LLM call; oversized
  text is rejected rather than silently truncated. Scanned PDFs need OCR
  first.
- Never commit `.env` (already git-ignored) — it holds real secrets
  (database credentials, API keys, SMTP passwords).

---

## Tests

Backend/matching engine (Python):

```bash
python -m unittest discover -s tests -v
# or, inside Docker (recommended -- host Python may differ from the container's):
docker compose exec -T zenith-api python -m unittest discover -s tests -v
```

Frontend build check:

```bash
cd frontend && npm run build
```

Tests use mocked providers and network responses; they do not incur API charges.

## Roadmap

- [ ] Add Naukri source
- [ ] Add Adzuna / Remotive API sources for broader coverage
- [ ] LLM-written tailored cover letter per job
- [ ] Export matches to CSV
- [ ] Sign in with Google / LinkedIn (currently email/password only)

- [ ] Export matches to CSV
