"use client";

import PremiumRouteError from "@/components/PremiumRouteError";

export default function AdvancedError({
  error,
  reset,
}: {
  error: Error & { status?: number; code?: string };
  reset: () => void;
}) {
  return <PremiumRouteError error={error} reset={reset} product="Advanced Analytics" />;
}
