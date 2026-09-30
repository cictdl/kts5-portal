/* யாப்புக் கலம் — யாப்பு இலக்கணப் பகுப்பாய்வுப் பொறி
 * எழுத்து → அசை → சீர் (வாய்பாடு) → தளை → தொடை → பா
 */
(function (global) {
  'use strict';

  var CONS = 'கஙசஞடணதநபமயரலவழளறனஜஷஸஹ';
  var VOWELS = 'அஆஇஈஉஊஎஏஐஒஓஔ';
  var SHORT = 'அஇஉஎஒ';
  var SIGN = { 'ா': 'ஆ', 'ி': 'இ', 'ீ': 'ஈ', 'ு': 'உ', 'ூ': 'ஊ', 'ெ': 'எ', 'ே': 'ஏ', 'ை': 'ஐ', 'ொ': 'ஒ', 'ோ': 'ஓ', 'ௌ': 'ஔ' };
  var PULLI = '்';
  var VALLINAM = 'கசடதபற';

  var NER = 'நேர்', NIRAI = 'நிரை';

  /* ---------- எழுத்து ---------- */
  // type: K = குறில், N = நெடில், O = ஒற்று / ஆய்தம்
  function letters(word) {
    var s = (word || '').normalize('NFC');
    var out = [];
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (VOWELS.indexOf(c) >= 0) {
        out.push({ text: c, cons: null, vowel: c });
      } else if (c === 'ஃ') {
        out.push({ text: c, cons: 'ஃ', vowel: null, type: 'O', aytham: true });
      } else if (CONS.indexOf(c) >= 0) {
        var n = s[i + 1];
        if (n === PULLI) { out.push({ text: c + n, cons: c, vowel: null, type: 'O' }); i++; }
        else if (SIGN[n]) { out.push({ text: c + n, cons: c, vowel: SIGN[n] }); i++; }
        else out.push({ text: c, cons: c, vowel: 'அ' });
      }
      // வேறு குறிகள் (நிறுத்தற்குறி, எண், இடைவெளிக் குறி) புறக்கணிக்கப்படும்
    }
    // சொல்முதலில் வாராத மெய்யில் தொடங்கும் சீர், சொல்லின் இடையில் வெட்டுண்டது (வகையுளி)
    var midWord = out.length && 'ஙடணரலழளறன'.indexOf(out[0].cons) >= 0;
    out.forEach(function (L, idx) {
      if (L.type) return;
      if (L.vowel === 'ஐ' && (idx > 0 || midWord)) { L.type = 'K'; L.note = 'ஐகாரக் குறுக்கம்'; }
      else L.type = SHORT.indexOf(L.vowel) >= 0 ? 'K' : 'N';
    });
    // குற்றியலிகரம் ஆகக்கூடிய இடம்: குற்றியலுகரம் யகரத்தின் முன் இகரமாகத் திரிந்தது
    // (நாடு + யாது → நாடியாது; அல்லது + யாதெனின் → அல்லதியாதெனின்). தனிக்குறிலை அடுத்து வருவது
    // (அடியார், நொடியாக) உடம்படுமெய் இகரம்; அது கணக்கில் இல்லை.
    out.forEach(function (L, idx) {
      var nx = out[idx + 1], pv = out[idx - 1];
      if (L.vowel === 'இ' && 'கசடதபறமன'.indexOf(L.cons) >= 0 && nx && nx.cons === 'ய' && nx.vowel &&
          !(idx === 1 && out[0].type === 'K')) { L.alt = 'ki'; return; }
      // உயிரளபெடை: நெடிலுக்குப் பின் அதன் இனக்குறில் தனித்து நிற்பது (தொழாஅர், பேஎய், தூஉம், உப்போஒ)
      if (pv && !L.cons && L.vowel && pv.vowel && ALAPEDAI[L.vowel] && ALAPEDAI[L.vowel].indexOf(pv.vowel) >= 0) { L.alt = 'uyir'; return; }
      // ஒற்றளபெடை / ஆய்த அளபெடை: ஒரே ஒற்று இரட்டித்து நிற்பது (கண்ண், எஃஃ)
      if (pv && L.type === 'O' && pv.type === 'O' && pv.text === L.text) { L.alt = L.aytham ? 'aytham' : 'otru'; L.solo = true; return; }
      // தனி ஆய்தம் சில இடங்களில் குற்றெழுத்துப் போல அலகு பெறும் (அஃதொருவன் ≈ அகுதொருவன்)
      if (L.aytham && !(nx && nx.aytham) && !(pv && pv.aytham) && pv && pv.type === 'K') L.alt = 'aythamK';
    });
    return out;
  }

  var ALAPEDAI = { 'அ': ['ஆ'], 'இ': ['ஈ', 'ஐ'], 'உ': ['ஊ', 'ஔ'], 'எ': ['ஏ'], 'ஒ': ['ஓ'] };
  // மாற்று அலகீடு: இயல்பில் ஒரு வகை; ஓசை கெடும் இடத்தில் மட்டும் மற்றது
  var ALT = {
    ki: { name: 'குற்றியலிகரம்', lose: true, why: 'குற்றியலுகரம் யகரத்தின் முன் இகரமாகத் திரிந்தது குற்றியலிகரம்; அரை மாத்திரையே ஒலிப்பதால் மெய்யைப் போல நிற்கும்.' },
    uyir: { name: 'உயிரளபெடை', lose: true, why: 'செய்யுள் ஓசை நிறைக்க வந்த அளபெடை அலகு பெறும்; விளியிலும் கூவலிலும் இயல்பாக நீளும் ஒலி (உப்போஒ) ஓசை நிறைக்க வாராததால் அலகு பெறாது.' },
    otru: { name: 'ஒற்றளபெடை', lose: false, why: 'ஓசை குறையும் இடத்தில் ஒற்று அளபெடுத்து நின்றால் அது ஓர் அலகு பெறும் (கண்ண், பொன்ன்).' },
    aytham: { name: 'ஆய்த அளபெடை', lose: false, why: 'ஆய்தம் அளபெடுத்து நின்றால் ஓர் எழுத்தைப் போல அலகு பெறும் (எஃஃ, வெஃஃகு).' },
    aythamK: { name: 'ஆய்தம்', lose: false, why: 'ஆய்தம் பொதுவாக அலகு பெறாது; ஓசை குறையும் இடத்தில் ஒரு குற்றெழுத்தைப் போல அலகு பெறும் (அஃதொருவன் ≈ அகுதொருவன்; கவி பாடலாம், வினா 12).' }
  };

  /* ---------- அசை ---------- */
  function asaiSplit(ls) {
    var res = [], i = 0, n = ls.length, lead = [];
    while (i < n) {
      var L = ls[i];
      if (L.type === 'O') {
        if (res.length) res[res.length - 1].letters.push(L);
        else lead.push(L); // சீர்முதலில் அலகு பெறாத எழுத்து — அடுத்த அசையோடு காட்டப்படும்
        i++; continue;
      }
      var a = { letters: lead.concat([L]) }, j = i + 1;
      lead = [];
      // அளபெடுத்த ஒற்று / ஆய்தம் தனியே ஒரு நேரசை (வெஃ | ஃ | கு)
      if (L.type === 'K' && !(L.gained && L.solo) && j < n && ls[j].type !== 'O' && !(ls[j].gained && ls[j].solo)) { a.letters.push(ls[j]); a.kind = NIRAI; j++; }
      else a.kind = NER;
      while (j < n && ls[j].type === 'O') { a.letters.push(ls[j]); j++; }
      a.text = a.letters.map(function (x) { return x.text; }).join('');
      res.push(a); i = j;
    }
    res.forEach(function (a) { a.text = a.letters.map(function (x) { return x.text; }).join(''); });
    return res;
  }

  // குற்றியலுகரம்: சொல்லிறுதி வல்லின உகரம், தனிக்குறிலை அடுத்து வராதது
  function kutriyalugaram(ls) {
    var n = ls.length;
    if (n < 2) return false;
    var last = ls[n - 1];
    if (last.vowel !== 'உ' || VALLINAM.indexOf(last.cons) < 0) return false;
    if (n === 2 && ls[0].type === 'K') return false; // பசு, அது — முற்றியலுகரம்
    return true;
  }

  /* ---------- சீர் ---------- */
  var TWO = { 'நேர் நேர்': 'தேமா', 'நிரை நேர்': 'புளிமா', 'நிரை நிரை': 'கருவிளம்', 'நேர் நிரை': 'கூவிளம்' };
  var STEM3 = { 'நேர் நேர்': 'தேமாங்', 'நிரை நேர்': 'புளிமாங்', 'நிரை நிரை': 'கருவிளங்', 'நேர் நிரை': 'கூவிளங்' };
  var STEM4 = { 'நேர் நேர்': 'தேமா', 'நிரை நேர்': 'புளிமா', 'நிரை நிரை': 'கருவிள', 'நேர் நிரை': 'கூவிள' };
  var TAIL4 = { 'நேர் நேர்': 'ந்தண்பூ', 'நேர் நிரை': 'ந்தண்ணிழல்', 'நிரை நேர்': 'நறும்பூ', 'நிரை நிரை': 'நறுநிழல்' };

  function vaaypaadu(kinds) {
    var k = kinds.slice(), n = k.length;
    if (n === 1) return k[0] === NER ? 'நாள்' : 'மலர்';
    var head = k[0] + ' ' + k[1];
    if (n === 2) return TWO[head];
    if (n === 3) return STEM3[head] + (k[2] === NER ? 'காய்' : 'கனி');
    if (n === 4) {
      return STEM4[head] + TAIL4[k[2] + ' ' + k[3]];
    }
    return kinds.join(' ');
  }

  // சுருக்கப் பெயர்: மா / விளம் / காய் / கனி / பூ / நிழல் / நாள் / மலர் / காசு / பிறப்பு
  function shortName(sir) {
    var k = sir.kinds, n = k.length, last = k[n - 1];
    if (sir.special) return sir.special;
    if (n === 1) return last === NER ? 'நாள்' : 'மலர்';
    if (n === 2) return last === NER ? 'மா' : 'விளம்';
    if (n === 3) return last === NER ? 'காய்' : 'கனி';
    return last === NER ? 'பூ' : 'நிழல்';
  }

  function sirClass(n, last) {
    if (n === 1) return 'அசைச்சீர் (ஓரசைச்சீர்)';
    if (n === 2) return 'இயற்சீர் (ஈரசைச்சீர் / ஆசிரிய உரிச்சீர்)';
    if (n === 3) return last === NER ? 'வெண்சீர் (காய்ச்சீர் / வெண்பா உரிச்சீர்)' : 'வஞ்சியுரிச்சீர் (கனிச்சீர்)';
    if (n === 4) return 'பொதுச்சீர் (நாலசைச்சீர்)';
    return 'அளவு மீறிய சீர்';
  }

  // சீரிடை ஒற்றைக் கடந்து அலகிடுதல்: இரு குறில்களுக்கு இடையே நிற்கும் ஒற்று ஓசையில் மறைந்து
  // அவை நிரையாக ஒலிப்பது (டாக்கும்வண்ணம் → டாக் | குவ | ணம்; ஆயர்தம் → ஆ | யதம்).
  // softOnly: மெல்லின, இடையின ஒற்றுகள் மட்டும் (விருத்தங்களில்); இல்லையேல் எந்த ஒற்றும் (கட்டளை ஈற்றுச்சீர்).
  function passOtru(word, softOnly) {
    var ls = letters(word), gone = [];
    var keep = ls.filter(function (L, i) {
      var pv = ls[i - 1], nx = ls[i + 1];
      var ok = L.type === 'O' && !L.aytham && pv && pv.type === 'K' && nx && nx.type !== 'O' && i < ls.length - 1 &&
        (!softOnly || 'ஙஞணநமனயரலவழள'.indexOf(L.cons) >= 0);
      if (ok) gone.push(L.text);
      return !ok;
    });
    if (!gone.length) return null;
    var kinds = asaiSplit(keep).map(function (a) { return a.kind; });
    var s = { kinds: kinds, name: vaaypaadu(kinds), gone: gone };
    s.short = shortName(s);
    return s;
  }

  // alt = true: இச்சீரின் குற்றியலிகரமும் உயிரளபெடையும் அலகு இழக்கின்றன; ஒற்றளபெடையும் ஆய்த அளபெடையும் அலகு பெறுகின்றன
  function makeSir(word, alt) {
    var ls = letters(word);
    if (alt) ls.forEach(function (L) {
      if (!L.alt) return;
      if (ALT[L.alt].lose) { L.type = 'O'; L.dropped = true; L.note = ALT[L.alt].name + ' — அலகு பெறாது'; }
      else { L.type = 'K'; L.gained = true; L.note = ALT[L.alt].name + ' — அலகு பெறும்'; }
    });
    var asai = asaiSplit(ls);
    var kinds = asai.map(function (a) { return a.kind; });
    var sir = { word: word, letters: ls, asai: asai, kinds: kinds };
    var lastA = asai[asai.length - 1];
    // சீர் தனி உகர எழுத்தில் முடிவது (அசையில் தனித்து நிற்பது)
    sir.uEnd = !!lastA && lastA.letters.length === 1 && lastA.letters[0].vowel === 'உ';
    sir.kurriyal = kutriyalugaram(ls) && sir.uEnd;
    // முற்றியலுகர ஈறு (கதவு, அறிவு) — வெண்பா ஈற்றில் சிறுபான்மை காசு / பிறப்பாக வரும்
    sir.mutru = sir.uEnd && !sir.kurriyal;
    sir.altKinds = ls.filter(function (L) { return L.alt; }).map(function (L) { return L.alt; })
      .filter(function (k, i, a) { return a.indexOf(k) === i; });
    sir.altCand = sir.altKinds.length > 0;
    sir.altApplied = !!alt && sir.altCand;
    sir.name = kinds.length ? vaaypaadu(kinds) : '';
    sir.short = kinds.length ? shortName(sir) : '';
    sir.klass = sirClass(kinds.length, kinds[kinds.length - 1]);
    sir.count = ls.filter(function (x) { return x.type !== 'O'; }).length; // ஒற்று நீக்கிய எழுத்து எண்ணிக்கை
    return sir;
  }

  // வெண்பாவின் ஈற்றுச்சீராக மதிப்பிடல்: நாள் / மலர் / காசு / பிறப்பு
  function asVenbaEnd(sir) {
    var k = sir.kinds;
    if (k.length === 1) return k[0] === NER ? 'நாள்' : 'மலர்';
    if (k.length === 2 && k[1] === NER && (sir.kurriyal || sir.mutru)) return k[0] === NER ? 'காசு' : 'பிறப்பு';
    return null;
  }

  /* ---------- தளை ---------- */
  var THALAI = {
    NERONRU: { name: 'நேரொன்றாசிரியத்தளை', fam: 'ஆசிரியம்', rule: 'மா முன் நேர்' },
    NIRAIONRU: { name: 'நிரையொன்றாசிரியத்தளை', fam: 'ஆசிரியம்', rule: 'விளம் முன் நிரை' },
    IYARVEN: { name: 'இயற்சீர் வெண்டளை', fam: 'வெண்மை', rule: 'மா முன் நிரை, விளம் முன் நேர்' },
    VENSIRVEN: { name: 'வெண்சீர் வெண்டளை', fam: 'வெண்மை', rule: 'காய் முன் நேர்' },
    KALI: { name: 'கலித்தளை', fam: 'கலி', rule: 'காய் முன் நிரை' },
    ONRIYA: { name: 'ஒன்றிய வஞ்சித்தளை', fam: 'வஞ்சி', rule: 'கனி முன் நிரை' },
    ONRATHA: { name: 'ஒன்றாத வஞ்சித்தளை', fam: 'வஞ்சி', rule: 'கனி முன் நேர்' }
  };

  function thalai(a, b) {
    if (!a.kinds.length || !b.kinds.length) return null;
    var last = a.kinds[a.kinds.length - 1], first = b.kinds[0];
    if (a.kinds.length <= 2) {
      if (last === first) return last === NER ? THALAI.NERONRU : THALAI.NIRAIONRU;
      return THALAI.IYARVEN;
    }
    if (last === NER) return first === NER ? THALAI.VENSIRVEN : THALAI.KALI;
    return first === NIRAI ? THALAI.ONRIYA : THALAI.ONRATHA;
  }

  /* ---------- தொடை ---------- */
  var VGROUP = { 'அ': 1, 'ஆ': 1, 'ஐ': 1, 'ஔ': 1, 'இ': 2, 'ஈ': 2, 'எ': 2, 'ஏ': 2, 'உ': 3, 'ஊ': 3, 'ஒ': 3, 'ஓ': 3 };
  var CGROUP = { 'ச': 'சத', 'த': 'சத', 'ஞ': 'ஞந', 'ந': 'ஞந', 'ம': 'மவ', 'வ': 'மவ' };

  function firstSyl(sir) { return sir.letters.filter(function (x) { return x.type !== 'O' || x.aytham; })[0]; }

  // மோனை: முதல் எழுத்து ஒன்றுதல் (இன எழுத்தும் கொள்ளப்படும்)
  function monai(a, b) {
    var x = a.letters[0], y = b.letters[0];
    if (!x || !y) return null;
    // ய, ர, ல முதல் சொற்களுக்கு இ ஈ எ ஏ உயிர்கள் மோனையாகும்
    var YRL = 'யரல';
    if ((YRL.indexOf(x.cons) >= 0 && !y.cons && VGROUP[y.vowel] === 2) ||
        (YRL.indexOf(y.cons) >= 0 && !x.cons && VGROUP[x.vowel] === 2)) return 'இனம்';
    if (x.cons !== y.cons) {
      if (!(x.cons && y.cons && CGROUP[x.cons] && CGROUP[x.cons] === CGROUP[y.cons])) return null;
      if (VGROUP[x.vowel] !== VGROUP[y.vowel]) return null;
      return 'இனம்';
    }
    if (x.vowel === y.vowel) return 'நேர்';
    if (VGROUP[x.vowel] && VGROUP[x.vowel] === VGROUP[y.vowel]) return 'இனம்';
    return null;
  }

  // எதுகை: இரண்டாம் எழுத்து (மெய்) ஒன்றுதல்; முதலெழுத்தின் அளவும் ஒத்திருக்க வேண்டும்
  function ethukai(a, b) {
    var x = a.letters, y = b.letters;
    if (x.length < 2 || y.length < 2) return null;
    var cx = x[1].cons || x[1].vowel, cy = y[1].cons || y[1].vowel;
    var lenOk = (x[0].type === 'N') === (y[0].type === 'N');
    if (cx !== cy) {
      // இன எதுகை: இரண்டாம் எழுத்து ஒரே இனமாக (வல்லினம் / மெல்லினம் / இடையினம்)
      var cls = function (c) { return 'கசடதபற'.indexOf(c) >= 0 ? 1 : 'ஙஞணநமன'.indexOf(c) >= 0 ? 2 : 'யரலவழள'.indexOf(c) >= 0 ? 3 : 0; };
      if (lenOk && cls(cx) > 1 && cls(cx) === cls(cy)) return 'இனம்';
      return null;
    }
    return lenOk ? 'நேர்' : 'அளவு மாறியது';
  }

  var TODAI_KIND = [
    { key: '1,2', name: 'இணை' },
    { key: '1,3', name: 'பொழிப்பு' },
    { key: '1,4', name: 'ஒரூஉ' },
    { key: '1,2,3', name: 'கூழை' },
    { key: '1,3,4', name: 'மேற்கதுவாய்' },
    { key: '1,2,4', name: 'கீழ்க்கதுவாய்' },
    { key: '1,2,3,4', name: 'முற்று' }
  ];

  function todaiInLine(sirs, fn) {
    if (sirs.length < 2) return null;
    var hits = [1];
    for (var i = 1; i < Math.min(4, sirs.length); i++) if (fn(sirs[0], sirs[i])) hits.push(i + 1);
    if (hits.length < 2) return null;
    var key = hits.join(',');
    var k = TODAI_KIND.filter(function (t) { return t.key === key; })[0];
    return { positions: hits, name: k ? k.name : null };
  }

  /* ---------- பகுப்பு ---------- */
  function splitWords(line) {
    return line.normalize('NFC')
      .replace(/[​-‍﻿]/g, '')
      .replace(/[.,;:!?'"“”‘’()\[\]{}0-9|/\\—–_*#…]/g, ' ')
      .split(/[\s\-]+/).filter(function (w) { return letters(w).length; });
  }

  function analyze(text) {
    var rawLines = (text || '').split(/\r?\n/).map(function (l) { return l.trim(); })
      .filter(function (l) { return l && splitWords(l).length; });
    var words = rawLines.map(splitWords);
    var base = build(rawLines, words, {});
    // குற்றியலிகரம், அளபெடை: இயல்பான அலகீடு சீரையும் தளையையும் கெடுக்கும் இடங்களில் மட்டும் மாற்று அலகீடு
    var cands = [];
    base.flat.forEach(function (f) { if (f.sir.altCand) cands.push(f.line + ':' + f.pos); });
    if (!cands.length || !base.pa || base.pa.ok || cands.length > 8) return base;
    var best = base, bestScore = score(base.pa), bestDrops = 0;
    for (var mask = 1; mask < (1 << cands.length); mask++) {
      var drop = {}, nd = 0;
      cands.forEach(function (c, ci) { if (mask & (1 << ci)) { drop[c] = true; nd++; } });
      var r = build(rawLines, words, drop), sc = score(r.pa);
      if (sc < bestScore || (sc === bestScore && best !== base && nd < bestDrops)) { best = r; bestScore = sc; bestDrops = nd; }
    }
    if (best !== base) {
      best.flat.forEach(function (f, k) {
        if (!f.sir.altApplied) return;
        var was = base.flat[k].sir;
        // அலகு கொடுத்தால் கெடும் தளைகள் (முந்தைய சீருடனும் அடுத்த சீருடனும்)
        var broke = [];
        if (k > 0 && base.flat[k - 1].sir.next && best.flat[k - 1].sir.next &&
            base.flat[k - 1].sir.next.name !== best.flat[k - 1].sir.next.name)
          broke.push('“' + base.flat[k - 1].sir.word + '” உடன் ' + base.flat[k - 1].sir.next.name);
        if (was.next && f.sir.next && was.next.name !== f.sir.next.name)
          broke.push('“' + base.flat[k + 1].sir.word + '” உடன் ' + was.next.name);
        var alts = f.sir.letters.filter(function (x) { return x.alt; });
        var lose = ALT[alts[0].alt].lose;
        var what = alts.map(function (x) { return '“' + x.text + '” ' + ALT[x.alt].name; }).join(', ');
        best.pa.issues.unshift({ soft: true, info: true, line: f.line, pos: f.pos,
          msg: '“' + f.sir.word + '” — ' + what + '. ' + (lose ? 'அலகு கொடுத்தால்' : 'அலகு கொடாவிட்டால்') + ' இச்சீர் ' + was.name +
            (was.kinds.length === 1 && !broke.length ? ' (ஓரசைச்சீர்; அது பாட்டின் இடையில் வாராது)' : '') +
            (broke.length ? ' ஆகி, ' + broke.join('; ') + ' உண்டாகும்' : '') +
            '. ' + (lose ? 'அலகு நீக்கியதால்' : 'அலகு கொடுத்ததால்') + ' ' + (f.sir.venbaEnd || f.sir.name) + '; இலக்கணம் சரியாகிறது.' });
      });
      best.altApplied = true;
    }
    return best;
  }

  function build(rawLines, words, drop) {
    var lines = rawLines.map(function (l, li) {
      var sirs = words[li].map(function (w, si) { return makeSir(w, drop[li + ':' + si]); });
      return { text: l, sirs: sirs, index: li };
    });

    // தளைகள் (அடி கடந்தும்)
    var flat = [];
    lines.forEach(function (l) { l.sirs.forEach(function (s, si) { flat.push({ sir: s, line: l.index, pos: si }); }); });
    for (var i = 0; i < flat.length - 1; i++) {
      flat[i].sir.next = thalai(flat[i].sir, flat[i + 1].sir);
      flat[i].sir.nextCrossesLine = flat[i].line !== flat[i + 1].line;
    }

    lines.forEach(function (l) {
      l.monai = todaiInLine(l.sirs, monai);
      l.ethukai = todaiInLine(l.sirs, function (a, b) { return ethukai(a, b) === 'நேர்'; });
      l.pattern = l.sirs.map(function (s) { return s.short; });
      l.count = l.sirs.reduce(function (t, s) { return t + s.count; }, 0);
    });

    // அடியெதுகை / அடிமோனை
    var adiEthukai = [], adiMonai = [];
    for (var j = 1; j < lines.length; j++) {
      adiEthukai.push(ethukai(lines[0].sirs[0], lines[j].sirs[0]));
      adiMonai.push(monai(lines[0].sirs[0], lines[j].sirs[0]));
    }

    var result = { lines: lines, flat: flat, adiEthukai: adiEthukai, adiMonai: adiMonai };
    result.stats = stats(flat);
    result.pa = identify(result);
    return result;
  }

  function stats(flat) {
    var fam = { 'வெண்மை': 0, 'ஆசிரியம்': 0, 'கலி': 0, 'வஞ்சி': 0 }, total = 0;
    flat.forEach(function (f) { if (f.sir.next) { fam[f.sir.next.fam]++; total++; } });
    return { fam: fam, total: total };
  }

  /* ---------- பா அடையாளம் ---------- */
  function adiName(n) {
    return ({ 1: 'தனிச்சீர்', 2: 'குறளடி', 3: 'சிந்தடி', 4: 'அளவடி', 5: 'நெடிலடி' })[n] || (n >= 6 ? 'கழிநெடிலடி' : '');
  }

  function venbaCheck(r) {
    var L = r.lines, issues = [];
    if (L.length < 2) return null;
    L.forEach(function (l, li) {
      var last = li === L.length - 1;
      var want = last ? 3 : 4;
      if (l.sirs.length !== want)
        issues.push({ line: li, msg: (li + 1) + 'ஆம் அடியில் ' + l.sirs.length + ' சீர்; ' + (last ? 'ஈற்றடி சிந்தடியாக (3 சீர்)' : 'அளவடியாக (4 சீர்)') + ' இருக்க வேண்டும்.' });
      l.sirs.forEach(function (s, si) {
        var isEnd = last && si === l.sirs.length - 1;
        if (isEnd) {
          var e = asVenbaEnd(s);
          if (e) {
            s.venbaEnd = e;
            if (s.mutru && s.kinds.length === 2) issues.push({ line: li, pos: si, soft: true, info: true, msg: 'ஈற்றுச்சீர் “' + s.word + '” முற்றியலுகரத்தில் முடிகிறது; காசு, பிறப்பு ஈற்றில் பெரும்பாலும் குற்றியலுகரம் வரும், சிறுபான்மை இப்படியும் வரும் (கதவு).' });
          }
          else issues.push({ line: li, pos: si, msg: 'ஈற்றுச்சீர் “' + s.word + '” ' + s.name + '. வெண்பா நாள், மலர், காசு, பிறப்பு என்னும் வாய்பாட்டில் முடிய வேண்டும்.' });
          return;
        }
        if (s.kinds.length === 1) issues.push({ line: li, pos: si, msg: '“' + s.word + '” ஓரசைச்சீர்; அது ஈற்றில் மட்டுமே வரலாம்.' });
        if (s.kinds.length === 3 && s.kinds[2] === NIRAI) issues.push({ line: li, pos: si, msg: '“' + s.word + '” கனிச்சீர் (' + s.name + '); வெண்பாவில் கனிச்சீர் வராது.' });
        if (s.kinds.length >= 4) issues.push({ line: li, pos: si, msg: '“' + s.word + '” நாலசைச்சீர்; வெண்பாவில் வராது.' });
        if (s.next && s.next.fam !== 'வெண்மை') issues.push({ line: li, pos: si, thalai: true, msg: '“' + s.word + '” → “' + nextWord(r, li, si) + '”: ' + s.next.name + ' (' + s.next.rule + '). வெண்டளை வேண்டும்.' });
      });
    });
    var name;
    var n = L.length;
    if (n === 2) name = 'குறள் வெண்பா';
    else if (n === 3) name = 'சிந்தியல் வெண்பா';
    else if (n === 4) {
      var tani = L[1].sirs[L[1].sirs.length - 1];
      var e1 = L[1].sirs.length >= 4 && ethukai(L[0].sirs[0], tani) === 'நேர்';
      name = e1 ? 'நேரிசை வெண்பா' : 'இன்னிசை வெண்பா';
    } else if (n <= 12) name = 'பஃறொடை வெண்பா';
    else name = 'கலிவெண்பா';
    return { name: name, family: 'வெண்பா', issues: issues };
  }

  function nextWord(r, li, si) {
    var l = r.lines[li];
    if (si + 1 < l.sirs.length) return l.sirs[si + 1].word;
    return r.lines[li + 1] ? r.lines[li + 1].sirs[0].word : '';
  }

  function kattalaiCheck(r) {
    var L = r.lines;
    if (L.length !== 4 || L.some(function (l) { return l.sirs.length !== 5; })) return null;
    var issues = [];
    L.forEach(function (l, li) {
      var startNer = l.sirs[0].kinds[0] === NER, want = startNer ? 16 : 17;
      if (l.count !== want) issues.push({ line: li, msg: (li + 1) + 'ஆம் அடியில் ஒற்று நீக்கி ' + l.count + ' எழுத்து; ' + (startNer ? 'நேரசையில்' : 'நிரையசையில்') + ' தொடங்குவதால் ' + want + ' வேண்டும்.' });
      for (var i = 0; i < 4; i++) {
        var s = l.sirs[i];
        if (s.next && s.next.fam !== 'வெண்மை') issues.push({ line: li, pos: i, thalai: true, msg: '“' + s.word + '” → “' + l.sirs[i + 1].word + '”: ' + s.next.name + '. முதல் நான்கு சீரும் வெண்டளையால் பிணைய வேண்டும்.' });
      }
      var e = l.sirs[4];
      var vilangaay = function (k) { return k.length === 3 && k[1] === NIRAI && k[2] === NER; };
      if (!vilangaay(e.kinds)) {
        var pe = passOtru(e.word, false);
        if (pe && vilangaay(pe.kinds)) issues.push({ line: li, pos: 4, soft: true, info: true, msg: 'ஈற்றுச்சீர் “' + e.word + '” தோற்றத்தில் ' + e.name + '; இடையிலுள்ள ஒற்றை (' + pe.gone.join(', ') + ') நீக்கி அலகிட ' + pe.name + ' — கட்டளைக் கலித்துறை ஈற்றில் இவ்வாறு கொள்வது மரபு.' });
        else issues.push({ line: li, pos: 4, msg: 'ஈற்றுச்சீர் “' + e.word + '” ' + e.name + '; கூவிளங்காய் அல்லது கருவிளங்காய் வேண்டும்.' });
      }
    });
    var lastL = L[3].sirs[4].letters, lastLetter = lastL[lastL.length - 1];
    if (!lastLetter || lastLetter.vowel !== 'ஏ') issues.push({ line: 3, msg: 'கட்டளைக் கலித்துறை பெரும்பாலும் ஏகாரத்தில் முடியும்.', soft: true });
    return { name: 'கட்டளைக் கலித்துறை', family: 'பாவினம் (கலிப்பா இனம்)', issues: issues };
  }

  function samePattern(L) {
    var p = L[0].pattern.join(' ');
    return L.every(function (l) { return l.pattern.join(' ') === p; });
  }

  function viruttamCheck(r) {
    var L = r.lines;
    if (L.length !== 4) return null;
    var n = L[0].sirs.length;
    if (!L.every(function (l) { return l.sirs.length === n; }) || n < 2) return null;
    var issues = [];
    var ref = L[0].pattern;
    // ஐஞ்சீருக்குக் குறைந்த வஞ்சி, கலித்துறை வடிவங்களில் சீரமைப்பு ஒத்திருப்பது சிறப்பு மட்டுமே
    var soft = n <= 5 && n !== 4;
    // கட்டளைக் கலிப்பாவின் அரையடி போன்ற கலிவிருத்தம்: நேர் முதல் 11, நிரை முதல் 12 எழுத்து
    var kattalaiHalf = n === 4 && L.every(function (l) { return l.count === (l.sirs[0].kinds[0] === NER ? 11 : 12); });
    L.forEach(function (l, li) {
      l.pattern.forEach(function (p, pi) {
        if (p === ref[pi]) return;
        var w = l.sirs[pi].word;
        // இடையின / மெல்லின ஒற்று இடையில் வந்த காய், விளம் போலவே ஒலிக்கும் (கவி பாடலாம், வினா 48, 51)
        var alt = (p === 'காய்' || p === 'கனி') && passOtru(w, true);
        if (alt && alt.short === ref[pi]) {
          issues.push({ line: li, pos: pi, soft: true, info: true, msg: '“' + w + '” தோற்றத்தில் ' + l.sirs[pi].name + '; இடையிலுள்ள “' + alt.gone.join('”, “') + '” ஒற்று ஓசையில் மறைவதால் ' + alt.name + ' போல ஒலித்து, முதலடியின் ' + ref[pi] + ' இடத்தோடு ஒத்து நிற்கிறது.' });
          return;
        }
        issues.push({ line: li, pos: pi, soft: soft || kattalaiHalf, msg: (li + 1) + 'ஆம் அடி ' + (pi + 1) + 'ஆம் சீர் “' + w + '” ' + p + '; முதலடியில் அவ்விடத்தில் ' + ref[pi] + '.' });
      });
    });
    if (kattalaiHalf) issues.push({ soft: true, msg: 'அடிதோறும் ஒற்று நீக்கி நேர் முதல் 11 / நிரை முதல் 12 எழுத்து — கட்டளைக் கலிப்பாவின் அரையடி போன்ற கலிவிருத்தம்.' });
    var name;
    if (n === 2) name = 'வஞ்சித்துறை';
    else if (n === 3) name = 'வஞ்சி விருத்தம்';
    else if (n === 4) name = 'கலி விருத்தம்';
    else if (n === 5) name = ref[2] === 'கனி' ? 'காப்பியக் கலித்துறை (விருத்தக் கலித்துறை)' : 'கலித்துறை (கலிநிலைத்துறை)';
    else name = ({ 6: 'அறுசீர்', 7: 'எழுசீர்', 8: 'எண்சீர்' })[n] ? ({ 6: 'அறுசீர்', 7: 'எழுசீர்', 8: 'எண்சீர்' })[n] + 'க் கழிநெடிலடி ஆசிரிய விருத்தம்' : n + ' சீர்க் கழிநெடிலடி ஆசிரிய விருத்தம்';
    return { name: name, family: 'பாவினம்', issues: issues, pattern: ref.join(' ') };
  }

  function asiriyamCheck(r) {
    var L = r.lines;
    if (L.length < 3) return null;
    var issues = [], n = L.length;
    var counts = L.map(function (l) { return l.sirs.length; });
    var bad = counts.filter(function (c) { return c < 2 || c > 4; }).length;
    if (bad || counts[0] !== 4 || counts[n - 1] < 3) return null;
    L.forEach(function (l, li) {
      l.sirs.forEach(function (s, si) {
        if (s.kinds.length === 3 && s.kinds[2] === NIRAI) issues.push({ line: li, pos: si, msg: '“' + s.word + '” கனிச்சீர்; ஆசிரியப்பாவில் கனிச்சீர் வாராது.' });
        if (s.kinds.length === 1 && !(li === n - 1 && si === l.sirs.length - 1)) issues.push({ line: li, pos: si, msg: '“' + s.word + '” ஓரசைச்சீர்.', soft: true });
      });
    });
    var name;
    var inner = counts.slice(1, -1);
    if (counts.every(function (c) { return c === 4; })) name = 'நிலைமண்டில ஆசிரியப்பா';
    else if (counts[n - 2] === 3 && counts.filter(function (c, i) { return i !== n - 2 && c !== 4; }).length === 0) name = 'நேரிசை ஆசிரியப்பா';
    else if (counts[0] === 4 && counts[n - 1] === 4 && inner.some(function (c) { return c < 4; })) name = 'இணைக்குறள் ஆசிரியப்பா';
    else name = 'ஆசிரியப்பா';
    var st = r.stats;
    var asiFrac = st.total ? st.fam['ஆசிரியம்'] / st.total : 1;
    if (asiFrac < 0.15) issues.push({ msg: 'ஆசிரியத்தளை ' + st.fam['ஆசிரியம்'] + '/' + st.total + ' இடங்களில் மட்டுமே; அகவல் ஓசை இல்லை.' });
    else if (asiFrac < 0.4) issues.push({ msg: 'ஆசிரியத்தளை ' + st.fam['ஆசிரியம்'] + '/' + st.total + ' இடங்களில் மட்டுமே; அகவல் ஓசை மிகுதியாக இருக்க வேண்டும்.', soft: true });
    var lastSir = L[n - 1].sirs[L[n - 1].sirs.length - 1], ll = lastSir.letters[lastSir.letters.length - 1];
    if (!ll || ll.vowel !== 'ஏ') issues.push({ msg: 'ஆசிரியப்பா பெரும்பாலும் ஏகாரத்தில் முடியும் (ஏ, ஓ, ஈ, ஆய், என், ஐ ஈறுகளும் உண்டு).', soft: true });
    return { name: name, family: 'ஆசிரியப்பா', issues: issues };
  }

  // தரவு கொச்சகக் கலிப்பா: நாற்சீர் நான்கடி; காய் மிகுதி; மாமுன் நேர் கூடாது; கனி இல்லை
  function kochagamCheck(r) {
    var L = r.lines;
    if (L.length !== 4 || L.some(function (l) { return l.sirs.length !== 4; })) return null;
    var all = r.flat.map(function (f) { return f.sir; });
    var kaay = all.filter(function (s) { return s.short === 'காய்'; }).length;
    if (kaay * 3 < all.length) return null;
    var issues = [];
    all.forEach(function (s, i) {
      var f = r.flat[i];
      if (s.short === 'கனி') issues.push({ line: f.line, pos: f.pos, soft: true, msg: '“' + s.word + '” கனிச்சீர்; தரவு கொச்சகத்தில் காய், விளம், மா மிகுதி — கனி அரிது.' });
      if (s.next && s.next.name === THALAI.NERONRU.name) issues.push({ line: f.line, pos: f.pos, thalai: true, msg: '“' + s.word + '” மாச்சீர்; அதன் பின் நேர் வருகிறது. “மாஞ்சீர் கலியுட் புகா” — மாவுக்குப் பின் நிரை வேண்டும்.' });
    });
    return { name: 'தரவு கொச்சகக் கலிப்பா', family: 'கலிப்பா', issues: issues };
  }

  function hardCount(c) { return c ? c.issues.filter(function (i) { return !i.soft; }).length : 1e9; }
  var PRI = { 'வெண்பா': 0, 'பாவினம் (கலிப்பா இனம்)': 1, 'பாவினம்': 2, 'கலிப்பா': 3, 'ஆசிரியப்பா': 4 };
  // அலகீடுகளை ஒப்பிட: பிழை குறைவு முதலில், பின் வடிவ முன்னுரிமை
  function score(pa) { return pa ? hardCount(pa) * 10 + (PRI[pa.family] != null ? PRI[pa.family] : 9) : 1e9; }

  function identify(r) {
    if (!r.lines.length) return null;
    var cands = [venbaCheck(r), kattalaiCheck(r), viruttamCheck(r), kochagamCheck(r), asiriyamCheck(r)].filter(Boolean);
    if (!cands.length) {
      return { name: 'இனம் காண இயலவில்லை', family: '', issues: [{ msg: 'அடிகளின் சீர் எண்ணிக்கை எந்த வடிவத்துக்கும் பொருந்தவில்லை. அடிக்கு ஒரு வரியாக, சீர்களை இடைவெளி விட்டு எழுதுங்கள்.' }], candidates: [] };
    }
    // வடிவ அமைப்பு பொருந்தினால் வெண்பாவுக்கு முன்னுரிமை; பிறகு பிழை குறைந்தது
    cands.sort(function (a, b) {
      var d = hardCount(a) - hardCount(b);
      if (d) return d;
      return PRI[a.family] - PRI[b.family];
    });
    var best = cands[0];
    best.ok = hardCount(best) === 0;
    best.candidates = cands.slice(1);
    return best;
  }

  global.Yappu = {
    letters: letters, asaiSplit: asaiSplit, makeSir: makeSir, vaaypaadu: vaaypaadu,
    thalai: thalai, monai: monai, ethukai: ethukai, analyze: analyze, splitWords: splitWords,
    adiName: adiName, ALT: ALT, asVenbaEnd: asVenbaEnd, THALAI: THALAI, NER: NER, NIRAI: NIRAI
  };
})(typeof window !== 'undefined' ? window : this);
