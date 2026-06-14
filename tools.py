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
import re

from dotenv import load_dotenv
from groq import Groq

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
    # 1. Load every listing from the dataset (don't re-read the file ourselves).
    listings = load_listings()

    # Turn the search text into a set of lowercase keywords, e.g.
    # "Vintage Graphic Tee" -> {"vintage", "graphic", "tee"}.
    # Using a set means each keyword is counted at most once.
    keywords = set(description.lower().split())

    matches = []
    for item in listings:
        # 2a. Price filter: skip anything above the ceiling (if one was given).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2b. Size filter: split the listing's size into whole tokens and keep
        # the item only if the requested size matches one exactly. This avoids
        # over-matching (e.g. "L" should NOT match "XL (oversized)" or "W30 L30").
        if size is not None:
            size_tokens = re.split(r"[^a-z0-9]+", item["size"].lower())
            if size.lower() not in size_tokens:
                continue

        # 3. Relevance score: count how many distinct keywords show up anywhere
        # in the title, description, or style tags (all lowercased).
        haystack = (
            item["title"]
            + " "
            + item["description"]
            + " "
            + " ".join(item["style_tags"])
        ).lower()
        score = sum(1 for kw in keywords if kw in haystack)

        # 4. Drop listings that matched no keywords at all.
        if score > 0:
            matches.append((score, item))

    # 5. Sort by score, highest first, and return just the listing dicts.
    matches.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in matches]


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
    # A short, readable description of the thrifted find for the prompt.
    item_desc = (
        f"{new_item['title']} "
        f"(category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    # The persona/instructions stay the same whether or not there's a wardrobe.
    system_prompt = (
        "You are FitFindr, a sharp, friendly secondhand-fashion stylist. "
        "You suggest concise but complete, wearable outfits. Be specific and "
        "practical — name real pieces and how to wear them (tuck, layer, roll). "
        "Sound like a stylist friend, never like a product description."
    )

    # Branch on whether the user actually has a wardrobe. An empty wardrobe is
    # NOT an error — we fall back to general styling advice for the item alone.
    items = wardrobe.get("items", [])
    if not items:
        user_prompt = (
            f"The user is considering this secondhand find:\n{item_desc}\n\n"
            "They haven't entered any wardrobe items yet. Suggest ONE complete "
            "outfit idea describing the kinds of pieces (colors, silhouettes) "
            "that pair well with this find, then ONE short alternative tweak "
            "(one sentence). Keep it under ~5 sentences total. Briefly note that "
            "adding their wardrobe would let you tailor it to what they own."
        )
    else:
        # Format each wardrobe piece into a readable line for the prompt.
        wardrobe_lines = []
        for w in items:
            line = f"- {w['name']} ({w['category']}; {', '.join(w['style_tags'])})"
            if w.get("notes"):
                line += f" — {w['notes']}"
            wardrobe_lines.append(line)
        wardrobe_text = "\n".join(wardrobe_lines)

        user_prompt = (
            f"The user is considering this secondhand find:\n{item_desc}\n\n"
            f"Here is what they already own:\n{wardrobe_text}\n\n"
            "Suggest ONE complete outfit built around the find, naming specific "
            "pieces from their wardrobe by name. Then add ONE short alternative "
            "tweak (one sentence). Keep it under ~5 sentences total — concise, "
            "specific, and practical."
        )

    # Call the LLM, wrapped so an API/network error returns a safe string
    # instead of crashing the agent.
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=250,
        )
        suggestion = response.choices[0].message.content.strip()
        if not suggestion:
            return "Couldn't generate an outfit suggestion right now — try again."
        return suggestion
    except Exception as e:
        return f"Couldn't generate an outfit suggestion right now ({e})."


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
    # 1. Guard an empty / whitespace-only outfit BEFORE calling the LLM. There's
    # nothing to caption without an outfit, so return a clear message instead of
    # wasting an API call or crashing.
    if not outfit or not outfit.strip():
        return "Can't create a fit card without an outfit suggestion."

    # Pull the concrete details that make a caption feel real (mentioned once each).
    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "secondhand")

    # 2. Voice instructions: how an actual teen captions a fit in 2026 — casual,
    # confident, lowercase-leaning, NOT corny or hashtag-stuffed.
    system_prompt = (
        "You write outfit captions the way a stylish teen actually posts in 2026: "
        "short, casual, lowercase-leaning, and effortless. Sound genuinely cool — "
        "never corny, never like an ad or product description. No hashtag spam. "
        "Use an emoji only if it genuinely fits (zero or one is fine). Keep it to "
        "one or two short lines, like a real caption someone would post with a fit pic."
    )

    # ":g" drops a trailing ".0" so a $18.0 price reads as "$18" in the caption.
    price_str = f"${price:g}" if price is not None else ""
    user_prompt = (
        f"Write a caption for this thrifted fit.\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit / vibe: {outfit}\n\n"
        "Mention the item, the price, and where it's from naturally (once each). "
        "Capture the vibe in specific terms. Make it feel like a real post."
    )

    # 3. Call the LLM with a HIGHER temperature so the caption varies each run,
    # and wrap it so an error returns a safe string instead of crashing.
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.1,
            max_tokens=80,
        )
        caption = response.choices[0].message.content.strip()
        # The model occasionally wraps the whole caption in quotes — strip them
        # so the shareable text reads cleanly.
        caption = caption.strip('"').strip("'").strip()
        if not caption:
            return "Couldn't create a fit card right now — try again."
        return caption
    except Exception as e:
        return f"Couldn't create a fit card right now ({e})."
