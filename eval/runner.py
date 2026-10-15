"""Evaluation run over the synthetic corpus: ingest as a throwaway user, run
every golden query through Quick Search, measure retrieval and grounding, and
optionally run the deep queries through the FakeRunner investigation path.
Writes eval/results/<date>.md. No external provider is called unless
EMBEDDER/LLM_PROVIDER select one in the environment."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from django.conf import settings

from answers.api import answer_question
from infra.api import with_org
from retrieval.api import search

from .metrics import QueryResult, claim_supported, mrr, precision_at_k, recall_at_k

GOLDEN = Path(__file__).with_name("golden.yaml")
RESULTS = Path(__file__).with_name("results")


def load_golden() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text())["queries"]


def run_quick(principal, query: dict) -> QueryResult:
    started = time.monotonic()
    results = search(principal, query["question"], limit=10, mode="quick")
    retrieved = []
    for r in results:
        with with_org(principal.organization_id):
            from knowledge.api import Document

            sid = (
                Document.objects.filter(id=r.document_id)
                .values_list("source_id", flat=True)
                .first()
            )
        if sid and sid not in retrieved:
            retrieved.append(sid)
    relevant = list(query.get("relevant") or [])
    qr = QueryResult(
        id=query["id"],
        mode="quick",
        retrieved=retrieved,
        relevant=relevant,
        recall5=recall_at_k(retrieved, relevant, 5),
        precision5=precision_at_k(retrieved, relevant, 5),
        mrr=mrr(retrieved, relevant),
    )
    answer = answer_question(principal, query["question"])
    qr.evidence_state = answer.evidence_state
    qr.claims = len(answer.claims)
    qr.unsupported_listed = len(answer.unsupported)
    evidence_texts = [c.excerpt for c in answer.citations]
    qr.supported = sum(1 for c in answer.claims if _judge(c["text"], evidence_texts))
    terms = query.get("claim_terms") or []
    if terms:
        joined = " ".join(c["text"] for c in answer.claims).lower()
        qr.expected_terms_hit = all(t.lower() in joined for t in terms)
    if not relevant:
        qr.notes.append(
            "expected insufficient"
            + (" ✓" if answer.evidence_state == "insufficient" else " ✗ (answered anyway)")
        )
    qr.latency_ms = int((time.monotonic() - started) * 1000)
    return qr


def _judge(claim: str, evidence_texts: list[str]) -> bool:
    """LLM judge when EVAL_JUDGE=anthropic and a key exists; otherwise the proxy."""
    import os

    if os.environ.get("EVAL_JUDGE") == "anthropic" and settings.ANTHROPIC_API_KEY:
        import anthropic
        from pydantic import BaseModel

        class Verdict(BaseModel):
            supported: bool
            reason: str

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.parse(
            model="claude-opus-5",
            max_tokens=400,
            system="Judge whether the claim is fully supported by the evidence passages. Negations and numbers must agree.",
            messages=[
                {
                    "role": "user",
                    "content": f"Claim: {claim}\n\nEvidence:\n" + "\n---\n".join(evidence_texts),
                }
            ],
            output_format=Verdict,
        )
        return bool(response.parsed_output and response.parsed_output.supported)
    return claim_supported(claim, evidence_texts)


def write_report(rows: list[QueryResult], meta: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = RESULTS / f"{stamp}.md"
    lines = [
        f"# Evaluation {stamp}",
        "",
        f"Embedder: `{meta['embedder']}` · answer model: `{meta['llm']}` · corpus: {meta['documents']} synthetic documents · "
        f"support check: {meta['judge']}",
        "",
    ]
    lines += [
        "| query | mode | recall@5 | precision@5 | MRR | evidence state | claims | supported (proxy) | unsupported listed | expected terms | ms | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        f = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(
            f"| {r.id} | {r.mode} | {f(r.recall5)} | {f(r.precision5)} | {f(r.mrr)} | {r.evidence_state} | {r.claims} | {r.supported} | "
            f"{r.unsupported_listed} | {'n/a' if r.expected_terms_hit is None else ('yes' if r.expected_terms_hit else 'no')} | {r.latency_ms} | {'; '.join(r.notes)} |"
        )
    scored = [r for r in rows if r.recall5 is not None]
    if scored:
        lines += [
            "",
            f"Mean recall@5 {sum(r.recall5 for r in scored) / len(scored):.2f} · mean precision@5 {sum(r.precision5 for r in scored) / len(scored):.2f} · "
            f"mean MRR {sum(r.mrr for r in scored) / len(scored):.2f} over {len(scored)} answerable queries.",
        ]
    lines += [
        "",
        "Interpretation: with `EMBEDDER=mock` the vector leg carries no meaning and the keyword leg does the work, so these "
        "numbers describe the keyword path only; vector metrics need `EMBEDDER=openai`. The support check is a ordered-content-word proxy "
        "unless `EVAL_JUDGE=anthropic` and a key are set. Deep queries run through the real investigation lifecycle with the "
        "in-process FakeRunner driving the MCP tools (evidence coverage and citation validity of the agent path, no model); "
        "live Hermes numbers appear only when the `hermes` marker tests ran.",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def run_deep(principal, query: dict) -> QueryResult:
    """Deep golden queries run through the real investigation lifecycle with the
    in-process FakeRunner driving the MCP tools (no Hermes process): evidence
    coverage and citation validity of the agent path."""
    from infra.api import with_org
    from investigations import service
    from investigations import tasks as inv_tasks
    from investigations.api import FakeRunner, Investigation, start_investigation
    from knowledge.api import Document

    started = time.monotonic()
    words = [w for w in query["question"].replace("?", "").split() if len(w) > 4][:3]
    runner = FakeRunner("complete", queries=[query["question"], " ".join(words)], read_first=False)
    settings.HERMES_ENABLED = True
    original_delay = inv_tasks.run_investigation.delay
    inv_tasks.run_investigation.delay = lambda *a, **k: None
    try:
        inv = start_investigation(principal, query["question"])
        outcome = service.execute(principal.organization_id, inv.id, client=runner)
    finally:
        inv_tasks.run_investigation.delay = original_delay
    with with_org(principal.organization_id):
        row = Investigation.objects.get(id=inv.id)
        cited_docs: list[str] = []
        for c in (row.result or {}).get("citations", []):
            sid = (
                Document.objects.filter(id=c["document_id"])
                .values_list("source_id", flat=True)
                .first()
            )
            if sid and sid not in cited_docs:
                cited_docs.append(sid)
    relevant = list(query.get("relevant") or [])
    qr = QueryResult(
        id=query["id"],
        mode="deep",
        retrieved=cited_docs,
        relevant=relevant,
        recall5=recall_at_k(cited_docs, relevant, 5),
        precision5=precision_at_k(cited_docs, relevant, 5),
        mrr=mrr(cited_docs, relevant),
        evidence_state=outcome,
    )
    result = row.result or {}
    statements = result.get("statements", [])
    qr.claims = len(statements)
    # Grounding: each statement judged (proxy or configured judge) against the
    # passages it cites, not merely by the presence of evidence ids.
    cited_text = {c["evidence_id"]: c["excerpt"] for c in result.get("citations", [])}
    qr.supported = sum(
        1
        for st in statements
        if _judge(
            st["text"], [cited_text.get(e, "") for e in st["evidence_ids"] if e in cited_text]
        )
    )
    qr.unsupported_listed = len(result.get("unsupported_statements", []))
    terms = query.get("claim_terms") or []
    if terms:
        joined = " ".join(st["text"] for st in statements).lower()
        qr.expected_terms_hit = all(t.lower() in joined for t in terms)
    qr.notes.append(f"tool_calls={row.tool_calls_used}")
    qr.latency_ms = int((time.monotonic() - started) * 1000)
    return qr


def judge_name() -> str:
    import os

    judge = os.environ.get("EVAL_JUDGE", "")
    if judge == "anthropic" and settings.ANTHROPIC_API_KEY:
        return "anthropic LLM judge"
    return "ordered-content-word proxy" + (
        " (EVAL_JUDGE set but no key: judge not run)" if judge else ""
    )


def run_all(principal) -> tuple[list[QueryResult], Path]:
    rows = []
    for q in load_golden():
        rows.append(run_deep(principal, q) if q.get("mode") == "deep" else run_quick(principal, q))
    meta = {
        "embedder": settings.EMBEDDER,
        "llm": settings.LLM_PROVIDER,
        "documents": "7",
        "judge": judge_name(),
    }
    return rows, write_report(rows, meta)
