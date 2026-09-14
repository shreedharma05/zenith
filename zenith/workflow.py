"""Session-local orchestration; only public job data uses shared caches."""

from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .matcher import evaluate_jobs, title_matches
from .models import CandidateProfile, Job, ScoredJob
from .profile_extractor import EXTRACTOR_VERSION, ProfileExtractionError, extract_profile
from .resume_parser import extract_text
from .sources import LinkedInSource


@dataclass
class SearchResult:
    profile: CandidateProfile
    matches: list[ScoredJob]
    fetched: int
    enriched: int
    pending: int
    discovery_complete: bool
    warnings: list[str]
    timings: dict[str, float]
    profile_reused: bool
    jobs_reused: bool
    cache_hits: int
    network_requests: int
    rejected: dict[str, int] = field(default_factory=dict)
    keywords: str = ""


@dataclass
class _Discovery:
    """Persisted, cross-call progress for one search: which jobs have been
    found so far (by id) and whether card discovery ran to exhaustion.

    Kept across `SearchSession.run()` calls so a rate limit mid-search never
    throws away what was already found -- the next call for the same search
    resumes discovery/enrichment instead of restarting from nothing.
    """

    key: tuple
    jobs: dict[str, Job] = field(default_factory=dict)
    discovery_complete: bool = False


class SearchSession:
    def __init__(self):
        self._profile_key = None
        self._profile: CandidateProfile | None = None
        self._discovery: _Discovery | None = None

    def get_profile(self, data: bytes, filename: str, provider: str) -> tuple[CandidateProfile, bool]:
        model = config.OPENAI_MODEL if provider == "openai" else config.OLLAMA_MODEL
        key = (hashlib.sha256(data).hexdigest(), filename.rsplit(".", 1)[-1].lower(), provider, model,
               config.OLLAMA_HOST if provider == "ollama" else "openai", EXTRACTOR_VERSION)
        if key == self._profile_key and self._profile is not None:
            return deepcopy(self._profile), True
        if len(data) > 10 * 1024 * 1024:
            raise ProfileExtractionError("Resume must be 10 MB or smaller.")
        try:
            text = extract_text(data, filename)
        except Exception:
            raise ProfileExtractionError("Could not read this resume. Upload a valid PDF, DOCX or UTF-8 TXT file.") from None
        if not text.strip():
            raise ProfileExtractionError("No text found. Scanned PDFs need text recognition before uploading.")
        profile = extract_profile(text, provider=provider)
        if not profile.skills:
            raise ProfileExtractionError("No technical skills found in the resume.")
        if profile.extraction_method != "offline":
            self._profile_key, self._profile = key, deepcopy(profile)
        return profile, False

    def run(
        self, data: bytes, filename: str, provider: str, locations: list[str],
        time_posted: str, include_remote: bool = True, force_refresh: bool = False,
        per_location: int | None = None, progress: Callable[[str], None] | None = None,
        enrich_limit: int | None = None,
    ) -> SearchResult:
        """Run (or resume) a search.

        Discovery (finding job cards) and enrichment (fetching descriptions)
        are separate, independently resumable phases. Calling `run()` again
        with the same inputs -- e.g. after a warning was raised, or via an
        explicit "Continue search" action -- never restarts from scratch: it
        picks up card pagination where it stopped and only fetches
        descriptions for jobs that don't have one yet. Nothing discovered so
        far is ever discarded because of a warning.
        """
        started = time.perf_counter()
        if progress:
            progress(f"Reading resume and extracting profile with {'OpenAI' if provider == 'openai' else 'Local Ollama'}")
        profile, profile_reused = self.get_profile(data, filename, provider)
        profile_finished = time.perf_counter()
        locations = list(dict.fromkeys(location.strip() for location in locations if location.strip()))
        locations = locations or profile.locations or list(config.DEFAULT_LOCATIONS)
        profile.locations = locations
        keywords = profile.primary_skills[0] if profile.primary_skills else profile.primary_keywords()
        key = (keywords, tuple(locations), time_posted, per_location, tuple(profile.primary_skills))

        if force_refresh or self._discovery is None or self._discovery.key != key:
            self._discovery = _Discovery(key=key)
        discovery = self._discovery

        warnings = [profile.extraction_warning] if profile.extraction_warning else []
        cache_hits = network_requests = 0
        pending_before = any(not job.description.strip() for job in discovery.jobs.values())
        work_needed = force_refresh or not discovery.discovery_complete or pending_before
        jobs_reused = not work_needed

        if work_needed:
            with LinkedInSource(use_cache=not force_refresh) as source:
                if force_refresh or not discovery.discovery_complete:
                    if progress:
                        progress(f'Searching LinkedIn for "{keywords}" in {", ".join(locations)}')
                    found = source.search_many(
                        keywords, locations, time_posted, per_location,
                        fetch_details=False, progress=progress,
                    )
                    for job in found:
                        discovery.jobs.setdefault(job.id, job)
                    discovery.discovery_complete = not source.warnings
                    warnings.extend(source.warnings)

                pending = sorted(
                    (job for job in discovery.jobs.values() if not job.description.strip()),
                    key=lambda job: title_matches(profile, job), reverse=True,
                )
                if pending:
                    # Cap how many descriptions this single call fetches, so a
                    # search with thousands of pending jobs still returns
                    # promptly with its best matches -- the rest stay pending
                    # for a later call (e.g. "Continue search") instead of
                    # making the caller wait for all of them up front.
                    batch = pending if enrich_limit is None else pending[: max(0, enrich_limit)]
                    if progress:
                        progress(f"Reading job details for {len(batch)} pending jobs")
                    before = len(source.warnings)
                    source.enrich_pending(batch, progress)
                    warnings.extend(source.warnings[before:])
                cache_hits, network_requests = source.cache_hits, source.network_requests
        elif progress:
            progress(f"Reusing {len(discovery.jobs)} jobs from this session")

        jobs = list(discovery.jobs.values())
        fetch_finished = time.perf_counter()
        pending_count = sum(1 for job in jobs if not job.description.strip())
        if progress:
            progress(f"Matching {len(jobs) - pending_count} described jobs against primary skills and experience")
        rejected: dict[str, int] = {}
        matches = evaluate_jobs(profile, jobs, include_remote=include_remote, diagnostics=rejected)
        finished = time.perf_counter()
        return SearchResult(
            profile, matches, len(jobs), len(jobs) - pending_count, pending_count,
            discovery.discovery_complete, warnings,
            {"profile": profile_finished - started, "fetch": fetch_finished - profile_finished,
             "match": finished - fetch_finished, "total": finished - started},
            profile_reused, jobs_reused, cache_hits, network_requests,
            rejected, keywords,
        )