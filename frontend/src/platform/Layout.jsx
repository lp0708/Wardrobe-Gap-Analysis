import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import "./platform.css";

function Icon({ name }) {
  const paths = {
    dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
    customers:
      "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1M17 3.5a4 4 0 0 1 0 7M22 21v-1a6 6 0 0 0-4-5.6",
    recommendations: "M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z",
    analytics: "M4 20V10M10 20V4M16 20v-7M22 20H2",
    demo: "M8 5v14l11-7z",
    menu: "M4 6h16M4 12h16M4 18h16",
  };
  return (
    <svg className="pf-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/customers", label: "Customers", icon: "customers" },
  { to: "/recommendations", label: "Recommendations", icon: "recommendations" },
  { to: "/analytics", label: "Analytics", icon: "analytics" },
];

export default function Layout() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const isDemo = location.pathname.startsWith("/demo");

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className={`pf-shell ${menuOpen ? "pf-shell-menu-open" : ""}`}>
      <aside className="pf-sidebar" aria-label="Main navigation">
        <div className="pf-brand">
          <img className="pf-brand-mark" src="/logo.png" alt="" />
          <span className="pf-brand-text">
            <span className="pf-brand-name">Recon</span>
            <span className="pf-brand-sub">AI retail intelligence</span>
          </span>
        </div>

        <nav className="pf-nav">
          <p className="pf-nav-heading">Workspace</p>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `pf-nav-link ${isActive ? "pf-nav-link-active" : ""}`}
            >
              <Icon name={item.icon} />
              {item.label}
            </NavLink>
          ))}

          <p className="pf-nav-heading">AI workflow</p>
          <NavLink
            to="/demo"
            className={({ isActive }) => `pf-nav-demo ${isActive ? "pf-nav-demo-active" : ""}`}
          >
            <span className="pf-nav-demo-icon">
              <Icon name="demo" />
            </span>
            <span className="pf-nav-demo-text">
              <span className="pf-nav-demo-title">Demo</span>
              <span className="pf-nav-demo-sub">Run the agent end to end</span>
            </span>
          </NavLink>
        </nav>
      </aside>

      <button
        type="button"
        className="pf-scrim"
        aria-label="Close navigation"
        onClick={() => setMenuOpen(false)}
      />

      <div className="pf-main">
        {/* Small screens only: the sidebar collapses, so this bar holds the menu button. */}
        <div className="pf-mobile-bar">
          <button
            type="button"
            className="pf-menu-button"
            aria-label="Open navigation"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <span className="pf-mobile-brand">Recon</span>
        </div>

        {/* The demo keeps its own page layout, so it gets no extra padding. */}
        <main className={isDemo ? "pf-content-demo" : "pf-content"}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
