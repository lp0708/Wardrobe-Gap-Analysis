"""Seasonal context for a customer.

Two sources, kept separate so neither is over-claimed:

  curated trends   seasonal_trends.json - a small hand-written dataset for this
                   prototype (trending categories, subcategories, colours and
                   styles per season). Demo data, not a forecast; it says so in
                   its own `source` field, which is passed through to the UI.
  observed demand  what shoppers across the whole dataset have actually been
                   browsing, computed from browsing_history.json. Real, but a
                   small sample, so it is reported as context and never scored.

The customer's season comes from their profile's current_season field.
"""

import json
from collections import Counter

import tools

with open(tools.DATA_DIR / "seasonal_trends.json", encoding="utf-8") as _fh:
    TRENDS = json.load(_fh)

OBSERVED_TOP_N = 3


def _observed_demand() -> dict:
    events = tools.BROWSING_HISTORY
    categories = Counter(tools._PRODUCT_BY_ID[e["product_id"]]["category"]
                         for e in events if e["product_id"] in tools._PRODUCT_BY_ID)
    total = sum(categories.values())
    return {
        "event_count": total,
        "customer_count": len({e["customer_id"] for e in events}),
        "top_categories": [{"category": c, "events": n, "share_pct": round(n / total * 100)}
                           for c, n in categories.most_common(OBSERVED_TOP_N)] if total else [],
    }


def _headline(season: str, trend: dict | None, matched_colors: list) -> str:
    if trend is None:
        return f"No curated trend data for {season}."
    high = [c for c, level in trend["trending_categories"].items() if level == "high"]
    text = (f"{season.capitalize()}: {', '.join(trend['trending_subcategories'])} are on the "
            f"curated trend list; {' and '.join(high)} in high demand")
    if matched_colors:
        text += f"; {', '.join(matched_colors)} {'is' if len(matched_colors) == 1 else 'are'} both in season and a preferred colour"
    return text + "."


def get_seasonal_context(customer_id: str) -> dict:
    """The seasonal signals that apply to this customer right now."""
    profile = tools.get_customer_profile(customer_id)
    season = profile["current_season"]
    trend = TRENDS["seasons"].get(season)

    avoided = set(profile.get("avoided_colors") or [])
    in_season = [p for p in tools.PRODUCTS if p["season"] == season]
    shoppable = [p for p in in_season if p["price"] <= profile["budget"] and p["color"] not in avoided]

    trending_subcategories = trend["trending_subcategories"] if trend else []
    relevant_colors = trend["relevant_colors"] if trend else []
    popular_styles = trend["popular_styles"] if trend else []
    matched_colors = [c for c in relevant_colors if c in (profile.get("preferred_colors") or [])]
    matched_styles = [s for s in popular_styles if s in (profile.get("preferred_styles") or [])]

    return {
        "customer_id": customer_id,
        "season": season,
        "has_trend_data": trend is not None,
        "source": TRENDS["source"],
        "trending_categories": trend["trending_categories"] if trend else {},
        "trending_subcategories": trending_subcategories,
        "relevant_colors": relevant_colors,
        "popular_styles": popular_styles,
        "notes": trend["notes"] if trend else "",
        "matches_customer": {"colors": matched_colors, "styles": matched_styles},
        "in_season_catalogue": {
            "total": len(in_season),
            "within_budget": len(shoppable),
            "trending_within_budget": sum(1 for p in shoppable
                                          if p["subcategory"] in trending_subcategories),
        },
        "observed_demand": _observed_demand(),
        "headline": _headline(season, trend, matched_colors),
    }


def seasonal_matches(product: dict, context: dict) -> dict:
    """How a product sits against the customer's season and the curated trends."""
    season = context["season"]
    if product["season"] == season:
        fit = "in_season"
    elif product["season"] == "all-season":
        fit = "all_season"
    else:
        fit = "off_season"

    matches = []
    demand = context["trending_categories"].get(product["category"])
    if demand:
        matches.append({"kind": "category", "category": product["category"], "demand": demand})
    if product["subcategory"] in context["trending_subcategories"]:
        matches.append({"kind": "subcategory", "subcategory": product["subcategory"]})
    if product["color"] in context["relevant_colors"]:
        matches.append({"kind": "color", "color": product["color"]})
    styles = [s for s in product["style_tags"] if s in context["popular_styles"]]
    if styles:
        matches.append({"kind": "style", "styles": styles})

    return {"fit": fit, "product_season": product["season"], "matches": matches}
