import type { CfpSeasonResult } from "./types";

export type CfpStatus = "champion" | "runnerUp" | "participant" | undefined;

// teamId -> status for a season's CFP results. null/undefined input (not
// yet fetched, or that season's CFP hasn't been played) just yields an
// empty map -- every lookup falls through to `undefined` (no box).
export function buildCfpStatusMap(results: CfpSeasonResult | null | undefined): Map<number, CfpStatus> {
  const byTeamId = new Map<number, CfpStatus>();
  if (!results) return byTeamId;
  for (const team of results.participants) byTeamId.set(team.teamId, "participant");
  if (results.runnerUp) byTeamId.set(results.runnerUp.teamId, "runnerUp");
  if (results.champion) byTeamId.set(results.champion.teamId, "champion");
  return byTeamId;
}

export function cfpModifier(status: CfpStatus): string | null {
  if (status === "champion") return "champion";
  if (status === "runnerUp") return "runner-up";
  if (status === "participant") return "participant";
  return null;
}

export function cfpCellClass(status: CfpStatus, baseClass = "team-cell"): string {
  const modifier = cfpModifier(status);
  return modifier ? `${baseClass} team-cell--cfp team-cell--cfp-${modifier}` : baseClass;
}

export function cfpLabel(status: CfpStatus): string | null {
  if (status === "champion") return "CFP Champion";
  if (status === "runnerUp") return "CFP Runner-Up";
  if (status === "participant") return "CFP";
  return null;
}

export function cfpTitle(status: CfpStatus, year: string): string | undefined {
  if (status === "champion") return `${year} National Champion`;
  if (status === "runnerUp") return `${year} National Championship runner-up`;
  if (status === "participant") return `${year} College Football Playoff field`;
  return undefined;
}
