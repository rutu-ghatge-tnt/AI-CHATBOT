/**
 * HLHP Streak UI hotfix for Skintruth embed (localhost:5174).
 * Load once: <script src="http://localhost:8000/hlhp-ui/hlhp-streak-patch.js" defer></script>
 *
 * Fixes legacy prototype markup:
 *  - .day-dot.done was orange; logged days should be green
 *  - .day-dot.today overrode .done; only today looked green
 *  - counter digits stacked inside flameFlicker animation
 */
(function () {
  "use strict";

  var DONE = "linear-gradient(135deg, #65a30d, #a3e635)";
  var MISSED = "linear-gradient(135deg, #dc2626, #ef4444)";
  var RING = "0 0 0 3px rgba(26, 43, 71, 0.35)";

  function patchDots(root) {
    var dots = (root || document).querySelectorAll(".day-dot, [data-hlhp-day-dot]");
    dots.forEach(function (el) {
      var today = el.classList.contains("today") || el.getAttribute("data-today") === "true";
      var doneAttr = el.getAttribute("data-done");
      var done;
      if (doneAttr === "true") done = true;
      else if (doneAttr === "false") done = false;
      else {
        done = el.classList.contains("done");
        // Legacy embed: className = today ? " today" : done ? " done" (drops .done on today)
        if (today) done = true;
      }

      el.style.background = done ? DONE : MISSED;
      el.style.color = "#fff";
      el.style.fontWeight = "600";
      el.style.display = "flex";
      el.style.alignItems = "center";
      el.style.justifyContent = "center";
      el.style.boxShadow = today ? RING : "";
      if (done) el.classList.add("done");
      if (!done) el.classList.add("missed");
      if (today) el.classList.add("today");
    });
  }

  function patchCounter(root) {
    var scope = root || document;
    var selectors = [
      "#s2-num",
      ".hlhp-streak-count",
      "[data-streak-count]",
      "[class*='streakCount']",
      "[class*='StreakCount']",
    ];
    selectors.forEach(function (sel) {
      scope.querySelectorAll(sel).forEach(fixCounterEl);
    });

    scope.querySelectorAll("[class*='digit'], [class*='roller'], [class*='Roller']").forEach(function (container) {
      var kids = container.querySelectorAll(":scope > span, :scope > div");
      if (kids.length !== 2) return;
      var n = parseInt(
        Array.prototype.map.call(kids, function (k) { return (k.textContent || "").trim(); }).join(""),
        10
      );
      if (isNaN(n)) return;
      var span = document.createElement("span");
      span.className = "hlhp-streak-count";
      span.textContent = String(n);
      span.style.cssText =
        "display:inline-block;white-space:nowrap;line-height:1;font-size:32px;font-weight:600;color:#fff;text-shadow:0 2px 4px rgba(0,0,0,.35);font-variant-numeric:tabular-nums";
      container.replaceWith(span);
      fixCounterEl(span);
    });
  }

  function fixCounterEl(el) {
    if (!el || el.dataset.hlhpCounterFixed === "1") return;
    var raw = (el.textContent || "").replace(/\s/g, "");
    var n = parseInt(raw, 10);
    if (!isNaN(n)) el.textContent = String(n);

    el.style.display = "inline-block";
    el.style.whiteSpace = "nowrap";
    el.style.lineHeight = "1";
    el.style.fontVariantNumeric = "tabular-nums";

    var anim = el.closest(".flame-anim, .flame-wrap, [class*='flameFlicker'], [class*='Flame']");
    if (anim && anim.parentElement) {
      var stack = anim.parentElement;
      stack.appendChild(el);
      el.style.position = "absolute";
      el.style.left = "0";
      el.style.right = "0";
      el.style.bottom = "26px";
      el.style.zIndex = "3";
      el.style.textAlign = "center";
      el.style.pointerEvents = "none";
    }
    el.dataset.hlhpCounterFixed = "1";
  }

  function patch(root) {
    try {
      patchDots(root);
      patchCounter(root);
    } catch (e) {
      /* ignore */
    }
  }

  patch();
  var t = 0;
  var interval = setInterval(function () {
    patch();
    if (++t > 40) clearInterval(interval);
  }, 250);

  if (typeof MutationObserver !== "undefined") {
    var mo = new MutationObserver(function () { patch(); });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }

  window.HLHP_STREAK_PATCH = { patch: patch };
})();
