from __future__ import annotations

import csv

from brownout_policy_compiler.action_model import CSV_COLUMNS
from brownout_policy_compiler.compile_rules import compile_from_paths


def test_actions_csv_has_exact_column_order(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    assert result.plan.actions
    with open(compile_options_factory().output_actions, newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
    assert header == CSV_COLUMNS

