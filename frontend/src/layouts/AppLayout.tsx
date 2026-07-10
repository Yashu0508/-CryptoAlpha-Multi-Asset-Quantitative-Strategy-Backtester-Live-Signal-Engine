import type { PropsWithChildren, ReactElement } from "react";

/** Shared visual frame for authenticated application pages. */
export function AppLayout({ children }: PropsWithChildren): ReactElement {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 px-6 py-4">
        <span className="text-lg font-semibold tracking-tight">CryptoAlpha</span>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
