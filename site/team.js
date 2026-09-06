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

  function cell(className, text) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text;
    return td;
  }

  function statCell(value, rankValue, primary, digits, metricKey) {
    var td = document.createElement("td");
    td.className = "num stat-cell history-metric-cell" + (primary ? " primary" : "");
    td.dataset.historyMetric = metricKey;
    td.appendChild(document.createTextNode(signed(value, digits)));
    if (!na(rankValue)) {
      var sub = document.createElement("span");
      sub.className = "rank-sub";
      sub.textContent = "(" + rankValue + ")";
      td.appendChild(sub);
    }
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
    notFound.innerHTML = 'Team not found. <a href="index.html">Back to all ratings &rarr;</a>';
    content.appendChild(notFound);
    return;
  }

  var latest = seasons[0];
  document.title = latest.team + " Football Ratings — CollegeFootballFocus";
  var meta = document.querySelector('meta[name="description"]');
  if (meta) {
    meta.setAttribute("content", latest.team + " college football ratings, opponent-adjusted offense and defense, strength of schedule, and season history.");
  }

  renderBreadcrumbs();
  renderHero();
  renderSnapshot();
  renderHistory();
  renderAdvancedPreview();

  function renderBreadcrumbs() {
    var breadcrumbs = document.getElementById("breadcrumbs");
    if (!breadcrumbs) return;
    breadcrumbs.innerHTML = "";

    var ratings = document.createElement("a");
    ratings.href = "index.html";
    ratings.textContent = "Ratings";
    breadcrumbs.appendChild(ratings);

    var sep1 = document.createElement("span");
    sep1.className = "crumb-sep";
    sep1.textContent = "/";
    breadcrumbs.appendChild(sep1);

    var conf = document.createElement("a");
    conf.href = "index.html?conf=" + encodeURIComponent(latest.conf);
    conf.textContent = latest.conf;
    breadcrumbs.appendChild(conf);

    var sep2 = document.createElement("span");
    sep2.className = "crumb-sep";
    sep2.textContent = "/";
    breadcrumbs.appendChild(sep2);

    var team = document.createElement("span");
    team.className = "crumb-current";
    team.textContent = latest.team;
    breadcrumbs.appendChild(team);
  }

  function renderHero() {
    var hero = document.createElement("section");
    hero.className = "team-hero";

    var img = document.createElement("img");
    img.className = "team-hero__logo";
    img.src = logoUrl(latest.teamId);
    img.alt = latest.team + " logo";
    img.decoding = "async";
    img.onerror = function () { img.style.visibility = "hidden"; };
    hero.appendChild(img);

    var info = document.createElement("div");
    info.className = "team-hero__info";

    var eyebrow = document.createElement("span");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = latest.conf + " · " + latest.year + " through Week " + latest.finalWeek;
    info.appendChild(eyebrow);

    var name = document.createElement("h1");
    name.className = "team-hero__name";
    name.textContent = latest.team;
    info.appendChild(name);

    var rankText = na(latest.rank) ? "—" : "#" + latest.rank;
    var current = document.createElement("div");
    current.className = "team-hero__current";
    current.innerHTML = '<b>' + rankText + '</b> nationally &middot; <b>' + latest.record + '</b> &middot; AdjEM <b>' + signed(latest.adjEM, 1) + '</b>';
    info.appendChild(current);

    hero.appendChild(info);
    content.appendChild(hero);
  }

  function renderSnapshot() {
    var section = document.createElement("section");
    section.className = "team-snapshot";

    var header = document.createElement("div");
    header.className = "section-heading";
    var heading = document.createElement("h2");
    heading.textContent = "Current Rating Snapshot";
    header.appendChild(heading);
    var note = document.createElement("span");
    note.textContent = "Value · national rank";
    header.appendChild(note);
    section.appendChild(header);

    var grid = document.createElement("div");
    grid.className = "snapshot-grid";
    [
      { label: "Overall", value: signed(latest.adjEM, 1), rank: latest.rank, detail: "AdjEM" },
      { label: "Offense", value: signed(latest.adjO, 2), rank: latest.adjORank, detail: "AdjO" },
      { label: "Defense", value: signed(latest.adjD, 2), rank: latest.adjDRank, detail: "AdjD" },
      { label: "Schedule", value: signed(latest.sos, 1), rank: latest.sosRank, detail: "SOS" }
    ].forEach(function (item) {
      var card = document.createElement("div");
      card.className = "snapshot-card";

      var top = document.createElement("div");
      top.className = "snapshot-card__top";
      var label = document.createElement("span");
      label.className = "snapshot-card__label";
      label.textContent = item.label;
      var detail = document.createElement("span");
      detail.className = "snapshot-card__detail";
      detail.textContent = item.detail;
      top.appendChild(label);
      top.appendChild(detail);
      card.appendChild(top);

      var values = document.createElement("div");
      values.className = "snapshot-card__values";
      var value = document.createElement("strong");
      value.className = "mono";
      value.textContent = item.value;
      var rank = document.createElement("span");
      rank.className = "mono snapshot-card__rank";
      rank.textContent = na(item.rank) ? "—" : "#" + item.rank;
      values.appendChild(value);
      values.appendChild(rank);
      card.appendChild(values);
      grid.appendChild(card);
    });

    section.appendChild(grid);
    content.appendChild(section);
  }

  function renderHistory() {
    var section = document.createElement("section");
    section.className = "team-history";

    var header = document.createElement("div");
    header.className = "section-heading";
    var heading = document.createElement("h2");
    heading.textContent = "Season History";
    header.appendChild(heading);
    var note = document.createElement("span");
    note.textContent = seasons.length + (seasons.length === 1 ? " season" : " seasons") + " available";
    header.appendChild(note);
    section.appendChild(header);

    var tools = document.createElement("div");
    tools.className = "history-mobile-tools";
    var label = document.createElement("label");
    label.setAttribute("for", "historyMetricSelect");
    label.textContent = "Compare";
    var select = document.createElement("select");
    select.id = "historyMetricSelect";
    [
      ["adjEM", "Overall rating (AdjEM)"],
      ["rank", "Overall rank"],
      ["adjO", "Offense (AdjO)"],
      ["adjD", "Defense (AdjD)"],
      ["sos", "Strength of schedule"]
    ].forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item[0];
      opt.textContent = item[1];
      select.appendChild(opt);
    });
    tools.appendChild(label);
    tools.appendChild(select);
    section.appendChild(tools);

    var scroll = document.createElement("div");
    scroll.className = "table-scroll history-table-scroll";
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", latest.team + " season history");
    scroll.setAttribute("tabindex", "0");

    var table = document.createElement("table");
    table.className = "data-table";
    table.id = "historyTable";
    var caption = document.createElement("caption");
    caption.className = "sr-only";
    caption.textContent = latest.team + " historical college football ratings";
    table.appendChild(caption);

    var thead = document.createElement("thead");
    var headRow = document.createElement("tr");
    [
      { label: "Year", cls: "year-cell" },
      { label: "Conf", cls: "conf-cell" },
      { label: "W-L", cls: "num record-cell" },
      { label: "Rk", cls: "num history-rank-cell", metric: "rank" },
      { label: "AdjEM", cls: "num history-metric-cell", metric: "adjEM" },
      { label: "AdjO", cls: "num history-metric-cell", metric: "adjO" },
      { label: "AdjD", cls: "num history-metric-cell", metric: "adjD" },
      { label: "SOS", cls: "num history-metric-cell", metric: "sos" }
    ].forEach(function (def) {
      var th = document.createElement("th");
      th.scope = "col";
      th.className = def.cls || "";
      th.textContent = def.label;
      if (def.metric) th.dataset.historyMetric = def.metric;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    seasons.forEach(function (s) {
      var tr = document.createElement("tr");
      if (s.year === latest.year) tr.classList.add("history-current");
      tr.appendChild(cell("mono year-cell", String(s.year)));
      tr.appendChild(cell("conf-cell", s.conf));
      tr.appendChild(cell("num record-cell", s.record));

      var rankCell = cell("num mono history-rank-cell", na(s.rank) ? "—" : String(s.rank));
      rankCell.dataset.historyMetric = "rank";
      tr.appendChild(rankCell);
      tr.appendChild(statCell(s.adjEM, undefined, true, 1, "adjEM"));
      tr.appendChild(statCell(s.adjO, s.adjORank, false, 2, "adjO"));
      tr.appendChild(statCell(s.adjD, s.adjDRank, false, 2, "adjD"));
      tr.appendChild(statCell(s.sos, s.sosRank, false, 1, "sos"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    section.appendChild(scroll);
    content.appendChild(section);

    function applyHistoryMetric() {
      var selected = select.value;
      Array.prototype.forEach.call(table.querySelectorAll("[data-history-metric]"), function (el) {
        el.classList.toggle("mobile-selected-history-metric", el.dataset.historyMetric === selected);
      });
    }

    select.addEventListener("change", applyHistoryMetric);
    applyHistoryMetric();
  }

  function renderAdvancedPreview() {
    var section = document.createElement("section");
    section.className = "adv-preview";

    var headingRow = document.createElement("div");
    headingRow.className = "adv-preview__heading";
    var heading = document.createElement("h2");
    heading.textContent = "Advanced CFF Analytics";
    var badge = document.createElement("span");
    badge.className = "adv-preview__badge";
    badge.textContent = "PRO";
    headingRow.appendChild(heading);
    headingRow.appendChild(badge);
    section.appendChild(headingRow);

    var note = document.createElement("p");
    note.className = "adv-preview__note";
    note.textContent = "Go beyond the overall rating and isolate how this team wins: efficiency, explosiveness, finishing drives, field position, pace and custom week ranges.";
    section.appendChild(note);

    var locked = document.createElement("div");
    locked.className = "adv-preview__locked";
    var grid = document.createElement("div");
    grid.className = "adv-preview__grid";
    ["Success Rate", "Explosiveness", "Finishing", "Field Position", "Pace", "Week Splits"].forEach(function (label) {
      var item = document.createElement("div");
      item.className = "adv-preview__metric";
      var name = document.createElement("span");
      name.textContent = label;
      var value = document.createElement("strong");
      value.className = "adv-preview__blur-value";
      value.textContent = "••••";
      item.appendChild(name);
      item.appendChild(value);
      grid.appendChild(item);
    });
    locked.appendChild(grid);

    var overlay = document.createElement("div");
    overlay.className = "adv-preview__overlay";
    var link = document.createElement("a");
    link.className = "subscribe-btn";
    link.href = "advanced.html";
    link.textContent = "Preview Advanced CFF";
    overlay.appendChild(link);
    locked.appendChild(overlay);

    section.appendChild(locked);
    content.appendChild(section);
  }
})();
