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

// Site-week -> human label, for any week that isn't just "Week N" -- e.g.
// "17": "CFP Semifinal". Grouped by CFBD's own playoff round field, not by
// date gaps, so postseason weeks are named correctly instead of numbered.
export type WeekLabels = Record<string, string>;

export type RankingsSeason = {
  weeks: number[];
  weekLabels: WeekLabels;
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
  weekLabels: WeekLabels;
  byWeek: Record<string, AdvancedRow[]>;
};

export type TeamStatsRow = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  successRate: number | null;
  successRateRank: number | null;
  passSuccessRate: number | null;
  passSuccessRateRank: number | null;
  rushSuccessRate: number | null;
  rushSuccessRateRank: number | null;
  successRateAllowed: number | null;
  successRateAllowedRank: number | null;
  passSuccessRateAllowed: number | null;
  passSuccessRateAllowedRank: number | null;
  rushSuccessRateAllowed: number | null;
  rushSuccessRateAllowedRank: number | null;
  yardsPerPlay: number | null;
  yardsPerPlayRank: number | null;
  yardsPerPlayAllowed: number | null;
  yardsPerPlayAllowedRank: number | null;
  explosivePlayRate: number | null;
  explosivePlayRateRank: number | null;
  explosivePlayRateAllowed: number | null;
  explosivePlayRateAllowedRank: number | null;
  passRate: number | null;
  passRateAgainst: number | null;
  pace: number | null;
  fieldPositionEdge: number | null;
  fieldPositionEdgeRank: number | null;
  fieldPositionRaw: number | null;
  fieldPositionRawRank: number | null;
  fieldPositionRawAllowed: number | null;
  fieldPositionRawAllowedRank: number | null;
  finishingRate: number | null;
  finishingRateRank: number | null;
  finishingRateAllowed: number | null;
  finishingRateAllowedRank: number | null;
  adjustedExplosivenessOffense: number | null;
  adjustedExplosivenessOffenseRank: number | null;
  adjustedExplosivenessDefense: number | null;
  adjustedExplosivenessDefenseRank: number | null;
  adjustedFinishingOffense: number | null;
  adjustedFinishingOffenseRank: number | null;
  adjustedFinishingDefense: number | null;
  adjustedFinishingDefenseRank: number | null;
};

export type TeamStatsSeason = {
  week: number;
  weekLabel: string;
  teams: TeamStatsRow[];
};

// Same rows as TeamStatsSeason, but one snapshot per week (cumulative
// through that week only) instead of one season-to-date snapshot -- lets a
// matchup/weekly page look up a team's stats strictly before a given game,
// the same pregame-snapshot pattern already used for RPI/RPI-O/RPI-D.
export type TeamStatsWeeklySeason = {
  weeks: number[];
  weekLabels: WeekLabels;
  byWeek: Record<string, TeamStatsRow[]>;
};

export type ScheduleGame = {
  gameId: string;
  week: number;
  seasonType: string;
  startDate: string | null;
  startTimeTBD: boolean;
  completed: boolean;
  neutralSite: boolean;
  conferenceGame: boolean;
  venue: string | null;
  homeTeam: string;
  homeTeamId: number;
  homeSlug: string;
  homeConference: string | null;
  awayTeam: string;
  awayTeamId: number;
  awaySlug: string;
  awayConference: string | null;
  homePoints: number | null;
  awayPoints: number | null;
};

export type ScheduleSeason = {
  weeks: number[];
  weekLabels: WeekLabels;
  currentWeek: number;
  byWeek: Record<string, ScheduleGame[]>;
};

export type SearchIndexEntry = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
};

export type SiteMeta = {
  generatedAt?: string;
  dataVersion?: string;
  scope?: string;
  rankingsYears: number[];
  advancedYears: number[];
  scheduleYears?: number[];
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
  access?: "limited" | "full";
  totalGames?: number;
};
