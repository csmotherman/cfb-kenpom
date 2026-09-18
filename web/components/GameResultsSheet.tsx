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
  // The matchup page supplies the leakage-safe PRE-game record snapshot.
  // This component is only used for a completed game, so it advances that
  // record exactly once using the final score before displaying it.
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

export function postgameRecord(pregameRecord: string, score: number, opponentScore: number): string {
  const match = pregameRecord.trim().match(/^(\d+)-(\d+)(?:-(\d+))?$/);
  if (!match) return pregameRecord;
  let wins = Number.parseInt(match[1], 10);
  let losses = Number.parseInt(match[2], 10);
  let ties = match[3] ? Number.parseInt(match[3], 10) : 0;

  if (score > opponentScore) wins += 1;
  else if (score < opponentScore) losses += 1;
  else ties += 1;

  return ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`;
}

function ResultValue({ datum }: { datum: StatValue }) {
  const tone = percentileTone(datum.percentile, datum.neutral);
  const marker = tone === "elite" || tone === "good"
    ? "▲"
    : tone === "poor" || tone === "bad"
      ? "▼"
      : null;

  return (
    <span className={`${styles.resultValue} ${styles[`tone_${tone}`]}`}>
      {marker ? <span className={styles.toneMarker} aria-hidden="true">{marker}</span> : null}
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
  description = "Official box-score facts are shown separately from LEILA’s advanced metrics. Color applies only to LEILA performance metrics against the historical FBS-vs-FBS single-game baseline.",
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
  const leftPostgameRecord = postgameRecord(leftTeam.record, leftTeam.score, rightTeam.score);
  const rightPostgameRecord = postgameRecord(rightTeam.record, rightTeam.score, leftTeam.score);

  return (
    <>
      <section className={styles.scoreboard} aria-label="Final score">
        <div className={`${styles.teamScore} ${styles.teamScoreLeft}`}>
          <img src={logoUrl(leftTeam.teamId, 128)} alt="" />
          <div className={styles.teamIdentity}>
            <strong>{leftTeam.name}</strong>
            <small>{leftPostgameRecord}</small>
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
            <small>{rightPostgameRecord}</small>
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

      <div className={styles.legend} aria-label="Historical percentile legend">
        <span>Historical FBS game percentile</span>
        <i className={`${styles.legendDot} ${styles.tone_elite}`} /><small>▲ 90+</small>
        <i className={`${styles.legendDot} ${styles.tone_good}`} /><small>▲ 70&ndash;89</small>
        <i className={`${styles.legendDot} ${styles.tone_average}`} /><small>30&ndash;69</small>
        <i className={`${styles.legendDot} ${styles.tone_poor}`} /><small>▼ 10&ndash;29</small>
        <i className={`${styles.legendDot} ${styles.tone_bad}`} /><small>▼ 0&ndash;9</small>
      </div>
    </>
  );
}
