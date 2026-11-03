/* KTS 5.0 portal · progressive enhancement (no framework, no dependencies) */
(function () {
  "use strict";

  // ---- interface strings in the language of the page ----------------------
  var MSG = {};
  try { MSG = JSON.parse(document.getElementById("i18n").textContent) || {}; } catch (e) { MSG = {}; }
  function text(key, fallback) { return MSG[key] && MSG[key] !== key ? MSG[key] : fallback; }

  // ---- mobile navigation ---------------------------------------------------
  var toggle = document.querySelector(".nav .toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var ul = document.querySelector(".nav ul");
      var open = ul.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // ---- countdown ----------------------------------------------------------
  document.querySelectorAll("[data-countdown]").forEach(function (el) {
    var target = new Date(el.getAttribute("data-countdown"));
    if (isNaN(target.getTime())) return;
    var units = ["d", "h", "m", "s"].map(function (k) { return el.querySelector("[data-u='" + k + "']"); });
    var label = el.querySelector("[data-cd-label]"), ended = false;
    function tick() {
      if (ended) return;
      var diff = Math.max(0, Math.floor((target - new Date()) / 1000));
      var d = Math.floor(diff / 86400), h = Math.floor(diff % 86400 / 3600), m = Math.floor(diff % 3600 / 60), s = diff % 60;
      [d, h, m, s].forEach(function (v, i) { if (units[i]) units[i].textContent = i ? String(v).padStart(2, "0") : v; });
      if (diff > 0 || !el.dataset.done) return;
      ended = true;
      // the countdown to Kashi Tamil Sangamam 5.0 (1.2.50): the label says that it is under way
      if (label) { label.textContent = el.dataset.done; el.classList.add("live"); el.querySelector(".units").remove(); }
      else { var b = document.createElement("b"); b.textContent = el.dataset.done; el.querySelector(".units").replaceChildren(b); }
      // the launch of the registration portal (1.2.69): at the hour the page loads again, a few seconds apart for each visitor
      if (el.dataset.reload) setTimeout(function () { window.location.reload(); }, 3000 + Math.floor(Math.random() * 17000));
    }
    tick(); setInterval(tick, 1000);
  });

  // ---- a couplet keeps its two lines whole: four words, then three (1.2.58) --------------
  // When a line is wider than its box, the couplet's type is made smaller, both lines alike, down to 11px.
  var couplets = document.querySelectorAll(".couplet");
  function fitCouplets() {
    couplets.forEach(function (p) {
      p.style.fontSize = "";
      var avail = p.clientWidth, widest = 0;
      if (!avail) return;
      Array.prototype.forEach.call(p.children, function (line) { widest = Math.max(widest, line.scrollWidth); });
      if (widest > avail) p.style.fontSize = Math.max(11, parseFloat(getComputedStyle(p).fontSize) * avail / widest * 0.97) + "px";
    });
  }
  if (couplets.length) {
    fitCouplets();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitCouplets);
    var coupletWidth = window.innerWidth;
    window.addEventListener("resize", function () {
      if (window.innerWidth !== coupletWidth) { coupletWidth = window.innerWidth; fitCouplets(); }
    });
  }

  // ---- confirm dialogs ----------------------------------------------------
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault(); });
  });
  // one button of a form with several: a refusal stops the click, and with it the form.
  // Buttons and links only: #exam-app keeps the question of the test in the same attribute.
  document.querySelectorAll("button[data-confirm], a[data-confirm]").forEach(function (b) {
    b.addEventListener("click", function (e) { if (!window.confirm(b.getAttribute("data-confirm"))) e.preventDefault(); });
  });

  // ---- print buttons (the pages carry no script of their own) -------------
  document.querySelectorAll("[data-print]").forEach(function (b) {
    b.addEventListener("click", function () { window.print(); });
  });

  // ---- chapter list of the Thirukkural browser: opened at the chapter shown -----
  document.querySelectorAll(".chapter-list").forEach(function (list) {
    var on = list.querySelector("a.on");
    if (on && list.scrollHeight > list.clientHeight + 4) {
      list.scrollTop = Math.max(0, on.offsetTop - list.clientHeight / 2 + on.offsetHeight / 2);
    }
  });

  // ---- auto-submit selects (language/chapter pickers) --------------------
  document.querySelectorAll("select[data-autosubmit]").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });

  // ---- registration helpers ----------------------------------------------
  var state = document.getElementById("state"), cstate = document.getElementById("college_state");
  if (state && cstate) {
    state.addEventListener("change", function () { if (!cstate.value) cstate.value = state.value; });
  }
  var mobile = document.getElementById("mobile"), wa = document.getElementById("whatsapp"), same = document.getElementById("same_wa");
  if (mobile && wa && same) {
    same.addEventListener("change", function () { if (same.checked) { wa.value = mobile.value; wa.readOnly = true; } else { wa.readOnly = false; } });
    mobile.addEventListener("input", function () { if (same.checked) wa.value = mobile.value; });
  }
  document.querySelectorAll("input[type=file][data-max]").forEach(function (inp) {
    inp.addEventListener("change", function () {
      var max = parseInt(inp.dataset.max, 10), f = inp.files[0], msg = inp.parentElement.querySelector(".file-msg");
      if (!msg) { msg = document.createElement("div"); msg.className = "file-msg small"; inp.parentElement.appendChild(msg); }
      if (msg) msg.dir = "auto";
      if (f && f.size > max) { msg.textContent = text("js.file_big", "This file is too large.") + " " + (f.size / 1024).toFixed(0) + " KB > " + (max / 1024).toFixed(0) + " KB"; msg.style.color = "var(--kumkum)"; }
      else if (f) { msg.textContent = f.name + " · " + (f.size / 1024).toFixed(0) + " KB"; msg.style.color = "var(--green)"; }
    });
  });
  document.querySelectorAll("form[data-once]").forEach(function (f) {
    f.addEventListener("submit", function () {
      var b = f.querySelector("button[type=submit]");
      if (b) { b.disabled = true; b.textContent = b.dataset.busy || text("js.wait", "Please wait…"); }
    });
  });

  // ---- select-all checkboxes (console lists) -----------------------------
  var all = document.getElementById("check-all");
  if (all) all.addEventListener("change", function () {
    document.querySelectorAll("input[name=ids]").forEach(function (c) { c.checked = all.checked; });
  });

  // ---- exam engine -------------------------------------------------------
  var exam = document.getElementById("exam-app");
  if (exam) {
    var csrf = exam.dataset.csrf, saveUrl = exam.dataset.save, submitForm = document.getElementById("submit-form");
    var remaining = parseInt(exam.dataset.remaining, 10), timerEl = document.getElementById("timer");
    var answers = {}, dirty = {}, saving = false, submitted = false;
    exam.querySelectorAll("input[type=radio]:checked").forEach(function (r) { answers[r.name.replace("q", "")] = r.value; });
    var paletteLinks = {};
    document.querySelectorAll(".palette a").forEach(function (a) { paletteLinks[a.dataset.q] = a; });
    function paint() {
      var n = 0;
      Object.keys(answers).forEach(function (q) { n++; if (paletteLinks[q]) paletteLinks[q].classList.add("done"); });
      var c = document.getElementById("answered"); if (c) c.textContent = n;
      exam.querySelectorAll(".opt").forEach(function (o) { o.classList.toggle("on", o.querySelector("input").checked); });
    }
    exam.addEventListener("change", function (e) {
      if (e.target.type !== "radio") return;
      var q = e.target.name.replace("q", "");
      answers[q] = e.target.value; dirty[q] = e.target.value; paint(); scheduleSave();
    });
    var saveTimer = null;
    function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(save, 900); }
    function save() {
      if (saving || submitted) { scheduleSave(); return; }
      var payload = dirty; dirty = {}; if (!Object.keys(payload).length) return;
      saving = true; setState(text("js.saving", "Saving…"));
      fetch(saveUrl, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ answers: payload }) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          saving = false;
          if (res.ok && res.j.ok) { setState(text("js.saved", "Saved") + " · " + res.j.saved + " " + text("exam.answered", "answered")); if (typeof res.j.remaining === "number") remaining = Math.min(remaining, res.j.remaining); }
          else if (res.j && res.j.reason === "expired") { finish(); }
          else { setState(text("js.not_saved", "Not saved. Trying again…")); Object.keys(payload).forEach(function (k) { dirty[k] = payload[k]; }); scheduleSave(); }
        })
        .catch(function () { saving = false; setState(text("js.offline", "No internet connection. Trying again…")); Object.keys(payload).forEach(function (k) { dirty[k] = payload[k]; }); setTimeout(scheduleSave, 3000); });
    }
    function setState(t) { var s = document.getElementById("save-state"); if (s) s.textContent = t; }
    // When the time is up, every page of the test would send its paper in the same second: the answers
    // are locked, kept in the form, and the paper goes in after a random 0-20 seconds, well inside the
    // 45 seconds that the portal still takes as in time (version 1.2.36, after the load test). A paper
    // sent by the student, or one the portal already holds as over, goes in at once.
    function finish(spread) {
      if (submitted) return; submitted = true; window.onbeforeunload = null;
      document.getElementById("answers-field").value = JSON.stringify(answers);
      if (!spread) { submitForm.submit(); return; }
      exam.querySelectorAll("input[type=radio]").forEach(function (r) { r.disabled = true; });
      submitForm.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      setState(text("js.time_up", "Time is up. Your answers are saved and are being submitted; please wait and do not close this page."));
      setTimeout(function () { submitForm.submit(); }, Math.floor(Math.random() * 20000));
    }
    function tick() {
      if (submitted) return;
      remaining -= 1;
      var m = Math.floor(Math.max(0, remaining) / 60), s = Math.max(0, remaining) % 60;
      timerEl.textContent = String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
      if (remaining <= 120) timerEl.classList.add("low");
      if (remaining <= 0) finish(true);
    }
    setInterval(tick, 1000); tick(); paint();
    submitForm.addEventListener("submit", function (e) {
      if (submitted) return;
      e.preventDefault();
      var n = Object.keys(answers).length, total = parseInt(exam.dataset.total, 10);
      var question = exam.dataset.confirm + (n < total ? "\n(" + (total - n) + " " + text("js.unanswered", "not answered") + ")" : "");
      if (window.confirm(question)) finish();
    });
    window.onbeforeunload = function () { return "The test is in progress."; };
    window.addEventListener("keydown", function (e) { if (e.key === "F5" || (e.ctrlKey && e.key.toLowerCase() === "r")) e.preventDefault(); });
  }
})();

// Registration (1.2.47): the list of participating institutions shows those of the State/UT chosen.
(function () {
  var pick = document.querySelector("[data-hei-pick]");
  if (!pick) return;
  var state = document.getElementById("college_state");
  function update() {
    var chosen = state ? state.value : "";
    pick.querySelectorAll("optgroup").forEach(function (g) {
      var on = !chosen || g.getAttribute("data-state") === chosen;
      g.hidden = !on; g.disabled = !on;
    });
    var opt = pick.options[pick.selectedIndex];
    if (opt && opt.parentNode.tagName === "OPTGROUP" && opt.parentNode.disabled) pick.value = "";
  }
  if (state) state.addEventListener("change", update);
  update();
})();

// Hear the couplet in Tamil (1.2.82): one player for the page. A second press pauses the couplet, a third goes on; another
// couplet stops the first. "Slower" reads at three quarters of the speed, at the same pitch.
(function () {
  var buttons = document.querySelectorAll("[data-listen]");
  if (!buttons.length) return;
  var audio = null, current = null, slow = false;
  function show(b, playing) {
    if (!b) return;
    b.classList.toggle("playing", playing);
    b.querySelector(".ico").textContent = playing ? "\u23F8" : "\uD83D\uDD0A";
    var lbl = b.querySelector(".lbl"), n = lbl.textContent.split(" · ")[1];
    lbl.textContent = b.getAttribute(playing ? "data-pause" : "data-play") + (n ? " · " + n : "");
  }
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      if (current === b && !audio.paused) { audio.pause(); return; }
      if (current !== b) {
        if (audio) audio.pause();
        show(current, false);
        var a = audio = new Audio(b.getAttribute("data-listen"));
        current = b;
        a.addEventListener("playing", function () { if (audio === a) show(b, true); });
        a.addEventListener("pause", function () { if (audio === a) show(b, false); });
        a.addEventListener("ended", function () { if (audio === a) show(b, false); });
        a.addEventListener("error", function () { if (audio === a) { show(b, false); current = null; } });
      }
      audio.playbackRate = slow ? 0.75 : 1;
      var p = audio.play();
      if (p && p.catch) p.catch(function () { show(b, false); });
    });
  });
  document.querySelectorAll("[data-slower]").forEach(function (s) {
    s.addEventListener("click", function () {
      slow = !slow;
      document.querySelectorAll("[data-slower]").forEach(function (x) { x.setAttribute("aria-pressed", slow ? "true" : "false"); });
      if (audio) audio.playbackRate = slow ? 0.75 : 1;
    });
  });
})();

// The Back button (1.2.77): back to the previous page when it was a page of the portal; otherwise its own link (the
// home page, or the dashboard of the Console) is followed.
(function () {
  document.querySelectorAll("[data-back]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      var ref = document.referrer;
      if (ref && ref.indexOf(location.origin + "/") === 0 && ref !== location.href && history.length > 1) {
        e.preventDefault();
        history.back();
      }
    });
  });
})();

// The video guide to the portal (1.2.128): a poster pressed plays its video in the page, in YouTube's player from
// www.youtube-nocookie.com (the only frame the policy of the portal allows); nothing of YouTube loads before. Without scripts,
// the poster's link opens the video on YouTube.
(function () {
  document.querySelectorAll("a[data-yt]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      var id = a.getAttribute("data-yt") || "";
      if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return;
      e.preventDefault();
      var f = document.createElement("iframe");
      f.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
      f.title = (a.getAttribute("aria-label") || "").replace(/^\u25B6\s*/, "");
      f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
      f.allowFullscreen = true;
      f.referrerPolicy = "strict-origin-when-cross-origin";
      f.className = "gv-frame";
      var card = a.closest(".gv-card");
      if (card) card.classList.add("gv-playing");
      a.replaceWith(f);
      f.focus();
    });
  });
})();

// KTS 5.0 in numbers (1.2.129): each figure counts up from nought as its tile comes into view, in the grouping of India
// (1,00,000); not for a visitor who asks for reduced motion, nor in a browser without the observer: the figure is written
// in the page already.
(function () {
  var els = document.querySelectorAll("[data-count]");
  if (!els.length) return;
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (still || !("IntersectionObserver" in window) || !window.Intl) {
    els.forEach(function (el) { var t = el.closest(".num-tile"); if (t) t.classList.add("num-in"); });
    return;
  }
  var fmt = new Intl.NumberFormat("en-IN");
  function run(el) {
    var end = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(end)) return;
    var start = null, span = 900 + Math.min(900, end / 100);
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / span), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt.format(Math.round(end * e));
      if (p < 1) requestAnimationFrame(step); else el.textContent = fmt.format(end);
    }
    requestAnimationFrame(step);
  }
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      seen.unobserve(en.target);
      var tile = en.target.closest(".num-tile");
      if (tile) tile.classList.add("num-in");
      run(en.target);
    });
  }, { threshold: 0.35 });
  els.forEach(function (el) { seen.observe(el); });
})();


// The progress of the institutions (1.2.138): the rings and the bars grow once the page is in view, and the figures refresh
// every minute from /progress.json while the page is shown; every figure is written in the page already.
(function () {
  var root = document.querySelector("[data-progress]");
  if (!root) return;
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function reveal() { root.classList.add("prog-in"); }
  if (still || !("IntersectionObserver" in window)) {
    reveal();
  } else {
    var io = new IntersectionObserver(function (entries) {
      if (entries.some(function (e) { return e.isIntersecting; })) { reveal(); io.disconnect(); }
    }, { threshold: 0.05 });
    io.observe(root);
    setTimeout(reveal, 1500);
  }
  var fmt = window.Intl ? new Intl.NumberFormat("en-IN") : null;
  function put(key, value) {
    root.querySelectorAll('[data-k="' + key + '"]').forEach(function (el) {
      var tpl = el.getAttribute("data-tpl");
      el.textContent = tpl ? tpl.replace("{n}", value) : (typeof value === "number" && fmt ? fmt.format(value) : value);
    });
  }
  function apply(d) {
    Object.keys(d.flat || {}).forEach(function (k) { put(k, d.flat[k]); });
    Object.keys(d.shares || {}).forEach(function (k) {
      root.querySelectorAll('[data-ring="' + k + '"]').forEach(function (el) { el.style.setProperty("--share", d.shares[k]); });
    });
    Object.keys(d.widths || {}).forEach(function (k) {
      root.querySelectorAll('[data-bar="' + k + '"]').forEach(function (el) { el.style.setProperty("--w", d.widths[k] + "%"); });
    });
    Object.keys(d.series || {}).forEach(function (k) {
      var line = root.querySelector('[data-line="' + k + '"]'), area = root.querySelector('[data-area="' + k + '"]');
      if (line) line.setAttribute("points", d.series[k].points);
      if (area) area.setAttribute("points", d.series[k].area);
    });
  }
  function refresh() {
    if (document.hidden || !window.fetch) return;
    fetch(root.getAttribute("data-progress"), { cache: "no-store", credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) apply(d); })
      .catch(function () {});
  }
  setInterval(refresh, 60000);
})();


// "Find your next step" (1.2.140): the tabs of the hub of the home page (the last one chosen is remembered in this browser, a
// #hub-inst or #hub-nodal in the address opens that one), the search of the Participating Institutions as the student types,
// and the copy of the message to the Principal. Without the script the panels stand one under the other and the search is a form.
(function () {
  var root = document.querySelector("[data-hub]");
  if (!root) return;
  root.classList.add("hub-js");
  var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-hub-tab]"));
  var panels = root.querySelectorAll("[data-hub-panel]");
  var keys = tabs.map(function (t) { return t.getAttribute("data-hub-tab"); });
  function show(key, focus, remember) {
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-hub-tab") === key;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    });
    panels.forEach(function (p) { p.classList.toggle("on", p.getAttribute("data-hub-panel") === key); });
    if (remember) { try { localStorage.setItem("kts.hub", key); } catch (e) {} }
  }
  var start = root.getAttribute("data-hub-start");
  var fromHash = (location.hash || "").replace("#hub-", "");
  if (!start && keys.indexOf(fromHash) >= 0) start = fromHash;
  if (!start) { try { start = localStorage.getItem("kts.hub"); } catch (e) {} }
  show(keys.indexOf(start) >= 0 ? start : keys[0], false, false);
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { show(t.getAttribute("data-hub-tab"), false, true); });
    t.addEventListener("keydown", function (ev) {
      var step = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      if (document.documentElement.dir === "rtl") step = -step;
      ev.preventDefault();
      show(keys[(i + step + keys.length) % keys.length], true, true);
    });
  });

  // the search of the Participating Institutions
  var form = root.querySelector("[data-hub-find]");
  var out = root.querySelector("[data-hub-results]");
  var invite = root.querySelector("[data-hub-invite]");
  if (form && out && window.fetch) {
    var input = form.querySelector("input[name=q]");
    var url = form.getAttribute("data-hub-find");
    var timer = null, asked = 0;
    function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
    function render(d, q) {
      out.textContent = "";
      if (q.length < 3) { if (invite) invite.hidden = true; return; }
      if (d.results && d.results.length) {
        var ul = el("ul", "hub-list");
        d.results.forEach(function (r) {
          var li = el("li"), a = el("a"), name = el("b", null, r.name), where = el("span", "small muted", (r.district ? r.district + " · " : "") + r.state);
          name.setAttribute("lang", "en"); name.setAttribute("dir", "ltr");
          a.href = r.url; a.appendChild(name); a.appendChild(where);
          li.appendChild(a); li.appendChild(el("span", "hub-yes", "✓ " + out.getAttribute("data-found")));
          ul.appendChild(li);
        });
        out.appendChild(ul);
        if (d.total > d.results.length) out.appendChild(el("p", "small muted", out.getAttribute("data-more").replace("{n}", d.total - d.results.length)));
        if (invite) invite.hidden = true;
      } else {
        out.appendChild(el("p", "hub-none", out.getAttribute("data-none")));
        if (invite) invite.hidden = false;
      }
    }
    function ask(q) {
      var n = ++asked;
      if (q.length < 3) { render({}, q); return; }
      fetch(url + (url.indexOf("?") >= 0 ? "&" : "?") + "q=" + encodeURIComponent(q), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && n === asked) render(d, q); })
        .catch(function () {});
    }
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      timer = setTimeout(function () { ask(q); }, 250);
    });
    form.addEventListener("submit", function (ev) { ev.preventDefault(); clearTimeout(timer); ask(input.value.trim()); });
    if (input.value.trim().length >= 3) ask(input.value.trim());
  }

  // the copy of the message to the Principal
  var copy = root.querySelector("[data-hub-copy]");
  var msg = root.querySelector("[data-hub-msg]");
  if (copy && msg && navigator.clipboard) {
    copy.hidden = false;
    var label = copy.textContent;
    copy.addEventListener("click", function () {
      navigator.clipboard.writeText(msg.textContent.trim()).then(function () {
        copy.textContent = "✓ " + copy.getAttribute("data-done");
        setTimeout(function () { copy.textContent = label; }, 2200);
      }).catch(function () {});
    });
  }
})();


// The State/UT pages (1.2.142): a button that copies a message ([data-copy] names the element whose text it copies) and one
// that opens the phone's own share sheet ([data-share]); both stay hidden where the browser cannot do it.
(function () {
  if (navigator.clipboard) {
    document.querySelectorAll("[data-copy]").forEach(function (b) {
      var src = document.getElementById(b.getAttribute("data-copy"));
      if (!src) return;
      b.hidden = false;
      var label = b.textContent;
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(src.textContent.trim()).then(function () {
          b.textContent = "✓ " + b.getAttribute("data-done");
          setTimeout(function () { b.textContent = label; }, 2200);
        }).catch(function () {});
      });
    });
  }
  if (navigator.share) {
    document.querySelectorAll("[data-share]").forEach(function (b) {
      b.hidden = false;
      b.addEventListener("click", function () {
        navigator.share({ text: b.getAttribute("data-text"), url: b.getAttribute("data-url") }).catch(function () {});
      });
    });
  }
})();
