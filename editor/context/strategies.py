"""
Three context strategies — RQ2 controlled comparison.

Compared on the same edit chain to measure the degradation curve:
1. Full history: replay the full DSL history
2. Current only: current-state DSL only
3. Summarized: feature-tree summary + relevant subtree excerpt
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ContextStrategy(ABC):
    @abstractmethod
    def build(self, history: list[str], current_dsl: str) -> str:
        """Build the context fed to the model."""
        ...


class FullHistory(ContextStrategy):
    def build(self, history, current_dsl):
        # TODO(M8): concatenate full history
        raise NotImplementedError


class CurrentOnly(ContextStrategy):
    def build(self, history, current_dsl):
        return current_dsl


class SummarizedSubtree(ContextStrategy):
    def build(self, history, current_dsl):
        # TODO(M8): feature-tree summary + relevant subtree excerpt
        raise NotImplementedError
