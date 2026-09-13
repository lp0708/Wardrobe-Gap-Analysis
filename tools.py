"""Data access layer for the wardrobe-gap recommendation agent.

All five datasets are loaded once at import time and resolved relative to this
file, so the module behaves identically regardless of the caller's cwd.
"""

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent


def _load(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


PRODUCTS = _load("products.json")
CUSTOMERS = _load("customers.json")
WARDROBES = _load("wardrobes.json")
BROWSING_HISTORY = _load("browsing_history.json")
OFFERS = _load("offers.json")

# product_id -> product dict, for the joins below
_PRODUCT_BY_ID = {p["product_id"]: p for p in PRODUCTS}

# Fields merged into wardrobe / browsing rows when a product resolves.
_PRODUCT_FIELDS = (
    "name",
    "category",
    "subcategory",
    "color",
    "style_tags",
    "occasion",
    "season",
    "price",
    "store",
)


def _merge_product(row: dict, product_id: str, source: str) -> dict | None:
    """Return `row` merged with its product details, or None if unresolvable."""
    product = _PRODUCT_BY_ID.get(product_id)
    if product is None:
        print(f"WARNING: {source} references unknown product_id {product_id!r} - skipping row")
        return None
    merged = dict(row)
    merged["product_id"] = product_id
    for field in _PRODUCT_FIELDS:
        merged[field] = product[field]
    return merged


def get_customer_profile(customer_id: str) -> dict:
    """Return the profile for `customer_id`, or raise ValueError if unknown."""
    for customer in CUSTOMERS:
        if customer["customer_id"] == customer_id:
            return dict(customer)
    known = ", ".join(sorted(c["customer_id"] for c in CUSTOMERS))
    raise ValueError(f"Unknown customer_id {customer_id!r}. Known customers: {known}")


def get_wardrobe(customer_id: str) -> list[dict]:
    """Return the customer's owned items, each joined to its full product record.

    Each row keeps date_acquired and price_paid alongside the merged product
    fields. Rows whose owned_product_id does not resolve are skipped with a
    warning rather than raising.
    """
    wardrobe = []
    for row in WARDROBES:
        if row["customer_id"] != customer_id:
            continue
        merged = _merge_product(row, row["owned_product_id"], "wardrobes.owned_product_id")
        if merged is not None:
            wardrobe.append(merged)
    return wardrobe


def get_browsing_history(customer_id: str) -> list[dict]:
    """Return the customer's browsing events, each joined to its product record.

    Keeps event_type, timestamp and view_count from the browsing record. Rows
    whose product_id does not resolve are skipped with a warning.
    """
    history = []
    for row in BROWSING_HISTORY:
        if row["customer_id"] != customer_id:
            continue
        merged = _merge_product(row, row["product_id"], "browsing_history.product_id")
        if merged is not None:
            history.append(merged)
    return history


def search_products(filters: dict) -> list[dict]:
    """Return products matching every provided filter (AND logic).

    Supported keys: category, color, style_tags, occasion, season, max_price.
    Omitted or None keys are not filtered on. A `season` filter also matches
    "all-season" products. `style_tags` matches if the value appears anywhere
    in a product's style_tags list. Returns [] when nothing matches.
    """
    filters = filters or {}
    category = filters.get("category")
    color = filters.get("color")
    style_tag = filters.get("style_tags")
    occasion = filters.get("occasion")
    season = filters.get("season")
    max_price = filters.get("max_price")

    results = []
    for product in PRODUCTS:
        if category and product["category"] != category:
            continue
        if color and product["color"] != color:
            continue
        if style_tag and style_tag not in product["style_tags"]:
            continue
        if occasion and product["occasion"] != occasion:
            continue
        if season and product["season"] not in (season, "all-season"):
            continue
        if max_price is not None and product["price"] > max_price:
            continue
        results.append(dict(product))
    return results


def check_offer(customer_id: str, product_id: str) -> dict | None:
    """Return the active, qualifying offer for `product_id`, else None.

    Returns None when no offer exists for the product, when the offer's
    valid_until has passed, or when a category_pair offer's condition_category
    is absent from the customer's wardrobe.
    """
    offer = next((o for o in OFFERS if o["applies_to_product_id"] == product_id), None)
    if offer is None:
        return None

    if date.fromisoformat(offer["valid_until"]) < date.today():
        return None

    if offer["condition_type"] == "category_pair":
        required = offer["condition_category"]
        owned_categories = {item["category"] for item in get_wardrobe(customer_id)}
        if required not in owned_categories:
            return None

    return dict(offer)
