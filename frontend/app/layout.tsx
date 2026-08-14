import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis OS — Institutional Intelligence",
  description:
    "Analytical workbench over ten years of studio history — ClickHouse track, Convergence Studios",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
