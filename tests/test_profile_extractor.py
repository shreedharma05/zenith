import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zenith import config
from zenith.profile_extractor import (
    ProfileExtractionError, _messages, _loads_lenient, _profile_from_dict, extract_profile,
)


PROFILE = dict(name="Example", current_title="Java Developer", target_titles=["Java Developer"],
               total_years_experience=3, seniority="mid", skills=["Java", "Spring Boot"],
               primary_skills=["Java"], locations=[], summary="Backend engineer")


class ProviderTests(unittest.TestCase):
    def test_primary_stack_comes_from_work_not_incidental_skill_list(self):
        text = (
            "Consultant with 3 years of software engineering experience, specializing in Java, Spring Boot.\n"
            "Developed Java backend services using Spring Boot, Kafka, AWS and databases.\n"
            "Recent Experience\nDeveloped and maintained enterprise Java microservices using Spring Boot.\n"
            "Professional Skills\nJava\nSpring Boot\nJavaScript\nAWS\nSQL\nDocker\n"
        )
        raw = {**PROFILE, "primary_skills": ["AWS", "JavaScript", "Java"], "skills": ["Java", "JavaScript", "AWS", "Spring Boot"]}
        with patch("zenith.profile_extractor._try_ollama", return_value=raw):
            profile = extract_profile(text, "ollama")
        self.assertEqual(profile.primary_skills, ["Java", "Spring Boot"])
        self.assertIn("AWS", profile.skills)
        self.assertEqual(profile.total_years_experience, 3)

    def test_local_never_calls_openai(self):
        with patch("zenith.profile_extractor._try_ollama", return_value=PROFILE), patch("zenith.profile_extractor._try_openai") as cloud:
            profile = extract_profile("3 years Java and Spring Boot", "ollama")
        cloud.assert_not_called()
        self.assertEqual(profile.extraction_method, "ollama")

    def test_local_failure_is_explicit(self):
        with patch("zenith.profile_extractor._try_ollama", return_value=None):
            profile = extract_profile("Java Spring Boot", "ollama")
        self.assertEqual(profile.extraction_method, "offline")
        self.assertTrue(profile.extraction_warning)

    def test_openai_missing_key_fails_without_local_fallback(self):
        with patch.object(config, "OPENAI_API_KEY", ""), patch("zenith.profile_extractor._try_ollama") as local:
            with self.assertRaisesRegex(ProfileExtractionError, "OPENAI_API_KEY"):
                extract_profile("Java", "openai")
        local.assert_not_called()

    def test_openai_uses_schema_and_disables_storage(self):
        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(refusal=None, content=json.dumps(PROFILE)))])
        with patch.object(config, "OPENAI_API_KEY", "test-not-a-real-key"), patch("openai.OpenAI") as constructor:
            constructor.return_value.__enter__.return_value = client
            profile = extract_profile("Java Spring Boot", "openai")
        sent = client.chat.completions.create.call_args.kwargs
        self.assertFalse(sent["store"])
        self.assertTrue(sent["response_format"]["json_schema"]["strict"])
        self.assertEqual(sent["messages"][0]["role"], "system")
        self.assertEqual(profile.extraction_method, "openai")

    def test_invalid_output_and_nonfinite_years(self):
        self.assertIsNone(_loads_lenient("[]"))
        self.assertEqual(_profile_from_dict({"total_years_experience": "NaN"}).total_years_experience, 0)

    def test_long_resume_is_not_silently_truncated(self):
        with self.assertRaises(ProfileExtractionError):
            _messages("a" * (config.RESUME_MAX_CHARS + 1))

    def test_long_resume_error_not_swallowed_by_ollama_fallback(self):
        # _try_ollama wraps everything in a broad except; the length check must
        # happen before that, or this error would be silently swallowed and
        # mistaken for a normal offline fallback.
        with patch("zenith.profile_extractor._try_ollama") as local:
            with self.assertRaisesRegex(ProfileExtractionError, "too long"):
                extract_profile("a" * (config.RESUME_MAX_CHARS + 1), "ollama")
        local.assert_not_called()


if __name__ == "__main__":
    unittest.main()