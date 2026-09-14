import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "Nobody Knows Who's Good Yet. Here's Why Week 4 Matters | LEILA Ratings",
  description:
    "After two games, college football is still split into dozens of disconnected groups. LEILA's data shows why rankings become much more useful around Week 4.",
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
          <h1>Nobody Knows Who&rsquo;s Good Yet. Here&rsquo;s Why Week 4 Matters.</h1>
          <p className="article-dek">
            Two games can tell us something. They cannot tell us enough. Early in the season, huge parts of college
            football have not crossed paths yet, which makes national rankings much shakier than the number beside a
            team&rsquo;s name suggests. Our own data shows when that starts to change.
          </p>
          <p className="article-byline">LEILA Ratings Data Desk</p>
        </header>

        <section className="article-section">
          <p>
            Every September, the same thing happens. A team crushes two overmatched opponents, jumps in the polls,
            and suddenly everyone wants to know whether it is a playoff team. Another team wins ugly twice and gets
            written off. After only a couple of games, we talk about the rankings as if the country has already been
            sorted out.
          </p>
          <p>
            It has not. The problem is not just that two games are a small sample. The bigger problem is that most
            teams have not played enough connected competition yet. Michigan may have played two teams, Georgia may
            have played two completely different teams, and Oregon may be sitting in another part of the schedule
            altogether. There may be almost no game evidence connecting those teams to one another.
          </p>
          <p>
            That means early-season college football is not really one national comparison yet. It is a bunch of
            smaller groups trying to be ranked on the same list. Our <Link href="/network">live network page</Link>
            shows exactly how quickly those groups begin to connect.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">The Big Problem</span>
            <h2>After two weeks, college football is basically 39 mini-leagues</h2>
          </div>
          <p>
            Think of every game as a bridge between two teams. Once enough bridges exist, you can trace a path from
            almost any team in the country to any other team through shared opponents and opponents of opponents.
            That is what allows an opponent-adjusted rating to compare teams nationally.
          </p>
          <p>
            Early in September, those bridges barely exist. We pulled the published 2026 FBS schedule from CFBD and
            counted how many separate groups of teams are actually connected after each week.
          </p>
          <div className="article-table-wrap">
            <table className="article-table">
              <thead>
                <tr><th>Through week</th><th>Separate groups</th><th>Largest group</th></tr>
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
            Through two weeks, the sport is still split into <strong>39 separate groups</strong>. The biggest one
            contains only 17 of 138 teams. If Team A is the best team in one group and Team B is the best team in
            another, there may still be no path of game results connecting them. We are trying to decide which is
            better without having much common evidence.
          </p>
          <p>
            By Week 3, almost the entire country has connected. By <strong>Week 4</strong>, all 138 teams are part of
            one network. For the first time, the season itself gives us a chain of results connecting everyone.
          </p>
          <p>
            Week 4 does not suddenly make every ranking correct. Four games are still four games. It is simply the
            first point this season when ranking the whole country is based on one connected body of evidence instead
            of dozens of separate islands.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">A Real Example</span>
            <h2>That is how an 0-2 team ended up No. 4</h2>
          </div>
          <p>
            Two games into 2026, one version of our own ratings produced something obviously wrong: Sam Houston was
            <strong> 0-2 and ranked fourth in the country</strong>.
          </p>
          <p>
            The reason was not that Sam Houston had secretly played like a top-four team. Sam Houston, Troy and Tulsa
            were sitting inside a small pocket of connected teams that also included Oregon and Indiana. With so few
            games linking that pocket to the rest of the country, strength from the top of the group could spill into
            teams that had done very little to earn it.
          </p>
          <p>
            In plain English: <strong>the computer had not seen enough football yet.</strong>
          </p>
          <p>
            LEILA&rsquo;s main rating, Adj. Net, is designed to pull extreme early results back toward average until
            more evidence arrives. That helps prevent wild rankings like Sam Houston at No. 4. But no model can create
            information that has not happened on the field yet.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">We Tested Ourselves</span>
            <h2>Our own history says two games are not enough</h2>
          </div>
          <p>
            Instead of only criticizing the AP Poll, we tested LEILA against itself. We went back through eleven full
            seasons of our historical ratings from 2014 through 2025, excluding 2020, and asked a simple question:
            how similar are the rankings after about two games to the rankings at the end of the season?
          </p>
          <div className="article-stat-grid">
            <Stat value="4.1 / 10" label="Teams from the ~2-game top 10 that are still top 10 at season's end" />
            <Stat value="5.8 / 10" label="Teams from the ~4-game top 10 that are still top 10 at season's end" />
            <Stat value="0.71" label="Overall rank similarity after ~2 games (1.00 would be a perfect match)" />
            <Stat value="0.83" label="Overall rank similarity after ~4 games (1.00 would be a perfect match)" />
          </div>
          <p>
            The easiest number to understand is the top 10. After roughly two games, only
            <strong> 4.1 of the teams in our top 10</strong>, on average, are still there at the end of the season.
            After roughly four games, that rises to <strong>5.8 of 10</strong>.
          </p>
          <p>
            The full rankings tell the same story. Our rank similarity score improves from 0.71 after about two games
            to 0.83 after about four. Early rankings clearly contain useful information, but they become noticeably
            more stable once teams have played more football and the national schedule is connected.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">It Is Not Just LEILA</span>
            <h2>The AP Poll starts the season guessing too</h2>
          </div>
          <p>
            Every ranking system has the same basic September problem: there is not enough current-season football to
            work with yet. Human polls fill that gap with preseason expectations. Computer models use some combination
            of previous seasons, recruiting, returning production or conservative early-season adjustments.
          </p>
          <p>
            Those preseason expectations are far from perfect. Across the twelve seasons of the College Football
            Playoff era from 2014 through 2025, a study of 300 preseason-ranked AP teams found that only
            <strong> 57% finished the season in the final Top 25</strong> and just
            <strong> 32% finished in the final top 10</strong>.
          </p>
          <p>
            So when a preseason No. 4 team starts 2-0, its Week 2 ranking is not suddenly based on two games alone.
            A lot of what we believed in August is still baked into that number. Sometimes that prior is useful.
            Sometimes it is wrong. Either way, two games have not fully replaced it yet.
          </p>
        </section>

        <section className="article-section">
          <div className="article-section__heading">
            <span className="eyebrow">And It Is Getting Harder</span>
            <h2>Last year&rsquo;s team tells us less than it used to</h2>
          </div>
          <p>
            The obvious solution to having too little new data is to lean on last year. But modern college football
            has made that harder too. Rosters change faster than they used to, so the team wearing the same logo in
            September may look very different from the one that finished the previous season.
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
            In 2014, only 30% of FBS teams returned less than half of their production from the previous year. In
            2025, that number reached <strong>65%</strong>. The average team returned just
            <strong> 39.9%</strong> of its production.
          </p>
          <p>
            That creates a bad combination for early rankings: we do not have enough games from this season yet, and
            the information from last season is becoming less reliable too.
          </p>
        </section>

        <section className="article-section article-actions">
          <div>
            <span className="eyebrow">So When Should You Trust The Rankings?</span>
            <h2>Start taking them more seriously around Week 4.</h2>
            <p>
              Not because Week 4 magically reveals who is good. It does not. But by then, every FBS team is finally
              connected through the schedule, and our historical testing shows the rankings become meaningfully more
              stable around the same point.
            </p>
            <p>
              That is the real takeaway: <strong>early rankings should come with less confidence.</strong> Watch the
              games. Argue about the top 10. Have fun with it. Just understand that in Weeks 1 and 2, everyone is
              working with an incomplete picture, including us.
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
          Rank-similarity figures use Spearman correlation across eleven historical seasons (2014-2025, excluding
          2020, which has no published data) of LEILA&rsquo;s own rating history. Because site week-numbering shifted
          slightly across seasons, each season is aligned by median games played (&asymp;2 and &asymp;4) rather than
          raw week label. Returning-production figures are CFBD&rsquo;s <code>/player/returning</code> data (national
          average and per-team usage share, 2014-2026; 2013 has no published data). AP Poll historical figures via
          RotoWire&rsquo;s 12-year preseason-poll study.
        </p>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}