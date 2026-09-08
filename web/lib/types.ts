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
  offHavoc: number | null;
  defHavoc: number | null;
  // EPA (CFBD ppa) and Success Rate, opponent-adjusted, pass/rush and by
  // down. Each is a confidence-blended edge -- at ~1 game played it reads
  // as the team's own raw rate minus league average (no adjustment yet);
  // confidence ramps up to a full opponent-adjusted edge by ~5 games
  // played. See EPA_ADJUSTMENT_RAMP_GAMES in build_real_data.py. The raw
  // (non-adjusted) rate for each of these is summable client-side from
  // `wk` using the matching Num/Den keys (epaNum/epaDen, passEpaNum/
  // passEpaDen, passDown1EpaNum/passDown1EpaDen, passSuccessNum/
  // passSuccessDen, passDown1SuccessNum/passDown1SuccessDen, etc; the
  // "Allowed"-suffixed pair is the defensive raw rate).
  successAdj: number | null; successAdjAllowed: number | null;
  epaAdj: number | null; epaAdjAllowed: number | null;
  passEpaAdj: number | null; passEpaAdjAllowed: number | null;
  rushEpaAdj: number | null; rushEpaAdjAllowed: number | null;
  passEpaDown1Adj: number | null; passEpaDown1AdjAllowed: number | null;
  passEpaDown2Adj: number | null; passEpaDown2AdjAllowed: number | null;
  passEpaDown3Adj: number | null; passEpaDown3AdjAllowed: number | null;
  rushEpaDown1Adj: number | null; rushEpaDown1AdjAllowed: number | null;
  rushEpaDown2Adj: number | null; rushEpaDown2AdjAllowed: number | null;
  rushEpaDown3Adj: number | null; rushEpaDown3AdjAllowed: number | null;
  passSuccessAdj: number | null; passSuccessAdjAllowed: number | null;
  rushSuccessAdj: number | null; rushSuccessAdjAllowed: number | null;
  passSuccessDown1Adj: number | null; passSuccessDown1AdjAllowed: number | null;
  passSuccessDown2Adj: number | null; passSuccessDown2AdjAllowed: number | null;
  passSuccessDown3Adj: number | null; passSuccessDown3AdjAllowed: number | null;
  rushSuccessDown1Adj: number | null; rushSuccessDown1AdjAllowed: number | null;
  rushSuccessDown2Adj: number | null; rushSuccessDown2AdjAllowed: number | null;
  rushSuccessDown3Adj: number | null; rushSuccessDown3AdjAllowed: number | null;
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
  havocRateForced: number | null;
  havocRateForcedRank: number | null;
  havocRateAllowed: number | null;
  havocRateAllowedRank: number | null;
  adjustedHavocOffense: number | null;
  adjustedHavocOffenseRank: number | null;
  adjustedHavocDefense: number | null;
  adjustedHavocDefenseRank: number | null;
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

// A week's predictions are only "graded" once every game GRID can verify
// (gameId matched against the public schedule, with a final score) has
// finished -- so `games` and `graded` can differ for an in-progress week,
// and accuracySU/avgAbsMarginError are null (not 0) until at least one game
// in that week is gradeable, so an unplayed week never reads as "wrong."
export type PredictionRecordStats = {
  games: number;
  graded: number;
  correct: number;
  accuracySU: number | null;
  avgAbsMarginError: number | null;
};

export type PredictionWeekRecord = PredictionRecordStats & { week: number };

export type PredictionsTrackRecord = {
  season: number;
  modelVersion: string;
  generatedAt: string;
  weeks: PredictionWeekRecord[];
  overall: PredictionRecordStats;
};
