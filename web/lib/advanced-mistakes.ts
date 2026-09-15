export type MistakesPerspective = "offense" | "defense" | "margin" | "both";

export type MistakesColumn = {
  key: string;
  label: string;
  fmt: "pct1" | "signedPct1" | "plain2" | "plain3" | "signed2" | "signed3";
  primary?: boolean;
  rankable: true;
  lowerBetter?: boolean;
  kind: "snapshot";
  tooltip: string;
};

export type MistakesSection = { title: string; columns: MistakesColumn[] };

export type MistakesTab = {
  label: string;
  primaryKey: string;
  columns: MistakesColumn[];
  sections: MistakesSection[];
  note: string;
  supportsPerspective: true;
};

function col(
  key: string,
  label: string,
  fmt: MistakesColumn["fmt"],
  tooltip: string,
  options: Pick<MistakesColumn, "primary" | "lowerBetter"> = {},
): MistakesColumn {
  return { key, label, fmt, tooltip, rankable: true, kind: "snapshot", ...options };
}

const TURNOVER_OFFENSE: MistakesColumn[] = [
  col("turnoverRate", "TO Rate", "pct1", "Share of offensive drives ending in an interception or fumble lost to the defense. Self-recovered fumbles do not count.", { primary: true, lowerBetter: true }),
  col("intRate", "INT Rate", "pct1", "Interceptions thrown divided by pass attempts.", { lowerBetter: true }),
  col("lostFumbleRate", "Lost Fumble Rate", "pct1", "Fumbles lost to the defense divided by offensive drives. Self-recovered fumbles do not count.", { lowerBetter: true }),
  col("turnoverEpaLostPerGame", "TO EPA Lost/Game", "plain3", "Canonical play EPA lost on interceptions and lost fumbles per game. Lower is better.", { lowerBetter: true }),
  col("turnoverEpaLostPerDrive", "TO EPA Lost/Drive", "plain3", "Canonical play EPA lost on interceptions and lost fumbles per offensive drive. Lower is better.", { lowerBetter: true }),
];

const TURNOVER_DEFENSE: MistakesColumn[] = [
  col("takeawayRate", "Takeaway Rate", "pct1", "Share of opponent drives ending in an interception or fumble recovered by this defense.", { primary: true }),
  col("intRateForced", "INT Rate Forced", "pct1", "Defensive interceptions divided by opponent pass attempts."),
  col("fumbleRecoveryRate", "Fumble Recovery Rate", "pct1", "Opponent fumbles actually recovered by this defense divided by opponent drives."),
  col("turnoverEpaCreatedPerGame", "TO EPA Created/Game", "plain3", "Canonical play EPA taken from opponents on interceptions and recovered fumbles per game."),
  col("turnoverEpaCreatedPerDrive", "TO EPA Created/Drive", "plain3", "Canonical play EPA taken from opponents on interceptions and recovered fumbles per opponent drive."),
];

const TURNOVER_MARGIN: MistakesColumn[] = [
  col("turnoverRateMargin", "TO Rate Margin", "signedPct1", "Takeaway rate minus offensive turnover rate. Higher is better.", { primary: true }),
  col("intRateMargin", "INT Rate Margin", "signedPct1", "Defensive interception rate minus offensive interception rate. Higher is better."),
  col("fumbleRateMargin", "Fumble Rate Margin", "signedPct1", "Defensive fumble-recovery rate minus offensive lost-fumble rate. Higher is better."),
  col("turnoverEpaMarginPerGame", "TO EPA Margin/Game", "signed3", "Turnover EPA created minus turnover EPA lost per game. Higher is better."),
  col("turnoverEpaMarginPerDrive", "TO EPA Margin/Drive", "signed3", "Turnover EPA created minus turnover EPA lost per drive. Higher is better."),
];

const PENALTY_OFFENSE: MistakesColumn[] = [
  col("penaltyRate", "Penalty Rate", "pct1", "Accepted penalties against the offense divided by offensive drives.", { lowerBetter: true }),
  col("penaltyYardsPerDrive", "Penalty Yds/Drive", "plain2", "Penalty yards charged to the offense per offensive drive.", { lowerBetter: true }),
  col("penaltiesDrawnRate", "Drawn Rate", "pct1", "Accepted penalties drawn on the opposing defense divided by offensive drives."),
  col("penaltyYardsDrawnPerDrive", "Drawn Yds/Drive", "plain2", "Penalty yards gained from fouls drawn on the opposing defense per offensive drive."),
];

const PENALTY_DEFENSE: MistakesColumn[] = [
  col("penaltiesForcedRate", "Penalties Forced Rate", "pct1", "Accepted offensive penalties by opponents divided by opponent drives."),
  col("penaltyYardsForcedPerDrive", "Penalty Yds Forced/Drive", "plain2", "Penalty yards taken from opponent offenses per opponent drive."),
  col("defensivePenaltyRate", "Def. Penalty Rate", "pct1", "Accepted penalties against this defense divided by opponent drives.", { lowerBetter: true }),
  col("defensivePenaltyYardsPerDrive", "Def. Penalty Yds/Drive", "plain2", "Penalty yards conceded by this defense per opponent drive.", { lowerBetter: true }),
];

const PENALTY_MARGIN: MistakesColumn[] = [
  col("offPenaltyRateMargin", "Off Penalty Margin", "signedPct1", "Penalties drawn by the offense minus penalties committed by the offense, per drive. Higher is better."),
  col("offPenaltyYardsMargin", "Off Pen Yds Margin", "signed2", "Penalty yards drawn minus penalty yards committed by the offense, per drive. Higher is better."),
  col("defPenaltyRateMargin", "Def Penalty Margin", "signedPct1", "Opponent offensive penalties forced minus penalties committed by this defense, per opponent drive. Higher is better."),
  col("defPenaltyYardsMargin", "Def Pen Yds Margin", "signed2", "Opponent penalty yards forced minus penalty yards conceded by this defense, per opponent drive. Higher is better."),
];

export function buildMistakesTab(perspective: MistakesPerspective): MistakesTab {
  const offense = perspective === "offense" || perspective === "both";
  const defense = perspective === "defense";
  const turnoverColumns = offense ? TURNOVER_OFFENSE : defense ? TURNOVER_DEFENSE : TURNOVER_MARGIN;
  const penaltyColumns = offense ? PENALTY_OFFENSE : defense ? PENALTY_DEFENSE : PENALTY_MARGIN;
  const sections = [
    { title: "Turnovers", columns: turnoverColumns },
    { title: "Penalties", columns: penaltyColumns },
  ];
  return {
    label: "Turnovers & Penalties",
    primaryKey: turnoverColumns[0].key,
    sections,
    columns: sections.flatMap((section) => section.columns),
    supportsPerspective: true,
    note: "2025 data only for now. Fumbles count only when possession is lost to the defense; self-recovered fumbles are excluded. Margin is benefit minus cost, so higher is better.",
  };
}

function safeRate(num: number, den: number): number | null {
  return den > 0 ? num / den : null;
}

function diff(a: number | null, b: number | null): number | null {
  return a === null || b === null ? null : a - b;
}

export function computeMistakesMetrics(counts: Record<string, number> | undefined): Record<string, number | null> {
  if (!counts) return {};
  const n = (key: string) => Number(counts[key] || 0);
  const games = n("games");
  const offensiveDrives = n("offensiveDrives");
  const opponentDrives = n("opponentDrives");
  const passAttempts = n("passAttempts");
  const opponentPassAttempts = n("opponentPassAttempts");

  const turnoverRate = safeRate(n("turnovers"), offensiveDrives);
  const intRate = safeRate(n("interceptions"), passAttempts);
  const lostFumbleRate = safeRate(n("lostFumbles"), offensiveDrives);
  const turnoverEpaLostPerGame = games > 0 ? -n("turnoverEpaSum") / games : null;
  const turnoverEpaLostPerDrive = offensiveDrives > 0 ? -n("turnoverEpaSum") / offensiveDrives : null;

  const takeawayRate = safeRate(n("takeaways"), opponentDrives);
  const intRateForced = safeRate(n("interceptionsForced"), opponentPassAttempts);
  const fumbleRecoveryRate = safeRate(n("fumbleRecoveries"), opponentDrives);
  const turnoverEpaCreatedPerGame = games > 0 ? -n("opponentTurnoverEpaSum") / games : null;
  const turnoverEpaCreatedPerDrive = opponentDrives > 0 ? -n("opponentTurnoverEpaSum") / opponentDrives : null;

  const penaltyRate = safeRate(n("offensivePenalties"), offensiveDrives);
  const penaltyYardsPerDrive = safeRate(n("offensivePenaltyYards"), offensiveDrives);
  const penaltiesDrawnRate = safeRate(n("penaltiesDrawn"), offensiveDrives);
  const penaltyYardsDrawnPerDrive = safeRate(n("penaltyYardsDrawn"), offensiveDrives);
  const penaltiesForcedRate = safeRate(n("penaltiesForced"), opponentDrives);
  const penaltyYardsForcedPerDrive = safeRate(n("penaltyYardsForced"), opponentDrives);
  const defensivePenaltyRate = safeRate(n("defensivePenalties"), opponentDrives);
  const defensivePenaltyYardsPerDrive = safeRate(n("defensivePenaltyYards"), opponentDrives);

  return {
    turnoverRate,
    intRate,
    lostFumbleRate,
    turnoverEpaLostPerGame,
    turnoverEpaLostPerDrive,
    takeawayRate,
    intRateForced,
    fumbleRecoveryRate,
    turnoverEpaCreatedPerGame,
    turnoverEpaCreatedPerDrive,
    turnoverRateMargin: diff(takeawayRate, turnoverRate),
    intRateMargin: diff(intRateForced, intRate),
    fumbleRateMargin: diff(fumbleRecoveryRate, lostFumbleRate),
    turnoverEpaMarginPerGame: diff(turnoverEpaCreatedPerGame, turnoverEpaLostPerGame),
    turnoverEpaMarginPerDrive: diff(turnoverEpaCreatedPerDrive, turnoverEpaLostPerDrive),
    penaltyRate,
    penaltyYardsPerDrive,
    penaltiesDrawnRate,
    penaltyYardsDrawnPerDrive,
    penaltiesForcedRate,
    penaltyYardsForcedPerDrive,
    defensivePenaltyRate,
    defensivePenaltyYardsPerDrive,
    offPenaltyRateMargin: diff(penaltiesDrawnRate, penaltyRate),
    offPenaltyYardsMargin: diff(penaltyYardsDrawnPerDrive, penaltyYardsPerDrive),
    defPenaltyRateMargin: diff(penaltiesForcedRate, defensivePenaltyRate),
    defPenaltyYardsMargin: diff(penaltyYardsForcedPerDrive, defensivePenaltyYardsPerDrive),
  };
}
