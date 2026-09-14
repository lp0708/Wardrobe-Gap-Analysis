import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getOverview } from "../api";
import { capitalize, formatDate, rupees } from "../platform/format";
import {
  ErrorState,
  IntentBadge,
  LoadingState,
  OpportunityChips,
  PageHeader,
  Segmented,
  useApi,
  EmptyState,
} from "../platform/ui";

const FILTERS = [
  { value: "all", label: "All", test: () => true },
  { value: "gaps", label: "With gaps", test: (c) => c.opportunities.length > 0 },
  { value: "intent", label: "Active intent", test: (c) => c.intent_strength !== "insufficient" },
  { value: "no_gaps", label: "No gaps", test: (c) => c.opportunities.length === 0 },
  { value: "not_run", label: "Not yet run", test: (c) => !c.latest_run },
];

export default function CustomersPage() {
  const { data, error, loading } = useApi(getOverview, []);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  const customers = useMemo(() => data?.customers || [], [data]);
  const visible = useMemo(() => {
    const test = FILTERS.find((f) => f.value === filter).test;
    const q = query.trim().toLowerCase();
    return customers.filter(
      (c) =>
        test(c) &&
        (!q ||
          c.customer_id.toLowerCase().includes(q) ||
          c.preferred_styles.some((s) => s.includes(q)) ||
          c.preferred_colors.some((s) => s.includes(q)))
    );
  }, [customers, filter, query]);

  return (
    <>
      <PageHeader
        eyebrow="Customer base"
        title="Customers"
        description="Every customer's purchase and browsing activity, with the opportunities the intelligence layer found."
      />

      {loading && !data && <LoadingState label="Loading customers" />}
      {error && <ErrorState message={error} />}

      {data && (
        <section className="pf-card pf-card-flush">
          <div className="pf-toolbar">
            <Segmented
              label="Filter customers"
              value={filter}
              onChange={setFilter}
              options={FILTERS.map((f) => ({
                value: f.value,
                label: f.label,
                count: customers.filter(f.test).length,
              }))}
            />
            <input
              className="pf-search"
              type="search"
              placeholder="Search ID, style or colour"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search customers"
            />
          </div>

          {visible.length === 0 ? (
            <EmptyState title="No customers match">Try a different filter or search.</EmptyState>
          ) : (
            <div className="pf-table-wrap">
              <table className="pf-table pf-table-interactive">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th className="pf-num">Budget</th>
                    <th>Purchases</th>
                    <th>Browsing</th>
                    <th>Intent</th>
                    <th>Opportunities</th>
                    <th>Latest AI run</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c) => (
                    <tr key={c.customer_id} onClick={() => navigate(`/customers/${c.customer_id}`)}>
                      <td>
                        <span className="pf-id">{c.customer_id}</span>
                        <span className="pf-cell-sub">
                          {c.preferred_styles.map(capitalize).join(" · ")}
                        </span>
                      </td>
                      <td className="pf-num">{rupees(c.budget)}</td>
                      <td>
                        {c.purchase_count} {c.purchase_count === 1 ? "purchase" : "purchases"}
                        <span className="pf-cell-sub">{rupees(c.total_spend)} total</span>
                      </td>
                      <td>
                        {c.browsing_event_count} {c.browsing_event_count === 1 ? "event" : "events"}
                        <span className="pf-cell-sub">
                          {c.cart_or_save_events} cart/save &middot; last {formatDate(c.last_browsed)}
                        </span>
                      </td>
                      <td>
                        <IntentBadge strength={c.intent_strength} />
                      </td>
                      <td>
                        <OpportunityChips items={c.opportunities} />
                      </td>
                      <td>
                        {c.latest_run ? (
                          <>
                            {formatDate(c.latest_run.saved_at)}
                            <span className="pf-cell-sub">{c.latest_run.recommendation_count} picks</span>
                          </>
                        ) : (
                          <span className="pf-muted">Not run</span>
                        )}
                      </td>
                      <td className="pf-actions-cell">
                        <Link
                          className="pf-button pf-button-small"
                          to={`/customers/${c.customer_id}`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          View customer
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
