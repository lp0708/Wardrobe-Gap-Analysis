"""Gemini-powered retail personalisation agent with MANUAL function calling.

The agent is the orchestrator. It decides which facts and which intelligence
modules it needs, asks the recommendation engine for ranked candidates, chooses
the final picks and writes the explanations. The intelligence modules supply
grounded evidence; the engine ranks; the model reasons and explains.

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
from intelligence import recommendation_engine as engine
from intelligence.gap_analysis import analyze_outfit_gaps
from intelligence.intent_analysis import detect_browsing_intent
from intelligence.purchase_analysis import analyze_purchase_patterns
from intelligence.seasonal_trends import get_seasonal_context

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
# - one agent run eats a fifth of it. Quota is bucketed per concrete model, so
# naming a model pins a separate allowance and keeps the demo runnable.
# gemini-2.5-flash 404s for new keys; its own error names gemini-3.6-flash as
# the replacement, which is what we use. Override with GEMINI_MODEL in .env.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
MAX_TURNS = 10
MAX_RETRIES = 5          # 503 "high demand" and 429 rate limits are common on the free tier
RETRY_BASE_DELAY = 2.0   # seconds; doubles each attempt
MIN_RECOMMENDATIONS = 3
MAX_RECOMMENDATIONS = 5

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
            if code not in (429, 500, 502, 503, 504):
                raise AgentError(f"Gemini call failed ({code}): {exc}") from exc
            if attempt == MAX_RETRIES:
                # Google's raw error body is a JSON dump - say what happened instead.
                reason = ("is rate-limiting requests" if code == 429
                          else "is overloaded right now (high demand)")
                raise AgentError(
                    f"Gemini model {MODEL} {reason} and still failed after {MAX_RETRIES} "
                    f"attempts. Try again in a minute, or set GEMINI_MODEL in .env to "
                    f"another Flash model."
                ) from exc
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


def _compact_candidate(candidate: dict) -> dict:
    """What the model needs to choose between candidates, without the bulk."""
    offer = candidate["offer"]
    return {
        "product_id": candidate["product_id"],
        "name": candidate["name"],
        "category": candidate["category"],
        "color": candidate["color"],
        "price": candidate["price"],
        "season": candidate["season"],
        "score": candidate["score"],
        "types": candidate["types"],
        "primary_type": candidate["primary_type"],
        "offer": ({key: offer[key] for key in ("offer_type", "discount_percentage", "valid_until")}
                  if offer else None),
        "signals": [f"{s['points']:+d} [{s['group']}] {s['evidence']}" for s in candidate["signals"]],
    }


def _rank_recommendations(customer_id, category=None, recommendation_type=None, limit=None) -> dict:
    result = engine.rank_recommendations(customer_id, category=category,
                                         recommendation_type=recommendation_type,
                                         limit=limit or engine.DEFAULT_LIMIT)
    return {**result, "candidates": [_compact_candidate(c) for c in result["candidates"]]}


TOOL_IMPLS = {
    "get_customer_profile": tools.get_customer_profile,
    "get_wardrobe": tools.get_wardrobe,
    "get_browsing_history": tools.get_browsing_history,
    "analyze_outfit_gaps": analyze_outfit_gaps,
    "analyze_purchase_patterns": analyze_purchase_patterns,
    "detect_browsing_intent": detect_browsing_intent,
    "get_seasonal_context": get_seasonal_context,
    "rank_recommendations": _rank_recommendations,
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


def _customer_tool(name: str, description: str) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(name=name, description=description,
                                     parameters=_obj(CUSTOMER_ID, ["customer_id"]))


FUNCTION_DECLARATIONS = [
    # ---- facts ------------------------------------------------------------
    _customer_tool(
        "get_customer_profile",
        "Returns the customer's stated preferences: preferred_styles, preferred_colors, "
        "avoided_colors, budget (a hard maximum price per item, in rupees), "
        "preferred_occasions and current_season.",
    ),
    _customer_tool(
        "get_wardrobe",
        "Returns every item the customer owns (their purchase history), each joined to its "
        "full product record plus date_acquired and price_paid. Use it to check exactly what a "
        "recommendation would be worn with.",
    ),
    _customer_tool(
        "get_browsing_history",
        "Returns the customer's raw browsing events (viewed, saved, added_to_cart, "
        "abandoned_cart) with timestamps and view counts, joined to product details. "
        "detect_browsing_intent is usually more useful - it scores these events for you.",
    ),
    # ---- customer intelligence ---------------------------------------------
    _customer_tool(
        "analyze_outfit_gaps",
        "Runs full gap analysis: missing categories, category imbalances, occasion gaps and a "
        "colour gap, each marked high priority when the customer's browsing backs it. This is "
        "the ONLY authority on what the customer is missing. Call it early.",
    ),
    _customer_tool(
        "analyze_purchase_patterns",
        "Summarises how the customer actually buys: category and colour frequency, dominant "
        "styles, repeat purchases, recent purchases, and spend (average, typical price range, "
        "share of budget). Flags when there are too few purchases to establish patterns.",
    ),
    _customer_tool(
        "detect_browsing_intent",
        "Scores the customer's browsing into intent by category, occasion and colour, weighting "
        "cart and save events above views and recent events above old ones. Returns a headline, "
        "strength (strong/moderate/weak) and the products behind it. Says explicitly when there "
        "is not enough browsing to infer intent - never claim intent in that case.",
    ),
    _customer_tool(
        "get_seasonal_context",
        "Returns the customer's current season and the curated seasonal trends for it "
        "(trending categories with demand level, trending item types, colours, styles), which "
        "of those match the customer's preferences, and observed browsing demand across all "
        "shoppers. The trend list is curated demo data, not a market forecast.",
    ),
    # ---- ranking ------------------------------------------------------------
    types.FunctionDeclaration(
        name="rank_recommendations",
        description=(
            "Ranks eligible products for the customer by combining every signal: wardrobe gaps, "
            "browsing intent, purchase patterns, seasonal trends, stated preferences, fit with "
            "items they own, and active offers. Products over budget, in avoided colours, or "
            "already owned are excluded before scoring. Each candidate lists its score, its "
            "recommendation types (gap / intent / seasonal / complementary) and every signal "
            "with the evidence behind it. Call it once unfocused, and optionally again with a "
            "recommendation_type or category to surface picks the overall ranking under-represents."
        ),
        parameters=_obj(
            {
                **CUSTOMER_ID,
                "category": _s("Optional: only rank one category - top, bottom, dress, "
                               "outerwear, shoes or accessory."),
                "recommendation_type": _s("Optional: only candidates of this type - gap, intent, "
                                          "seasonal or complementary."),
                "limit": _s("Optional: how many candidates to return (default 8, max 20).", _INT),
            },
            ["customer_id"],
        ),
    ),
    # ---- catalogue access -----------------------------------------------------
    types.FunctionDeclaration(
        name="search_products",
        description=(
            "Searches the raw catalogue. All parameters are optional and combine with AND logic. "
            "Unlike rank_recommendations this applies no personalisation and no budget or colour "
            "rules - only use it to look beyond the ranked candidates, and pass max_price."
        ),
        parameters=_obj(
            {
                "category": _s("One of: top, bottom, dress, outerwear, shoes, accessory."),
                "color": _s("Exact colour name, e.g. 'black', 'navy', 'beige'."),
                "style_tags": _s("A single style tag: casual, smart-casual, streetwear, formal, "
                                 "fusion or ethnic."),
                "occasion": _s("One of: college, casual, office, party, festive."),
                "season": _s("One of: summer, monsoon, winter. Also matches all-season items."),
                "max_price": _s("Maximum price in rupees.", _INT),
            },
            [],
        ),
    ),
    types.FunctionDeclaration(
        name="check_offer",
        description=(
            "Checks whether one product has an active offer this customer qualifies for. "
            "rank_recommendations already includes this for its candidates; use it only for "
            "products you found through search_products."
        ),
        parameters=_obj(
            {**CUSTOMER_ID, "product_id": _s("The product identifier, e.g. 'P0063'.")},
            ["customer_id", "product_id"],
        ),
    ),
]

TOOLS = [types.Tool(function_declarations=FUNCTION_DECLARATIONS)]

SYSTEM_INSTRUCTION = """You are a personalisation agent working for a fashion retailer. Given a customer_id, you build an evidence-based picture of that customer and recommend 3-5 products, with any offers, that the retailer should put in front of them - and you explain why each one is personal to this customer.

Your tools come in three layers:
  Facts: get_customer_profile, get_wardrobe, get_browsing_history, search_products, check_offer.
  Customer intelligence (deterministic analysis of those facts): analyze_outfit_gaps, analyze_purchase_patterns, detect_browsing_intent, get_seasonal_context.
  Ranking: rank_recommendations, which scores eligible products against all of the signals and shows the evidence behind every point.

Decide for yourself which tools you need. A good approach is to understand the customer first, then rank candidates, then choose. Use a focused rank_recommendations call (by recommendation_type or category) when you want a kind of pick the overall ranking under-represents - for example a complementary piece, or the category the customer has been browsing.

Choosing recommendations:
- Pick 3-5 products from what the tools returned. Favour higher scores, but aim for a set that covers the customer's strongest distinct signals rather than five near-identical items.
- If two candidates are otherwise similar, prefer the one with an active offer.
- Never recommend a product over budget or in an avoided colour.

Grounding rules - strict:
- Every factual claim must come from a tool result. Never invent preferences, purchases, browsing, gaps, trends, prices, colours or offers.
- analyze_outfit_gaps is the only authority on gaps. Only say a product fills a gap (or that something is missing, lacking or needed) if that product's signals include a [gap] signal. Otherwise describe it by the signals it does have.
- Only mention browsing if the product has an [intent] signal. Only mention a trend if it has a [trend] signal. Only mention an offer if it has one, with the exact discount.
- When detect_browsing_intent reports there is not enough browsing to infer intent, do not claim browsing intent.
- The seasonal trend list is curated demo data. Call it "seasonal trends"; never present it as market research or a forecast.

Work efficiently - several tool calls in one turn run together:
  Turn 1: get_customer_profile, analyze_outfit_gaps, analyze_purchase_patterns, detect_browsing_intent and get_seasonal_context, all at once.
  Turn 2: rank_recommendations - the overall ranking plus any focused rankings you want, all at once.
  Turn 3: the final answer. Only take an extra turn if you genuinely need search_products or check_offer.
Never repeat an identical call.

Final answer format - plain text, exactly this shape and nothing else:
SUMMARY: <one or two sentences for the retailer: who this customer is and the biggest opportunity, using only tool facts>
P0123 | <one sentence on why this product, citing its specific evidence>
(one product line per recommendation)"""


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

    if name == "analyze_purchase_patterns":
        return f"Purchase patterns: {result['headline']}"

    if name == "detect_browsing_intent":
        return f"Browsing intent: {result['headline']}"

    if name == "get_seasonal_context":
        return f"Seasonal context: {result['headline']}"

    if name == "rank_recommendations":
        focus = [f"{k}={v}" for k, v in result["filters"].items() if v and k != "limit"]
        excluded = ", ".join(f"{n} {reason.replace('_', ' ')}"
                             for reason, n in result["excluded"].items())
        top = ", ".join(f"{c['name']} ({c['score']}, {c['primary_type']})"
                        for c in result["candidates"][:3])
        return (f"Ranked {result['eligible']} eligible of {result['considered']} products"
                f"{' (' + ', '.join(focus) + ')' if focus else ''}"
                f"{'; excluded ' + excluded if excluded else ''}. "
                f"Top: {top or 'nothing eligible'}.")

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
# Parsing the final answer
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
                        description="The one-sentence explanation already written for it."),
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
_SUMMARY_RE = re.compile(r"^\W*SUMMARY\W*:?\s*(.+)$", re.I)


def _parse_final_text(final_text: str) -> tuple[str, list]:
    """Pull the summary and each product_id + explanation out of the final answer.

    Costs no API call, which matters on a quota-limited key.
    """
    summary, rows, seen = "", [], set()
    for line in final_text.splitlines():
        match = _SUMMARY_RE.match(line)
        if match:
            summary = match.group(1).replace("**", "").strip()
            continue
        ids = _PRODUCT_ID_RE.findall(line)
        if not ids or ids[0] in seen:
            continue
        seen.add(ids[0])
        explanation = line.split("|", 1)[1] if "|" in line else line
        explanation = re.sub(r"^[\s*\-#>\d.)]+", "", explanation).replace("**", "").strip()
        rows.append({"product_id": ids[0], "explanation": explanation})
    return summary, rows


def _clean_explanation(text: str, product: dict) -> str:
    """Drop the model's restatement of the product id, name and price.

    The model habitually opens with "P0158 - Beige Overshirt (Rs. 1199): ..."
    but the card already shows all three, so the prefix is pure duplication.
    """
    text = _PRODUCT_ID_RE.sub("", text, count=1).strip(" -–—,:|")
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
# Grounding check on the model's explanations
# --------------------------------------------------------------------------

_CLAIMS = (
    ("gap", re.compile(r"\b(gaps?|missing|lacks?|lacking|absent|needs?|needed)\b", re.I),
     "claims a wardrobe gap the gap analyzer did not report"),
    ("intent", re.compile(r"\b(brows\w*|viewed|views?|saved|cart\w*)\b", re.I),
     "cites browsing behaviour this product has no signal for"),
    ("trend", re.compile(r"\btrend\w*", re.I),
     "cites a seasonal trend this product does not match"),
    ("offer", re.compile(r"(\boffers?\b|\bdiscount\w*|\bsale\b|%\s*off|free shipping|\bbundle\b)", re.I),
     "mentions an offer this product does not have"),
)
_PERCENT_RE = re.compile(r"(\d{1,2})\s*%")


def grounding_issues(text: str, candidate: dict) -> list:
    """Claims in an explanation that the candidate's recorded evidence doesn't support."""
    groups = {s["group"] for s in candidate["signals"] if s["points"] > 0}
    issues = [message for group, pattern, message in _CLAIMS
              if pattern.search(text) and group not in groups]

    offer = candidate["offer"]
    if offer:
        cited = {int(p) for p in _PERCENT_RE.findall(text)}
        purchase_shares = {int(p) for s in candidate["signals"] if s["group"] == "purchase"
                           for p in _PERCENT_RE.findall(s["evidence"])}
        if cited - purchase_shares - {offer["discount_percentage"]}:
            issues.append("quotes a discount that doesn't match the offer")
    return issues


# --------------------------------------------------------------------------
# Building the grounded recommendation list
# --------------------------------------------------------------------------

def _recommendation(candidate: dict, explanation: str, source: str, issues: list, selected_by: str) -> dict:
    return {
        **{key: candidate[key] for key in ("product_id", "name", "category", "subcategory", "color",
                                           "price", "season", "occasion", "store", "score", "types",
                                           "primary_type", "signals", "pairs_with", "offer")},
        "explanation": explanation,
        "explanation_source": source,
        "grounding_issues": issues,
        "selected_by": selected_by,
    }


def _build_recommendations(rows: list, customer_id: str, ctx: dict) -> tuple[list, list]:
    """Turn the agent's picks into grounded recommendations.

    Product facts, types, signals and offers come from the engine and the
    datasets, never from the model's text. Picks that break a hard rule are
    dropped, and an explanation that claims something the evidence doesn't
    support is replaced with one built from the evidence itself.
    """
    recommendations, dropped, seen = [], [], set()

    for row in rows:
        product_id = row.get("product_id")
        if product_id in seen:
            continue
        if product_id not in tools._PRODUCT_BY_ID:
            dropped.append({"product_id": product_id, "reason": "unknown product"})
            continue
        candidate = engine.evaluate_product(customer_id, product_id, ctx)
        if candidate["exclusion_reason"]:
            dropped.append({"product_id": product_id,
                            "reason": candidate["exclusion_reason"].replace("_", " ")})
            continue
        if not candidate["types"]:
            dropped.append({"product_id": product_id, "reason": "no personalisation signal"})
            continue

        explanation = _clean_explanation(row.get("explanation", ""), tools._PRODUCT_BY_ID[product_id])
        issues = grounding_issues(explanation, candidate) if explanation else ["empty explanation"]
        if issues:
            print(f"  ! {product_id}: replacing model explanation - {'; '.join(issues)}")
            recommendations.append(_recommendation(candidate, candidate["evidence_summary"],
                                                   "engine", issues, "agent"))
        else:
            recommendations.append(_recommendation(candidate, explanation, "agent", [], "agent"))
        seen.add(product_id)
        if len(recommendations) == MAX_RECOMMENDATIONS:
            break

    if len(recommendations) < MIN_RECOMMENDATIONS:
        ranked = engine.rank_recommendations(customer_id, ctx=ctx, limit=MAX_RECOMMENDATIONS * 2)
        for candidate in ranked["candidates"]:
            if len(recommendations) == MIN_RECOMMENDATIONS:
                break
            if candidate["product_id"] not in seen:
                recommendations.append(_recommendation(candidate, candidate["evidence_summary"],
                                                       "engine", [], "engine_top_up"))
                seen.add(candidate["product_id"])

    return recommendations, dropped


def _extract_rows(history: list, final_text: str) -> tuple[str, list]:
    summary, rows = _parse_final_text(final_text)
    if len(rows) >= MIN_RECOMMENDATIONS:
        return summary, rows

    print(f"  .. local parse found {len(rows)} recommendation(s), asking the model")
    try:
        response = _generate(
            model=MODEL,
            contents=history + [types.Content(role="user", parts=[types.Part(text=_EXTRACT_PROMPT)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RECOMMENDATION_SCHEMA,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        rows = json.loads(response.text)["recommendations"]
    except (AgentError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"  ! structured extraction unavailable ({exc}); keeping the local parse")
    return summary, rows


def _fallback_summary(ctx: dict) -> str:
    return f"{ctx['intent']['headline']} {ctx['purchases']['headline']}"


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

CACHE_VERSION = 2  # bump whenever the result shape changes, so stale runs are ignored
CACHE_DIR = Path(__file__).parent / ".agent_cache"
CACHE_ENABLED = os.environ.get("AGENT_CACHE") == "1"


def _cache_path(customer_id: str) -> Path:
    return CACHE_DIR / f"{customer_id}.v{CACHE_VERSION}.json"


def customer_intelligence(customer_id: str, ctx: dict | None = None) -> dict:
    """The deterministic analysis for a customer - no model call involved."""
    ctx = ctx or engine.build_customer_context(customer_id)
    return {
        "customer_id": customer_id,
        "profile": ctx["profile"],
        "gaps": ctx["gaps"],
        "purchase_patterns": ctx["purchases"],
        "browsing_intent": ctx["intent"],
        "seasonal_context": ctx["seasonal"],
    }


def run_agent(customer_id: str) -> dict:
    """Run the agentic loop for one customer and return structured output.

    With AGENT_CACHE=1 a completed run is saved and replayed on the next call,
    which keeps the demo usable on a free-tier key's daily quota.
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
        text=f"Build personalised recommendations for customer {customer_id}.")])]

    trace = []
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
                if call.name not in TOOL_IMPLS:
                    raise ValueError(f"unknown tool {call.name!r}")
                result = TOOL_IMPLS[call.name](**args)
                summary = _summarize(call.name, args, result)
                payload = {"result": result}
            except Exception as exc:                      # surface the error to the model
                summary = f"{call.name} failed: {exc}"
                payload = {"error": str(exc)}
                print(f"          ERROR {exc}")

            print(f"          -> {summary}")
            trace.append({"step": len(trace) + 1, "turn": turn, "tool": call.name,
                          "args": args, "summary": summary})
            response_parts.append(types.Part.from_function_response(name=call.name,
                                                                   response=payload))

        history.append(types.Content(role="user", parts=response_parts))
    else:
        capped = True
        print(f"\n!! WARNING: hit the {MAX_TURNS}-turn safety cap without a final answer.")
        final_text = (response.text or "").strip() if response else ""

    ctx = engine.build_customer_context(customer_id)
    summary, rows = _extract_rows(history, final_text) if final_text else ("", [])
    recommendations, dropped = _build_recommendations(rows, customer_id, ctx) if final_text else ([], [])

    rule = "-" * 74
    print(f"\n{rule}\nFINAL ANSWER\n{rule}\n{final_text or '(none)'}")
    print(f"\n{len(trace)} tool calls, {len(recommendations)} recommendations"
          + (f", {len(dropped)} dropped" if dropped else "")
          + (" [TURN CAP HIT]" if capped else ""))

    result = {
        **customer_intelligence(customer_id, ctx),
        "model": MODEL,
        "trace": trace,
        "summary": summary or _fallback_summary(ctx),
        "summary_source": "agent" if summary else "engine",
        "recommendations": recommendations,
        "dropped_recommendations": dropped,
        "final_text": final_text,
        "turn_capped": capped,
    }

    if CACHE_ENABLED and recommendations:
        CACHE_DIR.mkdir(exist_ok=True)
        _cache_path(customer_id).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[cache] saved run for {customer_id}")

    return result


if __name__ == "__main__":
    run_agent(sys.argv[1] if len(sys.argv) > 1 else "C001")
