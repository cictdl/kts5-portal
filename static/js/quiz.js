/* Classroom quiz of the KTS 5.0 portal: the projector (#quiz-host) and the phone (#quiz-play).
   Both ask the portal for the state of the quiz every second or two and draw it. The portal
   counts the time; a screen counts down from what the portal says remains. Text from the portal
   is always set as text, never as markup: the names come from the players. */
(function () {
  "use strict";
  var dataEl = document.getElementById("quiz-data");
  if (!dataEl) return;
  var D;
  try { D = JSON.parse(dataEl.textContent); } catch (e) { return; }
  var S = D.strings || {};
  var MSG = {};
  try { MSG = JSON.parse(document.getElementById("i18n").textContent) || {}; } catch (e) { MSG = {}; }
  var LETTERS = ["a", "b", "c", "d"];
  // the arrow of the main button points the way the page reads
  var PLAY = document.documentElement.dir === "rtl" ? "◀" : "▶";

  function s(key, vars) {
    var out = S[key] || key;
    if (vars) Object.keys(vars).forEach(function (k) { out = out.split("{" + k + "}").join(String(vars[k])); });
    return out;
  }
  function h(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else n.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(function (c) {
      if (c !== null && c !== undefined) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
  function num(n) { return Number(n || 0).toLocaleString("en-IN"); }
  function lines(list, attrs) {
    return h("div", attrs, (list || []).map(function (line) { return h("div", { text: line }); }));
  }

  // ---- the connection ---------------------------------------------------------------------
  var offlineBar = null;
  function offline(on) {
    if (on && !offlineBar) {
      offlineBar = h("div", { class: "quiz-offline", role: "status", text: MSG["js.offline"] || "Offline" });
      document.body.appendChild(offlineBar);
    } else if (!on && offlineBar) {
      offlineBar.remove();
      offlineBar = null;
    }
  }
  function poll(url, every, draw) {
    var timer = null, stopped = false, busy = false, failures = 0, again = false;
    function tick() {
      if (stopped) return;
      busy = true;
      again = false;
      fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } })
        .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then(function (st) { failures = 0; offline(false); if (draw(st) === false) stopped = true; })
        .catch(function () { failures += 1; if (failures > 1) offline(true); })
        .then(function () { busy = false; if (again) tick(); else schedule(); });
    }
    function schedule() {
      if (stopped) return;
      clearTimeout(timer);
      timer = setTimeout(tick, document.hidden ? Math.max(every, 4000) : every);
    }
    document.addEventListener("visibilitychange", function () { if (!document.hidden) soon(); });
    function soon() {
      if (stopped) return;
      if (busy) { again = true; return; }
      clearTimeout(timer);
      tick();
    }
    tick();
    return { now: soon };
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": D.csrf },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j.status = r.status; return j; });
    });
  }

  function option(tag, i, text, q, extra) {
    return h(tag, Object.assign({ class: "opt " + LETTERS[i], lang: q.tag, dir: q.dir }, extra || {}), [
      h("span", { class: "shape", "aria-hidden": "true", text: (D.shapes || [])[i] }),
      h("span", { class: "txt", text: text })
    ]);
  }
  function stemNode(node, q) {
    node.textContent = q.stem;
    node.setAttribute("lang", q.stem_tag);
    node.setAttribute("dir", q.stem_dir);
  }

  // ---- the projector ------------------------------------------------------------------------
  function host(root) {
    function bind(name) { return root.querySelector('[data-bind="' + name + '"]'); }
    var sections = Array.prototype.slice.call(root.querySelectorAll("[data-stage]"));
    var cur = null, drawn = "", shownQ = -1, shownStage = "";
    var deadline = 0, limit = 1, readyEnd = 0, nudged = "";
    var readyTotal = D.ready_ms || 5000;
    var timer = bind("timer"), secs = bind("secs"), readyFill = bind("ready").firstElementChild;

    function show(stage) {
      sections.forEach(function (sec) { sec.hidden = sec.getAttribute("data-stage").split(" ").indexOf(stage) < 0; });
      root.setAttribute("data-stage-now", stage);
      root.querySelectorAll("[data-when]").forEach(function (b) {
        b.hidden = b.getAttribute("data-when").split(" ").indexOf(stage) < 0;
      });
      document.querySelectorAll("[data-live]").forEach(function (b) { b.hidden = stage === "end"; });
    }

    function drawLobby(st) {
      bind("players").textContent = num(st.players);
      bind("waiting").hidden = st.players > 0;
      root.querySelector('[data-act="start"]').disabled = st.players === 0;
      var list = clear(bind("names"));
      (st.names || []).forEach(function (p) {
        list.appendChild(h("li", {}, [h("bdi", { text: p.name }),
          h("button", { type: "button", "data-act": "remove", "data-player": String(p.id), "data-name": p.name,
                        title: s("remove"), "aria-label": s("remove") + ": " + p.name, text: "×" })]));
      });
    }

    function drawQuestion(st) {
      var q = st.question;
      var fresh = shownQ !== st.index;
      bind("qno").textContent = s("question_of", { n: st.index + 1, total: st.total });
      bind("answered").textContent = num(st.answered);
      bind("all").textContent = num(st.players);
      if (fresh) {
        shownQ = st.index;
        stemNode(bind("stem"), q);
        var quote = bind("quote");
        clear(quote);
        quote.setAttribute("lang", q.tag);
        quote.setAttribute("dir", q.dir);
        (q.quote || []).forEach(function (line) { quote.appendChild(h("div", { text: line })); });
        var list = clear(bind("options"));
        q.options.forEach(function (text, i) {
          list.appendChild(h("li", {}, [option("div", i, text, q, {}), null]));
        });
      }
      var options = bind("options");
      options.classList.toggle("waiting-options", st.stage === "ready");
      options.classList.toggle("revealed", st.stage === "reveal");
      timer.hidden = st.stage !== "question";
      bind("ready").hidden = st.stage !== "ready";
      var panel = bind("kural");
      if (st.stage === "reveal") {
        var total = (st.counts || []).reduce(function (a, b) { return a + b; }, 0) || 1;
        Array.prototype.forEach.call(options.querySelectorAll(".opt"), function (el, i) {
          var right = i === st.answer;
          el.classList.toggle("right", right);
          el.querySelectorAll(".count, .fill, .tick").forEach(function (x) { x.remove(); });
          if (right) el.appendChild(h("span", { class: "tick", "aria-hidden": "true", text: "✓" }));
          el.appendChild(h("span", { class: "count", dir: "ltr", text: num(st.counts[i]) }));
          var fill = h("span", { class: "fill" });
          el.appendChild(fill);
          requestAnimationFrame(function () { fill.style.width = Math.round(100 * st.counts[i] / total) + "%"; });
        });
        clear(panel);
        if (st.kural) {
          var k = st.kural;
          panel.appendChild(h("div", { class: "kn", text: s("kural", { n: k.n }) + " · " + k.chapter }));
          panel.appendChild(lines(k.ta, { class: "ta-lines", lang: "ta" }));
          if (k.tr && k.tr.length) panel.appendChild(lines(k.tr, { class: "tr-lines", lang: q.tag, dir: q.dir }));
          panel.hidden = false;
        } else {
          panel.hidden = true;
        }
        var label = st.last ? s("final") : s("next");
        bind("next1").textContent = label;
      } else {
        panel.hidden = true;
      }
    }

    function boardRow(r, gain) {
      return h("li", {}, [h("bdi", { class: "who", text: r.name }),
        gain ? h("span", { class: "gain", dir: "ltr", text: r.gained ? "+" + num(r.gained) : "" }) : h("span", {}),
        h("span", { class: "pts", dir: "ltr", text: num(r.score) })]);
    }
    function drawBoard(st) {
      bind("qno2").textContent = s("question_of", { n: st.index + 1, total: st.total });
      var list = clear(bind("board"));
      (st.board || []).forEach(function (r) { list.appendChild(boardRow(r, true)); });
      bind("next2").textContent = (st.last ? s("final") : s("next")) + " " + PLAY;
    }
    function drawEnd(st) {
      var podium = clear(bind("podium"));
      var rows = st.board || [];
      [[1, "second"], [0, "first"], [2, "third"]].forEach(function (p) {
        var r = rows[p[0]];
        if (!r) return;
        podium.appendChild(h("div", { class: "qz-step " + p[1] }, [
          h("bdi", { class: "who", text: r.name }), h("div", { class: "pts", dir: "ltr", text: num(r.score) }),
          h("div", { class: "block", text: String(p[0] + 1) })]));
      });
      var rest = clear(bind("rest"));
      rows.slice(3).forEach(function (r) { rest.appendChild(boardRow(r, false)); });
    }

    function draw(st) {
      cur = st;
      var now = performance.now();
      if (st.stage === "question") { deadline = now + st.remaining_ms; limit = st.limit_ms || 1; }
      if (st.stage === "ready") readyEnd = now + st.ready_ms;
      var key = JSON.stringify([st.stage, st.index, st.players, st.answered, st.names, st.counts, st.board]);
      if (key === drawn) return;
      drawn = key;
      if (st.stage !== shownStage) { shownStage = st.stage; show(st.stage); }
      if (st.stage === "lobby") drawLobby(st);
      else if (st.stage === "ready" || st.stage === "question" || st.stage === "reveal") drawQuestion(st);
      else if (st.stage === "board") drawBoard(st);
      else if (st.stage === "end") { drawEnd(st); return false; }
    }

    var link = poll(D.state, 1000, draw);

    (function frame() {
      var now = performance.now();
      if (cur && cur.stage === "question") {
        var left = Math.max(0, deadline - now);
        secs.textContent = String(Math.ceil(left / 1000));
        timer.style.setProperty("--p", (left / limit).toFixed(3));
        timer.classList.toggle("low", left < 5000);
        if (left <= 0 && nudged !== "q" + cur.index) { nudged = "q" + cur.index; link.now(); }
      } else if (cur && cur.stage === "ready") {
        var wait = Math.max(0, readyEnd - now);
        readyFill.style.width = (100 * (1 - wait / readyTotal)).toFixed(1) + "%";
        if (wait <= 0 && nudged !== "r" + cur.index) { nudged = "r" + cur.index; link.now(); }
      }
      requestAnimationFrame(frame);
    })();

    function act(button) {
      var name = button.getAttribute("data-act");
      var ask = button.getAttribute("data-ask");
      if (name === "remove") ask = s("remove") + ": " + button.getAttribute("data-name") + "?";
      if (ask && !window.confirm(ask)) return;
      var body = { action: name, index: cur ? cur.index : null };
      if (name === "remove") body.player = Number(button.getAttribute("data-player"));
      button.disabled = true;
      post(D.action, body).then(function () { button.disabled = false; link.now(); },
                                function () { button.disabled = false; });
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-act]") : null;
      if (b && !b.disabled) act(b);
      var full = e.target.closest ? e.target.closest("[data-full]") : null;
      if (full) {
        if (document.fullscreenElement) document.exitFullscreen();
        else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
      }
    });
    // a presenter's clicker sends Page Down or an arrow: the main button of the screen
    document.addEventListener("keydown", function (e) {
      if (["PageDown", "ArrowRight", "Enter", " "].indexOf(e.key) < 0) return;
      if (e.target && /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(e.target.tagName)) return;
      var b = root.querySelector("section:not([hidden]) [data-primary]:not([hidden]):not(:disabled)");
      if (b) { e.preventDefault(); act(b); }
    });
  }

  // ---- the phone -----------------------------------------------------------------------------
  function play(root) {
    var screen = root.querySelector("#qp-screen");
    var meScore = document.getElementById("me-score");
    var cur = null, drawn = "", sent = null, deadline = 0, limit = 1, nudged = "", problem = "";
    var timeBar = null;

    function card(cls, kids) { return h("div", { class: "quiz-card " + (cls || "") }, kids); }
    function place(st) {
      return h("p", { class: "place" }, [s("your_rank", { rank: st.rank, total: st.players })]);
    }
    function questionView(st) {
      var q = st.question;
      var chosen = st.answered !== null && st.answered !== undefined ? st.answered
        : (sent && sent.index === st.index ? sent.choice : null);
      timeBar = h("div", { class: "time" }, [h("span")]);
      var list = h("div", { class: "options" });
      q.options.forEach(function (text, i) {
        var b = option("button", i, text, q, { type: "button", "data-i": String(i), disabled: chosen !== null });
        if (chosen !== null) b.classList.add(i === chosen ? "chosen" : "faded");
        b.addEventListener("click", function () { choose(st, i); });
        list.appendChild(b);
      });
      var stem = h("p", { class: "stem" });
      stemNode(stem, q);
      var kids = [h("p", { class: "qno", text: s("question_of", { n: st.index + 1, total: st.total }) }), timeBar, stem];
      if (q.quote && q.quote.length) kids.push(lines(q.quote, { class: "quote", lang: q.tag, dir: q.dir }));
      kids.push(list);
      if (chosen !== null) kids.push(h("p", { class: "note", text: s("sent") }));
      if (problem) kids.push(h("p", { class: "note", text: problem }));
      return card("", kids);
    }
    function choose(st, i) {
      if (sent && sent.index === st.index) return;
      sent = { index: st.index, choice: i };
      problem = "";
      redraw();
      post(D.answer, { q: st.index, choice: i }).then(function (j) {
        if (j.ok || j.reason === "twice") return;
        if (j.reason === "late") problem = s("too_late");
        else sent = null;
        redraw();
      }, function () {
        // no connection: the answer may be given again
        sent = null;
        problem = MSG["js.offline"] || "";
        redraw();
      });
    }
    function resultView(st) {
      var r = st.result;
      var kind = !r.answered ? "none" : (r.correct ? "right" : "wrong");
      var kids = [
        h("div", { class: "big", "aria-hidden": "true", text: kind === "right" ? "✅" : (kind === "wrong" ? "❌" : "⏱") }),
        h("h2", { text: kind === "right" ? s("correct") : (kind === "wrong" ? s("wrong") : s("no_answer")) })
      ];
      if (kind === "right") kids.push(h("div", { class: "gained", dir: "ltr", text: "+" + num(r.points) + " " }, [h("small", { text: s("points") })]));
      kids.push(h("div", { class: "answer" }, [h("div", { class: "small dim", text: s("answer_was") }),
        option("div", r.answer_index, r.answer, r, {})]));
      kids.push(place(st));
      kids.push(h("p", { class: "small dim", text: s("look_screen") }));
      return card("result " + kind, kids);
    }
    function endView(st) {
      var top = h("ol", { class: "top" });
      (st.top || []).forEach(function (r, i) {
        top.appendChild(h("li", {}, [h("span", {}, [String(i + 1) + ". ", h("bdi", { text: r.name })]),
          h("span", { dir: "ltr", text: num(r.score) })]));
      });
      return card("", [h("div", { class: "big", "aria-hidden": "true", text: "🏆" }), h("h2", { text: s("final") }), place(st),
        top, h("p", { class: "dim", text: s("thanks") }),
        h("a", { class: "btn secondary", href: D.join, text: s("join_another") })]);
    }
    function messageView(icon, text) {
      return card("", [h("div", { class: "big", "aria-hidden": "true", text: icon }), h("h2", { text: text }),
        h("a", { class: "btn secondary", href: D.join, text: s("join_another") })]);
    }
    function redraw() { drawn = ""; if (cur) draw(cur); }

    function draw(st) {
      cur = st;
      var now = performance.now();
      if (st.stage === "question") { deadline = now + st.remaining_ms; limit = st.limit_ms || 1; }
      if (st.me) meScore.textContent = num(st.me.score);
      var key = JSON.stringify([st.stage, st.index, st.answered, st.result, st.rank, st.players, sent, problem]);
      if (key === drawn) return st.stage === "end" || st.stage === "removed" || st.stage === "gone" ? false : undefined;
      drawn = key;
      if (st.stage !== "question") { timeBar = null; problem = st.stage === "ready" ? "" : problem; }
      var view;
      switch (st.stage) {
        case "lobby":
          view = card("", [h("div", { class: "big", "aria-hidden": "true", text: "✅" }), h("h2", { text: s("you_are_in") }),
            h("p", {}, [h("bdi", { class: "me-chip", text: st.me.name })]), h("p", { class: "dim", text: s("see_name") })]);
          break;
        case "ready":
          view = card("", [h("p", { class: "qno", text: s("question_of", { n: st.index + 1, total: st.total }) }),
            h("div", { class: "big", "aria-hidden": "true", text: "⏳" }), h("h2", { text: s("get_ready") })]);
          break;
        case "question": view = questionView(st); break;
        case "reveal": case "board": view = resultView(st); break;
        case "end": view = endView(st); break;
        case "removed": view = messageView("🚫", s("removed")); break;
        default: window.location.href = D.join; return false;
      }
      clear(screen).appendChild(view);
      if (st.stage === "end" || st.stage === "removed") return false;
    }

    var link = poll(D.state, 1500, draw);

    (function frame() {
      if (cur && cur.stage === "question") {
        var left = Math.max(0, deadline - performance.now());
        if (timeBar) {
          timeBar.firstElementChild.style.width = (100 * left / limit).toFixed(1) + "%";
          timeBar.classList.toggle("low", left < 5000);
        }
        if (left <= 0 && nudged !== "q" + cur.index) { nudged = "q" + cur.index; link.now(); }
      } else if (cur && cur.stage === "ready" && nudged !== "r" + cur.index) {
        // the options appear when the portal says so; ask again as the wait ends
        nudged = "r" + cur.index;
        setTimeout(link.now, Math.max(0, cur.ready_ms));
      }
      requestAnimationFrame(frame);
    })();
  }

  var hostRoot = document.getElementById("quiz-host");
  var playRoot = document.getElementById("quiz-play");
  if (D.mode === "host" && hostRoot) host(hostRoot);
  if (D.mode === "play" && playRoot) play(playRoot);
})();
