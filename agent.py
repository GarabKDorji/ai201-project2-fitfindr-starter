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

from tools import search_listings, suggest_outfit, create_fit_card
import re
import json
from tools import _get_groq_client


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


    session = _new_session(query, wardrobe)

    # Store the conversation history in the session.
    session["messages"] = [
        {
            "role": "system",
            "content": (
                "You are the FitFindr planning agent. Decide which tools are "
                "needed based on the user's request.\n\n"
                "Rules:\n"
                "1. Call search_listings first when the user wants to find an item.\n"
                "2. Call suggest_outfit only when the user asks for styling, "
                "outfit, pairing, or what to wear.\n"
                "3. Call create_fit_card only when the user asks for a fit card, "
                "caption, Instagram caption, or social media post.\n"
                "4. Never call suggest_outfit unless a listing has been selected.\n"
                "5. Never call create_fit_card unless an outfit suggestion exists.\n"
                "6. Do not call all tools automatically.\n"
                "7. When the request is complete, return a normal final response."
            ),
        },
        {
            "role": "user",
            "content": query,
        },
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_listings",
                "description": (
                    "Search thrift listings using a description, optional size, "
                    "and optional maximum price."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "The clothing item to search for.",
                        },
                        "size": {
                            "type": "string",
                            "description": "Optional requested clothing size.",
                        },
                        "max_price": {
                            "type": "number",
                            "description": "Optional maximum price.",
                        },
                    },
                    "required": ["description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "suggest_outfit",
                "description": (
                    "Create outfit suggestions using the selected listing and "
                    "the user's wardrobe. Call only when styling was requested."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_fit_card",
                "description": (
                    "Create a social-media fit card using the selected listing "
                    "and outfit suggestion. Call only when explicitly requested."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]

    client = _get_groq_client()
    max_tool_rounds = 6

    for _ in range(max_tool_rounds):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=session["messages"],
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as error:
            session["error"] = f"Unable to run the planning agent: {error}"
            return session

        assistant_message = response.choices[0].message

        # Save the assistant message, including its tool calls.
        session["messages"].append(
            assistant_message.model_dump(exclude_none=True)
        )

        # No tool calls means the agent has completed the request.
        if not assistant_message.tool_calls:
            return session

        # Execute only the tools requested in this newest response.
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name

            try:
                arguments = json.loads(
                    tool_call.function.arguments or "{}"
                )
            except json.JSONDecodeError:
                arguments = {}

            try:
                if tool_name == "search_listings":
                    description = arguments.get("description", query)
                    size = arguments.get("size")
                    max_price = arguments.get("max_price")

                    session["parsed"] = {
                        "description": description,
                        "size": size,
                        "max_price": max_price,
                    }

                    result = search_listings(
                        description=description,
                        size=size,
                        max_price=max_price,
                    )

                    session["search_results"] = result

                    # Branch on the search result.
                    if not result:
                        session["error"] = (
                            "I couldn't find any matching listings. "
                            "Try broader keywords, a higher budget, or "
                            "removing the size filter."
                        )
                        return session

                    session["selected_item"] = result[0]

                elif tool_name == "suggest_outfit":
                    if session["selected_item"] is None:
                        result = {
                            "error": (
                                "An item must be selected before an outfit "
                                "can be suggested."
                            )
                        }
                    else:
                        result = suggest_outfit(
                            session["selected_item"],
                            session["wardrobe"],
                        )

                        session["outfit_suggestion"] = result

                elif tool_name == "create_fit_card":
                    if not session["outfit_suggestion"]:
                        result = {
                            "error": (
                                "An outfit suggestion is required before "
                                "a fit card can be created."
                            )
                        }
                    else:
                        result = create_fit_card(
                            session["outfit_suggestion"],
                            session["selected_item"],
                        )

                        session["fit_card"] = result

                else:
                    result = {
                        "error": f"Unknown tool requested: {tool_name}"
                    }

            except Exception as error:
                result = {
                    "error": f"{tool_name} failed: {error}"
                }

            # Give the tool result back to the agent.
            session["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(result),
                }
            )

    session["error"] = (
        "The agent reached the maximum number of tool rounds "
        "before completing the request."
    )
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
