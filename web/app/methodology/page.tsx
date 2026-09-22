import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = pageMetadata({
  title: "College Football Ratings Methodology",
  description: "How PRIME builds opponent-adjusted college football ratings, strength of schedule and record, advanced stats and predictions, and what each number means.",
  path: "/methodology",
});

export default function MethodologyPage() {
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/methodology", name: "College Football Ratings Methodology", description: "How PRIME builds opponent-adjusted college football ratings, strength of schedule and record, advanced stats and predictions." }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Methodology", path: "/methodology" }]),
      ]} />
      <a className="skip-link" href="#methodologyContent">Skip to methodology</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />

      <main id="methodologyContent" className="container methodology-main">
        <header className="methodology-hero">
          <span className="eyebrow">PRIME Football Methodology</span>
          <h1>What the numbers actually mean</h1>
          <p>
            PRIME Football is built to describe team strength from real games, not recreate a poll. The core ratings account for opponent quality so the same statistical performance is treated differently against a strong opponent than against a weak one.
          </p>
        </header>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Core</span>
            <h2>PRIME Ratings</h2>
          </div>
          <p>
            Possession efficiency remains the backbone of PRIME&rsquo;s rating system, but PRIME v6 combines three opponent-adjusted components: field-position-adjusted scoring value per resolved possession, Success Rate, and Explosiveness. The live blend was selected from a leakage-safe 2014&ndash;2025 walk-forward test; EPA was also tested but did not add meaningful incremental signal once Success Rate and Explosiveness were included. Net Rating is the overall team-strength metric, while Off Rating and Def Rating are its offensive and defensive sides. A team&rsquo;s own rating is never blended with a preseason rating, recruiting input or conference-strength term. During the first three site weeks only, the possession component&rsquo;s opponent-strength adjustment is stabilized with a tapered prior-season opponent baseline; that influence is 50% through Week 2, 25% in Week 3 and 0% from Week 4 onward.
          </p>
          <div className="methodology-definitions">
            <Definition term="PRIME Rating" tag="System" text="PRIME’s opponent-adjusted performance system. Possession efficiency is the backbone, with validated Success Rate and Explosiveness components added in PRIME v6." />
            <Definition term="Net Rating" tag="Overall" text="The overall team-strength rating. Net Rating = Off Rating + Def Rating. Zero is approximately FBS average; higher is better." />
            <Definition term="Off Rating" tag="Core" text="Offensive composite of field-position-adjusted possession efficiency, opponent-adjusted Success Rate and opponent-adjusted Explosiveness. Higher is better." />
            <Definition term="Def Rating" tag="Core" text="Defensive composite of possession scoring prevention, opponent-adjusted Success Rate prevention and opponent-adjusted Explosiveness prevention. Higher is better." />
            <Definition term="SOS" tag="Context" text="Strength of schedule, based on the strength of opponents played through the selected rating snapshot." />
            <Definition term="SOR" tag="Résumé" text="Strength of Record: wins above what an exactly-average FBS team would be expected to earn against the same schedule. It answers a résumé question, separate from Net Rating's performance question." />
            <Definition term="ASM" tag="Résumé" text="Adjusted Score Matrix: an opponent-adjusted scoring-margin rating (constrained least squares), with each game's margin capped at 28 points before fitting so a blowout can't dominate a team's number. A résumé lens like SOR, not a second opinion on who's better -- see &ldquo;Process vs. résumé&rdquo; below. Shown on Advanced, not the main Ratings page." />
          </div>
        </section>

        <section className="methodology-section">
          <div className="methodology-section__heading">
            <span className="eyebrow">Reading The Ratings</span>
            <h2>Process vs. résumé</h2>
          </div>
          <p>
            Net Rating is the primary opponent-adjusted team-strength rating. It is not a final-score rating: the backbone is field-position-adjusted offensive drive value per resolved possession, solved recursively across the FBS opponent network. PRIME v6 then adds opponent-adjusted Success Rate and Explosiveness using frozen weights validated on 2014&ndash;2025 walk-forward results. EPA was tested in the same framework but excluded from the live blend because it added almost no independent signal once those two play-level components were present. Net Rating equals Off Rating plus Def Rating. ASM is intentionally different: it is an opponent-adjusted scoring-margin r&eacute;sum&eacute; lens with each game&rsquo;s margin capped at 28 points.
          </p>
        </section>

        <section className="methodology-section methodology-two-column">
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Team Profiles</span>
              <h2>Raw vs adjusted</h2>
            </div>
            <p>
              PRIME Football does not label every number opponent-adjusted. Public team profiles include season-to-date raw football results such as success rate, pass/rush success, yards per play, explosiveness and tendencies. Net Rating and fields explicitly labeled as adjusted are model-based opponent-adjusted snapshots.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">Advanced</span>
              <h2>Week ranges</h2>
            </div>
            <p>
              Metrics built from additive weekly counts can be recalculated for a selected range. Model ratings are snapshots and cannot honestly be added or averaged across arbitrary weeks, so PRIME Football keeps those two classes separate instead of pretending every column is rangeable.
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
              PRIME Football uses chronological site weeks. Early opener games that occur several days before the main Week 1 slate are separated into Week 0 so the interface follows how fans actually experience the season instead of forcing every early game into one label.
            </p>
          </div>
          <div>
            <div className="methodology-section__heading">
              <span className="eyebrow">This Week</span>
              <h2>Pregame snapshots</h2>
            </div>
            <p>
              Weekly matchup pages use the latest overall rating snapshot strictly before the selected game week. That prevents the matchup page from quietly using the result it is supposed to be previewing.
            </p>
          </div>
        </section>

        <section className="methodology-section" id="metric-versions">
          <div className="methodology-section__heading">
            <span className="eyebrow">Historical comparability</span>
            <h2>Metric versions by era</h2>
          </div>
          <div className="methodology-rules">
            <p><strong>What this means.</strong> Some definitions changed during the 2026 season build, and history has not been rebuilt on them yet. Values are consistent within an era but are not directly comparable across eras, so treat comparisons such as a 2026 team against a 2021 team as approximate.</p>
            <p><strong>Ratings (Net, Off, Def).</strong> 2014&ndash;2025 historical files remain on their original possession-efficiency versions. 2026 uses PRIME v6: field-position-adjusted possession efficiency plus opponent-adjusted Success Rate and Explosiveness. Cross-era comparisons should therefore be treated as approximate until history is rebuilt on the v6 definition.</p>
            <p><strong>SOS and SOR.</strong> 2014&ndash;2025 use the original schedule-strength and record measures (v1). 2026 uses v2: SOS is the average Net Rating of opponents, and SOR is wins above what an average FBS team would expect against the same schedule.</p>
            <p><strong>Explosive rate.</strong> 2014&ndash;2025 use the original definition. 2026 counts a play as explosive when it is successful and gains at least 15 yards on a pass or 10 on a rush, so levels are not comparable across the boundary.</p>
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
            <p><strong>No fake probability precision.</strong> PRIME Football will not publish a model win probability as calibrated until calibration has actually been validated.</p>
            <p><strong>Misses stay visible.</strong> The long-term goal is a public prediction archive so users can inspect both correct calls and misses.</p>
          </div>
        </section>

        <section className="methodology-section methodology-actions">
          <div>
            <span className="eyebrow">Use PRIME Football</span>
            <h2>Start with the football</h2>
            <p>Check the national ratings, then open the weekly slate to see how the teams in this weekend&rsquo;s games compare before kickoff.</p>
          </div>
          <div className="methodology-actions__links">
            <Link href="/">View ratings →</Link>
            <Link href="/predictions">Open Predictions →</Link>
          </div>
        </section>
      </main>

      <SiteFooter note="PRIME Football favors explicit definitions over invented completeness. Research-stage metrics stay labeled, missing data stays missing, and predictive claims are separated from descriptive ratings." />
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
