"""Exercise every function in tools.py against the real datasets."""

import json
from datetime import date, timedelta

import tools


def header(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


def show(rows, fields, empty="(none)"):
    if not rows:
        print(f"  {empty}")
        return
    for r in rows:
        print("  " + " | ".join(f"{f}={r.get(f)!r}" for f in fields))


# ---------------------------------------------------------------- C001, all 5
header("1. get_customer_profile('C001')")
print(json.dumps(tools.get_customer_profile("C001"), indent=2))

header("2. get_wardrobe('C001')  -- joined against products.json")
wardrobe = tools.get_wardrobe("C001")
print(f"  {len(wardrobe)} items")
show(wardrobe, ["product_id", "name", "category", "color", "occasion", "season", "date_acquired", "price_paid"])
print("\n  full first row (proves every product field merged in):")
print(json.dumps(wardrobe[0], indent=4))

header("3. get_browsing_history('C001')")
history = tools.get_browsing_history("C001")
print(f"  {len(history)} events")
show(history, ["product_id", "name", "category", "event_type", "timestamp", "view_count"])

header("4. search_products(...)  -- C001-relevant filters")
combos = [
    {"category": "bottom", "occasion": "college", "max_price": 1500},
    {"category": "outerwear", "color": "black", "season": "monsoon"},
    {"style_tags": "streetwear", "occasion": "casual", "max_price": 1200},
    {"category": "dress", "color": "navy", "occasion": "office", "max_price": 900},
]
for f in combos:
    results = tools.search_products(f)
    print(f"\n  filters={f}")
    print(f"  -> {len(results)} match(es)")
    show(results[:5], ["product_id", "name", "color", "season", "style_tags", "price"])
    if len(results) > 5:
        print(f"  ... {len(results) - 5} more")

header("5. check_offer('C001', ...)  -- both condition types, both branches")
cases = [
    ("P0092", "condition_type='none'      -> should return the offer"),
    ("P0066", "condition_type='category_pair', needs 'shoes'; C001 OWNS shoes -> TRUE BRANCH"),
    ("P0170", "condition_type='category_pair', needs 'bottom'; C001 owns none -> None"),
    ("P0128", "no offer exists for this product -> None"),
]
for pid, note in cases:
    result = tools.check_offer("C001", pid)
    print(f"\n  {pid}: {note}")
    print(f"  -> {json.dumps(result) if result else 'None'}")

# ------------------------------------------------- other customers
for cid in ["C002", "C007", "C008"]:
    header(f"get_wardrobe / get_browsing_history for {cid}")
    w = tools.get_wardrobe(cid)
    print(f"  wardrobe: {len(w)} items")
    show(w, ["product_id", "name", "category", "color", "occasion", "price_paid"])
    h = tools.get_browsing_history(cid)
    print(f"\n  browsing: {len(h)} events")
    show(h, ["product_id", "name", "category", "event_type", "view_count"])

# ------------------------------------------------- edge cases
header("EDGE CASES")

print("\n  a) unknown customer_id raises ValueError:")
try:
    tools.get_customer_profile("C999")
except ValueError as exc:
    print(f"     ValueError: {exc}")

print("\n  b) unknown customer -> empty wardrobe / history, no crash:")
print(f"     get_wardrobe('C999')         -> {tools.get_wardrobe('C999')}")
print(f"     get_browsing_history('C999') -> {tools.get_browsing_history('C999')}")

print("\n  c) search_products with no matches returns [] (does not raise):")
print(f"     {tools.search_products({'category': 'dress', 'color': 'neon', 'max_price': 1})}")

print("\n  d) search_products({}) returns everything (no filters applied):")
print(f"     {len(tools.search_products({}))} products")

print("\n  e) season filter includes 'all-season' products:")
winter = tools.search_products({"category": "outerwear", "season": "winter"})
seasons = sorted({p["season"] for p in winter})
print(f"     season='winter' on outerwear -> {len(winter)} results, seasons present: {seasons}")

print("\n  f) expired offer -> None (no offer in the dataset has expired yet,")
print("     so this temporarily backdates one to prove the branch fires):")
offer = next(o for o in tools.OFFERS if o["applies_to_product_id"] == "P0092")
original = offer["valid_until"]
print(f"     P0092 valid_until={original} (today={date.today()}) -> {'offer' if tools.check_offer('C001','P0092') else 'None'}")
offer["valid_until"] = str(date.today() - timedelta(days=1))
print(f"     P0092 valid_until={offer['valid_until']} (backdated)   -> {'offer' if tools.check_offer('C001','P0092') else 'None'}")
offer["valid_until"] = original

print("\n  g) unresolvable product_id is skipped with a warning, not a crash:")
tools.WARDROBES.append({"customer_id": "C999", "owned_product_id": "P9999",
                        "date_acquired": "2026-01-01", "price_paid": 100})
print(f"     get_wardrobe('C999') -> {tools.get_wardrobe('C999')}")
tools.WARDROBES.pop()

print("\n" + "=" * 72)
print("done")
