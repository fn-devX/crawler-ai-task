"""The knowledge graph, stored in SQLite.

The tables:
    people(id, canonical_name, title_or_affiliation, mention_count)
    aliases(person_id, alias)            -- the names each person appears under
    edges(id, source_id, target_id, rel_type, explanation)
    edge_evidence(edge_id, article_url, article_title, sentence)
    articles(url, title, source, published_at)   -- for provenance / idempotency

The whole point is to avoid duplicates:
* people are de-duplicated by entity resolution (see resolution.py);
* an edge is unique on (source_id, target_id, rel_type), so the same
  relationship turning up again just adds another evidence row;
* re-ingesting the same article doesn't double-count, since evidence rows are
  unique on (edge_id, article_url, sentence).
"""
from __future__ import annotations

import sqlite3
from contextlib import closing

from .models import (
    ArticleExtraction,
    Article,
    Person,
    Relationship,
    RelationshipEvidence,
)
from .resolution import CanonicalIndex, normalize_rel_type

_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    title_or_affiliation TEXT,
    mention_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aliases (
    person_id INTEGER NOT NULL REFERENCES people(id),
    alias TEXT NOT NULL,
    UNIQUE(person_id, alias)
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES people(id),
    target_id INTEGER NOT NULL REFERENCES people(id),
    rel_type TEXT NOT NULL,
    explanation TEXT NOT NULL,
    UNIQUE(source_id, target_id, rel_type)
);
CREATE TABLE IF NOT EXISTS edge_evidence (
    edge_id INTEGER NOT NULL REFERENCES edges(id),
    article_url TEXT NOT NULL,
    article_title TEXT NOT NULL,
    sentence TEXT NOT NULL,
    UNIQUE(edge_id, article_url, sentence)
);
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    published_at TEXT
);
"""


class GraphStore:
    def __init__(self, db_path: str = "newskg.db"):
        # We pass check_same_thread=False because FastAPI runs sync endpoints in
        # a threadpool, so this connection gets touched from threads other than
        # the one that created it. The GIL plus short transactions keep that safe
        # here; anything heavier would want a connection pool or a real graph DB.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- ingestion ---
    def merge_article(self, article: Article, extraction: ArticleExtraction) -> dict:
        """Fold one article's extraction into the graph. Returns a little summary
        of counts that's handy for API responses and logging."""
        self._record_article(article)
        index = self._load_index()

        # Step 1: resolve or create each person, and remember which id every
        # name resolved to so we can wire up the edges next.
        name_to_id: dict[str, int] = {}
        new_people = 0
        for person in extraction.people:
            pid = index.resolve(person.name, person.aliases)
            if pid is None:
                pid = self._insert_person(person.name, person.title_or_affiliation)
                index.add(pid, person.name, person.aliases)
                new_people += 1
            self._add_aliases(pid, [person.name, *person.aliases])
            self._bump_mention(pid)
            for form in [person.name, *person.aliases]:
                name_to_id[form] = pid

        # Step 2: add the edges, keeping their evidence.
        new_edges = 0
        for rel in extraction.relationships:
            sid = name_to_id.get(rel.source) or index.resolve(rel.source)
            tid = name_to_id.get(rel.target) or index.resolve(rel.target)
            if sid is None or tid is None or sid == tid:
                # Drop self-loops and edges whose endpoints we couldn't resolve.
                continue
            created = self._upsert_edge(
                sid, tid, normalize_rel_type(rel.rel_type), rel.explanation,
                article.url, article.title, rel.evidence,
            )
            new_edges += int(created)

        self._conn.commit()
        return {
            "article": article.url,
            "people_in_article": len(extraction.people),
            "new_people": new_people,
            "relationships_in_article": len(extraction.relationships),
            "new_edges": new_edges,
        }

    # --- queries (this is what the API reads from) ---
    def list_people(self, limit: int, offset: int) -> tuple[list[Person], int]:
        total = self._conn.execute("SELECT COUNT(*) AS c FROM people").fetchone()["c"]
        rows = self._conn.execute(
            "SELECT * FROM people ORDER BY mention_count DESC, id ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._person_from_row(r) for r in rows], total

    def get_person(self, person_id: int) -> Person | None:
        row = self._conn.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
        return self._person_from_row(row) if row else None

    def get_relationships(self, person_id: int) -> list[Relationship]:
        rows = self._conn.execute(
            """SELECT e.*, ps.canonical_name AS source_name, pt.canonical_name AS target_name
               FROM edges e
               JOIN people ps ON ps.id = e.source_id
               JOIN people pt ON pt.id = e.target_id
               WHERE e.source_id=? OR e.target_id=?
               ORDER BY e.id""",
            (person_id, person_id),
        ).fetchall()
        out: list[Relationship] = []
        for r in rows:
            ev = self._conn.execute(
                "SELECT article_url, article_title, sentence FROM edge_evidence WHERE edge_id=?",
                (r["id"],),
            ).fetchall()
            out.append(
                Relationship(
                    id=r["id"],
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    source_name=r["source_name"],
                    target_name=r["target_name"],
                    rel_type=r["rel_type"],
                    explanation=r["explanation"],
                    evidence=[
                        RelationshipEvidence(
                            article_url=e["article_url"],
                            article_title=e["article_title"],
                            sentence=e["sentence"],
                        )
                        for e in ev
                    ],
                )
            )
        return out

    def stats(self) -> dict:
        c = self._conn
        return {
            "people": c.execute("SELECT COUNT(*) AS c FROM people").fetchone()["c"],
            "edges": c.execute("SELECT COUNT(*) AS c FROM edges").fetchone()["c"],
            "articles": c.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"],
        }

    # --- internal helpers ---
    def _load_index(self) -> CanonicalIndex:
        rows = self._conn.execute("SELECT id, canonical_name FROM people").fetchall()
        people = []
        for r in rows:
            aliases = [
                a["alias"]
                for a in self._conn.execute(
                    "SELECT alias FROM aliases WHERE person_id=?", (r["id"],)
                ).fetchall()
            ]
            people.append({"id": r["id"], "canonical_name": r["canonical_name"], "aliases": aliases})
        return CanonicalIndex.from_people(people)

    def _record_article(self, article: Article) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO articles(url, title, source, published_at) VALUES (?,?,?,?)",
            (
                article.url,
                article.title,
                article.source,
                article.published_at.isoformat() if article.published_at else None,
            ),
        )

    def _insert_person(self, name: str, title: str | None) -> int:
        cur = self._conn.execute(
            "INSERT INTO people(canonical_name, title_or_affiliation) VALUES (?,?)",
            (name, title),
        )
        return cur.lastrowid

    def _add_aliases(self, person_id: int, aliases: list[str]) -> None:
        for a in {a.strip() for a in aliases if a and a.strip()}:
            self._conn.execute(
                "INSERT OR IGNORE INTO aliases(person_id, alias) VALUES (?,?)", (person_id, a)
            )

    def _bump_mention(self, person_id: int) -> None:
        self._conn.execute(
            "UPDATE people SET mention_count = mention_count + 1 WHERE id=?", (person_id,)
        )

    def _upsert_edge(
        self, sid, tid, rel_type, explanation, url, title, sentence
    ) -> bool:
        row = self._conn.execute(
            "SELECT id FROM edges WHERE source_id=? AND target_id=? AND rel_type=?",
            (sid, tid, rel_type),
        ).fetchone()
        created = False
        if row:
            edge_id = row["id"]
        else:
            cur = self._conn.execute(
                "INSERT INTO edges(source_id, target_id, rel_type, explanation) VALUES (?,?,?,?)",
                (sid, tid, rel_type, explanation),
            )
            edge_id = cur.lastrowid
            created = True
        if sentence:
            self._conn.execute(
                "INSERT OR IGNORE INTO edge_evidence(edge_id, article_url, article_title, sentence)"
                " VALUES (?,?,?,?)",
                (edge_id, url, title, sentence),
            )
        return created

    def _person_from_row(self, row) -> Person:
        aliases = [
            a["alias"]
            for a in self._conn.execute(
                "SELECT alias FROM aliases WHERE person_id=?", (row["id"],)
            ).fetchall()
        ]
        return Person(
            id=row["id"],
            canonical_name=row["canonical_name"],
            aliases=sorted(set(aliases)),
            title_or_affiliation=row["title_or_affiliation"],
            mention_count=row["mention_count"],
        )
