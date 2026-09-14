import { COLOR_SWATCHES } from "../colors";

const rupees = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

const EVENT_LABELS = {
  abandoned_cart: "abandoned in cart",
  added_to_cart: "added to cart",
  saved: "saved",
};

const STRENGTH_RANK = { weak: 0, moderate: 1, strong: 2 };

function Swatch({ color }) {
  return (
    <span
      className="swatch swatch-sm"
      style={{ background: COLOR_SWATCHES[color] || "#cfc6bd" }}
    />
  );
}

function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function Fact({ label, children }) {
  return (
    <div className="fact">
      <span className="fact-label">{label}</span>
      <span className="fact-value">{children}</span>
    </div>
  );
}

function IntelCard({ title, badge, headline, footnote, children }) {
  return (
    <article className="intel-card">
      <div className="intel-card-head">
        <h3 className="intel-card-title">{title}</h3>
        {badge}
      </div>
      {headline && <p className="intel-headline">{headline}</p>}
      {children}
      {footnote && <p className="intel-footnote">{footnote}</p>}
    </article>
  );
}

function PurchaseCard({ patterns }) {
  const { spend } = patterns;

  if (!patterns.has_sufficient_history) {
    return (
      <IntelCard
        title="Purchase patterns"
        badge={<Badge tone="muted">Thin history</Badge>}
        headline={patterns.headline}
        footnote="Too few purchases to use as a recommendation signal."
      />
    );
  }

  const latest = patterns.recent_purchases[0];
  return (
    <IntelCard
      title="Purchase patterns"
      badge={<Badge>{patterns.purchase_count} purchases</Badge>}
      footnote={`Purchases from ${patterns.first_purchase} to ${patterns.last_purchase}`}
    >
      <div className="facts">
        <Fact label="Avg spend">
          {rupees(spend.average)}{" "}
          <span className="fact-sub">{spend.average_vs_budget_pct}% of budget</span>
        </Fact>
        <Fact label="Usual range">
          {rupees(spend.typical_range[0])}&ndash;{rupees(spend.typical_range[1])}
        </Fact>
        <Fact label="Buys most">
          {patterns.category_frequency
            .slice(0, 3)
            .map((row) => `${row.category} ×${row.count}`)
            .join(", ")}
        </Fact>
        <Fact label="Colours">
          <span className="inline-colors">
            {patterns.color_frequency.slice(0, 3).map((row) => (
              <span key={row.color} className="pill-color">
                <Swatch color={row.color} />
                {row.color} ×{row.count}
              </span>
            ))}
          </span>
        </Fact>
        {patterns.repeat_purchases.length > 0 && (
          <Fact label="Repeat buys">
            {patterns.repeat_purchases.map((row) => `${row.subcategory} ×${row.count}`).join(", ")}
          </Fact>
        )}
        {latest && (
          <Fact label="Latest">
            {latest.name} <span className="fact-sub">{latest.date_acquired}</span>
          </Fact>
        )}
      </div>
    </IntelCard>
  );
}

function IntentCard({ intent }) {
  const signals = [
    ...intent.category_intents.map((row) => ({ ...row, label: row.category })),
    ...intent.occasion_intents.map((row) => ({ ...row, label: `${row.occasion} wear` })),
  ].filter((row) => row.strength !== "weak");

  const strongest = signals.reduce(
    (best, row) => (!best || STRENGTH_RANK[row.strength] > STRENGTH_RANK[best.strength] ? row : best),
    null
  );

  const plural = intent.event_count === 1 ? "event" : "events";
  return (
    <IntelCard
      title="Browsing intent"
      badge={
        intent.has_sufficient_evidence ? (
          <Badge tone={strongest.strength === "strong" ? "accent" : "neutral"}>
            {strongest.strength} intent
          </Badge>
        ) : (
          <Badge tone="muted">Insufficient evidence</Badge>
        )
      }
      headline={intent.headline}
      footnote={
        `${intent.event_count} browsing ${plural} up to ${intent.as_of}` +
        (intent.has_sufficient_evidence ? "" : " · not used as an intent signal")
      }
    >
      {signals.length > 0 && (
        <div className="facts">
          {signals.map((row) => (
            <Fact key={row.label} label={row.label}>
              {row.strength} <span className="fact-sub">{row.event_count} events</span>
            </Fact>
          ))}
        </div>
      )}

      {intent.high_intent_products.length > 0 && (
        <ul className="evidence-list">
          {intent.high_intent_products.slice(0, 3).map((event) => (
            <li key={event.product_id}>
              <span className="evidence-name">{event.name}</span>
              <span className="evidence-tag">
                {EVENT_LABELS[event.event_type] || `viewed ${event.view_count}×`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </IntelCard>
  );
}

function SeasonCard({ seasonal }) {
  const footnote = "Trend list is curated demo data for this prototype, not a market forecast.";
  if (!seasonal.has_trend_data) {
    return (
      <IntelCard
        title="Seasonal context"
        badge={<Badge tone="muted">{seasonal.season}</Badge>}
        headline={`No curated trend data for ${seasonal.season}.`}
        footnote={footnote}
      />
    );
  }

  const highDemand = Object.entries(seasonal.trending_categories)
    .filter(([, level]) => level === "high")
    .map(([category]) => category);
  const matchedColors = new Set(seasonal.matches_customer.colors);
  const matches = [
    ...seasonal.matches_customer.colors,
    ...seasonal.matches_customer.styles.map((style) => `${style} style`),
  ];
  const observed = seasonal.observed_demand;
  const topObserved = observed.top_categories[0];

  return (
    <IntelCard
      title="Seasonal context"
      badge={<Badge tone="accent">{seasonal.season}</Badge>}
      headline={`High seasonal demand for ${highDemand.join(" and ")}.`}
      footnote={footnote}
    >
      <div className="facts">
        <Fact label="Trending">{seasonal.trending_subcategories.join(", ")}</Fact>
        <Fact label="Colours">
          <span className="inline-colors">
            {seasonal.relevant_colors.map((color) => (
              <span
                key={color}
                className={`pill-color ${matchedColors.has(color) ? "color-match" : ""}`}
              >
                <Swatch color={color} />
                {color}
              </span>
            ))}
          </span>
        </Fact>
        <Fact label="Fits them">
          {matches.length ? matches.join(", ") : <span className="fact-sub">no overlap with preferences</span>}
        </Fact>
        <Fact label="Shoppable">
          {seasonal.in_season_catalogue.within_budget} in-season within budget{" "}
          <span className="fact-sub">{seasonal.in_season_catalogue.trending_within_budget} trending</span>
        </Fact>
        {topObserved && (
          <Fact label="All shoppers">
            {topObserved.category} is {topObserved.share_pct}% of browsing{" "}
            <span className="fact-sub">
              {observed.event_count} events, {observed.customer_count} customers
            </span>
          </Fact>
        )}
      </div>
    </IntelCard>
  );
}

export default function IntelligencePanel({ purchases, intent, seasonal }) {
  return (
    <section className="panel">
      <p className="eyebrow">Customer intelligence</p>
      <h2 className="panel-title">What the data says</h2>
      <p className="panel-sub">
        Computed deterministically from purchase history, browsing events and seasonal trend
        data &mdash; before any AI is involved. These are the signals the agent reasons over.
      </p>

      <div className="intel-grid">
        <PurchaseCard patterns={purchases} />
        <IntentCard intent={intent} />
        <SeasonCard seasonal={seasonal} />
      </div>
    </section>
  );
}
