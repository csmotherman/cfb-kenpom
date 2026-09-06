(function () {
  function na(v) {
    return v === null || v === undefined || Number.isNaN(v);
  }

  function signed(n, digits) {
    if (na(n)) return "—";
    return (n >= 0 ? "+" : "") + n.toFixed(digits === undefined ? 1 : digits);
  }

  function logoUrl(teamId) {
    return "https://cdn.collegefootballdata.com/logos/256/" + teamId + ".png";
  }

  function statCell(value, rankValue, primary, useSign, digits) {
    var td = document.createElement("td");
    td.className = "num stat-cell" + (primary ? " primary" : "");
    var text;
    if (na(value)) {
      text = "—";
    } else if (useSign) {
      text = (value >= 0 ? "+" : "") + value.toFixed(digits === undefined ? 1 : digits);
    } else {
      text = value.toFixed(digits === undefined ? 1 : digits);
    }
    td.appendChild(document.createTextNode(text));
    if (rankValue !== undefined && rankValue !== null) {
      var sub = document.createElement("span");
      sub.className = "rank-sub";
      sub.textContent = " (" + rankValue + ")";
      td.appendChild(sub);
    }
    return td;
  }

  function cell(className, text) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text;
    return td;
  }

  var slug = new URLSearchParams(window.location.search).get("team");
  var years = (window.CFB_YEARS || []).slice().sort(function (a, b) { return b - a; });
  var content = document.getElementById("teamContent");

  var seasons = [];
  years.forEach(function (year) {
    var weeks = (window.CFB_WEEKS || {})[String(year)] || [];
    var finalWeek = weeks[weeks.length - 1];
    var rows = ((window.CFB_DATA[String(year)] || {})[String(finalWeek)]) || [];
    var match = rows.filter(function (t) { return t.slug === slug; })[0];
    if (match) seasons.push(Object.assign({ year: year, finalWeek: finalWeek }, match));
  });

  if (!slug || seasons.length === 0) {
    var notFound = document.createElement("div");
    notFound.className = "not-found";
    notFound.innerHTML = 'Team not found. <a href="index.html">Back to all teams &rarr;</a>';
    content.appendChild(notFound);
    return;
  }

  var latest = seasons[0];
  document.title = latest.team + " — CollegeFootballFocus";

  var breadcrumbs = document.getElementById("breadcrumbs");
  if (breadcrumbs) {
    breadcrumbs.innerHTML = "";
    var crumbTeams = document.createElement("a");
    crumbTeams.href = "index.html";
    crumbTeams.textContent = "Teams";
    breadcrumbs.appendChild(crumbTeams);

    var sep1 = document.createElement("span");
    sep1.className = "crumb-sep";
    sep1.textContent = "/";
    breadcrumbs.appendChild(sep1);

    var crumbConf = document.createElement("a");
    crumbConf.href = "index.html?q=" + encodeURIComponent(latest.conf);
    crumbConf.textContent = latest.conf;
    breadcrumbs.appendChild(crumbConf);

    var sep2 = document.createElement("span");
    sep2.className = "crumb-sep";
    sep2.textContent = "/";
    breadcrumbs.appendChild(sep2);

    var crumbTeam = document.createElement("span");
    crumbTeam.className = "crumb-current";
    crumbTeam.textContent = latest.team;
    breadcrumbs.appendChild(crumbTeam);
  }

  var hero = document.createElement("section");
  hero.className = "team-hero";

  var img = document.createElement("img");
  img.className = "team-hero__logo";
  img.src = logoUrl(latest.teamId);
  img.alt = "";
  img.onerror = function () { img.style.visibility = "hidden"; };
  hero.appendChild(img);

  var info = document.createElement("div");
  info.className = "team-hero__info";

  var conf = document.createElement("span");
  conf.className = "eyebrow";
  conf.textContent = latest.conf + " · " + latest.year + " (through Wk " + latest.finalWeek + ")";
  info.appendChild(conf);

  var name = document.createElement("h1");
  name.className = "team-hero__name";
  name.textContent = latest.team;
  info.appendChild(name);

  var current = document.createElement("div");
  current.className = "team-hero__current";
  current.innerHTML =
    "Rank <b>" + (na(latest.rank) ? "—" : latest.rank) + "</b> &middot; AdjEM <b>" + signed(latest.adjEM) +
    "</b> &middot; " + latest.record;
  info.appendChild(current);

  var glance = document.createElement("div");
  glance.className = "team-hero__glance";
  [
    ["Off", na(latest.adjO) ? "—" : latest.adjO.toFixed(2), latest.adjORank],
    ["Def", na(latest.adjD) ? "—" : latest.adjD.toFixed(2), latest.adjDRank]
  ].forEach(function (item) {
    var chip = document.createElement("div");
    chip.className = "glance-chip";
    var label = document.createElement("span");
    label.className = "glance-chip__label";
    label.textContent = item[0];
    var value = document.createElement("span");
    value.className = "glance-chip__value mono";
    value.textContent = item[1];
    var rank = document.createElement("span");
    rank.className = "glance-chip__rank";
    rank.textContent = na(item[2]) ? "" : "#" + item[2];
    chip.appendChild(label);
    chip.appendChild(value);
    chip.appendChild(rank);
    glance.appendChild(chip);
  });
  info.appendChild(glance);

  hero.appendChild(info);
  content.appendChild(hero);

  var historySection = document.createElement("section");
  historySection.className = "team-history";

  var heading = document.createElement("h2");
  heading.textContent = "Season History";
  historySection.appendChild(heading);

  var scroll = document.createElement("div");
  scroll.className = "table-scroll";

  var table = document.createElement("table");
  table.className = "data-table";
  table.id = "historyTable";

  var thead = document.createElement("thead");
  var headRow = document.createElement("tr");
  ["Year", "Conf", "W-L", "Rk", "AdjEM", "AdjO", "AdjD", "SOS", "SOR"].forEach(function (label, i) {
    var th = document.createElement("th");
    th.textContent = label;
    if (i === 0) th.classList.add("year-cell");
    if (i >= 2) th.classList.add("num");
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  seasons.forEach(function (s) {
    var tr = document.createElement("tr");
    tr.appendChild(cell("mono year-cell", String(s.year)));
    tr.appendChild(cell("conf-cell", s.conf));
    tr.appendChild(cell("num record-cell", s.record));
    tr.appendChild(cell("num rank-cell", na(s.rank) ? "—" : String(s.rank)));
    tr.appendChild(statCell(s.adjEM, undefined, true, true));
    tr.appendChild(statCell(s.adjO, s.adjORank, false, true, 2));
    tr.appendChild(statCell(s.adjD, s.adjDRank, false, true, 2));
    tr.appendChild(statCell(s.sos, s.sosRank, false, true));
    tr.appendChild(statCell(s.sor, s.sorRank, false, true));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  scroll.appendChild(table);
  historySection.appendChild(scroll);
  content.appendChild(historySection);

  renderAdvancedPreview(latest, slug);

  function renderAdvancedPreview(latest, slug) {
  var content = document.getElementById("teamContent");
  // data.js and advanced-data.js share the same 0-indexed week numbering.
  var advYearData = (window.CFF_ADV_DATA || {})[String(latest.year)] || {};
  var advRows = advYearData[String(latest.finalWeek)] || [];
  var adv = advRows.filter(function (r) { return r.slug === slug; })[0];
  if (!adv) return;

  var wk = adv.wk || {};
  var sos = (wk.opponentSrsCount) ? (wk.opponentSrsSum / wk.opponentSrsCount) : null;
  var pace = (wk.games) ? (wk.offPlays / wk.games) : null;

  var section = document.createElement("section");
  section.className = "adv-preview";

  var headingRow = document.createElement("div");
  headingRow.className = "adv-preview__heading";

  var heading = document.createElement("h2");
  heading.textContent = "Advanced CFF Analytics";
  headingRow.appendChild(heading);

  var badge = document.createElement("span");
  badge.className = "adv-preview__badge";
  badge.textContent = "Premium · Coming Soon";
  headingRow.appendChild(badge);

  section.appendChild(headingRow);

  var note = document.createElement("p");
  note.className = "adv-preview__note";
  note.textContent = "Opponent-adjusted efficiency splits by phase of the game — General, Offense, and Defense — with week-by-week filtering.";
  section.appendChild(note);

  var locked = document.createElement("div");
  locked.className = "adv-preview__locked";

  var scroll = document.createElement("div");
  scroll.className = "table-scroll adv-preview__table";

  var table = document.createElement("table");
  table.className = "data-table";

  var thead = document.createElement("thead");
  var headRow = document.createElement("tr");
  ["CFF", "SOS", "Field Pos", "Pace", "ST"].forEach(function (label) {
    var th = document.createElement("th");
    th.className = "num";
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  var tr = document.createElement("tr");
  tr.appendChild(cell("num stat-cell primary", signed(adv.cff, 1)));
  tr.appendChild(cell("num stat-cell", signed(sos, 1)));
  tr.appendChild(cell("num stat-cell", signed(adv.fieldPos, 1)));
  tr.appendChild(cell("num stat-cell", na(pace) ? "—" : pace.toFixed(1)));
  tr.appendChild(cell("num stat-cell", "—"));
  tbody.appendChild(tr);
  table.appendChild(tbody);

  scroll.appendChild(table);
  locked.appendChild(scroll);

  var overlay = document.createElement("div");
  overlay.className = "adv-preview__overlay";
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "subscribe-btn";
  btn.textContent = "Subscribe to View";
  overlay.appendChild(btn);
  locked.appendChild(overlay);

  section.appendChild(locked);
  content.appendChild(section);
  }
})();
