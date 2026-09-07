"use client";

import PremiumRouteError from "@/components/PremiumRouteError";

export default function PredictionsError({
  error,
  reset,
}: {
  error: Error & { status?: number; code?: string };
  reset: () => void;
}) {
  return <PremiumRouteError error={error} reset={reset} product="Predictions" />;
}
