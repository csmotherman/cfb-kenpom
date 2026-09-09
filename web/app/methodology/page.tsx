import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = {
  title: "Methodology | GRID",
  description: "How GRID builds opponent-adjusted college football ratings, team profiles, weekly matchup snapshots, and model research.",
};

export default function MethodologyPage() {
  return (
    <>
      <a className="skip-link" href="#methodologyContent">Skip to methodology</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="methodologyContent" className="container methodology-main">
        <header className="methodology-hero">
          <span className="eyebrow">GRID Methodology</span>
          <h1>What the numbers actually mean</h1>
          <p>
            GRID is built to describe team strength from real games, not recreate a poll. The core ratings account for opponent quality so the same statistical performance is treated differently against a strong opponent than against a weak one.
          </p>
        </header>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Core</span>
            <h2>Ratings</h2>
          </div>
          <div className="methodology-definitions">
            <Definition term="AdjNet" tag="Core" text="Adjusted Net Rating. GRID's overall opponent-adjusted measure of how strongly a team has performed. Higher is better." />
            <Definition term="AdjOff" tag="Core" text="Opponent-adjusted offensive performance. Higher means the offense has performed better after accounting for the defenses it faced." />
            <Definition term="AdjDef" tag="Core" text="Opponent-adjusted defensive performance. It is oriented so higher is better for defense too." />
            <Definition term="SOS" tag="Context" text="Strength of schedule, based on the strength of opponents played through the selected rating snapshot." />
            <Definition term="SOR" tag="Résumé" text="Strength of Record: wins above what an exactly-average FBS team would be expected to earn against the same schedule. It answers a résumé question, separate from AdjNet's performance question." />
          </div>
        </section>

        <section className="methodology-section methodology-two-column">
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Team Profiles</span>
              <h2>Raw vs adjusted</h2>
            </div>
            <p>
              GRID does not label every number opponent-adjusted. Public team profiles include season-to-date raw football results such as success rate, pass/rush success, yards per play, explosiveness and tendencies. AdjNet and fields explicitly labeled as adjusted are model-based opponent-adjusted snapshots.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Advanced</span>
              <h2>Week ranges</h2>
            </div>
            <p>
              Metrics built from additive weekly counts can be recalculated for a selected range. Model ratings are snapshots and cannot honestly be added or averaged across arbitrary weeks, so GRID keeps those two classes separate instead of pretending every column is rangeable.
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
              GRID uses chronological site weeks. Early opener games that occur several days before the main Week 1 slate are separated into Week 0 so the interface follows how fans actually experience the season instead of forcing every early game into one label.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">This Week</span>
              <h2>Pregame snapshots</h2>
            </div>
            <p>
              Weekly matchup pages use the latest GRID rating snapshot strictly before the selected game week. That prevents the matchup page from quietly using the result it is supposed to be previewing.
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
            <p><strong>No fake probability precision.</strong> GRID will not publish a model win probability as calibrated until calibration has actually been validated.</p>
            <p><strong>Misses stay visible.</strong> The long-term goal is a public prediction archive so users can inspect both correct calls and misses.</p>
          </div>
        </section>

        <section className="methodology-section methodology-actions">
          <div>
            <span className="eyebrow">Use GRID</span>
            <h2>Start with the football</h2>
            <p>Check the national ratings, then open the weekly slate to see how the teams in this weekend&rsquo;s games compare before kickoff.</p>
          </div>
          <div className="methodology-actions__links">
            <Link href="/">View ratings →</Link>
            <Link href="/this-week">Open This Week →</Link>
          </div>
        </section>
      </main>

      <SiteFooter note="GRID favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
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
