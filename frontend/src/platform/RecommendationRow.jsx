import { useState } from "react";
import { Link } from "react-router-dom";

import { SIGNAL_LABELS, capitalize, offerLabel, rupees } from "./format";
import { Badge, SourceBadge, Swatch, TypeBadges } from "./ui";

export default function RecommendationRow({ rec, showCustomer = true }) {
  const [expanded, setExpanded] = useState(false);
  const offer = offerLabel(rec.offer);

  return (
    <article className="pf-rec">
      <div className="pf-rec-main">
        <div className="pf-rec-product">
          <Swatch color={rec.color} size={28} />
          <div className="pf-rec-product-text">
            <span className="pf-rec-name">{rec.name}</span>
            <span className="pf-rec-meta">
              {capitalize(rec.color)} &middot; {rec.category} &middot; {rec.season} &middot;{" "}
              {rec.product_id}
            </span>
          </div>
        </div>

        {showCustomer && (
          <Link className="pf-rec-customer" to={`/customers/${rec.customer_id}`}>
            {rec.customer_id}
          </Link>
        )}

        <div className="pf-rec-types">
          <TypeBadges types={rec.types} primary={rec.primary_type} />
        </div>

        <div className="pf-rec-figures">
          <span className="pf-rec-price">{rupees(rec.price)}</span>
          {offer ? (
            <Badge tone="accent" title={`Valid until ${rec.offer.valid_until}`}>
              {offer}
            </Badge>
          ) : (
            <span className="pf-muted pf-small">No offer</span>
          )}
        </div>

        <div className="pf-rec-score" title="Recommendation engine score">
          <span className="pf-rec-score-value">{rec.score}</span>
          <span className="pf-rec-score-label">score</span>
        </div>
      </div>

      <div className="pf-rec-detail">
        <ul className="pf-signal-chips">
          {rec.key_signals.map((signal) => (
            <li key={signal.evidence} className="pf-signal-chip">
              <span className="pf-signal-chip-group">{SIGNAL_LABELS[signal.group] || signal.group}</span>
              {signal.evidence}
              <span className="pf-signal-chip-points">+{signal.points}</span>
            </li>
          ))}
        </ul>

        <div className="pf-rec-explanation-row">
          <SourceBadge source={rec.source} />
          <p className={`pf-rec-explanation ${expanded ? "" : "pf-clamp"}`}>{rec.explanation}</p>
          <button type="button" className="pf-link-button" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Less" : "More"}
          </button>
        </div>
      </div>
    </article>
  );
}
