function GapCard({ kind, title, detail, priority, hasSignal, supporting }) {
  return (
    <li className={`gap-card ${priority === "high" ? "gap-high" : "gap-medium"}`}>
      <span className="gap-kind">{kind}</span>
      <span className="gap-title">{title}</span>
      {detail && <span className="gap-detail">{detail}</span>}
      <span className="gap-priority">
        {priority} priority
        {hasSignal && supporting?.length ? (
          <span className="gap-signal">
            {" "}
            &middot; {supporting.length} browsed{" "}
            {supporting.length === 1 ? "item" : "items"}
          </span>
        ) : null}
      </span>
    </li>
  );
}

export default function GapsPanel({ gaps }) {
  const missing = gaps.missing_categories || [];
  const imbalances = gaps.imbalances || [];
  const occasions = gaps.occasion_gaps || [];
  const total = missing.length + imbalances.length + occasions.length;

  return (
    <section className="panel">
      <p className="eyebrow">What&rsquo;s missing</p>
      <h2 className="panel-title">Wardrobe gaps</h2>
      <p className="panel-sub">
        Found deterministically from the closet and cross-referenced against browsing
        history. A gap the shopper has already been looking at is marked high priority.
      </p>

      {total === 0 && !gaps.color_gap ? (
        <p className="empty">
          No gaps found &mdash; this wardrobe already covers every category, occasion and
          preferred colour.
        </p>
      ) : (
        <ul className="gap-row">
          {missing.map((gap) => (
            <GapCard
              key={`m-${gap.category}`}
              kind="Missing"
              title={gap.category}
              detail="owns none"
              priority={gap.priority}
              hasSignal={gap.has_browsing_signal}
              supporting={gap.supporting_product_ids}
            />
          ))}

          {imbalances.map((gap) => (
            <GapCard
              key={`i-${gap.oversupplied}-${gap.undersupplied}`}
              kind="Imbalance"
              title={gap.undersupplied}
              detail={`${gap.oversupplied_count} ${gap.oversupplied} vs ${gap.undersupplied_count}`}
              priority={gap.priority}
              hasSignal={gap.has_browsing_signal}
              supporting={gap.supporting_product_ids}
            />
          ))}

          {occasions.map((gap) => (
            <GapCard
              key={`o-${gap.occasion}`}
              kind="No outfit for"
              title={gap.occasion}
              detail="nothing suitable"
              priority={gap.priority}
              hasSignal={gap.has_browsing_signal}
              supporting={gap.supporting_product_ids}
            />
          ))}

          {gaps.color_gap && (
            <GapCard
              kind="Colour"
              title="preferred palette"
              detail="owns nothing in it"
              priority="medium"
              hasSignal={false}
            />
          )}
        </ul>
      )}
    </section>
  );
}
