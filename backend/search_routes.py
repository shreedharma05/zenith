"""Resume upload + job search/match endpoints, wrapping the existing
`zenith` matching pipeline behind authentication.

Each user gets their own in-memory `SearchSession` (keyed by user id), which
is what gives them the resumable discovery/enrichment behaviour: calling
/api/search again continues a rate-limited search instead of restarting it.
This is process-local (fine for a single backend worker; a multi-worker or
multi-instance production deployment would need to move this state into a
shared store such as Redis).
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool
from sqlalchemy import desc
from sqlalchemy.orm import Session

from zenith import config as zconfig
from zenith.profile_extractor import ProfileExtractionError
from zenith.workflow import SearchResult, SearchSession

from .database import get_db
from .deps import get_current_verified_user
from .models import ResumeVersion, User
from .resume_storage import load_resume, save_resume

router = APIRouter(prefix="/api/search", tags=["search"])

# Fetch descriptions for only the best-matching N pending jobs per call, so a
# search with a large result set still returns promptly. The rest stay
# "pending" and are picked up by the next call (e.g. "Continue search"),
# which never restarts discovery/enrichment from scratch.
_ENRICH_BATCH_SIZE = 60

# Server-side cap independent of the UI's default -- protects the LinkedIn
# discovery pipeline from a request that lists an unreasonable number of
# locations (each spawns its own full pagination pass).
_MAX_LOCATIONS = 10

# Discovery walks LinkedIn result pages (newest first) one paced request at a
# time, so an uncapped location can cost minutes for jobs that are then never
# described or matched. Only the newest N per location are collected.
_MAX_JOBS_PER_LOCATION = 150

_sessions: dict[int, SearchSession] = {}
logger = logging.getLogger(__name__)


def _parse_locations(locations: str) -> list[str]:
    parsed = [loc.strip() for loc in locations.split(",") if loc.strip()]
    return parsed[:_MAX_LOCATIONS]


def _latest_resume(user: User, db: Session, resume_id: int | None) -> ResumeVersion | None:
    if resume_id is not None:
        saved = db.get(ResumeVersion, resume_id)
        return saved if saved is not None and saved.user_id == user.id else None
    return db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).order_by(
        desc(ResumeVersion.created_at), desc(ResumeVersion.id)
    ).first()


async def _read_or_load_resume(
    user: User, db: Session, resume: UploadFile | None, resume_id: int | None,
) -> tuple[bytes, str]:
    if resume is not None:
        # Reject by the size Starlette already tracked while parsing the
        # multipart body, before we ever buffer it fully or upload it to R2.
        if resume.size is not None and resume.size > zconfig.MAX_RESUME_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume must be 10 MB or smaller.")
        data = await resume.read()
        if len(data) > zconfig.MAX_RESUME_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume must be 10 MB or smaller.")
        filename = resume.filename or "resume.txt"
        try:
            object_key, object_version_id = save_resume(user.id, filename, data)
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
        except Exception:
            logger.exception("Could not save resume for user %s", user.id)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not save your resume. Please retry.") from None
        db.add(ResumeVersion(
            user_id=user.id,
            object_key=object_key,
            object_version_id=object_version_id,
            filename=filename,
        ))
        db.commit()
        return data, filename

    saved = _latest_resume(user, db, resume_id)
    if saved is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a resume before searching.")
    try:
        return load_resume(saved.object_key, saved.object_version_id), saved.filename
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Saved resume is temporarily unavailable.") from None


@router.get("/resumes")
def latest_resume(
    user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> dict | None:
    saved = _latest_resume(user, db, None)
    if saved is None:
        return None
    return {"id": saved.id, "filename": saved.filename, "created_at": saved.created_at.isoformat()}


def _session_for(user: User) -> SearchSession:
    session = _sessions.get(user.id)
    if session is None:
        session = SearchSession()
        _sessions[user.id] = session
    return session


def _serialize(outcome: SearchResult) -> dict:
    return {
        "keywords": outcome.keywords,
        "fetched": outcome.fetched,
        "enriched": outcome.enriched,
        "pending": outcome.pending,
        "discovery_complete": outcome.discovery_complete,
        "can_continue": outcome.pending > 0 or not outcome.discovery_complete,
        "warnings": outcome.warnings,
        "rejected": outcome.rejected,
        "timings": outcome.timings,
        "profile_reused": outcome.profile_reused,
        "jobs_reused": outcome.jobs_reused,
        "profile": {
            "name": outcome.profile.name,
            "skills": outcome.profile.skills,
            "primary_skills": outcome.profile.primary_skills,
            "total_years_experience": outcome.profile.total_years_experience,
            "locations": outcome.profile.locations,
        },
        "matches": [
            {
                "id": match.job.id,
                "title": match.job.title,
                "company": match.job.company,
                "location": match.job.location,
                "url": match.job.url,
                "label": match.label,
                "score": match.score,
                "posted_at": match.job.posted_at.isoformat() if match.job.posted_at else None,
            }
            for match in outcome.matches
        ],
    }


@router.post("")
async def run_search(
    resume: UploadFile | None = File(None),
    resume_id: int | None = Form(None),
    locations: str = Form(""),
    time_posted: str = Form("r604800"),
    include_remote: bool = Form(True),
    force_refresh: bool = Form(False),
    user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> dict:
    data, filename = await _read_or_load_resume(user, db, resume, resume_id)
    session = _session_for(user)
    try:
        # session.run() is synchronous, blocking I/O (LLM calls, LinkedIn
        # scraping) that can take minutes -- run it off the event loop so one
        # user's long search doesn't freeze every other request being served
        # by this process.
        outcome = await run_in_threadpool(
            session.run,
            data,
            filename,
            zconfig.LLM_PROVIDER,
            _parse_locations(locations),
            time_posted,
            include_remote=include_remote,
            force_refresh=force_refresh,
            per_location=_MAX_JOBS_PER_LOCATION,
            enrich_limit=_ENRICH_BATCH_SIZE,
        )
    except ProfileExtractionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return _serialize(outcome)


# Approximate percentage checkpoints for the pipeline's fixed, short stages;
# the discovery/enrichment branches below compute a real percentage from the
# actual "done/total" counts already reported by zenith.workflow's progress
# callback, since those are the stages that actually take most of the time.
_LOCATION_PROGRESS = re.compile(r"Searching locations (\d+)/(\d+)")
_DETAIL_PROGRESS = re.compile(r"Reading job details (\d+)/(\d+) ")


def _progress_event(message: str) -> dict:
    match = _LOCATION_PROGRESS.search(message)
    if match:
        done, total = int(match.group(1)), int(match.group(2))
        return {"type": "progress", "message": message, "percent": 10 + round(30 * done / max(total, 1))}
    match = _DETAIL_PROGRESS.search(message)
    if match:
        done, total = int(match.group(1)), int(match.group(2))
        # Drop the "(N cached responses)" detail -- that's our own internal
        # optimization, not something a job seeker needs to know about.
        clean_message = f"Reading job details {done}/{total}"
        return {"type": "progress", "message": clean_message, "percent": 40 + round(50 * done / max(total, 1))}
    if message.startswith("Reading resume"):
        return {"type": "progress", "message": message, "percent": 5}
    if message.startswith("Searching LinkedIn for"):
        return {"type": "progress", "message": message, "percent": 10}
    if message.startswith("Reading job details for"):
        return {"type": "progress", "message": message, "percent": 40}
    if message.startswith("Reusing"):
        return {"type": "progress", "message": message, "percent": 85}
    if message.startswith("Matching"):
        return {"type": "progress", "message": message, "percent": 92}
    return {"type": "progress", "message": message, "percent": None}


@dataclass
class _SearchJob:
    id: str
    user_id: int
    status: str = "running"  # running | done | error
    message: str = "Starting search…"
    percent: int | None = None
    result: dict | None = None
    error: str | None = None
    updated_at: float = 0.0


# A search can take minutes, longer than proxies/hosts keep a single HTTP
# request open. So it runs in a background thread and the client polls short
# requests for its status, which also survives a page refresh or a dropped
# connection. Process-local, like `_sessions`.
_JOB_RETENTION_SECONDS = 60 * 60
_jobs: dict[str, _SearchJob] = {}
_jobs_lock = threading.Lock()


def _job_payload(job: _SearchJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "percent": job.percent,
        "result": job.result,
        "error": job.error,
    }


def _running_job(user_id: int) -> _SearchJob | None:
    return next((j for j in _jobs.values() if j.user_id == user_id and j.status == "running"), None)


def _run_job(job: _SearchJob, session: SearchSession, search_args: tuple, search_kwargs: dict) -> None:
    def progress(message: str) -> None:
        event = _progress_event(message)
        with _jobs_lock:
            job.message = event["message"]
            job.percent = event["percent"]
            job.updated_at = time.time()

    try:
        outcome = session.run(*search_args, progress=progress, **search_kwargs)
        result, error = _serialize(outcome), None
    except ProfileExtractionError as exc:
        result, error = None, str(exc)
    except Exception:
        logger.exception("Search failed for user %s", job.user_id)
        result, error = None, "Search failed. Please retry."
    with _jobs_lock:
        job.result, job.error = result, error
        job.status = "done" if error is None else "error"
        if error is None:
            job.percent = 100
        job.updated_at = time.time()


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def start_search_job(
    resume: UploadFile | None = File(None),
    resume_id: int | None = Form(None),
    locations: str = Form(""),
    time_posted: str = Form("r604800"),
    include_remote: bool = Form(True),
    force_refresh: bool = Form(False),
    user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> dict:
    with _jobs_lock:
        if _running_job(user.id) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A search is already running. Please wait for it to finish.")
    data, filename = await _read_or_load_resume(user, db, resume, resume_id)
    session = _session_for(user)
    job = _SearchJob(id=uuid.uuid4().hex, user_id=user.id, updated_at=time.time())
    with _jobs_lock:
        if _running_job(user.id) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A search is already running. Please wait for it to finish.")
        cutoff = time.time() - _JOB_RETENTION_SECONDS
        for stale_id in [j.id for j in _jobs.values() if j.status != "running" and j.updated_at < cutoff]:
            del _jobs[stale_id]
        _jobs[job.id] = job
    search_args = (data, filename, zconfig.LLM_PROVIDER, _parse_locations(locations), time_posted)
    search_kwargs = {
        "include_remote": include_remote,
        "force_refresh": force_refresh,
        "per_location": _MAX_JOBS_PER_LOCATION,
        "enrich_limit": _ENRICH_BATCH_SIZE,
    }
    threading.Thread(target=_run_job, args=(job, session, search_args, search_kwargs), daemon=True).start()
    return {"job_id": job.id}


@router.get("/jobs/active")
def active_search_job(user: User = Depends(get_current_verified_user)) -> dict | None:
    with _jobs_lock:
        job = _running_job(user.id)
        return _job_payload(job) if job is not None else None


@router.get("/jobs/{job_id}")
def get_search_job(job_id: str, user: User = Depends(get_current_verified_user)) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "This search is no longer available (the server may have restarted). Please retry.",
            )
        return _job_payload(job)
