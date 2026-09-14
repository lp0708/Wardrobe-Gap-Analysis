"""Offline checks for how the agent's final answer is parsed and grounded.

Feeds hand-written final answers - some honest, some with deliberate false
claims - through the same code run_agent uses, and checks that false claims
are caught and replaced with evidence-built explanations. No API calls.
"""

import sys

import agent
from intelligence import recommendation_engine as engine

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

failures = []


def check(condition: bool, message: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'}  {message}")
    if not condition:
        failures.append(message)


print("Parsing the final answer")
summary, rows = agent._parse_final_text(
    "SUMMARY: Owns no outerwear and has been browsing jackets.\n"
    "P0158 | Fills their outerwear gap and they added it to their cart.\n"
    "**P0063** | Fills their outerwear gap and they saved it.\n"
    "P0158 | duplicate line should be ignored\n"
)
check(summary == "Owns no outerwear and has been browsing jackets.", "summary line extracted")
check([r["product_id"] for r in rows] == ["P0158", "P0063"], "product lines extracted, duplicates dropped")
check(rows[0]["explanation"].startswith("Fills their outerwear gap"), "explanation taken after the pipe")

print("\nGrounding: C001 (real outerwear gap, no bottom gap)")
ctx = engine.build_customer_context("C001")
rows = [
    # Honest: P0158 really fills the outerwear gap and was really added to cart.
    {"product_id": "P0158", "explanation": "Fills their high-priority outerwear gap and they added it to their cart."},
    # False: bottoms are not a reported gap for C001 (dresses cover them).
    {"product_id": "P0080", "explanation": "Fills the missing bottoms gap in their wardrobe."},
    # False: P0063 has no offer.
    {"product_id": "P0063", "explanation": "A black bomber they saved, now with a 20% discount."},
    # No personalisation signal at all for C001 - the engine gives it no type.
    {"product_id": "P0134", "explanation": "A nice beige shirt."},
    # Hard rule: P0056 (Rs 2,149) costs more than C001's Rs 1,500 budget.
    {"product_id": "P0056", "explanation": "A black bomber they would love."},
]
recs, dropped = agent._build_recommendations(rows, "C001", ctx)
by_id = {r["product_id"]: r for r in recs}
dropped_reasons = {d["product_id"]: d["reason"] for d in dropped}

check(by_id["P0158"]["explanation_source"] == "agent", "honest gap + cart claim keeps the model's text")
check(by_id["P0080"]["explanation_source"] == "engine", "false gap claim is replaced")
check("gap" not in by_id["P0080"]["explanation"].lower(), "replacement explanation makes no gap claim")
check(by_id["P0063"]["explanation_source"] == "engine", "invented discount is replaced")
check(dropped_reasons.get("P0134") == "no personalisation signal", "pick with no signal is dropped")
check(dropped_reasons.get("P0056") == "over budget", "over-budget pick is dropped")
check(all(r["price"] <= ctx["profile"]["budget"] for r in recs), "every kept pick is within budget")

print("\nGrounding: C002 (real 25% offer on P0013)")
ctx = engine.build_customer_context("C002")
recs, _ = agent._build_recommendations([
    {"product_id": "P0013", "explanation": "Fills their shoe gap and has a 25% seasonal sale."},
    {"product_id": "P0112", "explanation": "Pairs with their navy shirt and is on a 40% sale."},
], "C002", ctx)
by_id = {r["product_id"]: r for r in recs}
check(by_id["P0013"]["explanation_source"] == "agent", "correct discount is kept")
check(by_id["P0112"]["explanation_source"] == "engine", "wrong discount percentage is replaced")
check(len(recs) >= agent.MIN_RECOMMENDATIONS, "list is topped up to the minimum from the engine ranking")
check(all(r["selected_by"] in ("agent", "engine_top_up") for r in recs), "every pick records who selected it")

print("\nGrounding: C002 browsing claim with no intent evidence")
candidate = engine.evaluate_product("C002", "P0112", ctx)
check(bool(agent.grounding_issues("They browsed chinos all week.", candidate)),
      "browsing claim without an intent signal is flagged")

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
