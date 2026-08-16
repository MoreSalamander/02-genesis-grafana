import type { Metadata } from "next";
import "./alive.css";   // first: globals.css maps this console's palette onto it
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis OS — Operational Intelligence",
  description: "Agentic operational cognition for Convergence Studios (Grafana track).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">{children}</div>
      </body>
    </html>
  );
}
