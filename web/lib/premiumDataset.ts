import { unstable_cache } from "next/cache";
import { createAdminClient } from "@/lib/supabase/admin";

type DatasetType =
  | "advanced"
  | "predictions"
  | "exploratory"
  | "exploratory_matchups"
  | "team_game_advanced";

type PredictionRow = {
  week: number;
  payload: unknown;
};

const loadPremiumDatasetCached = unstable_cache(
  async (datasetType: DatasetType, season: number, week: number) => {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", datasetType)
      .eq("season", season)
      .eq("week", week)
      .maybeSingle();

    if (error) throw error;
    return data?.payload ?? null;
  },
  ["premium-dataset-v1"],
  { revalidate: 300 },
);

const loadPredictionSeasonCached = unstable_cache(
  async (season: number): Promise<PredictionRow[]> => {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload,week")
      .eq("dataset_type", "predictions")
      .eq("season", season)
      .order("week", { ascending: true });

    if (error) throw error;
    return (data ?? []) as PredictionRow[];
  },
  ["premium-prediction-season-v1"],
  { revalidate: 300 },
);

export async function getPremiumDataset<T>(
  datasetType: DatasetType,
  season: number,
  week = 0,
): Promise<T | null> {
  return (await loadPremiumDatasetCached(datasetType, season, week)) as T | null;
}

export async function getPremiumPredictionSeasonRows<T>(
  season: number,
): Promise<Array<{ week: number; payload: T }>> {
  return (await loadPredictionSeasonCached(season)) as Array<{ week: number; payload: T }>;
}
