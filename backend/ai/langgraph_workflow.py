"""
DEPRECATED - renamed to ai/batch_analysis.py.

This module never imported LangGraph despite its name and docstring;
it is a loop over database rows. Import from ai.batch_analysis instead.
"""

from ai.batch_analysis import (  # noqa: F401
    BatchAnalyzer, batch_analyzer, langgraph_pipeline,
)
