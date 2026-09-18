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

// Which rating methodology produced this season's adjEM/adjO/adjD. Published
// with the numbers so a new-methodology rating can never be silently confused
// with a legacy one. `modelId` is stable per methodology (currently
// "adj-rating-hierarchical-hfa-v1"); the remaining fields are configuration
// provenance and are not surfaced in the UI.
export type RatingModelMeta = {
  modelId: string;
  modelMode: "hierarchical_hfa" | "legacy";
  [key: string]: unknown;
};

export type RankingsSeason = {
  weeks: number[];
  weekLabels: WeekLabels;
  byWeek: Record<string, RankingsRow[]>;
  ratingModel?: RatingModelMeta;
};

export type AdvancedWeekCounts = Record<string, number>;

export type AdvancedRow = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  // Injected by /api/premium/advanced/[year] from the public Rankings
  // snapshot. These are the canonical headline ratings/ranks used by both
  // Ratings and Advanced.
  adjEM?: number | null;
  adjO?: number | null;
  adjD?: number | null;
  rank?: number | null;
  adjORank?: number | null;
  adjDRank?: number | null;
  cff: number | null;
  // ASM ("Adjusted Score Matrix") -- LEILA's own opponent-adjusted, blowout-
  // clipped scoring-margin rating (constrained least squares, margins capped
  // at +/-28 before fitting). A results-based counterpart to Adj. Net's
  // process-based (EPA/Success/Explosiveness) composite -- see the
  // methodology page.
  asm: number | null;
  // CFP make-the-field chance (0-1 fraction), from a live Monte Carlo season
  // simulation seeded with this week's in-season power. Live-season-only:
  // null for every past (completed) season and every week but the latest.
  cfpChancePct?: number | null;
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

// Research-stage Exploratory Tier 1 (series-level) statistics -- see
// /advanced/exploratory. Raw counts only; every rate is num/den, summed
// across the selected week range client-side, same convention as
// AdvancedRow.wk. Never fed into Adj. Net/Off/Def, ASM, or any prediction.
export type ExploratoryWeekCounts = {
  seriesOpportunities: number; seriesConversions: number;
  seriesStopOpportunities: number; seriesStops: number;
  recoveryOpportunities: number; recoveredSeries: number;
  closeoutOpportunities: number; closeouts: number;
  eligibleSeries: number; longDownSeries: number; longDownAvoidanceSeries: number;
  longDownCreationOpportunities: number; longDownsCreated: number;
  // Wave 2: Possessions (Clean Drive / Drive Killer)
  eligibleDrives: number; cleanDrives: number;
  eligibleDrivesFaced: number; cleanDrivesAllowed: number;
  drivesWithKillerEvent: number; drivesKilled: number; killerEvents: number;
  drivesWithKillerEventForced: number; drivesKilledForced: number;
  driveInterceptions: number; driveLostFumbles: number; driveSelfRecoveredFumbles: number;
  driveSacks: number; driveTFLs: number; driveOffensivePenalties: number; driveFailedFourthDowns: number;
  // Wave 2: Style/Risk (Explosive Dependency, Failure Burden/Pressure)
  positiveEpa: number; explosivePositiveEpa: number;
  explosivePlayCount: number; epaEligiblePlayCount: number;
  nonExplosiveEpa: number; nonExplosivePlays: number;
  positiveYards: number; explosivePositiveYards: number;
  negativeEpaPlays: number; epaEligiblePlays: number; negativeEpaMagnitudeSum: number;
  opponentNegativeEpaMagnitudeSum: number; opponentEpaEligiblePlays: number;
  // Wave 2: Finishing (Scoring Opportunity Value)
  scoringOpportunities: number; scoringOpportunityPoints: number;
  scoringOpportunityTouchdowns: number; scoringOpportunityFieldGoals: number;
  scoringOpportunityEmptyDrives: number;
  opponentScoringOpportunities: number; opponentScoringOpportunityPoints: number;
  // Turnovers (2025 research build)
  offensiveDrives: number; turnovers: number; interceptions: number; lostFumbles: number;
  selfRecoveredFumbles: number; passAttempts: number; turnoverEpaSum: number; games: number;
  opponentDrives: number; takeaways: number; interceptionsForced: number; fumbleRecoveries: number;
  opponentSelfRecoveredFumbles: number; opponentPassAttempts: number; opponentTurnoverEpaSum: number;
  // Penalties (2025 research build)
  offensivePenalties: number; offensivePenaltyYards: number;
  penaltiesForced: number; penaltyYardsForced: number;
  defensivePenalties: number; defensivePenaltyYards: number;
  penaltiesDrawn: number; penaltyYardsDrawn: number;
};

export type ExploratoryRow = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  wk: ExploratoryWeekCounts;
};

export type ExploratorySeason = {
  weeks: number[];
  weekLabels: WeekLabels;
  byWeek: Record<string, ExploratoryRow[]>;
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
// the same pregame-snapshot pattern already used for AdjNet/AdjOff/AdjDef.
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

export type MarketQuote = {
  gameId: string;
  provider: string;
  spread: number | null;
  spreadOpen: number | null;
  overUnder: number | null;
  overUnderOpen: number | null;
  homeMoneyline: number | null;
  awayMoneyline: number | null;
};

export type MarketGame = {
  gameId: string;
  week: number;
  homeTeam: string;
  awayTeam: string;
  primary: MarketQuote | null;
  providers: MarketQuote[];
};

export type MarketLinesSeason = {
  season: number;
  generatedAt: string;
  source: string;
  weeks: number[];
  games: Record<string, MarketGame>;
};

// Raw per-game numerator/denominator counts, keyed exactly like the `wk`
// per-week raw-count fields Advanced's rate columns already sum over (see
// AdvColumn.num/den in app/advanced/page.tsx) -- just for one single game
// (GameLogEntry.own) or one team's running season-to-date total through the
// week before a given game (GameLogEntry.opponentContext).
export type GameLogFields = Record<string, number>;

export type GameLogEntry = {
  gameId: string;
  week: number;
  opponent: string;
  opponentSlug: string | null;
  opponentTeamId: number | null;
  opponentClassification: string | null;
  homeAway: string;
  win: boolean;
  pointsFor: number | null;
  pointsAgainst: number | null;
  own: GameLogFields;
  // Null when the opponent hadn't played an FBS-graded game yet (their own
  // season opener, or an FCS opponent that never gets its own row).
  opponentContext: (GameLogFields & { _gamesThroughWeek?: number }) | null;
};

export type GameLogSeason = {
  version: string;
  weeks: number[];
  weekLabels: WeekLabels;
  byTeam: Record<string, GameLogEntry[]>;
};

// team_game_advanced: one row per (season, game_id, team), two rows per
// completed game -- powers the completed-game Game Results view on the
// matchup page. Raw single-game values only, no percentile baked in (see
// web/lib/team-game-advanced.ts, which computes percentile at read time
// against this same season file's own FBS-vs-FBS population). A field this
// row can't compute is `undefined` here with a short reason code under
// fieldAvailability, keyed by the same field name -- never silently
// substituted, never zero. See scripts/export_team_game_advanced.py.
export type TeamGameAdvancedRow = {
  season: number;
  week: number;
  season_type: string;
  game_id: string;
  team_id: number;
  team: string;
  team_slug: string;
  conference: string | null;
  classification: string | null;
  opponent_id: number;
  opponent: string;
  opponent_slug: string;
  opponent_classification: string | null;
  home_away: string;
  neutral_site: boolean;
  points: number | null;
  opponent_points: number | null;
  win: boolean | number | null;
  [metricKey: string]: unknown;
  field_availability?: Record<string, string>;
};

export type TeamGameAdvancedSeason = {
  version: string;
  season: number;
  sourceVersions: Record<string, string | null>;
  fieldAvailabilityReasons: Record<string, string>;
  rows: TeamGameAdvancedRow[];
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
  ratingModels?: Record<string, string>;
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

export type PreseasonPowerTeam = {
  team: string;
  teamId: number | null;
  slug: string | null;
  conf: string | null;
  powerScore: number;
  rank: number;
};

export type PreseasonPowerBacktest = {
  description: string;
  n: number;
  mae: number;
  winnerPct: number;
};

export type PreseasonPower = {
  season: number;
  freezeVersion: string;
  generatedAt: string;
  backtest: PreseasonPowerBacktest;
  teams: PreseasonPowerTeam[];
};

export type PredictionsWeek = {
  season: number;
  week: number;
  generatedAt: string;
  games: PredictionGame[];
  access?: "limited" | "full";
  totalGames?: number;
};

// A week's predictions are only "graded" once every game LEILA Ratings can verify
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

// One offense-vs-defense pairing effect, produced by
// exploratory_matchup_product.py from pregame-only, walk-forward-fitted
// additive models. `unit` is "epa" for the failure pairing and "rate"
// (a 0-1 share) for every other pairing; failureRate/EPA values are not
// bounded to [0, 1] the way the others are. `advantageTeam` is null for a
// style pairing (Explosive Dependency) even when `meaningful` is true --
// dependency is descriptive, not good or bad, so no side is favored.
export type MatchupEdge = {
  pairing: string;
  title: string;
  definition: string;
  offenseTeam: string;
  defenseTeam: string;
  offenseLabel: string;
  defenseLabel: string;
  offenseRate: number;
  defenseRate: number;
  offenseRank: number | null;
  defenseRank: number | null;
  offenseN: number;
  defenseN: number;
  offenseMinN: number;
  defenseMinN: number;
  expected: number;
  offenseOnly: number;
  opponentEffect: number;
  advantageTeam: string | null;
  style: boolean;
  unit: "epa" | "rate";
  threshold: number | null;
  effectPercentile: number | null;
  meaningful: boolean;
  modelId: string;
  throughWeek: number;
};

// Public, free historical fact -- who made the CFP field, and who played in
// the championship game -- derived straight from CFBD's own structured
// `playoff` field on each postseason game (see scripts/export_cfp_results.py).
// `champion`/`runnerUp` are null until that season's championship game has
// been played.
export type CfpTeamRef = { teamId: number; team: string };

export type CfpSeasonResult = {
  season: number;
  fieldSize: number;
  participants: CfpTeamRef[];
  champion: CfpTeamRef | null;
  runnerUp: CfpTeamRef | null;
};

export type MatchupEdgesGame = {
  season: number;
  gameId: string;
  week: number;
  status: "ready" | "even" | "limited";
  availablePairings: number;
  possiblePairings: number;
  edges: MatchupEdge[];
};
