import { COLOR_SWATCHES, NEEDS_OUTLINE } from "../colors";

function offerLabel(offer) {
  if (!offer) return null;
  if (offer.offer_type === "free_shipping") return "Free shipping";
  if (offer.discount_percentage) {
    const kind = offer.offer_type === "bundle_discount" ? "bundle" : "off";
    return `${offer.discount_percentage}% ${kind}`;
  }
  return offer.offer_type.replace(/_/g, " ");
}

export default function RecommendationsGrid({ recommendations }) {
  return (
    <section className="panel">
      <p className="eyebrow">The picks</p>
      <h2 className="panel-title">Recommendations</h2>
      <p className="panel-sub">
        Names, prices and offers are read straight from the catalogue &mdash; only the
        reasoning is written by the model.
      </p>

      <div className="rec-grid">
        {recommendations.map((item) => {
          const swatch = COLOR_SWATCHES[item.color] || "#cfc6bd";
          const badge = offerLabel(item.offer);

          return (
            <article key={item.product_id} className="rec-card">
              <div className="rec-top">
                <span
                  className={`swatch ${NEEDS_OUTLINE.has(item.color) ? "swatch-outline" : ""}`}
                  style={{ background: swatch }}
                  title={item.color}
                />
                <div className="rec-heading">
                  <h3 className="rec-name">{item.name}</h3>
                  <p className="rec-meta">
                    {item.color} &middot; {item.category}
                    {item.store ? ` · ${item.store}` : ""}
                  </p>
                </div>
              </div>

              <p className="rec-explanation">{item.explanation}</p>

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
        })}
      </div>
    </section>
  );
}
