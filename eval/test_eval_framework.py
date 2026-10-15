"""The evaluation framework runs end to end on the synthetic corpus with the
mock embedder and the stub composer, and the keyword path meets the CI floor."""

import pytest
from django.core.management import call_command

from eval.metrics import claim_supported, mrr, precision_at_k, recall_at_k
from eval.runner import load_golden


def test_metric_functions():
    assert recall_at_k(["a", "b"], ["a", "c"], 5) == 0.5
    assert precision_at_k(["a", "b"], ["a"], 2) == 0.5
    assert mrr(["x", "a"], ["a"]) == 0.5 and mrr([], ["a"]) == 0.0 and mrr(["a"], []) is None
    assert claim_supported(
        "Employees accrue fifteen vacation days each year.",
        ["Vacation policy\nEmployees accrue fifteen vacation days each year."],
    )
    assert not claim_supported(
        "The CEO approved it personally.", ["Employees accrue fifteen vacation days each year."]
    )


@pytest.mark.django_db(transaction=True)
def test_run_eval_meets_keyword_floor(tmp_path, monkeypatch):
    import eval.runner as runner

    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    call_command("run_eval", org="eval-test")
    report = next(tmp_path.glob("*.md")).read_text()
    assert "Mean recall@5" in report
    rows = {}
    for line in report.splitlines():
        if line.startswith("| ") and not line.startswith("| query"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0]] = cells
    answerable = [q for q in load_golden() if q["relevant"]]
    recalls = [float(rows[q["id"]][2]) for q in answerable]
    assert sum(recalls) / len(recalls) >= 0.8, recalls
    assert rows["unanswerable"][5] == "insufficient"
    assert "quick" in rows["vacation-days"][1]
