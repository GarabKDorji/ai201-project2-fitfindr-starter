# FitFindr

FitFindr is an AI-powered thrifting and styling agent. It can search a mock
secondhand clothing dataset, recommend outfits using a user's wardrobe, and
create a short social-media-style fit card.

Unlike a fixed pipeline, FitFindr uses a **planning loop**. The agent reads the
user's request, decides which tools are necessary, executes only those tools,
observes their results, and continues until the request is complete.

---

## Running the Project

Install the required packages and add a valid Groq API key to a `.env` file:

```
GROQ_API_KEY=your_key_here
```

Start the Gradio application:

```bash
python app.py
```

Open the URL displayed in the terminal (usually http://localhost:7860 — check
your terminal, the port may differ).

---

## Tool Inventory

> These interfaces match the actual function signatures in `tools.py`.

### `search_listings`

**Purpose:** Searches the mock thrift-listings dataset and returns the most
relevant matching items.

**Inputs:**
- `description: str` — keywords describing the requested item.
- `size: str | None` — optional clothing-size filter (case-insensitive; "M"
  matches a listing size such as "S/M").
- `max_price: float | None` — optional maximum-price filter (inclusive).

**Output:**
- `list[dict]` — up to three matching listing dictionaries, ranked by keyword
  relevance (lower price breaks ties for determinism). Returns an empty list
  `[]` when nothing matches — it never raises.
- Each listing dict contains: `id`, `title`, `description`, `category`,
  `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list),
  `brand`, `platform`.

### `suggest_outfit`

**Purpose:** Generates one or two outfit ideas using a selected thrifted item
and the user's wardrobe.

**Inputs:**
- `new_item: dict` — the selected listing.
- `wardrobe: dict` — the user's wardrobe, containing an `items` list.

**Output:**
- `str` — outfit recommendations. When the wardrobe is empty, the tool returns
  general styling advice without claiming that the user owns the recommended
  pieces. Returns a descriptive error string instead of raising on failure.

### `create_fit_card`

**Purpose:** Creates a short, shareable outfit caption using the selected
listing and a completed outfit suggestion.

**Inputs:**
- `outfit: str` — the outfit recommendation from `suggest_outfit`.
- `new_item: dict` — the selected thrifted listing.

**Output:**
- `str` — a two-to-four-sentence social-media caption (higher LLM temperature,
  so captions vary between runs). If the outfit input is missing or empty, the
  tool returns a descriptive error message instead of calling the LLM.

---

## Interaction Walkthrough

**User query:**
"Find me a vintage graphic tee under $30, help me style it with my wardrobe, and
create a fit-card caption."

**Step 1 — Tool called: `search_listings`**
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why this tool: the user wants to *find* an item, so the agent searches first.
- Output: top match — **Y2K Baby Tee — Butterfly Print** ($18.00, size S/M,
  depop). Stored as `session["selected_item"]`.

**Step 2 — Tool called: `suggest_outfit`**
- Input: the selected Y2K Baby Tee listing + the example wardrobe.
- Why this tool: the user explicitly asked to *style it with my wardrobe*.
- Output: one to two outfit suggestions pairing the tee with named wardrobe
  pieces. Stored as `session["outfit_suggestion"]`.

**Step 3 — Tool called: `create_fit_card`**
- Input: the outfit suggestion from Step 2 + the selected listing.
- Why this tool: the user asked to *create a fit-card caption*.
- Output: a short OOTD-style caption mentioning the item, price, and platform.
  Stored as `session["fit_card"]`.

**Final output to user:** the top listing, the wardrobe-based outfit idea, and
the shareable fit-card caption — one per Gradio panel.

> The agent does **not** call all three tools automatically. A search-only
> request (e.g. "Find me a vintage graphic tee under $30.") stops after
> `search_listings`; a styling request adds `suggest_outfit`; only an explicit
> caption request adds `create_fit_card`.

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the query (e.g. "designer ballgown size XXS under $5") | Returns `[]`; the agent stores a helpful message in `session["error"]` ("Try broader keywords, a higher budget, or removing the size filter.") and stops. It does **not** call `suggest_outfit` or `create_fit_card`. |
| `suggest_outfit` | Wardrobe is empty | Does not crash. Asks the LLM for general styling ideas and clearly avoids claiming the user already owns the recommended pieces. Returns a non-empty string. |
| `create_fit_card` | Outfit input missing or empty | A guard clause returns a descriptive error string ("Unable to create a fit card because a complete outfit suggestion is required.") instead of making a broken LLM request. |

**Additional safeguards:**
- **Tool or API failure:** the tools catch Groq API exceptions and convert them
  into readable error strings; the planning loop also catches unexpected
  exceptions so the Gradio app does not crash.
- **Excessive tool rounds:** the planning loop enforces a maximum tool-round
  limit, ending the session with a clear error instead of looping forever.

---

## Planning Loop

The agent begins with the user's natural-language request and stores it in the
conversation history. On each round the Groq model receives the user's request,
the available tool definitions, instructions describing when each tool should be
used, and the results of any tools that have already run. The model then decides
which tool (if any) to call.

- When the user wants to find an item, the agent begins with `search_listings`,
  with the model extracting `description`, `size`, and `max_price` as arguments.
- If no listings are found, the agent stops and returns a helpful message — it
  does **not** call `suggest_outfit` with an empty item.
- If listings are found, the top result becomes the selected item.
- A styling request also calls `suggest_outfit`; a fit-card request calls
  `create_fit_card`, but only after a valid outfit suggestion exists.

After every tool call, the result is appended to the message history and sent
back to the model so it can decide whether another action is necessary. The loop
ends when the model returns a normal response without requesting another tool, or
when the maximum tool-round limit is reached.

Examples:
- "Find me a vintage graphic tee under $30." → `search_listings`
- "...and help me style it." → `search_listings` → `suggest_outfit`
- "...style it, and make a fit-card caption." → `search_listings` →
  `suggest_outfit` → `create_fit_card`

---

## State Management

FitFindr uses a session dictionary as the single source of truth for one
interaction:

```python
{
    "query": str,
    "parsed": dict,
    "search_results": list,
    "selected_item": dict | None,
    "wardrobe": dict,
    "outfit_suggestion": str | None,
    "fit_card": str | None,
    "error": str | None,
    "messages": list,
}
```

- The search arguments chosen by the model are stored in `session["parsed"]`.
- The full search result is stored in `session["search_results"]`; the first
  result becomes `session["selected_item"]`.
- That exact selected-item dict is passed into `suggest_outfit(...)`, and its
  result is stored in `session["outfit_suggestion"]`.
- That same outfit text is passed into `create_fit_card(...)`, and its result is
  stored in `session["fit_card"]`.

The agent does not ask the user to re-enter information and does not replace tool
results with hardcoded values between steps. The `messages` list preserves the
user request, assistant tool calls, tool outputs, and final response so the
model can make each new decision using the results of earlier steps.

---

## Gradio Interface

`handle_query()` connects the planning agent to the three Gradio output panels.
It:

- Rejects an empty query.
- Loads either the example wardrobe or the empty wardrobe based on the user's
  radio selection.
- Calls `run_agent()`.
- Displays an error in the first panel if the interaction fails.
- Otherwise maps the selected listing, outfit suggestion, and fit card to their
  corresponding panels. When a tool was not requested, its panel receives an
  empty string.

---

## AI Usage

**Planning-loop implementation.** I provided ChatGPT with the Planning Loop and
State Management sections from `planning.md`, the Error Handling table, the full
Mermaid architecture diagram, the three tool interfaces, and the starter
`agent.py`. I reviewed the generated code before using it — checking that it
branched on an empty `search_listings` result, stored intermediate values in the
session dictionary, and avoided calling every tool unconditionally. I then
revised it so the Groq model decides which tools are required from the request,
and added dependency guards, tool-result messages, session-state updates,
exception handling, and a maximum tool-round limit.

**Gradio handler implementation.** I gave ChatGPT the `handle_query()` TODO, the
session-dictionary structure, the two wardrobe choices, and the three required
outputs. Before using the generated mapping logic, I verified that an empty query
returns early, the correct wardrobe loader is selected, agent errors appear only
in the first panel, and optional values such as a missing fit card are converted
to empty strings.

---

## Spec Reflection

**One way planning.md helped during implementation:** The spec defined the
responsibilities and failure behavior of each tool before any code was written,
which made the strongest part of the design — the separation between planning and
execution — easy to implement. The planning loop decides *what* should happen,
while each tool performs one specific task. State management also prevents the
agent from losing information between steps: the selected item and outfit
suggestion are reused directly rather than regenerated or re-requested from the
user.

**One divergence from your spec, and why:** The hardest part was preventing
unnecessary tool calls. A fixed pipeline would always create an outfit and fit
card, even when the user requested only a listing. The final implementation
instead lets the model choose tools according to the request while enforcing
dependencies and safety guards in Python. A current limitation is that the
agent's planning quality depends on the LLM correctly interpreting the request;
tool descriptions, system instructions, state guards, and the maximum-round
limit reduce this risk but cannot remove it completely.

---

## Where to Start

1. Read `planning.md` for the full design rationale and architecture diagram.
2. Verify the data loads: `python utils/data_loader.py`
3. Each tool can be tested in isolation before running the full agent — see the
   failure-mode triggers in the Error Handling section above.
