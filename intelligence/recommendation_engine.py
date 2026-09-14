"""Multi-signal recommendation ranking.

Scores catalogue products for one customer by combining the evidence the
other intelligence modules produce: wardrobe gaps, browsing intent, purchase
patterns, seasonal context, stated preferences, complementary fit with what
they own, and live offers.

Deterministic and explainable. Every point a product earns is recorded as a
signal carrying the evidence behind it, so any ranking can be traced back to
the data. Weights all live in WEIGHTS below.

The agent decides when to call this, with what focus, and which ranked
candidates to put in front of the retailer. This module only ranks.
"""

from collections import Counter, defaultdict

import tools
from intelligence.gap_analysis import analyze_outfit_gaps, gap_matches
from intelligence.intent_analysis import detect_browsing_intent, intent_matches
from intelligence.purchase_analysis import analyze_purchase_patterns, purchase_matches
from intelligence.seasonal_trends import get_seasonal_context, seasonal_matches

RECOMMENDATION_TYPES = ("gap", "intent", "seasonal", "complementary")
TYPE_LABELS = {
    "gap": "wardrobe gap",
    "intent": "browsing intent",
    "seasonal": "seasonal",
    "complementary": "complementary",
}

# Points per signal. Gaps dominate because the gap analyzer is authoritative
# about what the customer lacks; intent is close behind because it is the
# freshest evidence of what they want. Preferences and purchase history refine
# the order within those, and offers break near-ties.
WEIGHTS = {
    "gap_missing_high": 30,
    "gap_missing_medium": 20,
    "gap_imbalance_high": 18,
    "gap_imbalance_medium": 12,
    "gap_occasion_high": 18,
    "gap_occasion_medium": 12,
    "gap_color": 6,

    "intent_category_strong": 18,
    "intent_category_moderate": 10,
    "intent_subcategory": 5,
    "intent_occasion": 4,
    "intent_color": 4,
    "intent_browsed_cart": 8,
    "intent_browsed_saved": 6,
    "intent_browsed_viewed": 3,

    "season_in": 6,
    "season_all": 2,
    "season_off": -6,
    "trend_subcategory": 5,
    "trend_category_high": 4,
    "trend_category_medium": 2,
    "trend_color": 2,
    "trend_style": 2,

    "complements_owned": 8,
    "complements_recent": 3,

    "pref_color": 8,
    "pref_style": 6,
    "pref_occasion": 5,

    "purchase_category": 4,
    "purchase_color": 4,
    "purchase_style": 3,
    "purchase_price": 4,

    "offer_base": 4,
    "offer_per_5_pct": 1,
    "offer_max": 10,

    "near_duplicate": -10,
}

# Owned categories each product category is worn with.
COMPLEMENTS = {
    "top": ("bottom", "outerwear"),
    "bottom": ("top", "shoes"),
    "dress": ("outerwear", "shoes", "accessory"),
    "outerwear": ("top", "bottom", "dress"),
    "shoes": ("bottom", "dress"),
    "accessory": ("top", "dress", "outerwear"),
}
# Colours treated as going with anything when checking a pairing.
NEUTRAL_COLORS = {"black", "white", "grey", "beige", "navy", "brown"}
MAX_PAIRS = 3

DEFAULT_LIMIT = 8
MAX_LIMIT = 20
MAX_PER_CATEGORY = 2

CART_EVENTS = {"added_to_cart", "abandoned_cart"}
BROWSE_VERBS = {
    "abandoned_cart": "left this exact product in an abandoned cart",
    "added_to_cart": "added this exact product to their cart",
    "saved": "saved this exact product",
    "viewed": "viewed this exact product",
}


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------

def build_customer_context(customer_id: str) -> dict:
    """Everything the ranker needs about one customer, computed once."""
    profile = tools.get_customer_profile(customer_id)
    purchases = analyze_purchase_patterns(customer_id)
    return {
        "profile": profile,
        "wardrobe": sorted(tools.get_wardrobe(customer_id), key=lambda i: i["date_acquired"]),
        "recent_ids": {p["product_id"] for p in purchases["recent_purchases"]},
        "gaps": analyze_outfit_gaps(customer_id),
        "purchases": purchases,
        "intent": detect_browsing_intent(customer_id),
        "seasonal": get_seasonal_context(customer_id),
    }


def exclusion_reason(product: dict, ctx: dict) -> str | None:
    """Hard rules no score can override."""
    profile = ctx["profile"]
    if product["price"] > profile["budget"]:
        return "over_budget"
    if product["color"] in (profile.get("avoided_colors") or []):
        return "avoided_color"
    if any(item["product_id"] == product["product_id"] for item in ctx["wardrobe"]):
        return "already_owned"
    return None


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def _gap_signals(product, ctx, add):
    preferred_colors = ctx["profile"].get("preferred_colors") or []
    for m in gap_matches(product, ctx["gaps"], preferred_colors):
        if m["kind"] == "missing_category":
            backed = "; their browsing backs it" if m["has_browsing_signal"] else ""
            add("gap", WEIGHTS[f"gap_missing_{m['priority']}"],
                f"Fills the {m['priority']}-priority missing {m['category']} gap "
                f"(they own none{backed})")
        elif m["kind"] == "imbalance":
            add("gap", WEIGHTS[f"gap_imbalance_{m['priority']}"],
                f"Eases their {m['oversupplied']} vs {m['category']} imbalance "
                f"({m['oversupplied_count']} vs {m['undersupplied_count']})")
        elif m["kind"] == "occasion":
            add("gap", WEIGHTS[f"gap_occasion_{m['priority']}"],
                f"Covers the {m['priority']}-priority {m['occasion']} occasion gap")
        elif m["kind"] == "color":
            add("gap", WEIGHTS["gap_color"],
                f"Adds a preferred colour ({m['color']}) to a wardrobe that has none")


def _intent_signals(product, ctx, add):
    for m in intent_matches(product, ctx["intent"]):
        if m["kind"] == "category":
            add("intent", WEIGHTS[f"intent_category_{m['strength']}"],
                f"{m['strength'].capitalize()} browsing intent for {m['category']} "
                f"({m['event_count']} event{'s' if m['event_count'] != 1 else ''})")
            if m["subcategory_match"]:
                add("intent", WEIGHTS["intent_subcategory"],
                    f"Same type they have been browsing ({product['subcategory']})")
        elif m["kind"] in ("occasion", "color"):
            add("intent", WEIGHTS[f"intent_{m['kind']}"],
                f"Their browsing centres on {m[m['kind']]} items")
        elif m["kind"] == "browsed_product":
            key = ("cart" if m["event_type"] in CART_EVENTS
                   else "saved" if m["event_type"] == "saved" else "viewed")
            views = f" ({m['view_count']} views)" if m["view_count"] > 1 else ""
            add("intent", WEIGHTS[f"intent_browsed_{key}"],
                f"Customer {BROWSE_VERBS[m['event_type']]}{views}")


def _seasonal_signals(product, ctx, add):
    season = ctx["seasonal"]["season"]
    fit = seasonal_matches(product, ctx["seasonal"])

    if fit["fit"] == "in_season":
        add("seasonal", WEIGHTS["season_in"], f"In season for {season}")
    elif fit["fit"] == "all_season":
        add("seasonal", WEIGHTS["season_all"], "All-season item")
    else:
        add("penalty", WEIGHTS["season_off"],
            f"Off-season ({product['season']} item during {season})")
        return fit  # trend points only count for something wearable now

    # Trend matches get their own group so an explanation that mentions a
    # trend can be checked against actual trend evidence, not just season fit.
    for m in fit["matches"]:
        if m["kind"] == "subcategory":
            add("trend", WEIGHTS["trend_subcategory"],
                f"{m['subcategory'].capitalize()} is on the curated {season} trend list")
        elif m["kind"] == "category":
            add("trend", WEIGHTS[f"trend_category_{m['demand']}"],
                f"{m['category'].capitalize()} has {m['demand']} curated {season} demand")
        elif m["kind"] == "color":
            add("trend", WEIGHTS["trend_color"], f"{m['color'].capitalize()} is a curated {season} colour")
        elif m["kind"] == "style":
            add("trend", WEIGHTS["trend_style"],
                f"{'/'.join(m['styles']).capitalize()} style is on the curated {season} trend list")
    return fit


def complement_pairs(product: dict, wardrobe: list) -> list:
    """Owned items this product would be worn with, most recent purchase first.

    A pairing needs a complementary category, the same occasion, and colours
    that go together (matching, or either one neutral).
    """
    partners = COMPLEMENTS.get(product["category"], ())
    pairs = []
    for item in reversed(wardrobe):
        if item["category"] not in partners or item["occasion"] != product["occasion"]:
            continue
        colours_work = (item["color"] == product["color"]
                        or item["color"] in NEUTRAL_COLORS or product["color"] in NEUTRAL_COLORS)
        if not colours_work:
            continue
        pairs.append({key: item[key] for key in ("product_id", "name", "category", "color",
                                                 "occasion", "date_acquired")})
        if len(pairs) == MAX_PAIRS:
            break
    return pairs


def _complement_signals(product, ctx, add):
    pairs = complement_pairs(product, ctx["wardrobe"])
    if not pairs:
        return pairs
    best = pairs[0]
    add("complementary", WEIGHTS["complements_owned"],
        f"Pairs with their {best['name']} (both for {best['occasion']})")
    recent = next((p for p in pairs if p["product_id"] in ctx["recent_ids"]), None)
    if recent:
        add("complementary", WEIGHTS["complements_recent"],
            f"Goes with one of their {len(ctx['recent_ids'])} latest purchases "
            f"({recent['name']}, bought {recent['date_acquired']})")
    return pairs


def _preference_signals(product, ctx, add):
    profile = ctx["profile"]
    if product["color"] in (profile.get("preferred_colors") or []):
        add("preference", WEIGHTS["pref_color"], f"In a preferred colour ({product['color']})")
    styles = [s for s in product["style_tags"] if s in (profile.get("preferred_styles") or [])]
    if styles:
        add("preference", WEIGHTS["pref_style"], f"Matches their preferred {'/'.join(styles)} style")
    if product["occasion"] in (profile.get("preferred_occasions") or []):
        add("preference", WEIGHTS["pref_occasion"], f"For a preferred occasion ({product['occasion']})")


def _purchase_signals(product, ctx, add):
    for m in purchase_matches(product, ctx["purchases"]):
        if m["kind"] == "category":
            add("purchase", WEIGHTS["purchase_category"],
                f"They have bought {m['count']} {m['category']} items before")
        elif m["kind"] == "color":
            add("purchase", WEIGHTS["purchase_color"], f"{m['count']} past purchases in {m['color']}")
        elif m["kind"] == "style":
            add("purchase", WEIGHTS["purchase_style"],
                f"{m['share_pct']}% of their purchases are {m['style']}")
        elif m["kind"] == "price":
            low, high = m["typical_range"]
            add("purchase", WEIGHTS["purchase_price"],
                f"Priced within their usual spend (Rs {low:,}-{high:,})")


def _offer_signal(product, ctx, add):
    offer = tools.check_offer(ctx["profile"]["customer_id"], product["product_id"])
    if offer:
        pct = offer["discount_percentage"] or 0
        points = min(WEIGHTS["offer_base"] + (pct // 5) * WEIGHTS["offer_per_5_pct"], WEIGHTS["offer_max"])
        label = ("free shipping" if offer["offer_type"] == "free_shipping"
                 else f"{pct}% {offer['offer_type'].replace('_', ' ')}")
        add("offer", points, f"Active offer: {label}, valid until {offer['valid_until']}")
    return offer


def _duplicate_signal(product, ctx, add):
    duplicate = next((i for i in ctx["wardrobe"]
                      if i["subcategory"] == product["subcategory"] and i["color"] == product["color"]),
                     None)
    if duplicate:
        add("penalty", WEIGHTS["near_duplicate"],
            f"Very similar to their {duplicate['name']} (same type and colour)")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_product(product: dict, ctx: dict) -> dict:
    """Score one product for one customer, keeping every signal and its evidence."""
    signals = []

    def add(group, points, evidence):
        signals.append({"group": group, "points": points, "evidence": evidence})

    _gap_signals(product, ctx, add)
    _intent_signals(product, ctx, add)
    season_fit = _seasonal_signals(product, ctx, add)
    pairs = _complement_signals(product, ctx, add)
    _preference_signals(product, ctx, add)
    _purchase_signals(product, ctx, add)
    offer = _offer_signal(product, ctx, add)
    _duplicate_signal(product, ctx, add)

    points_by_group = defaultdict(int)
    for s in signals:
        points_by_group[s["group"]] += s["points"]

    # A type is only claimed when its defining evidence is present - not just
    # because the group scored a point or two.
    intent_kinds = {m["kind"] for m in intent_matches(product, ctx["intent"])}
    trend_kinds = {m["kind"] for m in season_fit["matches"]}
    high_demand = any(m["kind"] == "category" and m["demand"] == "high" for m in season_fit["matches"])
    types = []
    if points_by_group["gap"] > 0:
        types.append("gap")
    if intent_kinds & {"category", "browsed_product"}:
        types.append("intent")
    # Seasonal needs a trending item type or high seasonal demand - being a top
    # in a season where tops have "medium" demand isn't a reason on its own.
    if ((season_fit["fit"] == "in_season" and ("subcategory" in trend_kinds or high_demand))
            or (season_fit["fit"] == "all_season" and "subcategory" in trend_kinds)):
        types.append("seasonal")
    if pairs:
        types.append("complementary")

    candidate = {
        "product_id": product["product_id"],
        "name": product["name"],
        "category": product["category"],
        "subcategory": product["subcategory"],
        "color": product["color"],
        "price": product["price"],
        "season": product["season"],
        "occasion": product["occasion"],
        "store": product["store"],
        "score": sum(s["points"] for s in signals),
        "types": types,
        # Precedence, not points: RECOMMENDATION_TYPES is ordered by authority, so
        # a product that fills a reported gap is always a gap pick first.
        "primary_type": types[0] if types else None,
        "signals": sorted(signals, key=lambda s: -s["points"]),
        "pairs_with": pairs,
        "offer": offer,
    }
    candidate["evidence_summary"] = explain(candidate)
    return candidate


def explain(candidate: dict) -> str:
    """A plain sentence built only from the candidate's recorded evidence."""
    positives = [s for s in candidate["signals"] if s["points"] > 0][:3]
    if not positives:
        return "No personalisation signal."
    reasons = "; ".join(s["evidence"][:1].lower() + s["evidence"][1:] for s in positives)
    label = TYPE_LABELS.get(candidate["primary_type"], "general")
    return f"Recommended as a {label} pick: {reasons}."


def evaluate_product(customer_id: str, product_id: str, ctx: dict | None = None) -> dict:
    """Score a specific product, including why it would be excluded if it is."""
    ctx = ctx or build_customer_context(customer_id)
    product = tools._PRODUCT_BY_ID.get(product_id)
    if product is None:
        raise ValueError(f"Unknown product_id {product_id!r}")
    candidate = score_product(product, ctx)
    candidate["exclusion_reason"] = exclusion_reason(product, ctx)
    return candidate


def _diversify(scored: list, limit: int, cap_categories: bool) -> list:
    """Top candidates with no repeated names and, unless focused, a per-category cap."""
    chosen, names, per_category = [], set(), Counter()
    for candidate in scored:
        if candidate["name"] in names:
            continue
        if cap_categories and per_category[candidate["category"]] >= MAX_PER_CATEGORY:
            continue
        chosen.append(candidate)
        names.add(candidate["name"])
        per_category[candidate["category"]] += 1
        if len(chosen) == limit:
            return chosen
    # Not enough variety to fill the list - top up by score, still skipping repeats.
    for candidate in scored:
        if len(chosen) == limit:
            break
        if candidate["name"] not in names:
            chosen.append(candidate)
            names.add(candidate["name"])
    return chosen


def rank_recommendations(customer_id: str, category: str | None = None,
                         recommendation_type: str | None = None,
                         limit: int = DEFAULT_LIMIT, ctx: dict | None = None) -> dict:
    """Rank eligible products for a customer, optionally focused on a category or type."""
    if recommendation_type and recommendation_type not in RECOMMENDATION_TYPES:
        raise ValueError(f"recommendation_type must be one of {', '.join(RECOMMENDATION_TYPES)}")
    ctx = ctx or build_customer_context(customer_id)
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    excluded, scored, considered = Counter(), [], 0
    for product in tools.PRODUCTS:
        if category and product["category"] != category:
            continue
        considered += 1
        reason = exclusion_reason(product, ctx)
        if reason:
            excluded[reason] += 1
            continue
        candidate = score_product(product, ctx)
        if not candidate["types"]:
            excluded["no_personalised_signal"] += 1
            continue
        if recommendation_type and recommendation_type not in candidate["types"]:
            continue
        scored.append(candidate)

    scored.sort(key=lambda c: (-c["score"], c["price"], c["product_id"]))
    return {
        "customer_id": customer_id,
        "filters": {"category": category, "recommendation_type": recommendation_type, "limit": limit},
        "considered": considered,
        "eligible": len(scored),
        "excluded": dict(excluded),
        "candidates": _diversify(scored, limit, cap_categories=category is None),
    }
