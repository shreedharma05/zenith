"""LinkedIn job source using the public *guest* jobs endpoints.

These endpoints power the logged-out "/jobs/search" experience, so no account
credentials are used or put at risk. We still keep volume low and add delays to
be a good citizen. If LinkedIn changes markup or rate-limits you, results will
simply come back empty/short -- that is expected, just try again later.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Callable, Iterable

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .. import config
from ..models import Job

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


class _RequestPacer:
    """Space request starts across all workers and sessions in this process."""

    def __init__(self):
        self.lock = threading.Lock()
        self.next_start = 0.0
        self.blocked_until = 0.0

    def wait(self, delay_range: tuple[float, float]) -> bool:
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self.blocked_until:
                    return False
                delay = self.next_start - now
                if delay <= 0:
                    self.next_start = now + random.uniform(*delay_range)
                    return True
            threading.Event().wait(min(delay, 0.25))

    def cooldown(self, seconds: float) -> None:
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.monotonic() + seconds)
            self.next_start = max(self.next_start, self.blocked_until)


_PACER = _RequestPacer()
_ACCESS_PAUSED = (
    "LinkedIn rate-limited or blocked requests. Results are partial; cached pages remain available. "
    "Pause searches for at least 5 minutes (longer if LinkedIn requests it), then retry with Force refresh off. "
    "LinkedIn may keep the restriction in place longer."
)


def _posted_timestamp(job: Job) -> float:
    if job.posted_at is None:
        return 0.0
    return job.posted_at.replace(tzinfo=job.posted_at.tzinfo or timezone.utc).timestamp()


class LinkedInSource:
    name = "LinkedIn"

    def __init__(self, delay_range: tuple[float, float] | None = None, use_cache: bool = True):
        self.delay_range = delay_range or config.REQUEST_DELAY_RANGE
        self.use_cache = use_cache
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions: list[requests.Session] = []
        self._stopped = threading.Event()
        self.warnings: list[str] = []
        self.cache_hits = 0
        self.network_requests = 0
        os.makedirs(config.CACHE_DIR, exist_ok=True)

    @property
    def session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            session = requests.Session()
            session.headers.update(_HEADERS)
            self._local.session = session
            with self._lock:
                self._sessions.append(session)
        return self._local.session

    def close(self) -> None:
        for session in self._sessions:
            session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def _warn(self, message: str) -> None:
        with self._lock:
            if message not in self.warnings:
                self.warnings.append(message)

    # -- public API ------------------------------------------------------

    def search(
        self,
        keywords: str,
        location: str,
        time_posted: str = "r604800",
        limit: int | None = None,
        fetch_details: bool = True,
    ) -> list[Job]:
        """Fetch available pages until exhausted, unless an explicit limit is supplied."""
        jobs = self._search_cards(keywords, location, time_posted, limit)
        jobs.sort(key=_posted_timestamp, reverse=True)
        if fetch_details:
            self._enrich_many(jobs)
        return jobs

    def search_many(
        self,
        keywords: str,
        locations: Iterable[str],
        time_posted: str = "r604800",
        per_location: int | None = None,
        fetch_details: bool = True,
        progress: Callable[[str], None] | None = None,
        prioritize: Callable[[Job], bool] | None = None,
        detail_limit: int | None = None,
    ) -> list[Job]:
        """Search several locations and merge/dedupe the results."""
        seen: dict[str, Job] = {}
        locations = list(dict.fromkeys(loc.strip() for loc in locations if loc.strip()))
        with ThreadPoolExecutor(max_workers=config.FETCH_WORKERS) as pool:
            searches = {pool.submit(self._search_cards, keywords, loc, time_posted, per_location): loc for loc in locations}
            for completed, future in enumerate(as_completed(searches), 1):
                for job in future.result():
                    seen.setdefault(job.id, job)
                if progress:
                    progress(f"Searching locations {completed}/{len(locations)}: {len(seen)} unique jobs found")

        jobs = sorted(seen.values(), key=_posted_timestamp, reverse=True)
        if fetch_details:
            ordered = sorted(jobs, key=prioritize, reverse=True) if prioritize else jobs
            selected = ordered if detail_limit is None else ordered[:max(0, detail_limit)]
            self._enrich_many(selected, progress)
        return jobs

    def _enrich_many(self, jobs: list[Job], progress: Callable[[str], None] | None = None) -> None:
        with ThreadPoolExecutor(max_workers=config.FETCH_WORKERS) as pool:
            futures = [pool.submit(self._enrich, job) for job in jobs]
            for completed, future in enumerate(as_completed(futures), 1):
                future.result()
                if progress:
                    progress(f"Reading job details {completed}/{len(jobs)} ({self.cache_hits} cached responses)")

    def enrich_pending(self, jobs: list[Job], progress: Callable[[str], None] | None = None) -> None:
        """Fetch descriptions for jobs that don't have one yet, in place.

        Public entry point so callers can enrich a persisted, cross-call job
        list incrementally (resuming after a rate limit) without repeating
        discovery or re-fetching jobs that already have a description.
        """
        self._enrich_many([job for job in jobs if not job.description.strip()], progress)

    # -- internals -------------------------------------------------------

    def _search_cards(self, keywords: str, location: str, time_posted: str, limit: int | None = None) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        start = 0
        while limit is None or len(jobs) < limit:
            params = {
                "keywords": keywords,
                "location": location,
                "start": start,
                "sortBy": "DD",  # date descending -> newest first
            }
            if time_posted:
                params["f_TPR"] = time_posted

            html = self._get(_SEARCH_URL, params)
            if not html:
                break

            page_jobs = self._parse_cards(html)
            if not page_jobs:
                break

            new_jobs = [job for job in page_jobs if job.id not in seen]
            if not new_jobs:
                break
            for job in new_jobs:
                if job.id not in seen:
                    jobs.append(job)
                    seen.add(job.id)
            start += len(page_jobs)

        return jobs if limit is None else jobs[:limit]

    def _parse_cards(self, html: str) -> list[Job]:
        return deepcopy(self._cached_cards(html))

    @staticmethod
    @lru_cache(maxsize=64)
    def _cached_cards(html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[Job] = []
        for card in soup.select("li"):
            base = card.find("div", class_="base-card") or card.find("div", class_="base-search-card")
            if not base:
                continue

            urn = base.get("data-entity-urn", "")
            job_id = urn.split(":")[-1] if urn else ""
            if not job_id:
                continue

            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one(
                "h4.base-search-card__subtitle"
            )
            location_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link") or card.select_one("a")
            time_el = card.select_one("time")

            url = ""
            if link_el and link_el.get("href"):
                url = link_el["href"].split("?")[0]

            jobs.append(
                Job(
                    id=job_id,
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(location_el),
                    url=url,
                    source="LinkedIn",
                    posted_at=_parse_time(time_el),
                )
            )
        return jobs

    def _enrich(self, job: Job) -> None:
        """Fetch the job detail page for full description + criteria."""
        html = self._get(_DETAIL_URL.format(job_id=job.id), None)
        if not html:
            return
        description, criteria = self._cached_detail(html)
        job.description = description
        job.criteria = dict(criteria)

    @staticmethod
    @lru_cache(maxsize=256)
    def _cached_detail(html: str) -> tuple[str, dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")

        desc = soup.select_one("div.show-more-less-html__markup") or soup.select_one(
            "div.description__text"
        )
        description = desc.get_text(" ", strip=True) if desc else ""

        criteria: dict[str, str] = {}
        for item in soup.select("li.description__job-criteria-item"):
            head = item.select_one("h3.description__job-criteria-subheader")
            val = item.select_one("span.description__job-criteria-text")
            if head and val:
                criteria[_text(head)] = _text(val)
        return description, criteria

    def _get(self, url: str, params: dict | None) -> str | None:
        cache_key = self._cache_key(url, params)
        ttl = config.DETAIL_CACHE_TTL_SECONDS if url.startswith(_DETAIL_URL.split("{")[0]) else config.CACHE_TTL_SECONDS
        cached = self._read_cache(cache_key, ttl)
        if cached is not None:
            with self._lock:
                self.cache_hits += 1
            return cached

        for attempt in range(2):
            if self._stopped.is_set() or not _PACER.wait(self.delay_range):
                self._warn(_ACCESS_PAUSED)
                return None
            with self._lock:
                self.network_requests += 1
            try:
                resp = self.session.get(url, params=params, timeout=(5, 15))
            except requests.RequestException:
                if attempt == 0:
                    continue
                self._warn("Some LinkedIn requests timed out or failed. Results may be incomplete.")
                return None
            if resp.status_code in (403, 429):
                retry_after = resp.headers.get("Retry-After", "60")
                try:
                    cooldown = float(retry_after)
                except ValueError:
                    try:
                        cooldown = parsedate_to_datetime(retry_after).timestamp() - time.time()
                    except (TypeError, ValueError, OverflowError):
                        cooldown = 60
                _PACER.cooldown(max(config.REQUEST_COOLDOWN_SECONDS, cooldown))
                self._stopped.set()
                self._warn(_ACCESS_PAUSED)
                return None
            if resp.status_code >= 500 and attempt == 0:
                continue
            if resp.status_code != 200 or (not resp.text.strip() and url != _SEARCH_URL):
                self._warn("Some LinkedIn pages were unavailable. Results may be incomplete.")
                return None
            self._write_cache(cache_key, resp.text)
            return resp.text
        return None

    # -- tiny file cache -------------------------------------------------

    def _cache_key(self, url: str, params: dict | None) -> str:
        raw = url + json.dumps(params or {}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _cache_path(self, key: str) -> str:
        return os.path.join(config.CACHE_DIR, f"{key}.html")

    def _read_cache(self, key: str, ttl: int = config.CACHE_TTL_SECONDS) -> str | None:
        if not self.use_cache:
            return None
        path = self._cache_path(key)
        try:
            if time.time() - os.path.getmtime(path) > ttl:
                return None
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def _write_cache(self, key: str, text: str) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config.CACHE_DIR, delete=False) as fh:
                temporary = fh.name
                fh.write(text)
            os.replace(temporary, self._cache_path(key))
        except OSError:
            pass
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def _text(el) -> str:
    return el.get_text(strip=True) if el else ""


def _parse_time(time_el) -> datetime | None:
    if not time_el:
        return None
    value = time_el.get("datetime", "") or time_el.get_text(strip=True)
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, OverflowError):
        return None
