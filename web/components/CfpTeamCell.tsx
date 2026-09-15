import TeamLink from "./TeamLink";
import { cfpCellClass, cfpLabel, cfpModifier, cfpTitle, type CfpStatus } from "@/lib/cfp";

function CfpBadgeIcon({ status }: { status: CfpStatus }) {
  if (status === "champion") {
    return (
      <svg className="cfp-badge__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3.2 7.2 7.5 11 12 4.2 16.5 11l4.3-3.8-2 11.6H5.2L3.2 7.2Zm2.8 13h12v1.6H6v-1.6Z" fill="currentColor" />
      </svg>
    );
  }

  if (status === "runnerUp") {
    return (
      <svg className="cfp-badge__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 3h10v3h3v2.1c0 3-1.7 5.1-4.7 5.8A5.3 5.3 0 0 1 13 15.7V19h4v2H7v-2h4v-3.3a5.3 5.3 0 0 1-2.3-1.8C5.7 13.2 4 11.1 4 8.1V6h3V3Zm10 5V6h1v2.1c0 1.5-.6 2.6-1.8 3.2.5-1 .8-2.1.8-3.3ZM6 8.1V8h1c0 1.2.3 2.3.8 3.3C6.6 10.7 6 9.6 6 8.1Z" fill="currentColor" />
      </svg>
    );
  }

  if (status === "participant") {
    return (
      <svg className="cfp-badge__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5.2 18.8c-2.8-2.8-1.5-8.5 2.9-12.9 4.4-4.4 10.1-5.7 12.9-2.9 2.8 2.8 1.5 8.5-2.9 12.9-4.4 4.4-10.1 5.7-12.9 2.9Zm3.9-9.7 5.8 5.8m-4.1-7.5 1.4 1.4m-.1 1.8 1.4 1.4m-.1 1.8 1.4 1.4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  return null;
}

// Shared team-name cell for Ratings/Advanced/Exploratory. CFP teams get an
// inset status card with the team identity on the left and a compact status
// badge on the right; non-CFP teams retain the standard table markup exactly.
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
      {label && modifier ? (
        <div className="team-cell-stack team-cell-stack--cfp">
          <div className="cfp-team-copy">
            <TeamLink team={team} teamId={teamId} slug={slug} />
            <span className="team-conf-label">{conf}</span>
          </div>
          <span className={`cfp-badge cfp-badge--${modifier}`}>
            <CfpBadgeIcon status={status} />
            <span className="cfp-badge__text">{label}</span>
          </span>
        </div>
      ) : (
        <div className="team-cell-stack">
          <TeamLink team={team} teamId={teamId} slug={slug} />
          <span className="team-conf-label">{conf}</span>
        </div>
      )}
    </td>
  );
}
