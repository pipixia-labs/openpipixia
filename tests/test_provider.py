"""Tests for provider helpers."""

from __future__ import annotations

import unittest
import os
from unittest.mock import patch

from sentientagent_v2.provider import build_adk_model_from_env, normalize_model_name, validate_provider_runtime
from sentientagent_v2.openai_codex_llm import OpenAICodexLlm


class ProviderTests(unittest.TestCase):
    def test_openai_model_is_prefixed_when_missing_provider(self) -> None:
        self.assertEqual(normalize_model_name("openai", "gpt-4.1-mini"), "openai/gpt-4.1-mini")

    def test_openai_model_keeps_existing_provider_prefix(self) -> None:
        self.assertEqual(normalize_model_name("openai", "openai/gpt-4.1"), "openai/gpt-4.1")

    def test_openrouter_is_supported_by_runtime(self) -> None:
        issue = validate_provider_runtime("openrouter")
        self.assertIsNone(issue)

    def test_deepseek_model_is_prefixed_when_missing_provider(self) -> None:
        self.assertEqual(normalize_model_name("deepseek", "deepseek-chat"), "deepseek/deepseek-chat")

    def test_openai_codex_runtime_is_supported(self) -> None:
        issue = validate_provider_runtime("openai_codex")
        self.assertIsNone(issue)

    def test_build_openai_codex_model_from_env(self) -> None:
        env = {
            "SENTIENTAGENT_V2_PROVIDER": "openai_codex",
            "SENTIENTAGENT_V2_MODEL": "openai-codex/gpt-5.1-codex",
            "SENTIENTAGENT_V2_PROVIDER_API_BASE": "https://chatgpt.com/backend-api/codex/responses",
        }
        with patch.dict(os.environ, env, clear=False):
            model = build_adk_model_from_env()
        self.assertIsInstance(model, OpenAICodexLlm)


if __name__ == "__main__":
    unittest.main()
