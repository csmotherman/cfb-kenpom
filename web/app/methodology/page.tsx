import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "Methodology | LEILA Ratings",
  description: "How LEILA Ratings builds opponent-adjusted college football ratings, team profiles, weekly matchup snapshots, and model research.",
};

export default function MethodologyPage() {
  return (
    <>
      <a className="skip-link" href="#methodologyContent">Skip to methodology</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="methodologyContent" className="container methodology-main">
        <header className="methodology-hero">
          <span className="eyebrow">LEILA Ratings Methodology</span>
          <h1>What the numbers actually mean</h1>
          <p>
            LEILA Ratings is built to describe team strength from real games, not recreate a poll. The core ratings account for opponent quality so the same statistical performance is treated differently against a strong opponent than against a weak one.
          </p>
        </header>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Core</span>
            <h2>APR — Adjusted Possession Rating</h2>
          </div>
          <p>
            APR stands for Adjusted Possession Rating. Net APR is LEILA’s overall team-strength metric, while Off APR and Def APR show the offensive and defensive components. In-season Net APR, Off APR and Def APR are possession-efficiency ratings built from offensive points per resolved possession and solved recursively across the FBS opponent network. A team&rsquo;s own rating is never blended with a preseason rating, recruiting input or conference-strength term. During the first three site weeks only, the opponent-strength adjustment is stabilized with a tapered prior-season opponent baseline; that influence is 50% through Week 2, 25% in Week 3 and 0% from Week 4 onward. A small zero-centered ridge toward the current-season FBS average also stabilizes sparse early-season samples.
          </p>
          <div className="methodology-definitions">
            <Definition term="APR" tag="System" text="Adjusted Possession Rating: LEILA’s opponent-adjusted possession-efficiency rating system, built from offensive points per resolved possession." />\n            <Definition term="Net APR" tag="Overall" text="The overall team-strength rating. Net APR = Off APR + Def APR. Zero represents an average FBS team; higher is better." />
            <Definition term="Off APR" tag="Core" text="Opponent-adjusted offensive points-per-resolved-possession effect, scaled to points per 10 resolved possessions above or below the FBS average. Higher is better." />
            <Definition term="Def APR" tag="Core" text="Opponent-adjusted defensive points-per-resolved-possession effect, scaled to points prevented per 10 resolved possessions above or below the FBS average. Higher is better." />
            <Definition term="SOS" tag="Context" text="Strength of schedule, based on the strength of opponents played through the selected rating snapshot." />
            <Definition term="SOR" tag="Résumé" text="Strength of Record: wins above what an exactly-average FBS team would be expected to earn against the same schedule. It answers a résumé question, separate from Net APR's performance question." />
            <Definition term="ASM" tag="Résumé" text="Adjusted Score Matrix: an opponent-adjusted scoring-margin rating (constrained least squares), with each game's margin capped at 28 points before fitting so a blowout can't dominate a team's number. A résumé lens like SOR, not a second opinion on who's better -- see &ldquo;Process vs. résumé&rdquo; below. Shown on Advanced, not the main Ratings page." />
          </div>
        </section>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Reading The Ratings</span>
            <h2>Process vs. résumé</h2>
          </div>
          <p>
            Net APR is LEILA&rsquo;s primary opponent-adjusted team-strength rating. It is fit from offensive drive points per resolved possession rather than directly from final scoring margin. Every completed FBS-vs-FBS team-game is solved simultaneously, so an efficiency result against a strong opponent is treated differently from the same result against a weak opponent. Net APR equals Off APR plus Def APR, with both components expressed on a points-per-10-resolved-possessions scale. EPA, Success Rate, Explosiveness and other play-level measures remain separate advanced and exploratory statistics; they do not currently determine Net APR. ASM is intentionally different: it is an opponent-adjusted scoring-margin r&eacute;sum&eacute; lens with each game&rsquo;s margin capped at 28 points. The disagreement between the possession-efficiency rating and ASM can therefore provide useful context without implying that the two metrics measure the same thing.
          </p>
        </section>

        <section className="methodology-section methodology-two-column">
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Team Profiles</span>
              <h2>Raw vs adjusted</h2>
            </div>
            <p>
              LEILA Ratings does not label every number opponent-adjusted. Public team profiles include season-to-date raw football results such as success rate, pass/rush success, yards per play, explosiveness and tendencies. Net APR and fields explicitly labeled as adjusted are model-based opponent-adjusted snapshots.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Advanced</span>
              <h2>Week ranges</h2>
            </div>
            <p>
              Metrics built from additive weekly counts can be recalculated for a selected range. Model ratings are snapshots and cannot honestly be added or averaged across arbitrary weeks, so LEILA Ratings keeps those two classes separate instead of pretending every column is rangeable.
            </p>
          </div>
        </section>

        <section className="methodology-section methodology-two-column">
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Schedule</span>
              <h2>Week 0</h2>
            </div>
            <p>
              LEILA Ratings uses chronological site weeks. Early opener games that occur several days before the main Week 1 slate are separated into Week 0 so the interface follows how fans actually experience the season instead of forcing every early game into one label.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">This Week</span>
              <h2>Pregame snapshots</h2>
            </div>
            <p>
              Weekly matchup pages use the latest LEILA rating snapshot strictly before the selected game week. That prevents the matchup page from quietly using the result it is supposed to be previewing.
            </p>
          </div>
        </section>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Model Research</span>
            <h2>Predictions must earn trust</h2>
          </div>
          <div className="methodology-rules">
            <p><strong>Walk-forward testing.</strong> Historical test seasons are evaluated using only seasons and games available before the test sample.</p>
            <p><strong>Immutable live predictions.</strong> Prospective prediction snapshots are timestamped and are not silently regenerated after the game.</p>
            <p><strong>No fake probability precision.</strong> LEILA Ratings will not publish a model win probability as calibrated until calibration has actually been validated.</p>
            <p><strong>Misses stay visible.</strong> The long-term goal is a public prediction archive so users can inspect both correct calls and misses.</p>
          </div>
        </section>

        <section className="methodology-section methodology-actions">
          <div>
            <span className="eyebrow">Use LEILA Ratings</span>
            <h2>Start with the football</h2>
            <p>Check the national ratings, then open the weekly slate to see how the teams in this weekend&rsquo;s games compare before kickoff.</p>
          </div>
          <div className="methodology-actions__links">
            <Link href="/">View ratings →</Link>
            <Link href="/predictions">Open Predictions →</Link>
          </div>
        </section>
      </main>

      <SiteFooter note="LEILA Ratings favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
    </>
  );
}

function Definition({ term, tag, text }: { term: string; tag: string; text: string }) {
  return (
    <article className="methodology-definition">
      <div>
        <h3>{term}</h3>
        <span>{tag}</span>
      </div>
      <p>{text}</p>
    </article>
  );
}
