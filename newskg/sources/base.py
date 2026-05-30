"""Base class for a news source.

Supporting a new website means subclassing NewsSource and filling in a handful
of methods. Nothing else in the pipeline (crawler, extractor, resolver, store,
API) ever imports a concrete source directly; everything goes through the
registry. That's the seam that keeps adding outlets cheap.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Article


class NewsSource(ABC):
    # Short id for this source. It gets stored on every article and edge so we
    # always know where a fact came from.
    name: str

    @abstractmethod
    def matches(self, url: str) -> bool:
        """True if this source knows how to handle the given URL."""

    @abstractmethod
    def listing_url(self, page: int) -> str:
        """URL of the topic listing for a given (1-based) page number."""

    @abstractmethod
    def parse_listing(self, html: str) -> list[str]:
        """Pull the article URLs out of a listing page."""

    @abstractmethod
    def parse_article(self, html: str, url: str) -> Article:
        """Turn a single article page into an Article."""
