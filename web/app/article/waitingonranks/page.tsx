import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "College Football Rankings Have a Week 4 Problem | LEILA Ratings",
  description:
    "Early-season college football rankings are far less certain than they look. LEILA's schedule-network analysis and historical backtest show why Week 4 is the first meaningful national comparison point.",
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

export default function WaitingOnRanksArticle() {
  return (
    <>
      <a className="skip-link" href="#articleContent">Skip to article</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="articleContent" className="container article-main">
        <header className="article-hero">
          <span className="eyebrow">Data Investigation</span>
          <h1>College Football Rankings Have a Week 4 Problem</h1>
          <p className="article-dek">
            Early-season rankings are not useless. They are simply much less certain than they look. The schedule
            itself is too disconnected to compare most teams cleanly, and our own historical backtest shows how much
            stability improves once teams reach roughly four games played.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            Every September, the same ritual plays out. A team wins two games against overmatched opponents, climbs
            eleven spots in the AP Poll, and the national conversation immediately turns to whether it is
            &ldquo;for real.&rdquo; The more important question comes first: is there enough information yet to compare
            that team to the rest of the country with any confidence?
          </p>
          <p>
            Through the first two or three weeks, often there is not. That is not primarily a criticism of voters.
            It is a structural problem. FBS teams have not played enough games against one another to form a single,
            well-connected comparison network. We built <Link href="/network">a live network page</Link> to make
            that problem visible, and the 2026 schedule shows exactly why early rankings should be treated as
            estimates with wide uncertainty bands rather than settled measurements.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Mechanism</span>
            <h2>The country is not one comparison pool yet</h2>
          </div>
          <p>
            Opponent-adjusted ratings work through chains of evidence. Team A is evaluated against the teams it
            played, those teams are evaluated against their opponents, and the system propagates outward. If two
            teams do not share an opponent, an opponent-of-an-opponent, or any longer path connecting their schedules,
            there is no results-based chain tying them together yet.
          </p>
          <p>
            We pulled the published 2026 FBS schedule from CFBD and asked a simple question: how many disconnected
            networks does the country contain after each week?
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead>
                <tr><th>Through week</th><th>Separate networks</th><th>Largest network</th></tr>
              </thead>
              <tbody>
                <tr><td>0 (openers)</td><td>130</td><td>2 of 138 teams</td></tr>
                <tr><td>1</td><td>87</td><td>6 of 138 teams</td></tr>
                <tr><td>2</td><td>39</td><td>17 of 138 teams</td></tr>
                <tr><td>3</td><td>3</td><td>129 of 138 teams</td></tr>
                <tr><td>4</td><td><strong>1</strong></td><td><strong>138 of 138 teams</strong></td></tr>
              </tbody>
            </table>
          </div>
          <p>
            Through two weeks, the sport is still split into <strong>39 separate islands</strong>. The largest
            contains only 17 of 138 teams. A team leading one island and a team leading another are not yet being
            measured through the same web of game results. By Week 3, the country is almost connected. By
            <strong> Week 4</strong>, all 138 teams sit in one network, with no single-game bridge capable of splitting
            that graph back apart.
          </p>
          <p>
            Week 4 is not a magic line where uncertainty disappears. Most teams still have only a handful of games.
            It is simply the first point this season when a national comparison is structurally defensible rather than
            a comparison between disconnected pockets of the sport.
          </p>
          <p>
            The danger is not theoretical. Two games into 2026, our unshrunk ASM rating had 0-2 Sam Houston ranked
            <strong> 4th nationally</strong>. Sam Houston, Troy, and Tulsa occupied a thinly connected pocket that
            also contained Oregon and Indiana, and a model without enough protection against small samples let that
            pocket&rsquo;s strength bleed into an absurd ranking. LEILA&rsquo;s Adj. Net uses shrinkage specifically to
            reduce that failure mode, but even a protected model cannot manufacture information that has not been
            played onto the field yet.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">We Checked Ourselves</span>
            <h2>Our own historical ratings are unstable after two games</h2>
          </div>
          <p>
            It would be easy to turn this into an argument about the AP Poll and stop there. So we tested LEILA
            instead. Across eleven full seasons of historical data (2014-2025, excluding 2020), we compared each
            team&rsquo;s rating at roughly two games played and roughly four games played with its final-season rank.
          </p>
          <div className="article-stat-grid">
            <Stat value="0.71" label="~2 games played → final season rank correlation (Spearman ρ)" />
            <Stat value="4.1 / 10" label="Average overlap between the ~2-game top 10 and the final top 10" />
            <Stat value="0.83" label="~4 games played → final season rank correlation" />
            <Stat value="5.8 / 10" label="Average overlap between the ~4-game top 10 and the final top 10" />
          </div>
          <p>
            After roughly two games, rank correlation with the final season is already meaningful at 0.71. That is
            why calling early ratings completely random would be wrong. But the top of the table is still volatile:
            the average early top 10 shares only <strong>4.1 teams</strong> with the eventual final top 10.
          </p>
          <p>
            Around four games played, correlation rises to <strong>0.83</strong> and average top-10 overlap improves to
            <strong> 5.8 teams</strong>. That is a better than 40% improvement in top-10 stability. The timing lines
            up with the network result above: as the schedule finally connects nationally, the ratings become
            materially more informative too.
          </p>
          <p>
            LEILA is built to resist early-season noise through hierarchical shrinkage toward the league mean and a
            tapered prior-season baseline for opponent strength. If a model with those safeguards still moves this
            much between two and four games, the correct takeaway is not that early rankings are worthless. It is that
            they should be presented with far less certainty.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Receipts</span>
            <h2>The AP Poll starts from an unstable baseline too</h2>
          </div>
          <p>
            This is not only a LEILA problem. Across the twelve seasons of the College Football Playoff era
            (2014-2025), a study of 300 preseason-ranked AP teams found that only <strong>57% finished in the final
            Top 25</strong> and just <strong>32% finished in the final top 10</strong>. Preseason top-five teams were
            much safer, finishing in the final top 10 77% of the time, but teams ranked 21-25 did so only 12% of the
            time.
          </p>
          <p>
            Weekly polls also do not start from zero. Early results are interpreted through preseason expectations,
            so uncertainty embedded in August can persist into September. That does not make the AP Poll useless;
            it means a Week 2 ranking should not be treated as if two games have replaced the preseason prior with a
            complete new measurement.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Why The Prior Is Weaker</span>
            <h2>Last year&rsquo;s team is becoming a worse shortcut for this year&rsquo;s team</h2>
          </div>
          <p>
            Early in a season, every rating system needs some prior belief while it waits for new evidence. That was
            easier when rosters were more stable. CFBD&rsquo;s returning-production data gives us a direct way to measure
            how much of the previous season&rsquo;s on-field usage actually returns.
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead><tr><th>Season</th><th>Avg. returning production</th><th>Teams under 50% returning</th></tr></thead>
              <tbody>
                <tr><td>2014</td><td>59.5%</td><td>30%</td></tr>
                <tr><td>2016</td><td>63.8%</td><td>23%</td></tr>
                <tr><td>2018</td><td>60.4%</td><td>32%</td></tr>
                <tr><td>2020</td><td>61.8%</td><td>29%</td></tr>
                <tr><td>2021*</td><td>69.4%</td><td>19%</td></tr>
                <tr><td>2022</td><td>55.6%</td><td>39%</td></tr>
                <tr><td>2023</td><td>55.2%</td><td>45%</td></tr>
                <tr><td>2024</td><td>47.6%</td><td>56%</td></tr>
                <tr><td className="hi">2025</td><td className="hi">39.9%</td><td className="hi">65%</td></tr>
                <tr><td>2026</td><td>44.0%</td><td>59%</td></tr>
              </tbody>
            </table>
          </div>
          <p className="article-table-caption">
            *2021 is inflated by the NCAA&rsquo;s blanket COVID eligibility waiver, which allowed many seniors to
            return for an additional season.
          </p>
          <p>
            In 2014, 30% of FBS teams returned less than half of their production. In 2025, that figure reached
            <strong> 65%</strong>, while the national average returning-production rate fell to
            <strong> 39.9%</strong>. The 2026 average has rebounded slightly to 44.0%, but a majority of teams are
            still below the 50% mark.
          </p>
          <p>
            That matters because early rankings lean most heavily on priors precisely when current-season evidence is
            thinnest. The schedule graph says there is not enough new data yet. Falling roster continuity says some of
            the old data is less representative too. Those two problems compound one another.
          </p>
        </section>

        <section className="article-section article-actions">
          <div>
            <span className="eyebrow">What To Actually Do</span>
            <h2>Wait for Week 4. Then keep the uncertainty in view.</h2>
            <p>
              Week 4 does not make a ranking final. It makes the national comparison more legitimate. By then, the
              schedule has connected the country into one network and historical LEILA ratings are materially more
              stable than they were after two games. That is the point where we should begin trusting the shape of the
              rankings more, while remembering that four games are still only four games.
            </p>
            <p>
              LEILA is built around that distinction: shrinkage on Adj. Net to guard against tiny samples, an honest
              &ldquo;résumé, not a power rating&rdquo; label on ASM, and a live network page showing how much connective
              evidence actually exists. Early-season uncertainty should be measured, not hidden.
            </p>
          </div>
          <div className="article-actions__links">
            <Link href="/network">See this week&rsquo;s network →</Link>
            <Link href="/methodology">How LEILA&rsquo;s ratings work →</Link>
            <Link href="/">View current ratings →</Link>
          </div>
        </section>

        <p className="article-footnote">
          Network figures are LEILA Ratings&rsquo; own analysis of the published 2026 FBS schedule (via CFBD).
          Correlation figures are our own analysis of eleven historical seasons (2014-2025, excluding 2020, which
          has no published data) of LEILA&rsquo;s own rating history, computed with scipy&rsquo;s Spearman
          implementation. Because the site&rsquo;s week-numbering shifted slightly across seasons (2014-2015 run
          about one week &ldquo;ahead&rdquo; of 2016-2024 at the same calendar point, and 2025 ran about one week
          &ldquo;behind&rdquo;), each season is aligned by median games played (&asymp;2 and &asymp;4), not by raw
          week label, so the comparison is apples to apples. Returning-production figures are CFBD&rsquo;s own{" "}
          <code>/player/returning</code> data (national average and per-team &ldquo;usage&rdquo; share, 2014-2026;
          2013 has no published data). AP Poll historical figures via RotoWire&rsquo;s 12-year preseason-poll study.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}