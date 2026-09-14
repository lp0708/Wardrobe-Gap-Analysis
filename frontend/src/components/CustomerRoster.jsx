export default function CustomerRoster({ customers, selectedId, onSelect, disabled }) {
  return (
    <section className="panel">
      <p className="eyebrow">Step 1</p>
      <h2 className="panel-title">Select a customer</h2>
      <p className="panel-sub">
        Demo roster of eight customers, each with their own purchase history, browsing
        behaviour, preferences and budget.
      </p>

      <div className="roster">
        {customers.map((customer) => {
          const active = customer.customer_id === selectedId;
          return (
            <button
              key={customer.customer_id}
              type="button"
              className={`roster-card ${active ? "roster-card-active" : ""}`}
              onClick={() => onSelect(customer.customer_id)}
              aria-pressed={active}
              disabled={disabled}
            >
              <span className="roster-id">{customer.customer_id}</span>
              <span className="roster-styles">{customer.preferred_styles.join(" · ")}</span>
              <span className="roster-meta">
                &#8377;{customer.budget.toLocaleString("en-IN")} budget &middot;{" "}
                {customer.purchase_count} {customer.purchase_count === 1 ? "purchase" : "purchases"}{" "}
                &middot; {customer.browsing_event_count} browsing{" "}
                {customer.browsing_event_count === 1 ? "event" : "events"}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
