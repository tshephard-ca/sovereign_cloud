import json

from stateful_storage_fit.corpus import evaluate_corpus
from stateful_storage_fit.portfolio import analyze_portfolio


def test_evaluates_synthetic_corpus_examples():
    data = evaluate_corpus(__import__("pathlib").Path("examples/corpus"))
    assert data["case_count"] == 3
    assert data["decision_accuracy"] == 1.0
    assert not data["mismatches"]


def test_analyzes_portfolio_inventory():
    data = analyze_portfolio(__import__("pathlib").Path("examples/portfolio.yml"))
    assert data["workload_count"] == 3
    assert data["status_counts"]["PASS"] == 1
    assert data["status_counts"]["REVIEW"] == 2
    assert data["capability_demands"]["rwx"] == 1

