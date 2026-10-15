"""HTTP client for the runner service (PLAN.md "Runner"). Pure transport; the
lifecycle logic lives in service.py so tests can replace this with a fake."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from django.conf import settings


class RunnerError(Exception):
    def __init__(self, code: str, message: str = "", status: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.status = status


@dataclass
class RunState:
    run_key: str
    state: str
    exit_code: int | None
    terminal: dict | None


class RunnerClient:
    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or settings.RUNNER_URL).rstrip("/")
        self.secret = secret if secret is not None else settings.RUNNER_SHARED_SECRET
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=35.0))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}", "Accept": "application/json"}

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
            )
        except httpx.TransportError as exc:
            raise RunnerError("runner_unreachable", str(exc)) from exc
        if response.status_code == 429:
            raise RunnerError("runner_busy", status=429)
        if response.status_code == 503:
            raise RunnerError("runner_not_attested", response.text[:200], status=503)
        if response.status_code >= 400:
            raise RunnerError("runner_error", response.text[:200], status=response.status_code)
        return response

    @staticmethod
    def _state(data: dict) -> RunState:
        return RunState(
            run_key=data["run_key"],
            state=data["state"],
            exit_code=data.get("exit_code"),
            terminal=data.get("terminal"),
        )

    def create(
        self,
        *,
        run_key: str,
        question: str,
        instructions: str,
        max_turns: int,
        max_tool_calls: int,
        timeout_s: int,
        mcp_token: str,
        model: str | None = None,
    ) -> RunState:
        body = {
            "run_key": run_key,
            "question": question,
            "instructions": instructions,
            "max_turns": max_turns,
            "max_tool_calls": max_tool_calls,
            "timeout_s": timeout_s,
            "mcp_token": mcp_token,
            "model": model,
        }
        return self._state(self._call("POST", "/runs", json=body).json())

    def start(self, run_key: str) -> RunState:
        return self._state(self._call("POST", f"/runs/{run_key}/start").json())

    def get(self, run_key: str) -> RunState:
        return self._state(self._call("GET", f"/runs/{run_key}").json())

    def events(self, run_key: str, after: int, wait_s: float = 20.0) -> list[dict]:
        response = self._call(
            "GET", f"/runs/{run_key}/events", params={"after": after, "wait_s": wait_s}
        )
        out = []
        for line in response.text.splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def cancel(self, run_key: str) -> None:
        self._call("POST", f"/runs/{run_key}/cancel")

    def delete(self, run_key: str) -> None:
        try:
            self._call("DELETE", f"/runs/{run_key}")
        except RunnerError as exc:
            if exc.status != 404:
                raise
