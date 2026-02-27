"""Tests for SQLite-backed token usage storage and parsing."""

from __future__ import annotations

import tempfile
import types as pytypes
import unittest
from pathlib import Path
import sqlite3

from openheron.runtime.token_usage_store import (
    ensure_token_usage_schema,
    extract_usage_tokens,
    parse_time_filter_to_epoch_ms,
    read_token_usage_stats,
    write_token_usage_event,
)


class TokenUsageStoreTests(unittest.TestCase):
    def test_schema_migration_adds_agent_id_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "token_usage.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE llm_token_usage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_at TEXT NOT NULL,
                        request_at_ms INTEGER NOT NULL,
                        response_at TEXT NOT NULL,
                        response_at_ms INTEGER NOT NULL,
                        provider TEXT,
                        model TEXT,
                        session_id TEXT,
                        invocation_id TEXT,
                        request_tokens INTEGER NOT NULL,
                        response_tokens INTEGER NOT NULL,
                        request_text_tokens INTEGER NOT NULL,
                        response_text_tokens INTEGER NOT NULL,
                        request_image_tokens INTEGER NOT NULL,
                        response_image_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        raw_usage_json TEXT
                    )
                    """
                )
            ensure_token_usage_schema(db_path)
            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_token_usage_events)").fetchall()}
                self.assertIn("agent_id", columns)

    def test_extract_usage_tokens_from_gemini_usage_metadata(self) -> None:
        usage_metadata = pytypes.SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=40,
            total_token_count=140,
            prompt_tokens_details=[
                pytypes.SimpleNamespace(modality=pytypes.SimpleNamespace(name="TEXT"), token_count=80),
                pytypes.SimpleNamespace(modality=pytypes.SimpleNamespace(name="IMAGE"), token_count=20),
            ],
            candidates_tokens_details=[
                pytypes.SimpleNamespace(modality=pytypes.SimpleNamespace(name="TEXT"), token_count=35),
                pytypes.SimpleNamespace(modality=pytypes.SimpleNamespace(name="IMAGE"), token_count=5),
            ],
        )
        llm_response = pytypes.SimpleNamespace(usage_metadata=usage_metadata, usage=None)

        tokens = extract_usage_tokens(llm_response)

        self.assertEqual(tokens["request_tokens"], 100)
        self.assertEqual(tokens["response_tokens"], 40)
        self.assertEqual(tokens["total_tokens"], 140)
        self.assertEqual(tokens["request_text_tokens"], 80)
        self.assertEqual(tokens["request_image_tokens"], 20)
        self.assertEqual(tokens["response_text_tokens"], 35)
        self.assertEqual(tokens["response_image_tokens"], 5)

    def test_extract_usage_tokens_fallback_to_openai_usage(self) -> None:
        llm_response = pytypes.SimpleNamespace(
            usage_metadata=None,
            usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        )

        tokens = extract_usage_tokens(llm_response)

        self.assertEqual(tokens["request_tokens"], 12)
        self.assertEqual(tokens["response_tokens"], 8)
        self.assertEqual(tokens["total_tokens"], 20)
        self.assertEqual(tokens["request_text_tokens"], 12)
        self.assertEqual(tokens["response_text_tokens"], 8)

    def test_write_and_read_token_usage_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "token_usage.db"
            ensure_token_usage_schema(db_path)
            write_token_usage_event(
                {
                    "request_at": "2026-02-26T10:00:00+00:00",
                    "request_at_ms": 1000,
                    "response_at": "2026-02-26T10:00:01+00:00",
                    "response_at_ms": 2000,
                    "provider": "google",
                    "model": "gemini-2.5-pro",
                    "agent_id": "main",
                    "session_id": "s1",
                    "invocation_id": "inv1",
                    "request_tokens": 20,
                    "response_tokens": 10,
                    "request_text_tokens": 15,
                    "response_text_tokens": 10,
                    "request_image_tokens": 5,
                    "response_image_tokens": 0,
                    "total_tokens": 30,
                    "raw_usage": {"usage_metadata": {"prompt_token_count": 20}},
                },
                db_path,
            )
            write_token_usage_event(
                {
                    "request_at": "2026-02-26T10:00:02+00:00",
                    "request_at_ms": 3000,
                    "response_at": "2026-02-26T10:00:03+00:00",
                    "response_at_ms": 4000,
                    "provider": "openai",
                    "model": "openai/gpt-5",
                    "agent_id": "biz",
                    "session_id": "s2",
                    "invocation_id": "inv2",
                    "request_tokens": 8,
                    "response_tokens": 12,
                    "request_text_tokens": 8,
                    "response_text_tokens": 12,
                    "request_image_tokens": 0,
                    "response_image_tokens": 0,
                    "total_tokens": 20,
                    "raw_usage": {"usage": {"prompt_tokens": 8}},
                },
                db_path,
            )

            all_stats = read_token_usage_stats(limit=10, db_path=db_path)
            google_stats = read_token_usage_stats(limit=10, provider="google", db_path=db_path)
            main_stats = read_token_usage_stats(limit=10, agent_id="main", db_path=db_path)

        self.assertEqual(all_stats["requests"], 2)
        self.assertEqual(all_stats["request_tokens"], 28)
        self.assertEqual(all_stats["response_tokens"], 22)
        self.assertEqual(all_stats["total_tokens"], 50)
        self.assertEqual(len(all_stats["recent"]), 2)

        self.assertEqual(google_stats["requests"], 1)
        self.assertEqual(google_stats["total_tokens"], 30)
        self.assertEqual(google_stats["recent"][0]["provider"], "google")
        self.assertEqual(main_stats["requests"], 1)
        self.assertEqual(main_stats["recent"][0]["agent_id"], "main")

    def test_read_token_usage_stats_filters_by_time_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "token_usage.db"
            ensure_token_usage_schema(db_path)
            write_token_usage_event(
                {
                    "request_at": "2026-02-26T10:00:00+00:00",
                    "request_at_ms": 1000,
                    "response_at": "2026-02-26T10:00:01+00:00",
                    "response_at_ms": 2000,
                    "provider": "google",
                    "model": "gemini-2.5-pro",
                    "agent_id": "main",
                    "session_id": "s1",
                    "invocation_id": "inv1",
                    "request_tokens": 10,
                    "response_tokens": 5,
                    "request_text_tokens": 10,
                    "response_text_tokens": 5,
                    "request_image_tokens": 0,
                    "response_image_tokens": 0,
                    "total_tokens": 15,
                    "raw_usage": {},
                },
                db_path,
            )
            write_token_usage_event(
                {
                    "request_at": "2026-02-26T10:00:02+00:00",
                    "request_at_ms": 3000,
                    "response_at": "2026-02-26T10:00:03+00:00",
                    "response_at_ms": 4000,
                    "provider": "openai",
                    "model": "openai/gpt-5",
                    "agent_id": "biz",
                    "session_id": "s2",
                    "invocation_id": "inv2",
                    "request_tokens": 20,
                    "response_tokens": 10,
                    "request_text_tokens": 20,
                    "response_text_tokens": 10,
                    "request_image_tokens": 0,
                    "response_image_tokens": 0,
                    "total_tokens": 30,
                    "raw_usage": {},
                },
                db_path,
            )

            filtered = read_token_usage_stats(limit=10, since_ms=2500, until_ms=5000, db_path=db_path)
            filtered_agent = read_token_usage_stats(limit=10, agent_id="biz", db_path=db_path)

        self.assertEqual(filtered["requests"], 1)
        self.assertEqual(filtered["total_tokens"], 30)
        self.assertEqual(filtered["recent"][0]["provider"], "openai")
        self.assertEqual(filtered_agent["requests"], 1)
        self.assertEqual(filtered_agent["recent"][0]["agent_id"], "biz")

    def test_parse_time_filter_to_epoch_ms_accepts_iso8601(self) -> None:
        parsed = parse_time_filter_to_epoch_ms("2026-02-26T00:00:00+00:00")
        self.assertIsInstance(parsed, int)
        self.assertGreater(parsed, 0)


if __name__ == "__main__":
    unittest.main()
