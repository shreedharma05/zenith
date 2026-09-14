"""Core data structures shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CandidateProfile:
    """Structured understanding of the candidate, extracted from the resume."""

    name: str = ""
    current_title: str = ""
    target_titles: list[str] = field(default_factory=list)
    total_years_experience: float = 0.0
    seniority: str = ""  # junior | mid | senior | lead
    skills: list[str] = field(default_factory=list)
    primary_skills: list[str] = field(default_factory=list)  # must-have core skills
    locations: list[str] = field(default_factory=list)
    summary: str = ""
    extraction_method: str = ""
    extraction_warning: str = ""

    def primary_keywords(self) -> str:
        """A search string to feed a job board."""
        if self.target_titles:
            return self.target_titles[0]
        return self.current_title or "Software Engineer"


@dataclass
class Job:
    """A single job listing pulled from a source."""

    id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    posted_at: Optional[datetime] = None
    description: str = ""
    criteria: dict[str, str] = field(default_factory=dict)  # source-provided criteria

    def age_days(self) -> Optional[float]:
        if not self.posted_at:
            return None
        delta = datetime.utcnow() - self.posted_at.replace(tzinfo=None)
        return max(delta.total_seconds() / 86400.0, 0.0)


@dataclass
class AcceptanceCriteria:
    """How well the candidate matches the concrete requirements of a job."""

    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    gap_skills: list[str] = field(default_factory=list)  # asked by JD, candidate lacks
    must_have_matched: list[str] = field(default_factory=list)
    must_have_missing: list[str] = field(default_factory=list)
    experience_required: Optional[float] = None
    experience_upper_limit: Optional[float] = None
    experience_ok: bool = True
    location_match: bool = True
    source_criteria: dict[str, str] = field(default_factory=dict)
    primary_required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    requirement_evidence: list[str] = field(default_factory=list)


@dataclass
class ScoredJob:
    """A job plus the computed match against the candidate."""

    job: Job
    acceptance: AcceptanceCriteria
    label: str = ""  # e.g. "Strong match"
    score: float = 0.0  # internal, for tie-breaking only
    reasons: list[str] = field(default_factory=list)
