"""Tests for the HTTP API. The network and the LLM are both stubbed out: a fake
crawler serves the fixture HTML and the heuristic extractor does the work, so
the whole POST -> store -> GET path runs offline."""
import pathlib

import pytest
from fastapi.testclient import TestClient

import newskg.api as api
import newskg.pipeline as pipeline_mod
from newskg.extraction import HeuristicExtractor
from newskg.store import GraphStore

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class _FakeCrawler:
    def __init__(self, *a, **k):
        self._article = (FIXTURES / "article.html").read_text(encoding="utf-8")
        self._listing = (FIXTURES / "listing.html").read_text(encoding="utf-8")

    async def fetch(self, url, **k):
        return self._listing if "/tag/" in url else self._article

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    api._store = GraphStore(str(tmp_path / "api.db"))
    monkeypatch.setattr(pipeline_mod, "Crawler", _FakeCrawler)
    # Override the FastAPI dependency so the endpoints use the heuristic
    # extractor (no API key, no network). dependency_overrides is the right hook
    # here; monkeypatching the function itself wouldn't reach routes that are
    # already bound.
    api.app.dependency_overrides[api.get_pipeline] = (
        lambda: pipeline_mod.Pipeline(api._config, api._store, HeuristicExtractor())
    )
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_post_article_then_list_and_detail(client):
    r = client.post("/articles", json={"url": "https://techcrunch.com/2026/02/27/x/"})
    assert r.status_code == 200

    people = client.get("/people?limit=10&offset=0").json()
    assert people["total"] >= 1
    assert {"total", "limit", "offset", "items"} <= people.keys()  # paginated shape

    pid = people["items"][0]["id"]
    detail = client.get(f"/people/{pid}").json()
    assert detail["person"]["id"] == pid
    assert "relationships" in detail


def test_post_rescan(client):
    r = client.post("/rescan", json={"pages": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["pages_scanned"] == 2
    assert body["articles_found"] >= 1


def test_unknown_person_404(client):
    assert client.get("/people/9999").status_code == 404


def test_unsupported_url_400(client):
    r = client.post("/articles", json={"url": "https://example.com/foo"})
    assert r.status_code == 400
