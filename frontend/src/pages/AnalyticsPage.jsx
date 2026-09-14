import { getAnalytics } from "../api";
import { EVENT_LABELS, INTENT_LABELS, TYPE_LABELS, capitalize, count, humanize, rupees } from "../platform/format";
import { BarList, Card, ErrorState, LoadingState, PageHeader, Stat, useApi } from "../platform/ui";

const EVENT_ORDER = ["abandoned_cart", "added_to_cart", "saved", "viewed"];
const pluralCustomers = (v) => `${v} ${v === 1 ? "customer" : "customers"}`;

export default function AnalyticsPage() {
  const { data, error, loading } = useApi(getAnalytics, []);

  return (
    <>
      <PageHeader
        eyebrow="Insight"
        title="Analytics"
        description="How customer activity turns into retail opportunity. Every figure is computed from the customer, product, browsing and offer data."
      />

      {loading && !data && <LoadingState label="Computing analytics" />}
      {error && <ErrorState message={error} />}
      {data && <Analytics data={data} />}
    </>
  );
}

function Analytics({ data }) {
  const { purchases, browsing, gaps, intent, recommendations, offers, seasonal } = data;
  const currentSeasons = seasonal.seasons.map((s) => s.season);

  return (
    <div className="pf-grid-2">
      <Card title="What do customers buy?" subtitle={`${count(purchases.total)} purchases by category.`}>
        <BarList
          items={purchases.by_category.map((row) => ({
            key: row.category,
            label: capitalize(row.category),
            sub: `${rupees(row.value)} spent`,
            value: row.purchases,
          }))}
        />
      </Card>

      <Card
        title="What are they browsing, and how close to buying?"
        subtitle={`${count(browsing.total)} browsing events by category. Cart and save events show buying intent.`}
      >
        <BarList
          items={browsing.by_category.map((row) => ({
            key: row.category,
            label: capitalize(row.category),
            sub: row.cart_or_save ? `${row.cart_or_save} cart or save` : "views only",
            value: row.events,
          }))}
        />
        <div className="pf-inline-stats">
          {EVENT_ORDER.filter((t) => browsing.event_types[t]).map((t) => (
            <Stat key={t} label={EVENT_LABELS[t]} value={browsing.event_types[t]} />
          ))}
        </div>
      </Card>

      <Card
        title="Where are the wardrobe gaps?"
        subtitle="Customers missing each category, as reported by gap analysis."
      >
        <BarList
          items={gaps.missing_categories.map((g) => ({
            key: g.label,
            label: capitalize(g.label),
            sub: g.customer_ids.join(", "),
            value: g.customer_ids.length,
          }))}
          formatValue={pluralCustomers}
          emptyText="No category gaps reported"
        />
        {gaps.occasion_gaps.length > 0 && (
          <>
            <p className="pf-section-label">Occasion gaps</p>
            <BarList
              items={gaps.occasion_gaps.map((g) => ({
                key: g.label,
                label: capitalize(g.label),
                sub: g.customer_ids.join(", "),
                value: g.customer_ids.length,
              }))}
              formatValue={pluralCustomers}
            />
          </>
        )}
        <p className="pf-footnote">
          {gaps.customers_without_gaps.length
            ? `No gaps: ${gaps.customers_without_gaps.join(", ")} — recommendations for them rely on intent, purchases and season.`
            : "Every customer has at least one reported gap."}
        </p>
      </Card>

      <Card
        title="How much browsing intent is there to act on?"
        subtitle="Customers by their strongest browsing intent. Insufficient means too little browsing to infer intent."
      >
        <div className="pf-inline-stats pf-inline-stats-large">
          {["strong", "moderate", "insufficient"].map((s) => (
            <Stat key={s} label={INTENT_LABELS[s]} value={intent[s] || 0} hint="customers" />
          ))}
        </div>
      </Card>

      <Card
        title="What kind of recommendations is the system making?"
        subtitle={`Primary type across ${count(recommendations.total)} recommendations (${recommendations.agent_selected} AI-selected).`}
      >
        <BarList
          items={Object.entries(recommendations.primary_type)
            .sort((a, b) => b[1] - a[1])
            .map(([type, value]) => ({ key: type, label: TYPE_LABELS[type] || type, value }))}
        />
        <p className="pf-footnote">
          {recommendations.with_offer} of {recommendations.total} carry an active offer.
        </p>
      </Card>

      <Card title="Which offers are live?" subtitle={`${offers.active} of ${offers.total} offers are active today, by type.`}>
        <BarList
          items={Object.entries(offers.active_by_type)
            .sort((a, b) => b[1] - a[1])
            .map(([type, value]) => ({ key: type, label: humanize(type), value }))}
          emptyText="No active offers"
        />
      </Card>
    </div>
  );
}
