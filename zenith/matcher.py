"""Match independently extracted role requirements to the candidate's core stack."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .models import AcceptanceCriteria, CandidateProfile, Job, ScoredJob
from .profile_extractor import _COMMON_SKILLS

# Vocabulary used to detect what a job posting asks for.
_KNOWN_SKILLS = sorted(set(_COMMON_SKILLS.values()), key=str.lower)

# Canonicalise variants the candidate might type or a JD might use.
_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "golang": "go",
    "nodejs": "node.js",
    "node js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "springboot": "spring boot",
    "spring-boot": "spring boot",
    "dotnet": ".net",
    "gcp": "google cloud",
}


def _canon(skill: str) -> str:
    s = re.sub(r"\s+", " ", skill.strip().lower())
    return _ALIASES.get(s, s)


@lru_cache(maxsize=2048)
def _skill_pattern(canon: str) -> re.Pattern[str] | None:
    # Split only on separators that sit *between* alphanumerics, so a leading
    # dot (".net") is preserved while an interior one ("node.js") is optional.
    parts = [p for p in re.split(r"(?<=[a-z0-9])[\s\-/.]+(?=[a-z0-9])", canon) if p]
    parts = [re.escape(p) for p in parts]
    if not parts:
        return None
    # Separators between words become optional, so "spring boot" also matches
    # "springboot"/"spring-boot" and "node.js" matches "nodejs".
    core = r"[\s\-/.]*".join(parts)
    return re.compile(rf"(?<![a-z0-9]){core}(?![a-z0-9])")


def _skill_in_text(skill: str, text_lower: str) -> bool:
    pattern = _skill_pattern(_canon(skill))
    return bool(pattern and pattern.search(text_lower))


_KNOWN_PATTERN = re.compile("|".join(
    pattern.pattern
    for skill in sorted(_KNOWN_SKILLS, key=lambda value: len(_canon(value)), reverse=True)
    if (pattern := _skill_pattern(_canon(skill))) is not None
))


@lru_cache(maxsize=1024)
def _expand_skill_match(text: str) -> frozenset[str]:
    return frozenset(skill for skill in _KNOWN_SKILLS if _skill_in_text(skill, text))


@lru_cache(maxsize=512)
def _known_skills_in_text(text: str) -> frozenset[str]:
    found: set[str] = set()
    for match in _KNOWN_PATTERN.finditer(text):
        found.update(_expand_skill_match(match.group()))
    return frozenset(found)


def title_matches(profile: CandidateProfile, job: Job) -> bool:
    return bool(_languages_in(", ".join(profile.primary_skills)) & _languages_in(job.title)) or any(
        _skill_in_text(skill, job.title.lower()) for skill in profile.primary_skills
        if _canon(skill) not in {"aws", "sql", "docker", "microservices", "databases"}
    )


_LANGUAGES = ("Java", "Python", "JavaScript", "TypeScript", "C#", "C++", "Go", "Ruby", "PHP", "Rust", "Kotlin", "Swift", "Scala")
_FRAMEWORK_LANGUAGES = {
    "Spring Boot": "Java", "Spring MVC": "Java", "Spring Cloud": "Java", "Spring AI": "Java",
    "Django": "Python", "Flask": "Python", "FastAPI": "Python",
    ".NET": "C#", "ASP.NET": "C#", "Node.js": "JavaScript", "React": "JavaScript",
    "Angular": "TypeScript", "Vue": "JavaScript",
}


def _languages_in(text: str) -> set[str]:
    languages = {language for language in _LANGUAGES if _skill_in_text(language, text.lower())}
    for framework, language in _FRAMEWORK_LANGUAGES.items():
        if _skill_in_text(framework, text.lower()):
            languages.add(language)
    for language in ("Java", "Python"):
        if re.search(rf"\b{language.lower()}\s*\d+(?:\.\d+)*\b", text.lower()):
            languages.add(language)
    if re.search(r"\b(?:dot\s*net|golang)\b", text.lower()):
        languages.add("C#" if re.search(r"\bdot\s*net\b", text.lower()) else "Go")
    return languages


def _jd_primary_matches(skills: list[str], job: Job) -> list[str]:
    requirements = _job_requirements(job.title, job.description)
    core_text = ", ".join(requirements.primary).lower()
    return [skill for skill in skills if _skill_in_text(skill, core_text)]


# Distinct disciplines whose titles shouldn't match each other even when a
# skill keyword (e.g. "Java") appears incidentally in both -- a QA/Testing
# opening that mentions Java as a tool is not a Java developer opening.
_ROLE_FAMILY_PATTERNS = {
    "qa": r"\b(?:qa|quality assurance|sdet|automation test(?:er|ing)?|manual test(?:er|ing)?|software tester|test engineer|testing)\b",
    "devops": r"\b(?:devops|site reliability|\bsre\b|platform engineer)\b",
    "data": r"\b(?:data scientist|data engineer|ml engineer|machine learning engineer|data analyst)\b",
    "support": r"\b(?:technical support|support engineer|customer support|helpdesk)\b",
    "development": r"\b(?:software engineer|software developer|backend|front[- ]?end|full[- ]?stack|application developer|programmer|developer)\b",
}


def _role_families(text: str) -> frozenset[str]:
    lowered = text.lower()
    return frozenset(family for family, pattern in _ROLE_FAMILY_PATTERNS.items() if re.search(pattern, lowered))


_SECTION = re.compile(
    r"\b(?P<optional>nice[ -]to[ -]have|good[ -]to[ -]have|preferred (?:skills|qualifications)|desired skills|desirable)\b"
    r"|\b(?P<required>mandatory(?: skills(?: description)?)?|skills required|required (?:skills|qualifications)|"
    r"essential skills|technical requirements|requirements|must[ -]have(?: skills)?|qualifications(?: (?:and|&) experience)?)\b"
    r"|\b(?P<neutral>(?:roles? (?:and|&) |key )?responsibilit(?:y|ies)|about (?:us|the role)|"
    r"what you(?:'ll| will) (?:do|work on)|summary)\b"
    r"|\b(?P<ignore>benefits|what we offer|about (?:the company|our company)|show more)\b",
    re.I,
)
_OPTIONAL_CLAUSE = re.compile(r"\b(?:optional|preferred|desirable|a plus|nice[ -]to[ -]have|good[ -]to[ -]have|not (?:a )?(?:mandatory|required))\b", re.I)
_ROLE_EVIDENCE = re.compile(r"\b(?:develop\w*|build\w*|design\w*|engineer\w*|experience|proficien\w*|expert\w*|strong|hands[ -]on|knowledge|required|looking for|seeking)\b", re.I)


def _requirement_clauses(description: str) -> tuple[list[str], list[str]]:
    markers = list(_SECTION.finditer(description))
    boundaries = [(0, 0, "neutral")] + [(match.start(), match.end(), match.lastgroup) for match in markers]
    required, preferred = [], []
    for index, (_start, end, mode) in enumerate(boundaries):
        stop = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(description)
        if mode == "ignore":
            continue
        for clause in re.split(r"\n+|(?<=[.!?;])\s+", description[end:stop]):
            clause = clause.strip(" :.-\t")
            if not clause:
                continue
            if mode == "optional" or _OPTIONAL_CLAUSE.search(clause):
                preferred.append(clause)
            elif mode == "required" or _ROLE_EVIDENCE.search(clause) or re.search(r"\b\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)\b", clause, re.I) or re.match(r"(?i)^(?:java|python|c#|c\+\+|spring|kubernetes)\b", clause):
                required.append(clause)
    return required, preferred


@dataclass(frozen=True)
class _Requirements:
    primary: tuple[str, ...]
    languages: frozenset[str]
    required_text: str
    preferred: tuple[str, ...]
    evidence: tuple[str, ...]
    language_groups: tuple[frozenset[str], ...]


@lru_cache(maxsize=512)
def _job_requirements(title: str, description: str) -> _Requirements:
    clauses, optional = _requirement_clauses(description)
    required_text = "\n".join(clauses)
    title_languages = _languages_in(title)
    languages = title_languages or _languages_in(required_text)
    known = _known_skills_in_text((title + "\n" + required_text).lower())
    primary = set(languages)
    primary.update(skill for skill, language in _FRAMEWORK_LANGUAGES.items() if skill in known and language in languages)
    if not primary:
        primary.update(known)
    evidence = tuple(clause for clause in clauses if _languages_in(clause).intersection(languages))[:3]
    groups = []
    for clause in clauses:
        explicit = {language for language in _LANGUAGES if _skill_in_text(language, clause.lower())}
        if not explicit or not re.search(r"\b(?:mandatory|required|must|proficient|strong|expertise|extensive|hands[ -]on)\b", clause, re.I):
            continue
        if re.search(r"\b(?:or|one of|any of)\b", clause, re.I):
            groups.append(frozenset(explicit))
        else:
            groups.extend(frozenset([language]) for language in sorted(explicit))
    return _Requirements(tuple(sorted(primary)), frozenset(languages), required_text,
                         tuple(sorted(_known_skills_in_text("\n".join(optional).lower()))), evidence, tuple(groups))


_MATCH_PRIORITY = {
    "Strong match": 3,
    "Good match": 2,
    "Worth a look": 1,
    "Experience unverified": 0,
}


def evaluate_jobs(
    profile: CandidateProfile,
    jobs: list[Job],
    include_remote: bool = True,
    diagnostics: dict[str, int] | None = None,
) -> list[ScoredJob]:
    """Return matches by tier, skill coverage, then newest posting date.

    Jobs without a description yet are skipped silently (not counted as
    rejections) -- they are pending analysis, not evaluated and failed.
    """
    # Candidate skills don't vary per job -- compute once instead of per job.
    candidate_skills = _known_skills_in_text(", ".join(profile.skills).lower())
    results: list[ScoredJob] = []
    for job in jobs:
        if not job.description.strip():
            continue
        scored = _evaluate_one(profile, job, include_remote, candidate_skills, diagnostics)
        if scored is not None:
            results.append(scored)

    results.sort(
        key=lambda result: (
            _MATCH_PRIORITY.get(result.label, -1),
            result.score,
            result.job.posted_at.timestamp() if result.job.posted_at else float("-inf"),
        ),
        reverse=True,
    )
    return results


def _evaluate_one(
    profile: CandidateProfile,
    job: Job,
    include_remote: bool,
    candidate_skills: frozenset[str],
    diagnostics: dict[str, int] | None = None,
) -> ScoredJob | None:
    def reject(reason: str) -> None:
        if diagnostics is not None:
            diagnostics[reason] = diagnostics.get(reason, 0) + 1

    candidate_family = _role_families(f"{profile.current_title} {' '.join(profile.target_titles)}")
    job_family = _role_families(job.title)
    if candidate_family and job_family and candidate_family.isdisjoint(job_family):
        return reject("Different role focus")

    requirements = _job_requirements(job.title, job.description)
    candidate_languages = _languages_in(", ".join(profile.primary_skills or profile.skills))
    if candidate_languages and requirements.languages and not candidate_languages.intersection(requirements.languages):
        return reject("Different core language")
    text = f"{job.title}\n{requirements.required_text}".lower()

    # --- gate 1: the JD must require one of the candidate's primary skills ---
    core_skills = profile.primary_skills or profile.skills
    primary_matches = _jd_primary_matches(core_skills, job)
    if not primary_matches:
        return reject("No primary requirement overlap")
    available_languages = _languages_in(", ".join(profile.skills))
    if any(not group.intersection(available_languages) for group in requirements.language_groups):
        return reject("Required language missing from resume")

    matched_set = {s for s in profile.skills if _skill_in_text(s, text)}
    matched = list(matched_set)

    # --- gate 2: experience ---------------------------------------------
    required = _required_years(job.description.lower())
    upper_limit = profile.total_years_experience
    experience_ok = required is None or required <= upper_limit
    if not experience_ok:
        return reject("Experience minimum not met")
    if required is None and re.search(r"\b(?:lead|principal|staff|architect|manager)\b", job.title, re.I) and profile.seniority != "lead":
        return reject("Leadership eligibility unverified")

    missing = [s for s in profile.skills if s not in matched_set]
    location_ok = _location_match(profile, job, include_remote)

    # Skills the posting asks for that the candidate does not list.
    gap = sorted(_known_skills_in_text(text) - candidate_skills, key=str.lower)

    acceptance = AcceptanceCriteria(
        matched_skills=sorted(matched, key=str.lower),
        missing_skills=sorted(missing, key=str.lower)[:15],
        gap_skills=gap[:12],
        experience_required=required,
        experience_upper_limit=float(upper_limit),
        experience_ok=experience_ok,
        location_match=location_ok,
        source_criteria=job.criteria,
        must_have_matched=primary_matches,
        must_have_missing=[skill for skill in requirements.primary if not _skill_in_text(skill, ", ".join(core_skills).lower())],
        primary_required_skills=list(requirements.primary),
        preferred_skills=list(requirements.preferred),
        requirement_evidence=list(requirements.evidence),
    )
    coverage = len(matched) / max(1, len(matched) + len(gap))
    label = "Experience unverified" if required is None else "Strong match" if coverage >= 0.7 and not acceptance.must_have_missing else "Good match" if coverage >= 0.4 else "Worth a look"
    return ScoredJob(
        job=job,
        acceptance=acceptance,
        label=label,
        score=coverage,
    )


def _required_years(text: str) -> float | None:
    clauses, _preferred = _requirement_clauses(text)
    numbers = []
    number_words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
    for clause in clauses:
        clause = re.sub(r"\b(?:" + "|".join(number_words) + r")\b", lambda match: number_words[match.group().lower()], clause, flags=re.I)
        for match in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+?\s*(?:(?:-|to|\u2013|\u2014)\s*\d+(?:\.\d+)?\s*)?(?:years?|yrs?)\b", clause, re.I):
            before = clause[max(0, match.start() - 65):match.start()]
            after = clause[match.end():match.end() + 65]
            if re.match(r"\s*(?:of\s+)?(?:full[ -]time\s+)?(?:education|degree|study|college|university|ago|old)\b", after, re.I):
                continue
            if re.search(r"\b(?:founded|established|history|company has|we have|we bring)\b", before, re.I):
                continue
            numbers.append(float(match.group(1)))
    return max(numbers) if numbers else None


def _location_match(profile: CandidateProfile, job: Job, include_remote: bool) -> bool:
    loc = job.location.lower()
    if "remote" in loc:
        return include_remote
    if not profile.locations:
        return True
    return any(_canon(p) in loc for p in profile.locations)
