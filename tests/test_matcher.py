import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from zenith.matcher import _KNOWN_SKILLS, _jd_primary_matches, _known_skills_in_text, _required_years, _skill_in_text, evaluate_jobs, title_matches
from zenith.models import AcceptanceCriteria, CandidateProfile, Job, ScoredJob


class MatcherTests(unittest.TestCase):
    def test_sort_prioritizes_tier_then_coverage_then_recency(self):
        cases = [
            ("unverified", "Experience unverified", 1.0, 11),
            ("good", "Good match", 0.9, 11),
            ("worth", "Worth a look", 0.3, 11),
            ("strong_lower_coverage", "Strong match", 0.75, 11),
            ("strong_old", "Strong match", 1.0, 9),
            ("strong_unknown_date", "Strong match", 1.0, None),
            ("strong_new", "Strong match", 1.0, 10),
        ]
        scored = [
            ScoredJob(
                Job(identifier, "Java Developer", "Example", "Chennai", "url", "test",
                    posted_at=datetime(2026, 9, day, tzinfo=timezone.utc) if day else None,
                    description="Java, 3 years"),
                AcceptanceCriteria(), label=label, score=score,
            )
            for identifier, label, score, day in cases
        ]
        with patch("zenith.matcher._evaluate_one", side_effect=scored):
            results = evaluate_jobs(CandidateProfile(), [result.job for result in scored])
        self.assertEqual([result.job.id for result in results], [
            "strong_new", "strong_old", "strong_unknown_date", "strong_lower_coverage",
            "good", "worth", "unverified",
        ])

    def test_required_language_not_rescued_by_other_core_overlap(self):
        profile = CandidateProfile(skills=["Java", "Spring Boot"], primary_skills=["Java"], total_years_experience=3)
        job = Job("both", "Backend Engineer", "Example", "Chennai", "url", "test",
                  description="Requirements: Strong Java experience. Proficient Python skills for integrations. 3 years.")
        self.assertEqual(evaluate_jobs(profile, [job]), [])
        job.description = "Requirements: Strong experience in Java or Python. 3 years."
        self.assertEqual(len(evaluate_jobs(profile, [job])), 1)

    def test_ethernet_java_is_optional_not_primary(self):
        job = Job("ethernet", "Ethernet Development Lead", "Example", "Chennai", "url", "test",
                  description="Skills Required: Experience with Ethernet, Linux/Android, C/C++, OS concepts. Nice to have: QNX, FreeRTOS, JAVA, Apps. Roles & Responsibilities: Develop Ethernet system software.")
        self.assertEqual(_jd_primary_matches(["Java", "AWS"], job), [])
        self.assertIn("C++", _jd_primary_matches(["C++"], job))

    def test_qa_title_rejected_for_java_backend_developer(self):
        profile = CandidateProfile(
            skills=["Java", "Spring Boot", "SQL"], primary_skills=["Java", "Spring Boot"],
            current_title="Java Backend Developer", target_titles=["Java Backend Developer"],
            total_years_experience=3,
        )
        job = Job("qa", "QA Engineer", "Example", "Chennai", "url", "test",
                  description="Requirements: Java, SQL, distributed systems knowledge. 3 years of QA/testing experience.")
        self.assertEqual(evaluate_jobs(profile, [job]), [])

    def test_role_family_gate_does_not_fire_without_a_clear_candidate_title(self):
        profile = CandidateProfile(skills=["Java", "SQL"], primary_skills=["Java"], total_years_experience=3)
        job = Job("qa2", "QA Engineer", "Example", "Chennai", "url", "test",
                  description="Requirements: Java, SQL. 3 years of experience.")
        self.assertEqual(len(evaluate_jobs(profile, [job])), 1)

    def test_explicit_minimum_has_no_invented_year_allowance(self):
        profile = CandidateProfile(skills=["Java", "Spring Boot"], primary_skills=["Java"], total_years_experience=3)
        job = Job("senior", "Senior Java Developer", "Example", "Chennai", "url", "test",
                  description="Requirements: 4+ years of hands-on Java development, including at least 2 years owning a service.")
        self.assertEqual(_required_years(job.description), 4)
        self.assertEqual(evaluate_jobs(profile, [job]), [])

    def test_experience_numbers_ignore_education_optional_and_company_age(self):
        self.assertEqual(_required_years("Our company has 50 years of experience. Requirements: 15 years full time education. 3-5 years of Java development. Nice to have: 8 years of Python."), 3)
        self.assertEqual(_required_years("Requirements: 8+ years overall experience. Minimum 2-3 years Java."), 8)
        self.assertEqual(_required_years("Requirements: three years of development experience."), 3)

    def test_unknown_experience_is_not_labelled_strong(self):
        profile = CandidateProfile(skills=["Java", "Spring Boot"], primary_skills=["Java", "Spring Boot"], total_years_experience=3)
        job = Job("unknown", "Java Developer", "Example", "Chennai", "url", "test", description="Required Qualifications: Java and Spring Boot.")
        result = evaluate_jobs(profile, [job])[0]
        self.assertEqual(result.label, "Experience unverified")
        self.assertEqual(result.acceptance.must_have_matched, ["Java", "Spring Boot"])

    def test_generic_title_finds_requirements_after_long_blurb(self):
        job = Job("generic", "Software Engineer", "Example", "Chennai", "url", "test",
                  description="Our company serves its clients. " * 160 + "Required Skills: Java Spring Boot. 3 years experience. Preferred skills: Python.")
        self.assertEqual(_jd_primary_matches(["Java"], job), ["Java"])
        self.assertEqual(_jd_primary_matches(["Python"], job), [])

    def test_supporting_cloud_skill_does_not_qualify_other_language_role(self):
        profile = CandidateProfile(
            skills=["Java", "Spring Boot", "AWS", "Microservices", "PostgreSQL"],
            primary_skills=["Java", "Spring Boot", "AWS", "Microservices"],
            total_years_experience=3,
        )
        job = Job("python", "Software Engineer - Python/AWS", "Example", "Chennai", "url", "test",
                  description="Requirements: Python, AWS, PostgreSQL, microservices; 3 years experience. Java is optional.")
        self.assertEqual(evaluate_jobs(profile, [job]), [])

    def test_missing_description_is_not_a_verified_match(self):
        profile = CandidateProfile(skills=["Java"], primary_skills=["Java"], total_years_experience=3)
        job = Job("unknown", "Java Developer", "Example", "Chennai", "url", "test")
        self.assertEqual(evaluate_jobs(profile, [job]), [])

    def test_combined_detector_preserves_baseline(self):
        samples = [
            ", ".join(_KNOWN_SKILLS),
            "JavaScript is not Java; .NET, ASP.NET, C#, C++, SQL and NoSQL",
            "REST API; REST APIs; RESTAPI; Springboot; Spring-Boot; Nodejs; node.js",
            "Apache Kafka, OpenFeign, Google Cloud and distributed systems",
            "ordinary text without any technology names",
        ] + _KNOWN_SKILLS
        for sample in samples:
            text = sample.lower()
            expected = frozenset(skill for skill in _KNOWN_SKILLS if _skill_in_text(skill, text))
            with self.subTest(sample=sample):
                self.assertEqual(_known_skills_in_text(text), expected)

    def test_primary_gate_preserved(self):
        profile = CandidateProfile(skills=["Java", "Spring Boot", "SQL"], primary_skills=["Java"], total_years_experience=3)
        java = Job("1", "Java Developer", "Example", "Chennai", "https://example.com/1", "test", description="Java Spring Boot SQL, 3 years")
        python = Job("2", "Python Developer", "Example", "Chennai", "https://example.com/2", "test", description="Python and React. " * 45 + "Java optional")
        self.assertEqual([match.job.id for match in evaluate_jobs(profile, [java, python])], ["1"])
        generic = Job("3", "Software Engineer", "Example", "Chennai", "https://example.com/3", "test", description="Java Spring Boot, 3 years")
        self.assertFalse(title_matches(profile, generic))
        self.assertEqual(len(evaluate_jobs(profile, [generic])), 1)

    def test_gap_skills_correct_across_multiple_jobs(self):
        # candidate_skills is computed once in evaluate_jobs and reused per job;
        # verify each job still gets its own correct, independent gap set.
        profile = CandidateProfile(skills=["Java", "Spring Boot"], primary_skills=["Java"], total_years_experience=3)
        kafka_job = Job("1", "Java Developer", "Example", "Chennai", "url1", "test", description="Java Spring Boot Kafka required")
        docker_job = Job("2", "Java Developer", "Example", "Chennai", "url2", "test", description="Java Spring Boot Docker required")
        results = {match.job.id: match for match in evaluate_jobs(profile, [kafka_job, docker_job])}
        self.assertIn("Kafka", results["1"].acceptance.gap_skills)
        self.assertNotIn("Docker", results["1"].acceptance.gap_skills)
        self.assertIn("Docker", results["2"].acceptance.gap_skills)
        self.assertNotIn("Kafka", results["2"].acceptance.gap_skills)

    def test_opening_summary_adapts_to_where_requirement_text_starts(self):
        # Measured against 100 real postings, the actual requirement text
        # starts past a fixed 600-char cutoff in over a third of cases. A
        # long company blurb before "Requirements: ..." must not hide it.
        blurb = "We are a great company. " * 40
        description = blurb + "Requirements: Kubernetes, Terraform, 3 years experience."
        job = Job("1", "Platform Engineer", "Example", "Chennai", "url", "test", description=description)
        self.assertIn("Kubernetes", _jd_primary_matches(["Kubernetes"], job))

    def test_opening_summary_still_excludes_deep_incidental_mentions(self):
        # A skill mentioned only once, far past the requirement-signal
        # sentence, in what reads like a trailing alternatives list, must
        # still be excluded -- this is the real UST JD false-positive case.
        description = (
            "Summary: looking for a Python engineer with React. " + ("filler " * 300)
            + "Nice to have: Java, Go, Rust as alternatives."
        )
        job = Job("1", "Python Engineer", "Example", "Chennai", "url", "test", description=description)
        self.assertEqual(_jd_primary_matches(["Java"], job), [])


if __name__ == "__main__":
    unittest.main()