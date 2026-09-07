export type RankingsRow = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  record: string;
  rank: number | null;
  adjEM: number | null;
  adjO: number | null;
  adjD: number | null;
  adjORank: number | null;
  adjDRank: number | null;
  sos: number | null;
  sosRank: number | null;
  sor: number | null;
  sorRank: number | null;
  rankChange: number | null;
};

export type RankingsSeason = {
  weeks: number[];
  byWeek: Record<string, RankingsRow[]>;
};

export type AdvancedWeekCounts = Record<string, number>;

export type AdvancedRow = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  cff: number | null;
  fieldPos: number | null;
  off: number | null;
  def: number | null;
  offExp: number | null;
  defExp: number | null;
  offFin: number | null;
  defFin: number | null;
  wk: AdvancedWeekCounts;
};

export type AdvancedSeason = {
  weeks: number[];
  byWeek: Record<string, AdvancedRow[]>;
};

export type SearchIndexEntry = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
};

export type SiteMeta = {
  rankingsYears: number[];
  advancedYears: number[];
};

export type PredictionGame = {
  gameId: string;
  week: number;
  homeTeam: string;
  homeTeamId: number;
  awayTeam: string;
  awayTeamId: number;
  predictedWinner: string;
  predictedMargin: number;
  confidence: number | null;
};

export type PredictionsWeek = {
  season: number;
  week: number;
  generatedAt: string;
  games: PredictionGame[];
};
