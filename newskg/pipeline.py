"""Wires the steps together: fetch -> parse -> extract -> resolve -> store.

This is the one place that knows about all the layers, which is what keeps the
API (and any CLI) thin. Extraction is the slow bit, so we push it onto a thread
to avoid blocking the event loop while it runs.
"""
from __future__ import annotations

import asyncio

from .config import Config
from .crawler import Crawler
from .extraction import Extractor, build_extractor
from .sources import source_for_url
from .sources.registry import get_source
from .store import GraphStore


class Pipeline:
    def __init__(self, config: Config, store: GraphStore, extractor: Extractor | None = None):
        self._config = config
        self._store = store
        self._extractor = extractor or build_extractor(config)

    async def ingest_article(self, url: str) -> dict:
        source = source_for_url(url)
        async with Crawler(self._config) as crawler:
            html = await crawler.fetch(url)
        article = source.parse_article(html, url)
        extraction = await asyncio.to_thread(self._extractor.extract, article)
        return self._store.merge_article(article, extraction)

    async def rescan(self, pages: int = 2, source_name: str = "techcrunch") -> dict:
        source = get_source(source_name)
        article_urls: list[str] = []
        async with Crawler(self._config) as crawler:
            for page in range(1, pages + 1):
                listing_html = await crawler.fetch(source.listing_url(page))
                article_urls.extend(source.parse_listing(listing_html))
            # drop duplicate URLs but keep the order we found them in
            article_urls = list(dict.fromkeys(article_urls))

            results = []
            for url in article_urls:
                try:
                    html = await crawler.fetch(url)
                    article = source.parse_article(html, url)
                    extraction = await asyncio.to_thread(self._extractor.extract, article)
                    results.append(self._store.merge_article(article, extraction))
                except Exception as exc:
                    # Don't let a single broken article kill the whole scan;
                    # record what went wrong and move on to the next one.
                    results.append({"article": url, "error": str(exc)})
        return {
            "pages_scanned": pages,
            "articles_found": len(article_urls),
            "articles_ingested": sum(1 for r in results if "error" not in r),
            "errors": [r for r in results if "error" in r],
            "graph": self._store.stats(),
        }
