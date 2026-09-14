# Retail Personalisation Agent

A recommendation agent for retailers. It profiles a customer from their purchase history, browsing behaviour, wardrobe and season, then recommends 3–5 products with any offers that apply. Every recommendation comes with the evidence behind it.

Built for the *Personalized Retail Recommendation Agent* problem statement. The goal is to recommend relevant products and offers from customer profile, purchase history, browsing behaviour and seasonal trends, and to explain why.

## Architecture

```
React (retailer console)
   │
FastAPI
   │
Gemini agent ── orchestrates: decides which tools to call, chooses the picks, writes explanations
   │
   ├── Facts                  tools.py
   │     profile · wardrobe · browsing history · product search · offer check
   │
   ├── Customer intelligence  intelligence/        (deterministic Python, no LLM)
   │     gap_analysis        what the wardrobe is genuinely missing
   │     purchase_analysis   how the customer actually buys
   │     intent_analysis     what they are browsing towards right now
   │     seasonal_trends     which seasonal signals apply to them
   │
   └── Ranking                intelligence/recommendation_engine.py
         weighted multi-signal scoring with recorded evidence for every point
```

The jobs are split three ways:

- **The intelligence modules** produce grounded evidence.
- **The engine** ranks products against that evidence.
- **The agent** decides what to look at, which candidates to pick, and how to explain them.

## Customer intelligence

| Module | Derives | Guards against over-claiming |
|---|---|---|
| `gap_analysis` | Missing categories, category imbalance, occasion gaps, colour gap, with browsing cross-reference. A dress covers the top + bottom need. | It is the **only** source of gap claims. |
| `purchase_analysis` | Category, colour and style frequency; repeat purchases; recent purchases; average spend, typical price range (IQR), share of budget. | Needs 3+ purchases before claiming any pattern; ties are reported as ties. |
| `intent_analysis` | Intent by category, occasion and colour. Weights cart and save events above views, repeat views above single views, and recent events above older ones. | A category needs 2+ events. With thin browsing it says *"not enough browsing to infer intent"*. |
| `seasonal_trends` | The customer's season, curated trends for it, overlap with their preferences, shoppable in-season stock, and observed browsing demand across all shoppers. | Trend data is labelled curated demo data. Observed demand is shown as context and never scored. |

## Recommendation engine

Hard rules come first: products over budget, in an avoided colour, or already owned are never scored. Every remaining product earns points from signals. Each signal records its evidence, and all weights live in `WEIGHTS` in `recommendation_engine.py`.

| Signal group | Examples |
|---|---|
| Gap | Fills a reported missing category (+30 high / +20 medium), covers a reported occasion gap |
| Intent | Strong or moderate category intent, same item type browsed, the exact product was carted, saved or viewed repeatedly |
| Season / trend | In season, trending item type, high-demand category, trend colour or style; off-season is a penalty |
| Complementary | Pairs with an owned item (complementary category, same occasion, colours that go together) |
| Preference | Preferred colour, style or occasion |
| Purchase history | Repeat category or colour, dominant style, priced within usual spend |
| Offer | Active qualifying offer, scaled by discount |
| Penalty | Near-duplicate of something they own |

Each candidate gets one or more **recommendation types**: `gap`, `intent`, `seasonal`, `complementary`. A type is only assigned when its defining evidence exists. The primary type follows precedence: gap → intent → seasonal → complementary.

## Grounding

- Product facts, offers, types and signal scores always come from the datasets and the engine, never from the model's text.
- Every explanation is checked against the product's recorded signals. If the model claims a gap, browsing behaviour, a trend or an offer that the evidence doesn't support, or quotes the wrong discount, its wording is replaced with an explanation built from the evidence. The UI says when this happened.
- Picks that break a hard rule (over budget, avoided colour, already owned, unknown product, no personalisation signal) are dropped. If fewer than 3 picks survive, the list is topped up from the engine ranking.

## Agent tools

`get_customer_profile` · `get_wardrobe` · `get_browsing_history` · `analyze_outfit_gaps` · `analyze_purchase_patterns` · `detect_browsing_intent` · `get_seasonal_context` · `rank_recommendations` · `search_products` · `check_offer`

`rank_recommendations` accepts an optional `category` or `recommendation_type`. The agent uses these to ask for kinds of picks the overall ranking under-represents. Automatic function calling is disabled, so every call is executed and logged by our own code, and the trace is shown in the UI.

## API

| Endpoint | Returns |
|---|---|
| `GET /customers` | Roster summaries |
| `GET /customers/{id}` | Full profile |
| `GET /customers/{id}/intelligence` | Profile, gaps, purchase patterns, browsing intent, seasonal context. No model call, so it is instant and uses no quota |
| `POST /recommend/{id}` | Everything above, plus the agent trace, agent brief and grounded recommendations |

## Setup

**Backend** (Python 3.10+):

```bash
pip install -r requirements.txt
cp .env.example .env        # then add your Gemini API key
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
```

## Running

Start the backend:

```bash
python -m uvicorn api:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 and select a customer. Their intelligence appears immediately. Click **Recommend** to run the agent.

## Configuration

Everything is set in `.env` (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | none, required | Get one at https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Which Gemini model the agent uses |
| `AGENT_CACHE` | `0` | Set to `1` to save each run to `.agent_cache/` and replay it on repeat requests |

### Free-tier quota

A free-tier Gemini key allows about **20 requests per day per model**. One agent run usually uses 3 requests. Two ways around the limit:

- **Switch model.** Quota is counted separately for each model, so changing `GEMINI_MODEL` to another Flash model gives you a new daily allowance.
- **Pre-warm the cache for demos.** Set `AGENT_CACHE=1` and run each customer once. After that the demo replays saved runs and makes no API calls.

## Tests

```bash
python test_tools.py          # data layer
python test_gap_analysis.py   # gap detection for all 8 customers
python test_intelligence.py   # ~3,400 checks of every module against the raw data (no API calls)
python test_grounding.py      # explanation grounding and hard rules (no API calls)
python test_agent.py C001     # full agent run (uses API quota)
```

## Known limitations

- **Seasonal trends are curated demo data**, not market data or a forecast. Every customer's `current_season` is monsoon, so seasonal signals differ between customers only through their preferences and budget.
- **Small behavioural sample.** There are 22 browsing events across 8 customers, all within one week. Intent is scored against the latest event in the dataset, so results are reproducible. Offer validity uses today's date.
- **Imbalance detection never triggers on this dataset**, because no customer owns 3+ more items in one category than in its pair. It is covered by an injected test case.
- **Weights are hand-tuned** on this dataset for sensible, explainable ordering. They are not learned.
- **The grounding check is keyword-based.** It catches false gap, browsing, trend and offer claims and wrong discounts. Subtler misstatements, such as a wrong occasion, rely on the agent's instructions.
- **No demographic data** exists in the dataset, so none is shown or used.
