import { Link } from "react-router-dom";

import { EmptyState, PageHeader } from "../platform/ui";

export default function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState
        title="There's nothing at this address"
        action={
          <Link className="pf-button" to="/dashboard">
            Go to dashboard
          </Link>
        }
      />
    </>
  );
}
