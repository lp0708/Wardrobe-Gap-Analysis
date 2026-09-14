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

export default function CustomerOverview({ profile }) {
  return (
    <section className="panel">
      <p className="eyebrow">Customer profile</p>
      <h2 className="panel-title">{profile.customer_id}</h2>
      <p className="panel-sub">Stated preferences and budget from the customer record.</p>

      <div className="pills">
        <Pill label="Styles">{profile.preferred_styles.join(", ")}</Pill>
        <ColorPill label="Likes" colors={profile.preferred_colors} />
        <ColorPill label="Avoids" colors={profile.avoided_colors} muted />
        <Pill label="Budget">&#8377;{profile.budget.toLocaleString("en-IN")} per item</Pill>
        <Pill label="Occasions">{profile.preferred_occasions.join(", ")}</Pill>
        <Pill label="Season">{profile.current_season}</Pill>
      </div>
    </section>
  );
}
