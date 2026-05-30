
---

## How it works

```
                        topic listing + article pages
                                    │
   ┌───────────┐      ┌──────────────┐     ┌────────────────┐     ┌────────────┐
   │  Crawler  │────> │    Source    │────>│   Extractor    │────>│   Store    │
   │ async I/O │      │  TechCrunch  │     │  Claude tool-  │     │  SQLite    │
   │  + retry  │      │    parser    │     │  use  /  LLM   │     │   graph    │
   └───────────┘      └──────────────┘     └────────────────┘     └─────┬──────┘
                                                                        │
                              fetch → parse → extract → resolve → store │
                                                                        ▼
                                                                  ┌────────────┐
                                                                  │  FastAPI   │
                                                                  │    API     │
                                                                  └────────────┘
```

Five stages run end to end: **crawl** the pages, **parse** them into clean articles,
**extract** people and relationships with the LLM, **resolve** duplicate names into one
entity, then **store and serve** the graph. Each layer talks to the next through a small
interface, so sources, extractors, and storage are all swappable.

---

## Run it

```bash
# Python 3.10+
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env          # then set ANTHROPIC_API_KEY
# no key? run fully offline:  export NEWSKG_EXTRACTOR=heuristic

uvicorn newskg.api:app --reload
```

Then open **http://localhost:8000/docs** — the interactive Swagger UI documents every
endpoint, with request/response shapes and examples. (ReDoc is at `/redoc`.)

---

## Test it

```bash
pytest
```

Tests run fully offline — no network and no API key required — and cover entity
resolution, the store's merge/dedup logic, the TechCrunch parser, the API, and the
evaluation metrics.




# P.S. 
# good joke with apple :)