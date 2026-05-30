"""The FastAPI app that exposes the graph over HTTP.

The endpoints:
    POST /articles   {"url": "..."}                       ingest one article
    POST /rescan     {"pages": 2, "source": "techcrunch"} re-crawl a listing
    GET  /people?limit=&offset=                           paginated list of people
    GET  /people/{id}                                     a person + their edges
    GET  /stats                                           quick size of the graph

Run it with: uvicorn newskg.api:app --reload
Interactive docs live at /docs (Swagger UI) and /redoc.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .config import get_config
from .models import Person, Relationship
from .pipeline import Pipeline
from .store import GraphStore

# Shown at the top of the Swagger / ReDoc pages.
_DESCRIPTION = """
**Typical flow**

1. `POST /rescan` to crawl listing pages and build the graph (or `POST /articles`
   for a single URL).
2. `GET /people` to browse who's in the graph.
3. `GET /people/{id}` to see one person and everyone they're connected to.
"""

# Tags group the endpoints into sections in the docs.
_TAGS_METADATA = [
    {"name": "ingestion", "description": "Crawl the news and grow the graph."},
    {"name": "graph", "description": "Read people and their relationships."},
    {"name": "meta", "description": "Health and size of the graph."},
]

app = FastAPI(
    title="crawler",
    description=_DESCRIPTION,
    openapi_tags=_TAGS_METADATA,
)

_config = get_config()
_store = GraphStore(_config.db_path)


def get_pipeline() -> Pipeline:
    return Pipeline(_config, _store)


# --- request / response shapes ---

class ArticleRequest(BaseModel):
    url: str = Field(
        description="A TechCrunch article URL to ingest.",
        examples=["https://techcrunch.com/2026/02/27/musk-bashes-openai-in-deposition/"],
    )


class RescanRequest(BaseModel):
    pages: int = Field(
        default=2, ge=1, le=50,
        description="How many listing pages to crawl, starting from the first.",
    )
    source: str = Field(
        default="techcrunch",
        description="Registered source to crawl. Only 'techcrunch' ships by default.",
    )


class IngestSummary(BaseModel):
    """What changed in the graph after ingesting one article."""

    article: str
    people_in_article: int
    new_people: int
    relationships_in_article: int
    new_edges: int


class RescanSummary(BaseModel):
    """Outcome of a crawl across one or more listing pages."""

    pages_scanned: int
    articles_found: int
    articles_ingested: int
    errors: list[dict]
    graph: dict


class PersonListResponse(BaseModel):
    total: int = Field(description="Total people in the graph (ignores paging).")
    limit: int
    offset: int
    items: list[Person]


class PersonDetailResponse(BaseModel):
    person: Person
    relationships: list[Relationship]


class StatsResponse(BaseModel):
    people: int
    edges: int
    articles: int


# --- endpoints ---

@app.post(
    "/articles",
    response_model=IngestSummary,
    tags=["ingestion"],
    summary="Ingest a single article",
    description=(
        "Fetch one TechCrunch article, extract its people and relationships, and "
        "merge them into the graph. Returns a summary of what was added."
    ),
    responses={
        400: {"description": "No registered source can handle this URL."},
        502: {"description": "Fetching or extracting the article failed."},
    },
)
async def post_article(req: ArticleRequest, pipeline: Pipeline = Depends(get_pipeline)):
    try:
        return await pipeline.ingest_article(req.url)
    except ValueError as exc:  # we don't have a source for this URL
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {exc}")


@app.post(
    "/rescan",
    response_model=RescanSummary,
    tags=["ingestion"],
    summary="Crawl listing pages",
    description=(
        "Walk the first N listing pages of a source, ingest every article found, "
        "and fold them all into the graph. A single failing article is recorded in "
        "`errors` and does not abort the run."
    ),
    responses={400: {"description": "Unknown source name."}},
)
async def post_rescan(req: RescanRequest, pipeline: Pipeline = Depends(get_pipeline)):
    try:
        return await pipeline.rescan(pages=req.pages, source_name=req.source)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get(
    "/people",
    response_model=PersonListResponse,
    tags=["graph"],
    summary="List people",
    description="Browse the people in the graph, most-mentioned first.",
)
def get_people(
    limit: int = Query(default=50, ge=1, le=200, description="Max people to return."),
    offset: int = Query(default=0, ge=0, description="How many to skip (for paging)."),
):
    items, total = _store.list_people(limit=limit, offset=offset)
    return PersonListResponse(total=total, limit=limit, offset=offset, items=items)


@app.get(
    "/people/{person_id}",
    response_model=PersonDetailResponse,
    tags=["graph"],
    summary="Get one person",
    description=(
        "Return a single person together with every relationship they take part "
        "in, each backed by the source article and a verbatim evidence sentence."
    ),
    responses={404: {"description": "No person with that id."}},
)
def get_person(person_id: int = Path(description="Numeric id of the person.")):
    person = _store.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return PersonDetailResponse(
        person=person, relationships=_store.get_relationships(person_id)
    )


@app.get(
    "/stats",
    response_model=StatsResponse,
    tags=["meta"],
    summary="Graph size",
    description="Quick counts of people, edges, and articles currently in the graph.",
)
def get_stats():
    return _store.stats()
