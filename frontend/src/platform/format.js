export const rupees = (value) =>
  value === null || value === undefined ? "—" : `₹${Number(value).toLocaleString("en-IN")}`;

export const count = (value) => Number(value || 0).toLocaleString("en-IN");

function toDate(iso) {
  // Plain dates ("2026-09-08") are calendar days - parse them as local, not UTC.
  return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
}

export function formatDate(iso) {
  if (!iso) return "—";
  return toDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  return toDate(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);

export const TYPE_LABELS = {
  gap: "Wardrobe gap",
  intent: "Browsing intent",
  seasonal: "Seasonal",
  complementary: "Complementary",
};

export const INTENT_LABELS = {
  strong: "Strong intent",
  moderate: "Moderate intent",
  insufficient: "Insufficient data",
};

export const EVENT_LABELS = {
  viewed: "Viewed",
  saved: "Saved",
  added_to_cart: "Added to cart",
  abandoned_cart: "Abandoned cart",
};

export const SIGNAL_LABELS = {
  gap: "Gap",
  intent: "Intent",
  seasonal: "Season",
  trend: "Trend",
  complementary: "Pairs",
  preference: "Preference",
  purchase: "Purchases",
  offer: "Offer",
  penalty: "Penalty",
};

export function offerLabel(offer) {
  if (!offer) return null;
  if (offer.offer_type === "free_shipping") return "Free shipping";
  if (offer.discount_percentage) {
    return `${offer.discount_percentage}% ${offer.offer_type === "bundle_discount" ? "bundle" : "off"}`;
  }
  return offer.offer_type.replace(/_/g, " ");
}

export const humanize = (key) => capitalize(String(key).replace(/_/g, " "));
