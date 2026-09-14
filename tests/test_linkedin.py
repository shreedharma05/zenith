import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from zenith import config
from zenith.models import Job
from zenith.sources.linkedin import LinkedInSource, _DETAIL_URL, _SEARCH_URL, _RequestPacer


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.setting = patch.object(config, "CACHE_DIR", self.directory.name)
        self.setting.start()
        self.addCleanup(self.setting.stop)
        self.source = LinkedInSource()
        self.addCleanup(self.source.close)
        self.pacer = patch("zenith.sources.linkedin._PACER", _RequestPacer())
        self.pacer.start()
        self.addCleanup(self.pacer.stop)

    def test_detail_cache_outlives_search_cache(self):
        for url, expected in [(_DETAIL_URL.format(job_id="123"), "content"), (_SEARCH_URL, None)]:
            key = self.source._cache_key(url, None)
            self.source._write_cache(key, "content")
            old = time.time() - 3600
            os.utime(self.source._cache_path(key), (old, old))
            with patch.object(self.source.session, "get", side_effect=AssertionError("network")):
                if expected:
                    self.assertEqual(self.source._get(url, None), expected)
                else:
                    with self.assertRaises(AssertionError):
                        self.source._get(url, None)

    def test_force_refresh_bypasses_cache(self):
        self.source._write_cache("key", "content")
        self.source.use_cache = False
        self.assertIsNone(self.source._read_cache("key"))

    def test_write_is_complete_and_leaves_no_temporary_files(self):
        self.source._write_cache("key", "first")
        self.source._write_cache("key", "second")
        self.assertEqual(self.source._read_cache("key"), "second")
        self.assertEqual(os.listdir(self.directory.name), ["key.html"])

    def test_rate_limit_stops_network_but_allows_cached_responses(self):
        response = MagicMock(status_code=429, headers={"Retry-After": "120"})
        with patch.object(self.source.session, "get", return_value=response) as request:
            self.assertIsNone(self.source._get(_SEARCH_URL, {"start": 0}))
            self.assertIsNone(self.source._get(_SEARCH_URL, {"start": 10}))
            self.assertEqual(request.call_count, 1)
        self.assertEqual(len(self.source.warnings), 1)
        url = _DETAIL_URL.format(job_id="cached")
        self.source._write_cache(self.source._cache_key(url, None), "cached content")
        self.assertEqual(self.source._get(url, None), "cached content")

    def test_short_pages_continue_and_duplicates_terminate(self):
        def job(identifier):
            return Job(str(identifier), "Java Engineer", "Example", "Chennai", "https://example.com", "LinkedIn")
        with patch.object(self.source, "_get", return_value="html") as request, patch.object(self.source, "_parse_cards", side_effect=[
            [job(1), job(2)], [job(2), job(3)], [job(2), job(3)],
        ]):
            jobs = self.source._search_cards("Java", "Chennai", "r86400", 100)
        self.assertEqual([value.id for value in jobs], ["1", "2", "3"])
        self.assertEqual([call.args[1]["start"] for call in request.call_args_list], [0, 2, 4])

    def test_default_search_fetches_more_than_one_thousand_and_enriches_all(self):
        jobs = [Job(str(number), "Java Engineer", "Example", "Chennai", "url", "test") for number in range(1235)]
        pages = [jobs[start:start + 10] for start in range(0, len(jobs), 10)] + [[]]
        with patch.object(self.source, "_get", return_value="html") as request, patch.object(self.source, "_parse_cards", side_effect=pages), patch.object(self.source, "_enrich_many") as enrich:
            results = self.source.search("Java", "Chennai")
        self.assertEqual(len(results), 1235)
        self.assertEqual(enrich.call_args.args[0], results)
        self.assertEqual([call.args[1]["start"] for call in request.call_args_list], list(range(0, 1235, 10)) + [1235])

    def test_multi_location_search_has_no_default_detail_budget(self):
        jobs = [Job(str(number), "Java Engineer", "Example", "Chennai", "url", "test") for number in range(1200)]
        with patch.object(self.source, "_search_cards", return_value=jobs) as search, patch.object(self.source, "_enrich_many") as enrich:
            results = self.source.search_many("Java", ["Chennai", "Bengaluru"])
            self.assertTrue(all(call.args[3] is None for call in search.call_args_list))
            self.assertEqual(len(results), 1200)
            self.assertEqual(len(enrich.call_args.args[0]), 1200)
            self.source.search_many("Java", ["Chennai"], detail_limit=3)
            self.assertEqual(len(enrich.call_args.args[0]), 3)

    def test_uncapped_pagination_stops_on_failure_and_preserves_results(self):
        job = Job("1", "Java Engineer", "Example", "Chennai", "url", "test")
        with patch.object(self.source, "_get", side_effect=["html", None]), patch.object(self.source, "_parse_cards", return_value=[job]):
            self.assertEqual(self.source._search_cards("Java", "Chennai", "r86400"), [job])

    def test_empty_search_response_is_cached_completion_not_failure(self):
        response = MagicMock(status_code=200, text="", headers={})
        with patch.object(self.source.session, "get", return_value=response) as request:
            self.assertEqual(self.source.search("Java", "Chennai"), [])
            self.assertEqual(self.source.search("Java", "Chennai"), [])
            self.assertEqual(request.call_count, 1)
        self.assertEqual(self.source.warnings, [])

    def test_empty_detail_response_is_still_a_failure(self):
        response = MagicMock(status_code=200, text="", headers={})
        with patch.object(self.source.session, "get", return_value=response):
            self.assertIsNone(self.source._get(_DETAIL_URL.format(job_id="missing"), None))
        self.assertTrue(self.source.warnings)

    def test_explicit_limit_is_still_supported_for_bounded_checks(self):
        jobs = [Job(str(number), "Java Engineer", "Example", "Chennai", "url", "test") for number in range(10)]
        with patch.object(self.source, "_get", return_value="html") as request, patch.object(self.source, "_parse_cards", return_value=jobs):
            self.assertEqual(len(self.source._search_cards("Java", "Chennai", "r86400", 3)), 3)
            self.assertEqual(request.call_count, 1)

    def test_native_parser_and_cached_objects_are_isolated(self):
        html = '<li><div class="base-card" data-entity-urn="urn:li:job:123"><h3 class="base-search-card__title">Java Engineer</h3><a class="base-card__full-link" href="https://example.com/job?tracking=1"></a><time datetime="2026-09-11"></time></div></li>'
        first = self.source._parse_cards(html)
        first[0].description = "Changed by a different request"
        second = self.source._parse_cards(html)
        self.assertEqual(second[0].title, "Java Engineer")
        self.assertEqual(second[0].description, "")
        self.assertEqual(second[0].url, "https://example.com/job")

    def test_details_are_concurrent_and_progress_stays_on_caller(self):
        barrier = threading.Barrier(config.FETCH_WORKERS)
        main_thread = threading.get_ident()
        jobs = [Job(str(number), "Java", "Example", "Chennai", "url", "test") for number in range(6)]
        def enrich(job):
            barrier.wait(timeout=2)
            job.description = "Java SQL"
        updates = []
        def progress(message):
            self.assertEqual(threading.get_ident(), main_thread)
            updates.append(message)
        with patch.object(self.source, "_enrich", side_effect=enrich):
            self.source._enrich_many(jobs, progress)
        self.assertEqual(len(updates), len(jobs))
        self.assertTrue(all(job.description for job in jobs))

    def test_worker_sessions_are_separate(self):
        barrier = threading.Barrier(3)
        def session_id(_number):
            session = self.source.session
            barrier.wait(timeout=2)
            return id(session)
        with ThreadPoolExecutor(max_workers=3) as pool:
            identities = list(pool.map(session_id, range(3)))
        self.assertEqual(len(set(identities)), 3)

    def test_pacer_spaces_request_starts(self):
        pacer = _RequestPacer()
        with patch("zenith.sources.linkedin.time.monotonic", side_effect=[10, 10.5, 11]), patch("zenith.sources.linkedin.threading.Event") as event:
            self.assertTrue(pacer.wait((1, 1)))
            self.assertTrue(pacer.wait((1, 1)))
            event.return_value.wait.assert_called_once()
        self.assertEqual(pacer.next_start, 12)

    def test_pacing_is_shared_across_worker_threads(self):
        pacer = _RequestPacer()
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertTrue(all(pool.map(lambda _number: pacer.wait((0.01, 0.01)), range(3))))
        self.assertGreaterEqual(time.monotonic() - started, 0.02)

    def test_pacer_cooldown_blocks_requests(self):
        pacer = _RequestPacer()
        pacer.cooldown(100)
        with patch("zenith.sources.linkedin.time.monotonic", return_value=0):
            self.assertFalse(pacer.wait((1, 1)))

    def test_new_search_and_force_refresh_cannot_bypass_cooldown(self):
        response = MagicMock(status_code=429, headers={"Retry-After": "900"})
        with patch("zenith.sources.linkedin.time.monotonic", return_value=100), patch("requests.Session.get", return_value=response) as request:
            self.assertIsNone(self.source._get(_SEARCH_URL, {"start": 0}))
            for use_cache in (True, False):
                with LinkedInSource(use_cache=use_cache) as another:
                    self.assertIsNone(another._get(_SEARCH_URL, {"start": 10}))
            self.assertEqual(request.call_count, 1)
            from zenith.sources.linkedin import _PACER
            self.assertEqual(_PACER.blocked_until, 1000)

    def test_cooldown_expires_without_releasing_a_burst(self):
        pacer = _RequestPacer()
        with patch("zenith.sources.linkedin.time.monotonic", return_value=100):
            pacer.cooldown(300)
        with patch("zenith.sources.linkedin.time.monotonic", return_value=399):
            self.assertFalse(pacer.wait((2, 2)))
        with patch("zenith.sources.linkedin.time.monotonic", side_effect=[400, 400, 402]), patch("zenith.sources.linkedin.threading.Event") as event:
            self.assertTrue(pacer.wait((2, 2)))
            self.assertTrue(pacer.wait((2, 2)))
        event.return_value.wait.assert_called_once()
        self.assertEqual(pacer.next_start, 404)


if __name__ == "__main__":
    unittest.main()