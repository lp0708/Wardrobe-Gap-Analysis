import { COLOR_SWATCHES } from "../colors";

function Pill({ label, children }) {
  return (
    <div className="pill">
      <span className="pill-label">{label}</span>
      <span className="pill-value">{children}</span>
    </div>
  );
}

function ColorPill({ label, colors, muted }) {
  if (!colors?.length) return null;
  return (
    <div className={muted ? "pill pill-muted" : "pill"}>
      <span className="pill-label">{label}</span>
      <span className="pill-value pill-colors">
        {colors.map((color) => (
          <span key={color} className="pill-color">
            <span
              className="swatch swatch-sm"
              style={{ background: COLOR_SWATCHES[color] || "#cfc6bd" }}
            />
            {color}
          </span>
        ))}
      </span>
    </div>
  );
}

export default function CustomerSelector({
  customers,
  selectedId,
  onSelect,
  profile,
  loading,
}) {
  return (
    <section className="panel">
      <p className="eyebrow">Step 1</p>
      <h2 className="panel-title">Choose a shopper</h2>
      <p className="panel-sub">
        Eight profiles, each with their own closet, budget and browsing history.
      </p>

      <select
        className="select"
        value={selectedId}
        onChange={(event) => onSelect(event.target.value)}
      >
        <option value="">Select a customer&hellip;</option>
        {customers.map((customer) => (
          <option key={customer.customer_id} value={customer.customer_id}>
            {customer.customer_id} &mdash; {customer.preferred_styles.join(", ")} &middot;{" "}
            &#8377;{customer.budget} budget
          </option>
        ))}
      </select>

      {loading && <p className="hint">Loading profile&hellip;</p>}

      {profile && !loading && (
        <div className="pills">
          <Pill label="Styles">{profile.preferred_styles.join(", ")}</Pill>
          <ColorPill label="Loves" colors={profile.preferred_colors} />
          <ColorPill label="Avoids" colors={profile.avoided_colors} muted />
          <Pill label="Budget">&#8377;{profile.budget}</Pill>
          <Pill label="Dresses for">{profile.preferred_occasions.join(", ")}</Pill>
          <Pill label="Season">{profile.current_season}</Pill>
        </div>
      )}
    </section>
  );
}
