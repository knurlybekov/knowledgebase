"""Run lifecycle for one isolated Hermes process per investigation (PLAN.md D1).

Each run gets its own HERMES_HOME under RUNS_ROOT with a generated config.yaml
(MCP server with the capability token read from the process environment, memory
off, only the knowledge toolset), an AGENTS.md carrying the investigator
instructions, and a new process group. Events are appended to a JSONL file with
sequence numbers so a reconnecting client can replay from any point. The
registry on disk makes terminal records survive a runner restart.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

RUNS_ROOT = Path(os.environ.get("RUNS_ROOT", "/opt/data/runs"))
REGISTRY_ROOT = Path(os.environ.get("REGISTRY_ROOT", "/opt/data/registry"))
HERMES_BIN = os.environ.get("HERMES_BIN", "/opt/hermes/bin/hermes")
KNOWLEDGE_MCP_URL = os.environ.get("KNOWLEDGE_MCP_URL", "http://knowledge-mcp:8710/mcp")
HERMES_MODEL = os.environ.get("HERMES_MODEL", "anthropic/claude-opus-5")
PROVIDER_KEY_ENV = os.environ.get("HERMES_PROVIDER_API_KEY_ENV", "ANTHROPIC_API_KEY")
RECORD_TTL_S = int(os.environ.get("RUNNER_RECORD_TTL_S", str(24 * 3600)))
GRACE_S = float(os.environ.get("RUNNER_KILL_GRACE_S", "10"))
TOOLSET = "mcp-knowledge"
BLOCKED_TOOL_PREFIXES = (
    "terminal",
    "browser",
    "web_",
    "read_file",
    "write_file",
    "memory",
    "session_search",
    "skill",
    "delegate",
    "execute_code",
    "search_files",
    "patch",
    "list_dir",
)


def boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return "unknown"


@dataclass
class RunRecord:
    run_key: str
    state: str  # created | running | completed | failed | cancelled | timed_out
    dir: str
    events_path: str
    pgid: int | None = None
    start_time: float | None = None
    boot_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    exit_code: int | None = None
    terminal: dict | None = None  # {outcome, final_text, usage, error}
    timeout_s: int = 180

    def save(self) -> None:
        self.updated_at = time.time()
        path = REGISTRY_ROOT / f"{self.run_key.replace(':', '_')}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self)))
        tmp.replace(path)

    @classmethod
    def load(cls, run_key: str) -> RunRecord | None:
        path = REGISTRY_ROOT / f"{run_key.replace(':', '_')}.json"
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text()))

    @classmethod
    def all(cls) -> list[RunRecord]:
        out = []
        for path in REGISTRY_ROOT.glob("*.json"):
            try:
                out.append(cls(**json.loads(path.read_text())))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def delete(self) -> None:
        path = REGISTRY_ROOT / f"{self.run_key.replace(':', '_')}.json"
        path.unlink(missing_ok=True)
        shutil.rmtree(self.dir, ignore_errors=True)
        Path(self.events_path).unlink(missing_ok=True)


def render_config(mcp_url: str, model: str, max_turns: int, max_tool_calls: int) -> str:
    """config.yaml for one run. The MCP token is read from the process environment
    through ${KNOWLEDGE_MCP_TOKEN}; it never appears in the file or the prompt."""
    return (
        f"model: {model}\n"
        "agent:\n"
        f"  max_turns: {max_turns}\n"
        f"  max_tool_calls: {max_tool_calls}\n"
        "memory:\n"
        "  memory_enabled: false\n"
        "  user_profile_enabled: false\n"
        "approvals:\n"
        "  mode: manual\n"
        "  single_query_mode: deny\n"
        "platform_toolsets:\n"
        f"  cli: [{TOOLSET}]\n"
        "mcp_servers:\n"
        "  knowledge:\n"
        f"    url: {mcp_url}\n"
        "    headers:\n"
        '      Authorization: "Bearer ${KNOWLEDGE_MCP_TOKEN}"\n'
        "    timeout: 60\n"
        "    connect_timeout: 20\n"
        "    tools:\n"
        "      resources: false\n"
        "      prompts: false\n"
    )


class Run:
    def __init__(self, record: RunRecord):
        self.record = record
        self._lock = threading.Lock()
        self._seq = 0
        self._proc: subprocess.Popen | None = None
        self._cancel_requested = False

    # --- events ---------------------------------------------------------------
    def _append(self, event: dict) -> None:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, **event}
            with open(self.record.events_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")

    def events_after(self, after: int) -> list[dict]:
        out = []
        try:
            with open(self.record.events_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("seq", 0) > after:
                        out.append(event)
        except FileNotFoundError:
            pass
        return out

    # --- lifecycle ------------------------------------------------------------
    def start(
        self,
        question: str,
        instructions: str,
        *,
        max_turns: int,
        max_tool_calls: int,
        timeout_s: int,
        mcp_token: str,
        model: str | None = None,
    ) -> None:
        run_dir = Path(self.record.dir)
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(run_dir, 0o700)
        (run_dir / "config.yaml").write_text(
            render_config(KNOWLEDGE_MCP_URL, model or HERMES_MODEL, max_turns, max_tool_calls)
        )
        (run_dir / "AGENTS.md").write_text(instructions)
        env = {
            "HOME": str(run_dir),
            "HERMES_HOME": str(run_dir),
            "KNOWLEDGE_MCP_TOKEN": mcp_token,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONUNBUFFERED": "1",
            "HERMES_RUNTIME_DIR": os.environ.get("HERMES_RUNTIME_DIR", ""),
            "HERMES_PYTHON": os.environ.get("HERMES_PYTHON", ""),
            "LANG": "C.UTF-8",
        }
        if PROVIDER_KEY_ENV in os.environ:
            env[PROVIDER_KEY_ENV] = os.environ[PROVIDER_KEY_ENV]
        cmd = [
            HERMES_BIN,
            "chat",
            "-q",
            question,
            "--toolsets",
            TOOLSET,
            "--max-turns",
            str(max_turns),
            "--format",
            "stream-json",
        ]
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(run_dir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.record.state = "running"
        self.record.pgid = os.getpgid(self._proc.pid)
        self.record.start_time = psutil.Process(self._proc.pid).create_time()
        self.record.boot_id = boot_id()
        self.record.timeout_s = timeout_s
        self.record.save()
        self._append({"type": "runner", "subtype": "started", "pid": self._proc.pid})
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._watchdog, args=(timeout_s,), daemon=True).start()

    def _pump(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        final_text = ""
        tokens: dict = {}
        error = None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                self._append({"type": "stderr", "text": line[:500]})
                continue
            kind = event.get("type")
            if kind == "text":
                self._append({"type": "text", "text": event.get("text", "")})
            elif kind == "tool_use":
                self._append(
                    {
                        "type": "tool_use",
                        "name": event.get("name"),
                        "tool_call_id": event.get("tool_call_id"),
                    }
                )
            elif kind == "tool_result":
                self._append(
                    {
                        "type": "tool_result",
                        "name": event.get("name"),
                        "duration_ms": event.get("duration_ms"),
                        "is_error": bool(event.get("is_error")),
                    }
                )
            elif kind == "result":
                final_text = event.get("text") or ""
                tokens = event.get("tokens") or {}
                error = event.get("error")
            elif kind == "system":
                self._append({"type": "system", "model": event.get("model")})
        stderr_tail = ""
        if self._proc.stderr is not None:
            stderr_tail = self._proc.stderr.read()[-2000:]
        code = self._proc.wait()
        if self.record.state == "running":
            if self._cancel_requested:
                outcome = "cancelled"
            elif code == 0:
                outcome = "completed"
            else:
                outcome = "failed"
            self.record.state = outcome
        outcome = self.record.state
        self.record.exit_code = code
        self.record.terminal = {
            "outcome": outcome,
            "final_text": final_text,
            "usage": tokens,
            "error": error or (stderr_tail.strip()[-500:] if code not in (0,) else None),
        }
        self.record.save()
        self._append({"type": "terminal", "outcome": outcome, "exit_code": code})
        shutil.rmtree(self.record.dir, ignore_errors=True)  # session db, config, AGENTS.md

    def _watchdog(self, timeout_s: int) -> None:
        deadline = time.time() + timeout_s
        while self._proc is not None and self._proc.poll() is None:
            if time.time() > deadline:
                self.record.state = "timed_out"
                self.record.save()
                self._append({"type": "runner", "subtype": "timeout"})
                self._signal_group()
                return
            time.sleep(0.5)

    def cancel(self) -> bool:
        if self._proc is None or self._proc.poll() is not None:
            return False
        self._cancel_requested = True
        self.record.state = "cancelled"
        self.record.save()
        self._append({"type": "runner", "subtype": "cancel"})
        self._signal_group()
        return True

    def _signal_group(self) -> None:
        if self.record.pgid is None:
            return
        try:
            os.killpg(self.record.pgid, signal.SIGINT)
        except ProcessLookupError:
            return
        deadline = time.time() + GRACE_S
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                return
            time.sleep(0.2)
        try:
            os.killpg(self.record.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


def group_alive_with_identity(record: RunRecord) -> bool:
    """True only when a live process matches pgid, start time and boot id."""
    if record.pgid is None or record.start_time is None or record.boot_id != boot_id():
        return False
    for proc in psutil.process_iter(["pid"]):
        try:
            if (
                os.getpgid(proc.pid) == record.pgid
                and abs(proc.create_time() - record.start_time) < 1.0
            ):
                return True
        except (psutil.NoSuchProcess, ProcessLookupError, psutil.AccessDenied):
            continue
    return False


def reconcile_orphans() -> dict:
    """Startup: kill recorded groups that still match their identity; erase run
    directories left behind; drop expired terminal records."""
    killed = erased = expired = 0
    now = time.time()
    for record in RunRecord.all():
        if record.state in ("created", "running"):
            if group_alive_with_identity(record):
                try:
                    os.killpg(record.pgid, signal.SIGKILL)  # type: ignore[arg-type]
                    killed += 1
                except ProcessLookupError:
                    pass
            record.state = "failed"
            record.terminal = {
                "outcome": "interrupted",
                "final_text": "",
                "usage": {},
                "error": "runner restarted",
            }
            record.save()
            shutil.rmtree(record.dir, ignore_errors=True)
            erased += 1
        elif now - record.updated_at > RECORD_TTL_S:
            record.delete()
            expired += 1
    for path in RUNS_ROOT.glob("*"):
        if path.is_dir() and RunRecord.load(path.name.replace("_", ":", 1)) is None:
            shutil.rmtree(path, ignore_errors=True)
            erased += 1
    return {"killed": killed, "erased": erased, "expired": expired}
