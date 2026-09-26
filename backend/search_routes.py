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

import asyncio
import json
import logging
import queue
import re
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
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

_sessions: dict[int, SearchSession] = {}
logger = logging.getLogger(__name__)


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
        data = await resume.read()
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
            [loc.strip() for loc in locations.split(",") if loc.strip()],
            time_posted,
            include_remote=include_remote,
            force_refresh=force_refresh,
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


@router.post("/stream")
async def run_search_stream(
    resume: UploadFile | None = File(None),
    resume_id: int | None = Form(None),
    locations: str = Form(""),
    time_posted: str = Form("r604800"),
    include_remote: bool = Form(True),
    force_refresh: bool = Form(False),
    user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Same search as POST /api/search, but streamed as Server-Sent Events
    so the client can show real progress instead of a simulated countdown."""
    data, filename = await _read_or_load_resume(user, db, resume, resume_id)
    session = _session_for(user)
    events: queue.Queue = queue.Queue()

    def progress(message: str) -> None:
        events.put(_progress_event(message))

    def worker() -> None:
        try:
            outcome = session.run(
                data,
                filename,
                zconfig.LLM_PROVIDER,
                [loc.strip() for loc in locations.split(",") if loc.strip()],
                time_posted,
                include_remote=include_remote,
                force_refresh=force_refresh,
                progress=progress,
                enrich_limit=_ENRICH_BATCH_SIZE,
            )
            events.put({"type": "done", "result": _serialize(outcome)})
        except ProfileExtractionError as exc:
            events.put({"type": "error", "message": str(exc)})
        except Exception:
            events.put({"type": "error", "message": "Search failed. Please retry."})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
