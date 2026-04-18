"""Tests for ADK text extraction and stream merging helpers."""

from __future__ import annotations

import types as pytypes
import unittest

from openppx.runtime.adk_utils import extract_text, merge_text_stream


class AdkUtilsTests(unittest.TestCase):
    def test_extract_text_preserves_text_part_spacing(self) -> None:
        content = pytypes.SimpleNamespace(
            parts=[
                pytypes.SimpleNamespace(text="hello"),
                pytypes.SimpleNamespace(text=" world"),
                pytypes.SimpleNamespace(text=None),
            ]
        )

        self.assertEqual(extract_text(content), "hello world")

    def test_merge_text_stream_appends_delta_chunks_without_newline(self) -> None:
        merged = merge_text_stream("", "hello")
        merged = merge_text_stream(merged, " world")

        self.assertEqual(merged, "hello world")

    def test_merge_text_stream_keeps_snapshot_updates(self) -> None:
        merged = merge_text_stream("", "hello")
        merged = merge_text_stream(merged, "hello world")

        self.assertEqual(merged, "hello world")

    def test_merge_text_stream_skips_final_aggregate_after_deltas(self) -> None:
        merged = merge_text_stream("", "hello")
        merged = merge_text_stream(merged, " world")
        merged = merge_text_stream(merged, "hello world")

        self.assertEqual(merged, "hello world")


if __name__ == "__main__":
    unittest.main()
