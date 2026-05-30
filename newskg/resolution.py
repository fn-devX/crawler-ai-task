"""Deciding when two messy names refer to the same person.

This is kept simple on purpose. It only needs to be right for a couple of pages
of articles, and stay easy to read. The logic:

1. Normalize the name (lowercase, drop punctuation/possessives and honorifics).
2. Try to match it against people we already know, in this order:
   a. exact match on the normalized full name,
   b. exact match on a normalized alias,
   c. if the incoming name is a single token, match it on last name (so
      "Altman" finds an existing "Sam Altman"), but only when that last name
      points to exactly one known person.
3. If nothing matches, it's a new person.

Descriptive forms like "OpenAI's CEO" are just kept as aliases on whoever the
extractor attached them to. We don't try to resolve them structurally; that
would mean guessing, and this is good enough here.

The resolver doesn't touch the database. It works off a small CanonicalIndex
that the store builds from what's already stored, which keeps the merge logic
unit-testable on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "sir"}
_POSSESSIVE = re.compile(r"['’]s\b")
_NONWORD = re.compile(r"[^a-z0-9\s]")


def normalize(name: str) -> str:
    s = name.strip().lower()
    s = _POSSESSIVE.sub("", s)
    s = _NONWORD.sub(" ", s)
    tokens = [t for t in s.split() if t and t not in _HONORIFICS]
    return " ".join(tokens)


@dataclass
class _Known:
    id: int
    canonical_name: str
    norm_full: str
    norm_aliases: set[str] = field(default_factory=set)

    @property
    def last_name(self) -> str:
        return self.norm_full.split()[-1] if self.norm_full else ""


@dataclass
class CanonicalIndex:
    """An in-memory snapshot of the people we already know, used to match new
    mentions against."""

    _people: list[_Known] = field(default_factory=list)

    @classmethod
    def from_people(cls, rows: list[dict]) -> "CanonicalIndex":
        idx = cls()
        for r in rows:
            idx._people.append(
                _Known(
                    id=r["id"],
                    canonical_name=r["canonical_name"],
                    norm_full=normalize(r["canonical_name"]),
                    norm_aliases={normalize(a) for a in r.get("aliases", [])},
                )
            )
        return idx

    def resolve(self, name: str, aliases: list[str] | None = None) -> int | None:
        """Id of the person this name matches, or None if we've never seen them."""
        forms = [name] + list(aliases or [])
        norm_forms = {normalize(f) for f in forms if normalize(f)}

        # First pass: an exact hit on a full name or a known alias.
        for nf in norm_forms:
            for k in self._people:
                if nf == k.norm_full or nf in k.norm_aliases:
                    return k.id

        # Second pass: a lone token is probably a last name. Only accept it if
        # exactly one known person has that surname, otherwise it's ambiguous.
        for nf in norm_forms:
            if " " in nf:
                continue
            matches = [k for k in self._people if k.last_name == nf]
            if len(matches) == 1:
                return matches[0].id
        return None

    def add(self, person_id: int, canonical_name: str, aliases: list[str]) -> None:
        self._people.append(
            _Known(
                id=person_id,
                canonical_name=canonical_name,
                norm_full=normalize(canonical_name),
                norm_aliases={normalize(a) for a in aliases},
            )
        )


def normalize_rel_type(rel_type: str) -> str:
    """Normalise an edge label so 'partners with' and 'partners_with' match."""
    s = rel_type.strip().lower()
    s = _NONWORD.sub(" ", s)
    return "_".join(s.split())
