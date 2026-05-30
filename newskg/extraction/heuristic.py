"""An extractor that uses no LLM at all.

It has no way to tell what a relationship actually means, so it sticks to what
it can be sure of: the author(s) are people, and each author gets a
"reports_on" edge to anyone named in the article's topic tags. We keep it
around for two reasons: it's the fallback when there's no API key, and it gives
the tests and the eval a cheap baseline to measure the real extractor against
(the LLM should always beat it on recall).
"""
from __future__ import annotations

import re

from ..models import (
    Article,
    ArticleExtraction,
    ExtractedPerson,
    ExtractedRelationship,
)

# Matches a capitalised "Firstname Lastname" (maybe a middle name too). Rough,
# but tags are short and clean enough that it does the job.
_NAME_RE = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z]+){1,2}$")


class HeuristicExtractor:
    def extract(self, article: Article) -> ArticleExtraction:
        people: list[ExtractedPerson] = []
        rels: list[ExtractedRelationship] = []

        for author in article.authors:
            people.append(ExtractedPerson(name=author, role="author"))

        tag_people = [t for t in article.tags if _NAME_RE.match(t)]
        for person in tag_people:
            people.append(ExtractedPerson(name=person, role="subject"))
            for author in article.authors:
                rels.append(
                    ExtractedRelationship(
                        source=author,
                        target=person,
                        rel_type="reports_on",
                        explanation=f"{author} authored an article discussing {person}.",
                        evidence=article.title,
                    )
                )
        return ArticleExtraction(people=people, relationships=rels)
