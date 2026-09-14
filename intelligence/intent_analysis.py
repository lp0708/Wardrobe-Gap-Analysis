"""Browsing-intent detection.

Turns a customer's raw browsing events into a scored statement of what they
are shopping for right now, together with the events that support it.
Deterministic, no LLM. When the evidence is thin - a single product viewed
once - it says so rather than inventing an intent.
"""

from collections import Counter, defaultdict
from datetime import date

import tools

# How much each event type says about purchase intent. Cart events are the
# strongest signal a shopper gives short of buying.
EVENT_WEIGHTS = {"viewed": 1.0, "saved": 2.0, "added_to_cart": 3.0, "abandoned_cart": 3.0}
CART_OR_SAVE = {"saved", "added_to_cart", "abandoned_cart"}

# Repeat views of the same product raise its weight, up to a cap.
REPEAT_VIEW_BONUS = 0.25
MAX_COUNTED_VIEWS = 5
REPEAT_VIEW_THRESHOLD = 3   # views at which a plain "viewed" event counts as high intent

# Recency multipliers by age in days, measured against the dataset snapshot.
RECENCY_BANDS = ((3, 1.0), (7, 0.8))
OLDER_EVENT_MULTIPLIER = 0.6

# Calibrated on this dataset: a save plus a cart event clears STRONG, while a
# single plain view never clears MODERATE.
STRONG_SCORE = 4.5
MODERATE_SCORE = 2.5
MIN_EVENTS_FOR_STRONG = 2

# A season, colour or occasion is only called out for a category when it
# carries at least this share of that category's weight.
DOMINANT_SHARE = 0.6


def snapshot_date() -> date:
    """The latest browsing timestamp in the dataset.

    Recency is measured against this rather than the wall clock, so the same
    data yields the same intent no matter how long after collection it runs.
    """
    if not tools.BROWSING_HISTORY:
        return date.today()
    return max(date.fromisoformat(e["timestamp"]) for e in tools.BROWSING_HISTORY)


def _event_weight(event: dict, as_of: date) -> float:
    views = min(max(event.get("view_count") or 1, 1), MAX_COUNTED_VIEWS)
    age_days = (as_of - date.fromisoformat(event["timestamp"])).days
    recency = next((m for limit, m in RECENCY_BANDS if age_days <= limit), OLDER_EVENT_MULTIPLIER)
    base = EVENT_WEIGHTS.get(event["event_type"], EVENT_WEIGHTS["viewed"])
    return round(base * (1 + REPEAT_VIEW_BONUS * (views - 1)) * recency, 2)


def _strength(score: float, event_count: int, min_events_for_moderate: int) -> str:
    if score >= STRONG_SCORE and event_count >= MIN_EVENTS_FOR_STRONG:
        return "strong"
    if score >= MODERATE_SCORE and event_count >= min_events_for_moderate:
        return "moderate"
    return "weak"


def _dominant(weight_by_value: dict) -> str | None:
    total = sum(weight_by_value.values())
    if not total:
        return None
    value, weight = max(weight_by_value.items(), key=lambda kv: kv[1])
    return value if weight / total >= DOMINANT_SHARE else None


def _group(events: list, field: str, min_events_for_moderate: int) -> list:
    """Aggregate weighted events by one product field, strongest first."""
    groups = defaultdict(list)
    for event in events:
        groups[event[field]].append(event)

    rows = []
    for value, group in groups.items():
        score = round(sum(e["weight"] for e in group), 2)
        rows.append({
            field: value,
            "score": score,
            "strength": _strength(score, len(group), min_events_for_moderate),
            "event_count": len(group),
            "product_ids": sorted({e["product_id"] for e in group}),
        })
    return sorted(rows, key=lambda r: -r["score"])


def _category_intents(events: list) -> list:
    # Two events minimum: one abandoned shirt is interest in that shirt (see
    # high_intent_products), not evidence the customer is shopping for tops.
    rows = _group(events, "category", min_events_for_moderate=2)
    for row in rows:
        group = [e for e in events if e["category"] == row["category"]]
        row["subcategories"] = sorted({e["subcategory"] for e in group})
        row["event_types"] = dict(Counter(e["event_type"] for e in group))
        row["total_views"] = sum(e["view_count"] for e in group)
        for facet in ("season", "color", "occasion"):
            weights = defaultdict(float)
            for e in group:
                weights[e[facet]] += e["weight"]
            # One event can't establish a "dominant" anything.
            row[f"dominant_{facet}"] = _dominant(weights) if len(group) >= 2 else None
    return rows


STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}


def _headline(category_intents: list, occasion_intents: list, events: list) -> str:
    if not events:
        return "No browsing activity on record."

    top = category_intents[0]
    top_occasion = occasion_intents[0] if occasion_intents else None
    if STRENGTH_RANK[top["strength"]] == 0 and (
            top_occasion is None or STRENGTH_RANK[top_occasion["strength"]] == 0):
        views = sum(e["view_count"] for e in events)
        return (f"Not enough browsing to infer intent ({len(events)} "
                f"event{'s' if len(events) != 1 else ''}, {views} "
                f"view{'s' if views != 1 else ''} in total).")

    # Lead with whichever dimension carries the stronger signal: a shopper
    # browsing office shirts and cardigans is shopping for office wear.
    if top_occasion and STRENGTH_RANK[top_occasion["strength"]] > STRENGTH_RANK[top["strength"]]:
        group = [e for e in events if e["occasion"] == top_occasion["occasion"]]
        categories = sorted({e["category"] for e in group})
        text = (f"{top_occasion['strength'].capitalize()} interest in {top_occasion['occasion']} "
                f"wear ({', '.join(categories)})")
    else:
        group = [e for e in events if e["category"] == top["category"]]
        text = f"{top['strength'].capitalize()} interest in {top['category']} ({', '.join(top['subcategories'])})"
        if top["dominant_season"] and top["dominant_season"] != "all-season":
            text += f", mostly {top['dominant_season']}-season pieces"

    carted = sum(1 for e in group if e["event_type"] in CART_OR_SAVE)
    if carted:
        text += f"; {carted} saved or carted"
    return text + "."


def detect_browsing_intent(customer_id: str) -> dict:
    """Score what the customer is currently shopping for, with its evidence."""
    tools.get_customer_profile(customer_id)  # raises ValueError for unknown ids
    as_of = snapshot_date()
    events = [{**e, "weight": _event_weight(e, as_of)}
              for e in tools.get_browsing_history(customer_id)]

    category_intents = _category_intents(events)
    # Occasion and colour need two events before they count as a pattern.
    occasion_intents = _group(events, "occasion", min_events_for_moderate=2)
    high_intent = sorted(
        (
            {key: e[key] for key in ("product_id", "name", "category", "subcategory",
                                     "event_type", "view_count", "timestamp", "weight")}
            for e in events
            if e["event_type"] in CART_OR_SAVE or e["view_count"] >= REPEAT_VIEW_THRESHOLD
        ),
        key=lambda e: -e["weight"],
    )

    return {
        "customer_id": customer_id,
        "as_of": as_of.isoformat(),
        "event_count": len(events),
        "has_sufficient_evidence": any(r["strength"] != "weak"
                                       for r in category_intents + occasion_intents),
        "headline": _headline(category_intents, occasion_intents, events),
        "category_intents": category_intents,
        "occasion_intents": occasion_intents,
        "color_intents": _group(events, "color", min_events_for_moderate=2),
        "high_intent_products": high_intent,
    }


def intent_matches(product: dict, intent: dict) -> list:
    """Which non-weak intent signals this product lines up with."""
    matches = []
    for row in intent["category_intents"]:
        if row["category"] == product["category"] and row["strength"] != "weak":
            matches.append({
                "kind": "category",
                "strength": row["strength"],
                "category": row["category"],
                "event_count": row["event_count"],
                "subcategory_match": product["subcategory"] in row["subcategories"],
            })
    for field in ("occasion", "color"):
        for row in intent[f"{field}_intents"]:
            if row[field] == product[field] and row["strength"] != "weak":
                matches.append({"kind": field, "strength": row["strength"], field: row[field],
                                "event_count": row["event_count"]})
    for event in intent["high_intent_products"]:
        if event["product_id"] == product["product_id"]:
            matches.append({"kind": "browsed_product", "event_type": event["event_type"],
                            "view_count": event["view_count"]})
    return matches
