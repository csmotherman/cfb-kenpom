import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "Nobody Knows Who's Good Yet | LEILA Ratings",
  description:
    "Every college football ranking published before Week 4 -- the AP Poll, ESPN's FPI, even LEILA's own ratings -- is closer to a guess than a measurement. Here's the data.",
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
          <h1>Nobody Actually Knows Who&rsquo;s Good Right Now &mdash; Not the AP, Not ESPN, Not Even Us</h1>
          <p className="article-dek">
            Every ranking you&rsquo;re reading this early in the season &mdash; the AP Poll, the committee&rsquo;s
            future darling, LEILA&rsquo;s own Adj. Net &mdash; is closer to a guess than a measurement. We can prove
            it with our own data, and explain exactly why it happens. The short version: wait until Week 4.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            Every September, the same ritual plays out. A team wins two games against overmatched opponents, climbs
            eleven spots in the AP Poll, and pundits spend a week arguing about whether they&rsquo;re &ldquo;for
            real.&rdquo; Nobody stops to ask the more basic question: is there even enough information yet to know?
          </p>
          <p>
            For most of the sport, in most weeks, the honest answer is no. Not because voters are lazy or biased
            (though anchoring bias is real and well documented), but because of something more structural: through
            the first two or three weeks of a season, the country&rsquo;s 136+ FBS teams simply haven&rsquo;t played
            enough games against each other to be compared on the same scale. We built a page to show this happening
            in real time &mdash; <Link href="/network">/network</Link> &mdash; and the numbers behind it are stark
            enough that we think every fan should see them before they trust a single Week 1-3 ranking, including
            ours.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Mechanism</span>
            <h2>The networks nobody&rsquo;s talking about</h2>
          </div>
          <p>
            Every opponent-adjusted rating &mdash; ours, SP+, FPI, all of them &mdash; works by solving a giant,
            simultaneous system: Team A&rsquo;s rating depends on who Team A played, which depends on who
            <em> those</em> teams played, all the way out. For that system to mean anything, it needs one thing
            first: a single, connected web of games tying every team in the country together. If Team A and Team B
            haven&rsquo;t played each other, and don&rsquo;t share a common opponent, and don&rsquo;t share an
            opponent-of-an-opponent, there is no chain of evidence connecting them at all. Their ratings aren&rsquo;t
            wrong, exactly &mdash; they&rsquo;re just not comparable yet.
          </p>
          <p>
            We pulled the actual, real 2026 FBS schedule from CFBD and asked a simple question: how many separate,
            disconnected &ldquo;networks&rdquo; does the country split into, week by week?
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
            Through two weeks &mdash; roughly where most of the country sits when the first &ldquo;real&rdquo; AP
            Poll debates start &mdash; the sport is broken into <strong>39 separate islands</strong>. A team sitting
            at the top of the biggest island (17 teams) and a team sitting atop a 2-team island aren&rsquo;t
            measured against each other at all. It isn&rsquo;t until <strong>Week 4</strong> that this season&rsquo;s
            actual schedule finally ties the entire country into one connected network &mdash; and even then, we
            checked for weak points: zero of those connections are single-game &ldquo;bridges&rdquo; that could
            still split the graph back apart, which is the good news. The catch is that by Week 4 most teams have
            still played only 2-5 games, so every rating is still resting on a small sample even once it&rsquo;s
            technically comparable.
          </p>
          <p>
            This isn&rsquo;t hypothetical. Two weeks into the 2026 season, our own ASM metric &mdash; an
            unshrunk, results-based rating built the same way most fan-facing power rankings are &mdash; had Sam
            Houston ranked <strong>4th nationally</strong>. Sam Houston was 0-2. It happened because Sam Houston,
            Troy, and Tulsa formed a thinly-connected pocket that also contained Oregon and Indiana, and a model with
            no protection against small samples let that pocket&rsquo;s strength bleed onto three teams that hadn&rsquo;t
            won a game. Adj. Net &mdash; LEILA&rsquo;s primary rating, which has shrinkage built in specifically to
            guard against this &mdash; didn&rsquo;t make the same mistake. Most public rankings don&rsquo;t have that
            protection at all.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">We Checked Ourselves</span>
            <h2>Even our own model fails this test at 2 games played</h2>
          </div>
          <p>
            It would be easy to write all of this as a knock on the AP Poll and stop there. We didn&rsquo;t. We went
            back through eleven full seasons of our own historical data (2014-2025, excluding 2020) and asked: how
            well does our own rating &mdash; at the point each team had played about 2 games &mdash; actually
            predict where teams end up at season&rsquo;s end?
          </p>
          <div className="article-stat-grid">
            <Stat value="0.71" label="~2 games played → final season rank correlation (Spearman ρ)" />
            <Stat value="4.1 / 10" label="Average overlap between the ~2-game top 10 and the final top 10" />
            <Stat value="0.83" label="~4 games played → final season rank correlation" />
            <Stat value="5.8 / 10" label="Average overlap between the ~4-game top 10 and the final top 10" />
          </div>
          <p>
            Read that middle number again: across eleven seasons, on average, fewer than half of the teams in a
            team&rsquo;s own 2-games-played top 10 are still in the final top 10. And this is with a model built
            specifically to resist early-season noise &mdash; hierarchical shrinkage toward the league mean, plus a
            tapered prior-season baseline for opponent strength. Waiting until about 4 games played measurably
            helps: rank correlation with the final season climbs from 0.71 to 0.83, and top-10 stability improves by
            more than 40%. That match to our own network data above isn&rsquo;t a coincidence &mdash; 4 games in is
            roughly when this season&rsquo;s schedule actually finishes connecting the country into one graph.
          </p>
          <p>
            If our own numbers, with our own safeguards, still can&rsquo;t hold a stable top 10 through the first
            couple of games, it is not realistic to expect a human poll &mdash; filled out from memory, preseason
            expectations, and one or two data points &mdash; to do meaningfully better.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Receipts</span>
            <h2>The AP Poll&rsquo;s own numbers say the same thing</h2>
          </div>
          <p>
            This isn&rsquo;t just a LEILA problem, and it isn&rsquo;t new. Across the twelve seasons of the College
            Football Playoff era (2014-2025), research tracking all 300 preseason-ranked team-seasons found that only{" "}
            <strong>57% of preseason AP Top 25 teams finished the season in the final Top 25</strong>. Only{" "}
            <strong>32% of preseason top-10 teams finished in the final top 10</strong>. In the
            &ldquo;modern transfer-portal era,&rdquo; the average overlap between a preseason Top 25 and the final
            Top 25 has fallen to about 12 of 25 teams &mdash; roughly a coin flip, down from a 15-of-25 average in
            the 2007-2016 window.
          </p>
          <p>
            The AP doesn&rsquo;t re-poll from scratch every week, either. Voters are demonstrably anchored to where
            a team started: a team ranked #3 in the preseason poll that wins two unconvincing games rarely falls out
            of the top 10, while an unranked team that wins two blowouts rarely cracks it. That means most of the
            unreliability baked into the preseason poll is still riding along in the Week 2 and Week 3 polls people
            treat as fresh, current information.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">Why It&rsquo;s Worse Than Ever</span>
            <h2>NIL and the transfer portal broke the one thing polls used to lean on</h2>
          </div>
          <p>
            Even the flawed old system had one thing going for it: rosters used to be relatively stable year to year,
            so &ldquo;this team was good last year and returns most of its players&rdquo; was a reasonable prior.
            That prior is gone. Over <strong>3,350 FBS players</strong> entered the transfer portal in the 2025
            cycle &mdash; roughly a quarter of every scholarship player in the sport moving programs in a single
            offseason, more than double the number just three cycles earlier. Colorado, under Deion Sanders, lost
            61% of its entire 2023 roster class to the portal in one cycle. Nationally, the share of transfers who
            are themselves repeat transfers &mdash; players bouncing a second or third time &mdash; rose to 31% in
            the 2024-25 cycle.
          </p>
          <p>
            Money moved just as fast. Industry-wide NIL payments in college football went from roughly{" "}
            <strong>$917 million</strong> in 2021-22 to a projected <strong>$2.55 billion</strong> in 2025-26.
            Average Power 4 roster spend (NIL plus revenue-share) hit an estimated <strong>$24.8 million</strong> in
            2025, up from $9.4 million the year before. Texas alone reportedly spent up to $40 million building its
            2025 roster. The on-field effect shows up in the results: SEC games averaged a margin of victory of just
            10.0 points in 2025, the tightest the conference has been since 2006 &mdash; exactly what you&rsquo;d
            expect if talent is spreading out faster than anyone can track.
          </p>
          <p>
            Put together, that&rsquo;s a compounding problem, not two separate ones. The schedule graph tells you
            there isn&rsquo;t enough <em>data</em> yet to compare most teams. The transfer portal and NIL tell you
            that even the <em>priors</em> you&rsquo;d normally lean on while waiting for data &mdash; last
            year&rsquo;s tape, recruiting rankings, name recognition &mdash; are less trustworthy than they&rsquo;ve
            ever been, because the actual players wearing the jersey have changed more than at any point in the
            sport&rsquo;s history. There has never been a worse moment to trust a ranking built on vibes and
            two games.
          </p>
        </section>

        <section className="article-section article-actions">
          <div>
            <span className="eyebrow">What To Actually Do</span>
            <h2>Wait for Week 4. Then check the network.</h2>
            <p>
              None of this means early-season football doesn&rsquo;t matter, or that you shouldn&rsquo;t watch it.
              It means the number next to a team&rsquo;s name in Week 2 deserves a lot less certainty than the graphic
              on your screen implies. We built LEILA&rsquo;s ratings with that in mind &mdash; hierarchical shrinkage
              on Adj. Net, an honest &ldquo;résumé, not a power rating&rdquo; label on ASM, and a live page showing
              exactly how connected this season&rsquo;s schedule graph actually is, so you don&rsquo;t have to take
              our word for any of it.
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
          week label, so the comparison is apples to apples. AP Poll historical figures via RotoWire&rsquo;s
          12-year preseason-poll study. Transfer portal and NIL figures via 247Sports, CBS Sports, Front Office
          Sports, Sports Illustrated, and Opendorse&rsquo;s NIL industry reporting, current as of the 2025 offseason.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}
