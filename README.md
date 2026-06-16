# FitFindr 🛍️

FitFindr is a single AI agent that helps users find secondhand clothing and
figure out how to wear it. Given one natural-language request, it searches a
mock listings dataset, suggests an outfit built around the best match using the
user's wardrobe, and writes a shareable caption — stopping early with a helpful
message if any step can't continue.

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Running

**Web app (Gradio):**
```bash
python app.py
```
Open the URL printed in your terminal (usually http://localhost:7860). Type a
request, pick a wardrobe, and the three panels fill with the listing, outfit,
and fit card.

**Command line:**
```bash
python agent.py        # runs a happy-path and a no-results example
```

**Tests:**
```bash
pytest tests/          # 7 tests across the three tools
```

## Tools

FitFindr is built from three tools, each independently testable.

### `search_listings(description, size, max_price) -> list[dict]`
- **Inputs:** `description` (str) — search keywords; `size` (str | None) —
  desired size, token-matched; `max_price` (float | None) — price ceiling.
- **Output:** a list of listing dicts (`id`, `title`, `price`, `platform`,
  `size`, `style_tags`, …) sorted by keyword-relevance, best first. Empty list
  `[]` when nothing matches.
- **Purpose:** filter the dataset down to the most relevant items for the query.

### `suggest_outfit(new_item, wardrobe) -> str`
- **Inputs:** `new_item` (dict) — the found listing; `wardrobe` (dict) — the
  user's wardrobe with an `items` list (may be empty).
- **Output:** a string with one complete outfit plus a quick alternative. With a
  wardrobe it names real owned pieces; with an empty wardrobe it gives general
  styling advice. (LLM-generated via Groq `llama-3.3-70b-versatile`.)
- **Purpose:** turn a found item into a wearable look.

### `create_fit_card(outfit, new_item) -> str`
- **Inputs:** `outfit` (str) — the suggestion from `suggest_outfit`;
  `new_item` (dict) — the found listing (for price/platform/name).
- **Output:** a short, casual, shareable caption (varies each run). Returns a
  descriptive error string if `outfit` is empty. (LLM-generated, higher
  temperature for variety.)
- **Purpose:** produce the social-post caption for the finished look.

## Planning Loop

`run_agent(query, wardrobe)` in [agent.py](agent.py) is the planning loop. It
runs the tools in order but checks each result and decides whether to continue
or stop — it does **not** call all three tools unconditionally.

1. **Parse** the query into `description` / `size` / `max_price` using regex
   (no LLM), stored in `session["parsed"]`.
2. **Search.** Call `search_listings`. **Decision point:** if the result list is
   empty, set `session["error"]` with an actionable message and `return` — the
   agent does not proceed to the outfit step.
3. **Select** the top match (`results[0]`) → `session["selected_item"]`.
4. **Suggest.** Call `suggest_outfit`. **Decision point:** if it returns an empty
   string, set `session["error"]` and stop. (An empty wardrobe is *not* empty
   here — it returns general advice, so the flow continues.)
5. **Fit card.** Call `create_fit_card` with the suggestion and item.
6. **Return** the session.

The two decision points are what make behavior change with input: an impossible
query stops at step 2, while a good query flows all the way to step 6.

## State Management

All state for one interaction lives in a single `session` dict created by
`_new_session()`. Each tool writes its result into the session, and the next
tool reads what it needs from it — nothing is re-entered or hardcoded between
steps. Key fields:

| Key | Set by | Read by |
|-----|--------|---------|
| `parsed` | query parser | `search_listings` call |
| `search_results` | `search_listings` | branch check |
| `selected_item` | the loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | the UI |
| `error` | any failed step | the UI (shown instead of results) |

For example, the exact `selected_item` dict that `search_listings` produced is
the same object passed into both `suggest_outfit` and `create_fit_card` — the
user never re-types the item.

## Error Handling

Each tool handles its own failure mode, and the loop stops early when continuing
would mean feeding a tool garbage. Examples below are from actual test runs.

| Tool | Failure mode | What happens | Example |
|------|-------------|--------------|---------|
| `search_listings` | no matches | returns `[]`; the loop sets an actionable error and stops (never calls the next tools) | Query `"designer ballgown size XXS under $5"` → `error`: *"I couldn't find any listings matching that. Try raising your max price, removing or changing the size, or describing the item in broader terms."* and `fit_card` stays `None`. |
| `suggest_outfit` | empty wardrobe | not an error — returns general styling advice for the item alone | `suggest_outfit(item, get_empty_wardrobe())` returned a full paragraph of generic styling tips plus an invite to add wardrobe items, no crash. |
| `create_fit_card` | empty/whitespace outfit | guard runs *before* the LLM call and returns a fixed message | `create_fit_card("", item)` returned `"Can't create a fit card without an outfit suggestion."` |

There's a deliberate distinction: an empty wardrobe is a *handled degrade*
(still useful), while an empty outfit is a *guard-and-report* (nothing to do).
The LLM tools also wrap their API call in try/except so a network/API error
returns a safe message string rather than crashing the agent.

## Spec Reflection

The build mostly matched [planning.md](planning.md), with two refinements worth
noting:

- **Size matching changed from substring to token match.** My spec said
  "case-insensitive substring," but during implementation I found that
  over-matched (size `"L"` matched `"XL (oversized)"`). I switched to token-based
  matching and updated the spec.
- **Query parsing was under-specified.** My planning loop assumed
  `search_listings` already had its three arguments, but the real entry point is
  one natural-language sentence. I added a Step 0 regex parser to bridge the gap
  and documented it in planning.md.

Everything else — the two decision points, the `session` state design, and each
tool's failure mode — was implemented as specced, which made wiring the loop in
Milestone 4 mostly a matter of following my own diagram.

## AI Usage

**Instance 1 — `search_listings` size matching (substring → token match):**
When implementing `search_listings`, my planning.md spec described size matching as a
case-insensitive **substring** match. While building the tool I caught that pure
substring matching over-matches: requesting `size="L"` would also match `"XL (oversized)"`
and `"W30 L30"` because both contain the letter "l". I changed the approach to a
**token-based** match instead — the listing's size string is split into tokens and the
requested size must equal a whole token (so "M" matches "S/M", but "L" no longer matches
"XL"). I also updated the Tool 1 spec in planning.md to reflect this refinement.

**Instance 2 — Planning loop implementation (`run_agent`):**
I gave Claude the Planning Loop, State Management, and Architecture (diagram)
sections of planning.md and asked it to implement `run_agent()`. It produced a
loop that branched on the search result and stored values in the session dict.
Before trusting it I verified the three things my spec required: it does *not*
call all three tools unconditionally, it stores each result under the right
session key, and the no-results path leaves `fit_card` as `None`. I confirmed
this by running both the happy-path and impossible queries and printing the
session.

**Instance 3 — Fit card output polish:**
Claude's first `create_fit_card` output showed the raw price (`$18.0`) and
occasionally wrapped the whole caption in quotation marks. I overrode this by
formatting the price with `:g` (so it reads `$18`) and stripping wrapping quotes
before returning, so the caption is clean enough to actually post.
