# Hermes Agent integration

Hermes Agent (Nous Research) runs Deep Investigations. This document records the pinned version, how the service is built and configured, how user identity reaches the MCP tools, what the Sprint 2 spike verified by running the CLI, and how to troubleshoot.

## Pinned version

| Item | Value | Verified |
|---|---|---|
| Repository | https://github.com/NousResearch/hermes-agent | 2026-10-14 |
| Tag | `v0.22.1` (released 2026-10-14) | GitHub releases page |
| Image | built from the repository's own `Dockerfile` at that tag (`debian:13.4`, sealed venv `/opt/hermes/.venv`, `HERMES_HOME=/opt/data`, non-root uid 10000) | `docker build https://github.com/NousResearch/hermes-agent.git#v0.22.1` on 2026-10-15 |
| Python inside the image | 3.14.7 | `hermes --version` in the image |
| `hermes --version` output | `Hermes Agent vunknown (2026.9.24)` (the tag build does not stamp a version string; the install method shows `docker`) | spike |

The PyPI package is not used: the repository's `pyproject.toml` carries version `0.0.0`.

## Architecture (PLAN.md D1)

```
web/worker (Django)  --POST /runs (runner secret)-->  hermes-agent container
                                                       runner (FastAPI, our code)
                                                       └─ one `hermes chat -q …` process per investigation
                                                          HERMES_HOME=/opt/data/runs/<run_key>  (0700, erased at exit)
                                                          KNOWLEDGE_MCP_TOKEN in the process environment only
                                                               │ MCP streamable HTTP, Authorization: Bearer ${KNOWLEDGE_MCP_TOKEN}
                                                               ▼
                                                     knowledge-mcp (Django image, mcp_server app)
```

- The backend never exposes Hermes to browsers. Users talk to Django; Django talks to the runner over the internal network with `RUNNER_SHARED_SECRET`.
- Hermes receives no database credentials. Its only secrets are the LLM provider key and, per run, one capability token in the environment of that process.
- Identity propagation: Hermes has no per-request identity mechanism (MCP headers are static per `config.yaml`). Each investigation therefore gets its own Hermes process with its own generated `config.yaml` whose MCP header reads the token from `${KNOWLEDGE_MCP_TOKEN}`. The MCP server resolves the verified principal from the token hash (`investigations.CapabilityToken`), then enters the organization scope. Model arguments never carry identity.
- Memory: `memory.memory_enabled: false`, `memory.user_profile_enabled: false`; the per-run `HERMES_HOME` (including `state.db`) is erased when the process exits; the runner reconciles orphans at startup with a pgid + process start time + boot id identity check.
- **Per-run gateway (verified in the image, 2026-10-15):** in v0.22.1 `hermes chat -q` runs "through the canonical gateway, never AIAgent" (`hermes_cli/gateway_chat.py`). The CLI auto-starts a detached gateway process for the `HERMES_HOME` (own process group, `gateway run --quiet --idle-exit`, control socket `<home>/gateway.sock`, pid in `<home>/gateway.pid` as JSON with `pid`, `start_time`, `hermes_home`). It is not in the chat process group, so the runner stops it explicitly at run end and at startup reconciliation: `hermes gateway stop` with the run's `HERMES_HOME` (prints `✓ Stopped gateway for this profile`), then SIGTERM/SIGKILL of any gateway whose pid file, environment or cwd names that home. The generated config also sets `gateway.unmanaged_idle_exit_seconds: 60` so a missed stop exits on its own.
- Tool restriction: `platform_toolsets.cli: [mcp-knowledge]` plus `--toolsets mcp-knowledge` on the command line. The runner's configuration attestation (`hermes/runner/attestation.py`) runs the pinned invocation against a self-check MCP server before any run and refuses runs when a non-knowledge tool appears or the bearer did not arrive.

## Generated per-run `config.yaml`

```yaml
model:
  default: anthropic/claude-opus-5     # HERMES_MODEL
  provider: anthropic                  # HERMES_PROVIDER
agent:
  max_turns: 12
  max_tool_calls: 20
  disabled_toolsets: [terminal, file, browser, web, search, x_search, vision, image_gen, video_gen, tts, skills, todo, memory, session_search, cronjob, code_execution, delegation, clarify, messaging, discord, discord_admin, debugging, kanban, safe]
memory:
  memory_enabled: false
  user_profile_enabled: false
approvals:
  mode: manual
  single_query_mode: deny
gateway:
  unmanaged_idle_exit_seconds: 60
platform_toolsets:
  cli: [mcp-knowledge]
mcp_servers:
  knowledge:
    url: http://knowledge-mcp:8710/mcp
    headers:
      Authorization: "Bearer ${KNOWLEDGE_MCP_TOKEN}"
    timeout: 60
    connect_timeout: 20
    tools:
      resources: false
      prompts: false
```

The investigator instructions (`investigations/prompts/investigator.md`) are written as `AGENTS.md` in the run directory, which is the process cwd. Hermes loads `AGENTS.md` from the cwd chain (`agent/prompt_builder.py::_agents_md_candidates`) and scans it for injection patterns before use.

## Invocation

```
hermes chat -q "<question>" --toolsets mcp-knowledge --max-turns <N> --format stream-json
```

Verified in the pinned source (`hermes_cli/_parser.py`, `hermes_cli/stream_json.py`, `hermes_cli/cli_single_query.py`):

- `-q` on a non-TTY runs one turn and exits; `--format stream-json` implies quiet and emits one JSON object per line: `system` (init), `text` deltas, `tool_use` (`name`, `input`, `tool_call_id`), `tool_result` (`name`, `output` capped at 5,000 chars, `duration_ms`, `is_error`), then one `result` (`exit_code`, `text`, `tokens`, `duration_ms`, optional `error`).
- Exit codes: `0` completed, `1` failed (including "credentials or agent init failed"), `2` misuse (for example `--format stream-json` without `-q`), `130` interrupted.
- `--ignore-user-config` is **not** used: it ignores `config.yaml`, which would drop the MCP server. `--safe-mode` is not used: it disables MCP servers. `--ignore-rules` is not used: it skips `AGENTS.md`.
- MCP `headers` values support `${VAR}` interpolation (`tools/mcp_tool_config.py::_interpolate_env_vars`); unset variables keep the literal placeholder, so the runner always sets `KNOWLEDGE_MCP_TOKEN`.
- `platform_toolsets.<platform>` is the toolset allow-list per platform (`hermes_cli/config.py`); the CLI platform key is `cli`. `agent.disabled_toolsets` is a global suppression list applied last (`hermes_cli/tools_config.py`).
- **Unknown toolset fails closed:** when the MCP server is unreachable, the `mcp-knowledge` toolset never registers and the gateway refuses the session with `Error: invalid_params` (exit 1). With the self-check MCP server reachable and a fake provider key, the session is created, the MCP handshake carries the interpolated bearer (`auth_ok: true` on the self-check server) and the run fails only at the model call ("Anthropic rejected your API key"). Verified in the image on 2026-10-15.
- **Attestation is behavioral.** `hermes-agent --list-tools` prints the whole registry regardless of `--enabled-toolsets` (verified), so it is not an enabled inventory. The attestation runs a benign prompt (knowledge tool must be called, bearer must arrive) and an adversarial prompt (terminal, read_file, web_search requested; zero non-knowledge `tool_use` events allowed).

## Spike results (run inside the built image, 2026-10-15, no provider key)

| check | exit | detail |
|---|---|---|
| hermes --version | 0 | Hermes Agent vunknown (2026.9.24) Install directory: /opt/hermes Install method: docker Python: 3.14.7 OpenAI SDK: 2.24.0 |
| chat --help flags present | 0 | `--toolsets`, `--max-turns`, `--format`, `-q`, `--oneshot`, `--ignore-user-config` all present |
| config get memory.memory_enabled (per-run HERMES_HOME honored) | 0 | `false` (read from the generated config in the run directory) |
| chat -q --format stream-json without provider key | 1 | event types `['system', 'result']`; stderr ends with `Error: credentials or agent init failed` |
| attestation against self-check MCP (live model) | skipped | `ANTHROPIC_API_KEY` not set in this session |

Not verified in this session (needs a provider key): a full run with tool calls through the MCP server, the exact `tool_use` names Hermes reports for MCP tools (expected `mcp_knowledge_search_knowledge`), and the attestation. The runner refuses runs until the attestation passes, so a deployment without a key, or with a model configuration Hermes rejects, fails closed with HTTP 503 from `POST /runs`.

## Running it

```
make hermes-build          # builds hermes-base:v0.22.1 from the tag, then the service image with the runner
docker compose --profile hermes up -d hermes-agent
make hermes-spike          # prints the contract table above
```

Environment (see `.env.example`): `HERMES_MODEL`, `HERMES_PROVIDER`, `HERMES_PROVIDER_API_KEY_ENV` (name of the variable that holds the provider key, default `ANTHROPIC_API_KEY`), `RUNNER_SHARED_SECRET`, `RUNNER_MAX_CONCURRENT`, `KNOWLEDGE_MCP_URL`. The runner listens on 8700 inside the compose network only.

## Runner API (internal)

| Method | Path | Purpose |
|---|---|---|
| POST | `/runs` | create the run record (idempotent on `run_key`); refused with 503 until attestation passed |
| POST | `/runs/{run_key}/start` | start the process (idempotent) |
| GET | `/runs/{run_key}` | state and terminal record |
| GET | `/runs/{run_key}/events?after=<seq>&wait_s=<s>` | JSONL events with sequence numbers |
| POST | `/runs/{run_key}/cancel` | SIGINT the process group, SIGKILL after `RUNNER_KILL_GRACE_S` |
| DELETE | `/runs/{run_key}` | acknowledge: erase the terminal record and files (409 while active) |
| GET | `/health`, `/health/attestation` | liveness; last attestation result |

## Troubleshooting

- `POST /runs` returns 503 `configuration attestation failed`: read `GET /health/attestation`. Common causes: no provider key in the container, a model string Hermes does not accept, the MCP URL unreachable from the container.
- Investigation ends `failed` with `provider_failure`: the `result` event carried an error; the worker retried once with a rotated token. Check the runner log and the provider quota.
- Investigation ends `interrupted`: the worker lost its heartbeat past the deadline (worker restart); the reaper revoked the token.
- Tool calls return `not_ready`: the worker committed `running` after the process started; the agent retries. If it persists, the runner `/start` handshake failed.
- `unauthorized` from a tool: token expired, revoked (cancel, offboarding, terminal state) or the membership ended.
