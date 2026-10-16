"""Live Hermes contract checks (PLAN.md matrix, marker `hermes`). They run only
when the hermes-agent image exists and a provider key is present; otherwise
they are skipped and IMPLEMENTATION_STATUS.md reports them as not run."""

import json
import os
import shutil
import subprocess

import pytest

IMAGE = os.environ.get("KB_HERMES_IMAGE", "kb-hermes-agent:dev")
KEY_ENV = os.environ.get("HERMES_PROVIDER_API_KEY_ENV", "ANTHROPIC_API_KEY")


def _image_present() -> bool:
    if not shutil.which("docker"):
        return False
    return (
        subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    )


@pytest.mark.hermes
@pytest.mark.live
@pytest.mark.skipif(not _image_present(), reason=f"hermes image {IMAGE} not built")
@pytest.mark.skipif(not os.environ.get(KEY_ENV), reason=f"{KEY_ENV} not set")
def test_attestation_passes_with_live_model():
    """The pinned invocation, against the self-check MCP server: only knowledge
    tools are enabled, the bearer arrives, the run exits 0."""
    # posix_spawn, not fork: this test runs late in the suite, after tests that
    # used threads, and a fork() of the multithreaded pytest process on macOS
    # crashed the child (SIGSEGV, no output) before `docker` started. CPython
    # uses posix_spawn only for an absolute executable with close_fds=False.
    proc = subprocess.run(
        [
            shutil.which("docker"),
            "run",
            "--rm",
            "-e",
            f"{KEY_ENV}={os.environ[KEY_ENV]}",
            IMAGE,
            "/opt/hermes/.venv/bin/python",
            "-c",
            "import sys; sys.path.insert(0, '/opt/runner'); import attestation, json; print(json.dumps(attestation.run()))",
        ],
        capture_output=True,
        text=True,
        timeout=400,
        close_fds=False,
    )
    lines = proc.stdout.strip().splitlines()
    assert lines, f"no output from docker run: exit={proc.returncode} stderr={proc.stderr[-1500:]}"
    result = json.loads(lines[-1])
    assert result["ok"], result
    assert all(t.startswith("mcp__knowledge__") for t in result["tools"]), result
