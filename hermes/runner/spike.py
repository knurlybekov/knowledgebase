"""Hermes CLI contract checks (PLAN.md Sprint 2 step 8). Prints a Markdown report
for HERMES_INTEGRATION.md. Runs inside the hermes-agent image. Checks that need
a model provider are marked SKIPPED without a key."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runs

HERMES = runs.HERMES_BIN


def sh(args, **kw):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=kw.pop("timeout", 120), **kw
    )


def main() -> int:
    rows = []
    v = sh([HERMES, "--version"])
    rows.append(("hermes --version", v.returncode, (v.stdout or v.stderr).strip()[-200:]))
    h = sh([HERMES, "chat", "--help"])
    flags = {
        f: (f in h.stdout)
        for f in (
            "--toolsets",
            "--max-turns",
            "--format",
            "-q",
            "--oneshot",
            "--ignore-user-config",
        )
    }
    rows.append(("chat --help flags present", h.returncode, json.dumps(flags)))
    home = Path(tempfile.mkdtemp(prefix="spike-"))
    (home / "config.yaml").write_text(
        runs.render_config("http://127.0.0.1:1/mcp", runs.HERMES_MODEL, 2, 2)
    )
    env = {
        "HOME": str(home),
        "HERMES_HOME": str(home),
        "KNOWLEDGE_MCP_TOKEN": "spike-token",
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
    }
    for key in ("HERMES_RUNTIME_DIR", "HERMES_PYTHON"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    cfg = sh([HERMES, "config", "get", "memory.memory_enabled"], env=env, cwd=str(home))
    rows.append(
        (
            "config get memory.memory_enabled (per-run HERMES_HOME honored)",
            cfg.returncode,
            (cfg.stdout or cfg.stderr).strip()[-200:],
        )
    )
    sj = sh(
        [
            HERMES,
            "chat",
            "-q",
            "say ok",
            "--format",
            "stream-json",
            "--max-turns",
            "1",
            "--toolsets",
            runs.TOOLSET,
        ],
        env=env,
        cwd=str(home),
        timeout=180,
    )
    kinds = []
    for line in sj.stdout.splitlines():
        try:
            kinds.append(json.loads(line).get("type"))
        except json.JSONDecodeError:
            pass
    rows.append(
        (
            "chat -q --format stream-json without provider key (expect init+result, exit 1)",
            sj.returncode,
            f"event types={kinds} stderr={sj.stderr.strip()[-300:]}",
        )
    )
    # No-key handshake: with the self-check MCP server reachable, Hermes registers
    # the toolset, connects with the interpolated bearer, and fails only at the
    # model call (fake key). This verifies ${KNOWLEDGE_MCP_TOKEN} reaches the MCP server.
    import urllib.request

    sc_env = {**os.environ, "SELFCHECK_TOKEN": "spike-token", "SELFCHECK_PORT": "8799"}
    sc = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("selfcheck_mcp.py"))], env=sc_env
    )
    home2 = Path(tempfile.mkdtemp(prefix="spike2-"))
    try:
        time.sleep(1)
        (home2 / "config.yaml").write_text(
            runs.render_config("http://127.0.0.1:8799/mcp", runs.HERMES_MODEL, 1, 1)
        )
        env2 = {
            **env,
            "HOME": str(home2),
            "HERMES_HOME": str(home2),
            runs.PROVIDER_KEY_ENV: os.environ.get(runs.PROVIDER_KEY_ENV, "sk-fake-for-handshake"),
        }
        hs = sh(
            [
                HERMES,
                "chat",
                "-q",
                "say ok",
                "--format",
                "stream-json",
                "--max-turns",
                "1",
                "--toolsets",
                runs.TOOLSET,
            ],
            env=env2,
            cwd=str(home2),
            timeout=240,
        )
        seen = json.loads(
            urllib.request.urlopen("http://127.0.0.1:8799/selfcheck/seen", timeout=2).read()
        )
        gw = runs._gateway_pids_for_home(str(home2))
        stopped = runs.stop_gateway_for_home(str(home2))
        rows.append(
            (
                "MCP handshake with ${KNOWLEDGE_MCP_TOKEN} (self-check server; model call expected to fail without a real key)",
                hs.returncode,
                f"auth_ok={seen.get('auth_ok')} gateway_procs_after_run={len(gw)} stopped={stopped} stderr={hs.stderr.strip()[-200:]}",
            )
        )
    finally:
        sc.terminate()
        shutil.rmtree(home2, ignore_errors=True)
    if os.environ.get(runs.PROVIDER_KEY_ENV):
        import attestation

        att = attestation.run()
        rows.append(
            (
                "attestation against self-check MCP (live model)",
                0 if att["ok"] else 1,
                json.dumps(att)[:600],
            )
        )
    else:
        rows.append(
            (
                "attestation against self-check MCP (live model)",
                -1,
                f"SKIPPED: {runs.PROVIDER_KEY_ENV} not set",
            )
        )
    print("| check | exit | detail |\n|---|---|---|")
    for name, code, detail in rows:
        print(f"| {name} | {code} | {detail.replace('|', '/').replace(chr(10), ' ')} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
