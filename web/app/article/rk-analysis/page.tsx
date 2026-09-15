import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "We Found (and Fixed) a Real Gap in PPA/Play | LEILA Ratings",
  description:
    "Auditing three Week 2 classics against CFBD's box score turned up a real bug: every turnover in these games -- all 11, verified -- was being silently excluded from PPA/play. We found it, fixed the site's actual eligibility rule, and rebuilt every season back to 2014.",
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
          <h1>We Found (and Fixed) a Real Gap in PPA/Play</h1>
          <p className="article-dek">
            We set out to compare each team&rsquo;s PPA per play with turnovers included against the published
            number in three Week 2 classics: Texas-Ohio State, Alabama-Kentucky, and Michigan-Oklahoma. That turned
            into two rounds of corrections and, in the end, a real fix to the site&rsquo;s actual eligibility rule.
            Every real turnover in these three games &mdash; all 11, verified against CFBD&rsquo;s box score &mdash;
            was being silently excluded from PPA/play. Not some of them. All of them. Here&rsquo;s exactly why, and
            what we changed.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            PPA (predicted points added) is CFBD&rsquo;s own play-level model &mdash; the same kind of metric most
            sites, including this one, refer to as &ldquo;EPA&rdquo; (expected points added). Our eligibility rule
            for counting a play toward PPA/play used to require two things: a real offensive scrimmage snap, and no
            &ldquo;state transition modifier&rdquo; &mdash; a flag that gets set whenever a play&rsquo;s text
            mentions a fumble or an interception, regardless of what actually happened on the play.
          </p>
          <p>
            That second condition turned out to be the real problem, and it took us two passes to find the full
            extent of it. The first thing we noticed: CFBD&rsquo;s source data merges a turnover with its return
            into one row (&ldquo;Pass Interception Return,&rdquo; &ldquo;Fumble Recovery (Opponent)&rdquo;) and
            marks that merged row as not a scrimmage snap &mdash; correct for the return itself, but it also
            discards the original throw or handoff bundled into the same row. We assumed that only affected
            turnovers with an actual return attached, and that a &ldquo;clean&rdquo; interception or fumble (no
            return, just &ldquo;End of Play&rdquo;) would still count normally. It doesn&rsquo;t. The state-transition
            flag fires from the play text alone, so it excluded <em>every</em> turnover in these three games, clean
            or not &mdash; we only caught this on a second, closer look.
          </p>
          <p>
            <strong>We verified all 11 turnovers below against CFBD&rsquo;s official box score</strong> (the{" "}
            <code>/games/teams</code> endpoint&rsquo;s <code>turnovers</code> stat) and read the actual play text
            for each one, not CFBD&rsquo;s structured labels, which we also found to be unreliable on two plays. Full
            methodology at the end.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 1</span>
            <h2>Michigan 17, Oklahoma 10</h2>
          </div>
          <p>
            Box score: <strong>Oklahoma 2 turnovers, Michigan 0.</strong> Neither of Oklahoma&rsquo;s counted toward
            PPA/play under the old rule.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>Counted before the fix?</th></tr></thead>
              <tbody>
                <tr><td>Q2, 13:32</td><td>Oklahoma</td><td>Mateer completes to Livingstone for 8 yards, fumbles, recovered by Michigan (Bowles)</td><td>-3.34</td><td>No</td></tr>
                <tr><td>Q4, 8:49</td><td>Oklahoma</td><td>Mateer intercepted by J.Hill, returned 24 yards</td><td>+0.23</td><td>No</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Offense PPA/play (old)</th><th>Offense PPA/play (fixed)</th></tr></thead>
              <tbody>
                <tr><td>Michigan</td><td>0</td><td>0.101</td><td>0.064</td></tr>
                <tr><td>Oklahoma</td><td>2</td><td>0.083</td><td>0.025</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Michigan&rsquo;s own number moves too, even with 0 real turnovers &mdash; they fumbled twice and
            recovered both themselves, and those plays are turnover-flagged (and were excluded) regardless of
            whether possession actually changed.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 2</span>
            <h2>Alabama 45, Kentucky 17</h2>
          </div>
          <p>
            Box score: <strong>Alabama 3 turnovers (2 interceptions, 1 fumble), Kentucky 3 (1 interception, 2
            fumbles).</strong> Two rounds of corrections happened on this game specifically. First, we&rsquo;d
            undercounted the real turnovers by trusting a CFBD structured label (&ldquo;Fumble Recovery
            (Own)&rdquo;) that contradicted the actual play text on two plays. Second, we&rsquo;d assumed Alabama&rsquo;s
            late, &ldquo;clean&rdquo; interception was already counted in the published number. It wasn&rsquo;t
            &mdash; none of these six were:
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>Counted before the fix?</th></tr></thead>
              <tbody>
                <tr><td>Q1, 10:15</td><td>Alabama</td><td>Russell intercepted by Humphrey-Grace, returned 2 yards for a TOUCHDOWN</td><td>-6.61</td><td>No</td></tr>
                <tr><td>Q1, 7:17</td><td>Alabama</td><td>Russell sacked, fumbles, recovered by Kentucky (C.Works)</td><td>-0.96</td><td>No</td></tr>
                <tr><td>Q1, 6:44</td><td>Kentucky</td><td>Minchey intercepted by L.Metz, returned 34 yards for a TOUCHDOWN</td><td>-7.23</td><td>No</td></tr>
                <tr><td>Q2, 0:55</td><td>Alabama</td><td>Russell intercepted by J.Castell</td><td>+0.02</td><td>No</td></tr>
                <tr><td>Q3, 5:47</td><td>Kentucky</td><td>Minchey sacked, fumbles, recovered by Alabama (I.Faga)</td><td>-0.51</td><td>No</td></tr>
                <tr><td>Q4, 2:42</td><td>Kentucky</td><td>Patterson rushes for 3 yards, fumbles, recovered by Alabama (I.Taylor)</td><td>-1.66</td><td>No</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Offense PPA/play (old)</th><th>Offense PPA/play (fixed)</th></tr></thead>
              <tbody>
                <tr><td>Alabama</td><td>3</td><td>0.353</td><td>0.190</td></tr>
                <tr><td>Kentucky</td><td>3</td><td>0.001</td><td className="hi">-0.168</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            This is the game where the fix actually matters. The old number said Alabama and Kentucky were both
            hovering around &ldquo;average&rdquo; process (0.353 and 0.001). The corrected number tells a very
            different story: Alabama at a strong +0.190 PPA/play, Kentucky underwater at -0.168 &mdash; which lines
            up with a 45-17 final a lot better than &ldquo;both teams played about the same.&rdquo;
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Game 3</span>
            <h2>Texas 24, Ohio State 23</h2>
          </div>
          <p>
            Box score: <strong>Texas 2 turnovers (1 interception, 1 fumble), Ohio State 1 (interception).</strong>{" "}
            Same story as Alabama&rsquo;s late pick: we&rsquo;d assumed Ohio State&rsquo;s game-ending interception
            was already counted because it was a &ldquo;clean&rdquo; play with no return. It wasn&rsquo;t.
          </p>
          <div className="article-table-wrap">
            <table className="article-table article-table--wide">
              <thead><tr><th>Qtr / Clock</th><th>Team</th><th>What happened</th><th>CFBD play value</th><th>Counted before the fix?</th></tr></thead>
              <tbody>
                <tr><td>Q1, 14:49</td><td>Texas</td><td>Manning completes to R.Brown, fumbles, recovered by Ohio State (J.Timmons)</td><td>-0.73</td><td>No</td></tr>
                <tr><td>Q1, 10:15</td><td>Texas</td><td>Manning intercepted by J.McClain, returned 7 yards</td><td>-2.05</td><td>No</td></tr>
                <tr><td>Q4, 0:17</td><td>Ohio State</td><td>Sayin intercepted by G.Littleton, final play of the game</td><td>+0.14</td><td>No</td></tr>
              </tbody>
            </table>
          </div>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Team</th><th>Box score turnovers</th><th>Offense PPA/play (old)</th><th>Offense PPA/play (fixed)</th></tr></thead>
              <tbody>
                <tr><td>Texas</td><td>2</td><td>0.193</td><td>0.163</td></tr>
                <tr><td>Ohio State</td><td>1</td><td>0.148</td><td>0.148</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Ohio State&rsquo;s number barely moves &mdash; one low-stakes, game-ending pick spread across 63 plays
            isn&rsquo;t going to shift much. Texas&rsquo;s does, meaningfully, once its own two turnovers (including
            the first-half pick that set up an Ohio State scoring chance) are actually counted against them.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">What This Actually Means</span>
            <h2>0 of 11 turnovers counted. Now all 11 do.</h2>
          </div>
          <div className="article-stat-grid">
            <Stat value="11" label="Real turnovers across all 3 games, verified against CFBD's box score" />
            <Stat value="0" label="That counted toward PPA/play under the original rule" />
            <Stat value="-22.7" label="Combined CFBD play value that was being silently dropped every game" />
            <Stat value="11" label="That count now, on every play going forward and back to 2014" />
          </div>
          <p>
            The root cause was a flag meant to catch penalties and no-plays &mdash; &ldquo;state transition
            modifier&rdquo; &mdash; that also fires any time a play&rsquo;s text mentions a fumble or an
            interception, regardless of the play&rsquo;s actual structured type. Combined with CFBD merging a
            turnover&rsquo;s return into the same row as the original snap, the two together excluded every single
            turnover from PPA/play, in every game, for every season this site has ever published.
          </p>
          <p>
            <strong>We fixed it.</strong> The site&rsquo;s eligibility rule now counts a turnover&rsquo;s PPA value
            toward the offense that had the ball, whether or not the row also describes a return, and whether or not
            it happens to carry that text-triggered flag &mdash; while still correctly excluding real special-teams
            returns (kickoffs, punts) that never had an offensive snap attached, and turnovers nullified by a
            penalty. We rebuilt every season back to 2014 under the corrected rule rather than patch it forward
            only; a change like this either applies to the whole historical record or it doesn&rsquo;t mean
            anything.
          </p>
          <p>
            This does flow into LEILA&rsquo;s published Advanced-page PPA figures (the numbers in the tables above
            are the live, corrected ones). It does <em>not</em> change Adj. Off/Adj. Def &mdash; LEILA&rsquo;s
            primary ratings are built from opponent-adjusted scoring efficiency, not PPA, so they were never
            affected by this bug in the first place.
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
          category) for gameIds 401856679, 401856674, and 401856682 (Week 2, 2026). Each turnover was matched to its
          play-by-play row by hand, cross-referencing the play text (not CFBD&rsquo;s structured recovery label,
          found unreliable on two plays) against the box score total for that team. &ldquo;Counted before the
          fix&rdquo; reflects the site&rsquo;s actual PPA eligibility rule as published prior to this piece
          (<code>epa-v1-cfbd-ppa</code>); the &ldquo;fixed&rdquo; PPA/play figures reflect the corrected rule now
          live site-wide (<code>epa-v2-cfbd-ppa-turnovers-included</code>), rebuilt across every published season
          (2014-2026).
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}
