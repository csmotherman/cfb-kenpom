// Nickname for each FBS program, used only to build readable team titles ("Michigan Wolverines").
// Any team missing here simply falls back to its plain name, so a new program never produces a wrong title.
const MASCOTS: Record<string, string> = {
  "Air Force": "Falcons", Akron: "Zips", Alabama: "Crimson Tide", "App State": "Mountaineers", Arizona: "Wildcats",
  "Arizona State": "Sun Devils", Arkansas: "Razorbacks", "Arkansas State": "Red Wolves", Army: "Black Knights", Auburn: "Tigers",
  BYU: "Cougars", "Ball State": "Cardinals", Baylor: "Bears", "Boise State": "Broncos", "Boston College": "Eagles",
  "Bowling Green": "Falcons", Buffalo: "Bulls", California: "Golden Bears", "Central Michigan": "Chippewas", Charlotte: "49ers",
  Cincinnati: "Bearcats", Clemson: "Tigers", "Coastal Carolina": "Chanticleers", Colorado: "Buffaloes", "Colorado State": "Rams",
  Delaware: "Fightin' Blue Hens", Duke: "Blue Devils", "East Carolina": "Pirates", "Eastern Michigan": "Eagles", Florida: "Gators",
  "Florida Atlantic": "Owls", "Florida International": "Panthers", "Florida State": "Seminoles", "Fresno State": "Bulldogs",
  Georgia: "Bulldogs", "Georgia Southern": "Eagles", "Georgia State": "Panthers", "Georgia Tech": "Yellow Jackets",
  "Hawai'i": "Rainbow Warriors", Houston: "Cougars", Idaho: "Vandals", Illinois: "Fighting Illini", Indiana: "Hoosiers",
  Iowa: "Hawkeyes", "Iowa State": "Cyclones", "Jacksonville State": "Gamecocks", "James Madison": "Dukes", Kansas: "Jayhawks",
  "Kansas State": "Wildcats", "Kennesaw State": "Owls", "Kent State": "Golden Flashes", Kentucky: "Wildcats", LSU: "Tigers",
  Liberty: "Flames", Louisiana: "Ragin' Cajuns", "Louisiana Tech": "Bulldogs", Louisville: "Cardinals", Marshall: "Thundering Herd",
  Maryland: "Terrapins", Massachusetts: "Minutemen", Memphis: "Tigers", Miami: "Hurricanes", "Miami (OH)": "RedHawks",
  Michigan: "Wolverines", "Michigan State": "Spartans", "Middle Tennessee": "Blue Raiders", Minnesota: "Golden Gophers",
  "Mississippi State": "Bulldogs", Missouri: "Tigers", "Missouri State": "Bears", "NC State": "Wolfpack", Navy: "Midshipmen",
  Nebraska: "Cornhuskers", Nevada: "Wolf Pack", "New Mexico": "Lobos", "New Mexico State": "Aggies", "North Carolina": "Tar Heels",
  "North Dakota State": "Bison", "North Texas": "Mean Green", "Northern Illinois": "Huskies", Northwestern: "Wildcats",
  "Notre Dame": "Fighting Irish", Ohio: "Bobcats", "Ohio State": "Buckeyes", Oklahoma: "Sooners", "Oklahoma State": "Cowboys",
  "Old Dominion": "Monarchs", "Ole Miss": "Rebels", Oregon: "Ducks", "Oregon State": "Beavers", "Penn State": "Nittany Lions",
  Pittsburgh: "Panthers", Purdue: "Boilermakers", Rice: "Owls", Rutgers: "Scarlet Knights", SMU: "Mustangs",
  "Sacramento State": "Hornets", "Sam Houston": "Bearkats", "San Diego State": "Aztecs", "San José State": "Spartans",
  "South Alabama": "Jaguars", "South Carolina": "Gamecocks", "South Florida": "Bulls", "Southern Miss": "Golden Eagles",
  Stanford: "Cardinal", Syracuse: "Orange", TCU: "Horned Frogs", Temple: "Owls", Tennessee: "Volunteers", Texas: "Longhorns",
  "Texas A&M": "Aggies", "Texas State": "Bobcats", "Texas Tech": "Red Raiders", Toledo: "Rockets", Troy: "Trojans",
  Tulane: "Green Wave", Tulsa: "Golden Hurricane", UAB: "Blazers", UCF: "Knights", UCLA: "Bruins", UConn: "Huskies",
  "UL Monroe": "Warhawks", UNLV: "Rebels", USC: "Trojans", UTEP: "Miners", UTSA: "Roadrunners", Utah: "Utes",
  "Utah State": "Aggies", Vanderbilt: "Commodores", Virginia: "Cavaliers", "Virginia Tech": "Hokies", "Wake Forest": "Demon Deacons",
  Washington: "Huskies", "Washington State": "Cougars", "West Virginia": "Mountaineers", "Western Kentucky": "Hilltoppers",
  "Western Michigan": "Broncos", Wisconsin: "Badgers", Wyoming: "Cowboys",
};

export function teamMascot(team: string): string | null {
  return MASCOTS[team] ?? null;
}

/** "Michigan Wolverines", or just the school name when no nickname is on file. */
export function fullTeamName(team: string): string {
  const mascot = teamMascot(team);
  return mascot ? `${team} ${mascot}` : team;
}

const CONFERENCES: Record<string, string> = {
  B1G: "Big Ten", SEC: "SEC", ACC: "ACC", B12: "Big 12", SBC: "Sun Belt", AAC: "American Athletic", MAC: "Mid-American",
  MWC: "Mountain West", CUSA: "Conference USA", PAC: "Pac-12", IND: "Independent",
};

/** Readable conference name for the abbreviations used in the published data. */
export function conferenceName(abbreviation: string | null | undefined): string {
  if (!abbreviation) return "Independent";
  return CONFERENCES[abbreviation] ?? abbreviation;
}

// Conferences that get their own hub page (enough rated teams for a meaningful ratings table). Independents do not.
const CONFERENCE_SLUGS: Record<string, string> = {
  SEC: "sec", B1G: "big-ten", ACC: "acc", B12: "big-12", SBC: "sun-belt", AAC: "american-athletic", MAC: "mid-american",
  MWC: "mountain-west", CUSA: "conference-usa", PAC: "pac-12",
};

export function conferenceSlug(abbreviation: string | null | undefined): string | null {
  return abbreviation ? CONFERENCE_SLUGS[abbreviation] ?? null : null;
}

export function conferenceFromSlug(slug: string): string | null {
  return Object.entries(CONFERENCE_SLUGS).find(([, value]) => value === slug)?.[0] ?? null;
}

export const CONFERENCE_CODES = Object.keys(CONFERENCE_SLUGS);
