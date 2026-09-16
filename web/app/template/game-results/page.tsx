import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import GameResultsSheet, { type StatSection } from "@/components/GameResultsSheet";
import styles from "./page.module.css";

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
    title: "Overall",
    rows: [
      { label: "Plays", left: { value: "68", neutral: true }, right: { value: "71", neutral: true } },
      { label: "EPA / Play", left: { value: "+0.286", percentile: 91 }, right: { value: "+0.041", percentile: 56 } },
      { label: "Success Rate", left: { value: "49.2%", percentile: 86 }, right: { value: "40.3%", percentile: 43 } },
      { label: "Yards / Play", left: { value: "6.8", percentile: 88 }, right: { value: "5.1", percentile: 47 } },
      { label: "Total EPA", left: { value: "+19.4", percentile: 93 }, right: { value: "+2.7", percentile: 54 } },
    ],
  },
  {
    title: "Passing",
    rows: [
      { label: "Dropbacks", left: { value: "31", neutral: true }, right: { value: "38", neutral: true } },
      { label: "Pass Rate", left: { value: "45.6%", neutral: true }, right: { value: "53.5%", neutral: true }, indent: 1 },
      { label: "Passing EPA", left: { value: "+10.5", percentile: 87 }, right: { value: "+2.6", percentile: 57 }, indent: 1 },
      { label: "EPA / Dropback", left: { value: "+0.34", percentile: 89 }, right: { value: "+0.07", percentile: 57 }, indent: 1 },
      { label: "Success Rate", left: { value: "51.7%", percentile: 84 }, right: { value: "42.4%", percentile: 49 }, indent: 1 },
      { label: "Yards / Dropback", left: { value: "8.2", percentile: 87 }, right: { value: "6.1", percentile: 52 }, indent: 1 },
    ],
  },
  {
    title: "Rushing",
    rows: [
      { label: "Rushes", left: { value: "37", neutral: true }, right: { value: "33", neutral: true } },
      { label: "Rush Rate", left: { value: "54.4%", neutral: true }, right: { value: "46.5%", neutral: true }, indent: 1 },
      { label: "Rushing EPA", left: { value: "+8.1", percentile: 84 }, right: { value: "+0.3", percentile: 51 }, indent: 1 },
      { label: "EPA / Rush", left: { value: "+0.22", percentile: 85 }, right: { value: "+0.01", percentile: 51 }, indent: 1 },
      { label: "Success Rate", left: { value: "47.1%", percentile: 82 }, right: { value: "37.8%", percentile: 38 }, indent: 1 },
      { label: "Yards / Rush", left: { value: "5.7", percentile: 81 }, right: { value: "4.2", percentile: 44 }, indent: 1 },
    ],
  },
  {
    title: "By Down",
    rows: [
      { label: "1st Down EPA / Play", left: { value: "+0.31", percentile: 88 }, right: { value: "+0.02", percentile: 51 } },
      { label: "Pass EPA / Play", left: { value: "+0.39", percentile: 90 }, right: { value: "+0.06", percentile: 55 }, indent: 1 },
      { label: "Rush EPA / Play", left: { value: "+0.25", percentile: 84 }, right: { value: "-0.02", percentile: 47 }, indent: 1 },
      { label: "2nd Down EPA / Play", left: { value: "+0.25", percentile: 84 }, right: { value: "+0.09", percentile: 61 } },
      { label: "Pass EPA / Play", left: { value: "+0.30", percentile: 85 }, right: { value: "+0.14", percentile: 65 }, indent: 1 },
      { label: "Rush EPA / Play", left: { value: "+0.19", percentile: 79 }, right: { value: "+0.03", percentile: 53 }, indent: 1 },
      { label: "3rd Down EPA / Play", left: { value: "+0.29", percentile: 82 }, right: { value: "-0.08", percentile: 34 } },
      { label: "Pass EPA / Play", left: { value: "+0.33", percentile: 83 }, right: { value: "-0.11", percentile: 31 }, indent: 1 },
      { label: "Rush EPA / Play", left: { value: "+0.18", percentile: 76 }, right: { value: "+0.01", percentile: 51 }, indent: 1 },
    ],
  },
];

const controlSections: StatSection[] = [
  {
    title: "Drives",
    rows: [
      { label: "Drives", left: { value: "11", neutral: true }, right: { value: "12", neutral: true } },
      { label: "Points / Drive", left: { value: "2.45", percentile: 79 }, right: { value: "1.67", percentile: 47 } },
      { label: "Yards / Drive", left: { value: "43.7", percentile: 85 }, right: { value: "31.8", percentile: 48 } },
      { label: "Plays / Drive", left: { value: "6.5", percentile: 75 }, right: { value: "5.7", percentile: 48 } },
      { label: "Avg Starting Field Position", left: { value: "Own 31", neutral: true }, right: { value: "Own 27", neutral: true } },
      { label: "Scoring Opportunities", left: { value: "6", neutral: true }, right: { value: "4", neutral: true } },
      { label: "Points / Opportunity", left: { value: "4.8", percentile: 83 }, right: { value: "3.5", percentile: 49 }, indent: 1 },
      { label: "Possession Share", left: { value: "53.8%", neutral: true }, right: { value: "46.2%", neutral: true } },
    ],
  },
  {
    title: "Series Control",
    rows: [
      { label: "Series Conversion", left: { value: "67.4%", percentile: 92 }, right: { value: "44.8%", percentile: 38 } },
      { label: "Recovery Rate", left: { value: "58.3%", percentile: 88 }, right: { value: "31.3%", percentile: 29 }, indent: 1 },
      { label: "3rd & Long Exposure", left: { value: "19.4%", percentile: 86 }, right: { value: "37.0%", percentile: 31 }, indent: 1 },
    ],
  },
  {
    title: "Situational",
    rows: [
      { label: "Early Down EPA / Play", left: { value: "+0.30", percentile: 87 }, right: { value: "+0.05", percentile: 56 } },
      { label: "Early Down Success", left: { value: "51.0%", percentile: 86 }, right: { value: "41.2%", percentile: 44 }, indent: 1 },
      { label: "Late Down EPA / Play", left: { value: "+0.22", percentile: 78 }, right: { value: "-0.06", percentile: 37 } },
      { label: "Late Down Success", left: { value: "45.5%", percentile: 74 }, right: { value: "31.6%", percentile: 30 }, indent: 1 },
      { label: "3rd Down EPA / Play", left: { value: "+0.29", percentile: 82 }, right: { value: "-0.08", percentile: 34 } },
      { label: "3rd Down Success", left: { value: "53.8%", percentile: 84 }, right: { value: "33.3%", percentile: 34 }, indent: 1 },
      { label: "4th Down", left: { value: "1 / 1", neutral: true }, right: { value: "1 / 2", neutral: true } },
      { label: "Red Zone Success", left: { value: "75.0%", percentile: 80 }, right: { value: "50.0%", percentile: 47 } },
    ],
  },
];

const explanationSections: StatSection[] = [
  {
    title: "Explosiveness",
    rows: [
      { label: "Explosive Play Rate", left: { value: "13.8%", percentile: 89 }, right: { value: "8.5%", percentile: 55 } },
      { label: "Explosive Plays", left: { value: "9", neutral: true }, right: { value: "5", neutral: true } },
      { label: "Explosive Pass Rate", left: { value: "16.1%", percentile: 91 }, right: { value: "10.5%", percentile: 61 }, indent: 1 },
      { label: "Explosive Rush Rate", left: { value: "11.9%", percentile: 83 }, right: { value: "6.1%", percentile: 42 }, indent: 1 },
      { label: "EPA / Play w/o Explosives", left: { value: "+0.17", percentile: 90 }, right: { value: "-0.02", percentile: 42 } },
      { label: "Explosive Dependency", left: { value: "43%", neutral: true }, right: { value: "61%", neutral: true } },
    ],
  },
  {
    title: "Possession Quality",
    rows: [
      { label: "Clean Drive Rate", left: { value: "63.6%", percentile: 87 }, right: { value: "41.7%", percentile: 36 } },
      { label: "Drive Killer Rate", left: { value: "25.0%", percentile: 84 }, right: { value: "50.0%", percentile: 31 } },
      { label: "Failure Rate", left: { value: "35.4%", percentile: 79 }, right: { value: "44.1%", percentile: 39 }, indent: 1 },
      { label: "Avg Failure Damage", left: { value: "0.73", percentile: 76 }, right: { value: "1.02", percentile: 33 }, indent: 1 },
      { label: "Failure Burden", left: { value: "0.258", percentile: 82 }, right: { value: "0.450", percentile: 27 }, indent: 1 },
      { label: "Failure Pressure", left: { value: "0.31", percentile: 80 }, right: { value: "0.52", percentile: 24 }, indent: 1 },
    ],
  },
  {
    title: "Disruption",
    rows: [
      { label: "Havoc Allowed", left: { value: "8.9%", percentile: 88 }, right: { value: "16.9%", percentile: 35 } },
      { label: "Sacks Taken", left: { value: "1", neutral: true }, right: { value: "4", neutral: true }, indent: 1 },
      { label: "TFLs Taken", left: { value: "3", neutral: true }, right: { value: "7", neutral: true }, indent: 1 },
    ],
  },
  {
    title: "Turnovers",
    rows: [
      { label: "Turnovers Lost", left: { value: "0", neutral: true }, right: { value: "2", neutral: true } },
      { label: "Interceptions", left: { value: "0", neutral: true }, right: { value: "1", neutral: true }, indent: 1 },
      { label: "Fumbles Lost", left: { value: "0", neutral: true }, right: { value: "1", neutral: true }, indent: 1 },
      { label: "Turnover Rate", left: { value: "0.0%", percentile: 94 }, right: { value: "2.8%", percentile: 30 }, indent: 1 },
      { label: "Turnover EPA Lost", left: { value: "0.0", percentile: 94 }, right: { value: "6.8", percentile: 22 }, indent: 1 },
    ],
  },
  {
    title: "Penalties",
    rows: [
      { label: "Penalties", left: { value: "4", neutral: true }, right: { value: "7", neutral: true } },
      { label: "Penalty Yards", left: { value: "35", neutral: true }, right: { value: "61", neutral: true }, indent: 1 },
      { label: "Penalty Rate", left: { value: "5.9%", percentile: 76 }, right: { value: "9.9%", percentile: 33 }, indent: 1 },
      { label: "Penalty Yards / Drive", left: { value: "3.2", percentile: 81 }, right: { value: "5.1", percentile: 38 }, indent: 1 },
    ],
  },
];

export default function GameResultsTemplatePage() {
  return (
    <>
      <a className="skip-link" href="#gameResultsTemplate">Skip to game results template</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <main id="gameResultsTemplate" className={`container ${styles.page}`}>
        <div className={styles.templateFlag}>
          <span>Game Results Template</span>
          <small>Sample data</small>
        </div>

        <GameResultsSheet
          leftTeam={LEFT_TEAM}
          rightTeam={RIGHT_TEAM}
          gameLabel="Week 2"
          gameSubLabel="Michigan Stadium · Ann Arbor, MI"
          columns={[
            { title: "Efficiency", sections: efficiencySections },
            { title: "Control & Situations", sections: controlSections },
            { title: "Game Shape", sections: explanationSections },
          ]}
        />
      </main>

      <SiteFooter note="Game Results template preview. Sample values are illustrative and are not tied to a real game dataset." />
    </>
  );
}
