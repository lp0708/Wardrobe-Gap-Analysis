<p align="center">
  <img src="frontend/public/logo.png" alt="Recon logo" width="96" />
</p>

<h1 align="center">Recon</h1>

<p align="center">
  <strong>AI-powered retail intelligence for personalised customer recommendations.</strong>
</p>

Recon is a retailer-facing platform that profiles each customer from their purchases, browsing, wardrobe and season, then recommends 3–5 products and offers to put in front of them. Every recommendation comes with the evidence behind it.

A Gemini agent orchestrates the work. Deterministic Python modules supply grounded facts, a transparent scoring engine ranks the catalogue, and the agent chooses the picks and explains them. Every claim is then checked against the data before it reaches the screen.

Built for the **Personalized Retail Recommendation Agent** problem statement: recommend relevant products and offers using customer profile, purchase history, browsing behaviour and seasonal trends, and explain why each one was recommended.

---

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [The platform](#the-platform)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Customer intelligence](#customer-intelligence)
- [Recommendation engine and scoring](#recommendation-engine-and-scoring)
- [Grounding](#grounding)
- [The agent](#the-agent)
- [API reference](#api-reference)
- [Data](#data)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)

---

## Features

- **Customer intelligence:** wardrobe gaps, purchase patterns, browsing intent and seasonal context, each computed deterministically from the data.
- **Explainable ranking:** a multi-signal scoring engine where every point a product earns is recorded with its evidence.
- **Agentic orchestration:** a Gemini agent that decides which tools to call, requests focused rankings, and writes a brief and an explanation for each pick.
- **Grounded output:** product facts and offers always come from the catalogue. Explanations that claim something the evidence doesn't support are replaced.
- **Recommendation types:** every pick is labelled as a wardrobe gap, browsing intent, seasonal or complementary recommendation.
- **Retailer platform:** Dashboard, Customers, Recommendations and Analytics pages, plus a live end-to-end AI demo.
- **Full transparency:** the agent's tool-call trace is shown turn by turn.

---

## How it works

```
React retailer platform
   ├── Dashboard · Customers · Recommendations · Analytics   read-only views
   └── Demo                                                  the full AI workflow
                    │
                 FastAPI
   ├── platform_views.py     aggregates for the platform pages
   └── agent.py              Gemini agent with manual function calling
                    │
   ├── Facts                  tools.py
   │     profile · wardrobe · browsing history · product search · offer check
   │
   ├── Customer intelligence  intelligence/          deterministic Python, no LLM
   │     gap_analysis         what the wardrobe is genuinely missing
   │     purchase_analysis    how the customer actually buys
   │     intent_analysis      what they are browsing towards right now
   │     seasonal_trends      which seasonal signals apply to them
   │
   └── Ranking                intelligence/recommendation_engine.py
         weighted multi-signal scoring, evidence recorded for every point
```

Responsibilities are split three ways:

| Layer | Responsibility |
|---|---|
| **Intelligence modules** | Turn raw data into grounded evidence. |
| **Recommendation engine** | Rank products against that evidence with explicit, inspectable weights. |
| **Agent** | Decide what to look at, which candidates to pick, and how to explain them. |

---

## The platform

A persistent sidebar holds the navigation; on small screens it collapses into a menu.

| Route | What it shows |
|---|---|
| `/dashboard` | KPIs, opportunity overview, customer activity and the latest agent runs |
| `/customers` | Every customer with purchase and browsing activity, intent strength and reported gaps. Filter and search |
| `/customers/:id` | One customer's intelligence and their recommendations |
| `/recommendations` | Agent-selected picks plus engine-ranked products. Filter by customer, type, season, source and offer |
| `/analytics` | What customers buy and browse, where the gaps are, intent strength, the recommendation mix and live offers |
| `/demo` | The end-to-end AI workflow: select a customer, review their intelligence, run the agent, see grounded recommendations and the trace. `/demo?customer=C004` opens with a customer selected |

The platform pages never compute anything new. Every figure is a count or sum over the datasets, the intelligence modules, the engine and saved agent runs, so the platform and the demo always agree.

On the Recommendations pages, each product carries one of two labels:

- **AI-selected:** the agent chose it in that customer's latest run.
- **Engine-ranked:** it's among the engine's top-ranked products for the customer, but the agent didn't pick it.

---

## Getting started

### Prerequisites

- **Python 3.10+**
- **Node.js 20.19+ or 22.12+** (required by Vite 8)
- A **Gemini API key**, available free from [Google AI Studio](https://aistudio.google.com/apikey)

### 1. Clone and install

```bash
git clone https://github.com/lp0708/Wardrobe-Gap-Analysis.git
cd Wardrobe-Gap-Analysis
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Configure

Copy `.env.example` to `.env` (on Windows use `copy` instead of `cp`) and add your key:

```bash
cp .env.example .env
```

### 3. Run

Start the backend:

```bash
python -m uvicorn api:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. It opens on the dashboard.

### 4. Try the demo

1. Click **Demo** in the sidebar.
2. Select a customer. Their profile, intelligence and wardrobe gaps appear instantly, with no model call.
3. Click **Recommend** to run the agent. It takes a few seconds, then shows the agent brief, the recommendations and the tool-call trace.

These customers show off different behaviour:

| Customer | What it demonstrates |
|---|---|
| **C004** | No wardrobe gaps, strong browsing intent. Recommendations are driven by intent and complementary fit |
| **C002** | A real shoe gap with live offers; too little browsing to claim intent |
| **C001** | A high-priority outerwear gap backed by browsing |
| **C003** | Almost no data. The system says so rather than guessing |
| **C011** | A generated customer with no browsing and a category imbalance (too many tops for their bottoms) |

C001–C008 are the original hand-built customers; C009–C100 were generated (see [Data](#data)).

---

## Configuration

All settings live in `.env`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | none, required | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-3.6-flash` | The Gemini model the agent uses |
| `AGENT_CACHE` | `0` | Completed runs are always saved to `.agent_cache/`. Set to `1` to also replay a customer's saved run instead of calling Gemini again |

### Free-tier quota

A free-tier Gemini key allows roughly **20 requests per day per model**, and one agent run usually uses 3.

- **Switch model:** quota is counted per model, so changing `GEMINI_MODEL` to another Flash model gives a fresh allowance.
- **Pre-warm for demos:** run each customer once, then set `AGENT_CACHE=1`. The demo then replays saved runs with no API calls.

If the quota runs out, or the model reports high demand, the app shows a readable error rather than failing silently.

---

## Customer intelligence

Four deterministic modules turn raw data into evidence. None of them call an LLM.

| Module | Derives | Guards against over-claiming |
|---|---|---|
| `gap_analysis` | Missing categories, category imbalance, occasion gaps and colour gaps, cross-referenced with browsing. A dress counts as covering the top + bottom need | It is the **only** source of gap claims |
| `purchase_analysis` | Category, colour and style frequency; repeat purchases; recent purchases; average spend, typical price range and share of budget | Needs 3+ purchases before claiming a pattern; ties are reported as ties |
| `intent_analysis` | Intent by category, occasion and colour. Cart and save events outweigh views, repeat views outweigh single views, and recent events outweigh older ones | A category needs 2+ events; thin browsing reports *"not enough browsing to infer intent"* |
| `seasonal_trends` | The customer's season, curated trends for it, overlap with their preferences, in-season stock within budget, and observed browsing demand | Trend data is labelled as curated demo data; observed demand is context only and never scored |

---

## Recommendation engine and scoring

**Hard rules come first.** Products over budget, in an avoided colour, or already owned are excluded before any scoring.

**Every other product earns points from signals.** Each matching signal adds or removes points and records the evidence behind them. All weights live in `WEIGHTS` in `intelligence/recommendation_engine.py`.

| Signal group | Examples |
|---|---|
| Gap | Fills a reported missing category (+30 high priority, +20 medium); covers a reported occasion gap |
| Intent | Strong (+18) or moderate (+10) category intent; the exact product was carted (+8), saved or viewed repeatedly |
| Season / trend | In season; on the curated trend list; high-demand category. Off-season items get −6 |
| Complementary | Pairs with something the customer owns (complementary category, same occasion, colours that go together) |
| Preference | Preferred colour, style or occasion |
| Purchase history | Repeat category or colour, dominant style, priced within usual spend |
| Offer | An active offer the customer qualifies for, up to +10 |
| Penalty | Very similar to something already owned (−10) |

**Example: C004's Beige Chinos score 68.**

| Points | Evidence |
|---|---|
| +18 | Strong browsing intent for bottoms (3 events) |
| +8 | Preferred colour (beige) |
| +6 | Preferred style |
| +5 | Same item type they browsed (chinos) |
| +5 | Preferred occasion (casual) |
| +4 | Browsing centres on casual items |
| +4 | Browsing centres on beige items |
| +4 | 2 past purchases in beige |
| +4 | Priced within usual spend |
| +3 | Viewed this exact product 5 times |
| +3 | 71% of purchases are casual |
| +2 | All-season item |
| +2 | Casual style is on the curated trend list |

Scores aren't out of 100. They're meaningful for comparing products **within one customer**, and products that fill a real gap usually rank highest.

**Recommendation types.** Each candidate gets one or more types: `gap`, `intent`, `seasonal`, `complementary`. A type is assigned only when its defining evidence exists. The primary type follows the precedence gap → intent → seasonal → complementary.

---

## Grounding

- **Facts come from data.** Product names, prices, colours, offers, types and scores always come from the catalogue and the engine, never from the model's text.
- **Explanations are checked.** Each explanation is compared with the product's recorded signals. If it claims a gap, browsing behaviour, a trend or an offer the evidence doesn't support, or quotes the wrong discount, it's replaced with an explanation built from the evidence, and the UI says so.
- **Hard rules are enforced.** Picks that are over budget, in an avoided colour, already owned, unknown, or have no personalisation signal are dropped. If fewer than 3 survive, the list is topped up from the engine ranking.

---

## The agent

The agent uses Gemini with **manual function calling**. Automatic function calling is disabled, so every tool call is executed and logged by the application and shown in the trace.

| Layer | Tools |
|---|---|
| Facts | `get_customer_profile`, `get_wardrobe`, `get_browsing_history`, `search_products`, `check_offer` |
| Intelligence | `analyze_outfit_gaps`, `analyze_purchase_patterns`, `detect_browsing_intent`, `get_seasonal_context` |
| Ranking | `rank_recommendations`, with an optional `category` or `recommendation_type` focus |

A typical run takes three turns:

1. Gather the profile and all four analyses in parallel.
2. Request rankings, often with extra focused rankings the agent chooses itself.
3. Write the brief and the recommendations.

---

## API reference

| Endpoint | Returns |
|---|---|
| `GET /customers` | Roster summaries |
| `GET /customers/{id}` | Full customer profile |
| `GET /customers/{id}/intelligence` | Profile, gaps, purchase patterns, browsing intent and seasonal context. No model call |
| `POST /recommend/{id}` | Runs the agent: intelligence plus trace, agent brief and grounded recommendations |
| `GET /platform/overview` | Dashboard KPIs, activity, opportunity overview and one summary row per customer |
| `GET /platform/recommendations?customer_id=` | Recommendation rows for all customers, or one |
| `GET /platform/analytics` | Aggregates for the Analytics page |

Interactive docs are available at **http://localhost:8000/docs** while the backend is running.

---

## Data

The dataset is plain JSON in the repository root.

| File | Records | Contents |
|---|---|---|
| `customers.json` | 100 | Preferences (styles, colours, occasions), avoided colours, budget, current season |
| `products.json` | 420 | Catalogue: category, subcategory, colour, style tags, occasion, season, price, store |
| `wardrobes.json` | 625 | Purchase history: product, date acquired, price paid |
| `browsing_history.json` | 1,304 | Browsing events (`viewed`, `saved`, `added_to_cart`, `abandoned_cart`) with timestamps and view counts |
| `offers.json` | 45 | Offers per product, including category-pair bundle conditions and expiry dates |
| `seasonal_trends.json` | 3 seasons | Curated seasonal trend data for this prototype, not market data |

### Original and generated customers

| Range | Source |
|---|---|
| **C001–C008**, products P0001–P0180, offers O001–O030 | The original hand-built dataset. These are the demo personas, and their records are unchanged |
| **C009–C100**, products P0181–P0420, offers O031–O045 | Added by a seeded generator, for population-level analytics |

Generated customers come from segment profiles such as campus casual, office smart, festive fusion and value basics. Their budget, preferences, purchases and browsing therefore point the same way, rather than each field being random. Across the 92 generated customers:

- **Browsing:** 28 rich, 34 moderate, 17 sparse and 13 with none.
- **Wardrobes:** 74 have reported gaps and 18 have none.
- **Behaviour:** 36 have abandoned carts and 62 buy the same category repeatedly.
- **Budget:** every purchase is priced within the customer's stated budget.

The generator only uses values that already appear in the original data, so there are no new categories, occasions, seasons, style tags or event types. Two further rules keep the original customers' own analysis unaffected:

- New offers are attached only to new products.
- No browsing event is dated after the last original event.

### Regenerating the dataset

The original files are kept in `data/backup/`. Rebuild the current dataset from them (the same seed gives a byte-identical result):

```bash
python data/generate_dataset.py --source data/backup --customers 100 --products 420 --offers 45 --seed 42
```

Preview a different size or seed without writing anything:

```bash
python data/generate_dataset.py --source data/backup --customers 150 --seed 7 --dry-run
```

Validate the result:

```bash
python data/validate_dataset.py
```

About the generator:

- **Totals, not increments:** `--customers`, `--products` and `--offers` are totals, so running against already-expanded data adds nothing.
- **Existing records kept exactly:** it appends only, and refuses to write if any existing record would change.
- **Validation:** the validator checks schema, unique IDs, references, allowed values, dates and prices, and confirms the original records are byte-identical to the backup.

---

## Testing

Runs without API calls:

```bash
python test_tools.py                     # data layer
python test_gap_analysis.py              # gap detection for every customer
python test_intelligence.py              # ~45,000 checks of every module against the raw data
python test_grounding.py                 # explanation grounding and hard rules
python data/validate_dataset.py          # dataset schema, references and allowed values
python tests/golden_snapshot.py compare  # C001–C008 output versus the saved baseline
```

**Golden snapshots.** `tests/golden_snapshot.py` compares C001–C008 against snapshots captured on the original dataset.

- **Must be identical:** profile, gaps, purchase patterns, browsing intent and customer-specific seasonal fields.
- **Must score as before:** every product that was ranked before.
- **Reported as expected changes:** whole-catalogue seasonal counts, and new products entering their rankings, since both grow with the dataset.

On the current dataset it reports 0 failures.

**Known test failures.** `test_intelligence.py` reports 2 failures on the expanded data, both "category cap in the top 8", for C022 and C054. Those customers have very low budgets, so almost everything they can afford falls into one or two categories. That leaves fewer than 8 places under the 2-per-category cap, and the engine then fills the rest by score, as designed. The test's check doesn't allow for that case.

Uses API quota:

```bash
python test_agent.py C001                         # one full agent run
python tests/golden_snapshot.py compare --agent   # also re-run the agent for the baseline customers
```

The frontend can be built and linted from `frontend/`:

```bash
npm run build
npm run lint
```

---

## Project structure

```
.
├── api.py                    FastAPI app and endpoints
├── agent.py                  Gemini agent, tool declarations, grounding, saved runs
├── platform_views.py         Read-only aggregates for the platform pages
├── tools.py                  Data access layer
├── intelligence/
│   ├── gap_analysis.py
│   ├── purchase_analysis.py
│   ├── intent_analysis.py
│   ├── seasonal_trends.py
│   └── recommendation_engine.py
├── *.json                    Dataset and curated seasonal trends
├── data/
│   ├── generate_dataset.py   Seeded, append-only dataset expansion
│   ├── validate_dataset.py   Dataset validation
│   └── backup/               Original dataset
├── tests/
│   ├── golden_snapshot.py    Baseline capture and comparison for C001–C008
│   └── golden_snapshots/
├── test_*.py                 Test suites
└── frontend/
    ├── public/               Logo and favicon
    └── src/
        ├── App.jsx           Routes
        ├── api.js            Backend client
        ├── platform/         Layout, design system and shared UI
        ├── pages/            Dashboard, Customers, Recommendations, Analytics, Demo
        └── components/       Demo workflow components
```

---

## Known limitations

- **Seasonal trends are curated demo data**, not market data or a forecast. Every customer's current season is monsoon, so seasonal signals differ between customers only through their preferences and budget.
- **Generated customers are synthetic.** C009–C100 come from segment profiles, not real shoppers, so population figures show how the system behaves at scale rather than real market patterns.
- **Browsing covers about five weeks** (5 August – 8 September 2026). Intent is scored against the latest event in the dataset so results are reproducible, while offer validity uses today's date.
- **Imbalance gaps appear only in generated data.** 15 generated customers have one (C011, for example); none of the original eight do.
- **Platform pages slow down as the data grows.** With 100 customers, the Recommendations and Analytics pages rank every customer on each load and take several seconds. Recommendations also renders every row at once.
- **Scoring weights are hand-tuned** for sensible, explainable ordering; they aren't learned.
- **The grounding check is keyword-based.** It catches false gap, browsing, trend and offer claims and wrong discounts. Subtler misstatements, such as a wrong occasion, rely on the agent's instructions.
- **The agent's output is non-deterministic.** Picks and wording can vary between runs; the intelligence layer and the engine do not.
- **The dataset has no demographic data**, so none is shown or used.
