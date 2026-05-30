from newskg.models import (
    Article,
    ArticleExtraction,
    ExtractedPerson,
    ExtractedRelationship,
)
from newskg.store import GraphStore


def _article(url="https://techcrunch.com/2026/02/27/a/"):
    return Article(url=url, title="Test", body="body", authors=["Sarah Perez"])


def _extraction():
    return ArticleExtraction(
        people=[
            ExtractedPerson(name="Sam Altman", aliases=["Altman", "OpenAI's CEO"], role="subject"),
            ExtractedPerson(name="Elon Musk", aliases=["Musk"], role="subject"),
        ],
        relationships=[
            ExtractedRelationship(
                source="Elon Musk", target="Sam Altman", rel_type="sues",
                explanation="Musk sued Altman.", evidence="Musk's case against OpenAI.",
            )
        ],
    )


def test_merge_creates_people_and_edges(tmp_path):
    store = GraphStore(str(tmp_path / "t.db"))
    summary = store.merge_article(_article(), _extraction())
    assert summary["new_people"] == 2
    assert summary["new_edges"] == 1
    people, total = store.list_people(limit=10, offset=0)
    assert total == 2


def test_alias_resolution_prevents_duplicate_people(tmp_path):
    store = GraphStore(str(tmp_path / "t.db"))
    store.merge_article(_article(), _extraction())
    # Second article refers to "Altman" only -> must resolve to existing person.
    ext2 = ArticleExtraction(
        people=[ExtractedPerson(name="Altman", role="subject")],
        relationships=[],
    )
    store.merge_article(_article("https://techcrunch.com/2026/02/28/b/"), ext2)
    _, total = store.list_people(limit=10, offset=0)
    assert total == 2  # no new person created for "Altman"


def test_repeated_edge_adds_evidence_not_duplicate(tmp_path):
    store = GraphStore(str(tmp_path / "t.db"))
    store.merge_article(_article(), _extraction())
    # Same edge, different article -> one edge, two evidence rows.
    store.merge_article(_article("https://techcrunch.com/2026/03/01/c/"), _extraction())
    musk = [p for p in store.list_people(10, 0)[0] if p.canonical_name == "Elon Musk"][0]
    rels = store.get_relationships(musk.id)
    sues = [r for r in rels if r.rel_type == "sues"]
    assert len(sues) == 1
    assert len(sues[0].evidence) == 2


def test_pagination(tmp_path):
    store = GraphStore(str(tmp_path / "t.db"))
    store.merge_article(_article(), _extraction())
    page1, total = store.list_people(limit=1, offset=0)
    page2, _ = store.list_people(limit=1, offset=1)
    assert total == 2 and len(page1) == 1 and page1[0].id != page2[0].id
