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
    qr.supported = sum(1 for c in answer.claims if claim_supported(c["text"], evidence_texts))
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
        "numbers describe the keyword path only; vector metrics need `EMBEDDER=openai`. The support check is a word-overlap proxy "
        "unless `EVAL_JUDGE` names a provider. Deep (agent) queries are evaluated through the FakeRunner in the test suite "
        "(`investigations/tests/test_lifecycle.py::test_end_to_end_three_documents_with_chunk_level_citations`); live Hermes "
        "numbers appear here only when the `hermes` marker tests ran.",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def run_all(principal) -> tuple[list[QueryResult], Path]:
    rows = [run_quick(principal, q) for q in load_golden()]
    meta = {
        "embedder": settings.EMBEDDER,
        "llm": settings.LLM_PROVIDER,
        "documents": "7",
        "judge": "word-overlap proxy",
    }
    return rows, write_report(rows, meta)
