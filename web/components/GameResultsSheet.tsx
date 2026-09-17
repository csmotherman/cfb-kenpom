/* eslint-disable @next/next/no-img-element */
import { logoUrl } from "@/lib/teamCode";
import styles from "./GameResultsSheet.module.css";

export type PercentileTone = "elite" | "good" | "average" | "poor" | "bad" | "neutral";

export type StatValue = {
  value: string;
  percentile?: number;
  neutral?: boolean;
};

export type StatRow = {
  label: string;
  left: StatValue;
  right: StatValue;
  indent?: 0 | 1;
};

export type StatSection = {
  title: string;
  rows: StatRow[];
};

export type GameResultsTeam = {
  name: string;
  short: string;
  teamId: number;
  score: number;
  record: string;
};

export function percentileTone(percentile: number | undefined, neutral = false): PercentileTone {
  if (neutral || percentile === undefined) return "neutral";
  if (percentile >= 90) return "elite";
  if (percentile >= 70) return "good";
  if (percentile >= 30) return "average";
  if (percentile >= 10) return "poor";
  return "bad";
}

function ResultValue({ datum }: { datum: StatValue }) {
  const tone = percentileTone(datum.percentile, datum.neutral);
  return (
    <span className={`${styles.resultValue} ${styles[`tone_${tone}`]}`}>
      <strong>{datum.value}</strong>
    </span>
  );
}

function StatSectionBlock({ section }: { section: StatSection }) {
  return (
    <section className={styles.statSection}>
      <div className={styles.sectionTitle}>{section.title}</div>
      {section.rows.map((row, index) => (
        <div className={styles.statRow} key={`${row.label}-${index}`}>
          <span className={`${styles.metricLabel} ${row.indent ? styles.metricLabelIndented : ""}`}>
            <strong>{row.label}</strong>
          </span>
          <ResultValue datum={row.left} />
          <ResultValue datum={row.right} />
        </div>
      ))}
    </section>
  );
}

function TeamColumnHead({ team }: { team: GameResultsTeam }) {
  return (
    <span className={styles.teamColumnHead}>
      <img src={logoUrl(team.teamId, 64)} alt="" />
      <strong>{team.short}</strong>
    </span>
  );
}

function BreakdownColumn({
  title,
  sections,
  leftTeam,
  rightTeam,
}: {
  title: string;
  sections: StatSection[];
  leftTeam: GameResultsTeam;
  rightTeam: GameResultsTeam;
}) {
  return (
    <div className={styles.breakdownColumn}>
      <div className={styles.columnHeader}>
        <strong>{title}</strong>
        <TeamColumnHead team={leftTeam} />
        <TeamColumnHead team={rightTeam} />
      </div>
      {sections.map((section) => <StatSectionBlock section={section} key={section.title} />)}
    </div>
  );
}

export default function GameResultsSheet({
  leftTeam,
  rightTeam,
  eyebrow = "FINAL",
  gameLabel,
  gameSubLabel,
  heading = "Game Breakdown",
  headingEyebrow = "Final Game Analytics",
  description = "One dense game sheet using LEILA’s advanced and exploratory metrics. Percentiles compare each team’s single-game performance with FBS team-games.",
  columns,
}: {
  leftTeam: GameResultsTeam;
  rightTeam: GameResultsTeam;
  eyebrow?: string;
  gameLabel: string;
  gameSubLabel?: string;
  heading?: string;
  headingEyebrow?: string;
  description?: string;
  columns: { title: string; sections: StatSection[] }[];
}) {
  return (
    <>
      <section className={styles.scoreboard} aria-label="Final score">
        <div className={`${styles.teamScore} ${styles.teamScoreLeft}`}>
          <img src={logoUrl(leftTeam.teamId, 128)} alt="" />
          <div className={styles.teamIdentity}>
            <strong>{leftTeam.name}</strong>
            <small>{leftTeam.record}</small>
          </div>
          <div className={styles.score}>{leftTeam.score}</div>
        </div>

        <div className={styles.gameMeta}>
          <span>{eyebrow}</span>
          <strong>{gameLabel}</strong>
          {gameSubLabel ? <small>{gameSubLabel}</small> : null}
        </div>

        <div className={`${styles.teamScore} ${styles.teamScoreRight}`}>
          <div className={styles.score}>{rightTeam.score}</div>
          <div className={styles.teamIdentity}>
            <strong>{rightTeam.name}</strong>
            <small>{rightTeam.record}</small>
          </div>
          <img src={logoUrl(rightTeam.teamId, 128)} alt="" />
        </div>
      </section>

      <section className={styles.breakdownHeading}>
        <div>
          <span>{headingEyebrow}</span>
          <h1>{heading}</h1>
        </div>
        <p>{description}</p>
      </section>

      <div className={styles.breakdownGrid}>
        {columns.map((column) => (
          <BreakdownColumn key={column.title} title={column.title} sections={column.sections} leftTeam={leftTeam} rightTeam={rightTeam} />
        ))}
      </div>

      <div className={styles.legend} aria-label="Percentile legend">
        <span>Single-game FBS percentile</span>
        <i className={`${styles.legendDot} ${styles.tone_elite}`} /><small>90+</small>
        <i className={`${styles.legendDot} ${styles.tone_good}`} /><small>70&ndash;89</small>
        <i className={`${styles.legendDot} ${styles.tone_average}`} /><small>30&ndash;69</small>
        <i className={`${styles.legendDot} ${styles.tone_poor}`} /><small>10&ndash;29</small>
        <i className={`${styles.legendDot} ${styles.tone_bad}`} /><small>0&ndash;9</small>
      </div>
    </>
  );
}
