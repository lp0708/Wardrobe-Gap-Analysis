import { COLOR_SWATCHES, NEEDS_OUTLINE } from "../colors";

const TYPE_LABELS = {
  gap: "Wardrobe gap",
  intent: "Browsing intent",
  seasonal: "Seasonal",
  complementary: "Complementary",
};

const GROUP_LABELS = {
  gap: "Gap",
  intent: "Intent",
  seasonal: "Season",
  trend: "Trend",
  complementary: "Pairs",
  preference: "Preference",
  purchase: "Purchases",
  offer: "Offer",
  penalty: "Penalty",
};

const MAX_SIGNALS = 4;

function offerLabel(offer) {
  if (!offer) return null;
  if (offer.offer_type === "free_shipping") return "Free shipping";
  if (offer.discount_percentage) {
    const kind = offer.offer_type === "bundle_discount" ? "bundle" : "off";
    return `${offer.discount_percentage}% ${kind}`;
  }
  return offer.offer_type.replace(/_/g, " ");
}

function Signals({ signals }) {
  const shown = [
    ...signals.filter((s) => s.points > 0).slice(0, MAX_SIGNALS),
    ...signals.filter((s) => s.points < 0),
  ];
  return (
    <ul className="signal-list">
      {shown.map((signal) => (
        <li
          key={`${signal.group}-${signal.evidence}`}
          className={`signal ${signal.points < 0 ? "signal-negative" : ""}`}
        >
          <span className={`signal-group signal-group-${signal.group}`}>
            {GROUP_LABELS[signal.group] || signal.group}
          </span>
          <span className="signal-text">{signal.evidence}</span>
          <span className="signal-points">
            {signal.points > 0 ? `+${signal.points}` : signal.points}
          </span>
        </li>
      ))}
    </ul>
  );
}

function groundingNote(item) {
  if (item.selected_by === "engine_top_up") {
    return "Added by the recommendation engine so the list reaches three picks.";
  }
  if (item.explanation_source === "engine") {
    return "The agent's wording claimed something the data didn't support, so this explanation is built from the evidence instead.";
  }
  return null;
}

function RecommendationCard({ item }) {
  const badge = offerLabel(item.offer);
  const note = groundingNote(item);

  return (
    <article className="rec-card">
      <div className="rec-top">
        <span
          className={`swatch ${NEEDS_OUTLINE.has(item.color) ? "swatch-outline" : ""}`}
          style={{ background: COLOR_SWATCHES[item.color] || "#cfc6bd" }}
          title={item.color}
        />
        <div className="rec-heading">
          <h3 className="rec-name">{item.name}</h3>
          <p className="rec-meta">
            {item.color} &middot; {item.category} &middot; {item.season}
          </p>
        </div>
        <span className="rec-score" title="Recommendation engine score">
          {item.score}
          <span className="rec-score-label">score</span>
        </span>
      </div>

      <div className="type-row">
        {item.types.map((type) => (
          <span
            key={type}
            className={`type-badge ${type === item.primary_type ? "type-primary" : ""}`}
          >
            {TYPE_LABELS[type] || type}
          </span>
        ))}
      </div>

      <p className="rec-explanation">{item.explanation}</p>
      {note && <p className="grounding-note">{note}</p>}

      <p className="rec-section-label">Key signals</p>
      <Signals signals={item.signals} />

      <div className="rec-foot">
        <span className="rec-price">&#8377;{item.price.toLocaleString("en-IN")}</span>
        {badge && (
          <span className="rec-offer" title={`Valid until ${item.offer.valid_until}`}>
            &#127991;&#65039; {badge}
          </span>
        )}
        <span className="rec-id">{item.product_id}</span>
      </div>
    </article>
  );
}

export default function RecommendationsGrid({ result }) {
  const dropped = result.dropped_recommendations?.length || 0;

  return (
    <section className="panel">
      <p className="eyebrow">AI recommendations</p>
      <h2 className="panel-title">Recommended for {result.customer_id}</h2>
      <p className="panel-sub">
        Product facts, offers, recommendation types and signal scores come from the catalogue
        and the recommendation engine. Explanations are written by the agent and checked
        against that evidence.
      </p>

      {result.summary && (
        <div className="brief">
          <span className="brief-label">
            {result.summary_source === "agent" ? "Agent brief" : "Summary"}
          </span>
          <p className="brief-text">{result.summary}</p>
          <p className="brief-meta">
            {result.model} &middot; {result.trace.length} tool calls
            {dropped
              ? ` · ${dropped} ${dropped === 1 ? "pick" : "picks"} removed by grounding rules`
              : ""}
          </p>
        </div>
      )}

      <div className="rec-grid">
        {result.recommendations.map((item) => (
          <RecommendationCard key={item.product_id} item={item} />
        ))}
      </div>
    </section>
  );
}
