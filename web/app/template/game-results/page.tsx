/* eslint-disable @next/next/no-img-element */

import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";
import styles from "./page.module.css";

type PercentileTone = "elite" | "good" | "average" | "poor" | "bad" | "neutral";

type StatValue = {
  value: string;
  percentile?: number;
  neutral?: boolean;
};

type StatRow = {
  label: string;
  left: StatValue;
  right: StatValue;
  note?: string;
};

type StatSection = {
  title: string;
  eyebrow?: string;
  rows: StatRow[];
};

const LEFT_TEAM = {
  name: "Michigan",
  short: "MICH",
  teamId: 130,
  score: 27,
  record: "2-0",
};

const RIGHT_TEAM = {
  name: "Oklahoma",
  short: "OU",
  teamId: 201,
  score: 20,
  record: "1-1",
};

const efficiencySections: StatSection[] = [
  {
    title: "Overall Efficiency",
    eyebrow: "What happened",
    rows: [
      { label: "EPA / Play", left: { value: "+0.286", percentile: 91 }, right: { value: "+0.041", percentile: 56 } },
      { label: "Success Rate", left: { value: "49.2%", percentile: 86 }, right: { value: "40.3%", percentile: 43 } },
      { label: "Yards / Play", left: { value: "6.8", percentile: 88 }, right: { value: "5.1", percentile: 47 } },
      { label: "Total EPA", left: { value: "+19.4", percentile: 93 }, right: { value: "+2.7", percentile: 54 } },
    ],
  },
  {
    title: "Passing",
    rows: [
      { label: "EPA / Dropback", left: { value: "+0.34", percentile: 89 }, right: { value: "+0.07", percentile: 57 } },
      { label: "Pass Success", left: { value: "51.7%", percentile: 84 }, right: { value: "42.4%", percentile: 49 } },
      { label: "Yards / Dropback", left: { value: "8.2", percentile: 87 }, right: { value: "6.1", percentile: 52 } },
    ],
  },
  {
    title: "Rushing",
    rows: [
      { label: "EPA / Rush", left: { value: "+0.22", percentile: 85 }, right: { value: "+0.01", percentile: 51 } },
      { label: "Rush Success", left: { value: "47.1%", percentile: 82 }, right: { value: "37.8%", percentile: 38 } },
      { label: "Yards / Rush", left: { value: "5.7", percentile: 81 }, right: { value: "4.2", percentile: 44 } },
    ],
  },
  {
    title: "Down Efficiency",
    rows: [
      { label: "1st Down EPA / Play", left: { value: "+0.31", percentile: 88 }, right: { value: "+0.02", percentile: 51 } },
      { label: "2nd Down EPA / Play", left: { value: "+0.25", percentile: 84 }, right: { value: "+0.09", percentile: 61 } },
      { label: "3rd Down EPA / Play", left: { value: "+0.29", percentile: 82 }, right: { value: "-0.08", percentile: 34 } },
    ],
  },
];

const controlSections: StatSection[] = [
  {
    title: "Drive Production",
    eyebrow: "How it developed",
    rows: [
      { label: "Drives", left: { value: "11", neutral: true }, right: { value: "12", neutral: true } },
      { label: "Points / Drive", left: { value: "2.45", percentile: 79 }, right: { value: "1.67", percentile: 47 } },
      { label: "Yards / Drive", left: { value: "43.7", percentile: 85 }, right: { value: "31.8", percentile: 48 } },
      { label: "Plays / Drive", left: { value: "6.5", percentile: 75 }, right: { value: "5.7", percentile: 48 } },
      { label: "Avg Start", left: { value: "Own 31", neutral: true }, right: { value: "Own 27", neutral: true } },
      { label: "Pts / Scoring Opp", left: { value: "4.8", percentile: 83 }, right: { value: "3.5", percentile: 49 } },
    ],
  },
  {
    title: "Series Control",
    rows: [
      { label: "Series Conversion", left: { value: "67.4%", percentile: 92 }, right: { value: "44.8%", percentile: 38 } },
      { label: "Recovery After Failure", left: { value: "58.3%", percentile: 88 }, right: { value: "31.3%", percentile: 29 } },
      { label: "3rd & Long Exposure", left: { value: "19.4%", percentile: 86 }, right: { value: "37.0%", percentile: 31 }, note: "Lower is better" },
    ],
  },
  {
    title: "Situational",
    rows: [
      { label: "Early Down Success", left: { value: "51.0%", percentile: 86 }, right: { value: "41.2%", percentile: 44 } },
      { label: "3rd Down Success", left: { value: "53.8%", percentile: 84 }, right: { value: "33.3%", percentile: 34 } },
      { label: "4th Down", left: { value: "1 / 1", neutral: true }, right: { value: "1 / 2", neutral: true } },
      { label: "Red Zone TD Rate", left: { value: "75.0%", percentile: 80 }, right: { value: "50.0%", percentile: 47 } },
    ],
  },
];

const explanationSections: StatSection[] = [
  {
    title: "Explosiveness",
    eyebrow: "Why it happened",
    rows: [
      { label: "Explosive Play Rate", left: { value: "13.8%", percentile: 89 }, right: { value: "8.5%", percentile: 55 } },
      { label: "Explosive Plays", left: { value: "9", neutral: true }, right: { value: "5", neutral: true } },
      { label: "Non-Explosive EPA / Play", left: { value: "+0.17", percentile: 90 }, right: { value: "-0.02", percentile: 42 } },
      { label: "Explosive Dependency", left: { value: "43%", neutral: true }, right: { value: "61%", neutral: true }, note: "Style, not quality" },
    ],
  },
  {
    title: "Possession Quality",
    rows: [
      { label: "Clean Drive Rate", left: { value: "63.6%", percentile: 87 }, right: { value: "41.7%", percentile: 36 } },
      { label: "Drive Killer Rate", left: { value: "25.0%", percentile: 84 }, right: { value: "50.0%", percentile: 31 }, note: "Lower is better" },
      { label: "Failure Rate", left: { value: "35.4%", percentile: 79 }, right: { value: "44.1%", percentile: 39 }, note: "Lower is better" },
      { label: "Avg Failure Damage", left: { value: "0.73", percentile: 76 }, right: { value: "1.02", percentile: 33 }, note: "Lower is better" },
      { label: "Failure Burden", left: { value: "0.258", percentile: 82 }, right: { value: "0.450", percentile: 27 }, note: "Lower is better" },
    ],
  },
  {
    title: "Mistakes & Discipline",
    rows: [
      { label: "Havoc Allowed", left: { value: "8.9%", percentile: 88 }, right: { value: "16.9%", percentile: 35 }, note: "Lower is better" },
      { label: "Sacks Taken", left: { value: "1", neutral: true }, right: { value: "4", neutral: true } },
      { label: "TFLs Taken", left: { value: "3", neutral: true }, right: { value: "7", neutral: true } },
      { label: "Turnovers Lost", left: { value: "0", neutral: true }, right: { value: "2", neutral: true } },
      { label: "Turnover EPA Lost", left: { value: "0.0", percentile: 94 }, right: { value: "6.8", percentile: 22 }, note: "Lower is better" },
      { label: "Penalties", left: { value: "4", neutral: true }, right: { value: "7", neutral: true } },
      { label: "Penalty Yards", left: { value: "35", neutral: true }, right: { value: "61", neutral: true } },
    ],
  },
];

function percentileTone(percentile: number | undefined, neutral = false): PercentileTone {
  if (neutral || percentile === undefined) return "neutral";
  if (percentile >= 90) return "elite";
  if (percentile >= 70) return "good";
  if (percentile >= 30) return "average";
  if (percentile >= 10) return "poor";
  return "bad";
}

function ordinal(value: number): string {
  const mod100 = value % 100;
  const mod10 = value % 10;
  if (mod100 >= 11 && mod100 <= 13) return `${value}th`;
  if (mod10 === 1) return `${value}st`;
  if (mod10 === 2) return `${value}nd`;
  if (mod10 === 3) return `${value}rd`;
  return `${value}th`;
}

function ResultValue({ datum }: { datum: StatValue }) {
  const tone = percentileTone(datum.percentile, datum.neutral);
  return (
    <span className={`${styles.resultValue} ${styles[`tone_${tone}`]}`}>
      <strong>{datum.value}</strong>
      {datum.percentile !== undefined && !datum.neutral ? (
        <small>{ordinal(datum.percentile)}</small>
      ) : null}
    </span>
  );
}

function StatSectionBlock({ section }: { section: StatSection }) {
  return (
    <section className={styles.statSection}>
      <div className={styles.sectionTitle}>
        <span>{section.title}</span>
        {section.eyebrow ? <small>{section.eyebrow}</small> : null}
      </div>
      {section.rows.map((row) => (
        <div className={styles.statRow} key={row.label}>
          <ResultValue datum={row.left} />
          <span className={styles.metricLabel}>
            <strong>{row.label}</strong>
            {row.note ? <small>{row.note}</small> : null}
          </span>
          <ResultValue datum={row.right} />
        </div>
      ))}
    </section>
  );
}

function BreakdownColumn({
  title,
  number,
  sections,
}: {
  title: string;
  number: string;
  sections: StatSection[];
}) {
  return (
    <div className={styles.breakdownColumn}>
      <div className={styles.columnHeader}>
        <span className={styles.columnNumber}>{number}</span>
        <strong>{title}</strong>
      </div>
      <div className={styles.teamGuide} aria-hidden="true">
        <span>{LEFT_TEAM.short}</span>
        <span>Metric</span>
        <span>{RIGHT_TEAM.short}</span>
      </div>
      {sections.map((section) => <StatSectionBlock section={section} key={section.title} />)}
    </div>
  );
}

export default function GameResultsTemplatePage() {
  return (
    <>
      <a className="skip-link" href="#gameResultsTemplate">Skip to game results template</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <main id="gameResultsTemplate" className={`container ${styles.page}`}>
        <div className={styles.templateFlag}>
          <span>Template Preview</span>
          <small>Sample data only</small>
        </div>

        <section className={styles.scoreboard} aria-label="Example final score">
          <div className={`${styles.teamScore} ${styles.teamScoreLeft}`}>
            <img src={logoUrl(LEFT_TEAM.teamId, 128)} alt="" />
            <div className={styles.teamIdentity}>
              <span>{LEFT_TEAM.short}</span>
              <strong>{LEFT_TEAM.name}</strong>
              <small>{LEFT_TEAM.record}</small>
            </div>
            <div className={styles.score}>{LEFT_TEAM.score}</div>
          </div>

          <div className={styles.gameMeta}>
            <span>FINAL</span>
            <strong>Week 2</strong>
            <small>Michigan Stadium · Ann Arbor, MI</small>
          </div>

          <div className={`${styles.teamScore} ${styles.teamScoreRight}`}>
            <div className={styles.score}>{RIGHT_TEAM.score}</div>
            <div className={styles.teamIdentity}>
              <span>{RIGHT_TEAM.short}</span>
              <strong>{RIGHT_TEAM.name}</strong>
              <small>{RIGHT_TEAM.record}</small>
            </div>
            <img src={logoUrl(RIGHT_TEAM.teamId, 128)} alt="" />
          </div>
        </section>

        <section className={styles.intro}>
          <div>
            <span className="eyebrow">Final Game Analytics</span>
            <h1>Game Breakdown</h1>
          </div>
          <p>
            One view of the game, without mirroring the same snaps as separate offense and defense stats.
            Percentiles compare each performance with single-game FBS results; descriptive metrics stay neutral.
          </p>
        </section>

        <div className={styles.breakdownGrid}>
          <BreakdownColumn title="Efficiency" number="01" sections={efficiencySections} />
          <BreakdownColumn title="Drives & Control" number="02" sections={controlSections} />
          <BreakdownColumn title="Play Quality & Mistakes" number="03" sections={explanationSections} />
        </div>

        <div className={styles.legend} aria-label="Percentile legend">
          <span>Single-game FBS percentile</span>
          <i className={`${styles.legendDot} ${styles.tone_elite}`} /> <small>90+</small>
          <i className={`${styles.legendDot} ${styles.tone_good}`} /> <small>70–89</small>
          <i className={`${styles.legendDot} ${styles.tone_average}`} /> <small>30–69</small>
          <i className={`${styles.legendDot} ${styles.tone_poor}`} /> <small>10–29</small>
          <i className={`${styles.legendDot} ${styles.tone_bad}`} /> <small>0–9</small>
          <span className={styles.legendNeutral}>Neutral = descriptive / raw count</span>
        </div>
      </main>

      <SiteFooter note="Game Results template preview. Sample values are illustrative and are not tied to a real game dataset." />
    </>
  );
}
