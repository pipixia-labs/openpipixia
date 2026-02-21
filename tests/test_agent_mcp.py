"""Tests for MCP toolset wiring in root agent assembly."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class AgentMcpTests(unittest.TestCase):
    def test_build_tools_appends_mcp_toolsets(self) -> None:
        from openheron import agent

        sentinel_toolset = object()
        with patch("openheron.agent.build_mcp_toolsets_from_env", return_value=[sentinel_toolset]):
            tools = agent._build_tools()

        self.assertIn(sentinel_toolset, tools)


if __name__ == "__main__":
    unittest.main()

