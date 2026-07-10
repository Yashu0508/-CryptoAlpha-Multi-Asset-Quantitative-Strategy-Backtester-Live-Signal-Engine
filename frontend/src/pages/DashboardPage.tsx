import type { ReactElement } from "react";

import { PlaceholderPanel } from "../components/PlaceholderPanel";

/** Initial dashboard shell; data visualizations are deliberately not wired yet. */
export function DashboardPage(): ReactElement {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Trading dashboard</h1>
      <p className="mt-2 text-slate-400">Platform modules are ready for integration.</p>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <PlaceholderPanel title="Market data" />
        <PlaceholderPanel title="Strategies" />
        <PlaceholderPanel title="Portfolio" />
      </div>
    </section>
  );
}
