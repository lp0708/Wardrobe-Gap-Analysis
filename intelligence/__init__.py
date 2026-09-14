"""Deterministic customer-intelligence modules.

Each module turns raw data into grounded evidence the agent can reason over:

    gap_analysis           what the wardrobe is genuinely missing
    intent_analysis        what the customer is browsing towards right now
    purchase_analysis      how the customer actually buys
    seasonal_trends        which seasonal signals apply to them
    recommendation_engine  ranks products by combining all of the above

None of them call an LLM. The Gemini agent decides which to call and turns
their output into recommendations and explanations.
"""
