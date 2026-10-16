#!/usr/bin/env bash
# Start the whole development stack with the demo organization and Deep
# Investigation on. Stop everything with Ctrl-C. Logs go to .run/.
#
#   scripts/dev-up.sh            start, then wait (Ctrl-C stops all)
#   scripts/dev-up.sh --stop     stop background processes and the agent container
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_DIR=.run
mkdir -p "$RUN_DIR"
WEB_PORT="${WEB_PORT:-8010}"  # 8000 and 8001 are often taken by other local projects

stop_all() {
  echo "stopping..."
  for name in web beat worker mcp; do
    if [[ -f "$RUN_DIR/$name.pid" ]]; then
      kill "$(cat "$RUN_DIR/$name.pid")" 2>/dev/null || true
      rm -f "$RUN_DIR/$name.pid"
    fi
  done
  docker compose --profile hermes stop hermes-agent >/dev/null 2>&1 || true
  echo "stopped (postgres and redis keep running; 'make down' stops them)"
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_all
  exit 0
fi

[[ -f .env ]] || { echo ".env is missing: copy .env.example and set the keys"; exit 1; }
grep -qE '^ANTHROPIC_API_KEY=.+' .env || echo "warning: ANTHROPIC_API_KEY is empty; the agent attestation will fail and Deep Investigation stays closed"

# Deep Investigation on for this session; the runner is reached from the host.
export HERMES_ENABLED=True
export RUNNER_URL=http://127.0.0.1:8700

echo "1/6 postgres and redis"
docker compose up -d postgres redis >/dev/null
for _ in $(seq 1 30); do
  if docker compose ps --format '{{.Health}}' postgres | grep -q healthy; then break; fi
  sleep 1
done

echo "2/6 migrations, demo data, css"
make -s migrate >/dev/null
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py tailwind build >/dev/null 2>&1 || echo "warning: tailwind build failed; pages render without styles"

echo "3/6 knowledge MCP server :8710"
nohup .venv/bin/python manage.py run_mcp_server --host 0.0.0.0 --port 8710 >"$RUN_DIR/mcp.log" 2>&1 &
echo $! >"$RUN_DIR/mcp.pid"

echo "4/6 hermes-agent container (attestation runs at start)"
docker compose --profile hermes up -d hermes-agent >/dev/null
for _ in $(seq 1 60); do
  if docker logs kb-hermes-agent 2>&1 | grep -q '"event": "runner.attestation"'; then break; fi
  sleep 3
done
docker logs kb-hermes-agent 2>&1 | grep '"event": "runner.attestation"' | tail -n 1 | cut -c1-200 || echo "warning: no attestation line yet; see docker logs kb-hermes-agent"

echo "5/6 celery worker"
# threads pool: on macOS the default prefork pool spawned children that consumed
# tasks without running them (observed 2026-10-16); Linux containers keep prefork.
nohup .venv/bin/celery -A knowledgebase worker -l INFO --pool=threads --concurrency=4 >"$RUN_DIR/worker.log" 2>&1 &
echo $! >"$RUN_DIR/worker.pid"

echo "5b/6 celery beat (periodic syncs, reaper, sweeps)"
nohup .venv/bin/celery -A knowledgebase beat -l INFO >"$RUN_DIR/beat.log" 2>&1 &
echo $! >"$RUN_DIR/beat.pid"

echo "6/6 web server :$WEB_PORT"
if lsof -nP -iTCP:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "error: port $WEB_PORT is in use; run WEB_PORT=<other> scripts/dev-up.sh"; stop_all; exit 1; fi
nohup .venv/bin/python manage.py runserver 127.0.0.1:"$WEB_PORT" >"$RUN_DIR/web.log" 2>&1 &
echo $! >"$RUN_DIR/web.pid"

cat <<MSG

Ready.
  Web UI:        http://127.0.0.1:$WEB_PORT/o/demo/
  Login:         member@demo.invalid / steward@demo.invalid / admin@demo.invalid
  Password:      demo-passphrase-change-me   (seed_demo --password to change)
  Runner:        http://127.0.0.1:8700/health
  MCP server:    http://127.0.0.1:8710/healthz
  Logs:          $RUN_DIR/web.log  $RUN_DIR/worker.log  $RUN_DIR/mcp.log  docker logs -f kb-hermes-agent

Press Ctrl-C to stop everything.
MSG

trap stop_all INT TERM
while :; do sleep 3600; done
