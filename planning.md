# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (loaded via `load_listings()`) for items that match the user's request. It filters the listings by the given parameters, then sorts the matches by relevance — how many of the user's keywords appear in each listing's title, description, and style_tags — and returns the best matches first.

**Input parameters:**
- `description` (str): free-text of what the user is looking for (e.g. "vintage graphic tee"). Matched against each listing's `title`, `description`, and `style_tags`.
- `size` (str or None): the desired size (e.g. "M"). Matched loosely and case-insensitively (substring match), because sizes in the data are inconsistent ("M", "S/M", "XL (oversized)", "W30 L30"). If `None`, size is not used to filter.
- `max_price` (float or None): the maximum price the user will pay. Only listings with `price <= max_price` are kept. If `None`, price is not used to filter.

**What it returns:**
A list of listing dicts, sorted by relevance (most keyword matches first). Each dict has the same fields as the dataset: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Returns an empty list `[]` when nothing matches.

**What happens if it fails or returns nothing:**
If the result is an empty list, the agent does **not** continue to `suggest_outfit`. Instead it stops and tells the user that no matches were found, and suggests how to adjust the query — raise `max_price`, remove or change the `size`, or use broader keywords.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the item found by `search_listings` and the user's wardrobe, then calls the LLM (Groq `llama-3.3-70b-versatile`) to suggest a complete outfit built around that item. If the wardrobe has items, it pairs the new item with pieces the user already owns; if the wardrobe is empty, it gives general styling advice for the item on its own.

**Input parameters:**
- `new_item` (dict): a single listing dict (the top result that flowed out of `search_listings`), with fields like `title`, `category`, `style_tags`, `colors`.
- `wardrobe` (dict): the user's wardrobe, a dict with an `items` key holding a list of wardrobe-item dicts (from `get_example_wardrobe()` or `get_empty_wardrobe()`). The `items` list may be empty.

**What it returns:**
A single string containing the outfit suggestion (styling text describing what to wear the item with and how). This string is what flows into `create_fit_card` next.

**What happens if it fails or returns nothing:**
- **Empty/minimal wardrobe** — not an error. The tool returns general styling advice for the item on its own, so the agent stays useful without the user having to fill out a wardrobe first.
- **LLM call errors out** (network/API error, or empty response) — the tool catches the error and returns a clear, safe message string instead of crashing the agent, so the downstream `create_fit_card` is never fed garbage.

---

### Tool 3: create_fit_card

**What it does:**
Takes the outfit suggestion (from `suggest_outfit`) and the found item, then calls the LLM to write a short, casual, shareable caption — the kind of thing someone would post with their outfit on Instagram or Depop. It uses the item details (title, price, platform) to ground the caption in specifics and the outfit text to capture the overall vibe.

**Input parameters:**
- `outfit` (str): the outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): the same listing dict used earlier, used to pull concrete details for the caption (e.g. `title`, `price`, `platform`).

**What it returns:**
A single short string — the shareable caption (1–3 casual sentences, may include emoji). Designed to read like a social post, not a product description.

**What happens if it fails or returns nothing:**
If `outfit` is an empty or missing string, the tool does **not** call the LLM — it returns a clear error message string (e.g. "Can't create a fit card without an outfit suggestion."). If the LLM call itself errors out, it catches the error and returns a safe message string rather than raising an exception.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent moves through the three tools in order, but at each step it checks what the previous tool returned and decides whether to continue or stop. It does **not** call all three tools blindly — a failed or empty result ends the flow early. State is tracked in a `session` dict (`selected_item`, `outfit_suggestion`, `fit_card`, `error`).

1. **Call `search_listings(description, size, max_price)`** with the user's query.
   - Check: is the returned list empty?
     - If **empty** → set `session["error"]` to a "no matches, try adjusting your query" message, and **return early — do NOT call `suggest_outfit`.**
     - If it **has items** → save `session["selected_item"] = results[0]` (the top match) and continue.

2. **Call `suggest_outfit(selected_item, wardrobe)`.**
   - Check: did it return a usable (non-empty) suggestion string?
     - If the string is **empty or an error** → set `session["error"]` and stop; **do not call `create_fit_card`** with bad input.
     - If it returned a real suggestion → save `session["outfit_suggestion"] = suggestion` and continue. (An empty wardrobe is not a failure here — it still returns general styling advice, so this branch proceeds normally.)

3. **Call `create_fit_card(outfit_suggestion, selected_item)`** — the final step.
   - Check: did it produce a caption (or hit its own empty-outfit guard)?
     - Either way, save the returned string to `session["fit_card"]`. There is no further tool to call.

4. **Return the `session`** so the user sees the item found, the outfit suggestion, and the fit card (or the error message if the flow stopped early).

---

## State Management

**How does information from one tool get passed to the next?**

All information in a single run is stored in one Python dictionary called `session`, created at the start of `run_agent()`. Instead of passing values directly between tools or asking the user to re-enter anything, each tool writes its result into `session`, and the next tool reads what it needs out of `session`. This keeps every piece of state in one place that the planning loop controls.

The `session` dict tracks four keys:

- `selected_item` (dict or None) — the top listing returned by `search_listings` (`results[0]`). Written after a successful search; read by both `suggest_outfit` and `create_fit_card`.
- `outfit_suggestion` (str or None) — the styling text returned by `suggest_outfit`. Written after a successful suggestion; read by `create_fit_card`.
- `fit_card` (str or None) — the shareable caption returned by `create_fit_card`. Written at the final step; read by the app to show the user.
- `error` (str or None) — set only when a tool fails or returns nothing, so the flow can stop early and the app knows to show the error instead of results.

**Example of state flowing between tools:** `search_listings` finds a band tee and the loop stores it as `session["selected_item"]`. That *same dict* is then passed straight into `suggest_outfit(session["selected_item"], wardrobe)` — the user never re-types the item. The resulting outfit string is saved to `session["outfit_suggestion"]`, which then flows into `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. By the end, `session` holds the full record of the interaction.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | The agent stops before calling any other tool and tells the user specifically: *"I couldn't find any listings matching that. Try raising your max price, removing or changing the size, or describing the item in broader terms."* It offers the three concrete levers (price, size, keywords) rather than a generic "no results." |
| suggest_outfit | Wardrobe is empty | Not treated as an error — the agent still returns a useful outfit suggestion as **general styling advice for the item on its own** (e.g. how to style the piece, what colors/silhouettes pair with it), and notes that adding wardrobe items would let it give personalized pairings. The flow continues normally to the fit card. |
| create_fit_card | Outfit input is missing or incomplete | The tool checks `outfit` first; if it's empty/missing it skips the LLM call and returns a clear message string: *"Can't create a fit card without an outfit suggestion."* This surfaces to the user as a readable message, not a crash, and signals that the outfit step didn't complete. |

---

## Architecture

```
User query ("vintage graphic tee under $30, size M")        Wardrobe
     │                                                    (example or empty)
     ▼                                                          │
Planning Loop ─────────────────────────────────────────────────┼──────────┐
     │                                                          │          │
     ├─► search_listings(description, size, max_price)          │          │
     │       │ results == []                                    │          │
     │       ├──► [ERROR] session["error"] = "No matches —       │          │
     │       │            try raising price / changing size" ───┼────► return (stops here)
     │       │                                                  │          │
     │       │ results == [item, ...]                           │          │
     │       ▼                                                  │          │
     │   Session: selected_item = results[0]  ◄─────────────────┘          │
     │       │                                                             │
     ├─► suggest_outfit(selected_item, wardrobe)                           │
     │       │ empty string / LLM error                                    │
     │       ├──► [ERROR] session["error"] = "Couldn't build an outfit" ───┼─► return (stops here)
     │       │                                                             │
     │       │ outfit suggestion string                                    │
     │       ▼                                                             │
     │   Session: outfit_suggestion = "..."                                │
     │       │                                                             │
     └─► create_fit_card(outfit_suggestion, selected_item)                 │
             │                                                             │
         Session: fit_card = "..."  (or guard message if outfit empty)     │
             │                                                             │
             ▼                                       error paths return here ┘
        Return session ──► User sees: item found + outfit suggestion + fit card
                           (or the error message if the flow stopped early)
```


---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use **Claude (Claude Code)** to implement each tool one at a time. For each tool I'll give Claude that tool's block from the **Tools** section of this planning.md (what it does, input parameters with types, return value, and failure mode) that I wrote, plus the relevant data facts (the listing fields, and the `load_listings()` / `get_example_wardrobe()` / `get_empty_wardrobe()` helpers in `utils/data_loader.py`).

- **search_listings:** I expect Claude to produce a function that loads listings via `load_listings()`, filters on `description` (keyword match against title/description/style_tags), `size` (loose case-insensitive substring), and `max_price` (`price <= max_price`), then sorts by relevance and returns a list of listing dicts (or `[]`). **Before trusting it I'll verify:** it filters on all three parameters, it returns `[]` (not an exception) when nothing matches, and `None` size/price means "don't filter." Then I'll run it on 3 queries (a normal one, an impossible one, and a price-capped one).
- **suggest_outfit:** I expect a function that calls Groq `llama-3.3-70b-versatile`, builds a prompt from `new_item` and the wardrobe items, and returns a styling string. **I'll verify:** it doesn't crash on an empty `wardrobe["items"]` (returns general advice instead), and it wraps the LLM call so an API error returns a safe string.
- **create_fit_card:** I expect a function that guards an empty `outfit` (early return of an error string, no LLM call), otherwise calls the LLM with a higher temperature to produce a short, varied caption using item details. **I'll verify:** the empty-outfit guard returns a message (not an exception), and running it twice on the same input gives *different* captions.

For all three I'll confirm the generated signature matches the spec exactly before running, then lock the behavior in with the pytest tests in `tests/test_tools.py`.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the **Planning Loop**, **State Management**, and **Architecture** sections of this planning.md together (the diagram included, since it shows the branches and the `session` keys), and ask it to implement `run_agent()` following those branches.

- **I expect it to produce:** a `run_agent()` that creates the `session` dict, calls `search_listings` first, and **branches on the result** — returning early with `session["error"]` set when results are empty, and only calling `suggest_outfit` / `create_fit_card` when the prior step succeeded.
- **Before trusting it I'll verify:** it does *not* call all three tools unconditionally, it stores each tool's output in the matching `session` key, and the no-results path leaves `session["fit_card"]` as `None`. I'll test by running the happy-path query (and printing `session["selected_item"]` to confirm the same dict flows into `suggest_outfit`) and the impossible query (to confirm it stops early with an error).

---

## A Complete Interaction (Step by Step)

**Overview:** FitFindr is a single AI agent that uses three tools to help users thrift shop efficiently. When a user describes what they want, the agent triggers `search_listings` to find matching items; if nothing matches, it tells the user what to adjust (size, price, or description) and stops rather than guessing. If items are found, it passes the top result into `suggest_outfit` to build an outfit from the user's wardrobe — falling back to general styling advice when the wardrobe is empty — and finally passes that outfit into `create_fit_card` to write a shareable caption, returning an error message instead of crashing if the outfit is missing.

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:**
The agent calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. (No size was given in the query, so `size=None`; "under $30" → `max_price=30.0`.) It returns several matching listings sorted by relevance. The top match is:
`{"id": "lst_033", "title": "Vintage Band Tee — Faded Grey", "price": 19.0, "size": "L", "platform": "depop", "style_tags": ["vintage", "grunge", "band tee", "graphic tee", "streetwear"], ...}`
The loop saves it: `session["selected_item"] = results[0]`.

**Step 2 — Suggest outfit:**
The agent calls `suggest_outfit(new_item=<the band tee dict above>, wardrobe=<example wardrobe>)`. The LLM uses the item plus the user's stated style (baggy jeans, chunky sneakers) and wardrobe items to return a suggestion string, e.g.:
*"Wear the faded band tee with your wide-leg jeans and chunky sneakers for an easy grunge look. Half-tuck the front and layer a flannel over the top for cooler days."*
The loop saves it: `session["outfit_suggestion"] = <that string>`.

**Step 3 — Fit card:**
The agent calls `create_fit_card(outfit=<the suggestion string>, new_item=<the band tee dict>)`. Using the item's price ($19) and platform (Depop) plus the outfit vibe, the LLM returns a short shareable caption, e.g.:
*"scored this faded band tee on depop for $19 🖤 pairing it with my baggy jeans + chunky sneakers — full fit in my stories"*
The loop saves it: `session["fit_card"] = <that string>`.

**Final output to user:**
The user sees all three pieces of the session: the item found (*Vintage Band Tee — Faded Grey, $19, Depop*), the outfit suggestion, and the shareable fit card — produced from one natural-language query with no re-entry between steps.
