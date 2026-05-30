"""Parser for TechCrunch.

Their HTML changes pretty often, so the strategy is to lean on whatever is most
stable, roughly in this order:

* Title, author, date and tags come from <meta> tags. TechCrunch runs on
  WordPress and emits steady article:*, parsely-* and sailthru meta, which
  survives redesigns far better than CSS class names do.
* The body comes from the post-content container (with a couple of class
  fallbacks), reduced down to its paragraph text.
* Article links are recognised by the /YYYY/MM/DD/slug/ permalink shape rather
  than a CSS class, which conveniently also skips nav and "most popular" noise.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from ..models import Article
from .base import NewsSource

# Canonical article permalink, e.g. /2026/02/27/some-slug/
_ARTICLE_RE = re.compile(r"^https?://techcrunch\.com/\d{4}/\d{2}/\d{2}/[^/]+/?$")
_BASE = "https://techcrunch.com"


class TechCrunchSource(NewsSource):
    name = "techcrunch"
    topic = "openai"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("techcrunch.com")

    def listing_url(self, page: int) -> str:
        if page <= 1:
            return f"{_BASE}/tag/{self.topic}/"
        return f"{_BASE}/tag/{self.topic}/page/{page}/"

    def parse_listing(self, html: str) -> list[str]:
        tree = HTMLParser(html)
        seen: dict[str, None] = {}  # ordered set
        for a in tree.css("a[href]"):
            href = a.attributes.get("href") or ""
            full = urljoin(_BASE, href).split("?")[0].split("#")[0]
            if _ARTICLE_RE.match(full):
                seen.setdefault(full, None)
        return list(seen)

    def parse_article(self, html: str, url: str) -> Article:
        tree = HTMLParser(html)
        meta = _meta_map(tree)

        title = (
            meta.get("og:title")
            or _text(tree.css_first("h1"))
            or ""
        ).replace(" | TechCrunch", "").strip()

        authors = self._authors(tree, meta)
        published = _parse_date(meta.get("article:published_time"))
        tags = self._tags(meta)
        body = self._body(tree)

        return Article(
            url=url.split("?")[0],
            title=title,
            body=body,
            authors=authors,
            published_at=published,
            source=self.name,
            tags=tags,
        )

    def _authors(self, tree: HTMLParser, meta: dict[str, str]) -> list[str]:
        authors: list[str] = []
        # First choice: /author/ links in the article header.
        for a in tree.css("a[href*='/author/']"):
            name = _text(a)
            if name and name not in authors and len(name.split()) <= 5:
                authors.append(name)
        # If there were none, fall back to the author meta fields.
        if not authors:
            for key in ("author", "parsely-author", "sailthru.author"):
                if meta.get(key):
                    authors.append(meta[key].strip())
                    break
        return authors

    def _tags(self, meta: dict[str, str]) -> list[str]:
        # Prefer sailthru.tags because it keeps the proper casing ("Elon Musk"),
        # which matters since tags seed the person hints. parsely-tags is
        # lowercased, so we only use it as a fallback.
        raw = meta.get("sailthru.tags") or meta.get("parsely-tags") or ""
        return [t.strip() for t in raw.split(",") if t.strip()]

    def _body(self, tree: HTMLParser) -> str:
        container = (
            tree.css_first("div.entry-content")
            or tree.css_first("div.wp-block-post-content")
            or tree.css_first("article")
        )
        if container is None:
            return ""
        parts: list[str] = []
        for p in container.css("p"):
            txt = _text(p)
            # Skip empty lines, bare links, and the affiliate disclaimer.
            if not txt or txt.startswith("http") or "earn a small commission" in txt:
                continue
            parts.append(txt)
        return "\n\n".join(parts).strip()


# --- small helpers ---

def _text(node) -> str:
    return node.text(strip=True) if node is not None else ""


def _meta_map(tree: HTMLParser) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in tree.css("meta"):
        key = m.attributes.get("property") or m.attributes.get("name")
        content = m.attributes.get("content")
        if key and content is not None:
            out[key] = content
    return out


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
