"""Deterministic wardrobe gap detection.

No LLM calls live here - the agent calls analyze_outfit_gaps() as a tool and
reasons over its output. Everything below is plain Python over the joined
records that tools.py returns.
"""

from collections import Counter

from tools import get_browsing_history, get_customer_profile, get_wardrobe

# The full category set a complete wardrobe covers.
ALL_CATEGORIES = ["top", "bottom", "dress", "outerwear", "shoes", "accessory"]

# A dress satisfies the top+bottom combo need, so owning dresses suppresses
# a "missing top" / "missing bottom" flag.
COMBO_SUBSTITUTE = "dress"

# Categories that pair with each other to make an outfit. Each entry is
# (category_a, category_b, counts_dresses_toward_b).
#
#   top <-> bottom            a dress adds to BOTH sides, so it cancels out of
#                             the difference - raw counts are already correct.
#   outerwear <-> top         outerwear layers over a base, and a dress is a
#                             perfectly good base, so dresses count toward top.
PAIRS = [
    ("top", "bottom", False),
    ("outerwear", "top", True),
]

IMBALANCE_THRESHOLD = 3


def _category_counts(wardrobe: list[dict]) -> Counter:
    return Counter(item["category"] for item in wardrobe)


def _browsing_index(history: list[dict]) -> tuple[dict, dict]:
    """Map browsed category -> product_ids, and browsed occasion -> product_ids.

    Every event type counts as a signal: viewed, saved, added_to_cart and
    abandoned_cart all indicate the customer was looking at that item.
    """
    by_category: dict[str, list[str]] = {}
    by_occasion: dict[str, list[str]] = {}
    for event in history:
        by_category.setdefault(event["category"], []).append(event["product_id"])
        by_occasion.setdefault(event["occasion"], []).append(event["product_id"])
    return by_category, by_occasion


def _signal(supporting: list[str]) -> dict:
    """Priority/evidence fields shared by every gap type."""
    if supporting:
        return {
            "priority": "high",
            "has_browsing_signal": True,
            "supporting_product_ids": sorted(set(supporting)),
        }
    return {"priority": "medium", "has_browsing_signal": False, "supporting_product_ids": []}


def analyze_outfit_gaps(customer_id: str) -> dict:
    """Return the full gap profile for one customer.

    Detects missing categories, category imbalances, occasion gaps and a
    colour gap, then cross-references browsing history to raise the priority
    of any gap the customer has already shown interest in.
    """
    profile = get_customer_profile(customer_id)
    wardrobe = get_wardrobe(customer_id)
    history = get_browsing_history(customer_id)

    counts = _category_counts(wardrobe)
    browsed_categories, browsed_occasions = _browsing_index(history)
    owns_substitute = counts.get(COMBO_SUBSTITUTE, 0) > 0

    # ---- 1. missing categories -------------------------------------------
    missing_categories = []
    missing_names = set()
    for category in ALL_CATEGORIES:
        if counts.get(category, 0) > 0:
            continue
        # A customer who owns dresses is not missing a top or a bottom - the
        # dress already covers that combo.
        if category in ("top", "bottom") and owns_substitute:
            continue
        missing_names.add(category)
        missing_categories.append(
            {"category": category, **_signal(browsed_categories.get(category, []))}
        )

    # ---- 2. category imbalances ------------------------------------------
    imbalances = []
    for cat_a, cat_b, dresses_count_toward_b in PAIRS:
        count_a = counts.get(cat_a, 0)
        count_b = counts.get(cat_b, 0)
        if dresses_count_toward_b:
            count_b += counts.get(COMBO_SUBSTITUTE, 0)

        if count_a - count_b >= IMBALANCE_THRESHOLD:
            over, over_n, under, under_n = cat_a, count_a, cat_b, count_b
        elif count_b - count_a >= IMBALANCE_THRESHOLD:
            over, over_n, under, under_n = cat_b, count_b, cat_a, count_a
        else:
            continue

        # If the undersupplied side is already reported as a missing category,
        # that is the stronger and clearer claim - don't report it twice.
        if under in missing_names:
            continue

        imbalances.append(
            {
                "oversupplied": over,
                "oversupplied_count": over_n,
                "undersupplied": under,
                "undersupplied_count": under_n,
                **_signal(browsed_categories.get(under, [])),
            }
        )

    # ---- 3. occasion gaps -------------------------------------------------
    owned_occasions = {item["occasion"] for item in wardrobe}
    occasion_gaps = [
        {"occasion": occasion, **_signal(browsed_occasions.get(occasion, []))}
        for occasion in profile.get("preferred_occasions") or []
        if occasion not in owned_occasions
    ]

    # ---- 4. colour gap ----------------------------------------------------
    preferred_colors = profile.get("preferred_colors") or []
    owned_colors = {item["color"] for item in wardrobe}
    color_gap = bool(preferred_colors) and not (owned_colors & set(preferred_colors))

    return {
        "customer_id": customer_id,
        "missing_categories": missing_categories,
        "imbalances": imbalances,
        "occasion_gaps": occasion_gaps,
        "color_gap": color_gap,
    }
