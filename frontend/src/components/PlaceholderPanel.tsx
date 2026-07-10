import type { ReactElement } from "react";

interface PlaceholderPanelProps {
  title: string;
}

/** Reusable empty-state panel for unimplemented dashboard modules. */
export function PlaceholderPanel({ title }: PlaceholderPanelProps): ReactElement {
  return (
    <article className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h2 className="font-medium">{title}</h2>
      <p className="mt-2 text-sm text-slate-400">No data source connected.</p>
    </article>
  );
}
