import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "EPA/Play Already Hides Your Turnovers | LEILA Ratings",
  description:
    "We audited every turnover in three Week 2 classics -- Texas-Ohio State, Alabama-Kentucky, Michigan-Oklahoma -- against CFBD's official box score, then checked how many actually show up in EPA per play. Of 11 real turnovers, only 2 do.",
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
            The first pass at this got the turnover count wrong, so we redid it against CFBD&rsquo;s official box
            score, play by play, until every number below matched. Here&rsquo;s what actually happened.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            EPA (expected points added) per play is the backbone of most modern offensive and defensive ratings,
            including LEILA&rsquo;s own. Our eligibility rule for counting a play toward that average is simple: it
            has to be a real offensive scrimmage snap, not a penalty or no-play, and CFBD has to have actually
            produced a value for it.
          </p>
          <p>
            That rule turns out to exclude almost every turnover &mdash; not because of a methodology choice, but
            because the play-by-play feed logs a turnover&rsquo;s <em>return</em> (the interception return, the
            fumble recovery) as its own separate play, flagged as a non-offensive snap. The original throw or
            handoff that actually lost the ball usually carries no separate EPA value once the return is logged this
            way.
          </p>
          <p>
            <strong>We verified every turnover below against CFBD&rsquo;s official box score</strong> (the{" "}
            <code>/games/teams</code> endpoint&rsquo;s <code>turnovers</code> stat) before counting it, and read the
            actual play-by-play text for each one rather than trusting CFBD&rsquo;s own structured labels &mdash;
            which turned out to matter. More on that at the end.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 1</span>
            <h2>Michigan 17, Oklahoma 10</h2>
          </div>
          <p>
            Box score: <strong>Oklahoma 2 turnovers, Michigan 0.</strong> Both of Oklahoma&rsquo;s are logged as
            return/recovery plays rather than offensive snaps, so <strong>neither has a usable EPA value</strong>{" "}
            &mdash; the published EPA/play for both teams is identical whether you count turnovers or not, because
            there&rsquo;s nothing to add.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>EPA-visible?</th></tr></thead>
              <tbody>
                <tr><td>Q2, 13:32</td><td>Oklahoma</td><td>Mateer completes to Livingstone for 8 yards, fumbles, recovered by Michigan (Bowles)</td><td>-3.34</td><td>No</td></tr>
                <tr><td>Q4, 8:49</td><td>Oklahoma</td><td>Mateer intercepted by J.Hill, returned 24 yards</td><td>+0.23</td><td>No</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Offense EPA/play</th><th>Defense EPA/play allowed</th></tr></thead>
              <tbody>
                <tr><td>Michigan</td><td>0</td><td>0.101</td><td>0.083</td></tr>
                <tr><td>Oklahoma</td><td>2</td><td>0.083</td><td>0.101</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Michigan also fumbled twice, but recovered both themselves &mdash; no possession changed, so the box
            score correctly shows 0 turnovers for them despite the raw play-by-play flagging those two fumbles the
            same way it flags a real one.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 2</span>
            <h2>Alabama 45, Kentucky 17</h2>
          </div>
          <p>
            Box score: <strong>Alabama 3 turnovers (2 interceptions, 1 fumble), Kentucky 3 (1 interception, 2
            fumbles).</strong> This is the game our first pass got wrong &mdash; we initially found only one
            &ldquo;genuine&rdquo; turnover between both teams, because two of the real fumbles were logged by CFBD
            with a structured label that says &ldquo;Fumble Recovery (Own)&rdquo; while the actual play text says
            the <em>opponent</em> recovered it. Trusting the label instead of the text undercounted both teams.
            Corrected, here&rsquo;s every turnover and whether it reaches EPA:
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>EPA-visible?</th></tr></thead>
              <tbody>
                <tr><td>Q1, 10:15</td><td>Alabama</td><td>Russell intercepted by Humphrey-Grace, returned 2 yards for a TOUCHDOWN</td><td>-6.61</td><td>No</td></tr>
                <tr><td>Q1, 7:17</td><td>Alabama</td><td>Russell sacked, fumbles, recovered by Kentucky (C.Works)</td><td>-0.96</td><td>No</td></tr>
                <tr><td>Q1, 6:44</td><td>Kentucky</td><td>Minchey intercepted by L.Metz, returned 34 yards for a TOUCHDOWN</td><td>-7.23</td><td>No</td></tr>
                <tr><td>Q2, 0:55</td><td>Alabama</td><td>Russell intercepted by J.Castell</td><td>+0.02</td><td className="hi">Yes</td></tr>
                <tr><td>Q3, 5:47</td><td>Kentucky</td><td>Minchey sacked, fumbles, recovered by Alabama (I.Faga)</td><td>-0.51</td><td>No</td></tr>
                <tr><td>Q4, 2:42</td><td>Kentucky</td><td>Patterson rushes for 3 yards, fumbles, recovered by Alabama (I.Taylor)</td><td>-1.66</td><td>No</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Five of six real turnovers in this game &mdash; including both pick-six returns, worth a combined
            -13.8 points by CFBD&rsquo;s own model &mdash; never touch either offense&rsquo;s published EPA/play.
            Only Alabama&rsquo;s late interception is countable, and it barely moves anything:
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Published Off. EPA/play</th><th>+ the one EPA-visible turnover</th></tr></thead>
              <tbody>
                <tr><td>Alabama</td><td>3</td><td>0.353</td><td>0.347</td></tr>
                <tr><td>Kentucky</td><td>3</td><td>0.001</td><td className="hi">0.001 &mdash; unchanged</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            This was a 45-17 game, and the numbers say why in a way turnovers barely touch: Alabama was simply
            better on most snaps. Its 3 turnovers and Kentucky&rsquo;s 3 turnovers very nearly cancel out on paper
            &mdash; both had 2 interceptions and 1 fumble, give or take &mdash; so removing (or adding) turnovers
            from this specific comparison changes almost nothing about the gap between the two offenses.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 3</span>
            <h2>Texas 24, Ohio State 23</h2>
          </div>
          <p>
            Box score: <strong>Texas 2 turnovers (1 interception, 1 fumble), Ohio State 1 (interception).</strong>{" "}
            A one-point game, and this is the one where the invisible plays actually matter for how the game is
            remembered. Texas fumbled a short pass away on its opening drive (recovered by Ohio State) and threw a
            first-half interception that set up an Ohio State scoring chance &mdash; both logged as return/recovery
            plays, both invisible to EPA. Ohio State&rsquo;s only turnover was a desperation interception on the
            final, game-ending snap, which <em>is</em> EPA-visible (+0.14) but happened after the outcome was
            essentially decided.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>EPA-visible?</th></tr></thead>
              <tbody>
                <tr><td>Q1, 14:49</td><td>Texas</td><td>Manning completes to R.Brown, fumbles, recovered by Ohio State (J.Timmons)</td><td>-0.73</td><td>No</td></tr>
                <tr><td>Q1, 10:15</td><td>Texas</td><td>Manning intercepted by J.McClain, returned 7 yards</td><td>-2.05</td><td>No</td></tr>
                <tr><td>Q4, 0:17</td><td>Ohio State</td><td>Sayin intercepted by G.Littleton, final play of the game</td><td>+0.14</td><td className="hi">Yes</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Offense EPA/play</th><th>Defense EPA/play allowed</th></tr></thead>
              <tbody>
                <tr><td>Texas</td><td>2</td><td>0.193</td><td>0.148</td></tr>
                <tr><td>Ohio State</td><td>1</td><td>0.148</td><td>0.193</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            In a game decided by a single point, the one turnover we <em>can</em> measure explains almost none of
            why it was close. The two we can&rsquo;t &mdash; both of them Texas&rsquo;s &mdash; are much better
            candidates, and neither is part of the accounting.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">What This Actually Means</span>
            <h2>11 real turnovers. 2 show up in EPA.</h2>
          </div>
          <div className="article-stat-grid">
            <Stat value="11" label="Real turnovers across all 3 games, verified against CFBD's box score" />
            <Stat value="2" label="That are EPA-visible on the offense that committed them" />
            <Stat value="9" label="Real turnovers with zero EPA footprint -- including both pick-sixes" />
            <Stat value="-22.9" label="Combined CFBD play value on turnovers that never reach a published number" />
          </div>
          <p>
            The finding isn&rsquo;t &ldquo;turnovers barely mattered in these 3 games&rdquo; &mdash; two of them were
            pick-six touchdowns and a third set up a scoring chance in a one-point game. The finding is that{" "}
            <strong>the published EPA/play number is already much closer to &ldquo;EPA without turnovers&rdquo; than
            most readers would assume</strong>, for a structural reason that has nothing to do with how good or bad
            a team&rsquo;s process actually was.
          </p>
          <p>
            We also want to be direct about our own process here: the first version of this analysis undercounted
            real turnovers in the Alabama-Kentucky game by trusting CFBD&rsquo;s structured{" "}
            <code>playType</code> label (&ldquo;Fumble Recovery (Own)&rdquo; vs. &ldquo;(Opponent)&rdquo;) instead of
            reading the actual play text, which on at least two plays directly contradicted that label. Cross-checking
            every number against the official box score &mdash; not just the play-by-play feed &mdash; is what
            caught it, and it&rsquo;s why every count on this page is now sourced to that box score directly rather
            than to our own play-level classification alone.
          </p>
          <p>
            None of this changes LEILA&rsquo;s published Adj. Off/Adj. Def numbers &mdash; those are built from a
            full season of possessions, not one game&rsquo;s handful of turnovers &mdash; but it&rsquo;s a concrete,
            now-verified example of why we&rsquo;d rather show our work than hand you a number that looks more
            complete than it is.
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
          Turnover counts are CFBD&rsquo;s official box score (<code>/games/teams</code>, <code>turnovers</code>{" "}
          category) for gameIds 401856679, 401856674, and 401856682 (Week 2, 2026). EPA figures use the offensive-EPA
          eligibility rule published site-wide (a real scrimmage snap, an offensive play, a non-null CFBD PPA value,
          no penalty/no-play modifier). Each turnover was matched to its play-by-play row by hand, cross-referencing
          the play text (not CFBD&rsquo;s structured recovery label, which was found to be unreliable on at least two
          plays) against the box score total for that team, so every game&rsquo;s turnover count above reconciles
          exactly with CFBD&rsquo;s own official stat.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}
