"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# Filler words to drop from the description — they never appear in listings, so
# removing them just keeps the search keywords clean.
_FILLER_WORDS = {
    "looking", "for", "a", "an", "the", "i", "im", "i'm", "want", "wanna",
    "need", "to", "find", "me", "some", "please", "searching", "search",
}


def _parse_query(query: str) -> dict:
    """
    Turn a natural-language query into search parameters using regex/string
    parsing (no LLM). Returns a dict with description, size, and max_price.

    Examples:
        "vintage graphic tee under $30, size M"
            -> {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
        "designer ballgown size XXS under $5"
            -> {"description": "designer ballgown", "size": "XXS", "max_price": 5.0}
    """
    text = query.lower()

    # 1. Price: prefer an explicit "$30", fall back to "under/below/less than 30".
    max_price = None
    price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text) or re.search(
        r"(?:under|below|less than)\s+\$?(\d+(?:\.\d+)?)", text
    )
    if price_match:
        max_price = float(price_match.group(1))

    # 2. Size: the token right after the word "size".
    size = None
    size_match = re.search(r"\bsize\s+(\w+)", text)
    if size_match:
        size = size_match.group(1).upper()

    # 3. Description: strip the size and price phrases, then drop filler words.
    desc = re.sub(r"\bsize\s+\w+", "", text)
    desc = re.sub(r"(?:under|below|less than)\s+\$?\d+(?:\.\d+)?", "", desc)
    desc = re.sub(r"\$\s*\d+(?:\.\d+)?", "", desc)
    words = [w for w in re.findall(r"[a-z']+", desc) if w not in _FILLER_WORDS]
    description = " ".join(words).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session — the single source of truth for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the natural-language query into search parameters.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: search. Branch on the result — this is the first decision point.
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results
    if not results:
        # No matches: stop here. Do NOT call suggest_outfit with empty input.
        session["error"] = (
            "I couldn't find any listings matching that. Try raising your max "
            "price, removing or changing the size, or describing the item in "
            "broader terms."
        )
        return session

    # Step 4: pick the top (most relevant) result and save it as state.
    session["selected_item"] = results[0]

    # Step 5: suggest an outfit. Second decision point — stop if it comes back
    # empty (an empty wardrobe is NOT empty here; it returns general advice).
    suggestion = suggest_outfit(session["selected_item"], wardrobe)
    if not suggestion or not suggestion.strip():
        session["error"] = "I found an item but couldn't put an outfit together. Try again."
        return session
    session["outfit_suggestion"] = suggestion

    # Step 6: create the shareable fit card from the outfit + the item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
