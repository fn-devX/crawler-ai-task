"""The data models that move through the pipeline.

The flow is: a source parser builds an Article, the extractor turns that into
ExtractedPerson / ExtractedRelationship objects, and the store resolves those
into canonical Person / Relationship records. We keep the raw extraction models
separate from the canonical graph ones on purpose, since that gap is exactly
where entity resolution happens.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- what a source parser gives us ---

class Article(BaseModel):
    """One parsed news article. Doesn't care which site it came from."""

    url: str
    title: str
    body: str
    authors: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    source: str = "techcrunch"
    # Topic tags scraped off the page, e.g. "Elon Musk", "OpenAI". We pass them
    # to the extractor as hints and lean on them in the eval as a recall signal.
    tags: list[str] = Field(default_factory=list)


# --- what the extractor gives us (per article, before resolution) ---

PersonRole = Literal["author", "subject"]


class ExtractedPerson(BaseModel):
    """A person mention as the extractor saw it in one article."""

    name: str = Field(description="Best full canonical-looking name, e.g. 'Sam Altman'")
    aliases: list[str] = Field(
        default_factory=list,
        description="Other surface forms in this article, e.g. ['Altman', \"OpenAI's CEO\"]",
    )
    role: PersonRole = "subject"
    title_or_affiliation: Optional[str] = Field(
        default=None, description="e.g. 'CEO of OpenAI' if stated"
    )


class ExtractedRelationship(BaseModel):
    """A directed, typed edge between two people in one article."""

    source: str = Field(description="Name of the subject person (matches an ExtractedPerson.name)")
    target: str = Field(description="Name of the object person")
    rel_type: str = Field(description="Short snake_case verb phrase, e.g. 'criticizes'")
    explanation: str = Field(description="One sentence describing the relationship")
    evidence: str = Field(description="Verbatim sentence/quote from the article justifying it")


class ArticleExtraction(BaseModel):
    """Everything the extractor pulled out of one article."""

    people: list[ExtractedPerson] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


# --- the canonical graph, i.e. what you read back out of the store ---

class Person(BaseModel):
    id: int
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    title_or_affiliation: Optional[str] = None
    mention_count: int = 0


class RelationshipEvidence(BaseModel):
    article_url: str
    article_title: str
    sentence: str


class Relationship(BaseModel):
    id: int
    source_id: int
    target_id: int
    source_name: str
    target_name: str
    rel_type: str
    explanation: str
    evidence: list[RelationshipEvidence] = Field(default_factory=list)
