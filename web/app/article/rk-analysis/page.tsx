import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";

export const metadata = {
  title: "What Turnovers Actually Cost: PPA/Play Before and After | LEILA Ratings",
  description:
    "We pulled every turnover from three Week 2 classics -- Michigan-Oklahoma, Alabama-Kentucky, and Texas-Ohio State -- and measured exactly how much each one swung a team's PPA per play.",
  robots: { index: false, follow: false },
};

type TurnoverPlay = {
  qtrClock: string;
  team: string;
  description: string;
  value: number;
  defensiveTd?: boolean;
};

type TeamSwing = {
  team: string;
  turnovers: number;
  without: number;
  withTurnovers: number;
};

const TEAM_IDS: Record<string, number> = {
  Michigan: 130,
  Oklahoma: 201,
  Alabama: 333,
  Kentucky: 96,
  Texas: 251,
  "Ohio State": 194,
};

const SCALE_MIN = -0.2;
const SCALE_MAX = 0.4;
const SCALE_RANGE = SCALE_MAX - SCALE_MIN;
const ZERO_PCT = ((0 - SCALE_MIN) / SCALE_RANGE) * 100;

function barMetrics(value: number) {
  const clamped = Math.max(SCALE_MIN, Math.min(SCALE_MAX, value));
  const widthPct = (Math.abs(clamped) / SCALE_RANGE) * 100;
  const tone: "up" | "down" = clamped >= 0 ? "up" : "down";
  const left = tone === "up" ? ZERO_PCT : ZERO_PCT - widthPct;
  return { left, width: widthPct, tone };
}

function TeamLogo({ team, size = 20 }: { team: string; size?: number }) {
  const teamId = TEAM_IDS[team];
  if (!teamId) return null;
  return (
    // Server Component: no onError fallback here (that needs a client
    // component). Fine for this article's fixed, known-good set of six
    // team IDs.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className="ppa-team-logo"
      src={logoUrl(teamId)}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
    />
  );
}

function PpaChip({ value, decimals = 2, small }: { value: number; decimals?: number; small?: boolean }) {
  const tone = value >= 0 ? "pos" : "neg";
  return (
    <span className={`ppa-chip ppa-chip--${tone}${small ? " ppa-chip--sm" : ""}`}>
      {value >= 0 ? "+" : ""}
      {value.toFixed(decimals)}
    </span>
  );
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: "up" | "down" }) {
  return (
    <div className={`article-stat${tone ? ` article-stat--${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function MatchupStrip({ teamA, teamB }: { teamA: string; teamB: string }) {
  return (
    <div className="ppa-matchup-strip">
      <TeamLogo team={teamA} size={40} />
      <span className="ppa-matchup-strip__vs">vs</span>
      <TeamLogo team={teamB} size={40} />
    </div>
  );
}

function Callout({ tone, children }: { tone?: "up" | "down"; children: React.ReactNode }) {
  return <div className={`article-callout${tone ? ` article-callout--${tone}` : ""}`}>{children}</div>;
}

function PpaBar({ value }: { value: number }) {
  const { left, width, tone } = barMetrics(value);
  return (
    <div className="ppa-bar-track">
      <span className="ppa-bar-zero" style={{ left: `${ZERO_PCT}%` }} />
      <span
        className="ppa-bar-fill"
        style={{
          left: `${left}%`,
          width: `${width}%`,
          background: tone === "up" ? "var(--color-up)" : "var(--color-down)",
        }}
      />
    </div>
  );
}

function PpaSwingChart({ teams }: { teams: TeamSwing[] }) {
  return (
    <div className="ppa-swing-chart">
      {teams.map((t) => {
        const delta = t.withTurnovers - t.without;
        return (
          <div className="ppa-swing-row" key={t.team}>
            <div className="ppa-swing-row__team">
              <div className="ppa-swing-row__team-label">
                <TeamLogo team={t.team} size={24} />
                <span>{t.team}</span>
              </div>
              <span className="ppa-swing-row__team-sub">
                {t.turnovers} turnover{t.turnovers === 1 ? "" : "s"}
              </span>
            </div>
            <div className="ppa-swing-row__bars">
              <div className="ppa-swing-row__bar-line">
                <span className="ppa-swing-row__bar-tag">W/o TO</span>
                <PpaBar value={t.without} />
                <PpaChip value={t.without} decimals={3} small />
              </div>
              <div className="ppa-swing-row__bar-line">
                <span className="ppa-swing-row__bar-tag">W/ TO</span>
                <PpaBar value={t.withTurnovers} />
                <PpaChip value={t.withTurnovers} decimals={3} small />
              </div>
            </div>
            <div className="ppa-swing-row__delta">
              <span className="ppa-swing-row__delta-arrow">{delta >= 0 ? "▲" : "▼"}</span>
              <PpaChip value={delta} decimals={3} small />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TurnoverTable({ plays }: { plays: TurnoverPlay[] }) {
  return (
    <div className="article-table-wrap">
      <table className="article-table article-table--wide">
        <thead>
          <tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>PPA on the play</th></tr>
        </thead>
        <tbody>
          {plays.map((p) => {
            const isDefensiveTd = Boolean(p.defensiveTd);
            const isBackbreaker = p.value <= -5;
            return (
              <tr key={`${p.qtrClock}-${p.team}-${p.description}`}>
                <td>{p.qtrClock}</td>
                <td className="ppa-team-cell">
                  <TeamLogo team={p.team} />
                  <span>{p.team}</span>
                </td>
                <td>
                  {p.description}
                  {isDefensiveTd && <span className="ppa-td-pill">Defensive TD</span>}
                  {isBackbreaker && <span className="ppa-backbreaker">Back-breaker</span>}
                </td>
                <td><PpaChip value={p.value} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const MICHIGAN_OKLAHOMA_PLAYS: TurnoverPlay[] = [
  { qtrClock: "Q2, 13:32", team: "Oklahoma", description: "Mateer completes to Livingstone for 8 yards, fumbles, recovered by Michigan (Bowles)", value: -3.34 },
  { qtrClock: "Q4, 8:49", team: "Oklahoma", description: "Mateer intercepted by J.Hill, returned 24 yards", value: 0.23 },
];
const MICHIGAN_OKLAHOMA_SWING: TeamSwing[] = [
  { team: "Michigan", turnovers: 0, without: 0.101, withTurnovers: 0.064 },
  { team: "Oklahoma", turnovers: 2, without: 0.083, withTurnovers: 0.025 },
];

const ALABAMA_KENTUCKY_PLAYS: TurnoverPlay[] = [
  { qtrClock: "Q1, 10:15", team: "Alabama", description: "Russell intercepted by Humphrey-Grace, returned 2 yards", value: -6.61, defensiveTd: true },
  { qtrClock: "Q1, 7:17", team: "Alabama", description: "Russell sacked, fumbles, recovered by Kentucky (C.Works)", value: -0.96 },
  { qtrClock: "Q1, 6:44", team: "Kentucky", description: "Minchey intercepted by L.Metz, returned 34 yards", value: -7.23, defensiveTd: true },
  { qtrClock: "Q2, 0:55", team: "Alabama", description: "Russell intercepted by J.Castell", value: 0.02 },
  { qtrClock: "Q3, 5:47", team: "Kentucky", description: "Minchey sacked, fumbles, recovered by Alabama (I.Faga)", value: -0.51 },
  { qtrClock: "Q4, 2:42", team: "Kentucky", description: "Patterson rushes for 3 yards, fumbles, recovered by Alabama (I.Taylor)", value: -1.66 },
];
const ALABAMA_KENTUCKY_SWING: TeamSwing[] = [
  { team: "Alabama", turnovers: 3, without: 0.353, withTurnovers: 0.190 },
  { team: "Kentucky", turnovers: 3, without: 0.001, withTurnovers: -0.168 },
];

const TEXAS_OHIOSTATE_PLAYS: TurnoverPlay[] = [
  { qtrClock: "Q1, 14:49", team: "Texas", description: "Manning completes to R.Brown, fumbles, recovered by Ohio State (J.Timmons)", value: -0.73 },
  { qtrClock: "Q1, 10:15", team: "Texas", description: "Manning intercepted by J.McClain, returned 7 yards", value: -2.05 },
  { qtrClock: "Q4, 0:17", team: "Ohio State", description: "Sayin intercepted by G.Littleton, final play of the game", value: 0.14 },
];
const TEXAS_OHIOSTATE_SWING: TeamSwing[] = [
  { team: "Texas", turnovers: 2, without: 0.193, withTurnovers: 0.163 },
  { team: "Ohio State", turnovers: 1, without: 0.148, withTurnovers: 0.148 },
];

export default function RkAnalysisArticle() {
  return (
    <>
      <a className="skip-link" href="#articleContent">Skip to article</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="articleContent" className="container article-main">
        <header className="article-hero">
          <span className="eyebrow">Game Analysis</span>
          <h1>What Turnovers Actually Cost: PPA/Play Before and After</h1>
          <p className="article-dek">
            PPA (predicted points added) is CFBD&rsquo;s play-level efficiency model &mdash; the same kind of metric
            most sites, including this one, call &ldquo;EPA.&rdquo; We took three Week 2 classics &mdash;
            Michigan-Oklahoma, Alabama-Kentucky, and Texas-Ohio State &mdash; and measured each team&rsquo;s PPA per
            play two ways: with every turnover included, and with the turnovers stripped out. The gap between those
            two numbers is exactly how much a giveaway (or a takeaway) is worth beyond what the scoreboard shows.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <div className="ppa-chart-legend">
          <span><i className="up" /> Positive PPA/play</span>
          <span><i className="down" /> Negative PPA/play</span>
          <span>Every bar below is scaled from -0.20 to +0.40 PPA/play, so you can compare games directly.</span>
        </div>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 1</span>
            <h2>Michigan 17, Oklahoma 10</h2>
            <MatchupStrip teamA="Michigan" teamB="Oklahoma" />
          </div>
          <p>
            Oklahoma turned it over twice; Michigan turned it over zero times &mdash; but Michigan still fumbled
            twice and recovered both themselves, and those plays carry real PPA value even when possession never
            changes hands.
          </p>
          <TurnoverTable plays={MICHIGAN_OKLAHOMA_PLAYS} />
          <PpaSwingChart teams={MICHIGAN_OKLAHOMA_SWING} />
          <Callout tone="down">
            Oklahoma&rsquo;s process looked close to Michigan&rsquo;s on clean snaps &mdash; 0.083 to 0.101. Count
            the turnovers and the gap more than doubles, to 0.025 versus 0.064.
          </Callout>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 2</span>
            <h2>Alabama 45, Kentucky 17</h2>
            <MatchupStrip teamA="Alabama" teamB="Kentucky" />
          </div>
          <p>
            Six total turnovers in this one &mdash; Alabama gave it away three times, Kentucky three times, and two
            of the six went the distance for defensive touchdowns.
          </p>
          <TurnoverTable plays={ALABAMA_KENTUCKY_PLAYS} />
          <PpaSwingChart teams={ALABAMA_KENTUCKY_SWING} />
          <Callout tone="down">
            Before turnovers, Kentucky&rsquo;s offense looked like a coin flip at 0.001 PPA/play. After, they&rsquo;re
            underwater at -0.168 &mdash; the largest swing of any team in these three games. Alabama gave the ball
            away just as many times and still finished at a strong +0.190.
          </Callout>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 3</span>
            <h2>Texas 24, Ohio State 23</h2>
            <MatchupStrip teamA="Texas" teamB="Ohio State" />
          </div>
          <p>
            Texas turned it over twice, Ohio State once &mdash; on the final play of the game, with the outcome
            already decided.
          </p>
          <TurnoverTable plays={TEXAS_OHIOSTATE_PLAYS} />
          <PpaSwingChart teams={TEXAS_OHIOSTATE_SWING} />
          <Callout>
            One low-value, game-ending pick doesn&rsquo;t move Ohio State&rsquo;s number at all. Texas&rsquo;s two
            first-half giveaways do &mdash; pulling them from 0.193 down to 0.163, and tightening the gap between
            these two teams.
          </Callout>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Bigger Picture</span>
            <h2>Turnovers moved every offense&rsquo;s number &mdash; just not by the same amount</h2>
          </div>
          <div className="article-stat-grid">
            <Stat value="11" label="Total turnovers across the three games" />
            <Stat value="-22.7" label="Combined PPA value on those 11 plays" tone="down" />
            <Stat value="-0.169" label="Kentucky's swing, the largest of any team" tone="down" />
            <Stat value="0.000" label="Ohio State's swing, the smallest of any team" />
          </div>
          <p>
            The size of the swing depends on two things: how many turnovers a team had, and how costly each one was.
            Kentucky and Alabama each gave the ball away three times, but Kentucky&rsquo;s turnovers &mdash; two
            defensive touchdowns against them &mdash; were far more damaging than Alabama&rsquo;s, so their PPA/play
            swung more even though the raw turnover count was identical. Ohio State&rsquo;s single turnover came on
            a meaningless final snap and barely moved the needle at all.
          </p>
          <p>
            &ldquo;PPA/play without turnovers&rdquo; is useful for isolating how a team executed on the plays that
            stayed alive, but it can flatter an offense that got bailed out by turnover luck, or undersell one that
            was otherwise playing well before the ball came loose. The figures on LEILA&rsquo;s Advanced page already
            include every turnover, for exactly this reason.
          </p>
        </section>

        <section className="article-section article-actions">
          <div>
            <span className="eyebrow">Keep Reading</span>
            <h2>More on how LEILA builds its numbers</h2>
            <p>
              For the mechanism behind why early-season ratings shouldn&rsquo;t be fully trusted yet, see our Week 4
              networks piece. For the full breakdown of every rating on the site, see Methodology.
            </p>
          </div>
          <div className="article-actions__links">
            <Link href="/article/waitingonranks">Read: Nobody Knows Who&rsquo;s Good Yet →</Link>
            <Link href="/methodology">How LEILA&rsquo;s ratings work →</Link>
          </div>
        </section>

        <p className="article-footnote">
          Turnover counts are CFBD&rsquo;s official box score (<code>/games/teams</code>, <code>turnovers</code>{" "}
          category) for gameIds 401856679, 401856674, and 401856682 (Week 2, 2026); each was matched to its
          play-by-play row by hand. PPA/play figures use CFBD&rsquo;s play-level predicted-points-added model and
          match the live figures on LEILA&rsquo;s Advanced page.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}
