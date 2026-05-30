from .base import Extractor
from .heuristic import HeuristicExtractor

__all__ = ["Extractor", "HeuristicExtractor", "build_extractor"]


def build_extractor(config) -> Extractor:
    """Pick the extractor named in the config.

    The anthropic import is deferred to the LLM path on purpose, so tests and
    the heuristic path don't need the SDK installed.
    """
    if config.extractor == "heuristic":
        return HeuristicExtractor()
    from .llm_extractor import AnthropicExtractor

    return AnthropicExtractor(config)
