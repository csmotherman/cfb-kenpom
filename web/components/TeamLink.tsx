import Link from "next/link";
import { logoUrl, teamCode } from "@/lib/teamCode";

export default function TeamLink({ team, teamId, slug }: { team: string; teamId: number; slug: string }) {
  return (
    <Link href={`/team/${encodeURIComponent(slug)}`} className="team-link">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="team-logo"
        src={logoUrl(teamId)}
        alt=""
        loading="lazy"
        decoding="async"
        onError={(e) => {
          (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
        }}
      />
      <span className="team-name">{team}</span>
      <span className="team-code" aria-hidden="true">
        {teamCode(team)}
      </span>
    </Link>
  );
}
