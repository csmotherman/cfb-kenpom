import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "What Turnovers Actually Cost: PPA/Play Before and After | LEILA Ratings",
  description:
    "We pulled every turnover from three Week 2 classics -- Michigan-Oklahoma, Alabama-Kentucky, and Texas-Ohio State -- and measured exactly how much each one swung a team's PPA per play.",
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

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 1</span>
            <h2>Michigan 17, Oklahoma 10</h2>
          </div>
          <p>
            Oklahoma turned it over twice; Michigan turned it over zero times &mdash; but Michigan still fumbled
            twice and recovered both themselves, and those plays carry real PPA value even when possession never
            changes hands.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>PPA on the play</th></tr></thead>
              <tbody>
                <tr><td>Q2, 13:32</td><td>Oklahoma</td><td>Mateer completes to Livingstone for 8 yards, fumbles, recovered by Michigan (Bowles)</td><td>-3.34</td></tr>
                <tr><td>Q4, 8:49</td><td>Oklahoma</td><td>Mateer intercepted by J.Hill, returned 24 yards</td><td>+0.23</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Turnovers</th><th>PPA/play without turnovers</th><th>PPA/play with turnovers</th></tr></thead>
              <tbody>
                <tr><td>Michigan</td><td>0</td><td>0.101</td><td>0.064</td></tr>
                <tr><td>Oklahoma</td><td>2</td><td>0.083</td><td>0.025</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Oklahoma&rsquo;s process looks closer to Michigan&rsquo;s once you strip out the giveaways &mdash; 0.083
            to 0.101 is a real but modest gap. Include the turnovers and it widens to 0.025 versus 0.064: Oklahoma&rsquo;s
            two possessions ending in Michigan&rsquo;s hands did roughly as much damage as the rest of the box score
            suggests they should have.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 2</span>
            <h2>Alabama 45, Kentucky 17</h2>
          </div>
          <p>
            Six total turnovers in this one &mdash; Alabama gave it away three times, Kentucky three times, and two
            of the six went the distance for defensive touchdowns.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>PPA on the play</th></tr></thead>
              <tbody>
                <tr><td>Q1, 10:15</td><td>Alabama</td><td>Russell intercepted by Humphrey-Grace, returned 2 yards for a TOUCHDOWN</td><td>-6.61</td></tr>
                <tr><td>Q1, 7:17</td><td>Alabama</td><td>Russell sacked, fumbles, recovered by Kentucky (C.Works)</td><td>-0.96</td></tr>
                <tr><td>Q1, 6:44</td><td>Kentucky</td><td>Minchey intercepted by L.Metz, returned 34 yards for a TOUCHDOWN</td><td>-7.23</td></tr>
                <tr><td>Q2, 0:55</td><td>Alabama</td><td>Russell intercepted by J.Castell</td><td>+0.02</td></tr>
                <tr><td>Q3, 5:47</td><td>Kentucky</td><td>Minchey sacked, fumbles, recovered by Alabama (I.Faga)</td><td>-0.51</td></tr>
                <tr><td>Q4, 2:42</td><td>Kentucky</td><td>Patterson rushes for 3 yards, fumbles, recovered by Alabama (I.Taylor)</td><td>-1.66</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Turnovers</th><th>PPA/play without turnovers</th><th>PPA/play with turnovers</th></tr></thead>
              <tbody>
                <tr><td>Alabama</td><td>3</td><td>0.353</td><td>0.190</td></tr>
                <tr><td>Kentucky</td><td>3</td><td>0.001</td><td className="hi">-0.168</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            This is the game where the turnovers change the story the most. Strip them out and Kentucky&rsquo;s
            process looked dead even &mdash; 0.001 PPA/play, essentially a coin flip. Put the turnovers back and
            Kentucky drops to -0.168, while Alabama, who also gave the ball away three times, still comes out at a
            strong +0.190. Alabama&rsquo;s offense earned the win on non-turnover snaps too, but the turnover margin
            is what turned a competitive process into a 28-point final.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 3</span>
            <h2>Texas 24, Ohio State 23</h2>
          </div>
          <p>
            Texas turned it over twice, Ohio State once &mdash; on the final play of the game, with the outcome
            already decided.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>PPA on the play</th></tr></thead>
              <tbody>
                <tr><td>Q1, 14:49</td><td>Texas</td><td>Manning completes to R.Brown, fumbles, recovered by Ohio State (J.Timmons)</td><td>-0.73</td></tr>
                <tr><td>Q1, 10:15</td><td>Texas</td><td>Manning intercepted by J.McClain, returned 7 yards</td><td>-2.05</td></tr>
                <tr><td>Q4, 0:17</td><td>Ohio State</td><td>Sayin intercepted by G.Littleton, final play of the game</td><td>+0.14</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Turnovers</th><th>PPA/play without turnovers</th><th>PPA/play with turnovers</th></tr></thead>
              <tbody>
                <tr><td>Texas</td><td>2</td><td>0.193</td><td>0.163</td></tr>
                <tr><td>Ohio State</td><td>1</td><td>0.148</td><td>0.148</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Ohio State&rsquo;s number doesn&rsquo;t move at all &mdash; one low-value, game-ending pick spread across
            63 plays barely registers. Texas&rsquo;s does: two first-half giveaways, including one that handed Ohio
            State a short field, pull their PPA/play down from 0.193 to 0.163. Texas still finishes ahead of Ohio
            State either way, but the margin between them is noticeably tighter once the turnovers count.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Bigger Picture</span>
            <h2>Turnovers moved every offense&rsquo;s number &mdash; just not by the same amount</h2>
          </div>
          <div className="article-stat-grid">
            <Stat value="11" label="Total turnovers across the three games" />
            <Stat value="-22.7" label="Combined PPA value on those 11 plays" />
            <Stat value="-0.169" label="Kentucky's swing, the largest of any team" />
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
