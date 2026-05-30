"""Fetches pages over HTTP, with retries and a polite delay between requests.

It's deliberately small and kept apart from the parsing code, so the sources
stay pure (HTML in, data out) and can be tested without ever hitting the network.
"""
from __future__ import annotations

import asyncio

import httpx

from .config import Config


class Crawler:
    def __init__(self, config: Config):
        self._config = config
        self._client = httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=20.0,
            follow_redirects=True,
        )

    async def fetch(self, url: str, *, retries: int = 3) -> str:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                await asyncio.sleep(self._config.crawl_delay)
                return resp.text
            except (httpx.HTTPError,) as exc:  # connection trouble or a 4xx/5xx
                last_exc = exc
                # back off a little longer on each retry
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "Crawler":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
