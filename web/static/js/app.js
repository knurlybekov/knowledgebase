// Small, framework-free behaviors: theme toggle and evidence linking.
(function () {
  "use strict";

  // --- Theme -----------------------------------------------------------------
  var root = document.documentElement;
  function setTheme(next) {
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) { /* storage blocked: the choice lasts for this page */ }
  }
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-theme-toggle]");
    if (!toggle) return;
    setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });

  // --- Evidence linking --------------------------------------------------------
  // A claim carries data-ev="id1 id2"; a source card carries data-ev-id="id1".
  // Hovering or focusing one side lights the other, with the same class on both.
  var LINKED = "is-linked";

  function sourcesFor(ids) {
    return ids.map(function (id) {
      return document.querySelector('[data-ev-id="' + id + '"]');
    }).filter(Boolean);
  }
  function claimsFor(id) {
    return Array.prototype.slice.call(document.querySelectorAll("[data-ev]")).filter(function (el) {
      return el.getAttribute("data-ev").split(/\s+/).indexOf(id) !== -1;
    });
  }
  function clear() {
    Array.prototype.forEach.call(document.querySelectorAll("." + LINKED), function (el) {
      el.classList.remove(LINKED);
    });
  }
  function light(el) {
    clear();
    var claim = el.closest("[data-ev]");
    var source = el.closest("[data-ev-id]");
    if (claim) {
      claim.classList.add(LINKED);
      sourcesFor(claim.getAttribute("data-ev").split(/\s+/)).forEach(function (s) { s.classList.add(LINKED); });
      Array.prototype.forEach.call(claim.querySelectorAll(".cite"), function (c) { c.classList.add(LINKED); });
    } else if (source) {
      source.classList.add(LINKED);
      claimsFor(source.getAttribute("data-ev-id")).forEach(function (c) { c.classList.add(LINKED); });
    }
  }
  function onEnter(event) {
    var el = event.target.closest("[data-ev], [data-ev-id]");
    if (el) light(el);
  }
  function onLeave(event) {
    var el = event.target.closest("[data-ev], [data-ev-id]");
    if (el) clear();
  }
  document.addEventListener("mouseover", onEnter);
  document.addEventListener("mouseout", onLeave);
  document.addEventListener("focusin", onEnter);
  document.addEventListener("focusout", onLeave);

  // A citation chip click scrolls to its source and keeps it lit for a moment.
  document.addEventListener("click", function (event) {
    var chip = event.target.closest("a.cite[href^='#']");
    if (!chip) return;
    var target = document.querySelector(chip.getAttribute("href"));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    light(target);
    target.focus({ preventScroll: true });
  });
})();
