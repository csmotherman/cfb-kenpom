// Ported verbatim from site/site.js CFF.teamCode -- compact display aliases
// following CFBD/ESPN-style team abbreviations.
const CODES: Record<string, string> = {
  "Air Force": "AFA", Akron: "AKR", Alabama: "ALA", "App State": "APP",
  "Appalachian State": "APP", Arizona: "ARIZ", "Arizona State": "ASU",
  Arkansas: "ARK", "Arkansas State": "ARST", Army: "ARMY", Auburn: "AUB",
  BYU: "BYU", "Ball State": "BALL", Baylor: "BAY", "Boise State": "BOIS",
  "Boston College": "BC", "Bowling Green": "BGSU", Buffalo: "BUF",
  California: "CAL", "Central Michigan": "CMU", Charlotte: "CLT",
  Cincinnati: "CIN", Clemson: "CLEM", "Coastal Carolina": "CCU",
  Colorado: "COLO", "Colorado State": "CSU", Delaware: "DEL", Duke: "DUKE",
  "East Carolina": "ECU", "Eastern Michigan": "EMU", Florida: "FLA",
  "Florida Atlantic": "FAU", "Florida International": "FIU", "Florida State": "FSU",
  "Fresno State": "FRES", Georgia: "UGA", "Georgia Southern": "GASO",
  "Georgia State": "GAST", "Georgia Tech": "GT", "Hawai'i": "HAW", Hawaii: "HAW",
  Houston: "HOU", Illinois: "ILL", Indiana: "IND", Iowa: "IOWA",
  "Iowa State": "ISU", "Jacksonville State": "JVST", "James Madison": "JMU",
  Kansas: "KU", "Kansas State": "KSU", "Kennesaw State": "KENN", "Kent State": "KENT",
  Kentucky: "UK", LSU: "LSU", Liberty: "LIB", Louisiana: "UL",
  "Louisiana Tech": "LT", Louisville: "LOU", Marshall: "MRSH", Maryland: "MD",
  Massachusetts: "MASS", Memphis: "MEM", Miami: "MIA", "Miami (OH)": "M-OH",
  Michigan: "MICH", "Michigan State": "MSU", "Middle Tennessee": "MTSU",
  Minnesota: "MINN", "Mississippi State": "MSST", Missouri: "MIZ",
  "Missouri State": "MOST", "NC State": "NCST", Navy: "NAVY", Nebraska: "NEB",
  Nevada: "NEV", "New Mexico": "UNM", "New Mexico State": "NMSU",
  "North Carolina": "UNC", "North Dakota State": "NDSU", "North Texas": "UNT",
  "Northern Illinois": "NIU", Northwestern: "NU", "Notre Dame": "ND", Ohio: "OHIO",
  "Ohio State": "OSU", Oklahoma: "OU", "Oklahoma State": "OKST", "Old Dominion": "ODU",
  "Ole Miss": "MISS", Oregon: "ORE", "Oregon State": "ORST", "Penn State": "PSU",
  Pittsburgh: "PITT", Purdue: "PUR", Rice: "RICE", Rutgers: "RUTG",
  SMU: "SMU", "Sacramento State": "SAC", "Sam Houston": "SHSU",
  "San Diego State": "SDSU", "San José State": "SJSU", "San Jose State": "SJSU",
  "South Alabama": "USA", "South Carolina": "SC", "South Florida": "USF",
  "Southern Miss": "USM", Stanford: "STAN", Syracuse: "SYR", TCU: "TCU",
  Temple: "TEM", Tennessee: "TENN", Texas: "TEX", "Texas A&M": "TAMU",
  "Texas State": "TXST", "Texas Tech": "TTU", Toledo: "TOL", Troy: "TROY",
  Tulane: "TULN", Tulsa: "TLSA", UAB: "UAB", UCF: "UCF", UCLA: "UCLA",
  UConn: "CONN", "UL Monroe": "ULM", UNLV: "UNLV", USC: "USC", UTEP: "UTEP",
  UTSA: "UTSA", Utah: "UTAH", "Utah State": "USU", Vanderbilt: "VAN",
  Virginia: "UVA", "Virginia Tech": "VT", "Wake Forest": "WAKE", Washington: "WASH",
  "Washington State": "WSU", "West Virginia": "WVU", "Western Kentucky": "WKU",
  "Western Michigan": "WMU", Wisconsin: "WIS", Wyoming: "WYO",
};

export function teamCode(team: string): string {
  if (CODES[team]) return CODES[team];
  const clean = String(team || "").replace(/[^A-Za-z0-9 ]/g, " ").trim();
  const words = clean.split(/\s+/).filter(Boolean);
  if (!words.length) return "TEAM";
  if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
  const acronym = words.map((w) => w.charAt(0)).join("").toUpperCase();
  return acronym.slice(0, 5);
}

export function logoUrl(teamId: number | string, size = 64): string {
  return `https://cdn.collegefootballdata.com/logos/${size}/${teamId}.png`;
}
