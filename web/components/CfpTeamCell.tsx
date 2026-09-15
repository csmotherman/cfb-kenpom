import TeamLink from "./TeamLink";
import { cfpCellClass, cfpLabel, cfpModifier, cfpTitle, type CfpStatus } from "@/lib/cfp";

// Shared team-name cell for Ratings/Advanced/Exploratory: a <td> with the
// standard team-cell-stack markup, plus a CFP field/champion/runner-up box
// and label when `status` is set. One component so all three tables stay
// visually and behaviorally identical instead of drifting apart.
export default function CfpTeamCell({
  team,
  teamId,
  slug,
  conf,
  status,
  year,
  className = "team-cell",
}: {
  team: string;
  teamId: number;
  slug: string;
  conf: string;
  status: CfpStatus;
  year: string;
  className?: string;
}) {
  const label = cfpLabel(status);
  const modifier = cfpModifier(status);
  return (
    <td className={cfpCellClass(status, className)} title={cfpTitle(status, year)}>
      <div className="team-cell-stack">
        <TeamLink team={team} teamId={teamId} slug={slug} />
        <span className="team-conf-label">{conf}</span>
        {label ? <span className={`cfp-badge cfp-badge--${modifier}`}>{label}</span> : null}
      </div>
    </td>
  );
}
