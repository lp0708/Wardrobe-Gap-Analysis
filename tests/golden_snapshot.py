"""Capture or compare the system's output for the golden customers C001-C008.

    python tests/golden_snapshot.py capture             deterministic layers
    python tests/golden_snapshot.py adopt-runs          add the saved agent runs as the agent baseline
    python tests/golden_snapshot.py compare [--agent]   re-run and diff against the snapshots

Diff rules:
  * profile, gaps, purchase_patterns and browsing_intent must be identical.
  * seasonal_context must be identical except `in_season_catalogue` and
    `observed_demand`, which are counted over the whole catalogue and all
    shoppers and so change whenever the dataset grows. Those are reported as
    expected changes.
  * engine ranking: new products may enter the list (expected), but every
    product that was ranked before must score exactly as it did.
  * agent picks (--agent) come from a non-deterministic model, so overlap is
    reported rather than required.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intelligence import recommendation_engine as engine  # noqa: E402

SNAPSHOT_DIR = ROOT / "tests" / "golden_snapshots"
GOLDEN = [f"C{n:03d}" for n in range(1, 9)]
STRICT_SECTIONS = ("profile", "gaps", "purchase_patterns", "browsing_intent")
POPULATION_SEASONAL_FIELDS = ("in_season_catalogue", "observed_demand")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def deterministic(customer_id: str) -> dict:
    ctx = engine.build_customer_context(customer_id)
    ranked = engine.rank_recommendations(customer_id, ctx=ctx, limit=engine.MAX_LIMIT)
    return {
        "customer_id": customer_id,
        "profile": ctx["profile"],
        "gaps": ctx["gaps"],
        "purchase_patterns": ctx["purchases"],
        "browsing_intent": ctx["intent"],
        "seasonal_context": ctx["seasonal"],
        "ranking": ranked,
    }


def summarise_run(run: dict) -> dict:
    return {
        "model": run["model"],
        "saved_at": run.get("saved_at"),
        "summary": run["summary"],
        "tool_calls": [step["tool"] for step in run["trace"]],
        "recommendations": [
            {key: rec[key] for key in ("product_id", "name", "score", "types", "primary_type",
                                       "explanation", "explanation_source")}
            for rec in run["recommendations"]
        ],
    }


def fresh_agent_run(customer_id: str) -> dict:
    import agent  # imported lazily: only needed for agent comparisons

    agent.CACHE_ENABLED = False  # never replay a saved run when comparing
    return summarise_run(agent.run_agent(customer_id))


def diff(before, after, path=""):
    """Yield (path, before, after) for every difference between two JSON values."""
    if type(before) is not type(after):
        yield path, before, after
    elif isinstance(before, dict):
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                yield f"{path}.{key}", before.get(key, "<missing>"), after.get(key, "<missing>")
            else:
                yield from diff(before[key], after[key], f"{path}.{key}")
    elif isinstance(before, list):
        if len(before) != len(after):
            yield f"{path}.length", len(before), len(after)
        for index, (x, y) in enumerate(zip(before, after)):
            yield from diff(x, y, f"{path}[{index}]")
    elif before != after:
        yield path, before, after


def load_snapshot(customer_id: str) -> dict | None:
    path = SNAPSHOT_DIR / f"{customer_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_snapshot(customer_id: str, snapshot: dict) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_DIR / f"{customer_id}.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def capture() -> None:
    for customer_id in GOLDEN:
        existing = load_snapshot(customer_id) or {}
        snapshot = {"deterministic": deterministic(customer_id)}
        if "agent" in existing:
            snapshot["agent"] = existing["agent"]
        save_snapshot(customer_id, snapshot)
        print(f"captured {customer_id}: {snapshot['deterministic']['ranking']['eligible']} eligible products ranked")


def adopt_runs() -> None:
    from agent import load_saved_run

    for customer_id in GOLDEN:
        snapshot = load_snapshot(customer_id)
        if snapshot is None:
            print(f"{customer_id}: no snapshot - run capture first")
            continue
        run = load_saved_run(customer_id)
        if run is None:
            print(f"{customer_id}: no saved agent run - agent baseline skipped")
            continue
        snapshot["agent"] = summarise_run(run)
        save_snapshot(customer_id, snapshot)
        picks = [r["product_id"] for r in snapshot["agent"]["recommendations"]]
        print(f"{customer_id}: adopted saved run from {run['saved_at']} ({run['model']}): {picks}")


def print_differences(label: str, differences: list, limit: int = 12) -> None:
    for where, old, new in differences[:limit]:
        print(f"      {where}: {old!r} -> {new!r}")
    if len(differences) > limit:
        print(f"      ... {len(differences) - limit} more")


def compare(with_agent: bool) -> int:
    failed_customers = 0
    for customer_id in GOLDEN:
        snapshot = load_snapshot(customer_id)
        if snapshot is None:
            print(f"{customer_id}: no snapshot - run capture first")
            failed_customers += 1
            continue
        before, now = snapshot["deterministic"], deterministic(customer_id)
        failed = False
        print(f"\n== {customer_id}")

        for section in STRICT_SECTIONS:
            differences = list(diff(before[section], now[section], section))
            print(f"    {section:20} {'identical' if not differences else f'FAIL: {len(differences)} difference(s)'}")
            print_differences(section, differences)
            failed |= bool(differences)

        seasonal_before = {k: v for k, v in before["seasonal_context"].items() if k not in POPULATION_SEASONAL_FIELDS}
        seasonal_now = {k: v for k, v in now["seasonal_context"].items() if k not in POPULATION_SEASONAL_FIELDS}
        differences = list(diff(seasonal_before, seasonal_now, "seasonal_context"))
        print(f"    {'seasonal (customer)':20} {'identical' if not differences else f'FAIL: {len(differences)} difference(s)'}")
        print_differences("seasonal", differences)
        failed |= bool(differences)
        for field in POPULATION_SEASONAL_FIELDS:
            changes = list(diff(before["seasonal_context"][field], now["seasonal_context"][field], field))
            print(f"    {'seasonal ' + field:20} {'unchanged' if not changes else 'expected change'}")
            print_differences(field, changes, limit=6)

        ctx = engine.build_customer_context(customer_id)
        before_ids = [c["product_id"] for c in before["ranking"]["candidates"]]
        now_ids = [c["product_id"] for c in now["ranking"]["candidates"]]
        rescored = []
        for candidate in before["ranking"]["candidates"]:
            current = engine.evaluate_product(customer_id, candidate["product_id"], ctx)
            if (current["score"], current["types"], current["exclusion_reason"]) != \
                    (candidate["score"], candidate["types"], None):
                rescored.append(f"{candidate['product_id']} {candidate['score']}{candidate['types']} -> "
                                f"{current['score']}{current['types']} excl={current['exclusion_reason']}")
        entered = [pid for pid in now_ids if pid not in before_ids]
        print(f"    {'ranking':20} eligible {before['ranking']['eligible']} -> {now['ranking']['eligible']}; "
              f"top {len(now_ids)} {'identical' if before_ids == now_ids else f'changed: {len(entered)} new entries'}")
        if entered:
            print(f"      entered: {entered}")
        print(f"    {'ranked products':20} {'all previously ranked products score as before' if not rescored else 'FAIL: score/types changed'}")
        for line in rescored:
            print(f"      {line}")
        failed |= bool(rescored)

        if with_agent:
            if "agent" not in snapshot:
                print("    agent                no baseline run - skipped")
            else:
                old = snapshot["agent"]
                try:
                    new = fresh_agent_run(customer_id)
                except Exception as exc:  # quota or model overload: skip this run, keep comparing
                    print(f"    agent                SKIPPED - agent run failed: {exc}")
                    failed_customers += failed
                    continue
                old_ids = [r["product_id"] for r in old["recommendations"]]
                new_ids = [r["product_id"] for r in new["recommendations"]]
                shared = [pid for pid in new_ids if pid in old_ids]
                print(f"    agent before         {old_ids} ({old['model']})")
                print(f"    agent after          {new_ids} ({new['model']})")
                print(f"    agent overlap        {len(shared)}/{len(old_ids)}; primary types "
                      f"{sorted(r['primary_type'] for r in old['recommendations'])} -> "
                      f"{sorted(r['primary_type'] for r in new['recommendations'])}")

        failed_customers += failed
    print(f"\n{failed_customers} customer(s) with deterministic failures")
    return 1 if failed_customers else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("capture", "adopt-runs", "compare"))
    parser.add_argument("--agent", action="store_true", help="with compare: re-run the Gemini agent (uses quota)")
    args = parser.parse_args()
    if args.mode == "capture":
        capture()
    elif args.mode == "adopt-runs":
        adopt_runs()
    else:
        sys.exit(compare(args.agent))


if __name__ == "__main__":
    main()
