"""A small name -> source registry, so the pipeline never has to know about
specific websites."""
from __future__ import annotations

from .base import NewsSource

_REGISTRY: dict[str, NewsSource] = {}


def register_source(source: NewsSource) -> None:
    _REGISTRY[source.name] = source


def get_source(name: str) -> NewsSource:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"No registered source named {name!r}. Known: {list(_REGISTRY)}")


def source_for_url(url: str) -> NewsSource:
    for source in _REGISTRY.values():
        if source.matches(url):
            return source
    raise ValueError(f"No registered source can handle URL: {url}")


# Register built-in sources on import.
from .techcrunch import TechCrunchSource  # noqa: E402

register_source(TechCrunchSource())
