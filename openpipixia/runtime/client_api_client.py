"""Thin HTTP client for the local openpipixia client API service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


@dataclass(slots=True)
class ClientApiClient:
    """Call the local HTTP + SSE client API with stable typed helpers."""

    base_url: str = "http://127.0.0.1:8765"
    timeout_seconds: float = 10.0

    def _build_url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        """Build one request URL from a relative API path and query params."""
        normalized_path = "/" + str(path or "").lstrip("/")
        base = self.base_url.rstrip("/")
        if not query:
            return f"{base}{normalized_path}"
        encoded_query = parse.urlencode(
            {
                key: str(value)
                for key, value in query.items()
                if value is not None and str(value).strip()
            }
        )
        return f"{base}{normalized_path}?{encoded_query}" if encoded_query else f"{base}{normalized_path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute one JSON request and return the parsed response envelope."""
        payload = None
        headers = {"Accept": "application/json"}
        if json_body is not None:
            payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = request.Request(
            self._build_url(path, query=query),
            data=payload,
            headers=headers,
            method=method.upper(),
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = resp.read()
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def get_agent_access(self, agent_id: str, *, user_id: str = "ppx-client-user") -> dict[str, Any]:
        """Fetch one agent access snapshot."""
        return self._request(
            "GET",
            f"/api/v1/agents/{agent_id}/access",
            query={"user_id": user_id},
        )

    def list_memory_audit(
        self,
        agent_id: str,
        *,
        user_id: str = "ppx-client-user",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch visible explicit-memory audit rows for one agent."""
        return self._request(
            "GET",
            f"/api/v1/agents/{agent_id}/memory/audit",
            query={
                "user_id": user_id,
                "limit": limit,
            },
        )

    def set_agent_owner(
        self,
        agent_id: str,
        owner_principal_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Set one agent owner through the HTTP client API."""
        return self._request(
            "POST",
            f"/api/v1/agents/{agent_id}/access/owner",
            json_body={
                "user_id": user_id,
                "owner_principal_id": owner_principal_id,
            },
        )

    def upsert_agent_membership(
        self,
        agent_id: str,
        principal_id: str,
        *,
        relation: str = "participant",
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Create or update one agent membership through the HTTP client API."""
        return self._request(
            "POST",
            f"/api/v1/agents/{agent_id}/access/memberships",
            json_body={
                "user_id": user_id,
                "principal_id": principal_id,
                "relation": relation,
            },
        )

    def delete_agent_membership(
        self,
        agent_id: str,
        principal_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Delete one agent membership through the HTTP client API."""
        return self._request(
            "DELETE",
            f"/api/v1/agents/{agent_id}/access/memberships/{principal_id}",
            query={"user_id": user_id},
        )
