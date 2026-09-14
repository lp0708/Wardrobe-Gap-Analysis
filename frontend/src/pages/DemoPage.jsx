import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import "../App.css";
import { getIntelligence, listCustomers, recommend } from "../api";
import CustomerOverview from "../components/CustomerOverview";
import CustomerRoster from "../components/CustomerRoster";
import GapsPanel from "../components/GapsPanel";
import Header from "../components/Header";
import IntelligencePanel from "../components/IntelligencePanel";
import RecommendationsGrid from "../components/RecommendationsGrid";
import TracePanel from "../components/TracePanel";

/*
 * The original single-page demo, moved here unchanged so it lives at /demo.
 * The only addition: /demo?customer=C004 preselects that customer, so other
 * pages can deep-link into the demo. Without the parameter it behaves exactly
 * as before.
 */
export default function DemoPage() {
  const [customers, setCustomers] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [intel, setIntel] = useState(null);
  const [intelLoading, setIntelLoading] = useState(false);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const [searchParams] = useSearchParams();

  // The customer the latest request was for, so a slow response for a
  // previously selected customer can't overwrite the current one.
  const latestId = useRef("");

  useEffect(() => {
    listCustomers()
      .then((list) => {
        setCustomers(list);
        const preselect = searchParams.get("customer");
        if (preselect && list.some((c) => c.customer_id === preselect)) {
          handleSelect(preselect);
        }
      })
      .catch((err) => setError(err.message));
    // Runs once on mount, like the original page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSelect(id) {
    latestId.current = id;
    setSelectedId(id);
    setIntel(null);
    setResult(null);
    setError("");
    setIntelLoading(true);

    getIntelligence(id)
      .then((data) => latestId.current === id && setIntel(data))
      .catch((err) => latestId.current === id && setError(err.message))
      .finally(() => latestId.current === id && setIntelLoading(false));
  }

  function handleRun() {
    const id = selectedId;
    setRunning(true);
    setError("");
    setResult(null);

    recommend(id)
      .then((data) => latestId.current === id && setResult(data))
      .catch((err) => latestId.current === id && setError(err.message))
      .finally(() => setRunning(false));
  }

  return (
    <div className="page">
      <Header />

      <CustomerRoster
        customers={customers}
        selectedId={selectedId}
        onSelect={handleSelect}
        disabled={running}
      />

      {intelLoading && (
        <section className="panel">
          <p className="hint">Analysing {selectedId}&hellip;</p>
        </section>
      )}

      {intel && (
        <>
          <CustomerOverview profile={intel.profile} />
          <IntelligencePanel
            purchases={intel.purchase_patterns}
            intent={intel.browsing_intent}
            seasonal={intel.seasonal_context}
          />
          <GapsPanel gaps={intel.gaps} />

          <section className="panel run-panel">
            <div>
              <p className="eyebrow">Step 2</p>
              <h2 className="panel-title">Generate recommendations</h2>
              <p className="panel-sub run-sub">
                The agent decides which tools to call, ranks the catalogue with the
                recommendation engine, picks 3&ndash;5 products and explains each one. This
                takes a few seconds.
              </p>
            </div>
            <button className="run-button" onClick={handleRun} disabled={running}>
              {running ? (
                <>
                  <span className="spinner" />
                  Agent working&hellip;
                </>
              ) : (
                <>Recommend for {selectedId}</>
              )}
            </button>
          </section>
        </>
      )}

      {error && (
        <div className="error">
          <strong>Something went wrong.</strong>
          <p>{error}</p>
        </div>
      )}

      {running && (
        <section className="panel">
          <p className="eyebrow">Working</p>
          <h2 className="panel-title">
            Reviewing signals and ranking the catalogue&hellip;
          </h2>
          <div className="skeleton-rows">
            <span className="skeleton" />
            <span className="skeleton" />
            <span className="skeleton" />
          </div>
        </section>
      )}

      {result && (
        <>
          <RecommendationsGrid result={result} />
          <TracePanel trace={result.trace} />
        </>
      )}

      <footer className="site-footer">
        Customer intelligence and ranking are deterministic Python &middot; a Gemini agent
        orchestrates the tools, chooses the picks and writes the explanations &middot;
        seasonal trends are curated demo data
      </footer>
    </div>
  );
}
