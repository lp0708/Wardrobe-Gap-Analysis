import { useMemo, useState } from "react";

import { getPlatformRecommendations } from "../api";
import { TYPE_LABELS, capitalize, count } from "../platform/format";
import RecommendationRow from "../platform/RecommendationRow";
import {
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
  PageHeader,
  Segmented,
  useApi,
} from "../platform/ui";

const unique = (values) => [...new Set(values)].sort();

export default function RecommendationsPage() {
  const { data, error, loading } = useApi(() => getPlatformRecommendations(), []);
  const [customer, setCustomer] = useState("all");
  const [type, setType] = useState("all");
  const [season, setSeason] = useState("all");
  const [source, setSource] = useState("all");
  const [offersOnly, setOffersOnly] = useState(false);
  const [sort, setSort] = useState("score");

  const rows = useMemo(() => data?.rows || [], [data]);

  const visible = useMemo(() => {
    const filtered = rows.filter(
      (r) =>
        (customer === "all" || r.customer_id === customer) &&
        (type === "all" || r.types.includes(type)) &&
        (season === "all" || r.season === season) &&
        (source === "all" || r.source === source) &&
        (!offersOnly || r.offer)
    );
    return filtered.sort((a, b) =>
      sort === "score"
        ? b.score - a.score || a.customer_id.localeCompare(b.customer_id)
        : a.customer_id.localeCompare(b.customer_id) ||
          (a.source === b.source ? b.score - a.score : a.source === "agent" ? -1 : 1)
    );
  }, [rows, customer, type, season, source, offersOnly, sort]);

  return (
    <>
      <PageHeader
        eyebrow="Recommendation activity"
        title="Recommendations"
        description="Picks the agent selected in each customer's latest run, alongside the recommendation engine's other top-ranked products. Scores and signals come from the engine."
      />

      {loading && !data && <LoadingState label="Ranking products for every customer" />}
      {error && <ErrorState message={error} />}

      {data && (
        <div className="pf-stack">
          <div className="pf-kpi-grid pf-kpi-grid-4">
            <KpiCard label="Recommendations" value={count(rows.length)} hint={`Up to ${data.engine_picks_per_customer} engine picks per customer, plus agent picks`} />
            <KpiCard accent label="AI-selected" value={count(rows.filter((r) => r.source === "agent").length)} hint="Chosen in a saved agent run" />
            <KpiCard label="With an active offer" value={count(rows.filter((r) => r.offer).length)} />
            <KpiCard label="Customers covered" value={count(unique(rows.map((r) => r.customer_id)).length)} />
          </div>

          <section className="pf-card pf-card-flush">
            <div className="pf-toolbar pf-toolbar-wrap">
              <Segmented
                label="Source"
                value={source}
                onChange={setSource}
                options={[
                  { value: "all", label: "All", count: rows.length },
                  { value: "agent", label: "AI-selected", count: rows.filter((r) => r.source === "agent").length },
                  { value: "engine", label: "Engine-ranked", count: rows.filter((r) => r.source === "engine").length },
                ]}
              />

              <label className="pf-field">
                <span>Customer</span>
                <select className="pf-select" value={customer} onChange={(e) => setCustomer(e.target.value)}>
                  <option value="all">All customers</option>
                  {unique(rows.map((r) => r.customer_id)).map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </select>
              </label>

              <label className="pf-field">
                <span>Type</span>
                <select className="pf-select" value={type} onChange={(e) => setType(e.target.value)}>
                  <option value="all">All types</option>
                  {data.recommendation_types.map((t) => (
                    <option key={t} value={t}>
                      {TYPE_LABELS[t]}
                    </option>
                  ))}
                </select>
              </label>

              <label className="pf-field">
                <span>Product season</span>
                <select className="pf-select" value={season} onChange={(e) => setSeason(e.target.value)}>
                  <option value="all">All seasons</option>
                  {unique(rows.map((r) => r.season)).map((s) => (
                    <option key={s} value={s}>
                      {capitalize(s)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="pf-field">
                <span>Sort</span>
                <select className="pf-select" value={sort} onChange={(e) => setSort(e.target.value)}>
                  <option value="score">Highest score</option>
                  <option value="customer">By customer</option>
                </select>
              </label>

              <label className="pf-check">
                <input type="checkbox" checked={offersOnly} onChange={(e) => setOffersOnly(e.target.checked)} />
                With offer only
              </label>
            </div>

            <div className="pf-result-count">
              Showing {visible.length} of {rows.length}
            </div>

            {visible.length === 0 ? (
              <EmptyState title="No recommendations match these filters">Clear a filter to see more.</EmptyState>
            ) : (
              <div className="pf-rec-list pf-rec-list-flush">
                {visible.map((rec) => (
                  <RecommendationRow key={`${rec.customer_id}-${rec.source}-${rec.product_id}`} rec={rec} />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
