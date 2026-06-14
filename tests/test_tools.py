"""
Tests for the three FitFindr tools.

Run from the project root with:  pytest tests/

Each tool has at least one test for its normal behavior and one for its
failure mode, so we can re-run them all with a single command after any change.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    # Normal query: a common item should return a non-empty list.
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches -> empty list, NOT an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    # Every returned item must respect the price ceiling.
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# ── suggest_outfit (these make a live Groq call) ────────────────────────────────

def test_suggest_returns_string():
    # Normal case: with a real wardrobe, returns a non-empty suggestion string.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


def test_suggest_empty_wardrobe():
    # Failure mode: an empty wardrobe is handled gracefully (general advice),
    # NOT a crash or an empty string.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


# ── create_fit_card ─────────────────────────────────────────────────────────────

def test_fit_card_empty_outfit():
    # Failure mode: an empty/whitespace outfit returns a descriptive error
    # string WITHOUT calling the LLM — and never raises an exception.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    assert create_fit_card("", item) == "Can't create a fit card without an outfit suggestion."
    assert create_fit_card("   ", item) == "Can't create a fit card without an outfit suggestion."


def test_fit_card_returns_string():
    # Normal case (live Groq call): a real outfit yields a non-empty caption.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = suggest_outfit(item, get_example_wardrobe())
    caption = create_fit_card(outfit, item)
    assert isinstance(caption, str)
    assert len(caption) > 0
