"""In-process stand-in for the runner service. It drives the MCP tool functions
directly with the capability token (as Hermes would over HTTP) following a
script, and produces the agent's Markdown result."""

from __future__ import annotations

import time

from investigations.api import RunnerError, RunState
from mcp_server.api import authorize_and_run, get_document, search_knowledge


class FakeRunner:
    """Behaviors: 'complete' (search, read, answer with real evidence ids),
    'invent' (one real + one invented citation), 'fail' (provider error),
    'hang' (never finishes), 'unreachable' (every call raises)."""

    def __init__(
        self, behavior: str = "complete", queries: list[str] | None = None, read_first: bool = True
    ):
        self.behavior = behavior
        self.queries = queries or [
            "hosting decision provider",
            "alternatives considered",
            "revision contract",
        ]
        self.read_first = read_first
        self.runs: dict[str, dict] = {}
        self.calls: list[str] = []
        self.tool_payloads: list[dict] = []
        self.deleted: list[str] = []

    def _check(self):
        if self.behavior == "unreachable":
            raise RunnerError("runner_unreachable", "fake")

    def create(
        self,
        *,
        run_key,
        question,
        instructions,
        max_turns,
        max_tool_calls,
        timeout_s,
        mcp_token,
        model=None,
    ):
        self._check()
        self.calls.append(f"create:{run_key}")
        if run_key in self.runs:
            return self._state(run_key)
        self.runs[run_key] = {
            "state": "created",
            "events": [],
            "terminal": None,
            "token": mcp_token,
            "question": question,
            "instructions": instructions,
            "exit_code": None,
        }
        return self._state(run_key)

    def start(self, run_key):
        self._check()
        self.calls.append(f"start:{run_key}")
        run = self.runs[run_key]
        if run["state"] != "created":
            return self._state(run_key)
        run["state"] = "running"
        if self.behavior == "hang":
            return self._state(run_key)
        if self.behavior == "fail":
            run["terminal"] = {
                "outcome": "failed",
                "final_text": "",
                "usage": {},
                "error": "provider: 503 overloaded",
            }
            run["state"] = "failed"
            run["exit_code"] = 1
            self._event(run, {"type": "terminal", "outcome": "failed", "exit_code": 1})
            return self._state(run_key)
        self._agent_loop(run)
        return self._state(run_key)

    def _tool(self, run, name, args, impl):
        headers = {"authorization": f"Bearer {run['token']}"}
        self._event(run, {"type": "tool_use", "name": f"mcp_knowledge_{name}"})
        payload = authorize_and_run(headers, name, args, impl)
        self.tool_payloads.append(payload)
        self._event(
            run,
            {
                "type": "tool_result",
                "name": f"mcp_knowledge_{name}",
                "duration_ms": 5,
                "is_error": "error" in payload,
            },
        )
        return payload

    def _agent_loop(self, run):
        evidence_ids: list[str] = []
        statements: list[tuple[str, list[str]]] = []
        for q in self.queries:
            payload = self._tool(
                run, "search_knowledge", {"query": q, "limit": 5}, search_knowledge
            )
            for r in payload.get("results", []):
                if r["evidence_id"] not in evidence_ids:
                    evidence_ids.append(r["evidence_id"])
                    statements.append((r["excerpt"].split("\n")[-1][:160], [r["evidence_id"]]))
            if payload.get("results") and self.read_first:
                self._tool(
                    run,
                    "get_document",
                    {"document_id": payload["results"][0]["document_id"]},
                    get_document,
                )
        if self.behavior == "draft" and evidence_ids:
            from decisions.api import draft_knowledge_record

            payload = self._tool(
                run,
                "draft_knowledge_record",
                {"topic": "Hosting provider decision history", "evidence_ids": evidence_ids[:3]},
                draft_knowledge_record,
            )
            statements.append(
                (f"A candidate record was drafted ({payload.get('status')}).", [evidence_ids[0]])
            )
        if self.behavior == "invent":
            statements.append(
                (
                    "The board approved the migration unanimously.",
                    ["chunk:00000000-0000-0000-0000-000000000000@v9[0:10]"],
                )
            )
        lines = [
            "## Answer",
            "Based on the retrieved documents, the decision, the alternative and the later revision are described below.",
            "",
            "## Evidence summary",
        ]
        lines += [f"- {s[0]} [{', '.join(s[1])}]" for s in statements]
        lines += [
            "",
            "## Conflicts",
            "- None found.",
            "",
            "## Open questions",
            "- Approval is not documented in the retrieved evidence.",
            "",
            "## Statements",
        ]
        lines += [f"- {s[0]} [{', '.join(s[1])}]" for s in statements]
        run["terminal"] = {
            "outcome": "completed",
            "final_text": "\n".join(lines),
            "usage": {"input": 1200, "output": 300},
            "error": None,
        }
        run["state"] = "completed"
        run["exit_code"] = 0
        self._event(run, {"type": "text", "text": "..."})
        self._event(run, {"type": "terminal", "outcome": "completed", "exit_code": 0})

    def _event(self, run, event):
        run["events"].append({"seq": len(run["events"]) + 1, **event})

    def _state(self, run_key):
        run = self.runs[run_key]
        return RunState(
            run_key=run_key,
            state=run["state"],
            exit_code=run["exit_code"],
            terminal=run["terminal"],
        )

    def get(self, run_key):
        self._check()
        if run_key not in self.runs:
            raise RunnerError("runner_error", "unknown run", status=404)
        return self._state(run_key)

    def events(self, run_key, after, wait_s=0.0):
        self._check()
        run = self.runs[run_key]
        out = [e for e in run["events"] if e["seq"] > after]
        if not out and self.behavior == "hang":
            time.sleep(0.01)
        return out

    def cancel(self, run_key):
        self._check()
        self.calls.append(f"cancel:{run_key}")
        run = self.runs.get(run_key)
        if run and run["state"] in ("created", "running"):
            run["state"] = "cancelled"
            run["terminal"] = {"outcome": "cancelled", "final_text": "", "usage": {}, "error": None}
            self._event(run, {"type": "terminal", "outcome": "cancelled", "exit_code": 130})

    def delete(self, run_key):
        self.deleted.append(run_key)
        self.runs.pop(run_key, None)
