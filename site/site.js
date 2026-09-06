/* ==========================================================================
   CollegeFootballFocus — shared site chrome
   Header search + tap/hover tooltips. Loaded on every page, after
   search-index.js and before the page-specific script (app.js / advanced.js
   / team.js).
   ========================================================================== */

window.CFF = window.CFF || {};

CFF.getQueryParam = function (name) {
  return new URLSearchParams(window.location.search).get(name);
};

CFF.logoUrl = function (teamId, size) {
  return "https://cdn.collegefootballdata.com/logos/" + (size || 64) + "/" + teamId + ".png";
};

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
      return t.team.toLowerCase().indexOf(q) !== -1 || t.conf.toLowerCase().indexOf(q) !== -1;
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
      img.onerror = function () { img.style.visibility = "hidden"; };
      a.appendChild(img);

      var name = document.createElement("span");
      name.className = "site-search__result-name";
      name.textContent = t.team;
      a.appendChild(name);

      var conf = document.createElement("span");
      conf.className = "site-search__result-conf";
      conf.textContent = t.conf;
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
      if (root.classList.contains("site-search--open")) {
        closePanel();
      } else {
        openPanel();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", closePanel);
  }

  input.addEventListener("input", function () {
    activeIndex = -1;
    currentMatches = matches(input.value);
    renderResults();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (currentMatches.length === 0) return;
      activeIndex = Math.min(activeIndex + 1, currentMatches.length - 1);
      renderResults();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (currentMatches.length === 0) return;
      activeIndex = Math.max(activeIndex - 1, 0);
      renderResults();
    } else if (e.key === "Enter") {
      e.preventDefault();
      var target = currentMatches[activeIndex >= 0 ? activeIndex : 0];
      if (target) {
        window.location.href = "team.html?team=" + encodeURIComponent(target.slug);
      } else if (input.value.trim()) {
        window.location.href = "index.html?q=" + encodeURIComponent(input.value.trim());
      }
    } else if (e.key === "Escape") {
      closePanel();
    }
  });

  document.addEventListener("click", function (e) {
    if (!root.contains(e.target)) closePanel();
  });
})();

/* ---------------------------------------------------------------------
   Tap/hover metric tooltips — any element carrying data-tip gets a
   small "?" affordance (via CSS ::after) and a floating explanation
   that opens on hover (desktop) or tap (mobile), independent of any
   click handler on an ancestor (e.g. a sortable column header).
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
    var top = rect.bottom + 8;
    bubble.style.left = left + "px";
    bubble.style.top = top + "px";
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
    var trigger = e.target.closest("[data-tip]");
    if (trigger) hide();
  });

  document.addEventListener("click", function (e) {
    var trigger = e.target.closest("[data-tip]");
    if (trigger) {
      e.stopPropagation();
      if (pinned && current === trigger) {
        hide();
      } else {
        show(trigger);
        pinned = true;
      }
      return;
    }
    if (!bubble.contains(e.target)) hide();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") hide();
  });

  window.addEventListener("scroll", function () {
    if (current) place(current);
  }, true);
})();
