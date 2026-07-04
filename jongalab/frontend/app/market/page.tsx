import type { Metadata } from "next";
import { MarketClient } from "./MarketClient";

export const metadata: Metadata = {
  alternates: { canonical: "/market" },
};

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return <MarketClient />;
}
