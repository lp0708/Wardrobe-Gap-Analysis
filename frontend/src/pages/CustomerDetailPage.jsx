import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import "../App.css";
import { getIntelligence, getPlatformRecommendations } from "../api";
import CustomerOverview from "../components/CustomerOverview";
import GapsPanel from "../components/GapsPanel";
import IntelligencePanel from "../components/IntelligencePanel";
import { count, rupees } from "../platform/format";
import RecommendationRow from "../platform/RecommendationRow";
import {
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
  PageHeader,
  Tabs,
  useApi,
} from "../platform/ui";

export default function CustomerDetailPage() {
  const { customerId } = useParams();
  const intel = useApi(() => getIntelligence(customerId), [customerId]);
  const recs = useApi(() => getPlatformRecommendations(customerId), [customerId]);
  const [tab, setTab] = useState("intelligence");

  const back = { to: "/customers", label: "Customers" };

  if (intel.error) {
    return (
      <>
        <PageHeader back={back} title={customerId} />
        <ErrorState message={intel.error} />
      </>
    );
  }

  if (intel.loading && !intel.data) {
    return (
      <>
        <PageHeader back={back} title={customerId} />
        <LoadingState label={`Analysing ${customerId}`} />
      </>
    );
  }

  const data = intel.data;
  const purchases = data.purchase_patterns;
  const gaps = data.gaps;
  const gapCount = gaps.missing_categories.length + gaps.imbalances.length + gaps.occasion_gaps.length;
  const rows = recs.data?.rows || [];
  const agentRows = rows.filter((r) => r.source === "agent");

  return (
    <>
      <PageHeader
        back={back}
        eyebrow="Customer"
        title={customerId}
        description={data.browsing_intent.headline}
        actions={
          <Link className="pf-button pf-button-primary" to={`/demo?customer=${customerId}`}>
            Run AI agent in demo
          </Link>
        }
      />

      <div className="pf-kpi-grid pf-kpi-grid-5">
        <KpiCard label="Budget per item" value={rupees(data.profile.budget)} />
        <KpiCard label="Purchases" value={count(purchases.purchase_count)} hint={purchases.spend ? `${rupees(purchases.spend.total)} total` : "No purchases"} />
        <KpiCard label="Average spend" value={purchases.spend ? rupees(purchases.spend.average) : "—"} hint={purchases.spend ? `${purchases.spend.average_vs_budget_pct}% of budget` : null} />
        <KpiCard label="Browsing events" value={count(data.browsing_intent.event_count)} />
        <KpiCard accent={gapCount > 0} label="Wardrobe gaps" value={count(gapCount)} hint={gapCount ? "Reported by gap analysis" : "Wardrobe well covered"} />
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "intelligence", label: "Intelligence" },
          { value: "recommendations", label: "Recommendations", count: recs.data ? rows.length : undefined },
        ]}
      />

      {tab === "intelligence" && (
        <div className="pf-embedded-panels">
          <CustomerOverview profile={data.profile} />
          <IntelligencePanel
            purchases={data.purchase_patterns}
            intent={data.browsing_intent}
            seasonal={data.seasonal_context}
          />
          <GapsPanel gaps={data.gaps} />
        </div>
      )}

      {tab === "recommendations" && (
        <div className="pf-stack">
          {recs.loading && !recs.data && <LoadingState label="Ranking products" />}
          {recs.error && <ErrorState message={recs.error} />}
          {recs.data && (
            <>
              <p className="pf-footnote pf-footnote-top">
                {agentRows.length
                  ? `${agentRows.length} picks from the latest agent run, followed by the engine's other top-ranked products.`
                  : "No saved agent run yet — showing the recommendation engine's top-ranked products."}
              </p>
              {rows.length === 0 ? (
                <EmptyState title="No eligible products">Nothing in the catalogue fits this customer's budget and preferences.</EmptyState>
              ) : (
                <div className="pf-rec-list">
                  {rows.map((rec) => (
                    <RecommendationRow key={`${rec.source}-${rec.product_id}`} rec={rec} showCustomer={false} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
