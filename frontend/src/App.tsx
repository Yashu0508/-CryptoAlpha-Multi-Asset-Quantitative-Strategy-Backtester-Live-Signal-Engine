import type { ReactElement } from "react";

import { AppLayout } from "./layouts/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";

/** Root application composition point for routing and global providers. */
export function App(): ReactElement {
  return (
    <AppLayout>
      <DashboardPage />
    </AppLayout>
  );
}
