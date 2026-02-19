"""Tests for ADK memory wiring in root agent."""

from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch

from google.adk.tools.preload_memory_tool import PreloadMemoryTool


class AgentMemoryTests(unittest.TestCase):
    def test_build_tools_includes_preload_memory_tool(self) -> None:
        from sentientagent_v2 import agent

        tools = agent._build_tools()
        self.assertTrue(any(isinstance(item, PreloadMemoryTool) for item in tools))

    def test_after_agent_memory_callback_persists_session(self) -> None:
        from sentientagent_v2 import agent

        callback_context = types.SimpleNamespace(add_session_to_memory=AsyncMock(return_value=None))
        asyncio.run(agent._after_agent_memory_callback(callback_context))
        callback_context.add_session_to_memory.assert_awaited_once()

    def test_after_agent_memory_callback_ignores_missing_memory_service(self) -> None:
        from sentientagent_v2 import agent

        callback_context = types.SimpleNamespace(
            add_session_to_memory=AsyncMock(side_effect=ValueError("memory service is not available"))
        )
        asyncio.run(agent._after_agent_memory_callback(callback_context))
        callback_context.add_session_to_memory.assert_awaited_once()

    def test_root_agent_registers_after_agent_callback(self) -> None:
        from sentientagent_v2 import agent

        self.assertIs(agent.root_agent.after_agent_callback, agent._after_agent_memory_callback)

    def test_mcp_toolsets_still_appended_after_memory_tool(self) -> None:
        from sentientagent_v2 import agent

        sentinel_toolset = object()
        with patch("sentientagent_v2.agent.build_mcp_toolsets_from_env", return_value=[sentinel_toolset]):
            tools = agent._build_tools()
        self.assertIn(sentinel_toolset, tools)


if __name__ == "__main__":
    unittest.main()

