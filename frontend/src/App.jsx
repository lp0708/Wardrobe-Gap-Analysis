import { useEffect, useState } from "react";

import "./App.css";
import { getCustomer, listCustomers, recommend } from "./api";
import CustomerSelector from "./components/CustomerSelector";
import GapsPanel from "./components/GapsPanel";
import Header from "./components/Header";
import RecommendationsGrid from "./components/RecommendationsGrid";
import TracePanel from "./components/TracePanel";

export default function App() {
  const [customers, setCustomers] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listCustomers()
      .then(setCustomers)
      .catch((err) => setError(err.message));
  }, []);

  function handleSelect(id) {
    setSelectedId(id);
    setResult(null);
    setError("");
    setProfile(null);
    if (!id) return;

    setProfileLoading(true);
    getCustomer(id)
      .then(setProfile)
      .catch((err) => setError(err.message))
      .finally(() => setProfileLoading(false));
  }

  function handleRun() {
    setRunning(true);
    setError("");
    setResult(null);
    recommend(selectedId)
      .then(setResult)
      .catch((err) => setError(err.message))
      .finally(() => setRunning(false));
  }

  return (
    <div className="page">
      <Header />

      <CustomerSelector
        customers={customers}
        selectedId={selectedId}
        onSelect={handleSelect}
        profile={profile}
        loading={profileLoading}
      />

      {profile && (
        <section className="panel run-panel">
          <div>
            <p className="eyebrow">Step 2</p>
            <h2 className="panel-title">Run the agent</h2>
            <p className="panel-sub run-sub">
              The agent makes several round trips to the model and executes each tool
              call in between &mdash; this takes a few seconds.
            </p>
          </div>
          <button className="run-button" onClick={handleRun} disabled={running}>
            {running ? (
              <>
                <span className="spinner" />
                Thinking&hellip;
              </>
            ) : (
              <>Recommend for {selectedId}</>
            )}
          </button>
        </section>
      )}

      {error && (
        <div className="error">
          <strong>Something went wrong.</strong>
          <p>{error}</p>
        </div>
      )}

      {running && (
        <section className="panel skeleton-panel">
          <p className="eyebrow">Working</p>
          <h2 className="panel-title">Reading the closet, hunting for gaps&hellip;</h2>
          <div className="skeleton-rows">
            <span className="skeleton" />
            <span className="skeleton" />
            <span className="skeleton" />
          </div>
        </section>
      )}

      {result && (
        <>
          <GapsPanel gaps={result.gaps} />
          <TracePanel trace={result.trace} />
          <RecommendationsGrid recommendations={result.recommendations} />
        </>
      )}

      <footer className="site-footer">
        Gap analysis is deterministic Python &middot; recommendations are chosen by a
        Gemini agent with manual function calling
      </footer>
    </div>
  );
}
