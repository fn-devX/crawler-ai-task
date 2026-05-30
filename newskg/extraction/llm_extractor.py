"""Extractor that calls Claude.

We force a tool call so the model hands back well-shaped JSON instead of prose
we'd have to parse. The prompt asks it to list every person who actually
matters in the article (authors included), with the different names they show
up under, which is what entity resolution later keys off of, and to return
directed, typed edges between people only, each carrying a short explanation and
a verbatim quote we keep as evidence.

We run this one article at a time rather than over the whole corpus. That keeps
the prompt small and the evidence unambiguous, and leaves cross-article merging
to the resolver where it belongs.
"""
from __future__ import annotations

import json

from ..config import Config
from ..models import Article, ArticleExtraction

_SYSTEM = """You build knowledge graphs of PEOPLE from news articles.
Extract only real, named human individuals -- never companies, products, or models.
Include the article's author(s) as people with role "author".

For relationships:
- Only between two people you also listed.
- Directed: source performs the relation on target.
- rel_type is a short snake_case verb phrase (e.g. criticizes, partners_with,
  sues, succeeds, reports_on, accuses, praises, works_with).
- explanation: one neutral sentence.
- evidence: a VERBATIM sentence or quote from the article. Do not paraphrase.
Only assert a relationship the text actually supports. Prefer precision over recall."""

_TOOL = {
    "name": "emit_graph",
    "description": "Return the people and directed relationships found in the article.",
    "input_schema": {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "role": {"type": "string", "enum": ["author", "subject"]},
                        "title_or_affiliation": {"type": "string"},
                    },
                    "required": ["name", "role"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "rel_type": {"type": "string"},
                        "explanation": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["source", "target", "rel_type", "explanation", "evidence"],
                },
            },
        },
        "required": ["people", "relationships"],
    },
}


class AnthropicExtractor:
    def __init__(self, config: Config):
        if not config.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set; use NEWSKG_EXTRACTOR=heuristic.")
        import anthropic

        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self._model = config.model

    def extract(self, article: Article) -> ArticleExtraction:
        authors = ", ".join(article.authors) or "unknown"
        user = (
            f"ARTICLE TITLE: {article.title}\n"
            f"AUTHOR(S): {authors}\n"
            f"TOPIC TAGS: {', '.join(article.tags)}\n\n"
            f"BODY:\n{article.body}"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "emit_graph"},
            messages=[{"role": "user", "content": user}],
        )
        payload = _coerce_payload(_first_tool_input(resp))
        return ArticleExtraction.model_validate(payload)


def _coerce_payload(payload: dict) -> dict:
    # Normally the model returns people/relationships as real JSON arrays. Now
    # and then (usually on longer articles) it hands one of them back as a JSON
    # string instead, which would fail pydantic validation. So if we see a
    # string, parse it; if that doesn't work, fall back to an empty list rather
    # than dropping the whole article.
    for key in ("people", "relationships"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                payload[key] = json.loads(value)
            except json.JSONDecodeError:
                payload[key] = []
    return payload


def _first_tool_input(resp) -> dict:
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    # Shouldn't happen with a forced tool, but if the model answered with plain
    # text anyway, try to read JSON out of it instead of crashing.
    text = "".join(getattr(b, "text", "") for b in resp.content)
    return json.loads(text or '{"people": [], "relationships": []}')
