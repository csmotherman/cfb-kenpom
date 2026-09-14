import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "EPA/Play Already Hides Your Turnovers | LEILA Ratings",
  description:
    "We tried to compare EPA per play with vs. without turnovers for three Week 2 classics -- Texas-Ohio State, Alabama-Kentucky, Michigan-Oklahoma -- and found that standard EPA accounting already excludes almost every one of them, for a structural reason that has nothing to do with methodology choices.",
  robots: { index: false, follow: false },
};

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="article-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export default function RkAnalysisArticle() {
  return (
    <>
      <a className="skip-link" href="#articleContent">Skip to article</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="articleContent" className="container article-main">
        <header className="article-hero">
          <span className="eyebrow">Data Investigation</span>
          <h1>EPA/Play Already Hides Almost All of Your Turnovers</h1>
          <p className="article-dek">
            We set out to compare each team&rsquo;s EPA per play with turnovers included against the published number
            (which excludes them) in three Week 2 classics: Texas-Ohio State, Alabama-Kentucky, and Michigan-Oklahoma.
            The comparison turned out to be far harder than it should be &mdash; not because of a methodology choice
            we made, but because of how play-by-play data represents a turnover in the first place. Here&rsquo;s what
            we found, game by game.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            EPA (expected points added) per play is the backbone of most modern offensive and defensive ratings,
            including LEILA&rsquo;s own. The number CFBD publishes for a play &mdash; and the number every site
            downstream of it, including this one, sums up into &ldquo;EPA/play&rdquo; &mdash; comes from CFBD&rsquo;s
            own play-level model. Our own eligibility rule for counting a play toward that average is simple: it has
            to be a real offensive scrimmage snap, not a penalty or no-play, and CFBD has to have actually produced a
            number for it.
          </p>
          <p>
            That rule turns out to already exclude almost every turnover in the games we checked &mdash; not because
            we (or anyone) decided turnovers shouldn&rsquo;t count, but because the play-by-play feed logs a
            turnover&rsquo;s <em>return</em> (the interception return, the fumble recovery) as its own separate play,
            and that return play is flagged as a non-offensive snap. The original throw or handoff that actually lost
            the ball often carries no separate EPA value of its own once the return is logged this way. We went game
            by game to see exactly how much of each result was going untouched.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 1</span>
            <h2>Michigan 17, Oklahoma 10</h2>
          </div>
          <p>
            Four plays in this game were flagged as turnovers: two Michigan fumbles (recovered by Michigan both
            times &mdash; no ball actually changed hands), one Oklahoma fumble Michigan recovered, and one Oklahoma
            interception return. <strong>All four are logged as return/recovery plays, not offensive snaps</strong>,
            so none of them carry a play-level EPA value that counts toward either team&rsquo;s number. Combined,
            those four plays represent about <strong>-5.0 points</strong> of real CFBD-modeled value that simply
            never touches either team&rsquo;s published EPA/play.
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Offense EPA/play</th><th>Defense EPA/play allowed</th></tr></thead>
              <tbody>
                <tr><td>Michigan</td><td>0.101</td><td>0.083</td></tr>
                <tr><td>Oklahoma</td><td>0.083</td><td>0.101</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            There is no &ldquo;with turnovers&rdquo; column here because there&rsquo;s nothing to add. These are the
            same numbers either way &mdash; a clean, if slightly unsatisfying, illustration of the underlying
            problem: this comparison genuinely does not exist for every game.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 2</span>
            <h2>Alabama 45, Kentucky 17</h2>
          </div>
          <p>
            This is where it gets interesting. Ten plays were flagged as turnovers &mdash; the richest case of the
            three &mdash; but only <strong>one</strong> of them turned out to be both a genuine change of possession
            <em>and</em> a play with a real, countable EPA value: a low-stakes late Alabama interception (+0.02 EPA,
            barely worth anything on its own). The other nine split into two very different problems.
          </p>
          <p>
            <strong>Six were invisible</strong> the same way as in the Michigan-Oklahoma game &mdash; logged as
            return/recovery plays, carrying real CFBD values that never reach either team&rsquo;s number. That
            group includes both of this game&rsquo;s backbreaking momentum swings: Alabama&rsquo;s
            interception-return touchdown (-6.6 EPA) and Kentucky&rsquo;s own interception-return touchdown
            (-7.2 EPA) against them. Two of the biggest plays of the game, by CFBD&rsquo;s own model, and neither
            one is in the published EPA/play for either offense.
          </p>
          <p>
            <strong>Two were false positives</strong> &mdash; a Kentucky fumble and an Alabama fumble that were each
            recovered by the team that fumbled. No possession changed on either play, but both are flagged as
            turnovers anyway, and our own eligibility rule excludes them along with everything else that carries
            that flag. That&rsquo;s arguably a mistake in the other direction: Kentucky&rsquo;s fumble came on a play
            that had just picked up a first down (+0.92 EPA) before the ball came loose, and excluding it drags an
            already-poor offensive day down further than it should be.
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Published Off. EPA/play</th><th>+ the one genuine turnover</th><th>+ the non-turnover fumble too</th></tr></thead>
              <tbody>
                <tr><td>Alabama</td><td>0.353</td><td>0.347</td><td>0.330</td></tr>
                <tr><td>Kentucky</td><td>0.001</td><td className="hi">&mdash;</td><td>0.016</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Even fully corrected, Alabama&rsquo;s real advantage barely moves (0.353 &rarr; 0.330) &mdash; the one
            genuine turnover was nearly free, and the fumble that gets added back only nudges the number down a
            little further. Kentucky&rsquo;s day looks a hair less bleak once you stop excluding a first-down play
            just because the ball came loose afterward (0.001 &rarr; 0.016), but this was a 45-17 game and the
            per-play numbers say exactly what the scoreboard already told you: Alabama was simply the better team on
            most snaps, turnovers or not.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 3</span>
            <h2>Texas 24, Ohio State 23</h2>
          </div>
          <p>
            A one-point game, decided late, and turnovers get more interesting the closer the final score. Five
            plays were flagged. Only <strong>one</strong> is countable: Ohio State&rsquo;s interception on the final
            snap of the game (+0.145 EPA) &mdash; real, but happening after the outcome was essentially decided, so
            it barely moves anything.
          </p>
          <p>
            The other four are invisible, and one of them actually matters a lot for how this specific game is
            remembered: a first-half Texas interception that set up an Ohio State scoring chance, in a game Texas
            won by a single point. That play doesn&rsquo;t exist in either team&rsquo;s EPA/play number at all
            &mdash; not because it wasn&rsquo;t costly, but because it was logged as a return, the same structural
            gap as every other missing play in this piece.
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Offense EPA/play</th><th>Defense EPA/play allowed</th></tr></thead>
              <tbody>
                <tr><td>Texas</td><td>0.193</td><td>0.148</td></tr>
                <tr><td>Ohio State</td><td>0.148</td><td>0.193</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            In a game this close, the one turnover we <em>can</em> measure explains almost none of why it was close.
            The one we can&rsquo;t measure &mdash; Texas&rsquo;s own first-half pick &mdash; is a much better
            candidate, and it&rsquo;s simply not part of the accounting.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">What This Actually Means</span>
            <h2>The comparison you&rsquo;d expect isn&rsquo;t really possible yet</h2>
          </div>
          <div className="article-stat-grid">
            <Stat value="19" label="Total turnover-flagged plays across all 3 games" />
            <Stat value="2" label="That were genuine, possession-changing, AND EPA-measurable" />
            <Stat value="13" label="Invisible to EPA entirely (logged as return/recovery plays)" />
            <Stat value="3" label="False positives -- flagged as turnovers with no possession change" />
          </div>
          <p>
            Going in, we expected to find turnovers quietly inflating or deflating some team&rsquo;s process grade
            &mdash; the standard &ldquo;this team&rsquo;s EPA looks better/worse than they actually played&rdquo;
            story. That&rsquo;s not really what we found. What we found is that <strong>the published number is
            already an &ldquo;EPA without turnovers&rdquo; number, for essentially every game</strong> &mdash; not
            because anyone chose to strip them out, but because the way play-by-play data logs a turnover&rsquo;s
            return leaves no EPA-eligible row for most of them to attach to. Pick-sixes, fumble-return touchdowns,
            and the returns that set up short fields all happened, and all show up in the score and the box score
            &mdash; just not in the per-play average.
          </p>
          <p>
            The smaller, second finding is worth remembering too: not every play flagged as a turnover was actually
            one. A fumble a team recovers itself isn&rsquo;t a turnover in any meaningful football sense, but it
            still carries the same flag as one that ends a drive &mdash; and that flag is what our (and most
            everyone&rsquo;s) EPA eligibility rule keys off. Two of the three &ldquo;turnovers&rdquo; in the
            Alabama-Kentucky game fell into that trap.
          </p>
          <p>
            None of this changes LEILA&rsquo;s published Adj. Off/Adj. Def numbers &mdash; those are built from a
            season&rsquo;s worth of possessions, not one game&rsquo;s handful of turnovers, and that volume already
            drowns out the effect of a single missing play. But it&rsquo;s a real, concrete example of why we&rsquo;d
            rather show our work than hand you a number that looks more complete than it is.
          </p>
        </section>

        <section className="article-section article-actions">
          <div>
            <span className="eyebrow">Keep Reading</span>
            <h2>More on how LEILA builds its numbers</h2>
            <p>
              For the mechanism behind why early-season ratings (turnovers or not) shouldn&rsquo;t be fully trusted
              yet, see our Week 4 networks piece. For the full breakdown of every rating on the site, see Methodology.
            </p>
          </div>
          <div className="article-actions__links">
            <Link href="/article/waitingonranks">Read: Nobody Knows Who&rsquo;s Good Yet →</Link>
            <Link href="/methodology">How LEILA&rsquo;s ratings work →</Link>
          </div>
        </section>

        <p className="article-footnote">
          All figures are LEILA Ratings&rsquo; own analysis of CFBD&rsquo;s canonical Week 2, 2026 play-by-play for
          these three games (gameIds 401856679, 401856674, 401856682), using the same offensive-EPA eligibility rule
          published site-wide (a real scrimmage snap, an offensive play, a non-null CFBD PPA value, no penalty/no-play
          modifier). &ldquo;Genuine turnover&rdquo; classification was done by hand, checking whether the offense of
          the following play/drive actually changed teams, since CFBD&rsquo;s own <code>isTurnover</code> flag marks
          some fumbles a team recovered itself the same way it marks a real change of possession.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}
