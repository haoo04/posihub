import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { OverviewPage } from "@/pages/OverviewPage";
import { AccountsPage } from "@/pages/AccountsPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { PnlPage } from "@/pages/PnlPage";
import { ManualEntryPage } from "@/pages/ManualEntryPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/positions" element={<PositionsPage />} />
        <Route path="/pnl" element={<PnlPage />} />
        <Route path="/manual" element={<ManualEntryPage />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  );
}
