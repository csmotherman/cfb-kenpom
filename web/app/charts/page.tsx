import type { Metadata } from "next";
import ChartsClient from "./ChartsClient";

export const metadata: Metadata = {
  title: "Chart Studio | PRIME",
  description: "Internal PRIME college football chart builder.",
  robots: {
    index: false,
    follow: false,
    googleBot: { index: false, follow: false },
  },
};

export default function ChartsPage() {
  return <ChartsClient />;
}
