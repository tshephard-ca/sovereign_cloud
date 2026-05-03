"""Primary analysis pipeline entry points.

The legacy ``lint_rules`` module remains as a compatibility facade for tests
and downstream users. New code should import the pipeline from here.
"""

from __future__ import annotations

from .lint_rules import AnalysisResult, analyze_inputs

__all__ = ["AnalysisResult", "analyze_inputs"]
