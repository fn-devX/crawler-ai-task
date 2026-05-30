import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing.html").read_text(encoding="utf-8")


@pytest.fixture
def article_html() -> str:
    return (FIXTURES / "article.html").read_text(encoding="utf-8")
