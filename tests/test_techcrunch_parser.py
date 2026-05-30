from newskg.sources import TechCrunchSource

src = TechCrunchSource()


def test_listing_extracts_unique_article_urls(listing_html):
    urls = src.parse_listing(listing_html)
    assert urls == [
        "https://techcrunch.com/2026/02/27/musk-bashes-openai-in-deposition-saying-nobody-committed-suicide-because-of-grok/",
        "https://techcrunch.com/2026/02/28/openais-sam-altman-announces-pentagon-deal-with-technical-safeguards/",
    ]
    # nav, page/2, and event links must be excluded
    assert all("/events/" not in u and "/page/" not in u for u in urls)


def test_listing_url_paging():
    assert src.listing_url(1).endswith("/tag/openai/")
    assert src.listing_url(2).endswith("/tag/openai/page/2/")


def test_parse_article_metadata_and_body(article_html):
    art = src.parse_article(article_html, "https://techcrunch.com/2026/02/27/musk-bashes-openai/?utm=x")
    assert art.title == "Musk bashes OpenAI in deposition"  # | TechCrunch stripped
    assert art.authors == ["Sarah Perez"]
    assert art.published_at.year == 2026 and art.published_at.month == 2
    assert "Elon Musk" in art.tags and "OpenAI" in art.tags  # proper-cased from sailthru.tags
    assert "?utm=x" not in art.url  # query stripped
    # body keeps real paragraphs, drops share links + affiliate boilerplate
    assert "deposition filed" in art.body
    assert "small commission" not in art.body
    assert "twitter.com" not in art.body
