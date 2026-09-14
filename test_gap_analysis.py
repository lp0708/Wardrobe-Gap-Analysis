"""Run gap analysis for all 8 customers, with the wardrobe shown alongside
each result so the output can actually be checked rather than trusted."""

import json
from collections import Counter

import tools
from intelligence import gap_analysis

CUSTOMERS = [c["customer_id"] for c in tools.CUSTOMERS]

for cid in CUSTOMERS:
    profile = tools.get_customer_profile(cid)
    wardrobe = tools.get_wardrobe(cid)
    history = tools.get_browsing_history(cid)
    counts = Counter(i["category"] for i in wardrobe)

    print("=" * 74)
    print(f"{cid}")
    print("=" * 74)
    print(f"  prefers      : occasions={profile['preferred_occasions']} "
          f"colors={profile['preferred_colors']} styles={profile['preferred_styles']}")
    print(f"  owns ({len(wardrobe)})    : " + ", ".join(
        f"{c}x{counts[c]}" for c in gap_analysis.ALL_CATEGORIES if counts.get(c)) or "  owns: nothing")
    print(f"  occasions    : {sorted({i['occasion'] for i in wardrobe})}")
    print(f"  colors       : {sorted({i['color'] for i in wardrobe})}")
    if history:
        print(f"  browsed ({len(history)})  : " + ", ".join(
            f"{e['product_id']}({e['category']}/{e['occasion']},{e['event_type']})" for e in history))
    else:
        print("  browsed      : (none)")
    print("\n  --> gaps:")
    print("\n".join("  " + line for line in
                    json.dumps(gap_analysis.analyze_outfit_gaps(cid), indent=2).splitlines()))
    print()

# ---------------------------------------------------------------- edge cases
print("=" * 74)
print("EDGE CASES")
print("=" * 74)

print("\n  a) near-empty wardrobe (C003 owns exactly 1 item) - handled above, no crash")

print("\n  b) customer with NO browsing history at all:")
saved_history = tools.BROWSING_HISTORY[:]
tools.BROWSING_HISTORY[:] = [e for e in tools.BROWSING_HISTORY if e["customer_id"] != "C001"]
result = gap_analysis.analyze_outfit_gaps("C001")
print(f"     C001 with browsing stripped -> missing={[m['category'] for m in result['missing_categories']]}, "
      f"priority={[m['priority'] for m in result['missing_categories']]}, "
      f"signal={[m['has_browsing_signal'] for m in result['missing_categories']]}")
tools.BROWSING_HISTORY[:] = saved_history

print("\n  c) empty preferred_occasions / preferred_colors lists:")
profile = next(c for c in tools.CUSTOMERS if c["customer_id"] == "C001")
saved = (profile["preferred_occasions"], profile["preferred_colors"])
profile["preferred_occasions"], profile["preferred_colors"] = [], []
result = gap_analysis.analyze_outfit_gaps("C001")
print(f"     -> occasion_gaps={result['occasion_gaps']}, color_gap={result['color_gap']} (no preference = no gap)")
profile["preferred_occasions"], profile["preferred_colors"] = saved

print("\n  d) completely empty wardrobe:")
saved_wardrobe = tools.WARDROBES[:]
tools.WARDROBES[:] = [w for w in tools.WARDROBES if w["customer_id"] != "C001"]
result = gap_analysis.analyze_outfit_gaps("C001")
print(f"     -> missing={[m['category'] for m in result['missing_categories']]}")
print(f"     -> occasion_gaps={[g['occasion'] for g in result['occasion_gaps']]}, color_gap={result['color_gap']}")
tools.WARDROBES[:] = saved_wardrobe

print("\n  e) unknown customer still raises ValueError:")
try:
    gap_analysis.analyze_outfit_gaps("C999")
except ValueError as exc:
    print(f"     ValueError: {exc}")

print("\n  f) IMBALANCE branch: no real customer owns 3+ more of a paired category")
print("     (largest category holding in the dataset is 4), so this injects the")
print("     spec's own example - 5 bottoms vs 1 top - to prove the branch fires:")
tools.WARDROBES[:] = [w for w in tools.WARDROBES if w["customer_id"] != "C001"]
bottoms = [p["product_id"] for p in tools.PRODUCTS if p["category"] == "bottom"][:5]
tops = [p["product_id"] for p in tools.PRODUCTS if p["category"] == "top"][:1]
for pid in bottoms + tops:
    tools.WARDROBES.append({"customer_id": "C001", "owned_product_id": pid,
                            "date_acquired": "2026-01-01", "price_paid": 999})
result = gap_analysis.analyze_outfit_gaps("C001")
print("     " + json.dumps(result["imbalances"], indent=2).replace("\n", "\n     "))
tools.WARDROBES[:] = saved_wardrobe

print("\n" + "=" * 74)
print("done")
