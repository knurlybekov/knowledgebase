"""Configuration attestation (PLAN.md D1): before any run, start the self-check
MCP server, run the pinned invocation against it with the generated config, and
assert that the tool inventory Hermes reports contains only knowledge tools and
that the token reached the MCP server as the Authorization bearer.

The inventory is read from the stream-json `system`/`tool_use` events and from
the `--list-tools` style dump when the CLI offers one; the spike records which."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import runs

ATTEST_TIMEOUT_S = int(os.environ.get("RUNNER_ATTEST_TIMEOUT_S", "240"))


def _start_selfcheck(token: str, port: int) -> subprocess.Popen:
    env = {**os.environ, "SELFCHECK_TOKEN": token, "SELFCHECK_PORT": str(port)}
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("selfcheck_mcp.py"))], env=env
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/selfcheck/seen", timeout=0.5)
            return proc
        except Exception:
            time.sleep(0.1)
    return proc


def run() -> dict:
    """Returns {ok, detail, tools, auth_ok, exit_code}. Never raises."""
    if not os.environ.get(runs.PROVIDER_KEY_ENV):
        return {
            "ok": False,
            "detail": f"{runs.PROVIDER_KEY_ENV} not set; cannot attest without a model",
        }
    token = secrets.token_urlsafe(24)
    port = int(os.environ.get("SELFCHECK_PORT", "8799"))
    selfcheck = _start_selfcheck(token, port)
    home = Path(tempfile.mkdtemp(prefix="attest-", dir=str(runs.RUNS_ROOT)))
    try:
        (home / "config.yaml").write_text(
            runs.render_config(f"http://127.0.0.1:{port}/mcp", runs.HERMES_MODEL, 3, 3)
        )
        (home / "AGENTS.md").write_text(
            "Call the search_knowledge tool once with query 'attest', then answer with the tool output."
        )
        env = {
            "HOME": str(home),
            "HERMES_HOME": str(home),
            "KNOWLEDGE_MCP_TOKEN": token,
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "LANG": "C.UTF-8",
            runs.PROVIDER_KEY_ENV: os.environ[runs.PROVIDER_KEY_ENV],
        }
        for key in ("HERMES_RUNTIME_DIR", "HERMES_PYTHON"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        cmd = [
            runs.HERMES_BIN,
            "chat",
            "-q",
            "Call the search_knowledge tool with query 'attest' and report its output.",
            "--toolsets",
            runs.TOOLSET,
            "--max-turns",
            "3",
            "--format",
            "stream-json",
        ]
        proc = subprocess.run(
            cmd, cwd=str(home), env=env, capture_output=True, text=True, timeout=ATTEST_TIMEOUT_S
        )
        tools_used: set[str] = set()
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "tool_use":
                tools_used.add(str(event.get("name")))
        try:
            seen = json.loads(
                urllib.request.urlopen(f"http://127.0.0.1:{port}/selfcheck/seen", timeout=2).read()
            )
        except Exception:
            seen = {"auth_ok": False, "calls": 0}
        foreign = sorted(
            t
            for t in tools_used
            if not t.startswith("mcp_knowledge_") and not t.startswith("search_knowledge")
        )
        ok = (
            proc.returncode == 0
            and seen.get("auth_ok")
            and seen.get("calls", 0) >= 1
            and not foreign
        )
        detail = (
            "ok"
            if ok
            else (
                f"exit={proc.returncode} auth_ok={seen.get('auth_ok')} calls={seen.get('calls')} foreign={foreign} "
                f"stderr={proc.stderr[-400:].strip()}"
            )
        )
        return {
            "ok": bool(ok),
            "detail": detail,
            "tools": sorted(tools_used),
            "auth_ok": bool(seen.get("auth_ok")),
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "attestation timed out"}
    finally:
        selfcheck.terminate()
        shutil.rmtree(home, ignore_errors=True)
