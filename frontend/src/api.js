// Set VITE_API_URL at build time for a deployed backend; defaults to local uvicorn.
const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, options) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new Error(
      `Can't reach the backend at ${BASE}. Is uvicorn running on port 8000?`
    );
  }

  if (!response.ok) {
    // FastAPI puts the readable message in `detail`.
    let detail = `Request failed (HTTP ${response.status}).`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body - keep the status message */
    }
    throw new Error(detail);
  }

  return response.json();
}

export const listCustomers = () => request("/customers");

// Deterministic analysis - instant, no model call.
export const getIntelligence = (id) => request(`/customers/${id}/intelligence`);

export const recommend = (id) => request(`/recommend/${id}`, { method: "POST" });

// Platform views - read-only aggregation over the same intelligence and saved runs.
export const getOverview = () => request("/platform/overview");

export const getPlatformRecommendations = (customerId) =>
  request(
    customerId
      ? `/platform/recommendations?customer_id=${encodeURIComponent(customerId)}`
      : "/platform/recommendations"
  );

export const getAnalytics = () => request("/platform/analytics");
