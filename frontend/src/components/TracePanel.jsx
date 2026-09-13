import { useEffect, useState } from "react";

const REVEAL_MS = 480; // inside the 400-600ms window

const TOOL_LABELS = {
  get_customer_profile: "Read the profile",
  get_wardrobe: "Opened the wardrobe",
  get_browsing_history: "Checked browsing history",
  analyze_outfit_gaps: "Ran gap analysis",
  search_products: "Searched the catalogue",
  check_offer: "Checked for an offer",
};

function formatArgs(args) {
  const entries = Object.entries(args).filter(
    ([key, value]) => key !== "customer_id" && value !== null && value !== undefined
  );
  if (!entries.length) return null;
  return entries.map(([key, value]) => `${key}: ${value}`).join("  ·  ");
}

export default function TracePanel({ trace }) {
  const [shown, setShown] = useState(0);

  // The whole trace arrives in one response; the reveal is purely cosmetic,
  // so it's animated here rather than streamed from the backend.
  useEffect(() => {
    setShown(0);
    if (!trace.length) return undefined;

    const timers = trace.map((_, index) =>
      setTimeout(() => setShown(index + 1), index * REVEAL_MS)
    );
    return () => timers.forEach(clearTimeout);
  }, [trace]);

  const done = shown >= trace.length;

  return (
    <section className="panel">
      <p className="eyebrow">How it got there</p>
      <h2 className="panel-title">
        Agent trace
        <span className="trace-count">
          {shown} / {trace.length} steps
        </span>
      </h2>
      <p className="panel-sub">
        Every tool the agent chose to call, in the order it called them, with what each
        one actually returned.
      </p>

      <ol className="trace">
        {trace.slice(0, shown).map((step) => (
          <li key={step.step} className="trace-step">
            <span className="trace-num">{step.step}</span>
            <div className="trace-body">
              <div className="trace-head">
                <span className="trace-label">
                  {TOOL_LABELS[step.tool] || step.tool}
                </span>
                <code className="trace-tool">{step.tool}</code>
              </div>
              <p className="trace-summary">{step.summary}</p>
              {formatArgs(step.args) && (
                <p className="trace-args">{formatArgs(step.args)}</p>
              )}
            </div>
          </li>
        ))}
      </ol>

      {!done && (
        <p className="trace-thinking">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </p>
      )}
    </section>
  );
}
