from newskg.resolution import CanonicalIndex, normalize, normalize_rel_type


def test_normalize_strips_possessive_and_honorifics():
    assert normalize("Mr. Altman's") == "altman"
    assert normalize("Sam Altman") == "sam altman"


def test_resolves_last_name_to_existing_full_name():
    idx = CanonicalIndex.from_people([{"id": 1, "canonical_name": "Sam Altman", "aliases": []}])
    assert idx.resolve("Altman") == 1
    assert idx.resolve("Sam Altman") == 1


def test_resolves_via_alias_and_possessive_description():
    idx = CanonicalIndex.from_people(
        [{"id": 7, "canonical_name": "Sam Altman", "aliases": ["OpenAI's CEO"]}]
    )
    assert idx.resolve("OpenAI's CEO") == 7


def test_ambiguous_last_name_is_not_merged():
    idx = CanonicalIndex.from_people(
        [
            {"id": 1, "canonical_name": "Logan Page", "aliases": []},
            {"id": 2, "canonical_name": "Larry Page", "aliases": []},
        ]
    )
    assert idx.resolve("Page") is None  # ambiguous -> new entity, no wrong merge


def test_unknown_person_returns_none():
    idx = CanonicalIndex.from_people([{"id": 1, "canonical_name": "Sam Altman", "aliases": []}])
    assert idx.resolve("Satya Nadella") is None


def test_rel_type_normalization():
    assert normalize_rel_type("partners with") == "partners_with"
    assert normalize_rel_type("Partners_With") == "partners_with"
