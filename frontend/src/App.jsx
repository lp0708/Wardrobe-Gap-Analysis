import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AnalyticsPage from "./pages/AnalyticsPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomersPage from "./pages/CustomersPage";
import DashboardPage from "./pages/DashboardPage";
import DemoPage from "./pages/DemoPage";
import NotFoundPage from "./pages/NotFoundPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import Layout from "./platform/Layout";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="customers/:customerId" element={<CustomerDetailPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="demo" element={<DemoPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
