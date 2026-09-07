/* ==========================================================================
   CollegeFootballFocus — shared site chrome
   Header search + tap/hover tooltips. Loaded on every page.
   ========================================================================== */

window.CFF = window.CFF || {};

CFF.getQueryParam = function (name) {
  return new URLSearchParams(window.location.search).get(name);
};

CFF.logoUrl = function (teamId, size) {
  return "https://cdn.collegefootballdata.com/logos/" + (size || 64) + "/" + teamId + ".png";
};

/* Compact display aliases follow CFBD/ESPN-style team abbreviations. The
   canonical data pipeline can eventually persist CFBD's abbreviation field;
   this lookup keeps the current historical payload backward-compatible. */
CFF.teamCode = function (team) {
  var codes = {
    "Air Force":"AFA", "Akron":"AKR", "Alabama":"ALA", "App State":"APP",
    "Appalachian State":"APP", "Arizona":"ARIZ", "Arizona State":"ASU",
    "Arkansas":"ARK", "Arkansas State":"ARST", "Army":"ARMY", "Auburn":"AUB",
    "BYU":"BYU", "Ball State":"BALL", "Baylor":"BAY", "Boise State":"BOIS",
    "Boston College":"BC", "Bowling Green":"BGSU", "Buffalo":"BUF",
    "California":"CAL", "Central Michigan":"CMU", "Charlotte":"CLT",
    "Cincinnati":"CIN", "Clemson":"CLEM", "Coastal Carolina":"CCU",
    "Colorado":"COLO", "Colorado State":"CSU", "Delaware":"DEL", "Duke":"DUKE",
    "East Carolina":"ECU", "Eastern Michigan":"EMU", "Florida":"FLA",
    "Florida Atlantic":"FAU", "Florida International":"FIU", "Florida State":"FSU",
    "Fresno State":"FRES", "Georgia":"UGA", "Georgia Southern":"GASO",
    "Georgia State":"GAST", "Georgia Tech":"GT", "Hawai'i":"HAW", "Hawaii":"HAW",
    "Houston":"HOU", "Illinois":"ILL", "Indiana":"IND", "Iowa":"IOWA",
    "Iowa State":"ISU", "Jacksonville State":"JVST", "James Madison":"JMU",
    "Kansas":"KU", "Kansas State":"KSU", "Kennesaw State":"KENN", "Kent State":"KENT",
    "Kentucky":"UK", "LSU":"LSU", "Liberty":"LIB", "Louisiana":"UL",
    "Louisiana Tech":"LT", "Louisville":"LOU", "Marshall":"MRSH", "Maryland":"MD",
    "Massachusetts":"MASS", "Memphis":"MEM", "Miami":"MIA", "Miami (OH)":"M-OH",
    "Michigan":"MICH", "Michigan State":"MSU", "Middle Tennessee":"MTSU",
    "Minnesota":"MINN", "Mississippi State":"MSST", "Missouri":"MIZ",
    "Missouri State":"MOST", "NC State":"NCST", "Navy":"NAVY", "Nebraska":"NEB",
    "Nevada":"NEV", "New Mexico":"UNM", "New Mexico State":"NMSU",
    "North Carolina":"UNC", "North Dakota State":"NDSU", "North Texas":"UNT",
    "Northern Illinois":"NIU", "Northwestern":"NU", "Notre Dame":"ND", "Ohio":"OHIO",
    "Ohio State":"OSU", "Oklahoma":"OU", "Oklahoma State":"OKST", "Old Dominion":"ODU",
    "Ole Miss":"MISS", "Oregon":"ORE", "Oregon State":"ORST", "Penn State":"PSU",
    "Pittsburgh":"PITT", "Purdue":"PUR", "Rice":"RICE", "Rutgers":"RUTG",
    "SMU":"SMU", "Sacramento State":"SAC", "Sam Houston":"SHSU",
    "San Diego State":"SDSU", "San José State":"SJSU", "San Jose State":"SJSU",
    "South Alabama":"USA", "South Carolina":"SC", "South Florida":"USF",
    "Southern Miss":"USM", "Stanford":"STAN", "Syracuse":"SYR", "TCU":"TCU",
    "Temple":"TEM", "Tennessee":"TENN", "Texas":"TEX", "Texas A&M":"TAMU",
    "Texas State":"TXST", "Texas Tech":"TTU", "Toledo":"TOL", "Troy":"TROY",
    "Tulane":"TULN", "Tulsa":"TLSA", "UAB":"UAB", "UCF":"UCF", "UCLA":"UCLA",
    "UConn":"CONN", "UL Monroe":"ULM", "UNLV":"UNLV", "USC":"USC", "UTEP":"UTEP",
    "UTSA":"UTSA", "Utah":"UTAH", "Utah State":"USU", "Vanderbilt":"VAN",
    "Virginia":"UVA", "Virginia Tech":"VT", "Wake Forest":"WAKE", "Washington":"WASH",
    "Washington State":"WSU", "West Virginia":"WVU", "Western Kentucky":"WKU",
    "Western Michigan":"WMU", "Wisconsin":"WIS", "Wyoming":"WYO"
  };
  if (codes[team]) return codes[team];
  var clean = String(team || "").replace(/[^A-Za-z0-9 ]/g, " ").trim();
  var words = clean.split(/\s+/).filter(Boolean);
  if (!words.length) return "TEAM";
  if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
  var acronym = words.map(function (w) { return w.charAt(0); }).join("").toUpperCase();
  return acronym.slice(0, 5);
};

/* Load the dedicated mobile table overrides after the page CSS. */
(function () {
  if (document.querySelector('link[href="mobile-tables.css"]')) return;
  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "mobile-tables.css";
  document.head.appendChild(link);
})();

/* Ratings/Advanced render team rows after site.js loads. Decorate those links
   whenever the table rerenders so mobile can show logo + compact code while
   desktop keeps the full school name. */
(function () {
  function decorate(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll(".team-link"), function (link) {
      if (link.dataset.cffDecorated === "1") return;
      var name = link.querySelector("span");
      if (!name) return;
      var fullName = name.textContent.trim();
      name.classList.add("team-name");
      var code = document.createElement("span");
      code.className = "team-code";
      code.textContent = CFF.teamCode(fullName);
      code.setAttribute("aria-hidden", "true");
      link.appendChild(code);
      link.dataset.cffDecorated = "1";
    });
  }

  decorate(document);
  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      Array.prototype.forEach.call(mutation.addedNodes, function (node) {
        if (node.nodeType !== 1) return;
        if (node.matches && node.matches(".team-link")) decorate(node.parentNode || document);
        else decorate(node);
      });
    });
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();

/* ---------------------------------------------------------------------
   Header search
   --------------------------------------------------------------------- */
(function () {
  var root = document.getElementById("siteSearch");
  if (!root) return;

  var INDEX = window.CFF_SEARCH_INDEX || [];
  var toggle = root.querySelector(".site-search__toggle");
  var closeBtn = root.querySelector(".site-search__close");
  var input = root.querySelector(".site-search__input");
  var results = root.querySelector(".site-search__results");
  var activeIndex = -1;
  var currentMatches = [];

  function matches(query) {
    var q = query.trim().toLowerCase();
    if (!q) return [];
    return INDEX.filter(function (t) {
      return t.team.toLowerCase().indexOf(q) !== -1 ||
        t.conf.toLowerCase().indexOf(q) !== -1 ||
        CFF.teamCode(t.team).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 8);
  }

  function renderResults() {
    results.innerHTML = "";
    if (currentMatches.length === 0) {
      results.hidden = true;
      return;
    }
    results.hidden = false;
    currentMatches.forEach(function (t, i) {
      var a = document.createElement("a");
      a.className = "site-search__result" + (i === activeIndex ? " active" : "");
      a.href = "team.html?team=" + encodeURIComponent(t.slug);

      var img = document.createElement("img");
      img.src = CFF.logoUrl(t.teamId, 64);
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.onerror = function () { img.style.visibility = "hidden"; };
      a.appendChild(img);

      var name = document.createElement("span");
      name.className = "site-search__result-name";
      name.textContent = t.team;
      a.appendChild(name);

      var conf = document.createElement("span");
      conf.className = "site-search__result-conf";
      conf.textContent = CFF.teamCode(t.team) + " · " + t.conf;
      a.appendChild(conf);

      results.appendChild(a);
    });
  }

  function openPanel() {
    root.classList.add("site-search--open");
    document.body.classList.add("search-open");
    input.focus();
  }

  function closePanel() {
    root.classList.remove("site-search--open");
    document.body.classList.remove("search-open");
    results.hidden = true;
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (root.classList.contains("site-search--open")) closePanel();
      else openPanel();
    });
  }
  if (closeBtn) closeBtn.addEventListener("click", closePanel);

  input.addEventListener("input", function () {
    activeIndex = -1;
    currentMatches = matches(input.value);
    renderResults();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!currentMatches.length) return;
      activeIndex = Math.min(activeIndex + 1, currentMatches.length - 1);
      renderResults();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!currentMatches.length) return;
      activeIndex = Math.max(activeIndex - 1, 0);
      renderResults();
    } else if (e.key === "Enter") {
      e.preventDefault();
      var target = currentMatches[activeIndex >= 0 ? activeIndex : 0];
      if (target) window.location.href = "team.html?team=" + encodeURIComponent(target.slug);
      else if (input.value.trim()) window.location.href = "index.html?q=" + encodeURIComponent(input.value.trim());
    } else if (e.key === "Escape") closePanel();
  });

  document.addEventListener("click", function (e) {
    if (!root.contains(e.target)) closePanel();
  });
})();

/* ---------------------------------------------------------------------
   Tap/hover metric tooltips
   --------------------------------------------------------------------- */
(function () {
  var bubble = document.createElement("div");
  bubble.className = "tip-bubble";
  bubble.hidden = true;
  document.body.appendChild(bubble);

  var pinned = false;
  var current = null;

  function place(trigger) {
    var rect = trigger.getBoundingClientRect();
    bubble.style.left = "0px";
    bubble.style.top = "0px";
    bubble.hidden = false;
    var bw = bubble.offsetWidth;
    var left = rect.left + rect.width / 2 - bw / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
    bubble.style.left = left + "px";
    bubble.style.top = rect.bottom + 8 + "px";
  }

  function show(trigger) {
    bubble.textContent = trigger.getAttribute("data-tip");
    current = trigger;
    place(trigger);
  }

  function hide() {
    bubble.hidden = true;
    current = null;
    pinned = false;
  }

  document.addEventListener("mouseover", function (e) {
    var trigger = e.target.closest("[data-tip]");
    if (trigger) show(trigger);
  });
  document.addEventListener("mouseout", function (e) {
    if (pinned) return;
    if (e.target.closest("[data-tip]")) hide();
  });
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest("[data-tip]");
    if (trigger) {
      e.stopPropagation();
      if (pinned && current === trigger) hide();
      else { show(trigger); pinned = true; }
      return;
    }
    if (!bubble.contains(e.target)) hide();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") hide(); });
  window.addEventListener("scroll", function () { if (current) place(current); }, true);
})();
