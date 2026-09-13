"""FastAPI backend wrapping the wardrobe recommendation agent.

Run with:  uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import tools
from agent import MODEL, AgentError, run_agent

app = FastAPI(
    title="Wardrobe Gap Recommendation Agent",
    description="Gap analysis and product recommendations driven by a Gemini agent.",
    version="1.0.0",
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

# Fields shown in the customer selector - enough to populate it, not the wardrobe.
SUMMARY_FIELDS = (
    "customer_id",
    "preferred_styles",
    "preferred_colors",
    "budget",
    "preferred_occasions",
    "current_season",
)


@app.get("/")
def root() -> dict:
    """Tiny index so hitting the bare host tells you what is available."""
    return {
        "service": "wardrobe-gap-recommendation-agent",
        "model": MODEL,
        "endpoints": ["/customers", "/customers/{customer_id}", "/recommend/{customer_id}"],
    }


@app.get("/customers")
def list_customers() -> list:
    """Profile summaries for all customers, for the selector dropdown."""
    return [{field: customer[field] for field in SUMMARY_FIELDS} for customer in tools.CUSTOMERS]


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    """Full profile for one customer."""
    try:
        return tools.get_customer_profile(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/recommend/{customer_id}")
def recommend(customer_id: str) -> dict:
    """Run the agent and return its structured output.

    Takes several seconds - the agent makes multiple round trips to Gemini and
    executes each tool call in between.
    """
    try:
        tools.get_customer_profile(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
            detail=(
                f"The agent hit its 10-turn safety cap for {customer_id} without "
                f"settling on a final answer. Try again - this is usually transient."
            ),
        )

    if not result.get("recommendations"):
        raise HTTPException(
            status_code=502,
            detail=(
                f"The agent finished but produced no usable recommendations for "
                f"{customer_id}. Try again."
            ),
        )

    return {
        "customer_id": result["customer_id"],
        "gaps": result["gaps"],
        "trace": result["trace"],
        "recommendations": result["recommendations"],
        "final_text": result.get("final_text", ""),
    }
