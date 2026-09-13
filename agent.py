"""Gemini-powered wardrobe recommendation agent with MANUAL function calling.

Verified against google-genai 2.22.0:
  - types.FunctionDeclaration(name=, description=, parameters=types.Schema(...))
  - types.Tool(function_declarations=[...])
  - AutomaticFunctionCallingConfig(disable=True)  -> we execute every call ourselves
  - types.Part.from_function_response(name=, response={...})
Model: a Flash-tier model, pinned by name rather than the rolling alias - see
the MODEL comment below for why the alias is unusable on a free-tier key.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

import tools
from gap_analysis import analyze_outfit_gaps

load_dotenv()

# The agent prints rupee symbols; a default Windows console is cp1252 and would
# raise UnicodeEncodeError on the first one.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Model choice, deliberately NOT the rolling "gemini-flash-latest" alias.
#
# That alias currently resolves to gemini-3.8-flash, whose free tier is capped at
# 20 requests PER DAY (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier)
# - one agent run eats half of it. Quota is bucketed per concrete model, so
# naming a model pins a separate allowance and keeps the demo runnable.
# gemini-2.5-flash 404s for new keys; its own error names gemini-3.6-flash as
# the replacement, which is what we use. Override with GEMINI_MODEL in .env.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
MAX_TURNS = 10
MAX_RETRIES = 5          # 503 "high demand" and 429 rate limits are common on the free tier
RETRY_BASE_DELAY = 2.0   # seconds; doubles each attempt

_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise RuntimeError("GEMINI_API_KEY is not set. Put it in .env next to agent.py.")
client = genai.Client(api_key=_api_key)


class AgentError(RuntimeError):
    """Raised when the model is unreachable after retries - the API layer turns
    this into a readable error response rather than a raw traceback."""


def _generate(**kwargs):
    """client.models.generate_content with backoff on transient server errors."""
    delay = RETRY_BASE_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.models.generate_content(**kwargs)
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            code = getattr(exc, "code", None)
            # A per-DAY quota will not recover inside a retry loop - fail fast
            # with a message that says what actually needs to happen.
            if code == 429 and "PerDay" in str(exc):
                raise AgentError(
                    f"Daily free-tier quota exhausted for model {MODEL} (20 requests/day). "
                    f"Set GEMINI_MODEL in .env to another Flash model for a fresh quota "
                    f"bucket, or wait for the daily reset."
                ) from exc
            if code not in (429, 500, 502, 503, 504) or attempt == MAX_RETRIES:
                raise AgentError(f"Gemini call failed ({code}): {exc}") from exc
            print(f"          .. {code} from the model, retrying in {delay:.0f}s "
                  f"(attempt {attempt}/{MAX_RETRIES})")
            time.sleep(delay)
            delay *= 2
    raise AgentError("Gemini call failed after retries")


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def _search_products(category=None, color=None, style_tags=None,
                     occasion=None, season=None, max_price=None) -> list[dict]:
    """Flat-parameter wrapper: the model passes top-level fields, tools.search_products
    wants a dict. Declaring a nested dict parameter makes the model waste turns
    guessing the call shape, so the assembly happens here instead."""
    filters = {
        "category": category,
        "color": color,
        "style_tags": style_tags,
        "occasion": occasion,
        "season": season,
        "max_price": max_price,
    }
    return tools.search_products({k: v for k, v in filters.items() if v is not None})


TOOL_IMPLS = {
    "get_customer_profile": tools.get_customer_profile,
    "get_wardrobe": tools.get_wardrobe,
    "get_browsing_history": tools.get_browsing_history,
    "analyze_outfit_gaps": analyze_outfit_gaps,
    "search_products": _search_products,
    "check_offer": tools.check_offer,
}

_STR = types.Type.STRING
_INT = types.Type.INTEGER


def _obj(properties: dict, required: list) -> types.Schema:
    return types.Schema(type=types.Type.OBJECT, properties=properties, required=required)


def _s(description: str, type_=_STR) -> types.Schema:
    return types.Schema(type=type_, description=description)


CUSTOMER_ID = {"customer_id": _s("The customer identifier, e.g. 'C001'.")}

FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_customer_profile",
        description=(
            "Returns one customer's stated preferences: preferred_styles, preferred_colors, "
            "avoided_colors, budget (a hard maximum price per item, in rupees), "
            "preferred_occasions and current_season. Call this first - every later search "
            "should respect the budget, colors and season it returns."
        ),
        parameters=_obj(CUSTOMER_ID, ["customer_id"]),
    ),
    types.FunctionDeclaration(
        name="get_wardrobe",
        description=(
            "Returns every item the customer already owns, each joined to its full product "
            "record (category, subcategory, color, style_tags, occasion, season, price, store) "
            "plus date_acquired and price_paid. Use it to avoid recommending something they "
            "already have, and to see what a new item would pair with."
        ),
        parameters=_obj(CUSTOMER_ID, ["customer_id"]),
    ),
    types.FunctionDeclaration(
        name="get_browsing_history",
        description=(
            "Returns products the customer recently viewed, saved, added to cart or abandoned "
            "in their cart, joined to full product details. Strong evidence of intent - an "
            "abandoned_cart or added_to_cart item is a stronger signal than a single view."
        ),
        parameters=_obj(CUSTOMER_ID, ["customer_id"]),
    ),
    types.FunctionDeclaration(
        name="analyze_outfit_gaps",
        description=(
            "Runs full gap analysis for a customer, returning missing categories, imbalances, "
            "occasion gaps, and which gaps have supporting browsing behavior. Call this early - "
            "it's the fastest way to understand what a customer needs. Gaps marked "
            "priority='high' are backed by the customer's own browsing history and should be "
            "filled first."
        ),
        parameters=_obj(CUSTOMER_ID, ["customer_id"]),
    ),
    types.FunctionDeclaration(
        name="search_products",
        description=(
            "Searches the catalogue. All parameters are optional and combine with AND logic; "
            "omit a parameter to leave that dimension unfiltered. Returns [] when nothing "
            "matches - if that happens, relax one filter (usually color) and try again rather "
            "than giving up. Always pass max_price set to the customer's budget."
        ),
        parameters=_obj(
            {
                "category": _s("One of: top, bottom, dress, outerwear, shoes, accessory."),
                "color": _s("Exact colour name, e.g. 'black', 'navy', 'beige'. Never pass a "
                            "colour listed in the customer's avoided_colors."),
                "style_tags": _s("A single style tag to require: casual, smart-casual, "
                                 "streetwear, formal, fusion or ethnic."),
                "occasion": _s("One of: college, casual, office, party, festive."),
                "season": _s("One of: summer, monsoon, winter. Also matches all-season items."),
                "max_price": _s("Maximum price in rupees. Set this to the customer's budget.", _INT),
            },
            [],
        ),
    ),
    types.FunctionDeclaration(
        name="check_offer",
        description=(
            "Checks whether one product has an active offer this customer actually qualifies "
            "for. Returns the offer (offer_type, discount_percentage, valid_until) or null. "
            "Returns null for expired offers and for bundle offers whose required "
            "condition_category the customer doesn't own. Call this on each product you intend "
            "to recommend, before finalising."
        ),
        parameters=_obj(
            {**CUSTOMER_ID, "product_id": _s("The product identifier, e.g. 'P0063'.")},
            ["customer_id", "product_id"],
        ),
    ),
]

TOOLS = [types.Tool(function_declarations=FUNCTION_DECLARATIONS)]

SYSTEM_INSTRUCTION = """You are a retail recommendation agent. Given a customer_id, recommend 3-5 specific products with clear reasoning for each, and attach any applicable offers.

Use the tools available - decide for yourself which you need and in what order. A sensible approach is often: check the customer's profile and run gap analysis first to understand what they need, then search for products filling high-priority gaps (respecting budget, preferred colors/styles, and avoided colors), then check each candidate for an applicable offer.

Prioritize gaps marked 'high' priority over 'medium', but don't ignore medium gaps if you have room for more recommendations.

If a candidate that already satisfies budget, color, and style preferences also has an active applicable offer, prefer it over an otherwise similar candidate with no offer.

For each recommendation, write a one-sentence explanation citing specific evidence: the gap it fills, why it matches their preferences, and the offer if one applies. Never recommend outside budget or in avoided colors.

analyze_outfit_gaps is the only authority on what counts as a gap. Only call something a gap - missing, lacking, absent, needed, a hole in their wardrobe - if that tool actually reported it. Do not infer a gap yourself from a category you notice is empty in get_wardrobe; the analyzer deliberately suppresses some of those (for example it does not treat tops or bottoms as missing when the customer owns dresses, because a dress already covers that combination).

You should still recommend products outside the reported gaps to reach 3-5 recommendations. Frame those honestly as complementary: say what they pair with, what occasion or season they extend, or which preference they match. Never say a complementary pick fills a missing category that the analyzer did not report.

When you have enough information, respond with your final answer - don't call further tools once ready to conclude.

You can issue several tool calls in a single turn and they all run together, so work to this four-turn plan and do not exceed it:
  Turn 1 - call get_customer_profile and analyze_outfit_gaps together (add get_wardrobe and get_browsing_history in the same turn if you want them).
  Turn 2 - issue EVERY search you need at once. Cover the high-priority gaps first, then enough extra searches to reach 5 candidates. Assume some searches return nothing and issue a broader backup search in the same turn rather than waiting a turn to retry.
  Turn 3 - call check_offer on ALL your candidates at once.
  Turn 4 - write the final answer. No more tool calls.
Never repeat a call you have already made; reread the earlier result instead.

Format the final answer as a markdown list with one product per line, each line beginning with the product_id in the form P0123, then the product name, price, and your one-sentence explanation."""


# --------------------------------------------------------------------------
# Trace summaries - built from the real result, not from the arguments
# --------------------------------------------------------------------------

def _counts(rows: list, field: str) -> str:
    tally = {}
    for row in rows:
        tally[row[field]] = tally.get(row[field], 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(tally.items(), key=lambda kv: -kv[1]))


def _summarize(name: str, args: dict, result) -> str:
    """Plain-language description of what this call actually found."""
    if name == "get_customer_profile":
        return (f"Profile: budget Rs{result['budget']}, prefers "
                f"{'/'.join(result['preferred_styles'])} styles in "
                f"{'/'.join(result['preferred_colors'])}, avoids "
                f"{'/'.join(result['avoided_colors'])}, dresses for "
                f"{'/'.join(result['preferred_occasions'])} in {result['current_season']}.")

    if name == "get_wardrobe":
        if not result:
            return "Wardrobe is empty - no owned items on record."
        return f"Found {len(result)} owned items: {_counts(result, 'category')}."

    if name == "get_browsing_history":
        if not result:
            return "No browsing history on record for this customer."
        noun = "event" if len(result) == 1 else "events"
        return (f"Found {len(result)} browsing {noun} ({_counts(result, 'event_type')}), "
                f"covering {_counts(result, 'category')}.")

    if name == "analyze_outfit_gaps":
        parts = []
        missing = result["missing_categories"]
        if missing:
            parts.append("missing " + ", ".join(
                f"{m['category']} ({m['priority']}"
                + (f", backed by {len(m['supporting_product_ids'])} browsed "
                   f"{'item' if len(m['supporting_product_ids']) == 1 else 'items'})"
                   if m["has_browsing_signal"] else ")")
                for m in missing))
        for imb in result["imbalances"]:
            parts.append(f"{imb['oversupplied_count']} {imb['oversupplied']} vs only "
                         f"{imb['undersupplied_count']} {imb['undersupplied']}")
        if result["occasion_gaps"]:
            parts.append("no items for " + ", ".join(
                f"{g['occasion']} ({g['priority']})" for g in result["occasion_gaps"]))
        if result["color_gap"]:
            parts.append("owns nothing in their preferred colours")
        body = "; ".join(parts) if parts else "no gaps found - wardrobe is well covered"
        return "Gap analysis: " + body + "."

    if name == "search_products":
        # Read as a phrase rather than a dict dump - the raw arguments are
        # displayed separately, so repeating them here just adds noise.
        bits = []
        for key in ("color", "style_tags", "season", "occasion", "category"):
            value = args.get(key)
            if value and str(value) not in bits:   # e.g. style_tags and occasion
                bits.append(str(value))            # can both be "casual"
        phrase = " ".join(bits) if bits else "products"
        if args.get("max_price"):
            phrase += f" under Rs{args['max_price']}"
        if not result:
            return f"Searched for {phrase} - nothing matched, the filters were too narrow."
        cheapest = min(result, key=lambda p: p["price"])
        noun = "match" if len(result) == 1 else "matches"
        return (f"Searched for {phrase} - {len(result)} {noun}, cheapest is "
                f"{cheapest['name']} at Rs{cheapest['price']}.")

    if name == "check_offer":
        pid = args.get("product_id")
        if not result:
            return f"No active qualifying offer for {pid}."
        kind = result["offer_type"].replace("_", " ")
        detail = f"{result['discount_percentage']}% off" if result["discount_percentage"] else kind
        return f"{pid} has an active {kind} offer ({detail}), valid until {result['valid_until']}."

    return f"{name} returned {result!r}"


# --------------------------------------------------------------------------
# Final structured extraction
# --------------------------------------------------------------------------

_RECOMMENDATION_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "recommendations": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_id": types.Schema(type=_STR, description="e.g. 'P0063'"),
                    "explanation": types.Schema(
                        type=_STR,
                        description=("One sentence citing the gap it fills, why it suits their "
                                     "preferences, and the offer if one applies.")),
                },
                required=["product_id", "explanation"],
            ),
        )
    },
    required=["recommendations"],
)

_EXTRACT_PROMPT = ("Now list the products you just recommended as structured data. "
                   "Use the exact product_id values you cited, and keep each explanation "
                   "to the one sentence you already wrote.")


_PRODUCT_ID_RE = re.compile(r"\bP\d{4}\b")


def _parse_final_text(final_text: str) -> list:
    """Pull product_id + explanation straight out of the agent's prose answer.

    Costs no API call, which matters on a quota-limited key. Each line that
    cites a product id becomes one recommendation, with the line itself
    (stripped of markdown bullets and headings) as the explanation.
    """
    rows, seen = [], set()
    for line in final_text.splitlines():
        ids = _PRODUCT_ID_RE.findall(line)
        if not ids or ids[0] in seen:
            continue
        seen.add(ids[0])
        explanation = re.sub(r"^[\s*\-#>\d.)]+", "", line).replace("**", "").strip()
        rows.append({"product_id": ids[0], "explanation": explanation})
    return rows


def _extract_recommendations(history: list, customer_id: str, final_text: str) -> list:
    """Turn the agent's prose answer into structured rows.

    The model supplies product_id and the explanation; name, price, colour and
    the offer are re-read from the datasets so nothing user-facing can be a
    hallucinated figure.

    Parsing the prose locally is tried first because it is free. Only if that
    finds too little do we spend an extra request on a schema-constrained call,
    and a failure there degrades to whatever the local parse found rather than
    throwing away a run that already succeeded.
    """
    raw = _parse_final_text(final_text)

    if len(raw) < 3:
        print(f"  .. local parse found {len(raw)} recommendation(s), asking the model")
        try:
            response = _generate(
                model=MODEL,
                contents=history + [types.Content(role="user",
                                                  parts=[types.Part(text=_EXTRACT_PROMPT)])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RECOMMENDATION_SCHEMA,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            raw = json.loads(response.text)["recommendations"]
        except (AgentError, json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"  ! structured extraction unavailable ({exc}); keeping the local parse")

    recommendations = []
    for row in raw:
        product = tools._PRODUCT_BY_ID.get(row.get("product_id"))
        if product is None:
            print(f"  ! model cited unknown product_id {row.get('product_id')!r} - dropping")
            continue
        recommendations.append({
            "product_id": product["product_id"],
            "name": product["name"],
            "price": product["price"],
            "color": product["color"],
            "category": product["category"],
            "store": product["store"],
            "explanation": _clean_explanation(row.get("explanation", ""), product),
            "offer": tools.check_offer(customer_id, product["product_id"]),
        })
    return recommendations


def _clean_explanation(text: str, product: dict) -> str:
    """Drop the model's restatement of the product id, name and price.

    The model habitually opens with "P0158 - Beige Overshirt (Rs. 1199): ..."
    but the card already shows all three, so the prefix is pure duplication.
    """
    text = _PRODUCT_ID_RE.sub("", text, count=1).strip(" -–—,:")
    name = product["name"].lower()

    # Peel off leading fragments that only restate the product - the model uses
    # both "Beige Overshirt (Rs. 1199): ..." and "White Cap, 999, ..." forms.
    for _ in range(3):
        head, sep, tail = re.match(r"^([^:,]*)([:,])?(.*)$", text, re.S).groups()
        head = (head or "").strip()
        if not sep or len(head) > 60:
            break
        restates = head.lower() in name or name in head.lower() or head.replace(
            "Rs.", "").replace("Rs", "").replace("₹", "").replace(",", "").strip().isdigit()
        if not restates:
            break
        text = (tail or "").strip(" -–—,:")

    return text[:1].upper() + text[1:] if text else text


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent / ".agent_cache"
CACHE_ENABLED = os.environ.get("AGENT_CACHE") == "1"


def _cache_path(customer_id: str) -> Path:
    return CACHE_DIR / f"{customer_id}.json"


def run_agent(customer_id: str) -> dict:
    """Run the agentic loop for one customer and return structured output.

    With AGENT_CACHE=1 a completed run is saved and replayed on the next call.
    The free-tier key allows only 20 requests per day per model and one run
    spends four or five, so this keeps the API and frontend testable without
    burning the day's quota. It is off by default.
    """
    tools.get_customer_profile(customer_id)  # fail fast on an unknown id

    if CACHE_ENABLED and _cache_path(customer_id).exists():
        print(f"[cache] replaying saved run for {customer_id} (AGENT_CACHE=1)")
        return json.loads(_cache_path(customer_id).read_text(encoding="utf-8"))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=TOOLS,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    history = [types.Content(role="user", parts=[types.Part(
        text=f"Recommend products for customer {customer_id}")])]

    trace = []
    gaps = None
    final_text = ""
    capped = False
    response = None

    bar = "=" * 74
    print(f"\n{bar}\nAGENT RUN - {customer_id}  (model={MODEL}, manual function calling)\n{bar}")

    for turn in range(1, MAX_TURNS + 1):
        response = _generate(model=MODEL, contents=history, config=config)
        candidate = response.candidates[0]
        history.append(candidate.content)

        calls = [p.function_call for p in (candidate.content.parts or []) if p.function_call]
        if not calls:
            final_text = (response.text or "").strip()
            print(f"\n[turn {turn}] model returned final answer ({len(final_text)} chars)")
            break

        response_parts = []
        for call in calls:
            args = dict(call.args or {})
            print(f"\n[turn {turn}] TOOL  {call.name}({json.dumps(args)})")
            try:
                result = TOOL_IMPLS[call.name](**args)
                summary = _summarize(call.name, args, result)
                payload = {"result": result}
            except Exception as exc:                      # surface the error to the model
                result, summary = None, f"{call.name} failed: {exc}"
                payload = {"error": str(exc)}
                print(f"          ERROR {exc}")

            if call.name == "analyze_outfit_gaps" and isinstance(result, dict):
                gaps = result

            print(f"          -> {summary}")
            trace.append({"step": len(trace) + 1, "tool": call.name,
                          "args": args, "summary": summary})
            response_parts.append(types.Part.from_function_response(name=call.name,
                                                                   response=payload))

        history.append(types.Content(role="user", parts=response_parts))
    else:
        capped = True
        print(f"\n!! WARNING: hit the {MAX_TURNS}-turn safety cap without a final answer.")
        final_text = (response.text or "").strip() if response else ""

    if gaps is None:                    # model never called it - we still owe the caller gaps
        gaps = analyze_outfit_gaps(customer_id)

    recommendations = _extract_recommendations(history, customer_id, final_text) if final_text else []

    rule = "-" * 74
    print(f"\n{rule}\nFINAL ANSWER\n{rule}\n{final_text or '(none)'}")
    print(f"\n{len(trace)} tool calls, {len(recommendations)} structured recommendations"
          + (" [TURN CAP HIT]" if capped else ""))

    result = {
        "customer_id": customer_id,
        "gaps": gaps,
        "trace": trace,
        "recommendations": recommendations,
        "final_text": final_text,
        "turn_capped": capped,
    }

    if CACHE_ENABLED and recommendations:
        CACHE_DIR.mkdir(exist_ok=True)
        _cache_path(customer_id).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[cache] saved run for {customer_id}")

    return result


if __name__ == "__main__":
    import sys
    run_agent(sys.argv[1] if len(sys.argv) > 1 else "C001")
