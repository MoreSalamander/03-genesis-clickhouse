import type { Metadata } from "next";
import "./alive.css";   // first: globals.css maps this console's palette onto it
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis OS — Institutional Intelligence",
  description:
    "Analytical workbench over a century of studio history (1912–2026) — ClickHouse track, Convergence Studios",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
