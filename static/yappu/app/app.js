/* யாப்புக் கலம் — இடைமுகம் */
(function () {
  'use strict';
  var Y = window.Yappu;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem('yk.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem('yk.' + k, JSON.stringify(v)); } catch (e) { } }
  };
  var ORD = function (n) { return n + 'ஆம்'; };

  /* ---------- மாதிரிப் பாடல்கள் ---------- */
  var SAMPLES = (window.SAMPLES || []).length ? window.SAMPLES : [];

  /* ---------- தாவல்கள் ---------- */
  var views = ['analyze', 'learn', 'ref', 'compose', 'quiz', 'game', 'faq'];
  function show(v) {
    if (views.indexOf(v) < 0) v = 'analyze';
    views.forEach(function (x) {
      $('#v-' + x).hidden = x !== v;
      $('#t-' + x).setAttribute('aria-selected', x === v ? 'true' : 'false');
    });
    store.set('view', v);
    if (v === 'quiz' && !quiz.cur) nextQ();
  }
  document.querySelectorAll('.tab').forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.view); });
  });

  /* ---------- அலகிடு ---------- */
  var verse = $('#verse'), sampleSel = $('#sample');
  var groups = {};
  SAMPLES.forEach(function (s, i) {
    var parent = sampleSel;
    if (s.g) {
      if (!groups[s.g]) { groups[s.g] = document.createElement('optgroup'); groups[s.g].label = s.g; sampleSel.appendChild(groups[s.g]); }
      parent = groups[s.g];
    }
    var o = document.createElement('option'); o.value = i; o.textContent = s.label; parent.appendChild(o);
  });
  var custom = document.createElement('option'); custom.value = ''; custom.textContent = 'என் பாடல்'; sampleSel.appendChild(custom);
  sampleSel.addEventListener('change', function () {
    if (sampleSel.value === '') return;
    verse.value = SAMPLES[+sampleSel.value].text; runAnalyze();
  });
  $('#clear').addEventListener('click', function () { verse.value = ''; sampleSel.value = ''; runAnalyze(); verse.focus(); });
  var t;
  verse.addEventListener('input', function () {
    sampleSel.value = '';
    clearTimeout(t); t = setTimeout(runAnalyze, 120);
  });

  function sirDisplayName(s) { return s.venbaEnd || s.name; }

  function renderSir(s, li, si, flagged) {
    var asais = s.asai.map(function (a) {
      return '<span class="asai ' + (a.kind === Y.NER ? 'ner' : 'nirai') + '">' + esc(a.text) + '</span>';
    }).join('');
    var kinds = s.asai.map(function (a) {
      return '<span class="' + (a.kind === Y.NER ? 'ner' : 'nirai') + '" style="background:none">' + a.kind + '</span>';
    }).join('');
    return '<button class="sir' + (flagged ? ' flag' : '') + '" data-l="' + li + '" data-s="' + si + '" style="background:' + (flagged ? '' : 'none') + ';cursor:pointer;font:inherit;color:inherit" aria-label="' + esc(s.word) + ' விவரம்">' +
      '<span class="asais">' + asais + '</span><span class="kinds">' + kinds + '</span>' +
      '<span class="vp">' + esc(sirDisplayName(s)) + '</span></button>';
  }

  function renderLink(s) {
    if (!s.next) return '';
    var f = s.next.fam;
    return '<span class="link" title="' + esc(s.next.name + ' — ' + s.next.rule) + '"><span class="bar bg-' + f + '"></span><span class="tl fam-' + f + '">' + shortThalai(s.next) + '</span></span>';
  }
  function shortThalai(t) {
    return ({ 'நேரொன்றாசிரியத்தளை': 'நேரொன்று', 'நிரையொன்றாசிரியத்தளை': 'நிரையொன்று', 'இயற்சீர் வெண்டளை': 'இயற்சீர்', 'வெண்சீர் வெண்டளை': 'வெண்சீர்', 'கலித்தளை': 'கலி', 'ஒன்றிய வஞ்சித்தளை': 'ஒன்றிய', 'ஒன்றாத வஞ்சித்தளை': 'ஒன்றாத' })[t.name];
  }

  var lastResult = null;
  function runAnalyze() {
    var r = Y.analyze(verse.value);
    lastResult = r;
    store.set('verse', verse.value);
    var V = $('#verdict'), S = $('#summary'), L = $('#lines');
    $('#detail').hidden = true;
    if (!r.lines.length) {
      V.innerHTML = '<div class="verdict"><span class="eyebrow">பா</span><span class="pa muted">பாடலை இடுக</span><span class="muted">இடப்பக்கத்தில் ஒரு பாடலைத் தட்டச்சு செய்யுங்கள், அல்லது மாதிரிப் பாடல் ஒன்றைத் தேர்ந்தெடுங்கள்.</span></div>';
      S.innerHTML = ''; L.innerHTML = ''; return;
    }
    var pa = r.pa, flagged = {};
    (pa.issues || []).forEach(function (i) { if (i.pos != null && !i.soft) flagged[i.line + ':' + i.pos] = 1; });
    var hard = (pa.issues || []).filter(function (i) { return !i.soft; });
    var cls = pa.family ? (pa.ok ? 'ok' : 'bad') : 'bad';
    var h = '<div class="verdict ' + cls + '"><span class="eyebrow">' + esc(pa.family || 'பா') + '</span>' +
      '<span class="pa">' + esc(pa.name) + '</span>';
    if (pa.pattern) h += '<span class="pat muted">' + esc(pa.pattern) + '</span>';
    if (pa.family) h += '<span class="status ' + (pa.ok ? 'ok' : 'bad') + '">' + (pa.ok ? 'இலக்கணம் பிழையின்றி அமைந்துள்ளது' : hard.length + ' இடத்தில் இலக்கணம் பிறழ்கிறது') + '</span>';
    if (pa.issues && pa.issues.length) {
      h += '<ul class="issues">' + pa.issues.map(function (i) { return '<li class="' + (i.info ? 'info' : i.soft ? 'soft' : '') + '">' + esc(i.msg) + '</li>'; }).join('') + '</ul>';
    }
    if (pa.candidates && pa.candidates.length) {
      h += '<span class="alt">பிற வாய்ப்புகள்: ' + pa.candidates.map(function (c) {
        var n = c.issues.filter(function (i) { return !i.soft; }).length;
        return esc(c.name) + (n ? ' (' + n + ' பிழை)' : '');
      }).join(' · ') + '</span>';
    }
    V.innerHTML = h + '</div>';

    // தளைச் சுருக்கம்
    var st = r.stats, famNames = { 'வெண்மை': 'வெண்டளை', 'ஆசிரியம்': 'ஆசிரியத்தளை', 'கலி': 'கலித்தளை', 'வஞ்சி': 'வஞ்சித்தளை' };
    var nSir = r.flat.length;
    var sh = '<div class="summary-grid">';
    Object.keys(famNames).forEach(function (f) {
      var c = st.fam[f], pct = st.total ? Math.round(c * 100 / st.total) : 0;
      sh += '<div class="meter"><span><b class="fam-' + f + '">' + famNames[f] + '</b> <span class="muted" style="font-variant-numeric:tabular-nums">' + c + '/' + st.total + '</span></span><span class="track"><span class="fill bg-' + f + '" style="display:block;width:' + pct + '%"></span></span></div>';
    });
    sh += '</div>';
    var eth = r.adiEthukai.length ? r.adiEthukai.map(function (e, i) { return ORD(i + 2) + ' அடி: ' + (e === 'நேர்' ? '✓' : e === 'இனம்' ? 'இன எதுகை' : e === 'அளவு மாறியது' ? 'முதலெழுத்தளவு மாறுகிறது' : '✗'); }).join(' · ') : '';
    sh += '<p class="hint" style="margin-top:10px">' + r.lines.length + ' அடி · ' + nSir + ' சீர்' + (eth ? ' · அடியெதுகை (முதலடியுடன்) — ' + eth : '') + '</p>';
    S.innerHTML = sh;

    L.innerHTML = r.lines.map(function (l, li) {
      var inner = l.sirs.map(function (s, si) {
        return renderSir(s, li, si, flagged[li + ':' + si]) + (si < l.sirs.length - 1 ? renderLink(s) : '');
      }).join('');
      var cross = l.sirs[l.sirs.length - 1].next;
      var foot = [];
      if (l.monai) foot.push('<span><b>மோனை</b> ' + (l.monai.name ? l.monai.name + ' (' + l.monai.positions.join(', ') + ')' : l.monai.positions.join(', ')) + '</span>');
      if (l.ethukai) foot.push('<span><b>சீர் எதுகை</b> ' + (l.ethukai.name || '') + ' (' + l.ethukai.positions.join(', ') + ')</span>');
      if (cross) foot.push('<span><b>அடுத்த அடியுடன்</b> <span class="fam-' + cross.fam + '">' + cross.name + '</span></span>');
      return '<div class="line"><div class="line-head"><span><b>' + ORD(li + 1) + ' அடி</b> · ' + l.sirs.length + ' சீர் · ' + Y.adiName(l.sirs.length) + '</span><span style="font-variant-numeric:tabular-nums">ஒற்று நீக்கி ' + l.count + ' எழுத்து</span></div>' +
        '<div class="sirs">' + inner + '</div>' + (foot.length ? '<div class="line-foot">' + foot.join('') + '</div>' : '') + '</div>';
    }).join('');
  }

  $('#lines').addEventListener('click', function (e) {
    var b = e.target.closest('.sir'); if (!b || !lastResult) return;
    var l = lastResult.lines[+b.dataset.l], s = l.sirs[+b.dataset.s];
    var D = $('#detail');
    var letters = s.letters.map(function (x) {
      return '<span class="letter ' + x.type + (x.dropped ? ' dropped' : '') + (x.gained ? ' gained' : '') + '" title="' + (x.dropped || x.gained ? x.note : ({ K: 'குறில்', N: 'நெடில்', O: 'ஒற்று' })[x.type] + (x.note ? ' — ' + x.note : '')) + '">' + esc(x.text) + '</span>';
    }).join('');
    var rows = s.asai.map(function (a) {
      var desc = a.letters.map(function (x) {
        return x.dropped ? Y.ALT[x.alt].name + ' (அலகு இல்லை)' : x.gained ? Y.ALT[x.alt].name + ' (ஓரலகு)' : ({ K: 'குறில்', N: 'நெடில்', O: 'ஒற்று' })[x.type];
      }).join(' + ');
      return '<tr><td class="letter" style="font-size:18px">' + esc(a.text) + '</td><td>' + desc + '</td><td><span class="chip ' + (a.kind === Y.NER ? 'ner' : 'nirai') + '">' + a.kind + '</span></td></tr>';
    }).join('');
    var nx = s.next ? '<p style="margin:10px 0 0"><b>அடுத்த சீருடன் தளை:</b> <span class="fam-' + s.next.fam + '">' + s.next.name + '</span> <span class="muted">(' + s.next.rule + ')</span></p>' : '';
    var ku = (s.letters.some(function (x) { return x.note === 'ஐகாரக் குறுக்கம்'; }) ? '<p class="hint" style="margin-top:6px">சொல்லின் இடையிலும் இறுதியிலும் வரும் ஐகாரம் குறுகி ஒரு மாத்திரை ஒலிப்பதால் (ஐகாரக் குறுக்கம்) அசை பிரிப்பில் குறிலாகக் கொள்ளப்படுகிறது.</p>' : '') +
      s.altKinds.map(function (k) {
        var A = Y.ALT[k];
        var verdict = s.altApplied
          ? (A.lose ? 'இயல்பான அலகீட்டில் இப்பாடலின் சீரும் தளையும் கெடுவதால், இங்கே அதற்கு அலகு நீக்கப்பட்டுள்ளது.' : 'அலகு கொடாவிட்டால் இப்பாடலின் சீரும் தளையும் கெடுவதால், இங்கே அது ஓரலகாகக் கொள்ளப்பட்டுள்ளது.')
          : (A.lose ? 'இங்கே அலகு கொடுத்தே ஓசை சரியாக அமைவதால் அலகு நீக்கப்படவில்லை.' : 'இங்கே அலகு கொடாமலே ஓசை சரியாக அமைவதால் ஒற்றாகவே கொள்ளப்பட்டுள்ளது.');
        return '<p class="hint" style="margin-top:6px"><b>' + A.name + '.</b> ' + A.why + ' ' + verdict + '</p>';
      }).join('');
    var ve = s.venbaEnd && (s.venbaEnd === 'காசு' || s.venbaEnd === 'பிறப்பு') ? '<p class="hint" style="margin-top:6px">இறுதி உகரம் ' + (s.mutru ? 'முற்றியலுகரம் (சிறுபான்மை வழக்கு)' : 'குற்றியலுகரம்') + '; வெண்பாவின் ஈற்றில் இது ' + s.venbaEnd + ' வாய்பாடு (' + (s.venbaEnd === 'காசு' ? 'நேர்பு' : 'நிரைபு') + ').</p>' : '';
    D.innerHTML = '<div class="row" style="justify-content:space-between"><h3 style="font-size:24px">' + esc(s.word) + '</h3><button class="btn" id="dclose">மூடு</button></div>' +
      '<p style="margin:6px 0">' + letters + '</p><div class="tablebox"><table><tr><th>அசை</th><th>அமைப்பு</th><th>வகை</th></tr>' + rows + '</table></div>' +
      '<p style="margin:10px 0 0"><b>வாய்பாடு:</b> <span style="font-family:var(--display);font-size:18px">' + esc(sirDisplayName(s)) + '</span> · <span class="muted">' + esc(s.klass) + '</span></p>' + nx + ku + ve;
    D.hidden = false;
    $('#dclose').addEventListener('click', function () { D.hidden = true; });
    D.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });

  window.tryVerse = function (text) {
    verse.value = text; sampleSel.value = ''; runAnalyze(); show('analyze'); window.scrollTo({ top: 0 });
  };

  /* ---------- பாடங்கள் ---------- */
  var LESSONS = window.LESSONS || [];
  var CHECKS = window.LESSON_CHECKS || {};

  /* ---------- பாட முன்னேற்றம் ---------- */
  // உலாவியில் உடனே; கிடைத்தால் db-இல் பயனரின் தனிப்பகுதியிலும் (data/users/<id>/progress) — வேறு சாதனத்திலும் தொடர
  var prog = { done: store.get('progress', {}), db: null, uid: null };
  function progSave() {
    store.set('progress', prog.done);
    if (prog.db && prog.uid) prog.db.doc('data/users/' + prog.uid + '/progress').set({ done: prog.done }).catch(function () { prog.db = null; });
  }
  function progCount() { return LESSONS.filter(function (l) { return prog.done[l.id]; }).length; }
  if (window.claude && typeof window.claude.use === 'function') {
    Promise.all([window.claude.use('db'), window.claude.use('user')]).then(function (r) {
      if (!r[0] || !r[1]) return;
      r[1].id().then(function (uid) {
        if (!uid) return;
        prog.db = r[0]; prog.uid = uid;
        prog.db.doc('data/users/' + uid + '/progress').get().then(function (snap) {
          var remote = (snap.exists && snap.data().done) || {};
          Object.keys(remote).forEach(function (k) { if (!prog.done[k]) prog.done[k] = remote[k]; });
          store.set('progress', prog.done);
          var cur = store.get('lesson', null); renderToc(cur);
          var chk = $('#lcheck'); if (chk && cur) renderCheck(cur);
        }, function () { prog.db = null; });
      });
    });
  }

  function renderToc(cur) {
    var parts = [], n = progCount(), total = LESSONS.length;
    LESSONS.forEach(function (l) { if (parts.indexOf(l.part) < 0) parts.push(l.part); });
    $('#toc').innerHTML = '<div class="prog"><div class="prog-top"><b>' + n + ' / ' + total + '</b> பாடங்கள் முடிந்தன</div>' +
      '<div class="prog-track"><span style="width:' + Math.round(n * 100 / total) + '%"></span></div></div>' +
      parts.map(function (p) {
        return '<div><h4>' + esc(p) + '</h4>' + LESSONS.filter(function (l) { return l.part === p; }).map(function (l) {
          return '<button data-id="' + l.id + '" aria-current="' + (l.id === cur ? 'true' : 'false') + '" class="' + (prog.done[l.id] ? 'done' : '') + '">' +
            '<span class="tick" aria-hidden="true">' + (prog.done[l.id] ? '✓' : '') + '</span>' + esc(l.title) + (prog.done[l.id] ? '<span class="sr"> (முடிந்தது)</span>' : '') + '</button>';
        }).join('') + '</div>';
      }).join('');
  }

  // பாடச் சோதனை: மூன்று வினாக்கள்; எல்லாம் சரியானால் பாடம் முடிந்தது
  function renderCheck(id) {
    var qs = CHECKS[id], box = $('#lcheck');
    if (!box) return;
    if (!qs) { box.hidden = true; return; }
    box.hidden = false;
    var done = !!prog.done[id];
    var order = qs.map(function (q) { return shuffle(q.o.slice()); });
    box.innerHTML = '<div class="row" style="justify-content:space-between;gap:8px"><h3 style="margin:0">பாடச் சோதனை</h3>' +
      (done ? '<span class="chip lc-done">✓ முடித்த பாடம்</span>' : '<span class="hint" style="margin:0">மூன்றும் சரியானால் பாடம் முடியும்</span>') + '</div>' +
      qs.map(function (q, qi) {
        return '<fieldset class="lc-q" data-qi="' + qi + '"><legend>' + (qi + 1) + '. ' + esc(q.q) + '</legend>' +
          order[qi].map(function (o, oi) {
            var id2 = 'lc-' + id + '-' + qi + '-' + oi;
            return '<label class="lc-o" for="' + id2 + '"><input type="radio" name="lc-' + qi + '" id="' + id2 + '" value="' + esc(o) + '"><span></span></label>';
          }).join('') + '<p class="lc-exp" hidden></p></fieldset>';
      }).join('') +
      '<div class="row" style="gap:8px;margin-top:6px"><button class="btn primary" id="lcSubmit">சரிபார்</button><span class="lc-msg" id="lcMsg" role="status"></span></div>';
    // விடைகளை textContent ஆக இட
    box.querySelectorAll('.lc-q').forEach(function (fs) {
      var qi = +fs.dataset.qi;
      fs.querySelectorAll('.lc-o span').forEach(function (sp, oi) { sp.textContent = order[qi][oi]; });
    });
    $('#lcSubmit').addEventListener('click', function () {
      var right = 0, answered = 0;
      box.querySelectorAll('.lc-q').forEach(function (fs) {
        var q = qs[+fs.dataset.qi], sel = fs.querySelector('input:checked'), exp = fs.querySelector('.lc-exp');
        fs.classList.remove('ok', 'no');
        if (!sel) return;
        answered++;
        var ok = sel.value === q.o[0];
        if (ok) right++;
        fs.classList.add(ok ? 'ok' : 'no');
        exp.hidden = false;
        exp.textContent = (ok ? '✓ சரி. ' : '✗ விடை: ' + q.o[0] + '. ') + (q.e || '');
      });
      var msg = $('#lcMsg'), fx = FX();
      if (answered < qs.length) { msg.textContent = 'எல்லா வினாக்களுக்கும் விடை தேர்ந்தெடுங்கள்.'; msg.className = 'lc-msg bad'; return; }
      if (right === qs.length) {
        var first = !prog.done[id];
        prog.done[id] = Date.now(); progSave();
        renderToc(id);
        var nidx = LESSONS.findIndex(function (l) { return l.id === id; }) + 1, nx = LESSONS[nidx];
        msg.innerHTML = '<b>பாடம் முடிந்தது!</b> ' + progCount() + ' / ' + LESSONS.length + (nx ? ' <button class="btn" data-go="' + nx.id + '">அடுத்த பாடம் →</button>' : '');
        msg.className = 'lc-msg ok';
        if (fx) {
          fx.sfx('win');
          if (first) fx.confetti(200, progCount() === LESSONS.length, Y.letters(LESSONS[nidx - 1].title).filter(function (L) { return L.type !== 'O'; }).map(function (L) { return L.text; }).slice(0, 3));
        }
      } else {
        msg.textContent = right + ' / ' + qs.length + ' சரி. விளக்கங்களைப் படித்து மீண்டும் முயலுங்கள்.';
        msg.className = 'lc-msg bad';
        if (fx) fx.sfx('miss');
        var again = document.createElement('button'); again.className = 'btn'; again.textContent = 'மீண்டும் முயல்க'; again.style.marginLeft = '8px';
        again.addEventListener('click', function () { renderCheck(id); });
        msg.appendChild(again);
      }
    });
  }
  function openLesson(id) {
    var i = LESSONS.findIndex(function (l) { return l.id === id; });
    if (i < 0) i = 0;
    var l = LESSONS[i];
    if (!l) return;
    store.set('lesson', l.id);
    renderToc(l.id);
    var prev = LESSONS[i - 1], next = LESSONS[i + 1];
    $('#lesson').innerHTML = '<div class="eyebrow">' + esc(l.part) + '</div><h2>' + esc(l.title) + '</h2>' + (l.lede ? '<p class="lede">' + l.lede + '</p>' : '') + l.html +
      '<section class="lcheck" id="lcheck" aria-label="பாடச் சோதனை"></section>' +
      '<div class="lesson-nav">' + (prev ? '<button class="btn" data-go="' + prev.id + '">← ' + esc(prev.title) + '</button>' : '<span></span>') +
      (next ? '<button class="btn primary" data-go="' + next.id + '">' + esc(next.title) + ' →</button>' : '') + '</div>';
    wireVerses($('#lesson'));
    renderCheck(l.id);
  }
  function wireVerses(root) {
    root.querySelectorAll('.verse').forEach(function (v) {
      if (v.dataset.notry != null) return;
      var text = (v.dataset.text || v.childNodes[0].textContent).trim();
      var b = document.createElement('button');
      b.className = 'btn try'; b.textContent = 'அலகிட்டுப் பார்';
      b.addEventListener('click', function () { tryVerse(text); });
      v.appendChild(document.createElement('br')); v.appendChild(b);
    });
  }
  window.openLessonById = function (id) { openLesson(id); show('learn'); window.scrollTo({ top: 0 }); };
  $('#toc').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-id]'); if (!b) return;
    openLesson(b.dataset.id); $('#lesson').scrollIntoView({ block: 'start' });
  });
  $('#lesson').addEventListener('click', function (e) {
    var b = e.target.closest('[data-go]'); if (!b) return;
    openLesson(b.dataset.go); window.scrollTo({ top: 0 });
  });

  /* ---------- அட்டவணைகள் ---------- */
  function buildRef() {
    var N = Y.NER, R = Y.NIRAI;
    var seqs = [];
    [[N], [R]].forEach(function (s) { seqs.push(s); });
    function ext(list) { var o = []; list.forEach(function (s) { o.push(s.concat([N])); o.push(s.concat([R])); }); return o; }
    var two = [[N, N], [R, N], [R, R], [N, R]];
    var three = []; two.forEach(function (s) { three.push(s.concat([N])); }); two.forEach(function (s) { three.push(s.concat([R])); });
    var four = []; three.slice(0, 4).forEach(function (s) { [[N, N], [N, R], [R, N], [R, R]].forEach(function (t) { four.push(s.slice(0, 2).concat(t)); }); });
    function tbl(rows, extra) {
      return '<table class="vtable"><tr><th>அசை</th><th>வாய்பாடு</th>' + (extra ? '<th>' + extra + '</th>' : '') + '</tr>' + rows.map(function (s) {
        return '<tr><td>' + s.map(function (k) { return '<span class="' + (k === N ? 'ner' : 'nirai') + '" style="background:none;font-weight:600">' + k + '</span>'; }).join(' ') + '</td><td class="nm">' + Y.vaaypaadu(s) + '</td>' + (extra ? '<td class="muted">' + (s[s.length - 1] === N ? 'காய்' : 'கனி') + '</td>' : '') + '</tr>';
      }).join('') + '</table>';
    }
    var html = '';
    html += '<div class="panel"><h3>எழுத்தும் அசையும்</h3><table class="vtable">' +
      '<tr><th>எழுத்து</th><th>எடுத்துக்காட்டு</th><th>மாத்திரை</th></tr>' +
      '<tr><td>குறில்</td><td class="nm">அ இ உ எ ஒ · க கி கு கெ கொ</td><td>1</td></tr>' +
      '<tr><td>நெடில்</td><td class="nm">ஆ ஈ ஊ ஏ ஐ ஓ ஔ · கா கீ கூ கே கை கோ</td><td>2</td></tr>' +
      '<tr><td>ஒற்று</td><td class="nm">க் ங் ச் … ன் · ஃ</td><td>½</td></tr></table>' +
      '<table class="vtable" style="margin-top:14px"><tr><th>அசை</th><th>அமைப்பு</th><th>எ.கா.</th></tr>' +
      '<tr><td rowspan="4"><span class="chip ner">நேர்</span></td><td>குறில்</td><td class="nm">க</td></tr><tr><td>குறில் + ஒற்று</td><td class="nm">கல்</td></tr><tr><td>நெடில்</td><td class="nm">கா</td></tr><tr><td>நெடில் + ஒற்று</td><td class="nm">கால்</td></tr>' +
      '<tr><td rowspan="4"><span class="chip nirai">நிரை</span></td><td>குறில் + குறில்</td><td class="nm">பல</td></tr><tr><td>குறில் + குறில் + ஒற்று</td><td class="nm">பலம்</td></tr><tr><td>குறில் + நெடில்</td><td class="nm">பலா</td></tr><tr><td>குறில் + நெடில் + ஒற்று</td><td class="nm">பலாம்</td></tr></table>' +
      '<p class="hint" style="margin-top:10px">நெடில் தனியே நின்றே நேரசை ஆகும்; அதனுடன் எழுத்துச் சேர்ந்து நிரை ஆகாது. குறிலுக்குப் பின் உயிர் எழுத்து (குறிலோ நெடிலோ) வந்தால்தான் நிரை.</p></div>';

    html += '<div class="panel"><h3>ஓரசை, ஈரசைச் சீர்கள்</h3>' + tbl([[N], [R]]) +
      '<p class="hint" style="margin:8px 0 10px">வெண்பா ஈற்றில் மட்டும்: நேர்பு = <b>காசு</b>, நிரைபு = <b>பிறப்பு</b> (குற்றியலுகரம் ஈறு).</p>' + tbl(two) +
      '<p class="hint" style="margin-top:8px">ஈரசைச் சீர்கள் இயற்சீர் அல்லது ஆசிரிய உரிச்சீர். நேரில் முடிபவை “மா”, நிரையில் முடிபவை “விளம்”.</p></div>';

    html += '<div class="panel"><h3>மூவசைச் சீர்கள்</h3>' + tbl(three, 'இனம்') +
      '<p class="hint" style="margin-top:8px">நேரில் முடியும் காய்ச்சீர் வெண்சீர் (வெண்பா உரிச்சீர்); நிரையில் முடியும் கனிச்சீர் வஞ்சி உரிச்சீர்.</p></div>';

    html += '<div class="panel"><h3>நாலசைச் சீர்கள் (பொதுச்சீர்)</h3>' + tbl(four) + '</div>';

    // தளை அணி
    var M = [
      ['மா', 'நேரொன்றாசிரியத்தளை', 'ஆசிரியம்', 'இயற்சீர் வெண்டளை', 'வெண்மை'],
      ['விளம்', 'இயற்சீர் வெண்டளை', 'வெண்மை', 'நிரையொன்றாசிரியத்தளை', 'ஆசிரியம்'],
      ['காய்', 'வெண்சீர் வெண்டளை', 'வெண்மை', 'கலித்தளை', 'கலி'],
      ['கனி', 'ஒன்றாத வஞ்சித்தளை', 'வஞ்சி', 'ஒன்றிய வஞ்சித்தளை', 'வஞ்சி']
    ];
    html += '<div class="panel"><h3>தளை — நின்ற சீர் முன் வரும் அசை</h3><div class="matrix"><span class="h">நின்ற சீர் ↓ / வரும் சீரின் முதலசை →</span><span class="h"><span class="chip ner">நேர்</span></span><span class="h"><span class="chip nirai">நிரை</span></span>' +
      M.map(function (r) { return '<span class="rh">' + r[0] + '</span><span class="c"><b class="fam-' + r[2] + '">' + r[1] + '</b></span><span class="c"><b class="fam-' + r[4] + '">' + r[3] + '</b></span>'; }).join('') +
      '</div><p class="hint" style="margin-top:10px">ஓரசைச்சீர் மா போலவும் (நேர்) விளம் போலவும் (நிரை); நாலசைச்சீர் காய் போலவும் (நேரீறு) கனி போலவும் (நிரையீறு) தளை கொள்ளும்.</p></div>';

    // தொடை
    html += '<div class="panel"><h3>தொடை விகற்பம் (ஓர் அடிக்குள்)</h3><table class="vtable"><tr><th>பெயர்</th><th>சீர்கள்</th></tr>' +
      [['இணை', '1, 2'], ['பொழிப்பு', '1, 3'], ['ஒரூஉ', '1, 4'], ['கூழை', '1, 2, 3'], ['மேற்கதுவாய்', '1, 3, 4'], ['கீழ்க்கதுவாய்', '1, 2, 4'], ['முற்று', '1, 2, 3, 4']]
        .map(function (r) { return '<tr><td class="nm">' + r[0] + '</td><td style="font-variant-numeric:tabular-nums">' + r[1] + '</td></tr>'; }).join('') +
      '</table><p class="hint" style="margin-top:8px">மோனை: முதலெழுத்து ஒன்றுதல். எதுகை: இரண்டாம் எழுத்து ஒன்றுதல் (முதலெழுத்து அளவொத்து). இன எழுத்துகள்: அ ஆ ஐ ஔ · இ ஈ எ ஏ · உ ஊ ஒ ஓ · ச த · ஞ ந · ம வ.</p></div>';

    // பா அட்டவணை
    html += '<div class="panel" style="grid-column:1/-1"><h3>நால்வகைப் பாக்கள்</h3><div class="tablebox"><table class="vtable"><tr><th>பா</th><th>ஓசை</th><th>உரிய சீர்</th><th>உரிய தளை</th><th>அடி</th><th>ஈறு</th></tr>' +
      '<tr><td class="nm">வெண்பா</td><td>செப்பலோசை</td><td>ஈரசைச்சீர், காய்ச்சீர்</td><td>வெண்டளை மட்டும்</td><td>அளவடி; ஈற்றடி சிந்தடி</td><td>நாள், மலர், காசு, பிறப்பு</td></tr>' +
      '<tr><td class="nm">ஆசிரியப்பா (அகவல்)</td><td>அகவலோசை</td><td>ஈரசைச்சீர் மிகுதி</td><td>ஆசிரியத்தளை மிகுதி; பிறவும் விரவும்</td><td>அளவடி; 3 அடி முதல்</td><td>பெரும்பாலும் ஏகாரம்</td></tr>' +
      '<tr><td class="nm">கலிப்பா</td><td>துள்ளலோசை</td><td>காய்ச்சீர் மிகுதி</td><td>கலித்தளை மிகுதி</td><td>அளவடி</td><td>தரவு, தாழிசை, தனிச்சொல், சுரிதகம் உறுப்புகள்</td></tr>' +
      '<tr><td class="nm">வஞ்சிப்பா</td><td>தூங்கலோசை</td><td>கனிச்சீர் மிகுதி</td><td>வஞ்சித்தளை மிகுதி</td><td>குறளடி / சிந்தடி</td><td>தனிச்சொல்லும் ஆசிரியச் சுரிதகமும்</td></tr>' +
      '</table></div></div>';
    $('#refgrid').innerHTML = html;
  }

  /* ---------- சொல் வங்கி (பயிற்சிக்கும் குறிப்புக்கும்) ---------- */
  var BANK = ('அன்பு அறம் அமுதம் அழகு அருவி அலை ஆறு ஆழி இனிமை இரவு இளமை உலகம் உள்ளம் உயிர் ஊர் எழில் ஒளி ஓசை கடல் கதிர் கனவு கண்ணீர் கருணை கல்வி கவிதை காலை காற்று குயில் குழந்தை கொடி கோயில் சிறகு சுடர் செல்வம் செந்தமிழ் சோலை தாய் திங்கள் தென்றல் தேன் நட்பு நதி நிலவு நிழல் நெஞ்சம் பறவை பனி பாடல் பூமி பொன் மண் மலர் மழை மனம் மாலை முகில் முத்து மேகம் மொழி யாழ் வண்ணம் வயல் வானம் வாழ்க்கை விண் வீரம் வெயில் வெள்ளம் அருள்மொழி பொன்னுலகம் மலர்க்கொடி கார்முகில் செங்கதிர் தண்ணிலவு பூஞ்சோலை மாமழை இளந்தென்றல் கடலலை வானவில் அலைகடல் மணிவிளக்கு திருவருள் பெருமை கருங்குயில் பைந்தமிழ் வெண்ணிலவு நறுமலர் பொழில் அணிகலன் இசைமழை தமிழ்நாடு கண்மணி மின்னல் வாழ்த்து நாள்தோறும் பாவலர் புலவர் அமைதி ஆடல் நீலவானம் வீடு கனிமொழி உழவர் விடியல் தாமரை பனிமலர் சிறுமழை').split(' ').map(function (w) { return Y.makeSir(w); });

  /* ---------- கவி பாடு ---------- */
  var FORMS = window.FORMS || [];
  var formSel = $('#form'), draft = $('#draft');
  FORMS.forEach(function (f, i) { var o = document.createElement('option'); o.value = i; o.textContent = f.name; formSel.appendChild(o); });
  formSel.value = store.get('form', 0);
  draft.value = store.get('draft', '');
  formSel.addEventListener('change', function () { store.set('form', formSel.value); runCompose(); });
  draft.addEventListener('input', function () { store.set('draft', draft.value); runCompose(); });

  var SLOT_OK = {
    'மா': function (s) { return s.short === 'மா'; },
    'விளம்': function (s) { return s.short === 'விளம்'; },
    'காய்': function (s) { return s.short === 'காய்'; },
    'கனி': function (s) { return s.short === 'கனி'; },
    'ஈரசை': function (s) { return s.kinds.length === 2; },
    'வெண்சீர்': function (s) { return s.kinds.length === 2 || s.short === 'காய்'; },
    'ஈறு': function (s) { return !!Y.asVenbaEnd(s); },
    'விளங்காய்': function (s) { return s.kinds.length === 3 && s.kinds[1] === Y.NIRAI && s.kinds[2] === Y.NER; },
    'ஆசிரியம்': function (s) { return s.kinds.length === 2 || s.short === 'காய்'; },
    'கட்டளை': function (s) { return s.kinds.length === 2 || (s.kinds.length === 3 && s.kinds[1] === Y.NER && s.kinds[2] === Y.NER); }
  };
  var SLOT_LABEL = { 'ஈரசை': 'மா / விளம்', 'வெண்சீர்': 'மா / விளம் / காய்', 'ஈறு': 'நாள் / மலர் / காசு / பிறப்பு', 'விளங்காய்': 'கூவிளங்காய் / கருவிளங்காய்', 'ஆசிரியம்': 'ஈரசை (மிகுதி)', 'கட்டளை': 'மா / விளம் / மாங்காய்' };
  function slotLabel(k) { return SLOT_LABEL[k] || k; }
  function fits(s, k) { return SLOT_OK[k] ? SLOT_OK[k](s) : s.name === k; }

  var comp = null;
  // ஒரு வரைவின் ஓர் அடி வடிவத்துக்குப் பொருந்துகிறதா (Claude பரிந்துரைத்த திருத்தத்தைச் சரிபார்க்க)
  function lineProblems(f, text, li) {
    var r = Y.analyze(text), lines = r.lines, nLines = f.lines ? f.lines.length : Math.max(lines.length, 4);
    var pat = f.lines ? f.lines[li] : f.line(li, nLines), l = lines[li], probs = [];
    if (!l) return ['அடி இல்லை'];
    if (l.sirs.length !== pat.length) probs.push(l.sirs.length + ' சீர்; ' + pat.length + ' வேண்டும்');
    pat.forEach(function (k, si) {
      var s = l.sirs[si]; if (!s) return;
      if (!fits(s, k)) probs.push('“' + s.word + '” ' + s.name + '; ' + slotLabel(k) + ' வேண்டும்');
      var endOfLine = si === l.sirs.length - 1;
      if (f.thalai && s.next && !(li === nLines - 1 && si === pat.length - 1) && !(f.thalaiInLine && endOfLine) && f.thalai.indexOf(s.next.fam) < 0)
        probs.push('“' + s.word + '” பின் ' + s.next.name);
    });
    return probs;
  }

  function runCompose() {
    var f = FORMS[+formSel.value]; if (!f) return;
    $('#formdesc').innerHTML = f.desc;
    if (!draft.value.trim()) draft.placeholder = f.example ? 'எ.கா.:\n' + f.example : '';
    var r = Y.analyze(draft.value);
    var lines = r.lines;
    var nLines = f.lines ? f.lines.length : Math.max(lines.length, 4);
    var html = '';
    var firstBad = null, nextSlot = null;
    for (var li = 0; li < nLines; li++) {
      var pat = f.lines ? f.lines[li] : f.line(li, nLines);
      var l = lines[li];
      html += '<div class="slotline" aria-label="' + ORD(li + 1) + ' அடி">';
      pat.forEach(function (k, si) {
        var s = l && l.sirs[si];
        var cls = '', got = '';
        if (s) {
          var ok = fits(s, k);
          var endOfLine = si === l.sirs.length - 1;
          var th = f.thalai && s.next && !(li === nLines - 1 && si === pat.length - 1) && !(f.thalaiInLine && endOfLine) && f.thalai.indexOf(s.next.fam) < 0;
          if (th) ok = false;
          cls = ok ? 'good' : 'bad';
          got = (Y.asVenbaEnd(s) && k === 'ஈறு' ? Y.asVenbaEnd(s) : s.name) + (th ? ' · ' + s.next.name : '');
          if (!ok && !firstBad) firstBad = { li: li, si: si, s: s, k: k, th: th };
        } else if (!nextSlot) nextSlot = { li: li, si: si, k: k, prev: prevSir(lines, li, si) };
        html += '<div class="slot ' + cls + '"><span class="w">' + (s ? esc(s.word) : '') + '</span><span class="want">' + esc(slotLabel(k)) + '</span>' + (got ? '<span class="got">' + esc(got) + '</span>' : '') + '</div>';
      });
      var extra = l && l.sirs.length > pat.length ? l.sirs.length - pat.length : 0;
      if (extra) html += '<div class="slot bad"><span class="w">+' + extra + '</span><span class="want">மிகைச் சீர்</span></div>';
      html += '</div>';
    }
    $('#slots').innerHTML = html;

    // அடுத்த சீருக்கான குறிப்பு
    var hint = '';
    if (firstBad) {
      hint = '<div class="eyebrow">திருத்துக</div><p style="margin:4px 0 0">' + ORD(firstBad.li + 1) + ' அடி, ' + ORD(firstBad.si + 1) + ' சீர் <b>' + esc(firstBad.s.word) + '</b> — ' + esc(firstBad.s.name) +
        (firstBad.th ? '; அடுத்த சீருடன் ' + firstBad.s.next.name + ' (' + firstBad.s.next.rule + ') உண்டாகிறது.' : '; இங்கே ' + esc(slotLabel(firstBad.k)) + ' வேண்டும்.') + '</p>';
    } else if (nextSlot) {
      var need = '', cands = BANK.filter(function (w) { return fits(w, nextSlot.k); });
      if (f.thalai && nextSlot.prev && !(f.thalaiInLine && nextSlot.si === 0)) {
        var p = nextSlot.prev, last = p.kinds[p.kinds.length - 1];
        var want = f.thalai.indexOf('வெண்மை') >= 0 ? (p.kinds.length <= 2 ? (last === Y.NER ? Y.NIRAI : Y.NER) : Y.NER) : null;
        if (want) {
          need = ' முந்தைய சீர் “' + esc(p.word) + '” ' + p.short + ' ஆதலால் இச்சீர் <span class="chip ' + (want === Y.NER ? 'ner' : 'nirai') + '">' + want + '</span> அசையில் தொடங்க வேண்டும்.';
          cands = cands.filter(function (w) { return w.kinds[0] === want; });
        }
      }
      if (nextSlot.si === 0 && nextSlot.li > 0 && lines[0] && lines[0].sirs[0]) {
        var e0 = lines[0].sirs[0], sec = e0.letters[1] && (e0.letters[1].cons || e0.letters[1].vowel);
        if (sec) {
          need += ' அடியெதுகைக்கு இரண்டாம் எழுத்து “' + esc(e0.letters[1].cons ? e0.letters[1].cons + '்' : sec) + '” வரிசையில் அமையட்டும்; முதலெழுத்து ' + (e0.letters[0].type === 'N' ? 'நெடிலாக' : 'குறிலாக') + ' இருக்கட்டும்.';
          var ec = cands.filter(function (w) { return Y.ethukai(e0, w) === 'நேர்'; });
          if (ec.length) cands = ec;
        }
      }
      // விருத்த மோனை இடம்
      if (f.monai && nextSlot.si > 0 && f.monai.indexOf(nextSlot.si + 1) >= 0 && lines[nextSlot.li] && lines[nextSlot.li].sirs[0]) {
        var m0 = lines[nextSlot.li].sirs[0];
        need += ' இது மோனை இடம்: முதற்சீர் “' + esc(m0.word) + '” போல “' + esc(m0.letters[0].text) + '” வரிசை எழுத்தில் தொடங்கட்டும்.';
        var mc = cands.filter(function (w) { return Y.monai(m0, w); });
        if (mc.length) cands = mc;
      }
      shuffle(cands);
      hint = '<div class="eyebrow">அடுத்து</div><p style="margin:4px 0 6px">' + ORD(nextSlot.li + 1) + ' அடி, ' + ORD(nextSlot.si + 1) + ' சீர்: <b>' + esc(slotLabel(nextSlot.k)) + '</b>.' + need + '</p>' +
        (cands.length ? '<p class="hint" style="margin:0">பொருந்தும் சொற்கள் சில: <span style="font-family:var(--display);font-size:16px;color:var(--ink)">' + cands.slice(0, 6).map(function (w) { return esc(w.word); }).join(' · ') + '</span></p>' : '');
    } else {
      hint = '<div class="eyebrow">முடிந்தது</div><p style="margin:4px 0 0">எல்லாச் சீர்களும் வடிவத்துக்குப் பொருந்துகின்றன. இனி பொருள் நயத்தையும் ஓசையையும் வாய்விட்டுப் பாடிச் சரிபாருங்கள்.</p>';
    }
    $('#nexthint').innerHTML = hint;

    var chk = '<div class="eyebrow">பொறியின் மதிப்பீடு</div>';
    if (r.pa && r.lines.length) {
      chk += '<p style="margin:4px 0;font-family:var(--display);font-size:20px">' + esc(r.pa.name) + '</p>';
      var hard = r.pa.issues.filter(function (i) { return !i.soft; });
      chk += hard.length ? '<ul class="issues">' + hard.slice(0, 6).map(function (i) { return '<li>' + esc(i.msg) + '</li>'; }).join('') + '</ul>' : '<p class="status ok" style="margin:0">பிழை இல்லை</p>';
      chk += '<p style="margin:8px 0 0"><button class="btn" id="toAnalyze">விரிவாக அலகிடு</button></p>';
    } else chk += '<p class="muted" style="margin:4px 0 0">எழுதத் தொடங்கியதும் இங்கே மதிப்பீடு தோன்றும்.</p>';
    $('#compcheck').innerHTML = chk;
    var ta = $('#toAnalyze'); if (ta) ta.addEventListener('click', function () { tryVerse(draft.value); });
    // Claude உதவிக்கு: இப்போதைய நிலை, அடுத்த இடத்தின் தேவைகள்
    comp = { f: f, r: r, lines: lines, nLines: nLines, firstBad: firstBad, nextSlot: nextSlot,
      want: (nextSlot && want) || null, e0: (nextSlot && nextSlot.si === 0 && nextSlot.li > 0 && e0) || null,
      m0: (nextSlot && m0 && f.monai && f.monai.indexOf(nextSlot.si + 1) >= 0) ? m0 : null };
    if (window.renderTutor) window.renderTutor();
  }
  function prevSir(lines, li, si) {
    if (si > 0) return lines[li] && lines[li].sirs[si - 1];
    if (li > 0 && lines[li - 1]) return lines[li - 1].sirs[lines[li - 1].sirs.length - 1];
    return null;
  }
  function shuffle(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }

  /* ---------- Claude ஆசிரியர் (கவி பாடு) ---------- */
  // சொற்களையும் திருத்தங்களையும் Claude பரிந்துரைக்கிறது; ஒவ்வொன்றையும் இத்தளத்தின் பொறியே சரிபார்க்கிறது.
  var tutor = { sample: null, busy: false, ctl: null, out: '', view: null, hidden: false };
  var TUTOR_OFF = { not_granted: 1, sampling_disabled: 1, not_declared: 1, capability_disabled: 1, capability_removed: 1 };
  function tutorError(e) {
    var c = e && e.code;
    if (TUTOR_OFF[c]) { tutor.hidden = true; return 'இந்தப் பார்வையில் Claude உதவி கிடைக்கவில்லை.'; }
    return ({
      cancelled: '', rate_limited: 'இப்போது அதிகக் கோரிக்கைகள்; சிறிது நேரம் கழித்து மீண்டும் முயலுங்கள்.',
      session_expired: 'மீண்டும் உள்நுழைய வேண்டும்.', refused: 'இக்கோரிக்கைக்கு Claude பதில் தரவில்லை; வரைவை மாற்றி முயலுங்கள்.',
      invalid_json: 'பதிலைப் படிக்க இயலவில்லை; மீண்டும் முயலுங்கள்.', prompt_too_large: 'வரைவு மிக நீளம்; சுருக்கி முயலுங்கள்.'
    })[c] || 'இணைப்பில் சிக்கல்; மீண்டும் முயலுங்கள்.';
  }
  function tutorCtx() {
    var c = comp, f = c.f, parts = [];
    parts.push('வடிவம்: ' + f.name + '. ' + f.desc.replace(/<[^>]+>/g, ''));
    parts.push('இதுவரை எழுதிய வரைவு:\n' + (draft.value.trim() || '(இன்னும் எழுதவில்லை)'));
    if (c.r.pa && c.r.lines.length) {
      var hard = c.r.pa.issues.filter(function (i) { return !i.soft; }).map(function (i) { return '- ' + i.msg; });
      parts.push('இத்தளத்தின் அலகீட்டுப் பொறி கண்டது: ' + c.r.pa.name + (hard.length ? '\nபிழைகள்:\n' + hard.join('\n') : ' (பிழை இல்லை)'));
    }
    return parts.join('\n\n');
  }
  function slotNeeds() {
    var c = comp, ns = c.nextSlot, bits = [];
    bits.push(ORD(ns.li + 1) + ' அடி, ' + ORD(ns.si + 1) + ' சீர்: வாய்பாடு ' + slotLabel(ns.k));
    if (c.want) bits.push(c.want + ' அசையில் தொடங்க வேண்டும் (முந்தைய சீர் “' + ns.prev.word + '”)');
    if (c.e0) bits.push('அடியெதுகை: முதலடியின் முதற்சீர் “' + c.e0.word + '” உடன் இரண்டாம் எழுத்து ஒன்ற வேண்டும்; முதலெழுத்து ' + (c.e0.letters[0].type === 'N' ? 'நெடில்' : 'குறில்'));
    if (c.m0) bits.push('மோனை: “' + c.m0.letters[0].text + '” வரிசை எழுத்தில் தொடங்க வேண்டும்');
    return bits;
  }
  function wordCheck(w) {
    var c = comp, s = Y.makeSir(w), why = [];
    if (!s.kinds.length) return { ok: false, why: ['தமிழ்ச் சொல் அல்ல'] };
    if (!fits(s, c.nextSlot.k)) why.push(s.name + '; ' + slotLabel(c.nextSlot.k) + ' வேண்டும்');
    if (c.want && s.kinds[0] !== c.want) why.push(s.kinds[0] + ' அசையில் தொடங்குகிறது; ' + c.want + ' வேண்டும்');
    if (c.e0 && Y.ethukai(c.e0, s) !== 'நேர்') why.push('எதுகை இல்லை');
    if (c.m0 && !Y.monai(c.m0, s)) why.push('மோனை இல்லை');
    return { ok: !why.length, why: why, name: s.name };
  }

  function setTutorOut(html) { tutor.view = html; var o = $('#tutorOut'); if (o) o.innerHTML = html; }
  window.renderTutor = function () {
    var el = $('#tutor'); if (!el) return;
    if (!tutor.sample) { el.hidden = true; return; }
    el.hidden = false;
    if (tutor.hidden) {
      el.querySelectorAll('[data-t]').forEach(function (b) { b.disabled = true; });
      $('#tutorStop').hidden = true;
      $('#tutorHint').textContent = 'இந்தப் பார்வையில் Claude உதவி கிடைக்கவில்லை; பொறியின் குறிப்புகள் தொடர்ந்து வேலை செய்யும்.';
      return;
    }
    var c = comp, canWords = c && !c.firstBad && c.nextSlot, canFix = c && c.firstBad;
    var btns = el.querySelectorAll('[data-t]');
    btns.forEach(function (b) {
      var t = b.dataset.t;
      b.disabled = tutor.busy || (t === 'words' && !canWords) || (t === 'fix' && !canFix) || (t === 'critique' && !(c && c.lines.length));
    });
    $('#tutorStop').hidden = !tutor.busy;
    $('#tutorHint').textContent = c && c.firstBad ? 'முதலில் பிழையான அடியைத் திருத்தலாம்.' : (c && c.nextSlot ? 'அடுத்த இடம்: ' + slotNeeds()[0] + '.' : 'பாடல் முழுமையானது; கருத்துக் கேட்கலாம்.');
  };

  function runTutor(kind) {
    if (!tutor.sample || tutor.busy || !comp) return;
    var sample = tutor.sample;
    tutor.busy = true; tutor.ctl = new AbortController(); renderTutor();
    setTutorOut('<p class="tutor-wait">Claude சிந்திக்கிறது…</p>');
    var done = function () { tutor.busy = false; tutor.ctl = null; renderTutor(); };
    var fail = function (e) {
      var msg = tutorError(e);
      if (e && e.code === 'cancelled') setTutorOut(tutor.partial ? '<div class="tutor-text"></div><p class="hint">நிறுத்தப்பட்டது.</p>' : '');
      else setTutorOut('<p class="status bad">' + esc(msg) + '</p>');
      var t = $('#tutorOut .tutor-text'); if (t) t.textContent = tutor.partial || '';
      done();
    };
    tutor.partial = '';

    if (kind === 'words') {
      var needs = slotNeeds();
      var prompt = 'நீ தமிழ் யாப்பிலக்கண ஆசிரியர். ஒரு மாணவர் மரபுக் கவிதை எழுதுகிறார்.\n\n' + tutorCtx() +
        '\n\nஅடுத்து நிரப்ப வேண்டிய இடம்:\n- ' + needs.join('\n- ') +
        '\n\nவாய்பாட்டுக் குறிப்பு: மா = நேரில் முடியும் ஈரசை (தேமா நேர்நேர், புளிமா நிரைநேர்); விளம் = நிரையில் முடியும் ஈரசை; காய் = நேரில் முடியும் மூவசை; நேர் = தனிக்குறில்/நெடில் (ஒற்றுடனும்); நிரை = குறில்+குறில்/நெடில் (ஒற்றுடனும்).' +
        '\n\nபாடலின் பொருளோடு இயல்பாகத் தொடரும், இந்த இடத்துக்கேற்ற 10 தமிழ்ச் சொற்களைப் பரிந்துரை. ஒவ்வொன்றும் ஒரே சீர் (இடைவெளி இல்லாமல்). ' +
        'பதிலாக JSON array மட்டும்: [{"w": "சொல்", "m": "சுருக்கமான பொருள் (5 சொற்களுக்குள்)"}]';
      sample.json(prompt, { signal: tutor.ctl.signal, modelTier: 'default', cache: false }).then(function (arr) {
        var list = (Array.isArray(arr) ? arr : []).filter(function (x) { return x && typeof x.w === 'string' && x.w.trim(); })
          .map(function (x) { var w = x.w.trim().split(/\s+/)[0]; return { w: w, m: String(x.m || ''), chk: wordCheck(w) }; });
        var seen = {}; list = list.filter(function (x) { if (seen[x.w]) return false; seen[x.w] = 1; return true; });
        list.sort(function (a, b) { return (b.chk.ok ? 1 : 0) - (a.chk.ok ? 1 : 0); });
        var okN = list.filter(function (x) { return x.chk.ok; }).length;
        var html = '<p class="hint" style="margin:0 0 8px">Claude ' + list.length + ' சொற்களைப் பரிந்துரைத்தது; இத்தளத்தின் பொறி சரிபார்த்ததில் <b>' + okN + '</b> பொருந்துகின்றன. பொருந்துவதைத் தொட்டால் வரைவில் சேரும்.</p><div class="tutor-words">' +
          list.map(function (x, i) {
            return '<button class="tword ' + (x.chk.ok ? 'ok' : 'no') + '" data-i="' + i + '"' + (x.chk.ok ? '' : ' disabled') + '><b></b><small></small><em></em></button>';
          }).join('') + '</div>';
        setTutorOut(html);
        $('#tutorOut').querySelectorAll('.tword').forEach(function (b) {
          var x = list[+b.dataset.i];
          b.querySelector('b').textContent = x.w;
          b.querySelector('small').textContent = x.chk.ok ? '✓ ' + x.chk.name : '✗ ' + x.chk.why.join('; ');
          b.querySelector('em').textContent = x.m;
          if (x.chk.ok) b.addEventListener('click', function () { insertWord(x.w); });
        });
        done();
      }, fail);

    } else if (kind === 'critique') {
      var p2 = 'நீ அன்பும் நுட்பமும் உள்ள தமிழ்க் கவிதை ஆசிரியர். மாணவர் எழுதிய மரபுக் கவிதைக்குக் கருத்துச் சொல்.\n\n' + tutorCtx() +
        '\n\nயாப்பைப் பொறி ஏற்கெனவே சரிபார்த்துவிட்டது; நீ மீண்டும் அலகிட வேண்டாம். பொறி கண்ட பிழைகள் இருந்தால் ஒரு வரியில் மட்டும் நினைவூட்டு.' +
        '\nஇவற்றைப் பற்றி எழுது: (1) பொருளும் கருத்தோட்டமும், (2) சொல்லாட்சியும் கற்பனையும் (கவிதையெழில்), (3) மேம்படுத்த 2–3 குறிப்பிட்ட பரிந்துரைகள் — மாற்றுச் சொல் சொன்னால் அது அதே வாய்பாட்டில் இருக்கட்டும்.' +
        '\nதமிழில், அன்பான ஆசிரியர் தொனியில், 180 சொற்களுக்குள். சிறு தலைப்புகள் இடலாம்; அட்டவணை, markdown குறியீடுகள் வேண்டாம்.';
      setTutorOut('<p class="tutor-wait">Claude சிந்திக்கிறது…</p>');
      sample(p2, {
        signal: tutor.ctl.signal, modelTier: 'default',
        onText: function (u) { tutor.partial = u.text; if (!$('#tutorOut .tutor-text')) setTutorOut('<div class="tutor-text"></div>'); $('#tutorOut .tutor-text').textContent = u.text.replace(/[*#]+/g, ''); }
      }).then(function (res) {
        if (res.truncated) $('#tutorOut').insertAdjacentHTML('beforeend', '<p class="hint">பதில் இடையில் நின்றது.</p>');
        done();
      }, fail);

    } else if (kind === 'fix') {
      var fb = comp.firstBad, f = comp.f, li = fb.li;
      var nL = f.lines ? f.lines.length : Math.max(comp.lines.length, 4);
      var pat = f.lines ? f.lines[li] : f.line(li, nL);
      var lineText = comp.lines[li].sirs.map(function (s) { return s.word; }).join(' ');
      var rule = f.thalai ? (f.thalaiInLine ? 'இவ்வடிக்குள் ' : '') + 'எல்லாச் சீர் இணைப்பிலும் வெண்டளை (மாமுன் நிரை, விளமுன் நேர், காய்முன் நேர்) வேண்டும்.' : '';
      var p3 = 'நீ தமிழ் யாப்பிலக்கண ஆசிரியர்.\n\n' + tutorCtx() +
        '\n\n' + ORD(li + 1) + ' அடி “' + lineText + '” பிழையாக உள்ளது: ' + lineProblems(f, draft.value, li).join('; ') +
        '\nஇந்த அடிக்குத் தேவையான சீர் வரிசை: ' + pat.map(slotLabel).join(' | ') + ' (' + pat.length + ' சீர்). ' + rule +
        '\nவாய்பாட்டுக் குறிப்பு: மா = நேரில் முடியும் ஈரசை; விளம் = நிரையில் முடியும் ஈரசை; காய் = நேரில் முடியும் மூவசை; நேர் = தனிக்குறில்/நெடில் (ஒற்றுடனும்); நிரை = குறில்+குறில்/நெடில் (ஒற்றுடனும்); சொல்லிடை ஐ குறிலாகக் கொள்ளப்படும்.' +
        '\n\nஅதே பொருளைக் காத்து, இந்த அடியை மட்டும் மூன்று விதமாகத் திருத்தி எழுது. சீர்களை இடைவெளியால் பிரி. ' +
        'பதிலாக JSON array மட்டும்: [{"line": "திருத்திய அடி", "why": "என்ன மாற்றினாய் (10 சொற்களுக்குள்)"}]';
      sample.json(p3, { signal: tutor.ctl.signal, modelTier: 'default', cache: false }).then(function (arr) {
        var draftLines = draft.value.split(/\r?\n/).filter(function (l) { return l.trim(); });
        var opts = (Array.isArray(arr) ? arr : []).filter(function (x) { return x && typeof x.line === 'string' && x.line.trim(); }).slice(0, 3).map(function (x) {
          var nl = draftLines.slice(); nl[li] = x.line.trim();
          var probs = lineProblems(f, nl.join('\n'), li);
          return { line: x.line.trim(), why: String(x.why || ''), probs: probs, text: nl.join('\n') };
        });
        var okN = opts.filter(function (o) { return !o.probs.length; }).length;
        setTutorOut('<p class="hint" style="margin:0 0 8px">' + ORD(li + 1) + ' அடிக்கு ' + opts.length + ' திருத்தங்கள்; பொறி சரிபார்த்ததில் <b>' + okN + '</b> இலக்கணப்படி சரி.</p><div class="tutor-fixes"></div>');
        var box = $('#tutorOut .tutor-fixes');
        opts.forEach(function (o) {
          var d = document.createElement('div'); d.className = 'tfix ' + (o.probs.length ? 'no' : 'ok');
          var ln = document.createElement('p'); ln.className = 'tfix-line'; ln.textContent = o.line;
          var wy = document.createElement('p'); wy.className = 'hint'; wy.textContent = o.why;
          var st = document.createElement('p'); st.className = 'tfix-st'; st.textContent = o.probs.length ? '✗ ' + o.probs.join('; ') : '✓ இலக்கணம் சரி';
          d.appendChild(ln); d.appendChild(wy); d.appendChild(st);
          if (!o.probs.length) {
            var use = document.createElement('button'); use.className = 'btn primary'; use.textContent = 'பயன்படுத்து';
            use.addEventListener('click', function () { draft.value = o.text; store.set('draft', draft.value); runCompose(); setTutorOut('<p class="status ok">' + ORD(li + 1) + ' அடி மாற்றப்பட்டது.</p>'); });
            d.appendChild(use);
          }
          box.appendChild(d);
        });
        done();
      }, fail);
    }
  }
  function insertWord(w) {
    var ns = comp.nextSlot, v = draft.value.replace(/\s+$/, '');
    var sep = !v ? '' : (ns.si === 0 ? '\n' : ' ');
    draft.value = v + sep + w + ' ';
    store.set('draft', draft.value); runCompose(); draft.focus();
    setTutorOut('<p class="status ok">“' + esc(w) + '” சேர்க்கப்பட்டது. அடுத்த இடத்துக்கு மீண்டும் கேட்கலாம்.</p>');
  }
  $('#tutor').addEventListener('click', function (e) {
    var b = e.target.closest('[data-t]'); if (b) runTutor(b.dataset.t);
    if (e.target.closest('#tutorStop') && tutor.ctl) tutor.ctl.abort();
  });
  if (window.claude && typeof window.claude.use === 'function') {
    window.claude.use('sample').then(function (s) { tutor.sample = s; renderTutor(); });
  }

  /* ---------- பயிற்சி ---------- */
  var QT = [
    { id: 'vp', name: 'வாய்பாடு' }, { id: 'asai', name: 'அசை பிரிப்பு' }, { id: 'thalai', name: 'தளை' }, { id: 'todai', name: 'மோனை / எதுகை' }, { id: 'pa', name: 'இது எந்தப் பா?' }
  ];
  // “இது எந்தப் பா?” — மாதிரிப் பாடல்களிலிருந்து; முதலில் குழுவைத் தேர்ந்தெடுப்பதால் குறள்கள் மட்டுமே வாரா
  var PA_NAMES = ['குறள் வெண்பா', 'சிந்தியல் வெண்பா', 'நேரிசை வெண்பா', 'இன்னிசை வெண்பா', 'பஃறொடை வெண்பா',
    'நேரிசை ஆசிரியப்பா', 'நிலைமண்டில ஆசிரியப்பா', 'இணைக்குறள் ஆசிரியப்பா', 'அறுசீர்க் கழிநெடிலடி ஆசிரிய விருத்தம்',
    'எழுசீர்க் கழிநெடிலடி ஆசிரிய விருத்தம்', 'எண்சீர்க் கழிநெடிலடி ஆசிரிய விருத்தம்', 'கலி விருத்தம்', 'கட்டளைக் கலித்துறை',
    'கலித்துறை (கலிநிலைத்துறை)', 'தரவு கொச்சகக் கலிப்பா', 'வஞ்சி விருத்தம்', 'வஞ்சித்துறை'];
  function paQuestion() {
    var groups = {};
    SAMPLES.forEach(function (s) { var r = Y.analyze(s.text); if (r.pa && r.pa.ok && r.lines.length <= 7) (groups[s.g] = groups[s.g] || []).push({ s: s, r: r }); });
    var gk = Object.keys(groups), grp = groups[gk[Math.floor(Math.random() * gk.length)]];
    var it = grp[Math.floor(Math.random() * grp.length)], r = it.r, name = r.pa.name;
    // ஒரே குடும்பத்திலிருந்து ஒரு குழப்பும் விடை, மற்றவை பிற குடும்பங்களிலிருந்து
    var fam = PA_NAMES.filter(function (p) { return p !== name && p.split(' ').pop() === name.split(' ').pop(); });
    var other = PA_NAMES.filter(function (p) { return p !== name && fam.indexOf(p) < 0; });
    var opts = [name].concat(shuffle(fam).slice(0, 1)); shuffle(other).forEach(function (p) { if (opts.length < 4) opts.push(p); });
    var counts = r.lines.map(function (l) { return l.sirs.length; });
    var f = r.stats.fam, dom = Object.keys(f).sort(function (a, b) { return f[b] - f[a]; })[0];
    var famName = { 'வெண்மை': 'வெண்டளை', 'ஆசிரியம்': 'ஆசிரியத்தளை', 'கலி': 'கலித்தளை', 'வஞ்சி': 'வஞ்சித்தளை' }[dom];
    var last = r.lines[r.lines.length - 1].sirs.slice(-1)[0];
    return { prompt: 'இப்பாடல் எந்த வகைப் பா அல்லது பாவினம்?', verse: it.s.text, answer: name, opts: shuffle(opts), src: it.s.label,
      exp: r.lines.length + ' அடி (சீர்: ' + counts.join(', ') + ') · மிகுதியான தளை: ' + famName + ' ' + f[dom] + '/' + r.stats.total +
        (r.pa.family === 'வெண்பா' ? ' · ஈற்றுச்சீர் ' + (last.venbaEnd || last.name) : '') + (r.pa.pattern ? ' · அமைப்பு: ' + r.pa.pattern : '') + ' · ' + it.s.label };
  }
  var quiz = { type: store.get('qtype', 'vp'), score: store.get('qscore', { right: 0, total: 0 }), cur: null };
  quiz.score.streak = quiz.score.streak || 0; quiz.score.best = quiz.score.best || 0;
  var FX = function () { return window.YappuFX || null; };   // game.js-இல் உள்ள ஒலி, தூவல்
  var STREAK_STEP = 5;                                       // ஐந்து தொடர் சரிக்கு ஒரு கொண்டாட்டம்
  $('#qtypes').innerHTML = QT.map(function (q) { return '<button data-q="' + q.id + '" aria-pressed="' + (q.id === quiz.type) + '">' + q.name + '</button>'; }).join('');
  $('#qtypes').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    quiz.type = b.dataset.q; store.set('qtype', quiz.type);
    $('#qtypes').querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', x === b); });
    nextQ();
  });
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function uniqOpts(correct, pool, n) {
    var o = [correct]; shuffle(pool.slice()).forEach(function (p) { if (o.length < n && o.indexOf(p) < 0) o.push(p); });
    return shuffle(o);
  }
  function asaiStr(s) { return s.asai.map(function (a) { return a.text; }).join(' | '); }
  function nextQ() {
    var q = {};
    var words = BANK.filter(function (w) { return w.kinds.length >= 1 && w.kinds.length <= 3; });
    if (quiz.type === 'vp') {
      var w = pick(words.filter(function (x) { return x.kinds.length >= 2; }));
      var pool = ['தேமா', 'புளிமா', 'கூவிளம்', 'கருவிளம்', 'தேமாங்காய்', 'புளிமாங்காய்', 'கூவிளங்காய்', 'கருவிளங்காய்', 'தேமாங்கனி', 'புளிமாங்கனி', 'கூவிளங்கனி', 'கருவிளங்கனி']
        .filter(function (p) { return (w.kinds.length === 2) === !/ங்/.test(p); });
      q = { prompt: 'இச்சீரின் வாய்பாடு என்ன?', word: w.word, answer: w.name, opts: uniqOpts(w.name, pool, 4), exp: asaiStr(w) + ' → ' + w.kinds.join(' ') + ' → ' + w.name };
    } else if (quiz.type === 'asai') {
      var w2 = pick(words.filter(function (x) { return x.kinds.length >= 2; }));
      var ans = w2.kinds.join(' ');
      var all = []; [2, 3].forEach(function (n) { (function gen(p) { if (p.length === n) { all.push(p.join(' ')); return; } gen(p.concat(['நேர்'])); gen(p.concat(['நிரை'])); })([]); });
      q = { prompt: 'இச்சொல்லின் அசைகள் எவை?', word: w2.word, answer: ans, opts: uniqOpts(ans, all.filter(function (x) { return x.split(' ').length === w2.kinds.length || Math.random() < .3; }), 4), exp: asaiStr(w2) + ' — ' + w2.asai.map(function (a) { return a.letters.map(function (x) { return ({ K: 'குறில்', N: 'நெடில்', O: 'ஒற்று' })[x.type]; }).join('+') + ' = ' + a.kind; }).join('; ') };
    } else if (quiz.type === 'thalai') {
      var a = pick(words), b = pick(words), th = Y.thalai(a, b);
      var names = Object.keys(Y.THALAI).map(function (k) { return Y.THALAI[k].name; });
      q = { prompt: 'நின்ற சீரும் வரும் சீரும் — இவற்றிடையே தளை என்ன?', word: a.word + ' &nbsp;·&nbsp; ' + b.word, answer: th.name, opts: uniqOpts(th.name, names, 4), exp: a.word + ' ' + a.short + ' (' + a.name + '); ' + b.word + ' ' + b.kinds[0] + 'அசையில் தொடங்குகிறது → ' + th.rule + ' = ' + th.name };
    } else if (quiz.type === 'pa') {
      q = paQuestion();
    } else {
      var x, y, tries = 0, want = pick(['m', 'e', 'n']);
      do {
        x = pick(BANK); y = pick(BANK); tries++;
        var m = !!Y.monai(x, y), e = Y.ethukai(x, y) === 'நேர்';
        var got = m && e ? 'b' : m ? 'm' : e ? 'e' : 'n';
      } while (x === y || (got !== want && tries < 400));
      var mm = !!Y.monai(x, y), ee = Y.ethukai(x, y) === 'நேர்';
      var ansT = mm && ee ? 'இரண்டும் உண்டு' : mm ? 'மோனை' : ee ? 'எதுகை' : 'இரண்டும் இல்லை';
      q = { prompt: 'இவ்விரு சீர்களிடையே எத்தொடை?', word: x.word + ' &nbsp;·&nbsp; ' + y.word, answer: ansT, opts: ['மோனை', 'எதுகை', 'இரண்டும் உண்டு', 'இரண்டும் இல்லை'],
        exp: 'முதலெழுத்து: ' + x.letters[0].text + ' / ' + y.letters[0].text + (mm ? ' (ஒன்றுகிறது)' : '') + ' · இரண்டாம் எழுத்து: ' + (x.letters[1] ? x.letters[1].text : '—') + ' / ' + (y.letters[1] ? y.letters[1].text : '—') + (ee ? ' (ஒன்றுகிறது)' : '') };
    }
    quiz.cur = q; quiz.answered = false;
    $('#qprompt').textContent = q.prompt;
    if (q.verse) {
      $('#qword').innerHTML = '<div class="qverse"></div>';
      $('#qword .qverse').textContent = q.verse;
    } else $('#qword').innerHTML = q.word.split(' &nbsp;·&nbsp; ').map(esc).join(' &nbsp;·&nbsp; ');
    $('#qopts').innerHTML = q.opts.map(function (o) { return '<button class="qopt" data-o="' + esc(o) + '">' + esc(o) + '</button>'; }).join('');
    $('#qexp').textContent = '';
    renderScore();
  }
  function renderScore() {
    var s = quiz.score, fx = FX(), on = fx ? fx.soundOn() : false;
    $('#qscore').innerHTML = '<span class="q-stat">சரி <b>' + s.right + ' / ' + s.total + '</b></span>' +
      '<span class="q-stat' + (s.streak ? ' hot' : '') + '" title="தொடர்ந்து சரியான விடைகள்">தொடர் <b>' + s.streak + '</b>' + (s.best ? ' <small>உச்சம் ' + s.best + '</small>' : '') + '</span>' +
      (fx ? '<button class="q-stat q-sound" id="qSound" aria-pressed="' + on + '" title="ஒலியை ' + (on ? 'அணை' : 'இயக்கு') + '">ஒலி</button>' : '');
    var sb = $('#qSound');
    if (sb) sb.addEventListener('click', function () { fx.setSound(!fx.soundOn()); renderScore(); });
  }
  $('#qopts').addEventListener('click', function (e) {
    var b = e.target.closest('.qopt'); if (!b || quiz.answered) return;
    quiz.answered = true;
    var right = b.dataset.o === quiz.cur.answer;
    quiz.score.total++; if (right) quiz.score.right++;
    quiz.score.streak = right ? quiz.score.streak + 1 : 0;
    quiz.score.best = Math.max(quiz.score.best, quiz.score.streak);
    store.set('qscore', quiz.score);
    var fx = FX();
    if (fx) {
      if (!right) fx.sfx('miss');
      else if (quiz.score.streak % STREAK_STEP === 0) {
        // ஐந்து தொடர் சரி: வெற்றி இசையும் தூவலும்; பத்துக்குப் பெரிதாக. தூவலில் வினாச் சொல்லின் எழுத்துகள்
        var src = quiz.cur.verse ? quiz.cur.answer : String(quiz.cur.word || '').split(' &nbsp;·&nbsp; ')[0];
        var letters = Y.letters(src).filter(function (L) { return L.type !== 'O'; }).map(function (L) { return L.text; }).slice(0, 3);
        fx.sfx('hit'); fx.sfx('win', 0.18);
        fx.confetti(180, quiz.score.streak % (STREAK_STEP * 2) === 0, letters);
      } else fx.sfx('hit');
    }
    $('#qopts').querySelectorAll('.qopt').forEach(function (x) { if (x.dataset.o === quiz.cur.answer) x.classList.add('right'); });
    if (!right) b.classList.add('wrong');
    var cheer = right && quiz.score.streak % STREAK_STEP === 0 ? ' <b class="status ok">' + quiz.score.streak + ' தொடர் சரி!</b> ' : '';
    $('#qexp').innerHTML = (right ? '<b class="status ok">சரி.</b> ' : '<b class="status bad">விடை: ' + esc(quiz.cur.answer) + '.</b> ') + cheer + esc(quiz.cur.exp) +
      (quiz.cur.verse ? ' <button class="btn" id="qScan" style="margin-top:8px">அலகிட்டுப் பார்</button>' : '');
    var qs = $('#qScan'); if (qs) qs.addEventListener('click', function () { tryVerse(quiz.cur.verse); });
    renderScore();
  });
  $('#qnext').addEventListener('click', nextQ);
  // game.js (ஒலி) app.js-க்குப் பின் ஏறுவதால், பக்கம் ஏறியதும் ஒலிப் பொத்தானுடன் மீண்டும் வரைய
  window.addEventListener('load', function () { if (quiz.cur) renderScore(); });

  /* ---------- வினா–விடை ---------- */
  function buildFaq() {
    var F = window.FAQ || [];
    $('#faq').innerHTML = '<div class="eyebrow">கவி பாடலாம் — வினா விடைகள்</div><h2>வினா–விடை</h2><p class="lede">கவிதை எழுதத் தொடங்குவோர் அடிக்கடி கேட்கும் ஐயங்களும் அவற்றுக்கான விளக்கங்களும்.</p>' +
      F.map(function (q, i) {
        if (q.g) return '<h3>' + esc(q.g) + '</h3>';
        return '<details class="faq"' + (i === 1 ? ' open' : '') + '><summary>' + esc(q.q) + '</summary>' + q.a + '</details>';
      }).join('');
    wireVerses($('#faq'));
  }

  /* ---------- தொடக்கம் ---------- */
  verse.value = store.get('verse', '') || (SAMPLES[0] ? SAMPLES[0].text : '');
  if (SAMPLES[0] && verse.value === SAMPLES[0].text) sampleSel.value = 0; else sampleSel.value = '';
  runAnalyze();
  buildRef();
  openLesson(store.get('lesson', LESSONS[0] && LESSONS[0].id));
  if (!draft.value && FORMS[+formSel.value]) draft.value = '';
  runCompose();
  buildFaq();
  var h = (location.hash || '').replace('#', '');
  show(views.indexOf(h) >= 0 ? h : store.get('view', 'analyze'));
})();
