import { Link } from "react-router-dom";

import { getOverview } from "../api";
import { EVENT_LABELS, INTENT_LABELS, TYPE_LABELS, count, formatDate, formatDateTime, rupees } from "../platform/format";
import {
  BarList,
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
  PageHeader,
  Stat,
  useApi,
} from "../platform/ui";

const EVENT_ORDER = ["abandoned_cart", "added_to_cart", "saved", "viewed"];

export default function DashboardPage() {
  const { data, error, loading } = useApi(getOverview, []);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="AI-powered retail intelligence for personalised customer recommendations."
        actions={
          <Link className="pf-button pf-button-primary" to="/demo">
            Open live AI demo
          </Link>
        }
      />

      {loading && !data && <LoadingState label="Loading your customer base" />}
      {error && <ErrorState message={error} />}
      {data && <Dashboard data={data} />}
    </>
  );
}

function Dashboard({ data }) {
  const { kpis, customer_activity: activity, opportunity_overview: opportunities } = data;

  return (
    <div className="pf-stack">
      <div className="pf-kpi-grid">
        <KpiCard label="Total customers" value={count(kpis.total_customers)} hint="In the customer dataset" />
        <KpiCard
          accent
          label="Customers with opportunities"
          value={count(kpis.customers_with_opportunities)}
          hint={`${kpis.customers_with_gaps} with wardrobe gaps, the rest with active browsing intent`}
        />
        <KpiCard label="Products in catalogue" value={count(kpis.products_in_catalogue)} hint="Ranked for every customer" />
        <KpiCard
          label="Active offers"
          value={count(kpis.active_offers)}
          hint={`of ${kpis.total_offers} offers, as of ${formatDate(data.as_of)}`}
        />
        <KpiCard
          label="Customers analysed by AI"
          value={`${kpis.customers_with_ai_runs} / ${kpis.total_customers}`}
          hint="Have a saved agent run"
        />
        <KpiCard
          label="AI recommendations"
          value={count(kpis.ai_recommendations_saved)}
          hint="Picked by the agent across saved runs"
        />
      </div>

      <div className="pf-grid-2">
        <Card
          title="Opportunity overview"
          subtitle="Where the AI can help: reported wardrobe gaps and browsing intent strength."
          actions={
            <Link className="pf-link" to="/analytics">
              Analytics &rarr;
            </Link>
          }
        >
          <p className="pf-section-label">Customers missing each category</p>
          <BarList
            items={opportunities.gap_categories.map((gap) => ({
              key: gap.label,
              label: gap.label,
              sub: gap.customer_ids.join(", "),
              value: gap.customer_ids.length,
            }))}
            formatValue={(v) => `${v} ${v === 1 ? "customer" : "customers"}`}
            emptyText="No reported category gaps"
          />

          {opportunities.occasion_gaps.length > 0 && (
            <>
              <p className="pf-section-label">Occasion gaps</p>
              <BarList
                items={opportunities.occasion_gaps.map((gap) => ({
                  key: gap.label,
                  label: gap.label,
                  sub: gap.customer_ids.join(", "),
                  value: gap.customer_ids.length,
                }))}
                formatValue={(v) => `${v} ${v === 1 ? "customer" : "customers"}`}
              />
            </>
          )}

          <div className="pf-inline-stats">
            {["strong", "moderate", "insufficient"].map((strength) => (
              <Stat
                key={strength}
                label={INTENT_LABELS[strength]}
                value={opportunities.intent_strength[strength] || 0}
              />
            ))}
          </div>
        </Card>

        <Card title="Customer activity" subtitle="Purchases and browsing recorded across the customer base.">
          <div className="pf-inline-stats">
            <Stat label="Purchases" value={count(activity.purchases)} />
            <Stat label="Purchase value" value={rupees(activity.purchase_value)} />
            <Stat label="Browsing events" value={count(activity.browsing_events)} />
          </div>

          <p className="pf-section-label">Browsing events by type</p>
          <BarList
            items={EVENT_ORDER.filter((type) => activity.event_types[type]).map((type) => ({
              key: type,
              label: EVENT_LABELS[type],
              value: activity.event_types[type],
            }))}
            emphasis={["abandoned_cart", "added_to_cart", "saved"]}
          />
          {activity.browsing_window && (
            <p className="pf-footnote">
              Cart and save events are highlighted as the strongest buying signals. Browsing recorded{" "}
              {formatDate(activity.browsing_window[0])} &ndash; {formatDate(activity.browsing_window[1])}.
            </p>
          )}
        </Card>
      </div>

      <Card
        title="Recommendation activity"
        subtitle="Latest saved agent run for each customer."
        actions={
          <Link className="pf-link" to="/recommendations">
            All recommendations &rarr;
          </Link>
        }
      >
        {data.recent_runs.length === 0 ? (
          <EmptyState
            title="No agent runs yet"
            action={
              <Link className="pf-button" to="/demo">
                Run the agent
              </Link>
            }
          >
            Generate recommendations for a customer in the demo and they&rsquo;ll appear here.
          </EmptyState>
        ) : (
          <div className="pf-table-wrap">
            <table className="pf-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Top pick</th>
                  <th className="pf-num">Picks</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.map((run) => (
                  <tr key={run.customer_id}>
                    <td>
                      <Link className="pf-id-link" to={`/customers/${run.customer_id}`}>
                        {run.customer_id}
                      </Link>
                    </td>
                    <td>
                      {run.top_pick ? (
                        <>
                          {run.top_pick.name}
                          <span className="pf-cell-sub">{TYPE_LABELS[run.top_pick.primary_type]}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="pf-num">{run.recommendation_count}</td>
                    <td>
                      {formatDateTime(run.saved_at)}
                      <span className="pf-cell-sub">{run.tool_calls} tool calls</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <section className="pf-demo-cta">
        <div>
          <p className="pf-eyebrow pf-eyebrow-light">AI workflow</p>
          <h2 className="pf-demo-cta-title">See how a recommendation is made</h2>
          <p className="pf-demo-cta-text">
            Pick a customer, review their intelligence, and watch the Gemini agent call tools, rank the
            catalogue and explain every pick &mdash; with each claim checked against the data.
          </p>
        </div>
        <Link className="pf-button pf-button-light" to="/demo">
          Open the demo &rarr;
        </Link>
      </section>
    </div>
  );
}
