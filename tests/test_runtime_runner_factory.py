"""Tests for runner factory compaction and memory wiring."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from sentientagent_v2.runtime.runner_factory import (
    _build_events_compaction_config,
    create_runner,
)


class RunnerFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_build_events_compaction_config_defaults(self) -> None:
        os.environ.pop("SENTIENTAGENT_V2_COMPACTION_ENABLED", None)
        os.environ.pop("SENTIENTAGENT_V2_COMPACTION_INTERVAL", None)
        os.environ.pop("SENTIENTAGENT_V2_COMPACTION_OVERLAP", None)

        cfg = _build_events_compaction_config()

        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.compaction_interval, 8)
        self.assertEqual(cfg.overlap_size, 1)
        self.assertIsNone(cfg.token_threshold)
        self.assertIsNone(cfg.event_retention_size)

    def test_build_events_compaction_config_allows_token_threshold_pair(self) -> None:
        os.environ["SENTIENTAGENT_V2_COMPACTION_TOKEN_THRESHOLD"] = "12000"
        os.environ["SENTIENTAGENT_V2_COMPACTION_EVENT_RETENTION"] = "6"

        cfg = _build_events_compaction_config()

        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.token_threshold, 12000)
        self.assertEqual(cfg.event_retention_size, 6)

    def test_build_events_compaction_config_ignores_partial_token_input(self) -> None:
        os.environ["SENTIENTAGENT_V2_COMPACTION_TOKEN_THRESHOLD"] = "12000"
        os.environ.pop("SENTIENTAGENT_V2_COMPACTION_EVENT_RETENTION", None)

        cfg = _build_events_compaction_config()

        self.assertIsNotNone(cfg)
        self.assertIsNone(cfg.token_threshold)
        self.assertIsNone(cfg.event_retention_size)

    def test_create_runner_wires_memory_service_and_compaction(self) -> None:
        sentinel_memory = object()
        sentinel_session_service = object()
        sentinel_runner = object()
        fake_agent = object()
        sentinel_app = object()

        with patch("sentientagent_v2.runtime.runner_factory.create_memory_service", return_value=sentinel_memory):
            with patch("sentientagent_v2.runtime.runner_factory.App", return_value=sentinel_app) as mocked_app:
                with patch("sentientagent_v2.runtime.runner_factory.Runner", return_value=sentinel_runner) as mocked:
                    runner, session_service = create_runner(
                        agent=fake_agent,
                        app_name="sentientagent_v2_test",
                        session_service=sentinel_session_service,
                    )

        self.assertIs(runner, sentinel_runner)
        self.assertIs(session_service, sentinel_session_service)
        mocked_app.assert_called_once()
        self.assertEqual(mocked.call_count, 1)
        kwargs = mocked.call_args.kwargs
        self.assertIs(kwargs["memory_service"], sentinel_memory)
        self.assertIs(kwargs["session_service"], sentinel_session_service)
        self.assertIs(kwargs["app"], sentinel_app)


if __name__ == "__main__":
    unittest.main()
