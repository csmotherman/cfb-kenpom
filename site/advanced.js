(function () {
  var YEARS = window.CFF_ADV_YEARS || [];
  var WEEKS = window.CFF_ADV_WEEKS || {};

  function weeksForYear(year) {
    return WEEKS[String(year)] || [];
  }

  function na(v) {
    return v === null || v === undefined || Number.isNaN(v);
  }

  var FORMATTERS = {
    signed1: function (v) { return na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1); },
    signed2: function (v) { return na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2); },
    plain1: function (v) { return na(v) ? "—" : v.toFixed(1); },
    pct1: function (v) { return na(v) ? "—" : (v * 100).toFixed(1) + "%"; },
    split0: function (v) { if (na(v)) return "—"; var p = Math.round(v * 100); return p + "% | " + (100 - p) + "%"; }
  };

  // Rate columns are computed from summed `wk` (this-single-week) raw counts
  // across the selected [start,end] range -- genuinely range-restricted.
  // Snapshot columns come from the walk-forward research model and can only
  // ever reflect "as of the end week" (a model fit can't be split into a
  // sub-range), which is called out in their tooltip.
  var TABS = {
    general: {
      label: "General",
      primaryKey: "cff",
      columns: [
        { key: "cff", label: "CFF", fmt: "signed1", primary: true, rankable: true, kind: "snapshot",
          tooltip: "Real Simple Rating System (SRS) score, schedule-adjusted, as of the end week (a model fit can't be split into a sub-range)" },
        { key: "sos", label: "SOS", fmt: "signed1", rankable: true, kind: "rate", num: ["opponentSrsSum"], den: ["opponentSrsCount"],
          tooltip: "Strength of schedule: average real SRS of opponents played in the selected weeks" },
        { key: "fieldPos", label: "Field Pos", fmt: "signed1", rankable: true, kind: "snapshot",
          tooltip: "Real opponent-adjusted starting field position edge, as of the end week. Research-only model, independently validated this session" },
        { key: "pace", label: "Pace", fmt: "plain1", kind: "rate", num: ["offPlays"], den: ["games"],
          tooltip: "Real offensive plays per game in the selected weeks" },
        { key: "top", label: "TOP", fmt: "pct1", rankable: true, kind: "rate", num: ["possessionSeconds"], den: ["possessionSecondsTotal"],
          tooltip: "Time of possession — real share of game clock this team's offense held the ball, summed from actual drive lengths, in the selected weeks" },
        { key: "st", label: "ST", fmt: "signed1", kind: "constant-null",
          tooltip: "No special-teams data exists anywhere in this project yet — intentionally left blank rather than invented" }
      ]
    },
    offense: {
      label: "Offense",
      primaryKey: "off",
      columns: [
        { key: "off", label: "Off", fmt: "signed1", primary: true, rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted yards-per-possession edge (offense), as of the end week. Research-only model, independently validated" },
        { key: "offSuccess", label: "Success", fmt: "pct1", rankable: true, kind: "rate", num: ["successNum"], den: ["successDen"],
          tooltip: "Real offensive success rate in the selected weeks (raw, not opponent-adjusted)" },
        { key: "offPassSuccess", label: "Pass", fmt: "pct1", rankable: true, kind: "rate", num: ["passSuccessNum"], den: ["passSuccessDen"],
          tooltip: "Real passing success rate in the selected weeks (raw)" },
        { key: "offRushSuccess", label: "Run", fmt: "pct1", rankable: true, kind: "rate", num: ["rushSuccessNum"], den: ["rushSuccessDen"],
          tooltip: "Real rushing success rate in the selected weeks (raw)" },
        { key: "offPassRate", label: "Pass | Run Split", fmt: "split0", kind: "rate", num: ["dropbacks"], den: ["dropbacks", "rushAttempts"],
          tooltip: "Real offensive tendency — share of real plays that were dropbacks vs. rush attempts in the selected weeks" },
        { key: "offExp", label: "Exp", fmt: "signed2", rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted explosiveness edge (offense), as of the end week. Research-only model, independently validated" },
        { key: "offFin", label: "Fin", fmt: "signed2", rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted finishing-drives edge (offense), as of the end week. Research-only model, independently validated" }
      ]
    },
    defense: {
      label: "Defense",
      primaryKey: "def",
      columns: [
        { key: "def", label: "Def", fmt: "signed1", primary: true, rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted yards-per-possession edge (defense). Higher is better — a positive value means the defense beat expectation. Research-only model, independently validated" },
        { key: "defSuccess", label: "Success", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["successNumA"], den: ["successDenA"],
          tooltip: "Real success rate allowed in the selected weeks (raw, not opponent-adjusted)" },
        { key: "defPassSuccess", label: "Pass", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["passSuccessNumA"], den: ["passSuccessDenA"],
          tooltip: "Real passing success rate allowed in the selected weeks (raw)" },
        { key: "defRushSuccess", label: "Run", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["rushSuccessNumA"], den: ["rushSuccessDenA"],
          tooltip: "Real rushing success rate allowed in the selected weeks (raw)" },
        { key: "defPassRate", label: "Pass | Run Split", fmt: "split0", kind: "rate", num: ["dropbacksFaced"], den: ["dropbacksFaced", "rushAttemptsFaced"],
          tooltip: "Real opponent tendency against this defense in the selected weeks" },
        { key: "defExp", label: "Exp", fmt: "signed2", rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted explosiveness-allowed edge. Higher is better. Research-only model, independently validated" },
        { key: "defFin", label: "Fin", fmt: "signed2", rankable: true, kind: "snapshot",
          tooltip: "Real schedule-adjusted finishing-drives-allowed edge. Higher is better. Research-only model, independently validated" }
      ]
    }
  };

  var initialYear = YEARS[YEARS.length - 1];
  var initialWeeks = weeksForYear(initialYear);

  var state = {
    year: String(initialYear),
    startWeek: initialWeeks[0],
    endWeek: initialWeeks[initialWeeks.length - 1],
    tab: "general",
    sortKey: null,
    sortDir: "asc",
    filter: ""
  };

  var yearNav = document.getElementById("yearNav");
  var tabNav = document.getElementById("tabNav");
  var startWeekSelect = document.getElementById("startWeek");
  var endWeekSelect = document.getElementById("endWeek");
  var filterInput = document.getElementById("filterInput");
  var rowCount = document.getElementById("rowCount");
  var theadRow = document.getElementById("advTheadRow");
  var tbody = document.getElementById("advBody");

  function logoUrl(teamId) {
    return "https://cdn.collegefootballdata.com/logos/64/" + teamId + ".png";
  }

  function buildYearNav() {
    yearNav.innerHTML = "";
    YEARS.forEach(function (year) {
      var btn = document.createElement("button");
      btn.dataset.year = String(year);
      btn.textContent = String(year);
      if (String(year) === state.year) btn.classList.add("active");
      yearNav.appendChild(btn);
    });
  }

  function buildTabNav() {
    tabNav.innerHTML = "";
    Object.keys(TABS).forEach(function (key) {
      var btn = document.createElement("button");
      btn.dataset.tab = key;
      btn.textContent = TABS[key].label;
      if (key === state.tab) btn.classList.add("active");
      tabNav.appendChild(btn);
    });
  }

  function buildWeekSelects() {
    var weeks = weeksForYear(state.year);
    [startWeekSelect, endWeekSelect].forEach(function (sel) {
      sel.innerHTML = "";
      weeks.forEach(function (w) {
        var opt = document.createElement("option");
        opt.value = String(w);
        opt.textContent = "Week " + w;
        sel.appendChild(opt);
      });
    });
    startWeekSelect.value = String(state.startWeek);
    endWeekSelect.value = String(state.endWeek);
  }

  function rate(num, den) {
    return (den && den > 0) ? num / den : null;
  }

  function sumField(wk, fields) {
    var total = 0;
    var any = false;
    fields.forEach(function (f) {
      if (wk[f] !== undefined) { total += wk[f]; any = true; }
    });
    return any ? total : 0;
  }

  function aggregate() {
    var weeks = weeksForYear(state.year).filter(function (w) {
      return w >= state.startWeek && w <= state.endWeek;
    });
    var yearData = window.CFF_ADV_DATA[state.year] || {};
    var byTeam = {};

    var endRows = yearData[state.endWeek] || [];
    var snapshotBySlug = {};
    endRows.forEach(function (r) { snapshotBySlug[r.slug] = r; });

    weeks.forEach(function (wk) {
      var rows = yearData[wk] || [];
      rows.forEach(function (r) {
        var acc = byTeam[r.slug];
        if (!acc) {
          acc = byTeam[r.slug] = { team: r.team, slug: r.slug, teamId: r.teamId, conf: r.conf, wk: {} };
        }
        var wkData = r.wk || {};
        Object.keys(wkData).forEach(function (k) {
          acc.wk[k] = (acc.wk[k] || 0) + wkData[k];
        });
      });
    });

    var allCols = [].concat(TABS.general.columns, TABS.offense.columns, TABS.defense.columns);

    return Object.keys(byTeam).map(function (slug) {
      var acc = byTeam[slug];
      var snap = snapshotBySlug[slug] || {};
      var wins = acc.wk.wins || 0;
      var losses = acc.wk.losses || 0;
      var out = {
        team: acc.team, slug: acc.slug, teamId: acc.teamId, conf: acc.conf,
        record: wins + "-" + losses, wins: wins
      };
      allCols.forEach(function (col) {
        if (col.kind === "snapshot") {
          out[col.key] = na(snap[col.key]) ? null : snap[col.key];
        } else if (col.kind === "rate") {
          var num = sumField(acc.wk, col.num);
          var den = sumField(acc.wk, col.den);
          out[col.key] = rate(num, den);
        } else {
          out[col.key] = null;
        }
      });
      return out;
    });
  }

  function assignRanks(teams) {
    var tab = TABS[state.tab];
    var rankFields = tab.columns.filter(function (c) { return c.rankable; });
    rankFields.forEach(function (col) {
      var ranked = teams.filter(function (t) { return !na(t[col.key]); });
      ranked.sort(function (a, b) {
        return col.lowerBetter ? a[col.key] - b[col.key] : b[col.key] - a[col.key];
      });
      ranked.forEach(function (t, i) {
        t["_rank_" + col.key] = i + 1;
      });
      teams.forEach(function (t) {
        if (t["_rank_" + col.key] === undefined) t["_rank_" + col.key] = null;
      });
    });
    var primaryCol = tab.columns.filter(function (c) { return c.primary; })[0];
    teams.forEach(function (t) {
      t._rank = t["_rank_" + primaryCol.key];
    });
  }

  function buildHeader() {
    theadRow.innerHTML = "";
    var tab = TABS[state.tab];

    function addTh(key, label, numeric, sortable, tooltip) {
      var th = document.createElement("th");
      if (numeric) th.classList.add("num");
      if (key === "rank") th.classList.add("rank-cell");
      if (key === "team") th.classList.add("team-cell");
      var span = document.createElement("span");
      span.textContent = label;
      th.appendChild(span);
      if (tooltip) {
        var trigger = document.createElement("span");
        trigger.className = "tip-trigger";
        trigger.textContent = "?";
        trigger.setAttribute("data-tip", tooltip);
        trigger.setAttribute("tabindex", "0");
        th.appendChild(trigger);
      }
      if (sortable) {
        th.classList.add("sortable");
        th.dataset.key = key;
        var indicator = document.createElement("span");
        indicator.className = "sort-indicator";
        indicator.dataset.role = "indicator";
        th.appendChild(indicator);
        th.addEventListener("click", function () {
          if (state.sortKey === key) {
            state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
          } else {
            state.sortKey = key;
            state.sortDir = key === "rank" ? "asc" : "desc";
          }
          render();
        });
      }
      theadRow.appendChild(th);
    }

    addTh("rank", "Rk", true, true, "Rank by " + tab.label + " primary rating");
    addTh("team", "Team", false, true);
    addTh("conf", "Conf", false, true);
    addTh("wins", "Rec", true, true, "Real record within the selected week range");
    tab.columns.forEach(function (col) {
      addTh(col.key, col.label, true, !!col.rankable, col.tooltip);
    });
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
    img.onerror = function () { img.style.visibility = "hidden"; };
    link.appendChild(img);
    var name = document.createElement("span");
    name.textContent = t.team;
    link.appendChild(name);
    td.appendChild(link);
    return td;
  }

  function statCell(t, col) {
    var td = document.createElement("td");
    td.className = "num stat-cell" + (col.primary ? " primary" : "");
    td.appendChild(document.createTextNode(FORMATTERS[col.fmt](t[col.key])));
    if (col.rankable) {
      var r = t["_rank_" + col.key];
      var sub = document.createElement("span");
      sub.className = "rank-sub";
      sub.textContent = r ? " (" + r + ")" : "";
      td.appendChild(sub);
    }
    return td;
  }

  function getRows() {
    var teams = aggregate();
    assignRanks(teams);

    var needle = state.filter.trim().toLowerCase();
    if (needle) {
      teams = teams.filter(function (t) {
        return t.team.toLowerCase().indexOf(needle) !== -1 ||
          t.conf.toLowerCase().indexOf(needle) !== -1;
      });
    }

    var key = state.sortKey || "rank";
    var dir = state.sortDir === "asc" ? 1 : -1;
    teams.sort(function (a, b) {
      var av = key === "rank" ? a._rank : a[key];
      var bv = key === "rank" ? b._rank : b[key];
      if (na(av)) return na(bv) ? 0 : 1;
      if (na(bv)) return -1;
      if (typeof av === "string") return av.localeCompare(bv) * dir;
      return (av - bv) * dir;
    });

    return teams;
  }

  function renderSkeleton() {
    var colCount = theadRow.children.length;
    tbody.innerHTML = "";
    for (var i = 0; i < 14; i++) {
      var tr = document.createElement("tr");
      tr.className = "skeleton-row";
      for (var c = 0; c < colCount; c++) {
        var td = document.createElement("td");
        var bar = document.createElement("span");
        bar.className = "skeleton-bar";
        bar.style.width = (c === 1 ? 75 : 45 + ((c * 11) % 30)) + "%";
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
    var tab = TABS[state.tab];
    var rows = getRows();
    tbody.innerHTML = "";

    if (rows.length === 0) {
      var tr = document.createElement("tr");
      tr.className = "empty-row";
      var td = document.createElement("td");
      td.colSpan = 4 + tab.columns.length;
      td.textContent = "No teams match “" + state.filter + "”.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      rows.forEach(function (t) {
        var tr = document.createElement("tr");
        tr.appendChild(cell("num rank-cell", t._rank ? String(t._rank) : "—"));
        tr.appendChild(teamCell(t));
        tr.appendChild(cell("conf-cell", t.conf));
        tr.appendChild(cell("num record-cell", t.record));
        tab.columns.forEach(function (col) {
          tr.appendChild(statCell(t, col));
        });
        tbody.appendChild(tr);
      });
    }

    var weeks = weeksForYear(state.year).filter(function (w) {
      return w >= state.startWeek && w <= state.endWeek;
    });
    rowCount.textContent = rows.length + (rows.length === 1 ? " team" : " teams") +
      " · Wk " + state.startWeek + "–" + state.endWeek +
      " (" + weeks.length + (weeks.length === 1 ? " week" : " weeks") + ")";

    updateHeaderIndicators();
  }

  yearNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-year]");
    if (!btn) return;
    state.year = btn.dataset.year;
    var weeks = weeksForYear(state.year);
    state.startWeek = weeks[0];
    state.endWeek = weeks[weeks.length - 1];
    Array.prototype.forEach.call(yearNav.children, function (b) {
      b.classList.toggle("active", b === btn);
    });
    buildWeekSelects();
    renderSoon();
  });

  tabNav.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    state.tab = btn.dataset.tab;
    state.sortKey = null;
    state.sortDir = "asc";
    Array.prototype.forEach.call(tabNav.children, function (b) {
      b.classList.toggle("active", b === btn);
    });
    buildHeader();
    renderSoon();
  });

  startWeekSelect.addEventListener("change", function () {
    state.startWeek = Number(startWeekSelect.value);
    if (state.startWeek > state.endWeek) {
      state.endWeek = state.startWeek;
      endWeekSelect.value = String(state.endWeek);
    }
    renderSoon();
  });

  endWeekSelect.addEventListener("change", function () {
    state.endWeek = Number(endWeekSelect.value);
    if (state.endWeek < state.startWeek) {
      state.startWeek = state.endWeek;
      startWeekSelect.value = String(state.startWeek);
    }
    renderSoon();
  });

  filterInput.addEventListener("input", function () {
    state.filter = filterInput.value;
    render();
  });

  if (window.CFF) {
    var initialFilter = CFF.getQueryParam("q");
    if (initialFilter) {
      state.filter = initialFilter;
      filterInput.value = initialFilter;
    }
  }

  buildYearNav();
  buildTabNav();
  buildWeekSelects();
  buildHeader();
  render();
})();
