"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq
import re
from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # Replace this with your implementation
    listings = load_listings()


    # Turn the user's description into lowercase keywords.
    query_words = set(
        re.findall(r"[a-z0-9]+", description.lower())
    )

    scored_listings = []

    for listing in listings:
        # Filter by maximum price when provided.
        if (
            max_price is not None
            and listing["price"] > max_price
        ):
            continue

        # Filter by size when provided.
        if size is not None:
            requested_size = size.strip().lower()
            listing_size = listing["size"].strip().lower()

            # Allows "M" to match a listing size such as "S/M".
            available_sizes = [
                part.strip()
                for part in listing_size.split("/")
            ]

            if (
                requested_size != listing_size
                and requested_size not in available_sizes
            ):
                continue

        # Combine the searchable listing fields into one string.
        searchable_text = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand") or "",
            listing.get("platform", ""),
        ]).lower()

        listing_words = set(
            re.findall(r"[a-z0-9]+", searchable_text)
        )

        # Score based on how many query words appear in the listing.
        score = len(query_words & listing_words)

        # Do not include unrelated listings.
        if score > 0:
            scored_listings.append((score, listing))

    # Highest keyword score first.
    # Lower price breaks ties and keeps results deterministic.
    scored_listings.sort(
        key=lambda result: (-result[0], result[1]["price"])
    )

    # Return only the listing dictionaries, up to three results.
    return [
        listing
        for score, listing in scored_listings[:3]
    ]
# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Replace this with your implementation
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.
    """
    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = f"""
You are a personal stylist.

The user is considering buying this item:

{new_item}

The user's wardrobe is empty.

Suggest 1 or 2 general outfit ideas for this item. Explain what types of
tops, bottoms, shoes, outerwear, or accessories would pair well with it.

Do not claim that the user already owns any of the suggested pieces.
Clearly explain that these are general styling ideas.
"""
    else:
        wardrobe_text = "\n".join(
            f"- {item['name']} | "
            f"Category: {item['category']} | "
            f"Colors: {', '.join(item['colors'])} | "
            f"Style: {', '.join(item['style_tags'])} | "
            f"Notes: {item.get('notes') or 'None'}"
            for item in wardrobe_items
        )

        prompt = f"""
You are a personal stylist.

The user is considering buying this item:

{new_item}

The user already owns these clothes:

{wardrobe_text}

Suggest 1 or 2 complete outfits using the new item and named pieces from
the wardrobe.

Requirements:
- Include the new item in every outfit.
- Use only wardrobe pieces listed above.
- Refer to wardrobe pieces by their names.
- Explain how to wear the pieces together.
- Describe the style or vibe.
- If the wardrobe has limited options, create the best outfit possible
  and explain that the choices are limited.
"""

    try:
        client = _get_groq_client()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.7,
        )
        outfit_suggestion = response.choices[0].message.content
        if not outfit_suggestion or not outfit_suggestion.strip():
            return "The styling service did not return an outfit suggestion."

        return outfit_suggestion.strip()

    except Exception as error:
        return f"Unable to generate an outfit suggestion: {error}"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Replace this with your implementation

    # Do not call the LLM if there is no valid outfit.
    if not outfit or not outfit.strip():
        return (
            "Unable to create a fit card because a complete outfit "
            "suggestion is required."
        )

    item_title = new_item.get("title", "thrifted item")
    item_price = new_item.get("price")
    item_platform = new_item.get("platform")

    price_text = (
        f"${item_price}"
        if item_price is not None
        else "an unknown price"
    )

    platform_text = (
        item_platform
        if item_platform
        else "a secondhand platform"
    )

    prompt = f"""
You are writing a short social-media caption for an outfit post.

Thrifted item:
- Item name: {item_title}
- Price: {price_text}
- Platform: {platform_text}

Complete outfit:
{outfit}

Write a 2–4 sentence Instagram or TikTok caption.

Requirements:
- Sound casual and authentic, like a real OOTD post.
- Do not sound like a product advertisement.
- Mention the item name once.
- Mention the price once.
- Mention the platform once.
- Describe the specific style or vibe of the outfit.
- Keep it short and shareable.
"""

    try:
        client = _get_groq_client()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.9,
        )

        caption = response.choices[0].message.content

        if not caption or not caption.strip():
            return "The caption generator did not return a fit card."

        return caption.strip()

    except Exception as error:
        return f"Unable to create the fit card: {error}"

