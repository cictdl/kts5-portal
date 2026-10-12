/* Live banners for screens (1.2.61). The time comes from the portal (now.json), so a screen with a wrong clock
   still shows the time of India; the couplet changes when its slot ends, the same on every screen; when the
   network is down the banner keeps the time and the last couplet and asks again a minute later.
   Written for the older browsers of screen players: no modules, no arrow functions. */
(function () {
  "use strict";
  var body = document.getElementById("screen");

  // ---- the page of links (/display): copy a link, build it with its options -----------------------------
  document.querySelectorAll("[data-display-link]").forEach(function (card) {
    var out = card.querySelector("[data-link]"), base = out.getAttribute("data-base");
    var local = card.querySelector("[data-opt=local]"), every = card.querySelector("[data-opt=every]");
    var open = card.querySelector("[data-open]"), copy = card.querySelector("[data-copy]");
    function build() {
      var q = [];
      if (local && local.value) q.push("local=" + encodeURIComponent(local.value));
      if (every && every.value && every.value !== every.getAttribute("data-default")) q.push("every=" + encodeURIComponent(every.value));
      var url = base + (q.length ? "?" + q.join("&") : "");
      out.textContent = url; if (open) open.href = url;
    }
    [local, every].forEach(function (el) { if (el) el.addEventListener("change", build); });
    if (copy) copy.addEventListener("click", function () {
      var text = out.textContent, done = function () { copy.textContent = copy.getAttribute("data-done"); setTimeout(function () { copy.textContent = copy.getAttribute("data-label"); }, 2000); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { select(out); });
      else select(out);
    });
    build();
  });
  function select(el) { var r = document.createRange(); r.selectNodeContents(el); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }

  if (!body) return;

  // ---- the time of the portal ---------------------------------------------------------------------------
  var offset = 0;                         // portal time minus the screen's time, in ms
  var every = parseInt(body.getAttribute("data-every"), 10) * 60000;
  var nextAt = Date.now() + parseInt(body.getAttribute("data-left"), 10) * 1000;   // screen time of the next couplet
  var DAYS_TA = ["ஞாயிறு", "திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி"];
  var DAYS_HI = ["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"];
  var DAYS_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function ist() { return new Date(Date.now() + offset + 19800000); }   // read with the getUTC… methods
  function $(id) { return document.getElementById(id); }

  function tick() {
    var d = ist(), h = d.getUTCHours(), m = d.getUTCMinutes(), s = d.getUTCSeconds();
    var clock = $("clock");
    if (clock) clock.innerHTML = pad(h) + ":" + pad(m) + '<small id="clock-s">:' + pad(s) + "</small>";
    if ($("day-ta")) $("day-ta").textContent = DAYS_TA[d.getUTCDay()];
    if ($("day-hi")) $("day-hi").textContent = DAYS_HI[d.getUTCDay()];
    if ($("day-en")) $("day-en").textContent = DAYS_EN[d.getUTCDay()] + " " + pad(d.getUTCDate()) + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
    var hh = $("hand-h"), hm = $("hand-m"), hs = $("hand-s");
    if (hh) hh.setAttribute("transform", "rotate(" + ((h % 12) * 30 + m * 0.5) + " 50 50)");
    if (hm) hm.setAttribute("transform", "rotate(" + (m * 6 + s * 0.1) + " 50 50)");
    if (hs) hs.setAttribute("transform", "rotate(" + (s * 6) + " 50 50)");
    var bar = $("next-bar");
    if (bar && every) bar.style.width = Math.max(0, Math.min(100, 100 - (nextAt - Date.now()) / every * 100)) + "%";
    countdown();
  }

  // ---- the countdown to Kashi Tamil Sangamam 5.0 -----------------------------------------------------------
  var start = Date.parse(body.getAttribute("data-kts-start") || "");
  var endDay = body.getAttribute("data-kts-end") || "";
  var end = endDay ? Date.parse(endDay + "T23:59:59+05:30") : NaN;
  function countdown() {
    var units = $("count-units"), live = $("count-live");
    if (!units || isNaN(start)) return;
    var now = Date.now() + offset, left = Math.max(0, Math.floor((start - now) / 1000));
    if (left > 0) {
      var parts = { d: Math.floor(left / 86400), h: Math.floor(left % 86400 / 3600), m: Math.floor(left % 3600 / 60), s: left % 60 };
      units.querySelectorAll("[data-u]").forEach(function (b) { var u = b.getAttribute("data-u"); b.textContent = u === "d" ? parts.d : pad(parts[u]); });
      return;
    }
    units.hidden = true; live.hidden = false;
    if (isNaN(end) || now <= end) {
      var day = Math.floor((now - start) / 86400000) + 1;
      live.innerHTML = '<span lang="ta">காசி தமிழ்ச் சங்கமம் 5.0 நடைபெற்று வருகிறது</span><br><span lang="hi">काशी तमिल संगमम 5.0 जारी है</span> · ' +
        '<span lang="en">under way · day ' + day + "</span>";
    } else {
      live.innerHTML = '<span lang="ta">நன்றி</span> · <span lang="hi">धन्यवाद</span> · <span lang="en">Thank you</span>';
    }
  }

  // ---- fit: a couplet keeps four words, then three; the whole text fits the screen ------------------------
  function fit() {
    var main = $("kural");
    if (!main) return;
    // start from the sizes of the style sheet
    main.style.setProperty("--s", 1);
    main.querySelectorAll(".couplet, .fitw").forEach(function (el) { el.style.fontSize = ""; });
    // Measured from the top: in a box that centres its content, what overflows above the top is hidden and not
    // counted in scrollHeight, and the dots over the letters of the first line (the pulli) would be cut off.
    main.style.alignContent = "start";
    function tooTall() { return main.scrollHeight > main.clientHeight + 2; }
    function lines() {
      main.querySelectorAll(".couplet").forEach(function (p) {
        p.style.fontSize = "";
        var avail = p.clientWidth, widest = 0;
        for (var i = 0; i < p.children.length; i++) widest = Math.max(widest, p.children[i].scrollWidth);
        if (avail && widest > avail * 0.92) p.style.fontSize = (parseFloat(getComputedStyle(p).fontSize) * avail / widest * 0.92) + "px";
      });
      main.querySelectorAll(".fitw").forEach(function (el) {
        el.style.fontSize = "";
        var size = parseFloat(getComputedStyle(el).fontSize), n = 0;
        while (el.scrollWidth > el.clientWidth + 1 && n++ < 30) { size *= 0.94; el.style.fontSize = size + "px"; }
      });
    }
    var scale = 1, guard = 0;
    lines();
    while (tooTall() && scale > 0.4 && guard++ < 40) { scale *= 0.94; main.style.setProperty("--s", scale); lines(); }
    main.style.alignContent = "";
  }

  // ---- the couplet of the moment, from the portal ---------------------------------------------------------
  var url = body.getAttribute("data-now");
  function text(id, lines) { var el = $(id); if (el && lines) el.textContent = lines.join(" / "); }
  function show(k) {
    var main = $("kural");
    if (!main || String(k.n) === main.getAttribute("data-n")) return;
    main.classList.add("fade");
    setTimeout(function () {
      main.setAttribute("data-n", k.n);
      var ta = $("k-ta");
      ta.innerHTML = "";
      k.ta.forEach(function (line) { var s = document.createElement("span"); s.textContent = line; ta.appendChild(s); });
      text("k-hi", k.hi); text("k-en", k.en);
      if (k.local) text("k-local", k.local.lines);
      var cite = $("k-cite");
      if (cite) cite.innerHTML = '<span lang="ta"></span> · <span lang="en"></span>';
      if (cite) { cite.children[0].textContent = "குறள் " + k.n + " · " + k.chapter_ta; cite.children[1].textContent = k.chapter_en; }
      var qr = $("k-qr");
      if (qr && k.qr) { qr.src = k.qr; qr.alt = "QR code: couplet " + k.n + " on kts.cict.in"; }
      if (k.streams) streams(k.streams);
      fit();
      main.classList.remove("fade");
    }, 900);
  }
  function streams(list) {
    var cycle = $("cycle"), dots = $("dots");
    if (!cycle) return;
    cycle.innerHTML = ""; if (dots) dots.innerHTML = "";
    list.forEach(function (s, i) {
      var div = document.createElement("div");
      div.className = "stream" + (i === 0 ? " on" : ""); div.lang = s.tag; div.dir = s.dir;
      var p = document.createElement("p"); p.className = "tr fitw"; p.textContent = s.lines.join(" / ");
      var name = document.createElement("span"); name.className = "lname";
      name.textContent = s.name + (s.name !== s.en_name ? " · " + s.en_name : "");
      div.appendChild(p); div.appendChild(name); cycle.appendChild(div);
      if (dots) { var dot = document.createElement("i"); if (i === 0) dot.className = "on"; dots.appendChild(dot); }
    });
    shown = 0;
  }
  function ask(first) {
    var sent = Date.now();
    var req = new XMLHttpRequest();
    req.open("GET", url + (url.indexOf("?") < 0 ? "?" : "&") + "_=" + sent);
    req.timeout = 15000;
    req.onload = function () {
      if (req.status !== 200) return later(60000);
      try {
        var data = JSON.parse(req.responseText), back = Date.now();
        offset = data.epoch_ms - Math.round((sent + back) / 2);
        nextAt = back + data.next_ms;
        show(data.kural);
        // the next couplet: when its slot begins, plus up to 15 s, so that the screens do not all ask at once
        later(data.next_ms + 1000 + Math.floor(Math.random() * 15000));
      } catch (e) { later(60000); }
    };
    req.onerror = req.ontimeout = function () { later(60000); };
    req.send();
  }
  var timer = null;
  function later(ms) { clearTimeout(timer); timer = setTimeout(function () { ask(false); }, ms); }

  // ---- one couplet, many languages: the translations take turns -------------------------------------------
  var shown = 0, seconds = parseInt(body.getAttribute("data-lang-seconds"), 10) || 8;
  if ($("cycle")) setInterval(function () {
    var items = $("cycle").children, dots = $("dots") ? $("dots").children : [];
    if (!items.length) return;
    items[shown].classList.remove("on"); if (dots[shown]) dots[shown].classList.remove("on");
    shown = (shown + 1) % items.length;
    items[shown].classList.add("on"); if (dots[shown]) dots[shown].classList.add("on");
  }, seconds * 1000);

  // ---- the screen stays awake; a new version of the portal is taken up every six hours --------------------
  function awake() { try { if (navigator.wakeLock) navigator.wakeLock.request("screen").catch(function () {}); } catch (e) { /* not offered */ } }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) awake(); });
  awake();
  setTimeout(function () {
    var r = new XMLHttpRequest();
    r.open("GET", url); r.timeout = 15000;
    r.onload = function () { if (r.status === 200) location.reload(); };
    r.send();
  }, 6 * 3600000 + Math.floor(Math.random() * 600000));

  fit();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  window.addEventListener("resize", fit);
  tick();
  setTimeout(function () { tick(); setInterval(tick, 1000); }, 1000 - (Date.now() % 1000));
  ask(true);
})();
