(function () {
  var COLUMNS = [
    { key: "rank", label: "Rk", numeric: true, defaultDir: "asc", cellClass: "rank-cell", tooltip: "Overall rank by AdjNet." },
    { key: "team", label: "Team", numeric: false, defaultDir: "asc", cellClass: "team-cell" },
    { key: "conf", label: "Conf", numeric: false, defaultDir: "asc", cellClass: "conf-cell" },
    { key: "adjEM", label: "AdjNet", numeric: true, defaultDir: "desc", primary: true, tooltip: "Overall opponent-adjusted rating. Adj. Net = Adj. Off + Adj. Def" },
    { key: "adjO", label: "AdjOff", numeric: true, defaultDir: "desc", rankKey: "adjORank", tooltip: "Opponent-adjusted offensive rating combining EPA, Success Rate, and Explosiveness. Higher is better." },
    { key: "adjD", label: "AdjDef", numeric: true, defaultDir: "desc", rankKey: "adjDRank", tooltip: "Opponent-adjusted defensive rating combining EPA, Success Rate, and Explosiveness. Higher is better." },
    { key: "sos", label: "SOS", numeric: true, defaultDir: "desc", rankKey: "sosRank", tooltip: "Strength of schedule: average SRS strength of opponents played through the selected week." },
    { key: "sor", label: "SOR", numeric: true, defaultDir: "desc", rankKey: "sorRank", tooltip: "Strength of record: wins above what an exactly-average FBS team would be expected to get on this same schedule. A résumé measure (won/lost), not a performance measure like AdjNet. Higher is better." }
  ];

  var YEARS = window.CFB_YEARS || [];
  var WEEKS = window.CFB_WEEKS || {};
  var WEEK_LABELS = window.CFB_WEEK_LABELS || {};

  function weeksForYear(year) {
    return WEEKS[String(year)] || [];
  }

  function weekLabel(year, week) {
    var yearLabels = WEEK_LABELS[String(year)] || {};
    return yearLabels[String(week)] || ("Wk " + week);
  }

  function throughWeekPhrase(year, week) {
    var yearLabels = WEEK_LABELS[String(year)] || {};
    var label = yearLabels[String(week)];
    return label ? ("through " + label) : ("through Week " + week);
  }

  function lastWeek(year) {
    var ws = weeksForYear(year);
    return ws[ws.length - 1];
  }

  var initialYear = YEARS[YEARS.length - 1];
  var state = {
    year: String(initialYear),
    week: String(lastWeek(initialYear)),
    sortKey: "rank",
    sortDir: "asc",
    filter: (window.CFF && CFF.getQueryParam("q")) || "",
    conference: (window.CFF && CFF.getQueryParam("conf")) || "",
    mobileMetric: "adjEM"
  };

  var theadRow = document.getElementById("theadRow");
  var tbody = document.getElementById("ratingsBody");
  var yearNav = document.getElementById("yearNav");
  var weekNav = document.getElementById("weekNav");
  var filterInput = document.getElementById("filterInput");
  var conferenceSelect = document.getElementById("conferenceSelect");
  var rowCount = document.getElementById("rowCount");
  var mobileMetricSelect = document.getElementById("mobileMetricSelect");
  var ratingsTitle = document.getElementById("ratingsTitle");
  var ratingsStatus = document.getElementById("ratingsStatus");

  function logoUrl(teamId) {
    return "https://cdn.collegefootballdata.com/logos/64/" + teamId + ".png";
  }

  function baseRows() {
    var yearData = window.CFB_DATA[state.year] || {};
    return (yearData[state.week] || []).slice();
  }

  function setActiveButtonState(container, dataKey, selectedValue) {
    Array.prototype.forEach.call(container.children, function (btn) {
      var active = btn.dataset[dataKey] === String(selectedValue);
      btn.classList.toggle("active", active);
      if (active) btn.setAttribute("aria-current", "true");
      else btn.removeAttribute("aria-current");
    });
  }

  function buildYearNav() {
    yearNav.innerHTML = "";
    YEARS.forEach(function (year) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.year = String(year);
      btn.textContent = String(year);
      btn.setAttribute("aria-label", String(year) + " season");
      yearNav.appendChild(btn);
    });
    setActiveButtonState(yearNav, "year", state.year);
  }

  function buildWeekNav() {
    weekNav.innerHTML = "";
    weeksForYear(state.year).forEach(function (week) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.week = String(week);
      var label = weekLabel(state.year, week);
      btn.textContent = label;
      btn.setAttribute("aria-label", label);
      weekNav.appendChild(btn);
    });
    setActiveButtonState(weekNav, "week", state.week);
  }

  function buildConferenceSelect() {
    if (!conferenceSelect) return;

    var conferences = [];
    baseRows().forEach(function (t) {
      if (t.conf && conferences.indexOf(t.conf) === -1) conferences.push(t.conf);
    });
    conferences.sort();

    if (state.conference && conferences.indexOf(state.conference) === -1) {
      state.conference = "";
    }

    conferenceSelect.innerHTML = "";
    var all = document.createElement("option");
    all.value = "";
    all.textContent = "All conferences";
    conferenceSelect.appendChild(all);

    conferences.forEach(function (conf) {
      var opt = document.createElement("option");
      opt.value = conf;
      opt.textContent = conf;
      conferenceSelect.appendChild(opt);
    });
    conferenceSelect.value = state.conference;
  }

  function addTipTrigger(th, tooltip) {
    if (!tooltip) return;
    var trigger = document.createElement("span");
    trigger.className = "tip-trigger";
    trigger.textContent = "?";
    trigger.setAttribute("data-tip", tooltip);
    trigger.setAttribute("tabindex", "0");
    trigger.setAttribute("role", "button");
    trigger.setAttribute("aria-label", "Explain this metric");
    th.appendChild(trigger);
  }

  function buildHeader() {
    theadRow.innerHTML = "";

    COLUMNS.forEach(function (col) {
      var th = document.createElement("th");
      th.scope = "col";
      th.dataset.key = col.key;
      if (col.numeric) th.classList.add("num");
      if (col.cellClass) th.classList.add(col.cellClass);
      if (["adjEM", "adjO", "adjD", "sos", "sor"].indexOf(col.key) !== -1) {
        th.classList.add("metric-cell");
        th.dataset.metricKey = col.key;
      }
      th.classList.add("sortable");
      th.setAttribute("aria-sort", "none");

      var label = document.createElement("span");
      label.textContent = col.label;
      th.appendChild(label);
      addTipTrigger(th, col.tooltip);

      var indicator = document.createElement("span");
      indicator.className = "sort-indicator";
      indicator.dataset.role = "indicator";
      indicator.setAttribute("aria-hidden", "true");
      th.appendChild(indicator);

      th.addEventListener("click", function (e) {
        if (e.target.closest("[data-tip]")) return;
        if (state.sortKey === col.key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = col.key;
          state.sortDir = col.defaultDir;
        }
        render();
      });

      theadRow.appendChild(th);
    });

    var wlHeader = document.createElement("th");
    wlHeader.scope = "col";
    wlHeader.className = "num record-cell";
    wlHeader.textContent = "W-L";
    theadRow.insertBefore(wlHeader, theadRow.children[3]);

    var moveHeader = document.createElement("th");
    moveHeader.scope = "col";
    moveHeader.className = "num delta-cell";
    moveHeader.textContent = "Wk Δ";
    addTipTrigger(moveHeader, "Change in overall rank from the previous week.");
    theadRow.insertBefore(moveHeader, theadRow.children[1]);
  }

  function updateHeaderIndicators() {
    Array.prototype.forEach.call(theadRow.children, function (th) {
      var indicator = th.querySelector('[data-role="indicator"]');
      if (!indicator) return;
      var active = th.dataset.key === state.sortKey;
      indicator.textContent = active ? (state.sortDir === "asc" ? "▲" : "▼") : "";
      th.setAttribute("aria-sort", active ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
    });
  }

  function getRows() {
    var rows = baseRows();
    var needle = state.filter.trim().toLowerCase();

    if (needle) {
      rows = rows.filter(function (t) {
        return t.team.toLowerCase().indexOf(needle) !== -1;
      });
    }
    if (state.conference) {
      rows = rows.filter(function (t) {
        return t.conf === state.conference;
      });
    }

    var key = state.sortKey;
    var dir = state.sortDir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      var av = a[key];
      var bv = b[key];
      if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string") return av.localeCompare(bv) * dir;
      return (av - bv) * dir;
    });
    return rows;
  }

  function cell(className, text) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text;
    return td;
  }

  function teamCell(t) {
    var td = document.createElement("td");
    td.className = "team-cell";

    var link = document.createElement("a");
    link.className = "team-link";
    link.href = "team.html?team=" + encodeURIComponent(t.slug);

    var img = document.createElement("img");
    img.className = "team-logo";
    img.src = logoUrl(t.teamId);
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.onerror = function () {
      img.style.visibility = "hidden";
    };
    link.appendChild(img);

    var name = document.createElement("span");
    name.textContent = t.team;
    link.appendChild(name);
    td.appendChild(link);
    return td;
  }

  function deltaCell(change) {
    var td = document.createElement("td");
    td.className = "num delta-cell";
    if (change === null || change === undefined) {
      td.classList.add("delta-new");
      td.textContent = "NEW";
    } else if (change > 0) {
      td.classList.add("delta-up");
      td.textContent = "▲" + change;
    } else if (change < 0) {
      td.classList.add("delta-down");
      td.textContent = "▼" + Math.abs(change);
    } else {
      td.classList.add("delta-flat");
      td.textContent = "—";
    }
    return td;
  }

  function statCell(value, rankValue, primary, useSign, decimals, metricKey) {
    var td = document.createElement("td");
    td.className = "num stat-cell metric-cell" + (primary ? " primary" : "");
    td.dataset.metricKey = metricKey;

    var digits = decimals === undefined ? 1 : decimals;
    var text;
    if (value === null || value === undefined) {
      text = "—";
    } else if (useSign) {
      text = (value >= 0 ? "+" : "") + value.toFixed(digits);
    } else {
      text = value.toFixed(digits);
    }
    td.appendChild(document.createTextNode(text));

    if (rankValue !== undefined && rankValue !== null) {
      var sub = document.createElement("span");
      sub.className = "rank-sub";
      sub.textContent = "(" + rankValue + ")";
      td.appendChild(sub);
    }
    return td;
  }

  function renderSkeleton() {
    var colCount = theadRow.children.length;
    tbody.innerHTML = "";
    for (var i = 0; i < 10; i++) {
      var tr = document.createElement("tr");
      tr.className = "skeleton-row";
      for (var c = 0; c < colCount; c++) {
        var td = document.createElement("td");
        var bar = document.createElement("span");
        bar.className = "skeleton-bar";
        bar.style.width = (c === 2 ? 70 : 40 + ((c * 13) % 30)) + "%";
        td.appendChild(bar);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }

  function renderSoon() {
    renderSkeleton();
    window.setTimeout(render, 80);
  }

  function applyMobileMetricVisibility() {
    Array.prototype.forEach.call(document.querySelectorAll("#ratingsTable .metric-cell"), function (el) {
      el.classList.toggle("mobile-selected-metric", el.dataset.metricKey === state.mobileMetric);
    });
  }

  function updatePageStatus(visibleCount) {
    var total = baseRows().length;
    var status = state.year + " · " + throughWeekPhrase(state.year, state.week) + " · " + total + " teams";
    if (ratingsStatus) ratingsStatus.textContent = status;
    if (ratingsTitle) ratingsTitle.textContent = state.year + " College Football Ratings";
    document.title = state.year + " College Football Ratings — CollegeFootballFocus";

    var filtered = !!state.filter.trim() || !!state.conference;
    rowCount.textContent = filtered ? (visibleCount + " of " + total + " teams") : (total + " teams");
  }

  function render() {
    var rows = getRows();
    tbody.innerHTML = "";

    if (rows.length === 0) {
      var tr = document.createElement("tr");
      tr.className = "empty-row";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.textContent = "No teams match the current filters.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      rows.forEach(function (t) {
        var tr = document.createElement("tr");
        if (t.rank !== null && t.rank <= 10) tr.classList.add("rank-tier-top10");
        tr.appendChild(cell("num rank-cell", t.rank === null ? "—" : String(t.rank)));
        tr.appendChild(deltaCell(t.rank === null ? undefined : t.rankChange));
        tr.appendChild(teamCell(t));
        tr.appendChild(cell("conf-cell", t.conf));
        tr.appendChild(cell("num record-cell", t.record));
        tr.appendChild(statCell(t.adjEM, undefined, true, true, 1, "adjEM"));
        tr.appendChild(statCell(t.adjO, t.adjORank, false, true, 2, "adjO"));
        tr.appendChild(statCell(t.adjD, t.adjDRank, false, true, 2, "adjD"));
        tr.appendChild(statCell(t.sos, t.sosRank, false, true, 1, "sos"));
        tr.appendChild(statCell(t.sor, t.sorRank, false, true, 1, "sor"));
        tbody.appendChild(tr);
      });
    }

    updatePageStatus(rows.length);
    updateHeaderIndicators();
    applyMobileMetricVisibility();
  }

  yearNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-year]");
    if (!btn) return;
    state.year = btn.dataset.year;
    state.week = String(lastWeek(state.year));
    state.conference = "";
    setActiveButtonState(yearNav, "year", state.year);
    buildWeekNav();
    buildConferenceSelect();
    renderSoon();
  });

  weekNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-week]");
    if (!btn) return;
    state.week = btn.dataset.week;
    state.conference = "";
    setActiveButtonState(weekNav, "week", state.week);
    buildConferenceSelect();
    renderSoon();
  });

  filterInput.addEventListener("input", function () {
    state.filter = filterInput.value;
    render();
  });

  if (conferenceSelect) {
    conferenceSelect.addEventListener("change", function () {
      state.conference = conferenceSelect.value;
      render();
    });
  }

  if (mobileMetricSelect) {
    mobileMetricSelect.value = state.mobileMetric;
    mobileMetricSelect.addEventListener("change", function () {
      state.mobileMetric = mobileMetricSelect.value;
      applyMobileMetricVisibility();
    });
  }

  filterInput.value = state.filter;
  buildYearNav();
  buildWeekNav();
  buildConferenceSelect();
  buildHeader();
  render();
})();
