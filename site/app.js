(function () {
  var COLUMNS = [
    { key: "rank", label: "Rk", numeric: true, defaultDir: "asc", cellClass: "rank-cell",
      tooltip: "Overall rank by AdjEM (real SRS rating, opponent-adjusted, computed week by week from actual games only)" },
    { key: "team", label: "Team", numeric: false, defaultDir: "asc", cellClass: "team-cell" },
    { key: "conf", label: "Conf", numeric: false, defaultDir: "asc" },
    { key: "adjEM", label: "AdjEM", numeric: true, defaultDir: "desc", primary: true,
      tooltip: "Real Simple Rating System (SRS) score: schedule-adjusted point margin, computed walk-forward from actual results only" },
    { key: "adjO", label: "AdjO", numeric: true, defaultDir: "desc", rankKey: "adjORank",
      tooltip: "Real schedule-adjusted yards-per-play edge (offense). From a research-only model — independently validated this session (6-12% error reduction vs. naive baselines), not yet this project's production rating" },
    { key: "adjD", label: "AdjD", numeric: true, defaultDir: "desc", rankKey: "adjDRank",
      tooltip: "Real schedule-adjusted yards-per-play edge (defense). Higher is better — a positive value always means the defense outperformed expectation. Same research-only model as AdjO" },
    { key: "sos", label: "SOS", numeric: true, defaultDir: "desc", rankKey: "sosRank",
      tooltip: "Strength of schedule: average real SRS of opponents played so far" },
    { key: "sor", label: "SOR", numeric: true, defaultDir: "desc", rankKey: "sorRank",
      tooltip: "Strength of record has no defined, validated methodology in this project yet — intentionally left blank rather than invented" }
  ];

  var YEARS = window.CFB_YEARS || [];
  var WEEKS = window.CFB_WEEKS || {};

  function weeksForYear(year) {
    return WEEKS[String(year)] || [];
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
    filter: (window.CFF && CFF.getQueryParam("q")) || ""
  };

  var theadRow = document.getElementById("theadRow");
  var tbody = document.getElementById("ratingsBody");
  var yearNav = document.getElementById("yearNav");
  var weekNav = document.getElementById("weekNav");
  var filterInput = document.getElementById("filterInput");
  var rowCount = document.getElementById("rowCount");

  function logoUrl(teamId) {
    return "https://cdn.collegefootballdata.com/logos/64/" + teamId + ".png";
  }

  function buildYearNav() {
    YEARS.forEach(function (year) {
      var btn = document.createElement("button");
      btn.dataset.year = String(year);
      btn.textContent = String(year);
      if (String(year) === state.year) btn.classList.add("active");
      yearNav.appendChild(btn);
    });
  }

  function buildWeekNav() {
    weekNav.innerHTML = "";
    weeksForYear(state.year).forEach(function (week) {
      var btn = document.createElement("button");
      btn.dataset.week = String(week);
      btn.textContent = "Wk " + week;
      if (String(week) === state.week) btn.classList.add("active");
      weekNav.appendChild(btn);
    });
  }

  function addTipTrigger(th, tooltip) {
    if (!tooltip) return;
    var trigger = document.createElement("span");
    trigger.className = "tip-trigger";
    trigger.textContent = "?";
    trigger.setAttribute("data-tip", tooltip);
    trigger.setAttribute("tabindex", "0");
    th.appendChild(trigger);
  }

  function buildHeader() {
    COLUMNS.forEach(function (col) {
      var th = document.createElement("th");
      th.dataset.key = col.key;
      if (col.numeric) th.classList.add("num");
      if (col.cellClass) th.classList.add(col.cellClass);
      th.classList.add("sortable");

      var label = document.createElement("span");
      label.textContent = col.label;
      th.appendChild(label);

      addTipTrigger(th, col.tooltip);

      var indicator = document.createElement("span");
      indicator.className = "sort-indicator";
      indicator.dataset.role = "indicator";
      th.appendChild(indicator);

      th.addEventListener("click", function () {
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

    // Record column is not sortable — inserted after Conf
    var wlHeader = document.createElement("th");
    wlHeader.className = "num";
    wlHeader.textContent = "W-L";
    theadRow.insertBefore(wlHeader, theadRow.children[3]);

    // Week-over-week movement — inserted right after Rk
    var moveHeader = document.createElement("th");
    moveHeader.className = "num delta-cell";
    moveHeader.textContent = "Wk Δ";
    addTipTrigger(moveHeader, "Change in Rk since the previous week");
    theadRow.insertBefore(moveHeader, theadRow.children[1]);
  }

  function updateHeaderIndicators() {
    Array.prototype.forEach.call(theadRow.children, function (th) {
      var indicator = th.querySelector('[data-role="indicator"]');
      if (!indicator) return;
      if (th.dataset.key === state.sortKey) {
        indicator.textContent = state.sortDir === "asc" ? "▲" : "▼";
      } else {
        indicator.textContent = "";
      }
    });
  }

  function getRows() {
    var yearData = window.CFB_DATA[state.year] || {};
    var rows = (yearData[state.week] || []).slice();
    var needle = state.filter.trim().toLowerCase();
    if (needle) {
      rows = rows.filter(function (t) {
        return (
          t.team.toLowerCase().indexOf(needle) !== -1 ||
          t.conf.toLowerCase().indexOf(needle) !== -1
        );
      });
    }

    var key = state.sortKey;
    var dir = state.sortDir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      var av = a[key];
      var bv = b[key];
      if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string") {
        return av.localeCompare(bv) * dir;
      }
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

  function statCell(value, rankValue, primary, useSign, decimals) {
    var td = document.createElement("td");
    td.className = "num stat-cell" + (primary ? " primary" : "");
    var text;
    if (value === null || value === undefined) {
      text = "—";
    } else if (useSign) {
      text = (value >= 0 ? "+" : "") + value.toFixed(decimals || 1);
    } else {
      text = value.toFixed(decimals || 1);
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

  function renderSkeleton() {
    var colCount = theadRow.children.length;
    tbody.innerHTML = "";
    for (var i = 0; i < 12; i++) {
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
    window.setTimeout(render, 110);
  }

  function render() {
    var rows = getRows();
    tbody.innerHTML = "";

    if (rows.length === 0) {
      var tr = document.createElement("tr");
      tr.className = "empty-row";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.textContent = "No teams match “" + state.filter + "”.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      rows.forEach(function (t) {
        var tr = document.createElement("tr");
        tr.appendChild(cell("num rank-cell", t.rank === null ? "—" : String(t.rank)));
        tr.appendChild(deltaCell(t.rank === null ? undefined : t.rankChange));
        tr.appendChild(teamCell(t));
        tr.appendChild(cell("conf-cell", t.conf));
        tr.appendChild(cell("num record-cell", t.record));
        tr.appendChild(statCell(t.adjEM, undefined, true, true));
        tr.appendChild(statCell(t.adjO, t.adjORank, false, true, 2));
        tr.appendChild(statCell(t.adjD, t.adjDRank, false, true, 2));
        tr.appendChild(statCell(t.sos, t.sosRank, false, true));
        tr.appendChild(statCell(t.sor, t.sorRank, false, true));
        tbody.appendChild(tr);
      });
    }

    rowCount.textContent = rows.length + (rows.length === 1 ? " team" : " teams");
    updateHeaderIndicators();
  }

  yearNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-year]");
    if (!btn) return;
    state.year = btn.dataset.year;
    state.week = String(lastWeek(state.year));
    Array.prototype.forEach.call(yearNav.children, function (b) {
      b.classList.toggle("active", b === btn);
    });
    buildWeekNav();
    renderSoon();
  });

  weekNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-week]");
    if (!btn) return;
    state.week = btn.dataset.week;
    Array.prototype.forEach.call(weekNav.children, function (b) {
      b.classList.toggle("active", b === btn);
    });
    renderSoon();
  });

  filterInput.addEventListener("input", function () {
    state.filter = filterInput.value;
    render();
  });

  filterInput.value = state.filter;

  buildYearNav();
  buildWeekNav();
  buildHeader();
  render();
})();
