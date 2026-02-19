"""Tests for ADK memory service factory."""

from __future__ import annotations

import os
import unittest

from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService

from sentientagent_v2.runtime.markdown_memory_service import MarkdownMemoryService
from sentientagent_v2.runtime.memory_service import (
    MemoryConfig,
    create_memory_service,
    load_memory_config,
)


class MemoryServiceFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_load_memory_config_defaults_to_enabled_in_memory(self) -> None:
        os.environ.pop("SENTIENTAGENT_V2_MEMORY_ENABLED", None)
        os.environ.pop("SENTIENTAGENT_V2_MEMORY_BACKEND", None)

        cfg = load_memory_config()

        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.backend, "in_memory")
        self.assertEqual(cfg.agent_engine_id, "")
        self.assertIn(".sentientagent_v2/memory", cfg.markdown_dir)

    def test_create_memory_service_can_be_disabled(self) -> None:
        service = create_memory_service(MemoryConfig(False, "in_memory", "", "", "", ""))
        self.assertIsNone(service)

    def test_create_memory_service_uses_in_memory_by_default(self) -> None:
        service = create_memory_service(MemoryConfig(True, "in_memory", "", "", "", "/tmp/memory"))
        self.assertIsInstance(service, InMemoryMemoryService)

    def test_create_memory_service_uses_vertex_when_fully_configured(self) -> None:
        service = create_memory_service(
            MemoryConfig(
                enabled=True,
                backend="vertex_memory_bank",
                project="p1",
                location="us-central1",
                agent_engine_id="123456",
                markdown_dir="/tmp/memory",
            )
        )
        self.assertIsInstance(service, VertexAiMemoryBankService)

    def test_create_memory_service_uses_markdown_backend(self) -> None:
        service = create_memory_service(
            MemoryConfig(
                enabled=True,
                backend="markdown",
                project="",
                location="",
                agent_engine_id="",
                markdown_dir="/tmp/sentientagent_v2_md_memory",
            )
        )
        self.assertIsInstance(service, MarkdownMemoryService)


if __name__ == "__main__":
    unittest.main()
