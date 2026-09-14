"""Deterministic, append-only expansion of the Recon dataset.

    python data/generate_dataset.py --customers 100 --products 420 --offers 45 --seed 42

--customers, --products and --offers are TOTALS after generation, so running
the command again on already-expanded data adds nothing. Purchases and
browsing events are generated only for the new customers.

Guarantees:
  * Existing records are kept byte for byte - the files are re-serialised in
    their existing indent=2 format and the script verifies the original text
    is an exact prefix of the new text before writing.
  * Same source data + same seed = identical output.
  * Every value of a constrained field (category, subcategory, style_tags,
    occasion, season, event_type, offer_type, condition_type) - and colours,
    stores, discounts, condition categories and current_season - is drawn from
    the values already present in the source data.
  * New IDs continue from the current highest: C009..., P0181..., O031...
  * Offers are attached only to new products, and browsing timestamps never
    pass the latest existing event, so the analysis output for the original
    customers' own records cannot shift.

Customers come from segment profiles, so preferences, budget, purchases and
browsing point the same way instead of every field being random on its own.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
import random

DATA_DIR = Path(__file__).resolve().parents[1]
FILES = {
    "customers": "customers.json",
    "products": "products.json",
    "wardrobes": "wardrobes.json",
    "browsing": "browsing_history.json",
    "offers": "offers.json",
}

# Segment profiles. Every value here must exist in the source vocabulary;
# build_vocabulary() checks that before anything is generated.
SEGMENTS = [
    {"name": "campus_casual", "weight": 24, "styles": ["casual", "streetwear"],
     "occasions": ["college", "casual"], "colors": ["black", "white", "beige", "grey", "navy", "blue"],
     "budget": (900, 1800)},
    {"name": "office_smart", "weight": 20, "styles": ["smart-casual", "formal"],
     "occasions": ["office", "party"], "colors": ["navy", "white", "grey", "black", "brown", "beige"],
     "budget": (1700, 2500)},
    {"name": "festive_fusion", "weight": 14, "styles": ["fusion", "ethnic", "casual"],
     "occasions": ["festive", "casual"], "colors": ["red", "green", "yellow", "pink", "beige", "white"],
     "budget": (1400, 2500)},
    {"name": "night_out", "weight": 14, "styles": ["streetwear", "smart-casual", "casual"],
     "occasions": ["party", "college"], "colors": ["black", "red", "purple", "olive", "navy"],
     "budget": (1200, 2300)},
    {"name": "value_basics", "weight": 16, "styles": ["casual", "smart-casual"],
     "occasions": ["casual", "college"], "colors": ["white", "blue", "grey", "beige", "black"],
     "budget": (700, 1300)},
    {"name": "earthy_smart_casual", "weight": 12, "styles": ["smart-casual", "casual"],
     "occasions": ["college", "office", "casual"], "colors": ["brown", "olive", "beige", "navy", "green"],
     "budget": (1300, 2200)},
]

# (label, weight, (min, max)) - how many purchases / browsing events a customer has.
PURCHASE_TIERS = [("light", 30, (1, 3)), ("regular", 45, (4, 8)), ("heavy", 25, (9, 14))]
BROWSING_TIERS = [("none", 15, (0, 0)), ("sparse", 25, (1, 2)), ("moderate", 35, (5, 14)),
                  ("rich", 25, (20, 45))]

CART_ABANDONER_RATE = 0.30
REPEAT_BUYER_RATE = 0.35
GAPPY_RATE = 0.45
# Categories a "gappy" customer may lack. Tops and bottoms are left out because
# the gap analyzer treats a dress as covering them.
GAP_CANDIDATES = ["outerwear", "shoes", "accessory"]
SEASON_SKEW_WEIGHTS = {"monsoon": 40, "winter": 30, "summer": 30}

PURCHASE_WINDOW = (date(2025, 1, 1), date(2026, 8, 31))
BROWSING_WINDOW_DAYS = 35
PRICE_PAID_NOISE = [0, 0, 0, -50, -100, -150, 50, 100]
MAX_PRODUCT_ATTEMPTS = 50_000


# --------------------------------------------------------------------------
# Loading and vocabulary
# --------------------------------------------------------------------------

def load_source(source_dir: Path) -> tuple[dict, dict]:
    data, raw = {}, {}
    for key, name in FILES.items():
        text = (source_dir / name).read_bytes().decode("utf-8")
        rows = json.loads(text)
        if json.dumps(rows, indent=2) != text:
            raise SystemExit(f"{name} is not in the expected json.dumps(indent=2) format - "
                             f"refusing to rewrite it, because existing bytes could change.")
        data[key], raw[key] = rows, text
    return data, raw


def build_vocabulary(data: dict) -> dict:
    products, customers, offers = data["products"], data["customers"], data["offers"]
    by_pair = defaultdict(list)
    for product in products:
        by_pair[(product["category"], product["subcategory"])].append(product)

    descriptors = defaultdict(set)
    for (category, subcategory), items in by_pair.items():
        for item in items:
            first, _, rest = item["name"].partition(" ")
            descriptors[(category, subcategory)].add(rest if first.lower() == item["color"] and rest
                                                     else item["name"])

    vocab = {
        "categories": sorted({p["category"] for p in products}),
        "pairs": sorted(by_pair),
        "by_pair": by_pair,
        "descriptors": {pair: sorted(names) for pair, names in descriptors.items()},
        "style_tags": sorted({t for p in products for t in p["style_tags"]}),
        "occasions": sorted({p["occasion"] for p in products}),
        "seasons": sorted({p["season"] for p in products}),
        "colors": sorted({p["color"] for p in products}),
        "stores": sorted({p["store"] for p in products}),
        "price_min": min(p["price"] for p in products),
        "price_max": max(p["price"] for p in products),
        "event_types": sorted({e["event_type"] for e in data["browsing"]}),
        "offer_types": sorted({o["offer_type"] for o in offers}),
        "condition_types": sorted({o["condition_type"] for o in offers}),
        "condition_categories": sorted({o["condition_category"] for o in offers if o["condition_category"]}),
        "discounts": {t: sorted({o["discount_percentage"] for o in offers if o["offer_type"] == t})
                      for t in {o["offer_type"] for o in offers}},
        "avoided_colors": sorted({c for cu in customers for c in cu["avoided_colors"]}),
        "current_seasons": sorted({cu["current_season"] for cu in customers}),
        "latest_event": max(date.fromisoformat(e["timestamp"]) for e in data["browsing"]),
        "valid_until_range": (min(date.fromisoformat(o["valid_until"]) for o in offers),
                              max(date.fromisoformat(o["valid_until"]) for o in offers)),
        "category_weights": Counter(p["category"] for p in products),
        "offer_type_weights": Counter(o["offer_type"] for o in offers),
        "condition_type_weights": Counter(o["condition_type"] for o in offers),
    }

    # Refuse to run if a segment profile names a value the data doesn't use.
    for segment in SEGMENTS:
        for field, allowed in (("styles", vocab["style_tags"]), ("occasions", vocab["occasions"]),
                               ("colors", vocab["colors"])):
            unknown = sorted(set(segment[field]) - set(allowed))
            if unknown:
                raise SystemExit(f"segment {segment['name']} uses unknown {field}: {unknown}")
    unknown = sorted(set(GAP_CANDIDATES) - set(vocab["categories"])) + \
        sorted(set(SEASON_SKEW_WEIGHTS) - set(vocab["seasons"]))
    if unknown:
        raise SystemExit(f"generator constants use unknown values: {unknown}")
    required = {"viewed", "saved", "added_to_cart", "abandoned_cart"}
    if not required <= set(vocab["event_types"]):
        raise SystemExit(f"source data lacks event types {sorted(required - set(vocab['event_types']))}")
    return vocab


# --------------------------------------------------------------------------
# Random helpers
# --------------------------------------------------------------------------

def weighted_choice(rng: random.Random, items: list, weights: list):
    return rng.choices(items, weights=weights, k=1)[0]


def weighted_sample(rng: random.Random, items: list, weights: list, k: int) -> list:
    """k distinct items, each draw weighted, in draw order."""
    pool = list(zip(items, weights))
    chosen = []
    while pool and len(chosen) < k:
        index = rng.choices(range(len(pool)), weights=[w for _, w in pool], k=1)[0]
        chosen.append(pool.pop(index)[0])
    return chosen


def next_number(ids: list, prefix: str) -> int:
    return max((int(i[len(prefix):]) for i in ids), default=0) + 1


# --------------------------------------------------------------------------
# Products and offers
# --------------------------------------------------------------------------

def product_signature(product: dict) -> tuple:
    return (product["subcategory"], product["color"], product["occasion"], product["season"],
            tuple(sorted(product["style_tags"])))


def generate_products(rng, vocab, existing, count) -> list:
    seen = {product_signature(p) for p in existing}
    number = next_number([p["product_id"] for p in existing], "P")
    categories = vocab["categories"]
    category_weights = [vocab["category_weights"][c] for c in categories]
    pairs_by_category = defaultdict(list)
    for pair in vocab["pairs"]:
        pairs_by_category[pair[0]].append(pair)

    new, attempts = [], 0
    while len(new) < count:
        attempts += 1
        if attempts > MAX_PRODUCT_ATTEMPTS:
            raise SystemExit("could not generate enough distinct products from the existing vocabulary")

        category = weighted_choice(rng, categories, category_weights)
        pairs = pairs_by_category[category]
        pair = weighted_choice(rng, pairs, [len(vocab["by_pair"][p]) for p in pairs])
        template = rng.choice(vocab["by_pair"][pair])

        tags = (list(template["style_tags"]) if rng.random() < 0.7
                else sorted(rng.sample(vocab["style_tags"], rng.choice([1, 2]))))
        occasion = template["occasion"] if rng.random() < 0.65 else rng.choice(vocab["occasions"])
        # Seasons are drawn evenly so the catalogue isn't concentrated in one.
        season = rng.choice(vocab["seasons"])
        color = rng.choice(vocab["colors"])

        pair_prices = [p["price"] for p in vocab["by_pair"][pair]]
        low = max(vocab["price_min"], min(pair_prices) - 300)
        high = min(vocab["price_max"], max(pair_prices) + 300)
        price = max(vocab["price_min"], (rng.randint(low, high) // 50) * 50 - 1)

        product = {
            "product_id": f"P{number:04d}",
            "name": f"{color.capitalize()} {rng.choice(vocab['descriptors'][pair])}",
            "category": category,
            "subcategory": pair[1],
            "color": color,
            "style_tags": tags,
            "occasion": occasion,
            "season": season,
            "price": price,
            "store": rng.choice(vocab["stores"]),
        }
        signature = product_signature(product)
        if signature in seen:
            continue  # avoid near-duplicates that differ only by ID or price
        seen.add(signature)
        new.append(product)
        number += 1
    return new


def generate_offers(rng, vocab, existing, new_products, count) -> list:
    number = next_number([o["offer_id"] for o in existing], "O")
    targets = rng.sample(new_products, min(count, len(new_products)))
    types = vocab["offer_types"]
    conditions = vocab["condition_types"]
    first, last = vocab["valid_until_range"]
    offers = []
    for product in sorted(targets, key=lambda p: p["product_id"]):
        offer_type = weighted_choice(rng, types, [vocab["offer_type_weights"][t] for t in types])
        condition_type = weighted_choice(rng, conditions, [vocab["condition_type_weights"][c] for c in conditions])
        offers.append({
            "offer_id": f"O{number:03d}",
            "applies_to_product_id": product["product_id"],
            "offer_type": offer_type,
            "discount_percentage": rng.choice(vocab["discounts"][offer_type]),
            "condition_type": condition_type,
            "condition_category": (rng.choice(vocab["condition_categories"])
                                   if condition_type == "category_pair" else None),
            "valid_until": (first + timedelta(days=rng.randint(0, (last - first).days))).isoformat(),
        })
        number += 1
    return offers


# --------------------------------------------------------------------------
# Customers, purchases and browsing
# --------------------------------------------------------------------------

def make_customer(rng, vocab, customer_id, segment) -> dict:
    preferred_colors = rng.sample(segment["colors"], 3)
    avoid_pool = sorted(set(vocab["avoided_colors"] + vocab["colors"]) - set(preferred_colors))
    low, high = segment["budget"]
    return {
        "customer_id": customer_id,
        "preferred_styles": rng.sample(segment["styles"], min(2, len(segment["styles"]))),
        "preferred_colors": preferred_colors,
        "avoided_colors": [rng.choice(avoid_pool)],
        "budget": round(rng.randint(low, high), -2),
        "preferred_occasions": rng.sample(segment["occasions"],
                                          min(rng.choice([1, 2]), len(segment["occasions"]))),
        "current_season": rng.choice(vocab["current_seasons"]),
    }


def make_traits(rng) -> dict:
    gappy = rng.random() < GAPPY_RATE
    seasons = list(SEASON_SKEW_WEIGHTS)
    return {
        "purchase_tier": weighted_choice(rng, PURCHASE_TIERS, [t[1] for t in PURCHASE_TIERS]),
        "browsing_tier": weighted_choice(rng, BROWSING_TIERS, [t[1] for t in BROWSING_TIERS]),
        "abandoner": rng.random() < CART_ABANDONER_RATE,
        "repeat_buyer": rng.random() < REPEAT_BUYER_RATE,
        "missing": sorted(rng.sample(GAP_CANDIDATES, rng.choice([1, 2]))) if gappy else [],
        "season_skew": weighted_choice(rng, seasons, [SEASON_SKEW_WEIGHTS[s] for s in seasons]),
    }


def affinity(product: dict, customer: dict, traits: dict, browsing: bool) -> float:
    """How likely this customer is to buy (or browse) this product. 0 = never."""
    if product["color"] in customer["avoided_colors"]:
        return 0.0
    # Purchases stay within budget; browsing may stretch slightly above it.
    if product["price"] > customer["budget"] * (1.25 if browsing else 1.0):
        return 0.0
    if not browsing and product["category"] in traits["missing"]:
        return 0.0

    weight = 1.0
    if set(product["style_tags"]) & set(customer["preferred_styles"]):
        weight *= 4
    if product["occasion"] in customer["preferred_occasions"]:
        weight *= 3
    if product["color"] in customer["preferred_colors"]:
        weight *= 2.5
    if product["season"] == traits["season_skew"]:
        weight *= 2
    elif product["season"] == "all-season":
        weight *= 1.4
    if 0.35 <= product["price"] / customer["budget"] <= 0.9:
        weight *= 1.6
    return weight


def generate_purchases(rng, customer, traits, products) -> list:
    low, high = traits["purchase_tier"][2]
    target = rng.randint(low, high)
    scored = [(p, affinity(p, customer, traits, browsing=False)) for p in products]
    scored = [(p, w) for p, w in scored if w > 0]
    if not scored:
        return []

    if traits["repeat_buyer"]:
        counts = Counter(p["subcategory"] for p, _ in scored)
        repeatable = sorted(s for s, n in counts.items() if n >= 2)
        if repeatable:
            favourite = weighted_choice(rng, repeatable, [counts[s] for s in repeatable])
            scored = [(p, w * 6 if p["subcategory"] == favourite else w) for p, w in scored]

    chosen = []
    if not traits["missing"] and target >= len(set(p["category"] for p, _ in scored)):
        # Balanced wardrobe: cover every category first, then fill by affinity.
        for category in sorted({p["category"] for p, _ in scored}):
            options = [(p, w) for p, w in scored if p["category"] == category]
            chosen += weighted_sample(rng, [p for p, _ in options], [w for _, w in options], 1)
    remaining = [(p, w) for p, w in scored if p not in chosen]
    chosen += weighted_sample(rng, [p for p, _ in remaining], [w for _, w in remaining],
                              max(0, target - len(chosen)))

    start, end = PURCHASE_WINDOW
    span = (end - start).days
    purchases = []
    for product in chosen:
        acquired = start + timedelta(days=int(span * rng.random() ** 0.8))  # mild skew to recent
        purchases.append({
            "customer_id": customer["customer_id"],
            "owned_product_id": product["product_id"],
            "date_acquired": acquired.isoformat(),
            "price_paid": max(199, product["price"] + rng.choice(PRICE_PAID_NOISE)),
        })
    return sorted(purchases, key=lambda r: (r["date_acquired"], r["owned_product_id"]))


def event_type_for(rng, traits) -> str:
    abandoned = 0.22 if traits["abandoner"] else 0.02
    roll = rng.random()
    if roll < abandoned:
        return "abandoned_cart"
    if roll < abandoned + 0.08:
        return "added_to_cart"
    if roll < abandoned + 0.18:
        return "saved"
    return "viewed"


def generate_browsing(rng, vocab, customer, traits, products, owned_ids) -> list:
    low, high = traits["browsing_tier"][2]
    target = rng.randint(low, high)
    if target == 0:
        return []

    scored = [(p, affinity(p, customer, traits, browsing=True)) for p in products
              if p["product_id"] not in owned_ids]
    scored = [(p, w) for p, w in scored if w > 0]
    if not scored:
        return []

    # Engaged browsers concentrate on one category - often a category they are
    # missing, which is what makes browsing line up with real gaps.
    if traits["browsing_tier"][0] in ("moderate", "rich"):
        if traits["missing"] and rng.random() < 0.65:
            focus = rng.choice(traits["missing"])
        else:
            focus = weighted_choice(rng, [p["category"] for p, _ in scored], [w for _, w in scored])
        scored = [(p, w * 5 if p["category"] == focus else w) for p, w in scored]

    picks = weighted_sample(rng, [p for p, _ in scored], [w for _, w in scored], target)
    latest = vocab["latest_event"]
    events = []
    for product in picks:
        event_type = event_type_for(rng, traits)
        views = rng.choices([1, 2, 3, 4, 5],
                            weights=[40, 25, 17, 10, 8] if event_type == "viewed" else [15, 25, 25, 20, 15])[0]
        # Never later than the latest existing event, so the intent snapshot date holds.
        stamp = latest - timedelta(days=int(BROWSING_WINDOW_DAYS * rng.random() ** 1.8))
        events.append({
            "customer_id": customer["customer_id"],
            "product_id": product["product_id"],
            "event_type": event_type,
            "timestamp": stamp.isoformat(),
            "view_count": views,
        })

    if traits["abandoner"] and not any(e["event_type"] == "abandoned_cart" for e in events):
        events[0]["event_type"] = "abandoned_cart"  # the highest-affinity pick
    return sorted(events, key=lambda e: (e["timestamp"], e["product_id"]))


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def generate(data: dict, vocab: dict, targets: dict, seed: int) -> tuple[dict, Counter]:
    rng = random.Random(seed)
    additions = {key: [] for key in FILES}
    stats = Counter()

    new_products = generate_products(rng, vocab, data["products"],
                                     max(0, targets["products"] - len(data["products"])))
    additions["products"] = new_products
    additions["offers"] = generate_offers(rng, vocab, data["offers"], new_products,
                                          max(0, targets["offers"] - len(data["offers"])))
    catalogue = data["products"] + new_products

    number = next_number([c["customer_id"] for c in data["customers"]], "C")
    for _ in range(max(0, targets["customers"] - len(data["customers"]))):
        segment = weighted_choice(rng, SEGMENTS, [s["weight"] for s in SEGMENTS])
        customer = make_customer(rng, vocab, f"C{number:03d}", segment)
        traits = make_traits(rng)
        purchases = generate_purchases(rng, customer, traits, catalogue)
        owned = {p["owned_product_id"] for p in purchases}
        browsing = generate_browsing(rng, vocab, customer, traits, catalogue, owned)

        additions["customers"].append(customer)
        additions["wardrobes"] += purchases
        additions["browsing"] += browsing
        stats[f"segment:{segment['name']}"] += 1
        stats[f"purchases:{traits['purchase_tier'][0]}"] += 1
        stats[f"browsing:{traits['browsing_tier'][0]}"] += 1
        stats["cart abandoners"] += traits["abandoner"]
        stats["repeat buyers"] += traits["repeat_buyer"]
        stats["with planned gaps"] += bool(traits["missing"])
        number += 1
    return additions, stats


def write(out_dir: Path, data: dict, raw: dict, additions: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, name in FILES.items():
        text = json.dumps(data[key] + additions[key], indent=2)
        original = raw[key]
        # json.dumps(indent=2) ends a list with "\n]"; everything before that
        # must be unchanged, or an existing record was altered.
        if not text.startswith(original[:-2]):
            raise SystemExit(f"refusing to write {name}: existing records would not be preserved")
        (out_dir / name).write_bytes(text.encode("utf-8"))  # bytes: keep LF line endings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customers", type=int, default=100, help="total customers after generation")
    parser.add_argument("--products", type=int, default=420, help="total products after generation")
    parser.add_argument("--offers", type=int, default=45, help="total offers after generation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source", type=Path, default=DATA_DIR, help="directory to read the dataset from")
    parser.add_argument("--out", type=Path, default=DATA_DIR, help="directory to write the dataset to")
    parser.add_argument("--dry-run", action="store_true", help="report what would be added without writing")
    args = parser.parse_args()

    data, raw = load_source(args.source)
    vocab = build_vocabulary(data)
    targets = {"customers": args.customers, "products": args.products, "offers": args.offers}
    additions, stats = generate(data, vocab, targets, args.seed)

    print(f"seed {args.seed}  source {args.source}  out {args.out}{'  (dry run)' if args.dry_run else ''}")
    for key, name in FILES.items():
        before = len(data[key])
        print(f"  {name:24} {before:>5} -> {before + len(additions[key]):>5}  (+{len(additions[key])})")
    for label, value in sorted(stats.items()):
        print(f"  {label:32} {value}")

    if not args.dry_run:
        write(args.out, data, raw, additions)
        print("written")


if __name__ == "__main__":
    main()
