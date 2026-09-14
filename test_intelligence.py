"""Checks the intelligence layer against the raw datasets for every customer.

Each module's output is recomputed or cross-checked independently from the
JSON files, so a passing run means the evidence the agent reasons over is
actually true - not just that the code ran. No API calls.
"""

import sys
from collections import Counter

import tools
from intelligence import recommendation_engine as engine
from intelligence.gap_analysis import gap_matches
from intelligence.intent_analysis import CART_OR_SAVE, REPEAT_VIEW_THRESHOLD

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CATEGORIES = {p["category"] for p in tools.PRODUCTS}
SUBCATEGORIES = {p["subcategory"] for p in tools.PRODUCTS}
COLORS = {p["color"] for p in tools.PRODUCTS}
STYLES = {t for p in tools.PRODUCTS for t in p["style_tags"]}

checks = 0
failures = []


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def check_purchases(cid: str, ctx: dict) -> None:
    raw = [w for w in tools.WARDROBES if w["customer_id"] == cid]
    p = ctx["purchases"]
    check(p["purchase_count"] == len(raw), f"{cid} purchase count")
    if not raw:
        return
    check(p["spend"]["total"] == sum(w["price_paid"] for w in raw), f"{cid} total spend")
    check(p["spend"]["min"] <= p["spend"]["typical_range"][0] <= p["spend"]["typical_range"][1]
          <= p["spend"]["max"], f"{cid} typical range inside min-max")

    categories = Counter(tools._PRODUCT_BY_ID[w["owned_product_id"]]["category"] for w in raw)
    for row in p["category_frequency"]:
        check(categories[row["category"]] == row["count"], f"{cid} category count {row['category']}")
    for category in p["preferred_categories"]:
        check(categories[category] >= 2, f"{cid} preferred category {category} bought twice")
    if not p["has_sufficient_history"]:
        check(not (p["preferred_categories"] or p["preferred_colors"] or p["dominant_styles"]),
              f"{cid} thin history claims no preferences")

    # Purchases can share a date, so compare dates rather than tie order.
    recent_dates = [r["date_acquired"] for r in p["recent_purchases"]]
    latest_dates = sorted((w["date_acquired"] for w in raw), reverse=True)[:len(recent_dates)]
    check(recent_dates == latest_dates, f"{cid} recent purchases are the latest by date")


def check_intent(cid: str, ctx: dict) -> None:
    raw = [b for b in tools.BROWSING_HISTORY if b["customer_id"] == cid]
    browsed = {b["product_id"] for b in raw}
    intent = ctx["intent"]
    check(intent["event_count"] == len(raw), f"{cid} intent event count")

    for dimension in ("category_intents", "occasion_intents", "color_intents"):
        for row in intent[dimension]:
            check(set(row["product_ids"]) <= browsed, f"{cid} {dimension} cites only browsed products")
            if row["strength"] != "weak":
                check(row["event_count"] >= 2, f"{cid} {dimension} non-weak needs 2+ events")

    for event in intent["high_intent_products"]:
        check(event["product_id"] in browsed, f"{cid} high-intent product was browsed")
        check(event["event_type"] in CART_OR_SAVE or event["view_count"] >= REPEAT_VIEW_THRESHOLD,
              f"{cid} high-intent product has a cart/save or repeat views")

    has_signal = any(r["strength"] != "weak"
                     for r in intent["category_intents"] + intent["occasion_intents"])
    check(intent["has_sufficient_evidence"] == has_signal, f"{cid} sufficiency flag")
    if not has_signal:
        check(intent["headline"].startswith(("Not enough", "No browsing")),
              f"{cid} thin browsing headline does not claim intent")


def check_seasonal(cid: str, ctx: dict) -> None:
    s = ctx["seasonal"]
    check(s["season"] == ctx["profile"]["current_season"], f"{cid} season from profile")
    check(set(s["trending_categories"]) <= CATEGORIES, f"{cid} trend categories exist in catalogue")
    check(set(s["trending_subcategories"]) <= SUBCATEGORIES, f"{cid} trend subcategories exist")
    check(set(s["relevant_colors"]) <= COLORS, f"{cid} trend colours exist")
    check(set(s["popular_styles"]) <= STYLES, f"{cid} trend styles exist")
    check(s["observed_demand"]["event_count"] == len(tools.BROWSING_HISTORY), f"{cid} observed demand total")
    check(s["in_season_catalogue"]["total"] == sum(1 for p in tools.PRODUCTS if p["season"] == s["season"]),
          f"{cid} in-season catalogue count")
    check("curated" in s["source"].lower(), f"{cid} trend source labelled as curated")


def check_ranking(cid: str, ctx: dict) -> list:
    profile = ctx["profile"]
    owned = {i["product_id"] for i in ctx["wardrobe"]}
    ranked = engine.rank_recommendations(cid, ctx=ctx, limit=engine.MAX_LIMIT)
    candidates = ranked["candidates"]

    names = [c["name"] for c in candidates]
    check(len(names) == len(set(names)), f"{cid} no repeated product names")

    for c in candidates:
        pid = c["product_id"]
        product = tools._PRODUCT_BY_ID[pid]
        for field in ("name", "price", "color", "category", "subcategory", "season"):
            check(c[field] == product[field], f"{cid} {pid} {field} matches catalogue")

        check(c["price"] <= profile["budget"], f"{cid} {pid} within budget")
        check(c["color"] not in profile["avoided_colors"], f"{cid} {pid} not an avoided colour")
        check(pid not in owned, f"{cid} {pid} not already owned")
        check(c["score"] == sum(s["points"] for s in c["signals"]), f"{cid} {pid} score is sum of signals")
        check(bool(c["types"]) and c["primary_type"] == c["types"][0], f"{cid} {pid} primary type")

        # Gap claims: recompute from the reported gaps, independently of the engine.
        gaps = ctx["gaps"]
        fills_gap = (any(g["category"] == product["category"] for g in gaps["missing_categories"])
                     or any(g["undersupplied"] == product["category"] for g in gaps["imbalances"])
                     or any(g["occasion"] == product["occasion"] for g in gaps["occasion_gaps"])
                     or (gaps["color_gap"] and product["color"] in profile["preferred_colors"]))
        check(("gap" in c["types"]) == fills_gap, f"{cid} {pid} gap type iff a reported gap")
        check(fills_gap == bool(gap_matches(product, gaps, profile["preferred_colors"])),
              f"{cid} {pid} gap_matches agrees")

        offer = tools.check_offer(cid, pid)
        check(c["offer"] == offer, f"{cid} {pid} offer matches check_offer")
        check(any(s["group"] == "offer" for s in c["signals"]) == bool(offer), f"{cid} {pid} offer signal")

        if "intent" in c["types"]:
            category_intent = any(r["category"] == product["category"] and r["strength"] != "weak"
                                  for r in ctx["intent"]["category_intents"])
            exact = any(e["product_id"] == pid for e in ctx["intent"]["high_intent_products"])
            check(category_intent or exact, f"{cid} {pid} intent type has intent evidence")

        if "seasonal" in c["types"]:
            s = ctx["seasonal"]
            trending = product["subcategory"] in s["trending_subcategories"]
            high = s["trending_categories"].get(product["category"]) == "high"
            check((product["season"] == s["season"] and (trending or high))
                  or (product["season"] == "all-season" and trending),
                  f"{cid} {pid} seasonal type is in season and trending")

        check(("complementary" in c["types"]) == bool(c["pairs_with"]), f"{cid} {pid} complementary iff pairs")
        for pair in c["pairs_with"]:
            check(pair["product_id"] in owned, f"{cid} {pid} pairs only with owned items")
            check(pair["category"] in engine.COMPLEMENTS[product["category"]], f"{cid} {pid} pair category")
            check(pair["occasion"] == product["occasion"], f"{cid} {pid} pair shares occasion")

    capped = Counter(c["category"] for c in candidates[:8])
    check(max(capped.values(), default=0) <= engine.MAX_PER_CATEGORY or ranked["eligible"] < 8,
          f"{cid} category cap in the top 8")
    return candidates


def scenario_tags(ctx: dict, candidates: list) -> list:
    gaps = ctx["gaps"]
    tags = []
    if gaps["missing_categories"] or gaps["occasion_gaps"] or gaps["imbalances"]:
        tags.append("wardrobe gaps")
    else:
        tags.append("no gaps")
    strengths = {r["strength"] for r in ctx["intent"]["category_intents"] + ctx["intent"]["occasion_intents"]}
    tags.append("strong intent" if "strong" in strengths else
                "moderate intent" if "moderate" in strengths else "insufficient browsing")
    tags.append("thin purchase history" if not ctx["purchases"]["has_sufficient_history"] else "purchase patterns")
    top = candidates[:5]
    if any(c["offer"] for c in top):
        tags.append("offer in top 5")
    for kind in ("seasonal", "complementary"):
        if any(kind in c["types"] for c in top):
            tags.append(f"{kind} picks")
    return tags


for customer in tools.CUSTOMERS:
    cid = customer["customer_id"]
    ctx = engine.build_customer_context(cid)
    check_purchases(cid, ctx)
    check_intent(cid, ctx)
    check_seasonal(cid, ctx)
    candidates = check_ranking(cid, ctx)

    print(f"\n== {cid}  budget Rs{ctx['profile']['budget']}  [{', '.join(scenario_tags(ctx, candidates))}]")
    print(f"   purchases : {ctx['purchases']['headline']}")
    print(f"   intent    : {ctx['intent']['headline']}")
    print(f"   seasonal  : {ctx['seasonal']['headline']}")
    for c in candidates[:5]:
        offer = f"  offer:{c['offer']['offer_type']}" if c["offer"] else ""
        print(f"   {c['score']:>4}  {c['product_id']} {c['name']:26} Rs{c['price']:<5} "
              f"{c['primary_type']:<13} {'/'.join(c['types'])}{offer}")

print(f"\n{checks} checks, {len(failures)} failed")
for failure in failures:
    print(f"  FAIL: {failure}")
sys.exit(1 if failures else 0)
