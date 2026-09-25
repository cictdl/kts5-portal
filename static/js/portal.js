/* KTS 5.0 portal · progressive enhancement (no framework, no dependencies) */
(function () {
  "use strict";

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
      if (f && f.size > max) { msg.textContent = "File is " + (f.size / 1024).toFixed(0) + " KB; the limit is " + (max / 1024).toFixed(0) + " KB."; msg.style.color = "var(--kumkum)"; }
      else if (f) { msg.textContent = f.name + " · " + (f.size / 1024).toFixed(0) + " KB"; msg.style.color = "var(--green)"; }
    });
  });
  document.querySelectorAll("form[data-once]").forEach(function (f) {
    f.addEventListener("submit", function () {
      var b = f.querySelector("button[type=submit]");
      if (b) { b.disabled = true; b.textContent = b.dataset.busy || "Please wait…"; }
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
      saving = true; setState("Saving…");
      fetch(saveUrl, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ answers: payload }) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          saving = false;
          if (res.ok && res.j.ok) { setState("Saved · " + res.j.saved + " answered"); if (typeof res.j.remaining === "number") remaining = Math.min(remaining, res.j.remaining); }
          else if (res.j && res.j.reason === "expired") { finish(); }
          else { setState("Not saved – retrying"); Object.keys(payload).forEach(function (k) { dirty[k] = payload[k]; }); scheduleSave(); }
        })
        .catch(function () { saving = false; setState("Offline – retrying"); Object.keys(payload).forEach(function (k) { dirty[k] = payload[k]; }); setTimeout(scheduleSave, 3000); });
    }
    function setState(t) { var s = document.getElementById("save-state"); if (s) s.textContent = t; }
    function finish() {
      if (submitted) return; submitted = true; window.onbeforeunload = null;
      document.getElementById("answers-field").value = JSON.stringify(answers);
      submitForm.submit();
    }
    function tick() {
      if (submitted) return;
      remaining -= 1;
      var m = Math.floor(Math.max(0, remaining) / 60), s = Math.max(0, remaining) % 60;
      timerEl.textContent = String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
      if (remaining <= 120) timerEl.classList.add("low");
      if (remaining <= 0) finish();
    }
    setInterval(tick, 1000); tick(); paint();
    submitForm.addEventListener("submit", function (e) {
      if (submitted) return;
      e.preventDefault();
      var n = Object.keys(answers).length, total = parseInt(exam.dataset.total, 10);
      var msg = exam.dataset.confirm + (n < total ? "\n(" + (total - n) + " unanswered)" : "");
      if (window.confirm(msg)) finish();
    });
    window.onbeforeunload = function () { return "The test is in progress."; };
    window.addEventListener("keydown", function (e) { if (e.key === "F5" || (e.ctrlKey && e.key.toLowerCase() === "r")) e.preventDefault(); });
  }
})();
