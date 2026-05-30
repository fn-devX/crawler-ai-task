"""The extractor interface.

An extractor takes one Article and returns an ArticleExtraction (the people and
the directed relationships between them). Because the pipeline only ever talks
to this base class, switching LLM providers or dropping in a pure rule-based
version is just a matter of writing another subclass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Article, ArticleExtraction


class Extractor(ABC):
    @abstractmethod
    def extract(self, article: Article) -> ArticleExtraction:
        ...
