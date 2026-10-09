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
    function tick() {
      var diff = Math.max(0, Math.floor((target - new Date()) / 1000));
      var d = Math.floor(diff / 86400), h = Math.floor(diff % 86400 / 3600), m = Math.floor(diff % 3600 / 60), s = diff % 60;
      [d, h, m, s].forEach(function (v, i) { if (units[i]) units[i].textContent = i ? String(v).padStart(2, "0") : v; });
      if (diff <= 0 && el.dataset.done) el.querySelector(".units").innerHTML = "<b>" + el.dataset.done + "</b>";
    }
    tick(); setInterval(tick, 1000);
  });

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

// Registration (1.2.41): the list of institutions shows those of the State/UT chosen; the details of an
// institution are typed only when it is not listed.
(function () {
  var pick = document.querySelector("[data-hei-pick]");
  if (!pick) return;
  var state = document.getElementById("college_state");
  var free = document.querySelector("[data-hei-free]");
  function update() {
    var chosen = state ? state.value : "";
    pick.querySelectorAll("optgroup").forEach(function (g) {
      var on = !chosen || g.getAttribute("data-state") === chosen;
      g.hidden = !on; g.disabled = !on;
    });
    var opt = pick.options[pick.selectedIndex];
    if (opt && opt.parentNode.tagName === "OPTGROUP" && opt.parentNode.disabled) pick.value = "";
    var listed = pick.value !== "" && pick.value !== "0";
    if (free) {
      free.hidden = listed;
      free.querySelectorAll("input, select").forEach(function (el) { el.disabled = listed; });
    }
  }
  if (state) state.addEventListener("change", update);
  pick.addEventListener("change", update);
  update();
})();
