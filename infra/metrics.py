"""Prometheus metrics. Names follow PLAN.md. Served at /metrics with a bearer
token on the internal network."""

from prometheus_client import Counter, Gauge, Histogram

investigation_attempts_total = Counter(
    "investigation_attempts_total", "Investigation attempts started"
)
investigation_terminal_total = Counter(
    "investigation_terminal_total", "Investigations that reached a terminal state", ["status"]
)
investigation_duration_seconds = Histogram(
    "investigation_duration_seconds", "Wall clock per investigation",
    buckets=(5, 15, 30, 60, 120, 180, 300, 600),
)
tool_calls_used = Histogram(
    "tool_calls_used", "MCP tool calls per investigation", buckets=(1, 2, 5, 10, 20, 50)
)
output_chars_used = Histogram(
    "output_chars_used", "MCP output characters per investigation",
    buckets=(1000, 5000, 20000, 60000, 120000),
)
runner_orphans_reaped_total = Counter(
    "runner_orphans_reaped_total", "Runner orphans reaped at startup"
)
access_denied_total = Counter("access_denied_total", "Denied access checks", ["path"])
grant_revalidation_age_seconds = Gauge(
    "grant_revalidation_age_seconds", "Oldest valid grant per organization", ["organization"]
)
reconcile_overdue_scopes = Gauge("reconcile_overdue_scopes", "Scopes past the reconcile interval")
sync_checkpoint_seq = Gauge("sync_checkpoint_seq", "Last durable inbox seq per scope", ["scope"])
inbox_pending = Gauge("inbox_pending", "Pending inbox rows")
purge_completed_total = Counter("purge_completed_total", "Version purges completed")
lease_lost_total = Counter("lease_lost_total", "Sync writes skipped because the lease was lost")
