"""FastAPI backend for the retail personalisation agent.

Run with:  uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import platform_views
import tools
from agent import MODEL, AgentError, customer_intelligence, run_agent

app = FastAPI(
    title="Retail Personalisation Agent",
    description="Customer intelligence and explained product recommendations driven by a Gemini agent.",
    version="2.0.0",
)

# The Vite dev server. 5173 is Vite's default, but it walks up to 5174, 5175...
# when that port is already taken, so match any localhost port rather than
# pinning one and failing CORS the moment Vite picks a different number.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fields shown in the customer roster - enough to choose from, not the detail.
SUMMARY_FIELDS = (
    "customer_id",
    "preferred_styles",
    "preferred_colors",
    "budget",
    "preferred_occasions",
    "current_season",
)


def _require_customer(customer_id: str) -> dict:
    try:
        return tools.get_customer_profile(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
def root() -> dict:
    """Tiny index so hitting the bare host tells you what is available."""
    return {
        "service": "retail-personalisation-agent",
        "model": MODEL,
        "endpoints": [
            "GET /customers",
            "GET /customers/{customer_id}",
            "GET /customers/{customer_id}/intelligence",
            "POST /recommend/{customer_id}",
            "GET /platform/overview",
            "GET /platform/recommendations?customer_id=",
            "GET /platform/analytics",
        ],
    }


# --------------------------------------------------------------------------
# Platform views - read-only aggregation for the retailer pages. They reuse the
# intelligence modules, the engine and saved runs; no model calls, no new scoring.
# --------------------------------------------------------------------------

def _platform(view, *args):
    try:
        return view(*args)
    except Exception as exc:                      # never leak a raw traceback
        raise HTTPException(status_code=500,
                            detail=f"Could not build this view: {exc}") from exc


@app.get("/platform/overview")
def platform_overview() -> dict:
    """Dashboard KPIs, activity and one summary row per customer."""
    return _platform(platform_views.overview)


@app.get("/platform/recommendations")
def platform_recommendations(customer_id: str | None = None) -> dict:
    """Agent-selected picks from saved runs plus engine-ranked products."""
    if customer_id:
        _require_customer(customer_id)
    return _platform(platform_views.recommendations, customer_id)


@app.get("/platform/analytics")
def platform_analytics() -> dict:
    """Aggregates for the analytics page."""
    return _platform(platform_views.analytics)


@app.get("/customers")
def list_customers() -> list:
    """Profile summaries for all customers, for the roster."""
    purchases = {c["customer_id"]: 0 for c in tools.CUSTOMERS}
    browsing = dict(purchases)
    for row in tools.WARDROBES:
        purchases[row["customer_id"]] = purchases.get(row["customer_id"], 0) + 1
    for row in tools.BROWSING_HISTORY:
        browsing[row["customer_id"]] = browsing.get(row["customer_id"], 0) + 1
    return [
        {**{field: c[field] for field in SUMMARY_FIELDS},
         "purchase_count": purchases[c["customer_id"]],
         "browsing_event_count": browsing[c["customer_id"]]}
        for c in tools.CUSTOMERS
    ]


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    """Full profile for one customer."""
    return _require_customer(customer_id)


@app.get("/customers/{customer_id}/intelligence")
def get_intelligence(customer_id: str) -> dict:
    """Deterministic customer intelligence - profile, gaps, purchase patterns,
    browsing intent and seasonal context. No model call, so it is instant and
    uses no API quota."""
    _require_customer(customer_id)
    try:
        return customer_intelligence(customer_id)
    except Exception as exc:                      # never leak a raw traceback
        raise HTTPException(status_code=500,
                            detail=f"Customer analysis failed unexpectedly: {exc}") from exc


@app.post("/recommend/{customer_id}")
def recommend(customer_id: str) -> dict:
    """Run the agent and return its structured, grounded output.

    Takes several seconds - the agent makes multiple round trips to Gemini and
    executes each tool call in between.
    """
    _require_customer(customer_id)

    try:
        result = run_agent(customer_id)
    except AgentError as exc:
        message = str(exc)
        # A daily quota is the one failure a user can actually act on, so it
        # gets its own status and keeps the instruction in the message.
        status = 429 if "quota" in message.lower() else 502
        raise HTTPException(status_code=status, detail=message) from exc
    except Exception as exc:                      # never leak a raw traceback
        raise HTTPException(
            status_code=500,
            detail=f"The recommendation agent failed unexpectedly: {exc}",
        ) from exc

    if result.get("turn_capped"):
        raise HTTPException(
            status_code=504,
            detail=(f"The agent hit its 10-turn safety cap for {customer_id} without settling "
                    f"on a final answer. Try again - this is usually transient."),
        )

    if not result.get("recommendations"):
        raise HTTPException(
            status_code=502,
            detail=(f"The agent finished but produced no usable recommendations for "
                    f"{customer_id}. Try again."),
        )

    return result
