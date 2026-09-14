import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { COLOR_SWATCHES, NEEDS_OUTLINE } from "../colors";
import { INTENT_LABELS, TYPE_LABELS, capitalize } from "./format";

/* Data loading ----------------------------------------------------------- */

export function useApi(loader, deps) {
  const [state, setState] = useState({ data: null, error: "", loading: true });

  useEffect(() => {
    let live = true;
    setState((previous) => ({ ...previous, loading: true, error: "" }));
    loader()
      .then((data) => live && setState({ data, error: "", loading: false }))
      .catch((err) => live && setState({ data: null, error: err.message, loading: false }));
    return () => {
      live = false;
    };
    // The caller passes the dependencies that should trigger a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}

/* Layout ---------------------------------------------------------------- */

export function PageHeader({ eyebrow, title, description, actions, back }) {
  return (
    <header className="pf-page-header">
      {back && (
        <Link className="pf-back" to={back.to}>
          &larr; {back.label}
        </Link>
      )}
      <div className="pf-page-header-row">
        <div className="pf-page-heading">
          {eyebrow && <p className="pf-eyebrow">{eyebrow}</p>}
          <h1 className="pf-page-title">{title}</h1>
          {description && <p className="pf-page-description">{description}</p>}
        </div>
        {actions && <div className="pf-page-actions">{actions}</div>}
      </div>
    </header>
  );
}

export function Card({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`pf-card ${className}`}>
      {(title || actions) && (
        <div className="pf-card-head">
          <div>
            {title && <h2 className="pf-card-title">{title}</h2>}
            {subtitle && <p className="pf-card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="pf-card-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function KpiCard({ label, value, hint, accent }) {
  return (
    <div className={`pf-kpi ${accent ? "pf-kpi-accent" : ""}`}>
      <span className="pf-kpi-label">{label}</span>
      <span className="pf-kpi-value">{value}</span>
      {hint && <span className="pf-kpi-hint">{hint}</span>}
    </div>
  );
}

export function Stat({ label, value, hint }) {
  return (
    <div className="pf-stat">
      <span className="pf-stat-value">{value}</span>
      <span className="pf-stat-label">{label}</span>
      {hint && <span className="pf-stat-hint">{hint}</span>}
    </div>
  );
}

/* Badges ---------------------------------------------------------------- */

export function Badge({ tone = "neutral", children, title }) {
  return (
    <span className={`pf-badge pf-badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function IntentBadge({ strength }) {
  const tone = strength === "strong" ? "accent" : strength === "moderate" ? "soft" : "muted";
  return <Badge tone={tone}>{INTENT_LABELS[strength] || capitalize(strength)}</Badge>;
}

export function TypeBadges({ types, primary }) {
  return (
    <span className="pf-badge-row">
      {types.map((type) => (
        <Badge key={type} tone={type === primary ? "accent" : "neutral"}>
          {TYPE_LABELS[type] || type}
        </Badge>
      ))}
    </span>
  );
}

export function SourceBadge({ source }) {
  return source === "agent" ? (
    <Badge tone="soft" title="Chosen by the Gemini agent in this customer's latest run">
      AI-selected
    </Badge>
  ) : (
    <Badge tone="outline" title="Top-ranked by the recommendation engine; not picked in a saved agent run">
      Engine-ranked
    </Badge>
  );
}

export function OpportunityChips({ items, max = 3 }) {
  if (!items?.length) return <span className="pf-muted">No gaps</span>;
  const shown = items.slice(0, max);
  return (
    <span className="pf-badge-row">
      {shown.map((item) => (
        <Badge
          key={`${item.kind}-${item.label}`}
          tone={item.priority === "high" ? "accent" : "neutral"}
          title={`${item.priority} priority`}
        >
          {item.kind === "occasion" ? `${item.label} occasion` : item.label}
        </Badge>
      ))}
      {items.length > max && <Badge tone="muted">+{items.length - max}</Badge>}
    </span>
  );
}

export function Swatch({ color, size = 14 }) {
  return (
    <span
      className={`pf-swatch ${NEEDS_OUTLINE.has(color) ? "pf-swatch-outline" : ""}`}
      style={{ width: size, height: size, background: COLOR_SWATCHES[color] || "#cfc6bd" }}
      title={color}
    />
  );
}

/* Controls -------------------------------------------------------------- */

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className="pf-segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          className={`pf-segment ${value === option.value ? "pf-segment-active" : ""}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && <span className="pf-segment-count">{option.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="pf-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={value === tab.value}
          className={`pf-tab ${value === tab.value ? "pf-tab-active" : ""}`}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
          {tab.count !== undefined && <span className="pf-tab-count">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* Charts ---------------------------------------------------------------- */

/*
 * Horizontal bar list for comparing magnitude across nominal categories.
 * One series, one hue; `emphasis` highlights the items that matter and greys
 * the rest. Every value is printed, so nothing is readable only by hover.
 */
export function BarList({ items, formatValue = (v) => v, emphasis, emptyText = "No data" }) {
  if (!items?.length) return <p className="pf-muted">{emptyText}</p>;
  const max = Math.max(...items.map((item) => item.value), 1);

  return (
    <ul className="pf-bars">
      {items.map((item) => {
        const muted = emphasis && !emphasis.includes(item.key);
        return (
          <li key={item.key} className="pf-bar-row" title={`${item.label}: ${formatValue(item.value)}`}>
            <span className="pf-bar-label">
              {item.label}
              {item.sub && <span className="pf-bar-sub">{item.sub}</span>}
            </span>
            <span className="pf-bar-track">
              <span
                className={`pf-bar-fill ${muted ? "pf-bar-fill-muted" : ""}`}
                style={{ width: `${Math.max((item.value / max) * 100, item.value ? 2 : 0)}%` }}
              />
            </span>
            <span className="pf-bar-value">{formatValue(item.value)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/* States ---------------------------------------------------------------- */

export function LoadingState({ label = "Loading" }) {
  return (
    <div className="pf-state" aria-busy="true">
      <span className="pf-loader" />
      <span>{label}&hellip;</span>
    </div>
  );
}

export function ErrorState({ message }) {
  return (
    <div className="pf-state pf-state-error" role="alert">
      <strong>Couldn&rsquo;t load this page.</strong>
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="pf-empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
