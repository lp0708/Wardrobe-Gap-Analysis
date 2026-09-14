"""Purchase-pattern analysis.

The wardrobe dataset doubles as the purchase log: every row is an item the
customer bought, with the date and the price they actually paid. This module
condenses that log into a buying profile - what they buy, in which colours
and styles, what they spend and what they buy more than once.

Deterministic, no LLM. With fewer than MIN_PURCHASES rows it still reports the
raw facts but marks the patterns unreliable instead of generalising from one
or two purchases.
"""

from collections import Counter, defaultdict
from datetime import date

import tools

MIN_PURCHASES = 3
REPEAT_THRESHOLD = 2        # bought this many times = a preference, not a one-off
RECENT_COUNT = 3
DOMINANT_STYLE_SHARE = 50   # percent of purchases carrying a style tag


def _percentile(sorted_values: list, fraction: float) -> int:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return round(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low))


def _frequency(values: list, total: int, key: str) -> list:
    return [{key: value, "count": count, "share_pct": round(count / total * 100)}
            for value, count in Counter(values).most_common()]


def _spend(prices: list, budget: int) -> dict | None:
    if not prices:
        return None
    prices = sorted(prices)
    average = round(sum(prices) / len(prices))
    # The interquartile range is a fairer "usual spend" than min-max once there
    # are enough purchases for one outlier not to dominate.
    typical = ([_percentile(prices, 0.25), _percentile(prices, 0.75)]
               if len(prices) >= 4 else [prices[0], prices[-1]])
    return {
        "total": sum(prices),
        "average": average,
        "median": _percentile(prices, 0.5),
        "min": prices[0],
        "max": prices[-1],
        "typical_range": typical,
        "budget": budget,
        "average_vs_budget_pct": round(average / budget * 100) if budget else None,
    }


def _leaders(frequency: list, key: str) -> tuple | None:
    """Every value tied for the top count, or None if nothing was bought twice.

    Naming a single "favourite" out of a tie would overstate the data.
    """
    if not frequency or frequency[0]["count"] < REPEAT_THRESHOLD:
        return None
    top = frequency[0]["count"]
    names = [row[key] for row in frequency if row["count"] == top]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return joined, top


def _headline(purchases: list, patterns: dict) -> str:
    n = len(purchases)
    if not n:
        return "No purchase history on record."
    spend = patterns["spend"]
    if not patterns["has_sufficient_history"]:
        items = ", ".join(f"{p['color']} {p['subcategory']}" for p in purchases)
        return (f"Only {n} purchase{'s' if n != 1 else ''} on record ({items}, "
                f"Rs {spend['total']:,}) - too few to establish buying patterns.")

    first = date.fromisoformat(purchases[0]["date_acquired"])
    last = date.fromisoformat(purchases[-1]["date_acquired"])
    parts = [f"{n} purchases, {first:%b %Y} to {last:%b %Y}"]

    categories = _leaders(patterns["category_frequency"], "category")
    if categories:
        names, count = categories
        parts.append(f"buys {names} most often ({count}{' each' if ' and ' in names else ''})")
    colors = _leaders(patterns["color_frequency"], "color")
    if colors:
        names, count = colors
        parts.append(f"favours {names} ({count}{' each' if ' and ' in names else ''} of {n})")
    if patterns["repeat_purchases"]:
        repeat = patterns["repeat_purchases"][0]
        parts.append(f"repeat buyer of {repeat['subcategory']} ({repeat['count']})")
    low, high = spend["typical_range"]
    parts.append(f"usually spends Rs {low:,}-{high:,}, avg Rs {spend['average']:,} "
                 f"({spend['average_vs_budget_pct']}% of budget)")
    return "; ".join(parts) + "."


def analyze_purchase_patterns(customer_id: str) -> dict:
    """Summarise how the customer actually buys."""
    profile = tools.get_customer_profile(customer_id)
    purchases = sorted(tools.get_wardrobe(customer_id), key=lambda p: p["date_acquired"])
    n = len(purchases)
    sufficient = n >= MIN_PURCHASES

    by_subcategory = defaultdict(list)
    for p in purchases:
        by_subcategory[(p["category"], p["subcategory"])].append(p["product_id"])

    category_frequency = _frequency([p["category"] for p in purchases], n, "category") if n else []
    color_frequency = _frequency([p["color"] for p in purchases], n, "color") if n else []
    style_frequency = _frequency([t for p in purchases for t in p["style_tags"]], n, "style") if n else []
    stated_colors = sorted(set(profile.get("preferred_colors") or []))
    matching = sum(1 for p in purchases if p["color"] in stated_colors)

    patterns = {
        "customer_id": customer_id,
        "purchase_count": n,
        "has_sufficient_history": sufficient,
        "first_purchase": purchases[0]["date_acquired"] if n else None,
        "last_purchase": purchases[-1]["date_acquired"] if n else None,
        "spend": _spend([p["price_paid"] for p in purchases], profile["budget"]),
        "category_frequency": category_frequency,
        "color_frequency": color_frequency,
        "style_frequency": style_frequency,
        "occasion_frequency": _frequency([p["occasion"] for p in purchases], n, "occasion") if n else [],
        # Preferences are only claimed once something has been bought repeatedly.
        "preferred_categories": [r["category"] for r in category_frequency
                                 if sufficient and r["count"] >= REPEAT_THRESHOLD],
        "preferred_colors": [r["color"] for r in color_frequency
                             if sufficient and r["count"] >= REPEAT_THRESHOLD],
        "dominant_styles": [r["style"] for r in style_frequency
                            if sufficient and r["share_pct"] >= DOMINANT_STYLE_SHARE],
        "repeat_purchases": sorted(
            ({"category": cat, "subcategory": sub, "count": len(ids), "product_ids": ids}
             for (cat, sub), ids in by_subcategory.items() if len(ids) >= REPEAT_THRESHOLD),
            key=lambda r: -r["count"],
        ),
        "recent_purchases": [
            {key: p[key] for key in ("product_id", "name", "category", "subcategory",
                                     "color", "date_acquired", "price_paid")}
            for p in reversed(purchases[-RECENT_COUNT:])
        ],
        "stated_color_alignment": {
            "stated_colors": stated_colors,
            "matching_purchases": matching,
            "share_pct": round(matching / n * 100) if n else None,
        },
    }
    patterns["headline"] = _headline(purchases, patterns)
    return patterns


def purchase_matches(product: dict, patterns: dict) -> list:
    """Which established buying patterns this product fits. Empty when history is too thin."""
    if not patterns["has_sufficient_history"]:
        return []

    matches = []
    if product["category"] in patterns["preferred_categories"]:
        row = next(r for r in patterns["category_frequency"] if r["category"] == product["category"])
        matches.append({"kind": "category", "category": product["category"], "count": row["count"]})
    if product["color"] in patterns["preferred_colors"]:
        row = next(r for r in patterns["color_frequency"] if r["color"] == product["color"])
        matches.append({"kind": "color", "color": product["color"], "count": row["count"]})
    styles = [s for s in product["style_tags"] if s in patterns["dominant_styles"]]
    if styles:
        row = next(r for r in patterns["style_frequency"] if r["style"] == styles[0])
        matches.append({"kind": "style", "style": styles[0], "share_pct": row["share_pct"]})
    low, high = patterns["spend"]["typical_range"]
    if low <= product["price"] <= high:
        matches.append({"kind": "price", "typical_range": [low, high]})
    return matches
