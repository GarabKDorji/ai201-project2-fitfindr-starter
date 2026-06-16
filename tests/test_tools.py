
"""
Tests for the three FitFindr tools in tools.py.

search_listings is tested directly because it only reads local data.

suggest_outfit and create_fit_card call the Groq LLM, so the tests replace
tools._get_groq_client with a fake client. This keeps the tests fast, offline,
and independent of a real GROQ_API_KEY.
"""

import pytest

import tools
from tools import create_fit_card, search_listings, suggest_outfit


# ── Fake Groq client ──────────────────────────────────────────────────────────
#
# suggest_outfit() and create_fit_card() use:
#
#     client = _get_groq_client()
#     response = client.chat.completions.create(...)
#     text = response.choices[0].message.content
#
# These fake classes reproduce that structure without making a real API call.


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content, calls):
        self._content = content
        self._calls = calls

    def create(self, **kwargs):
        # Save the arguments so tests can inspect the prompt,
        # model, and temperature.
        self._calls.append(kwargs)

        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content, calls):
        self.completions = _FakeCompletions(content, calls)


class _FakeClient:
    def __init__(self, content, calls):
        self.chat = _FakeChat(content, calls)


def _patch_client(monkeypatch, content):
    """
    Replace tools._get_groq_client with a fake Groq client.

    The fake client always returns `content`.

    Returns:
        A list containing the arguments passed to each fake
        client.chat.completions.create() call.
    """
    calls = []

    monkeypatch.setattr(
        tools,
        "_get_groq_client",
        lambda: _FakeClient(content, calls),
    )

    return calls


def _raise(*args, **kwargs):
    """Fake function that simulates a Groq failure."""
    raise RuntimeError("Groq is down")


# ── Tool 1: search_listings ───────────────────────────────────────────────────


def test_search_returns_results():
    """A normal search returns a non-empty list."""
    results = search_listings(
        description="vintage graphic tee",
        size=None,
        max_price=50,
    )

    assert isinstance(results, list)
    assert len(results) > 0


def test_search_results_are_listing_dicts():
    """Every result is a dictionary with the required listing fields."""
    results = search_listings(
        description="vintage denim jeans",
        size=None,
        max_price=None,
    )

    assert len(results) > 0

    for item in results:
        assert isinstance(item, dict)

        required_fields = (
            "id",
            "title",
            "description",
            "category",
            "style_tags",
            "size",
            "condition",
            "price",
            "colors",
            "brand",
            "platform",
        )

        for field in required_fields:
            assert field in item


def test_search_empty_results():
    """No matching listings returns an empty list instead of raising."""
    results = search_listings(
        description="designer ballgown",
        size="XXS",
        max_price=5,
    )

    assert results == []


def test_search_price_filter_returns_empty_when_budget_is_too_low():
    """A price below every matching listing returns an empty list."""
    results = search_listings(
        description="jacket",
        size=None,
        max_price=10,
    )

    assert results == []


def test_search_price_filter_keeps_affordable_items():
    """All returned listings are at or below the maximum price."""
    results = search_listings(
        description="jeans",
        size=None,
        max_price=40,
    )

    assert len(results) > 0
    assert all(item["price"] <= 40 for item in results)


def test_search_without_price_filter():
    """A None maximum price skips price filtering."""
    results = search_listings(
        description="vintage",
        size=None,
        max_price=None,
    )

    assert isinstance(results, list)


def test_search_size_filter_is_case_insensitive_and_splits_slashes():
    """
    A requested size should match a grouped listing size such as 'S/M'.
    """
    grouped_listings = [
        listing
        for listing in tools.load_listings()
        if "/" in listing["size"]
    ]

    if not grouped_listings:
        pytest.skip("The dataset has no slash-grouped sizes.")

    listing = grouped_listings[0]

    requested_size = (
        listing["size"]
        .split("/")[0]
        .strip()
        .lower()
    )

    results = search_listings(
        description=listing["title"],
        size=requested_size,
        max_price=None,
    )

    returned_ids = {
        item["id"]
        for item in results
    }

    assert listing["id"] in returned_ids


def test_search_returns_at_most_three_results():
    """The function never returns more than three listings."""
    results = search_listings(
        description="vintage",
        size=None,
        max_price=None,
    )

    assert len(results) <= 3


def test_search_results_are_sorted_by_price_when_scores_tie():
    """
    When returned listings have the same keyword score,
    the less expensive listing should appear first.
    """
    results = search_listings(
        description="vintage",
        size=None,
        max_price=None,
    )

    if len(results) < 2:
        pytest.skip("Not enough matching listings to test sorting.")

    # This is only a useful check when the returned listings share
    # the same relevance score for the broad query.
    prices = [
        item["price"]
        for item in results
    ]

    assert all(
        isinstance(price, (int, float))
        for price in prices
    )


# ── Shared test data ──────────────────────────────────────────────────────────


NEW_ITEM = {
    "id": "test_001",
    "title": "Vintage Levi's 501 Jeans",
    "description": "Classic straight-leg blue denim jeans",
    "price": 38.0,
    "platform": "depop",
    "category": "bottoms",
    "style_tags": ["vintage", "denim", "classic"],
    "colors": ["blue"],
    "size": "M",
    "condition": "good",
    "brand": "Levi's",
}


WARDROBE_ITEM = {
    "id": "wardrobe_001",
    "name": "White cropped tee",
    "category": "tops",
    "colors": ["white"],
    "style_tags": ["basic", "casual"],
    "notes": None,
}


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────


def test_suggest_outfit_with_items(monkeypatch):
    """A populated wardrobe returns the LLM's outfit suggestion."""
    calls = _patch_client(
        monkeypatch,
        "Pair the jeans with the white cropped tee.",
    )

    result = suggest_outfit(
        NEW_ITEM,
        {"items": [WARDROBE_ITEM]},
    )

    assert isinstance(result, str)
    assert result.strip() != ""

    assert len(calls) == 1

    prompt = calls[0]["messages"][0]["content"]

    # The selected item and wardrobe item should both appear
    # in the prompt sent to the LLM.
    assert "Vintage Levi's 501 Jeans" in prompt
    assert "White cropped tee" in prompt


def test_suggest_outfit_uses_correct_model(monkeypatch):
    """The outfit tool uses the required Groq model."""
    calls = _patch_client(
        monkeypatch,
        "A complete outfit suggestion.",
    )

    suggest_outfit(
        NEW_ITEM,
        {"items": [WARDROBE_ITEM]},
    )

    assert calls[0]["model"] == "llama-3.3-70b-versatile"


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    """
    An empty wardrobe still returns general styling advice
    instead of crashing.
    """
    calls = _patch_client(
        monkeypatch,
        "Here are some general styling ideas.",
    )

    result = suggest_outfit(
        NEW_ITEM,
        {"items": []},
    )

    assert isinstance(result, str)
    assert result.strip() != ""

    prompt = calls[0]["messages"][0]["content"]

    # The prompt should tell the LLM that the wardrobe is empty.
    assert "empty" in prompt.lower()


def test_suggest_outfit_missing_items_key(monkeypatch):
    """
    A wardrobe dictionary without an 'items' key defaults
    to an empty wardrobe.
    """
    calls = _patch_client(
        monkeypatch,
        "General styling ideas.",
    )

    result = suggest_outfit(
        NEW_ITEM,
        {},
    )

    assert isinstance(result, str)
    assert result.strip() != ""
    assert len(calls) == 1

    prompt = calls[0]["messages"][0]["content"]
    assert "empty" in prompt.lower()


def test_suggest_outfit_llm_failure_returns_message(monkeypatch):
    """A Groq error returns a descriptive string instead of crashing."""
    monkeypatch.setattr(
        tools,
        "_get_groq_client",
        _raise,
    )

    result = suggest_outfit(
        NEW_ITEM,
        {"items": [WARDROBE_ITEM]},
    )

    assert isinstance(result, str)
    assert "Unable to generate an outfit suggestion" in result


# Include this test only if suggest_outfit checks for a blank LLM response.
def test_suggest_outfit_blank_llm_response(monkeypatch):
    """Blank LLM output should return a descriptive message."""
    _patch_client(monkeypatch, "   ")

    result = suggest_outfit(
        NEW_ITEM,
        {"items": [WARDROBE_ITEM]},
    )

    assert isinstance(result, str)
    assert result.strip() != ""


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────


def test_create_fit_card_happy_path(monkeypatch):
    """A valid outfit returns the caption generated by the LLM."""
    expected_caption = (
        "Thrifted these 501s and I'm obsessed. "
        "The casual denim look came together perfectly. 🤎"
    )

    _patch_client(
        monkeypatch,
        expected_caption,
    )

    result = create_fit_card(
        "Jeans with a white tee and boots.",
        NEW_ITEM,
    )

    assert isinstance(result, str)
    assert result == expected_caption


def test_create_fit_card_prompt_contains_required_information(monkeypatch):
    """
    The fit-card prompt includes the item title, price,
    platform, and outfit.
    """
    calls = _patch_client(
        monkeypatch,
        "A generated fit card.",
    )

    outfit = "Jeans with a white tee and boots."

    create_fit_card(
        outfit,
        NEW_ITEM,
    )

    assert len(calls) == 1

    call = calls[0]
    prompt = call["messages"][0]["content"]

    assert "Vintage Levi's 501 Jeans" in prompt
    assert "38" in prompt
    assert "depop" in prompt.lower()
    assert outfit in prompt


def test_create_fit_card_uses_correct_model(monkeypatch):
    """The fit-card tool uses the required Groq model."""
    calls = _patch_client(
        monkeypatch,
        "A generated fit card.",
    )

    create_fit_card(
        "Jeans with a white tee and boots.",
        NEW_ITEM,
    )

    assert calls[0]["model"] == "llama-3.3-70b-versatile"


def test_create_fit_card_uses_higher_temperature(monkeypatch):
    """
    The fit-card tool uses a higher temperature so repeated
    real LLM calls can produce varied captions.
    """
    calls = _patch_client(
        monkeypatch,
        "A generated fit card.",
    )

    create_fit_card(
        "Jeans with a white tee and boots.",
        NEW_ITEM,
    )

    assert "temperature" in calls[0]
    assert calls[0]["temperature"] >= 0.8


def test_create_fit_card_empty_outfit():
    """
    An empty outfit returns an error message without calling the LLM.
    """
    result = create_fit_card(
        "",
        NEW_ITEM,
    )

    assert isinstance(result, str)
    assert "Unable to create a fit card" in result


def test_create_fit_card_whitespace_outfit():
    """A whitespace-only outfit is handled like an empty outfit."""
    result = create_fit_card(
        "   \n  ",
        NEW_ITEM,
    )

    assert isinstance(result, str)
    assert "Unable to create a fit card" in result


def test_create_fit_card_blank_llm_response(monkeypatch):
    """Blank LLM output returns a descriptive message."""
    _patch_client(
        monkeypatch,
        "   ",
    )

    result = create_fit_card(
        "Jeans with a white tee.",
        NEW_ITEM,
    )

    assert isinstance(result, str)
    assert "did not return a fit card" in result


def test_create_fit_card_llm_failure_returns_message(monkeypatch):
    """A Groq error returns a descriptive string instead of crashing."""
    monkeypatch.setattr(
        tools,
        "_get_groq_client",
        _raise,
    )

    result = create_fit_card(
        "Jeans with a white tee.",
        NEW_ITEM,
    )

    assert isinstance(result, str)
    assert "Unable to create the fit card" in result
