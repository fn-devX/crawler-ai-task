"""App settings. Everything is read from env vars (or a local .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

# Load .env if python-dotenv is around. It's only a convenience for local dev,
# so don't blow up if it isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    model: str = os.getenv("NEWSKG_MODEL", "claude-sonnet-4-6")
    db_path: str = os.getenv("NEWSKG_DB", "newskg.db")
    extractor: str = os.getenv("NEWSKG_EXTRACTOR", "llm")  # "llm" or "heuristic"
    crawl_delay: float = float(os.getenv("NEWSKG_CRAWL_DELAY", "1.0"))
    user_agent: str = os.getenv(
        "NEWSKG_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )


def get_config() -> Config:
    return Config()
