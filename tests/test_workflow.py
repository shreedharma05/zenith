import unittest
from unittest.mock import MagicMock, patch

from zenith.models import CandidateProfile, Job
from zenith.workflow import SearchSession


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.profile = CandidateProfile(skills=["Java", "SQL"], primary_skills=["Java"],
            total_years_experience=3, locations=["Chennai"], extraction_method="ollama")
        self.job = Job("1", "Java Developer", "Example", "Chennai", "https://example.com/1", "test", description="Java SQL, 3 years")
        self.source = MagicMock()
        self.source.search_many.return_value = [self.job]
        self.source.warnings = []
        self.source.cache_hits = 0
        self.source.network_requests = 2

    def test_repeat_filters_force_refresh_and_session_isolation(self):
        with patch("zenith.workflow.extract_profile", return_value=self.profile) as extract, patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            first = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            second = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertFalse(first.profile_reused)
            self.assertTrue(first.discovery_complete)
            self.assertTrue(second.profile_reused)
            self.assertTrue(second.jobs_reused)
            self.assertEqual(extract.call_count, 1)
            self.assertEqual(self.source.search_many.call_count, 1)
            self.assertEqual(self.source.search_many.call_args.args[1], ["Chennai"])
            self.assertIsNone(self.source.search_many.call_args.args[3])
            self.assertFalse(self.source.search_many.call_args.kwargs["fetch_details"])
            session.run(b"Java", "cv.txt", "ollama", [], "r86400", force_refresh=True)
            self.assertEqual(extract.call_count, 1)
            self.assertEqual(self.source.search_many.call_count, 2)
            session.run(b"Java", "cv.txt", "openai", [], "r86400")
            self.assertEqual(extract.call_count, 2)
            SearchSession().run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertEqual(extract.call_count, 3)

    def test_profile_reuse_does_not_mutate_original_locations(self):
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            session.run(b"Java", "cv.txt", "ollama", ["Bengaluru"], "r86400")
            outcome = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertEqual(outcome.profile.locations, ["Chennai"])

    def test_enrich_limit_caps_batch_and_leaves_rest_pending_for_continue(self):
        jobs = [Job(str(n), "Java Developer", "Example", "Chennai", "url", "test") for n in range(5)]
        self.source.search_many.return_value = jobs

        def fake_enrich(batch, progress=None):
            for job in batch:
                job.description = "Java, 3 years"

        self.source.enrich_pending.side_effect = fake_enrich
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            first = session.run(b"Java", "cv.txt", "ollama", [], "r86400", enrich_limit=2)
        self.assertEqual(len(self.source.enrich_pending.call_args.args[0]), 2)
        self.assertEqual(first.pending, 3)
        self.assertTrue(first.pending > 0)

    def test_search_uses_primary_skill_and_reports_rejection_reasons(self):
        self.profile.target_titles = ["Consultant"]
        self.source.search_many.return_value = [self.job,
            Job("python", "Python Developer", "Example", "Chennai", "url", "test", description="Requirements: Python AWS, 3 years experience."),
            Job("pending", "Java Developer", "Example", "Chennai", "url", "test"),
            Job("senior", "Java Developer", "Example", "Chennai", "url", "test", description="Requirements: 5 years Java development."),
        ]
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            outcome = SearchSession().run(b"Java", "cv.txt", "ollama", [], "r86400")
        self.assertEqual(self.source.search_many.call_args.args[0], "Java")
        self.assertEqual(outcome.keywords, "Java")
        # A job without a description yet is "pending", not a rejection reason.
        self.assertEqual(outcome.rejected, {"Different core language": 1, "Experience minimum not met": 1})
        self.assertEqual(outcome.pending, 1)
        self.assertEqual(self.source.enrich_pending.call_count, 1)
        enriched_ids = {job.id for job in self.source.enrich_pending.call_args.args[0]}
        self.assertEqual(enriched_ids, {"pending"})
        self.assertEqual(len(outcome.matches) + sum(outcome.rejected.values()) + outcome.pending, outcome.fetched)

    def test_fallback_is_not_cached(self):
        self.profile.extraction_method = "offline"
        with patch("zenith.workflow.extract_profile", return_value=self.profile) as extract:
            session = SearchSession()
            session.get_profile(b"Java", "cv.txt", "ollama")
            session.get_profile(b"Java", "cv.txt", "ollama")
            self.assertEqual(extract.call_count, 2)

    def test_resumes_pending_enrichment_without_repeating_completed_discovery(self):
        pending_job = Job("pending", "Java Developer", "Example", "Chennai", "url", "test")
        self.source.search_many.return_value = [self.job, pending_job]
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            first = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertEqual(first.pending, 1)
            self.assertTrue(first.discovery_complete)
            self.assertFalse(first.jobs_reused)
            self.assertEqual(self.source.enrich_pending.call_count, 1)

            second = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            # Discovery already finished -- a resumed run must not repeat it,
            # but must keep trying to fetch the still-missing description.
            self.assertEqual(self.source.search_many.call_count, 1)
            self.assertEqual(self.source.enrich_pending.call_count, 2)
            self.assertEqual(second.pending, 1)
            self.assertFalse(second.jobs_reused)

    def test_warning_does_not_discard_already_discovered_jobs(self):
        self.source.warnings = ["LinkedIn rate-limited or blocked requests."]
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            first = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertEqual(first.fetched, 1)
            self.assertFalse(first.discovery_complete)
            self.assertIn("LinkedIn rate-limited or blocked requests.", first.warnings)

            # A later call for the same search must resume discovery (since
            # it never completed) instead of restarting from an empty list.
            second = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
            self.assertEqual(second.fetched, 1)
            self.assertEqual(self.source.search_many.call_count, 2)

    def test_changing_per_location_starts_a_fresh_discovery(self):
        with patch("zenith.workflow.extract_profile", return_value=self.profile), patch("zenith.workflow.LinkedInSource") as factory:
            factory.return_value.__enter__.return_value = self.source
            session = SearchSession()
            session.run(b"Java", "cv.txt", "ollama", [], "r86400", per_location=100)
            outcome = session.run(b"Java", "cv.txt", "ollama", [], "r86400")
        self.assertEqual(self.source.search_many.call_count, 2)
        self.assertIsNone(self.source.search_many.call_args.args[3])
        self.assertTrue(outcome.profile_reused)
        self.assertFalse(outcome.jobs_reused)


if __name__ == "__main__":
    unittest.main()