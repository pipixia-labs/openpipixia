"""LLM callback-based debug tracing."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

from ..env_utils import env_enabled

_DEFAULT_MAX_TEXT_CHARS = 2000
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?([^\s'\",]+)"),
]


def _debug_enabled() -> bool:
    return env_enabled("SENTIENTAGENT_V2_DEBUG", default=False)


def _max_chars() -> int:
    raw = os.getenv("SENTIENTAGENT_V2_DEBUG_MAX_CHARS", str(_DEFAULT_MAX_TEXT_CHARS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_MAX_TEXT_CHARS
    return max(200, min(value, 20000))


def _redact(text: str) -> str:
    value = text
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.lower().startswith("(?i)(api"):
            value = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", value)
        else:
            value = pattern.sub("<redacted>", value)
    return value


def _clip(text: str) -> str:
    max_chars = _max_chars()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (truncated {len(text) - max_chars} chars)"


def _extract_part_text(part: Any) -> str:
    text = getattr(part, "text", None)
    return text or ""


def _extract_content_text(content: Any) -> str:
    parts = getattr(content, "parts", None)
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:
        text = _extract_part_text(part)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _request_texts(llm_request: LlmRequest) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    system_instruction = getattr(getattr(llm_request, "config", None), "system_instruction", None)
    if isinstance(system_instruction, str) and system_instruction.strip():
        rows.append({"role": "system", "text": system_instruction.strip()})

    for content in getattr(llm_request, "contents", []) or []:
        text = _extract_content_text(content)
        if not text:
            continue
        role = str(getattr(content, "role", "") or "unknown")
        rows.append({"role": role, "text": text})
    return rows


def _non_empty_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _sanitize_tool_ids(callback_context: CallbackContext, llm_request: LlmRequest) -> int:
    """Ensure tool call / tool response ids are present before provider call."""
    invocation_id = _non_empty_str(getattr(callback_context, "invocation_id", None)) or "inv"
    patched = 0
    fallback_counter = 0
    pending_tool_call_ids: list[str] = []

    for content_index, content in enumerate(getattr(llm_request, "contents", []) or []):
        parts = getattr(content, "parts", None) or []
        for part_index, part in enumerate(parts):
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                current_id = _non_empty_str(getattr(function_call, "id", None))
                if current_id is None:
                    fallback_counter += 1
                    current_id = (
                        f"adk-auto-{invocation_id}-{content_index}-{part_index}-{fallback_counter}-{uuid.uuid4().hex[:8]}"
                    )
                    function_call.id = current_id
                    patched += 1
                pending_tool_call_ids.append(current_id)

            function_response = getattr(part, "function_response", None)
            if function_response is not None:
                response_id = _non_empty_str(getattr(function_response, "id", None))
                if response_id is None:
                    if pending_tool_call_ids:
                        response_id = pending_tool_call_ids.pop(0)
                    else:
                        fallback_counter += 1
                        response_id = (
                            f"adk-auto-resp-{invocation_id}-{content_index}-{part_index}-{fallback_counter}-{uuid.uuid4().hex[:8]}"
                        )
                    function_response.id = response_id
                    patched += 1
                else:
                    try:
                        pending_tool_call_ids.remove(response_id)
                    except ValueError:
                        pass

    return patched


def _response_text(llm_response: LlmResponse) -> str:
    return _extract_content_text(getattr(llm_response, "content", None))


def _write_debug(tag: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str)
    print(f"[DEBUG] {tag}: {body}", file=sys.stderr)


def before_model_debug_callback(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Emit sanitized request payload before model invocation."""
    patched = _sanitize_tool_ids(callback_context, llm_request)
    if not _debug_enabled():
        return None

    texts = _request_texts(llm_request)
    payload = {
        "invocation_id": getattr(callback_context, "invocation_id", ""),
        "session_id": getattr(getattr(callback_context, "session", None), "id", ""),
        "agent": getattr(callback_context, "agent_name", ""),
        "user_id": getattr(callback_context, "user_id", ""),
        "model": getattr(llm_request, "model", None),
        "tools": sorted((getattr(llm_request, "tools_dict", {}) or {}).keys()),
        "messages": [
            {"role": row["role"], "text": _clip(_redact(row["text"]))}
            for row in texts
        ],
    }
    if patched:
        payload["patched_tool_ids"] = patched
    _write_debug("llm.before_model", payload)
    return None


def after_model_debug_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """Emit sanitized response summary after model invocation."""
    if not _debug_enabled():
        return None

    payload = {
        "invocation_id": getattr(callback_context, "invocation_id", ""),
        "session_id": getattr(getattr(callback_context, "session", None), "id", ""),
        "agent": getattr(callback_context, "agent_name", ""),
        "finish_reason": str(getattr(llm_response, "finish_reason", "") or ""),
        "partial": bool(getattr(llm_response, "partial", False)),
        "turn_complete": bool(getattr(llm_response, "turn_complete", False)),
        "error_code": getattr(llm_response, "error_code", None),
        "error_message": getattr(llm_response, "error_message", None),
        "text": _clip(_redact(_response_text(llm_response))),
    }
    _write_debug("llm.after_model", payload)
    return None
