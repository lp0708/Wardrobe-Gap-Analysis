"""Retailer-level views for the platform pages: Dashboard, Customers,
Recommendations and Analytics.

Read-only aggregation over what already exists - the datasets, the
deterministic intelligence modules, the recommendation engine and saved agent
runs. Nothing here scores, ranks or infers anything new: every figure is a
count or sum over those sources, so the platform pages and the demo can never
disagree about a customer.
"""

from collections import Counter
from datetime import date

import tools
from agent import load_saved_run
from intelligence import recommendation_engine as engine
from intelligence.intent_analysis import CART_OR_SAVE, STRENGTH_RANK

ENGINE_PICKS_PER_CUSTOMER = 5
TOP_SIGNALS = 3


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------

def _customer_ids() -> list:
    return [c["customer_id"] for c in tools.CUSTOMERS]


def _contexts(customer_ids: list) -> dict:
    return {cid: engine.build_customer_context(cid) for cid in customer_ids}


def _runs(customer_ids: list) -> dict:
    return {cid: load_saved_run(cid) for cid in customer_ids}


def _intent_strength(intent: dict) -> str:
    """Strongest non-weak intent across category and occasion, else 'insufficient'."""
    strengths = [r["strength"] for r in intent["category_intents"] + intent["occasion_intents"]]
    best = max(strengths, key=STRENGTH_RANK.get, default="weak")
    return "insufficient" if best == "weak" else best


def _opportunities(gaps: dict) -> list:
    """The gaps analyze_outfit_gaps reported, flattened for display."""
    items = [{"kind": "missing_category", "label": g["category"], "priority": g["priority"]}
             for g in gaps["missing_categories"]]
    items += [{"kind": "imbalance", "label": g["undersupplied"], "priority": g["priority"]}
              for g in gaps["imbalances"]]
    items += [{"kind": "occasion", "label": g["occasion"], "priority": g["priority"]}
              for g in gaps["occasion_gaps"]]
    if gaps["color_gap"]:
        items.append({"kind": "color", "label": "preferred colours", "priority": "medium"})
    return items


def _active_offers() -> list:
    today = date.today()
    return [o for o in tools.OFFERS if date.fromisoformat(o["valid_until"]) >= today]


def _run_summary(run: dict | None) -> dict | None:
    if not run:
        return None
    recs = run["recommendations"]
    return {
        "saved_at": run["saved_at"],
        "model": run.get("model"),
        "recommendation_count": len(recs),
        "tool_calls": len(run.get("trace", [])),
        "top_pick": {"name": recs[0]["name"], "primary_type": recs[0]["primary_type"]} if recs else None,
    }


def _customer_row(ctx: dict, run: dict | None) -> dict:
    profile = ctx["profile"]
    customer_id = profile["customer_id"]
    events = tools.get_browsing_history(customer_id)
    purchases = ctx["purchases"]
    spend = purchases["spend"]
    opportunities = _opportunities(ctx["gaps"])
    strength = _intent_strength(ctx["intent"])

    return {
        "customer_id": customer_id,
        "preferred_styles": profile["preferred_styles"],
        "preferred_colors": profile["preferred_colors"],
        "budget": profile["budget"],
        "current_season": profile["current_season"],
        "purchase_count": purchases["purchase_count"],
        "total_spend": spend["total"] if spend else 0,
        "average_spend": spend["average"] if spend else None,
        "last_purchase": purchases["last_purchase"],
        "has_purchase_history": purchases["has_sufficient_history"],
        "browsing_event_count": len(events),
        "cart_or_save_events": sum(1 for e in events if e["event_type"] in CART_OR_SAVE),
        "last_browsed": max((e["timestamp"] for e in events), default=None),
        "intent_strength": strength,
        "intent_headline": ctx["intent"]["headline"],
        "opportunities": opportunities,
        # A retailer opportunity is a reported gap or intent strong enough to act on.
        "has_opportunity": bool(opportunities) or strength != "insufficient",
        "latest_run": _run_summary(run),
    }


def _recommendation_row(customer_id: str, rec: dict, source: str, explanation: str,
                        explanation_source: str, saved_at: str | None) -> dict:
    return {
        "customer_id": customer_id,
        **{key: rec[key] for key in ("product_id", "name", "category", "color", "price",
                                     "season", "score", "types", "primary_type")},
        "key_signals": [s for s in rec["signals"] if s["points"] > 0][:TOP_SIGNALS],
        # Re-checked now, so an offer that has expired since the run is not shown.
        "offer": tools.check_offer(customer_id, rec["product_id"]),
        "explanation": explanation,
        "explanation_source": explanation_source,
        "source": source,
        "saved_at": saved_at,
    }


def _recommendation_rows(contexts: dict, runs: dict) -> list:
    """Agent-selected picks from each customer's latest run, then the engine's
    top-ranked products that the agent didn't pick (or all of them, when the
    customer has never been run). The engine stays the single source of scores."""
    rows = []
    for customer_id, ctx in contexts.items():
        run = runs.get(customer_id)
        chosen = set()
        if run:
            for rec in run["recommendations"]:
                rows.append(_recommendation_row(customer_id, rec, "agent", rec["explanation"],
                                                rec["explanation_source"], run["saved_at"]))
                chosen.add(rec["product_id"])
        ranked = engine.rank_recommendations(customer_id, ctx=ctx, limit=ENGINE_PICKS_PER_CUSTOMER)
        for candidate in ranked["candidates"]:
            if candidate["product_id"] not in chosen:
                rows.append(_recommendation_row(customer_id, candidate, "engine",
                                                candidate["evidence_summary"], "engine", None))
    return rows


def _customers_by_label(rows: list, kinds: tuple) -> list:
    buckets = {}
    for row in rows:
        for item in row["opportunities"]:
            if item["kind"] in kinds:
                buckets.setdefault(item["label"], []).append(row["customer_id"])
    return sorted(({"label": label, "customer_ids": ids} for label, ids in buckets.items()),
                  key=lambda b: (-len(b["customer_ids"]), b["label"]))


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def overview() -> dict:
    """Dashboard KPIs and activity, plus one summary row per customer."""
    ids = _customer_ids()
    contexts, runs = _contexts(ids), _runs(ids)
    rows = [_customer_row(contexts[cid], runs[cid]) for cid in ids]
    events = tools.BROWSING_HISTORY
    recent_runs = sorted(({"customer_id": cid, **_run_summary(run)} for cid, run in runs.items() if run),
                         key=lambda r: r["saved_at"], reverse=True)

    return {
        "as_of": date.today().isoformat(),
        "kpis": {
            "total_customers": len(rows),
            "customers_with_opportunities": sum(r["has_opportunity"] for r in rows),
            "customers_with_gaps": sum(bool(r["opportunities"]) for r in rows),
            "products_in_catalogue": len(tools.PRODUCTS),
            "active_offers": len(_active_offers()),
            "total_offers": len(tools.OFFERS),
            "customers_with_ai_runs": len(recent_runs),
            "ai_recommendations_saved": sum(r["recommendation_count"] for r in recent_runs),
        },
        "customer_activity": {
            "purchases": len(tools.WARDROBES),
            "purchase_value": sum(w["price_paid"] for w in tools.WARDROBES),
            "browsing_events": len(events),
            "event_types": dict(Counter(e["event_type"] for e in events)),
            "browsing_window": ([min(e["timestamp"] for e in events), max(e["timestamp"] for e in events)]
                                if events else None),
        },
        "opportunity_overview": {
            "gap_categories": _customers_by_label(rows, ("missing_category", "imbalance")),
            "occasion_gaps": _customers_by_label(rows, ("occasion",)),
            "intent_strength": dict(Counter(r["intent_strength"] for r in rows)),
            "no_gap_customers": [r["customer_id"] for r in rows if not r["opportunities"]],
        },
        "recent_runs": recent_runs,
        "customers": rows,
    }


def recommendations(customer_id: str | None = None) -> dict:
    """Recommendation rows across customers, or for one customer."""
    ids = [customer_id] if customer_id else _customer_ids()
    rows = _recommendation_rows(_contexts(ids), _runs(ids))
    return {
        "as_of": date.today().isoformat(),
        "engine_picks_per_customer": ENGINE_PICKS_PER_CUSTOMER,
        "recommendation_types": list(engine.RECOMMENDATION_TYPES),
        "rows": rows,
    }


def analytics() -> dict:
    """Aggregates behind the Analytics page. Each block answers one business question."""
    ids = _customer_ids()
    contexts, runs = _contexts(ids), _runs(ids)
    rows = [_customer_row(contexts[cid], runs[cid]) for cid in ids]
    recs = _recommendation_rows(contexts, runs)

    purchases = [item for cid in ids for item in tools.get_wardrobe(cid)]
    events = [event for cid in ids for event in tools.get_browsing_history(cid)]

    purchase_count = Counter(p["category"] for p in purchases)
    purchase_value = Counter()
    for p in purchases:
        purchase_value[p["category"]] += p["price_paid"]

    browsed = Counter(e["category"] for e in events)
    carted = Counter(e["category"] for e in events if e["event_type"] in CART_OR_SAVE)

    active = _active_offers()
    seasons = Counter(r["current_season"] for r in rows)
    seasonal_blocks = []
    for season in seasons:
        ctx = next(contexts[r["customer_id"]] for r in rows if r["current_season"] == season)
        s = ctx["seasonal"]
        seasonal_blocks.append({
            "season": season,
            "customers": seasons[season],
            "has_trend_data": s["has_trend_data"],
            "source": s["source"],
            "trending_categories": s["trending_categories"],
            "trending_subcategories": s["trending_subcategories"],
            "catalogue_in_season": s["in_season_catalogue"]["total"],
            "shoppable_by_customer": [
                {"customer_id": r["customer_id"],
                 **{k: contexts[r["customer_id"]]["seasonal"]["in_season_catalogue"][k]
                    for k in ("within_budget", "trending_within_budget")}}
                for r in rows if r["current_season"] == season
            ],
        })

    return {
        "as_of": date.today().isoformat(),
        "purchases": {
            "total": len(purchases),
            "by_category": [{"category": c, "purchases": n, "value": purchase_value[c]}
                            for c, n in purchase_count.most_common()],
        },
        "browsing": {
            "total": len(events),
            "event_types": dict(Counter(e["event_type"] for e in events)),
            "by_category": [{"category": c, "events": n, "cart_or_save": carted[c]}
                            for c, n in browsed.most_common()],
        },
        "gaps": {
            "missing_categories": _customers_by_label(rows, ("missing_category", "imbalance")),
            "occasion_gaps": _customers_by_label(rows, ("occasion",)),
            "customers_without_gaps": [r["customer_id"] for r in rows if not r["opportunities"]],
        },
        "intent": dict(Counter(r["intent_strength"] for r in rows)),
        "recommendations": {
            "total": len(recs),
            "agent_selected": sum(1 for r in recs if r["source"] == "agent"),
            "primary_type": dict(Counter(r["primary_type"] for r in recs)),
            "with_offer": sum(1 for r in recs if r["offer"]),
        },
        "offers": {
            "active": len(active),
            "total": len(tools.OFFERS),
            "active_by_type": dict(Counter(o["offer_type"] for o in active)),
        },
        "seasonal": {
            "catalogue_by_season": dict(Counter(p["season"] for p in tools.PRODUCTS)),
            "seasons": seasonal_blocks,
        },
    }
