"""Validate the Recon dataset against its original schema and value sets.

    python data/validate_dataset.py

The original dataset in data/backup/ is the source of truth: field names and
order, allowed values for every constrained field, and the exact bytes of the
original records. Exits non-zero if any check fails.
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "data" / "backup"
FILES = {
    "customers": "customers.json",
    "products": "products.json",
    "wardrobes": "wardrobes.json",
    "browsing": "browsing_history.json",
    "offers": "offers.json",
}
GOLDEN = {f"C{n:03d}" for n in range(1, 9)}
EARLIEST_SANE_DATE = date(2020, 1, 1)

checks = 0
failures = []


def check(ok: bool, message: str) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append(message)


def load(directory: Path) -> tuple[dict, dict]:
    raw = {k: (directory / name).read_bytes().decode("utf-8") for k, name in FILES.items()}
    return {k: json.loads(text) for k, text in raw.items()}, raw


def parse_date(value: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    if not BACKUP.exists():
        print(f"no backup at {BACKUP} - nothing to validate against")
        return 1
    original, original_raw = load(BACKUP)
    current, current_raw = load(ROOT)

    # ---- original records preserved byte for byte --------------------------
    for key, name in FILES.items():
        check(current_raw[key].startswith(original_raw[key][:-2]),
              f"{name}: original records are not a byte-identical prefix of the current file")
    golden_now = {k: [json.dumps(r, indent=2) for r in current[k] if r.get("customer_id") in GOLDEN]
                  for k in ("customers", "wardrobes", "browsing")}
    golden_then = {k: [json.dumps(r, indent=2) for r in original[k] if r.get("customer_id") in GOLDEN]
                   for k in ("customers", "wardrobes", "browsing")}
    for key in golden_now:
        check(golden_now[key] == golden_then[key], f"{FILES[key]}: C001-C008 records differ from the backup")

    # ---- schema: identical field names, order and types ------------------------
    for key, name in FILES.items():
        expected_keys = [tuple(r.keys()) for r in original[key]][0]
        expected_types = {}
        for r in original[key]:
            for field, value in r.items():
                expected_types.setdefault(field, set()).add(type(value).__name__)
        for r in current[key]:
            check(tuple(r.keys()) == expected_keys, f"{name}: record {r} has fields {list(r.keys())}")
            for field, value in r.items():
                check(type(value).__name__ in expected_types.get(field, set()),
                      f"{name}: {field}={value!r} has type {type(value).__name__}")

    products, customers = current["products"], current["customers"]
    wardrobes, browsing, offers = current["wardrobes"], current["browsing"], current["offers"]

    # ---- unique IDs ----------------------------------------------------------
    for label, ids in (("customer", [c["customer_id"] for c in customers]),
                       ("product", [p["product_id"] for p in products]),
                       ("offer", [o["offer_id"] for o in offers])):
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        check(not dupes, f"duplicate {label} IDs: {dupes}")
    check(not [p for p, n in Counter(o["applies_to_product_id"] for o in offers).items() if n > 1],
          "a product has more than one offer")

    # ---- references ------------------------------------------------------------
    customer_ids = {c["customer_id"] for c in customers}
    product_ids = {p["product_id"] for p in products}
    for r in wardrobes:
        check(r["customer_id"] in customer_ids, f"wardrobe references unknown customer {r['customer_id']}")
        check(r["owned_product_id"] in product_ids, f"wardrobe references unknown product {r['owned_product_id']}")
    for r in browsing:
        check(r["customer_id"] in customer_ids, f"browsing references unknown customer {r['customer_id']}")
        check(r["product_id"] in product_ids, f"browsing references unknown product {r['product_id']}")
    for o in offers:
        check(o["applies_to_product_id"] in product_ids, f"offer {o['offer_id']} references unknown product")

    # ---- constrained values come from the original sets --------------------------
    op, oc, ob, oo = original["products"], original["customers"], original["browsing"], original["offers"]
    allowed = {
        "category": {p["category"] for p in op},
        "subcategory": {p["subcategory"] for p in op},
        "style_tags": {t for p in op for t in p["style_tags"]},
        "occasion": {p["occasion"] for p in op},
        "season": {p["season"] for p in op},
        "event_type": {e["event_type"] for e in ob},
        "offer_type": {o["offer_type"] for o in oo},
        "condition_type": {o["condition_type"] for o in oo},
        "color": {p["color"] for p in op},
        "store": {p["store"] for p in op},
        "condition_category": {o["condition_category"] for o in oo},
        "discount_percentage": {o["discount_percentage"] for o in oo},
        "current_season": {c["current_season"] for c in oc},
        "customer_style": {s for c in oc for s in c["preferred_styles"]},
        "customer_occasion": {s for c in oc for s in c["preferred_occasions"]},
        "customer_color": {p["color"] for p in op} | {s for c in oc for s in c["preferred_colors"] + c["avoided_colors"]},
    }
    flagged = Counter()

    def value_ok(field, value, record_label):
        ok = value in allowed[field]
        check(ok, f"{record_label}: {field}={value!r} is not an original value")
        if not ok:
            flagged[(field, value)] += 1

    pairs = {(p["category"], p["subcategory"]) for p in op}
    for p in products:
        label = p["product_id"]
        for field in ("category", "subcategory", "occasion", "season", "color", "store"):
            value_ok(field, p[field], label)
        for tag in p["style_tags"]:
            value_ok("style_tags", tag, label)
        check(bool(p["style_tags"]), f"{label}: empty style_tags")
        check((p["category"], p["subcategory"]) in pairs,
              f"{label}: category/subcategory pair {p['category']}/{p['subcategory']} never appears in the original")
        check(isinstance(p["price"], int) and p["price"] > 0, f"{label}: bad price {p['price']!r}")
    for c in customers:
        label = c["customer_id"]
        value_ok("current_season", c["current_season"], label)
        for s in c["preferred_styles"]:
            value_ok("customer_style", s, label)
        for s in c["preferred_occasions"]:
            value_ok("customer_occasion", s, label)
        for s in c["preferred_colors"] + c["avoided_colors"]:
            value_ok("customer_color", s, label)
        check(isinstance(c["budget"], int) and c["budget"] > 0, f"{label}: bad budget {c['budget']!r}")
        check(bool(c["preferred_styles"] and c["preferred_colors"] and c["preferred_occasions"]),
              f"{label}: empty preference list")
    for e in browsing:
        value_ok("event_type", e["event_type"], f"browsing {e['customer_id']}/{e['product_id']}")
        check(isinstance(e["view_count"], int) and e["view_count"] >= 1, f"browsing: bad view_count {e}")
    for o in offers:
        for field in ("offer_type", "condition_type", "condition_category", "discount_percentage"):
            value_ok(field, o[field], o["offer_id"])
        check((o["condition_type"] == "category_pair") == (o["condition_category"] is not None),
              f"{o['offer_id']}: condition_category does not match condition_type")

    # ---- dates and prices are sane --------------------------------------------------
    today = date.today()
    snapshot = max(date.fromisoformat(e["timestamp"]) for e in ob)
    for r in wardrobes:
        d = parse_date(r["date_acquired"])
        check(d is not None and EARLIEST_SANE_DATE <= d <= today, f"wardrobe: bad date_acquired {r}")
        check(isinstance(r["price_paid"], int) and r["price_paid"] > 0, f"wardrobe: bad price_paid {r}")
    for e in browsing:
        d = parse_date(e["timestamp"])
        check(d is not None and EARLIEST_SANE_DATE <= d <= today, f"browsing: bad timestamp {e}")
        # Later events would move the intent snapshot date for every customer.
        check(d is not None and d <= snapshot, f"browsing: timestamp {e['timestamp']} is after {snapshot}")
    for o in offers:
        check(parse_date(o["valid_until"]) is not None, f"{o['offer_id']}: bad valid_until")

    # ---- report ---------------------------------------------------------------
    print("COUNTS (backup -> current)")
    for key, name in FILES.items():
        print(f"  {name:24} {len(original[key]):>5} -> {len(current[key]):>5}")

    new_customers = [c for c in customers if c["customer_id"] not in GOLDEN]
    per_customer_browse = Counter(e["customer_id"] for e in browsing)
    per_customer_buy = Counter(w["customer_id"] for w in wardrobes)
    price = {p["product_id"]: p["price"] for p in products}
    category = {p["product_id"]: p["category"] for p in products}
    budget = {c["customer_id"]: c["budget"] for c in customers}
    new_ids = {c["customer_id"] for c in new_customers}
    new_buys = [w for w in wardrobes if w["customer_id"] in new_ids]

    def bucket(n):
        return "none" if n == 0 else "sparse (1-2)" if n <= 2 else "moderate (3-14)" if n <= 14 else "rich (15+)"

    print("\nCOVERAGE (generated customers)")
    print("  browsing volume   :", dict(Counter(bucket(per_customer_browse[c]) for c in new_ids)))
    print("  purchase volume   :", dict(Counter(bucket(per_customer_buy[c]) for c in new_ids)))
    print("  with abandoned carts:", len({e["customer_id"] for e in browsing
                                          if e["customer_id"] in new_ids and e["event_type"] == "abandoned_cart"}))
    owned_categories = {c: {category[w["owned_product_id"]] for w in wardrobes if w["customer_id"] == c}
                        for c in new_ids}
    print("  missing outerwear/shoes/accessory:",
          sum(1 for c in new_ids if {"outerwear", "shoes", "accessory"} - owned_categories[c]),
          "| own all six categories:",
          sum(1 for c in new_ids if len(owned_categories[c]) == 6))
    repeat = sum(1 for c in new_ids
                 if any(n >= 2 for n in Counter(category[w["owned_product_id"]]
                                                 for w in wardrobes if w["customer_id"] == c).values()))
    print("  repeat category buyers:", repeat)
    within = sum(1 for w in new_buys if price[w["owned_product_id"]] <= budget[w["customer_id"]])
    print(f"  purchases with list price <= stated budget: {within}/{len(new_buys)}")
    print("  products by season:", dict(sorted(Counter(p["season"] for p in products).items())))
    dates = sorted(w["date_acquired"] for w in wardrobes)
    stamps = sorted(e["timestamp"] for e in browsing)
    print(f"  purchase dates {dates[0]} .. {dates[-1]} | browsing {stamps[0]} .. {stamps[-1]}")

    print(f"\nVALIDATION: {checks} checks, {len(failures)} failed")
    for (field, value), n in sorted(flagged.items()):
        print(f"  FLAGGED value {field}={value!r} ({n} records)")
    for message in failures[:25]:
        print(f"  FAIL: {message}")
    if len(failures) > 25:
        print(f"  ... {len(failures) - 25} more")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
