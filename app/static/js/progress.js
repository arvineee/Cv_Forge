/*
 * CVForge progress overlay.
 *
 * Shows a progress bar while the server does slow work (AI, parsing,
 * generating files). The server doesn't report progress, so the bar is
 * estimated from elapsed time: it moves quickly at first, slows as it nears
 * 92%, and jumps to 100% when the request finishes.
 *
 * Use it from HTML:
 *   <form method="POST" data-progress="Revamping your CV" data-estimate="25">
 *   <button name="action" value="enhance" data-progress="Improving" data-estimate="12">
 *   <a href="..." data-progress="Preparing your file" data-estimate="4" data-autohide="10">
 *   htmx forms with data-progress are handled automatically.
 *
 * Use it from JavaScript:
 *   CVProgress.track(fetch(url, opts).then(r => r.json()), {label: "...", estimate: 12});
 */
(function () {
  "use strict";

  var overlay, bar, pct, label, note;
  var timer = null, autoHideTimer = null, startedAt = 0, estimateSec = 20;

  function ensure() {
    if (overlay) return true;
    overlay = document.getElementById("cv-progress");
    if (!overlay) return false;
    bar = document.getElementById("cv-progress-bar");
    pct = document.getElementById("cv-progress-pct");
    label = document.getElementById("cv-progress-label");
    note = document.getElementById("cv-progress-note");
    return true;
  }

  function paint(p) {
    bar.style.width = p.toFixed(1) + "%";
    pct.textContent = Math.round(p) + "%";
  }

  // Rises quickly, then slows, never passing 92% until the request finishes.
  function curve(elapsed, est) {
    return 92 * (1 - Math.exp(-2.5 * (elapsed / est)));
  }

  function tick() {
    var elapsed = (Date.now() - startedAt) / 1000;
    paint(curve(elapsed, estimateSec));
    if (elapsed > estimateSec * 1.5) {
      note.textContent = "Still working. Thanks for your patience. Please keep this page open.";
    }
  }

  function show(text, opts) {
    if (!ensure()) return;
    opts = opts || {};
    clearInterval(timer);
    clearTimeout(autoHideTimer);
    estimateSec = Math.max(3, Number(opts.estimate) || 20);
    label.textContent = text || "Working…";
    note.textContent = "This usually takes about " + estimateSec + " seconds. Please keep this page open.";
    startedAt = Date.now();
    paint(0);
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-busy", "true");
    timer = setInterval(tick, 200);
    if (opts.autohide) {
      autoHideTimer = setTimeout(done, Number(opts.autohide) * 1000);
    }
  }

  function done() {
    if (!ensure()) return;
    clearInterval(timer);
    clearTimeout(autoHideTimer);
    paint(100);
    setTimeout(function () {
      overlay.classList.add("hidden");
      overlay.setAttribute("aria-busy", "false");
    }, 300);
  }

  function track(promise, opts) {
    show(opts && opts.label, opts);
    return Promise.resolve(promise).finally(done);
  }

  // Forms: a submit button can carry its own message (e.g. "Enhance with AI").
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    var btn = e.submitter;
    var src = btn && btn.hasAttribute("data-progress") ? btn
            : form.hasAttribute("data-progress") ? form : null;
    if (!src) return;
    show(src.getAttribute("data-progress"), { estimate: src.getAttribute("data-estimate") });
  });

  // Links that start a slow download.
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-progress]");
    if (!a) return;
    show(a.getAttribute("data-progress"), {
      estimate: a.getAttribute("data-estimate"),
      autohide: a.getAttribute("data-autohide") || 12,
    });
  });

  // htmx requests (used by the ATS check forms).
  document.addEventListener("htmx:beforeRequest", function (e) {
    var el = e.detail && e.detail.elt;
    if (el && el.hasAttribute && el.hasAttribute("data-progress")) {
      show(el.getAttribute("data-progress"), { estimate: el.getAttribute("data-estimate") });
    }
  });
  document.addEventListener("htmx:afterRequest", function (e) {
    var el = e.detail && e.detail.elt;
    if (el && el.hasAttribute && el.hasAttribute("data-progress")) done();
  });

  // Coming back with the browser's Back button must not leave the overlay showing.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) done();
  });

  window.CVProgress = { show: show, done: done, track: track };
})();
