/* குறள் உறியடி · Kural Uriyadi — a Thirukkural game of the village festival.
   A couplet stands on the palm leaf with one word missing; each clay pot (உறி) carries a word. Tap the pot with the right word while it
   hangs low, inside its ring, and the stick breaks it. Text, word lists and translations: Central Institute of Classical Tamil. */
(() => {
'use strict';

const VERSION = '1.0.1';
const LS_KEY = 'kural-uriyadi.v1';
const KURAL_APP = 'https://cictdl.github.io/index.html/kural-app/#/k/';
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = a => a[Math.floor(Math.random() * a.length)];
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const TAU = Math.PI * 2;

// ---------------------------------------------------------------- the words of the interface
const TEXT = {
  ta: {
    tagline: 'குறளில் விடுபட்ட சொல் எந்தப் பானையில்? கம்பால் அடித்து உடையுங்கள்!',
    m_festival: 'திருவிழா ஆட்டம்', m_festival_d: '1,330 குறள்களிலிருந்து · விளக்குகள் அணையும் வரை',
    m_chapters: 'அதிகாரம் வாரியாக', m_chapters_d: '133 அதிகாரங்கள் · ஒவ்வொன்றிலும் பத்துக் குறள்',
    m_k108: '108 குறள்கள்', m_k108_d: 'KTS 5.0 – திருக்குறள் பயில்வோம் திட்டத்தின் 108 குறள்கள்',
    how: 'எப்படி ஆடுவது',
    how_list: ['ஓலையில் ஒரு குறள் தோன்றும்; அதில் ஒரு சொல் விடுபட்டிருக்கும்.',
      'ஒவ்வொரு பானையிலும் ஒரு சொல். சரியான சொல் உள்ள பானையைத் தட்டுங்கள்.',
      'பானை கீழே இறங்கி வளையத்துக்குள் வரும்போது தட்டினால்தான் கம்பு படும்.',
      'தவறான பானையை உடைத்தால் தண்ணீர் கொட்டும்; ஒரு விளக்கு அணையும்.',
      'கண்கட்டுச் சுற்றில் சொற்கள் சில நொடிகளில் மறையும்; நினைவில் வைத்து அடியுங்கள். இரட்டை மதிப்பெண்!'],
    settings: 'அமைப்புகள்', set_ui: 'இடைமுக மொழி', set_tr: 'பொருள் மொழி', set_aid: 'சொல்லின் கீழ் ஒலிப்பு உதவி',
    set_sound: 'ஒலி', set_voice: 'குறளை உரக்கப் படி (கருவியில் தமிழ்க் குரல் இருந்தால்)',
    aid_auto: 'தானாக (பொருள் மொழியின் எழுத்தில்)', aid_off: 'வேண்டாம்', aid_latin: 'ஆங்கில எழுத்தில்',
    best: 'சிறந்த மதிப்பெண்', kural: 'குறள்', score: 'மதிப்பெண்', streak: 'தொடர்', hint: '💡 குறிப்பு',
    blind: 'கண்கட்டுச் சுற்று! சொற்களை நினைவில் வையுங்கள்', miss: 'எட்டவில்லை!', wrong: 'தவறான பானை!', timeup: 'நேரம் முடிந்தது!',
    right: ['அருமை!', 'சரியான சொல்!', 'நன்று!', 'சபாஷ்!'], next: 'தொடரத் தட்டுங்கள்',
    paused: 'இடைநிறுத்தம்', resume: 'தொடர்', quit: 'முகப்புக்குச் செல்', home: 'முகப்பு', again: 'மீண்டும் ஆடு',
    over: 'விளக்குகள் அணைந்தன', over_quit: 'ஆட்டம் முடிந்தது', over_chapter: 'அதிகாரம் நிறைவு!', over_all: 'எல்லாக் குறள்களும் நிறைவு!',
    solved: 'சரியான குறள்கள்', review: 'ஆடிய குறள்கள்', open_app: 'குறள் செயலியில் திற', chapters: 'அதிகாரங்கள்',
    lamps: 'விளக்குகள்', sound_on: 'ஒலி உண்டு', sound_off: 'ஒலி இல்லை', pause: 'இடைநிறுத்து', loading: 'ஏற்றுகிறது…',
    load_fail: 'தரவை ஏற்ற முடியவில்லை. இணைப்பைச் சரிபார்த்து மீண்டும் திறக்கவும்.',
    credits: 'குறள் மூலம், சொற்பிரிப்பு, மொழிபெயர்ப்புகள்: செம்மொழித் தமிழாய்வு மத்திய நிறுவனம் (CICT). குறளின் விடுபட்ட சொல்லைத் தேடும் எண்ணத்துக்குத் தூண்டுதல்: adhavan18, Md-Shameem-Dev ஆகியோரின் மாணவர் படைப்பு “Valluvar\'s Pond”.',
  },
  en: {
    tagline: 'A couplet is missing a word. Which pot carries it? Break it with the stick!',
    m_festival: 'Festival play', m_festival_d: 'From all 1,330 couplets · until the lamps go out',
    m_chapters: 'Chapter by chapter', m_chapters_d: '133 chapters · ten couplets in each',
    m_k108: 'The 108 Thirukkural', m_k108_d: 'The 108 couplets of KTS 5.0 – Thirukkural Payilvom',
    how: 'How to play',
    how_list: ['A couplet appears on the palm leaf with one word missing.',
      'Each pot carries a word. Tap the pot with the right word.',
      'The stick reaches a pot only while it hangs low, inside its ring.',
      'Break a wrong pot and the water comes down: one lamp goes out.',
      'In a blindfold round the words vanish after a few seconds; strike from memory, for double points.'],
    settings: 'Settings', set_ui: 'Interface', set_tr: 'Meaning in', set_aid: 'Reading aid under each word',
    set_sound: 'Sound', set_voice: 'Read the couplet aloud (if the device has a Tamil voice)',
    aid_auto: 'Automatic (script of the meaning)', aid_off: 'None', aid_latin: 'Latin letters',
    best: 'Best score', kural: 'Kural', score: 'Score', streak: 'Streak', hint: '💡 Hint',
    blind: 'Blindfold round! Remember the words', miss: 'Out of reach!', wrong: 'Wrong pot!', timeup: 'Time is up!',
    right: ['Well done!', 'The right word!', 'Good!', 'Sabash!'], next: 'Tap to go on',
    paused: 'Paused', resume: 'Resume', quit: 'Leave the game', home: 'Home', again: 'Play again',
    over: 'The lamps are out', over_quit: 'Game over', over_chapter: 'Chapter complete!', over_all: 'Every couplet done!',
    solved: 'Couplets right', review: 'The couplets you played', open_app: 'Open in the Kural app', chapters: 'Chapters',
    lamps: 'Lamps', sound_on: 'Sound on', sound_off: 'Sound off', pause: 'Pause', loading: 'Loading…',
    load_fail: 'The data could not be loaded. Check the connection and open the game again.',
    credits: 'Couplets, word division and translations: Central Institute of Classical Tamil (CICT). The idea of finding the missing word of a kural was prompted by “Valluvar\'s Pond”, a student project by adhavan18 and Md-Shameem-Dev.',
  },
};
const AID_NAMES = { Devanagari: 'देवनागरी', Bengali: 'বাংলা', Gurmukhi: 'ਗੁਰਮੁਖੀ', Gujarati: 'ગુજરાતી', Oriya: 'ଓଡ଼ିଆ', Telugu: 'తెలుగు',
  Kannada: 'ಕನ್ನಡ', Malayalam: 'മലയാളം' };
const SCRIPT_OF_STREAM = { Devanagari: 'Devanagari', Bengali: 'Bengali', Gurmukhi: 'Gurmukhi', Gujarati: 'Gujarati', Odia: 'Oriya',
  Oriya: 'Oriya', Telugu: 'Telugu', Kannada: 'Kannada', Malayalam: 'Malayalam', Latin: 'Latin', Arabic: 'Latin', 'Meetei Mayek': 'Latin',
  Tamil: 'off' };

// ---------------------------------------------------------------- what the player keeps
const S = { ui: 'en', tr: 'en', aid: 'auto', sound: true, voice: true, best: { festival: 0, k108: 0 }, stars: {} };
function loadState() {
  const nav = (navigator.language || 'en').toLowerCase();
  S.ui = nav.startsWith('ta') ? 'ta' : 'en';
  S.tr = S.ui === 'ta' ? 'tac' : 'en';
  S.navLang = nav.split('-')[0];
  try {
    const saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (saved && typeof saved === 'object') {
      for (const k of ['ui', 'tr', 'aid', 'sound', 'voice']) if (k in saved) S[k] = saved[k];
      Object.assign(S.best, saved.best || {});
      Object.assign(S.stars, saved.stars || {});
      S.saved = true;
    }
  } catch (e) { /* a private window: the game plays without keeping anything */ }
}
function saveState() {
  try { localStorage.setItem(LS_KEY, JSON.stringify({ ui: S.ui, tr: S.tr, aid: S.aid, sound: S.sound, voice: S.voice, best: S.best, stars: S.stars })); }
  catch (e) { /* nothing kept */ }
}
const t = key => (TEXT[S.ui] || TEXT.en)[key] || TEXT.en[key] || key;

// ---------------------------------------------------------------- the data
let META = null, SCRIPTS = {};
const CH = new Map(), TR = new Map();
const json = async url => { const r = await fetch(url); if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); };
async function chapter(n) {
  if (!CH.has(n)) CH.set(n, json(`corpus/ch/${String(n).padStart(3, '0')}.json`).catch(e => { CH.delete(n); throw e; }));
  return CH.get(n);
}
async function translation(code) {
  if (!TR.has(code)) TR.set(code, json(`corpus/tr/${code}.json`).catch(e => { TR.delete(code); throw e; }));
  return TR.get(code);
}
const stream = code => META.streams.find(s => s.code === code) || META.streams.find(s => s.code === 'en');
function aidMode() {
  if (!META) return 'off';
  if (S.aid !== 'auto') return S.aid;
  return SCRIPT_OF_STREAM[stream(S.tr).script] || 'Latin';
}
const LAT_C = { 'க': 'k', 'ங': 'ṅ', 'ச': 'c', 'ஞ': 'ñ', 'ட': 'ṭ', 'ண': 'ṇ', 'த': 't', 'ந': 'n', 'ப': 'p', 'ம': 'm', 'ய': 'y', 'ர': 'r',
  'ல': 'l', 'வ': 'v', 'ழ': 'ḻ', 'ள': 'ḷ', 'ற': 'ṟ', 'ன': 'ṉ', 'ஜ': 'j', 'ஷ': 'ṣ', 'ஸ': 's', 'ஹ': 'h', 'ஶ': 'ś' };
const LAT_V = { 'அ': 'a', 'ஆ': 'ā', 'இ': 'i', 'ஈ': 'ī', 'உ': 'u', 'ஊ': 'ū', 'எ': 'e', 'ஏ': 'ē', 'ஐ': 'ai', 'ஒ': 'o', 'ஓ': 'ō', 'ஔ': 'au', 'ஃ': 'ḵ' };
const LAT_S = { 'ா': 'ā', 'ி': 'i', 'ீ': 'ī', 'ு': 'u', 'ூ': 'ū', 'ெ': 'e', 'ே': 'ē', 'ை': 'ai', 'ொ': 'o', 'ோ': 'ō', 'ௌ': 'au', '்': '' };
/** A Tamil word in Latin letters, letter by letter: for the few words whose reading the data does not give. */
function toLatin(word) {
  const cs = Array.from(word); let out = '';
  for (let i = 0; i < cs.length; i++) {
    const c = cs[i], nx = cs[i + 1];
    if (LAT_C[c]) { out += LAT_C[c]; if (nx in LAT_S) { out += LAT_S[nx]; i++; } else out += 'a'; }
    else if (LAT_V[c]) out += LAT_V[c];
    else if (!(c in LAT_S)) out += c;
  }
  return out.charAt(0).toUpperCase() + out.slice(1);
}
const latinOf = w => w[2] || toLatin(w[0]);
function aidText(w) {          // w = [word, line, Latin, English gloss]
  const mode = aidMode();
  if (mode === 'off') return '';
  const table = SCRIPTS[mode];
  if (mode === 'Latin' || !table) return latinOf(w);
  return Array.from(w[0]).map(c => (table[c] !== undefined ? table[c] : c)).join('');
}
const letters = w => (w.match(/[அ-ஹ]/g) || []).length;      // the vowels and consonants of a Tamil word, not their signs

// ---------------------------------------------------------------- sound, made here: no audio files
const sfx = (() => {
  let ac = null, noiseBuf = null;
  function ctx() {
    if (!S.sound) return null;
    if (!ac) { const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null; try { ac = new AC(); } catch (e) { return null; } }
    if (ac.state === 'suspended') ac.resume().catch(() => {});
    return ac;
  }
  function env(g, at, attack, decay, peak) {
    g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(peak, at + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, at + attack + decay);
  }
  function tone(freq, at, dur, type, peak, slideTo) {
    const o = ac.createOscillator(), g = ac.createGain();
    o.type = type || 'sine'; o.frequency.setValueAtTime(freq, at);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, at + dur);
    env(g, at, 0.008, dur, peak || 0.2); o.connect(g).connect(ac.destination); o.start(at); o.stop(at + dur + 0.08);
  }
  function burst(at, dur, type, f0, f1, peak, q) {
    if (!noiseBuf) {
      noiseBuf = ac.createBuffer(1, Math.floor(ac.sampleRate * 1.2), ac.sampleRate);
      const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    const s = ac.createBufferSource(), f = ac.createBiquadFilter(), g = ac.createGain();
    s.buffer = noiseBuf; f.type = type; f.Q.value = q || 1; f.frequency.setValueAtTime(f0, at); f.frequency.exponentialRampToValueAtTime(f1, at + dur);
    env(g, at, 0.005, dur, peak); s.connect(f).connect(g).connect(ac.destination); s.start(at, Math.random() * 0.5); s.stop(at + dur + 0.08);
  }
  const play = fn => () => { const a = ctx(); if (!a) return; try { fn(a.currentTime); } catch (e) { /* no sound this time */ } };
  return {
    unlock: play(() => {}),
    whoosh: play(at => burst(at, 0.16, 'bandpass', 500, 2400, 0.16, 1.4)),
    crack: play(at => {
      burst(at, 0.2, 'highpass', 900, 3200, 0.45); tone(150, at, 0.16, 'sine', 0.5, 58);
      [1900, 2600, 3300].forEach((f, i) => tone(f * rand(0.9, 1.1), at + 0.02 + i * 0.03, 0.07, 'triangle', 0.07));
    }),
    splash: play(at => { burst(at, 0.55, 'lowpass', 2600, 280, 0.38); burst(at + 0.05, 0.3, 'bandpass', 1200, 500, 0.15, 2); }),
    good: play(at => [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => { tone(f, at + i * 0.085, 0.3, 'triangle', 0.16); tone(f * 2, at + i * 0.085, 0.2, 'sine', 0.05); })),
    bad: play(at => { tone(233, at, 0.18, 'sawtooth', 0.09, 170); tone(165, at + 0.17, 0.32, 'sawtooth', 0.09, 110); }),
    miss: play(at => tone(320, at, 0.13, 'sine', 0.1, 190)),
    drum: play(at => [0, 0.16, 0.32, 0.4].forEach((d, i) => { tone(i % 2 ? 150 : 105, at + d, 0.16, 'sine', 0.5, 55); burst(at + d, 0.04, 'bandpass', 1900, 1300, 0.16, 3); })),
    tick: play(at => tone(900, at, 0.035, 'square', 0.035)),
    fanfare: play(at => [523.25, 587.33, 659.25, 783.99, 880, 1046.5, 880, 1046.5].forEach((f, i) => tone(f, at + i * 0.11, 0.26, 'triangle', 0.15))),
  };
})();

let VOICE = null;
function findVoice() {
  if (!('speechSynthesis' in window)) return null;
  const voices = speechSynthesis.getVoices();
  return voices.find(v => /^ta[-_]IN/i.test(v.lang)) || voices.find(v => /^ta/i.test(v.lang)) || null;
}
function speak(text, onend) {
  if (!S.voice || !S.sound || !VOICE || !('speechSynthesis' in window)) { if (onend) onend(false); return false; }
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text); u.voice = VOICE; u.lang = VOICE.lang; u.rate = 0.9;
    if (onend) { u.onend = () => onend(true); u.onerror = () => onend(false); }
    speechSynthesis.speak(u); return true;
  } catch (e) { if (onend) onend(false); return false; }
}
const hush = () => { try { if ('speechSynthesis' in window) speechSynthesis.cancel(); } catch (e) { /* nothing to stop */ } };

// ---------------------------------------------------------------- the scene
const cv = $('#scene'), g2 = cv.getContext('2d');
let W = 0, H = 0, DPR = 1, bg = null, now = 0;
const geom = { x0: 0, x1: 0, y0: 0, groundY: 0, beamY: 0, potR: 24, tagH: 28, tiers: 1, amp: 40, sw: 100, playerH: 120, px: 0, fs: 16, afs: 10 };
const particles = [], floaters = [];
let stick = null, lastThrow = -9, throwAnim = 9, keysUsed = false;

const G = { on: false, paused: false, mode: 'festival', chapter: 0, queue: [], seen: new Set(), idx: 0, score: 0, lamps: 3, streak: 0, correct: 0, log: [] };
let R = null;         // the round: one couplet

function tuning(level) {
  return {
    pots: clamp(3 + Math.floor((level + 1) / 2), 3, 6),
    period: clamp(3.4 - level * 0.26, 1.75, 3.4),
    thr: clamp(0.2 + level * 0.07, 0.2, 0.58),
    time: clamp(27 - level * 2, 13, 27),
    blind: level >= 2 ? clamp(0.14 + (level - 2) * 0.06, 0, 0.36) : 0,
    hard: level >= 3,
  };
}
const levelNow = () => (G.mode === 'chapter' ? Math.floor(G.idx / 2) : Math.floor(G.correct / 4));

function resize() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  W = cv.clientWidth; H = cv.clientHeight;
  cv.width = Math.max(1, Math.round(W * DPR)); cv.height = Math.max(1, Math.round(H * DPR));
  paintBackground();
  layout();
}

function measure() {
  const hud = $('#hud');
  geom.groundY = H - clamp(H * 0.11, 44, 110);
  geom.x0 = 0; geom.x1 = W; geom.y0 = 0;
  if (!hud.hidden) {
    const r = hud.getBoundingClientRect();
    if (r.width < W * 0.8) geom.x0 = r.right + 4; else geom.y0 = r.bottom;
  }
  const width = geom.x1 - geom.x0, tall = geom.groundY - geom.y0;
  geom.px = (geom.x0 + geom.x1) / 2;
  geom.playerH = clamp(tall * 0.235, 56, 140);
  geom.beamY = geom.y0 + 20;
  geom.potR = clamp(Math.min(width / 9, tall / 10), 16, 30);
  geom.aid = aidMode() !== 'off';
  geom.fs = clamp(geom.potR * 0.7, 14, 19.5);
  geom.afs = Math.max(10, geom.fs * 0.64);
  geom.tagH = Math.round(geom.fs * 1.55 + (geom.aid ? geom.afs * 1.35 : 0));
  geom.V = (geom.groundY - geom.playerH * 1.3 - 6) - (geom.beamY + 12);      // down to the tip of the stick in the hand
  geom.unitH = geom.potR * 2.5 + geom.tagH + 12;
}
/** How many pots this window can hang, and in how many tiers. */
function fit(n) {
  const width = geom.x1 - geom.x0 - 20;
  let count = n, tiers = 1, sw = width / count;
  const twoTiers = geom.V >= 2 * (geom.unitH + 18);
  if (sw < 122 && twoTiers) tiers = 2;
  if (tiers === 1) while (count > 3 && width / count < 112) count--;
  else while (count > 4 && width / count < 68) count--;
  sw = width / count;
  const amp = clamp((geom.V - geom.unitH * tiers - (tiers - 1) * 6) / tiers, 14, 86);
  return { count, tiers, sw, amp };
}
function layout() {
  measure();
  const say = $('#say');
  say.style.left = geom.px + 'px'; say.style.top = (geom.y0 + (geom.groundY - geom.y0) * 0.56) + 'px';
  if (!R) return;
  const f = fit(R.pots.length);
  geom.tiers = f.tiers; geom.sw = f.sw; geom.amp = f.amp;
  const maxW = (f.tiers === 2 ? Math.min(f.sw * 1.86, (geom.x1 - geom.x0) * 0.47) : f.sw * 0.95) - 6;
  // one size of letters for all the words of the round, so that none looks more important
  let fs = geom.fs;
  const widest = () => { g2.font = fontTa(fs); return Math.max(...R.pots.map(p => g2.measureText(p.w[0]).width)); };
  while (fs > 11 && widest() + 18 > maxW) fs -= 0.5;
  R.fs = fs; R.afs = Math.max(9.5, fs * 0.64);
  // the tag as high as its letters ask, and the swing of the pots from the room that is left
  geom.tagH = Math.round(fs * 1.55 + (geom.aid ? R.afs * 1.35 : 0));
  geom.unitH = geom.potR * 2.5 + geom.tagH + 12;
  f.amp = geom.amp = clamp((geom.V - geom.unitH * f.tiers - (f.tiers - 1) * 6) / f.tiers, 14, 86);
  const top0 = geom.beamY + 12 + geom.potR + (f.tiers === 1 ? Math.max(0, (geom.V - geom.unitH - f.amp) * 0.22) : 0);
  R.pots.forEach((p, i) => {
    p.x = geom.x0 + 10 + f.sw * (i + 0.5);
    p.tier = f.tiers === 2 ? i % 2 : 0;
    p.base = top0 + p.tier * (f.amp + geom.unitH + 6);
    p.amp = f.amp;
    g2.font = fontTa(fs); let tw = g2.measureText(p.w[0]).width;
    if (geom.aid) { g2.font = fontAid(R.afs); tw = Math.max(tw, g2.measureText(p.aid).width); }
    p.tw = clamp(tw + 18, 46, maxW + 6);
    p.toff = clamp(p.x, geom.x0 + p.tw / 2 + 5, geom.x1 - p.tw / 2 - 5) - p.x;      // the tag stays inside the window
  });
}
const fontTa = px => `700 ${px}px "Noto Serif Tamil","Noto Sans Tamil","Nirmala UI","Latha",serif`;
const fontAid = px => `500 ${px}px "Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Gurmukhi","Noto Sans Gujarati","Noto Sans Oriya","Noto Sans Telugu","Noto Sans Kannada","Noto Sans Malayalam","Nirmala UI",system-ui,sans-serif`;
const fontUi = (px, weight) => `${weight || 700} ${px}px system-ui,"Segoe UI",Roboto,"Noto Sans Tamil","Nirmala UI",sans-serif`;

// ---- the backdrop, painted once for each size of the window
function paintBackground() {
  bg = document.createElement('canvas'); bg.width = cv.width; bg.height = cv.height;
  const c = bg.getContext('2d'); c.scale(DPR, DPR);
  const gy = H - clamp(H * 0.11, 44, 110);
  let gr = c.createLinearGradient(0, 0, 0, gy);
  gr.addColorStop(0, '#ffeab4'); gr.addColorStop(0.55, '#ffd27c'); gr.addColorStop(1, '#ffb463');
  c.fillStyle = gr; c.fillRect(0, 0, W, gy + 2);
  // the sun, low
  const sx = W * 0.2, sy = gy - Math.min(H * 0.16, 130);
  gr = c.createRadialGradient(sx, sy, 4, sx, sy, Math.min(W, H) * 0.3);
  gr.addColorStop(0, 'rgba(255,250,225,.95)'); gr.addColorStop(0.18, 'rgba(255,240,190,.55)'); gr.addColorStop(1, 'rgba(255,240,190,0)');
  c.fillStyle = gr; c.fillRect(0, 0, W, gy);
  // far hills
  c.fillStyle = 'rgba(214,150,92,.55)'; c.beginPath(); c.moveTo(0, gy);
  for (let x = 0; x <= W; x += 24) c.lineTo(x, gy - 26 - 22 * Math.sin(x * 0.006 + 1) - 12 * Math.sin(x * 0.017));
  c.lineTo(W, gy); c.fill();
  // the temple tower
  const bw = clamp(W * 0.17, 64, 150), bx = W * 0.83, tiers = 6, th = bw * 0.3;
  for (let i = 0; i < tiers; i++) {
    const w0 = bw * (1 - i * 0.125), w1 = bw * (1 - (i + 1) * 0.125), y0 = gy - i * th, y1 = y0 - th;
    c.fillStyle = i % 2 ? 'rgba(190,112,74,.62)' : 'rgba(176,98,62,.66)';
    c.beginPath(); c.moveTo(bx - w0 / 2, y0); c.lineTo(bx + w0 / 2, y0); c.lineTo(bx + w1 / 2, y1); c.lineTo(bx - w1 / 2, y1); c.fill();
    c.fillStyle = 'rgba(255,225,170,.35)'; c.fillRect(bx - w0 / 2, y0 - 3, w0, 2);
    c.fillStyle = 'rgba(90,40,20,.35)'; c.fillRect(bx - w1 * 0.09, y1 + th * 0.3, w1 * 0.18, th * 0.7);
  }
  const topW = bw * (1 - tiers * 0.125), topY = gy - tiers * th;
  c.fillStyle = 'rgba(168,92,58,.7)'; c.beginPath(); c.ellipse(bx, topY, topW * 0.62, th * 0.55, 0, Math.PI, 0); c.fill();
  c.fillStyle = 'rgba(224,170,60,.85)';
  for (const d of [-0.3, 0, 0.3]) { c.beginPath(); c.arc(bx + d * topW, topY - th * 0.62, 2.4, 0, TAU); c.fill(); c.fillRect(bx + d * topW - 0.7, topY - th * 0.62, 1.4, 6); }
  // palms
  const palm = (x, h, lean) => {
    c.strokeStyle = 'rgba(110,78,48,.7)'; c.lineWidth = Math.max(3, h * 0.045); c.lineCap = 'round';
    c.beginPath(); c.moveTo(x, gy + 2); c.quadraticCurveTo(x + lean * 0.4, gy - h * 0.5, x + lean, gy - h); c.stroke();
    c.strokeStyle = 'rgba(74,120,62,.78)'; c.lineWidth = Math.max(2.5, h * 0.03);
    for (let i = 0; i < 8; i++) {
      const a = -Math.PI * 0.94 + i * Math.PI * 0.125 + (i % 2) * 0.05, len = h * (0.3 + 0.07 * ((i * 3) % 4));
      c.beginPath(); c.moveTo(x + lean, gy - h);
      c.quadraticCurveTo(x + lean + Math.cos(a) * len * 0.6, gy - h + Math.sin(a) * len * 0.75 - len * 0.22, x + lean + Math.cos(a) * len, gy - h + Math.sin(a) * len * 0.45 + len * 0.2);
      c.stroke();
    }
  };
  const ph = clamp(H * 0.3, 110, 260);
  palm(W * 0.07, ph, 14); palm(W * 0.14, ph * 0.74, -10); palm(W * 0.955, ph * 0.86, -16);
  if (W > 700) { palm(W * 0.34, ph * 0.6, 8); palm(W * 0.62, ph * 0.68, -9); }
  // the ground of the street
  gr = c.createLinearGradient(0, gy, 0, H); gr.addColorStop(0, '#dba05a'); gr.addColorStop(1, '#b6763a');
  c.fillStyle = gr; c.fillRect(0, gy, W, H - gy);
  c.fillStyle = 'rgba(120,70,30,.25)'; c.fillRect(0, gy, W, 2);
  for (let i = 0; i < 40; i++) { c.fillStyle = `rgba(110,66,30,${rand(0.08, 0.2)})`; c.beginPath(); c.ellipse(rand(0, W), rand(gy + 6, H), rand(2, 7), rand(1, 2.4), 0, 0, TAU); c.fill(); }
}
/** The kolam at the player's feet, drawn each frame under the player (the window may be split between leaf and pots). */
function drawKolam(x, y, r) {
  g2.save(); g2.translate(x, y); g2.scale(1, 0.34);
  g2.strokeStyle = 'rgba(255,255,255,.9)'; g2.fillStyle = 'rgba(255,255,255,.9)'; g2.lineWidth = 2.2;
  for (let i = 0; i < 8; i++) {
    g2.save(); g2.rotate(i * TAU / 8);
    g2.beginPath(); g2.ellipse(r * 0.52, 0, r * 0.46, r * 0.2, 0, 0, TAU); g2.stroke();
    g2.beginPath(); g2.arc(r * 1.02, 0, 2.6, 0, TAU); g2.fill();
    g2.restore();
  }
  g2.beginPath(); g2.arc(0, 0, r * 0.16, 0, TAU); g2.stroke();
  g2.beginPath(); g2.arc(0, 0, 3, 0, TAU); g2.fill();
  g2.restore();
}

function roundRect(x, y, w, h, r) {
  g2.beginPath(); g2.moveTo(x + r, y); g2.arcTo(x + w, y, x + w, y + h, r); g2.arcTo(x + w, y + h, x, y + h, r);
  g2.arcTo(x, y + h, x, y, r); g2.arcTo(x, y, x + w, y, r); g2.closePath();
}

// ---- the poles, the rope with its festoon of mango leaves and marigolds
function drawRig() {
  const xa = geom.x0 + 9, xb = geom.x1 - 9, y = geom.beamY;
  for (const x of [xa, xb]) {
    const gr = g2.createLinearGradient(x - 5, 0, x + 5, 0); gr.addColorStop(0, '#b8892f'); gr.addColorStop(0.5, '#e6c067'); gr.addColorStop(1, '#a87a26');
    g2.fillStyle = gr; g2.fillRect(x - 5, y - 12, 10, geom.groundY - y + 14);
    g2.fillStyle = 'rgba(110,74,20,.55)'; for (let yy = y + 26; yy < geom.groundY; yy += 46) g2.fillRect(x - 5, yy, 10, 2);
    g2.fillStyle = '#c0261c'; g2.beginPath(); g2.moveTo(x, y - 12); g2.lineTo(x + (x === xa ? 22 : -22), y - 20); g2.lineTo(x, y - 28); g2.fill();
    g2.fillStyle = '#8a5a12'; g2.fillRect(x - 1, y - 30, 2, 20);
  }
  g2.strokeStyle = '#7a5226'; g2.lineWidth = 3; g2.beginPath(); g2.moveTo(xa, y); g2.quadraticCurveTo((xa + xb) / 2, y + 7, xb, y); g2.stroke();
  const n = Math.max(6, Math.floor((xb - xa) / 20));
  for (let i = 1; i < n; i++) {
    const u = i / n, x = lerp(xa, xb, u), yy = y + 7 * 4 * u * (1 - u) * 0.5 + 1, sway = Math.sin(now * 1.6 + i) * 1.2;
    if (i % 4 === 0) {       // a marigold
      g2.fillStyle = '#f59a1b'; g2.beginPath(); g2.arc(x, yy + 5, 4.2, 0, TAU); g2.fill();
      g2.fillStyle = '#ffd04a'; g2.beginPath(); g2.arc(x, yy + 5, 2, 0, TAU); g2.fill();
    } else {                 // a mango leaf
      g2.fillStyle = i % 2 ? '#3f8a3c' : '#2f7434';
      g2.beginPath(); g2.moveTo(x - 3.2, yy); g2.quadraticCurveTo(x + sway - 4.5, yy + 9, x + sway, yy + 17); g2.quadraticCurveTo(x + sway + 4.5, yy + 9, x + 3.2, yy); g2.fill();
    }
  }
}

// ---- a pot with its rope, its sling and the tag of its word
const potF = p => 0.5 - 0.5 * Math.cos(p.phase);
function potPos(p) {
  const appear = clamp((now - R.t0 - p.delay) / 0.45, 0, 1), e = 1 - Math.pow(1 - appear, 3);
  const y = p.base + p.amp * potF(p), sway = Math.sin(p.phase * 0.5 + p.seed) * 3;
  return { x: p.x + sway, y: lerp(geom.beamY - geom.potR, y, e), alpha: appear };
}
const reachable = p => potF(p) >= R.thr;
const hiddenNow = () => R.blind && R.state === 'play' && now > R.showUntil;

/** The ropes from the beam, under every pot and tag. */
function drawRope(p) {
  const pos = potPos(p);
  g2.globalAlpha = pos.alpha; g2.strokeStyle = '#7a5226'; g2.lineWidth = 2;
  g2.beginPath(); g2.moveTo(p.x, geom.beamY + 3); g2.lineTo(pos.x, pos.y - geom.potR * 1.5); g2.stroke(); g2.globalAlpha = 1;
}
function drawPot(p) {
  const r = geom.potR, pos = potPos(p), x = pos.x, y = pos.y;
  g2.globalAlpha = pos.alpha;
  if (!p.alive) {        // broken: the sling hangs empty
    g2.strokeStyle = '#7a5226'; g2.lineWidth = 1.5;
    for (const d of [-1, 0, 1]) { g2.beginPath(); g2.moveTo(x, y - r * 1.5); g2.quadraticCurveTo(x + d * r * 0.5, y - r * 0.8, x + d * r * 0.35 + Math.sin(now * 3 + d) * 2, y - r * 0.1); g2.stroke(); }
    g2.globalAlpha = 1; return;
  }
  const can = R.state === 'play' && reachable(p), glow = (R.state !== 'play' && p.right) || can;
  if (glow) {
    g2.save(); g2.shadowColor = p.right && R.state === 'lost' ? 'rgba(255,214,60,1)' : 'rgba(255,226,120,.95)'; g2.shadowBlur = 16;
    g2.fillStyle = 'rgba(255,226,120,.55)'; g2.beginPath(); g2.arc(x, y, r * 1.02, 0, TAU); g2.fill(); g2.restore();
  }
  // the body
  const gr = g2.createRadialGradient(x - r * 0.35, y - r * 0.35, r * 0.15, x, y, r * 1.1);
  gr.addColorStop(0, '#dd7a42'); gr.addColorStop(0.6, '#b9562b'); gr.addColorStop(1, '#8a3a18');
  g2.fillStyle = gr; g2.beginPath(); g2.ellipse(x, y + r * 0.06, r, r * 0.92, 0, 0, TAU); g2.fill();
  // the neck and the rim
  g2.fillStyle = '#a84a22'; g2.fillRect(x - r * 0.42, y - r * 1.02, r * 0.84, r * 0.3);
  g2.fillStyle = '#c96a36'; g2.beginPath(); g2.ellipse(x, y - r * 1.02, r * 0.56, r * 0.17, 0, 0, TAU); g2.fill();
  g2.fillStyle = '#5c2410'; g2.beginPath(); g2.ellipse(x, y - r * 1.02, r * 0.4, r * 0.1, 0, 0, TAU); g2.fill();
  // lime lines and dots
  g2.strokeStyle = 'rgba(255,248,230,.92)'; g2.lineWidth = Math.max(1.4, r * 0.07);
  g2.beginPath(); g2.ellipse(x, y - r * 0.28, r * 0.9, r * 0.2, 0, 0.12 * Math.PI, 0.88 * Math.PI); g2.stroke();
  g2.fillStyle = 'rgba(255,248,230,.95)';
  for (let i = -2; i <= 2; i++) { g2.beginPath(); g2.arc(x + i * r * 0.34, y + r * 0.2 + (2 - Math.abs(i)) * r * 0.07, Math.max(1.5, r * 0.075), 0, TAU); g2.fill(); }
  g2.fillStyle = '#c0261c'; g2.beginPath(); g2.arc(x, y + r * 0.56, Math.max(2, r * 0.1), 0, TAU); g2.fill();
  // the sling of rope
  g2.strokeStyle = 'rgba(92,60,26,.9)'; g2.lineWidth = 1.4;
  for (const d of [-1, 1]) { g2.beginPath(); g2.moveTo(x, y - r * 1.5); g2.quadraticCurveTo(x + d * r * 1.12, y - r * 0.5, x + d * r * 0.72, y + r * 0.7); g2.stroke(); }
  g2.beginPath(); g2.moveTo(x, y - r * 1.5); g2.lineTo(x, y - r * 1.1); g2.stroke();
  // the tag
  const tw = p.tw, th = geom.tagH, tc = x + (p.toff || 0), tx = tc - tw / 2, ty = y + r + 8, hidden = hiddenNow();
  g2.strokeStyle = 'rgba(92,60,26,.85)'; g2.lineWidth = 1;
  g2.beginPath(); g2.moveTo(x - r * 0.3, y + r * 0.86); g2.lineTo(clamp(x - r * 0.42, tx + 5, tx + tw - 5), ty); g2.moveTo(x + r * 0.3, y + r * 0.86); g2.lineTo(clamp(x + r * 0.42, tx + 5, tx + tw - 5), ty); g2.stroke();
  roundRect(tx, ty, tw, th, 7);
  g2.fillStyle = hidden ? '#3b2a6b' : (p.right && R.state === 'won' ? '#e4f4d6' : '#fff6dd'); g2.fill();
  g2.strokeStyle = can ? '#e0a01a' : (hidden ? '#221546' : '#8a5a2b'); g2.lineWidth = can ? 2.6 : 1.3; g2.stroke();
  g2.textAlign = 'center'; g2.textBaseline = 'middle';
  if (hidden) {
    g2.fillStyle = '#fff'; g2.font = fontUi(R.fs, 800); g2.fillText('?', tc, ty + th / 2 + 1);
  } else {
    g2.fillStyle = '#3a2413'; g2.font = fontTa(R.fs);
    const mid = geom.aid ? ty + R.fs * 0.82 : ty + th / 2 + 1;
    g2.fillText(p.w[0], tc, mid, tw - 8);
    if (geom.aid && p.aid) { g2.fillStyle = '#7a5a3a'; g2.font = fontAid(R.afs); g2.fillText(p.aid, tc, ty + th - R.afs * 0.78, tw - 8); }
  }
  if (keysUsed) {
    g2.fillStyle = 'rgba(58,36,19,.85)'; g2.beginPath(); g2.arc(x + r * 0.95, y - r * 0.95, 9, 0, TAU); g2.fill();
    g2.fillStyle = '#fff'; g2.font = fontUi(11, 700); g2.fillText(String(p.key), x + r * 0.95, y - r * 0.95 + 0.5);
  }
  g2.globalAlpha = 1;
  p.box = { x0: Math.min(tx, x - r) - 8, x1: Math.max(tx + tw, x + r) + 8, y0: y - r * 1.2 - 6, y1: ty + th + 8, cx: x, cy: y };
}
/** The ring where the stick lands: a pot inside it can be hit. */
function drawRing(p) {
  if (!p.alive || R.state !== 'play') return;
  const yLow = p.base + p.amp, yIn = p.base + p.amp * R.thr, r = geom.potR, can = reachable(p);
  g2.save(); g2.setLineDash([5, 5]); g2.lineWidth = 1.6; g2.strokeStyle = can ? 'rgba(255,255,255,.95)' : 'rgba(255,255,255,.5)';
  roundRect(p.x - r * 1.28, yIn - r * 1.15, r * 2.56, yLow - yIn + r * 2.25, r * 1.2); g2.stroke(); g2.restore();
}

// ---- the player, seen from behind, blindfolded as the game of the festival asks
function handPoint() { return { x: geom.px + geom.playerH * 0.2, y: geom.groundY + 6 - geom.playerH * 1.02 }; }
function drawPlayer() {
  const h = geom.playerH, x = geom.px, y = geom.groundY + 6;
  drawKolam(x, y + Math.min(26, (H - y) * 0.5), clamp(h * 0.5, 36, 74));
  g2.fillStyle = 'rgba(70,40,15,.25)'; g2.beginPath(); g2.ellipse(x, y + 2, h * 0.24, h * 0.05, 0, 0, TAU); g2.fill();
  const swing = throwAnim < 0.3 ? Math.sin(throwAnim / 0.3 * Math.PI) : 0;
  const skin = '#8d5a3b';
  // feet and the white veshti with its border
  g2.fillStyle = skin; g2.fillRect(x - h * 0.13, y - h * 0.03, h * 0.09, h * 0.035); g2.fillRect(x + h * 0.04, y - h * 0.03, h * 0.09, h * 0.035);
  g2.fillStyle = '#fffdf4'; g2.beginPath(); g2.moveTo(x - h * 0.15, y - h * 0.47); g2.lineTo(x + h * 0.15, y - h * 0.47); g2.lineTo(x + h * 0.185, y - h * 0.03); g2.lineTo(x - h * 0.185, y - h * 0.03); g2.fill();
  g2.fillStyle = '#c8962e'; g2.fillRect(x - h * 0.185, y - h * 0.065, h * 0.37, h * 0.025);
  g2.fillStyle = '#7a2e12'; g2.fillRect(x - h * 0.185, y - h * 0.04, h * 0.37, h * 0.012);
  // the far arm, out for balance
  g2.strokeStyle = skin; g2.lineWidth = h * 0.062; g2.lineCap = 'round';
  g2.beginPath(); g2.moveTo(x - h * 0.15, y - h * 0.71); g2.lineTo(x - h * 0.27, y - h * (0.56 + swing * 0.05)); g2.stroke();
  // the shirt
  g2.fillStyle = '#1f7a6d'; roundRect(x - h * 0.17, y - h * 0.76, h * 0.34, h * 0.32, h * 0.06); g2.fill();
  g2.fillStyle = '#c0261c'; g2.fillRect(x - h * 0.17, y - h * 0.49, h * 0.34, h * 0.035);
  // the head, the hair, the blindfold with its knot
  g2.fillStyle = skin; g2.fillRect(x - h * 0.035, y - h * 0.8, h * 0.07, h * 0.06);
  g2.fillStyle = '#1c1410'; g2.beginPath(); g2.arc(x, y - h * 0.885, h * 0.105, 0, TAU); g2.fill();
  g2.fillStyle = skin; g2.beginPath(); g2.arc(x - h * 0.105, y - h * 0.875, h * 0.022, 0, TAU); g2.arc(x + h * 0.105, y - h * 0.875, h * 0.022, 0, TAU); g2.fill();
  g2.fillStyle = '#d63a2a'; g2.fillRect(x - h * 0.108, y - h * 0.915, h * 0.216, h * 0.042);
  g2.beginPath(); g2.arc(x, y - h * 0.894, h * 0.028, 0, TAU); g2.fill();
  g2.strokeStyle = '#d63a2a'; g2.lineWidth = h * 0.026;
  const fl = Math.sin(now * 4) * h * 0.012;
  g2.beginPath(); g2.moveTo(x, y - h * 0.894); g2.quadraticCurveTo(x + h * 0.03 + fl, y - h * 0.84, x + h * 0.012 + fl, y - h * 0.79); g2.stroke();
  g2.beginPath(); g2.moveTo(x, y - h * 0.894); g2.quadraticCurveTo(x - h * 0.035 + fl, y - h * 0.85, x - h * 0.04 + fl, y - h * 0.805); g2.stroke();
  // the arm that throws
  const hp = handPoint(), hx = hp.x - swing * h * 0.1, hy = hp.y + swing * h * 0.2;
  g2.strokeStyle = skin; g2.lineWidth = h * 0.062;
  g2.beginPath(); g2.moveTo(x + h * 0.15, y - h * 0.71); g2.quadraticCurveTo(x + h * 0.3, y - h * 0.82, hx, hy); g2.stroke();
  // the stick in the hand, once it is back
  if (now - lastThrow > 0.34) drawStick(hx + h * 0.04, hy - h * 0.1, -0.5 + Math.sin(now * 2) * 0.05, h * 0.62);
}
function drawStick(x, y, angle, len) {
  g2.save(); g2.translate(x, y); g2.rotate(angle);
  g2.strokeStyle = '#8a6420'; g2.lineWidth = 6.5; g2.lineCap = 'round'; g2.beginPath(); g2.moveTo(0, -len / 2); g2.lineTo(0, len / 2); g2.stroke();
  g2.strokeStyle = '#dcb65c'; g2.lineWidth = 4; g2.beginPath(); g2.moveTo(0, -len / 2); g2.lineTo(0, len / 2); g2.stroke();
  g2.strokeStyle = 'rgba(120,84,24,.7)'; g2.lineWidth = 1.2;
  for (const u of [-0.25, 0.05, 0.3]) { g2.beginPath(); g2.moveTo(-2.4, len * u); g2.lineTo(2.4, len * u); g2.stroke(); }
  g2.restore();
}

// ---- what flies: shards, water, petals, and the points won
function shards(x, y, r) {
  for (let i = 0; i < 16; i++) particles.push({ kind: 'shard', x: x + rand(-r, r) * 0.5, y: y + rand(-r, r) * 0.5, vx: rand(-190, 190), vy: rand(-260, 40), g: 720, life: rand(0.6, 1.1), age: 0, size: rand(4, 10), rot: rand(0, TAU), vr: rand(-9, 9), color: pick(['#b9562b', '#8a3a18', '#dd7a42', '#a84a22']) });
}
function water(x, y) {
  for (let i = 0; i < 46; i++) particles.push({ kind: 'drop', x: x + rand(-14, 14), y: y + rand(-6, 10), vx: rand(-110, 110), vy: rand(-140, 160), g: 900, life: rand(0.6, 1.2), age: 0, size: rand(2.2, 5), color: pick(['#58b6e8', '#8fd3f4', '#3f9bd6', '#c5ecff']) });
}
function petals(x, y) {
  for (let i = 0; i < 46; i++) particles.push({ kind: 'petal', x: x + rand(-10, 10), y: y + rand(-10, 10), vx: rand(-170, 170), vy: rand(-300, -40), g: 300, life: rand(1.0, 1.9), age: 0, size: rand(3, 6.5), rot: rand(0, TAU), vr: rand(-5, 5), color: pick(['#f59a1b', '#ffd04a', '#f2536b', '#fff3c4', '#ff7a2f']) });
}
function floater(x, y, text, color) { floaters.push({ x, y, text, color: color || '#fff', age: 0, life: 1.1 }); }
function drawParticles(dt) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]; p.age += dt;
    if (p.age >= p.life || p.y > H + 20) { particles.splice(i, 1); continue; }
    p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt;
    if (p.kind === 'petal') { p.vx *= 1 - 1.6 * dt; p.vy = Math.min(p.vy, 110); p.x += Math.sin(p.age * 6 + p.rot) * 22 * dt; }
    if (p.rot !== undefined) p.rot += (p.vr || 0) * dt;
    g2.globalAlpha = clamp((p.life - p.age) / 0.35, 0, 1); g2.fillStyle = p.color;
    if (p.kind === 'shard') { g2.save(); g2.translate(p.x, p.y); g2.rotate(p.rot); g2.beginPath(); g2.moveTo(-p.size, -p.size * 0.5); g2.lineTo(p.size, -p.size * 0.2); g2.lineTo(0, p.size * 0.8); g2.fill(); g2.restore(); }
    else if (p.kind === 'petal') { g2.save(); g2.translate(p.x, p.y); g2.rotate(p.rot); g2.beginPath(); g2.ellipse(0, 0, p.size, p.size * 0.55, 0, 0, TAU); g2.fill(); g2.restore(); }
    else { g2.beginPath(); g2.ellipse(p.x, p.y, p.size * 0.7, p.size, 0, 0, TAU); g2.fill(); }
  }
  g2.globalAlpha = 1;
  for (let i = floaters.length - 1; i >= 0; i--) {
    const f = floaters[i]; f.age += dt;
    if (f.age >= f.life) { floaters.splice(i, 1); continue; }
    g2.globalAlpha = clamp((f.life - f.age) / 0.4, 0, 1); g2.font = fontUi(22, 800); g2.textAlign = 'center'; g2.textBaseline = 'middle';
    g2.lineWidth = 4; g2.strokeStyle = 'rgba(58,36,19,.85)'; g2.strokeText(f.text, f.x, f.y - f.age * 46); g2.fillStyle = f.color; g2.fillText(f.text, f.x, f.y - f.age * 46);
  }
  g2.globalAlpha = 1;
}

// ---------------------------------------------------------------- the frame
let last = 0;
function frame(ms) {
  const tNow = ms / 1000, dt = clamp(tNow - last, 0, 0.05); last = tNow;
  const live = G.on && !G.paused;
  if (live || !G.on) now += dt;
  if (live && R) update(dt);
  render(live ? dt : 0);
  requestAnimationFrame(frame);
}
function render(dt) {
  g2.setTransform(DPR, 0, 0, DPR, 0, 0);
  if (bg) g2.drawImage(bg, 0, 0, W, H);
  if (G.on && R) {
    drawRig();
    for (const p of R.pots) drawRing(p);
    for (const p of R.pots) drawRope(p);
    for (const p of R.pots) drawPot(p);
    drawPlayer();
    if (stick) drawStick(stick.x, stick.y, stick.rot, geom.playerH * 0.5);
    drawParticles(dt);
  }
}

function update(dt) {
  throwAnim += dt;
  for (const p of R.pots) p.phase += p.speed * dt;
  if (stick) {
    stick.t += dt; stick.rot += stick.vr * dt;
    if (!stick.done) {
      const u = clamp(stick.t / stick.dur, 0, 1), e = 1 - (1 - u) * (1 - u);
      stick.x = lerp(stick.from.x, stick.to.x, e); stick.y = lerp(stick.from.y, stick.to.y, e) - Math.sin(u * Math.PI) * 14;
      if (u >= 1) { stick.done = true; landed(stick); }
    } else {
      stick.vy += 900 * dt; stick.x += stick.vx * dt; stick.y += stick.vy * dt;
      if (stick.y > H + 60) stick = null;
    }
  }
  if (R.state === 'play') {
    R.timeLeft -= dt;
    const frac = clamp(R.timeLeft / R.timeMax, 0, 1);
    timerBar.style.transform = `scaleX(${frac.toFixed(4)})`;
    timerBox.classList.toggle('low', R.timeLeft < 6);
    if (R.timeLeft < 5 && Math.floor(R.timeLeft) !== R.lastTick) { R.lastTick = Math.floor(R.timeLeft); sfx.tick(); }
    if (R.blind && !R.hiddenSaid && now > R.showUntil) { R.hiddenSaid = true; renderKeys(); }
    if (R.timeLeft <= 0) timeUp();
  } else if (R.until && now >= R.until) {
    const then = R.then; R.until = 0; R.then = null; if (then) then();
  }
}
const timerBar = $('#timer-bar'), timerBox = $('.timer');

// ---------------------------------------------------------------- one couplet
function chooseBlank(k) {
  const all = k.w.map((w, i) => i), long = all.filter(i => letters(k.w[i][0]) >= 3);
  return pick(long.length ? long : all);
}
function decoys(k, ch, blank, count, hard) {
  const answer = k.w[blank][0], own = new Set(k.w.map(w => w[0])), last = blank === k.w.length - 1, line = k.w[blank][1];
  const found = new Map();
  for (const other of ch.kurals) {
    if (other.n === k.n) continue;
    other.w.forEach((w, i) => {
      if (own.has(w[0])) return;
      let score = Math.abs(letters(w[0]) - letters(answer));
      if ((i === other.w.length - 1) !== last) score += 2.5;       // the last foot of a kural has a shape of its own
      if (w[1] !== line) score += 0.4;
      if (hard) { if (w[0][0] === answer[0]) score -= 1.3; if (w[0].slice(-1) === answer.slice(-1)) score -= 0.7; }
      score += Math.random() * 1.3;
      if (!found.has(w[0]) || found.get(w[0]).score > score) found.set(w[0], { w, score });
    });
  }
  return [...found.values()].sort((a, b) => a.score - b.score).slice(0, count).map(f => f.w);
}

async function startRound() {
  const n = G.queue[G.idx];
  const chNo = Math.ceil(n / 10);
  let ch, tr;
  try { [ch, tr] = await Promise.all([chapter(chNo), translation(S.tr)]); }
  catch (e) { say(t('load_fail'), 'bad', 4); endGame('fail'); return; }
  if (!G.on) return;
  const k = ch.kurals.find(q => q.n === n);
  const after = G.queue[G.idx + 1]; if (after) chapter(Math.ceil(after / 10)).catch(() => {});      // the next one, ready
  const tune = tuning(levelNow());
  measure();
  const count = fit(tune.pots).count;
  const blank = chooseBlank(k);
  const options = shuffle([k.w[blank], ...decoys(k, ch, blank, count - 1, tune.hard)]);
  const blind = Math.random() < tune.blind;
  R = {
    k, n, chNo, blank, answer: k.w[blank], tr: tr[String(n)] || ['', ''], state: 'play', t0: now, thr: tune.thr,
    timeMax: tune.time + (blind ? 4 : 0), timeLeft: tune.time + (blind ? 4 : 0), lastTick: -1, blind, showUntil: now + 0.5 + 3.2 + options.length * 0.35,
    hintUsed: false, mistakes: 0, until: 0, then: null, fs: 16, afs: 10,
    pots: options.map((w, i) => ({ w, aid: aidText(w), right: w === k.w[blank], alive: true, key: i + 1, phase: rand(0, TAU), seed: rand(0, TAU),
      speed: TAU / (tune.period * rand(0.86, 1.16)), delay: i * 0.07, x: 0, base: 0, amp: 0, tier: 0, tw: 60, box: null })),
  };
  // not every pot low at the start: the right one begins high, so the first tap is a choice and not a reflex
  const right = R.pots.find(p => p.right); right.phase = rand(-0.5, 0.5);
  renderLeaf(); renderHud(); layout(); renderKeys();
  timerBar.style.transform = 'scaleX(1)'; timerBox.classList.remove('low');
  if (blind) say(t('blind'), 'blind', 2.2);
}

function renderLeaf() {
  const k = R.k, ch = META.chapters[R.chNo - 1];
  $('#leaf-where').textContent = `${t('kural')} ${k.n} · ${ch.ta}` + (S.ui === 'en' ? ` · ${ch.en}` : '');
  let at = 0;
  [0, 1].forEach(li => {
    const el = $('#leaf-l' + (li + 1)); el.textContent = '';
    k.l[li].split(' ').forEach((tok, j) => {
      if (j) el.append(' ');
      if (at === R.blank) {
        const m = tok.match(/^(.*?)([.?!,;:]*)$/), b = document.createElement('span');
        b.className = 'blank'; b.id = 'blank'; b.textContent = m[1]; b.setAttribute('aria-hidden', 'true');
        el.append(b); if (m[2]) el.append(m[2]);
      } else el.append(tok);
      at++;
    });
  });
  const s = stream(S.tr), m = $('#leaf-meaning');
  m.textContent = R.tr.filter(Boolean).join(' '); m.dir = s.dir || 'ltr'; m.lang = s.code === 'tac' ? 'ta' : s.code; m.classList.remove('open');
  const hint = $('#leaf-hint'); hint.hidden = true; hint.textContent = '';
  const hb = $('#btn-hint'); hb.disabled = false; hb.textContent = t('hint');
  fitLeaf();
}
/** Each line of the couplet on one row: the letters as large as the leaf allows. */
function fitLeaf() {
  const lines = [$('#leaf-l1'), $('#leaf-l2')];
  let px = clamp(Math.min(window.innerWidth, 900) * 0.052, 15, 25);
  for (const el of lines) { el.classList.remove('wrap'); el.style.fontSize = px + 'px'; }
  while (px > 11.5 && lines.some(el => el.scrollWidth > el.clientWidth + 1)) { px -= 0.5; for (const el of lines) el.style.fontSize = px + 'px'; }
  // a leaf too narrow even for the smallest letters: the line may break
  for (const el of lines) if (el.scrollWidth > el.clientWidth + 1) el.classList.add('wrap');
}
function renderHud() {
  const lamps = $('#lamps'); lamps.textContent = ''; lamps.setAttribute('aria-label', `${t('lamps')}: ${G.lamps}`);
  for (let i = 0; i < 3; i++) { const s = document.createElement('span'); s.textContent = '🪔'; if (i >= G.lamps) s.className = 'out'; lamps.append(s); }
  $('#score').textContent = G.score; $('#score-lbl').textContent = t('score');
  const st = $('#streak'); st.hidden = G.streak < 2; st.textContent = `🔥 ×${G.streak}`; st.setAttribute('aria-label', `${t('streak')}: ${G.streak}`);
  const total = G.mode === 'festival' ? '' : ` / ${G.queue.length}`;
  $('#round').textContent = `${G.idx + 1}${total}`;
  $('#btn-sound').textContent = S.sound ? '🔊' : '🔇'; $('#btn-sound').setAttribute('aria-label', S.sound ? t('sound_on') : t('sound_off'));
  $('#btn-pause').textContent = '⏸'; $('#btn-pause').setAttribute('aria-label', t('pause'));
}
/** The words as buttons for the keyboard and for screen readers: activating one strikes without the timing. */
function renderKeys() {
  const box = $('#keys'); box.textContent = '';
  if (!R || R.state !== 'play') return;
  const hidden = hiddenNow();
  R.pots.filter(p => p.alive).forEach(p => {
    const b = document.createElement('button'); b.type = 'button'; b.lang = 'ta';
    b.textContent = hidden ? `${p.key}: ?` : `${p.key}: ${p.w[0]}`;
    b.addEventListener('click', () => strike(p, true));
    box.append(b);
  });
}

let sayTimer = 0;
function say(text, kind, secs) {
  const el = $('#say'); el.textContent = text; el.className = 'say on ' + (kind || '');
  clearTimeout(sayTimer); sayTimer = setTimeout(() => { el.className = 'say ' + (kind || ''); }, (secs || 1.1) * 1000);
}

function strike(p, sure) {
  if (!G.on || G.paused || !R || R.state !== 'play' || !p.alive) return;
  if (now - lastThrow < 0.34 || (stick && !stick.done)) return;
  sfx.unlock();
  const pos = potPos(p), hit = sure || reachable(p), from = handPoint();
  const to = hit ? { x: pos.x, y: pos.y } : { x: p.x, y: p.base + p.amp * 0.92 };
  stick = { from, to, x: from.x, y: from.y, t: 0, dur: 0.17, rot: 0, vr: 26, pot: p, hit, done: false, vx: 0, vy: 0 };
  lastThrow = now; throwAnim = 0; sfx.whoosh();
}
function landed(s) {
  const p = s.pot;
  s.vx = (s.to.x - s.from.x) * 0.9 + rand(-40, 40); s.vy = s.hit ? -160 : -320; s.vr = rand(-14, 14);
  if (R.state !== 'play') return;
  if (!s.hit) { sfx.miss(); say(t('miss'), '', 0.8); R.timeLeft -= 1.5; return; }
  if (p.right) return won(p, s.to);
  // a wrong pot: the water comes down
  p.alive = false; R.mistakes++; G.lamps--; G.streak = 0;
  sfx.crack(); sfx.splash(); sfx.bad(); shards(s.to.x, s.to.y, geom.potR); water(s.to.x, s.to.y);
  say(t('wrong'), 'bad', 1); renderHud(); renderKeys();
  if (R.blind) R.showUntil = now + 1.6, R.hiddenSaid = false;
  if (navigator.vibrate) try { navigator.vibrate(80); } catch (e) { /* no vibration */ }
  if (G.lamps <= 0) reveal(() => endGame('out'));
}
function won(p, at) {
  R.state = 'won';
  const mult = Math.min(5, 1 + Math.floor((G.streak + 1) / 3));
  let pts = (10 + Math.ceil(clamp(R.timeLeft / R.timeMax, 0, 1) * 10)) * mult;
  if (R.blind) pts *= 2;
  if (R.hintUsed) pts = Math.ceil(pts / 2);
  G.score += pts; G.streak++; G.correct++;
  p.alive = false;
  sfx.crack(); sfx.good(); shards(at.x, at.y, geom.potR); petals(at.x, at.y); floater(at.x, at.y - geom.potR, '+' + pts, '#ffe27a');
  const b = $('#blank'); if (b) { b.classList.add('filled'); b.removeAttribute('aria-hidden'); fitLeaf(); }
  say(pick(t('right')), 'good', 1.1);
  G.log.push({ n: R.n, ok: true, blank: R.blank });
  renderHud(); $('#keys').textContent = '';
  const go = () => { if (R && R.state === 'won') nextRound(); };
  const spoken = speak(R.k.l.join(' '), () => { if (R && R.state === 'won') { R.until = now + 0.5; R.then = go; } });
  R.until = now + (spoken ? 9 : 2.1); R.then = go;
}
function reveal(then) {
  R.state = 'lost';
  const b = $('#blank'); if (b) { b.classList.add('shown'); b.removeAttribute('aria-hidden'); fitLeaf(); }
  if (!G.log.length || G.log[G.log.length - 1].n !== R.n) G.log.push({ n: R.n, ok: false, blank: R.blank });
  $('#keys').textContent = '';
  R.until = now + 2.4; R.then = then;
}
function timeUp() {
  G.lamps--; G.streak = 0; sfx.bad(); say(t('timeup'), 'bad', 1.2); renderHud();
  reveal(() => (G.lamps <= 0 ? endGame('out') : nextRound()));
}
function nextRound() {
  hush();
  G.idx++;
  if (G.mode === 'festival') G.queue.push(freshKural());      // always one ahead
  else if (G.idx >= G.queue.length) return endGame('done');
  startRound();
}
function freshKural() {
  let n; do { n = 1 + Math.floor(Math.random() * 1330); } while (G.seen.has(n) && G.seen.size < 1300);
  G.seen.add(n); return n;
}

// ---------------------------------------------------------------- a game
function show(id) {
  for (const s of ['home', 'chapters', 'pause', 'over']) $('#' + s).hidden = s !== id;
  $('#hud').hidden = !(G.on);
}
async function startGame(mode, chNo) {
  sfx.unlock(); hush();
  Object.assign(G, { on: true, paused: false, mode, chapter: chNo || 0, idx: 0, score: 0, lamps: 3, streak: 0, correct: 0, log: [], seen: new Set(), queue: [] });
  if (mode === 'festival') G.queue = [freshKural(), freshKural()];
  else if (mode === 'k108') G.queue = shuffle(META.k108.slice());
  else { const c = META.chapters[chNo - 1]; G.queue = Array.from({ length: c.end - c.start + 1 }, (_, i) => c.start + i); }
  particles.length = 0; floaters.length = 0; stick = null; R = null;
  show(null); $('#hud').hidden = false;
  $('#leaf-l1').textContent = ''; $('#leaf-l2').textContent = ''; $('#leaf-meaning').textContent = ''; $('#leaf-where').textContent = t('loading');
  renderHudBare(); sfx.drum();
  await Promise.all([document.fonts ? document.fonts.load(fontTa(18), 'குறள்').catch(() => {}) : null]);
  startRound();
}
function renderHudBare() {
  $('#btn-hint').textContent = t('hint'); $('#score-lbl').textContent = t('score'); $('#score').textContent = '0';
  $('#btn-sound').textContent = S.sound ? '🔊' : '🔇'; $('#btn-pause').textContent = '⏸'; $('#round').textContent = '';
  $('#streak').hidden = true; $('#lamps').textContent = '🪔🪔🪔';
}
function pause(on) {
  if (!G.on) return;
  G.paused = on; if (on) hush();
  $('#pause').hidden = !on;
}
function endGame(why) {
  hush();
  const mode = G.mode, done = why === 'done';
  G.on = false; G.paused = false;
  let best = 0, stars = 0;
  if (mode === 'chapter') {
    if (done) { stars = clamp(G.lamps, 1, 3); S.stars[G.chapter] = Math.max(S.stars[G.chapter] || 0, stars); }
  } else { S.best[mode] = Math.max(S.best[mode] || 0, G.score); best = S.best[mode]; }
  saveState();
  if (done) sfx.fanfare();
  $('#over-h').textContent = done ? (mode === 'chapter' ? t('over_chapter') : t('over_all')) : (why === 'out' ? t('over') : t('over_quit'));
  const st = $('#over-stars'); st.hidden = !(mode === 'chapter' && done); st.textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
  $('#over-score').textContent = G.score; $('#over-score-l').textContent = t('score');
  $('#over-solved').textContent = `${G.correct}`; $('#over-solved-l').textContent = t('solved');
  $('#over-best').textContent = mode === 'chapter' ? `${META.chapters[G.chapter - 1].n}` : best;
  $('#over-best-l').textContent = mode === 'chapter' ? META.chapters[G.chapter - 1].ta : t('best');
  $('#btn-again').textContent = t('again'); $$('[data-go="home"]').forEach(b => { b.textContent = t('home'); });
  $('#over-review-h').textContent = t('review');
  renderReview();
  show('over'); $('#hud').hidden = true; R = null;
}
async function renderReview() {
  const box = $('#over-review'); box.textContent = '';
  let tr = {}; try { tr = await translation(S.tr); } catch (e) { /* the couplets without their meaning */ }
  const s = stream(S.tr);
  for (const item of G.log.slice()) {
    let ch; try { ch = await chapter(Math.ceil(item.n / 10)); } catch (e) { continue; }
    const k = ch.kurals.find(q => q.n === item.n), row = document.createElement('div'); row.className = 'rv';
    const mark = document.createElement('span'); mark.className = 'mark ' + (item.ok ? 'ok' : 'no'); mark.textContent = item.ok ? '✓' : '✗';
    const kp = document.createElement('p'); kp.className = 'k'; kp.lang = 'ta';
    let at = 0;
    k.l.forEach((line, li) => {
      if (li) kp.append(document.createElement('br'));
      line.split(' ').forEach((tok, j) => { if (j) kp.append(' '); if (at === item.blank) { const m = document.createElement('mark'); m.textContent = tok; kp.append(m); } else kp.append(tok); at++; });
    });
    const mp = document.createElement('p'); mp.className = 'm'; mp.dir = s.dir || 'ltr'; mp.textContent = (tr[String(item.n)] || []).filter(Boolean).join(' ');
    const wp = document.createElement('p'); wp.className = 'w';
    const a = document.createElement('a'); a.href = KURAL_APP + item.n; a.target = '_blank'; a.rel = 'noopener'; a.textContent = t('open_app');
    wp.append(`${t('kural')} ${item.n} · `, a);
    row.append(mark, kp, mp, wp); box.append(row);
  }
}

// ---------------------------------------------------------------- the screens
function applyUi() {
  document.documentElement.lang = S.ui;
  $('#tagline').textContent = t('tagline');
  const icons = { festival: '🏮', chapters: '📖', k108: '🪔' };
  $$('.mode').forEach(b => {
    const m = b.dataset.mode;
    $('b', b).textContent = icons[m]; $('span', b).textContent = t('m_' + m);
    let d = t('m_' + m + '_d');
    if (m !== 'chapters' && S.best[m]) d += ` · ${t('best')}: ${S.best[m]}`;
    if (m === 'chapters') { const n = Object.keys(S.stars).length; if (n) d += ` · ✓ ${n}/133`; }
    $('em', b).textContent = d;
  });
  $('#how summary').textContent = t('how');
  const ol = $('#how-list'); ol.textContent = ''; t('how_list').forEach(x => { const li = document.createElement('li'); li.textContent = x; ol.append(li); });
  $('#set-h').textContent = t('settings'); $('#set-ui').textContent = t('set_ui'); $('#set-tr').textContent = t('set_tr');
  $('#set-aid').textContent = t('set_aid'); $('#set-sound').textContent = t('set_sound'); $('#set-voice').textContent = t('set_voice');
  $('#sel-ui').value = S.ui; $('#chk-sound').checked = !!S.sound; $('#chk-voice').checked = !!S.voice;
  const tr = $('#sel-tr'); tr.textContent = '';
  META.streams.forEach(s => { const o = document.createElement('option'); o.value = s.code; o.textContent = s.native === s.name ? s.name : `${s.native} · ${s.name}`; tr.append(o); });
  tr.value = S.tr;
  const aid = $('#sel-aid'); aid.textContent = '';
  [['auto', t('aid_auto')], ['off', t('aid_off')], ['Latin', t('aid_latin')], ...Object.keys(AID_NAMES).filter(k => SCRIPTS[k]).map(k => [k, AID_NAMES[k]])]
    .forEach(([v, label]) => { const o = document.createElement('option'); o.value = v; o.textContent = label; aid.append(o); });
  aid.value = S.aid;
  $('#credits').textContent = t('credits') + ` · v${VERSION}`;
  $('#pause-h').textContent = t('paused'); $('#btn-resume').textContent = t('resume'); $('#btn-quit').textContent = t('quit');
  $('#ch-h').textContent = t('chapters'); $$('[data-go="home"]').forEach(b => { b.textContent = t('home'); });
}
function renderChapters() {
  const box = $('#ch-list'); box.textContent = '';
  for (const pal of META.pals) {
    const h = document.createElement('h3'); h.className = 'pal'; h.textContent = pal.name + ' ';
    const sm = document.createElement('small'); sm.textContent = '· ' + pal.nameEn; h.append(sm); box.append(h);
    const grid = document.createElement('div'); grid.className = 'ch-grid';
    for (const iyal of pal.iyals) for (const n of iyal.chapters) {
      const c = META.chapters[n - 1], b = document.createElement('button'); b.type = 'button'; b.className = 'ch' + (S.stars[n] ? ' done' : '');
      const i = document.createElement('i'); i.textContent = n;
      const s = document.createElement('span'); s.lang = 'ta'; s.textContent = c.ta;
      const e = document.createElement('em');
      if (S.stars[n]) { const st = document.createElement('b'); st.className = 'st'; st.textContent = '★'.repeat(S.stars[n]) + '☆'.repeat(3 - S.stars[n]) + ' '; e.append(st); }
      e.append(c.en);
      b.append(i, s, e); b.addEventListener('click', () => startGame('chapter', n)); grid.append(b);
    }
    box.append(grid);
  }
}
function goHome() { hush(); G.on = false; G.paused = false; R = null; applyUi(); show('home'); }

// ---------------------------------------------------------------- the hands of the player
function potAt(x, y) {
  if (!R) return null;
  let best = null, bd = 1e9;
  for (const p of R.pots) {
    if (!p.alive || !p.box) continue;
    const b = p.box; if (x < b.x0 || x > b.x1 || y < b.y0 || y > b.y1) continue;
    const d = Math.hypot(x - b.cx, y - (b.cy + geom.potR * 0.6));
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}
cv.addEventListener('pointerdown', e => {
  if (!G.on || G.paused || !R) return;
  const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  if (R.state === 'won') { if (R.then && now - R.t0 > 0.3) { const then = R.then; R.until = 0; R.then = null; then(); } return; }
  const p = potAt(x, y); if (p) { e.preventDefault(); strike(p); }
});
window.addEventListener('keydown', e => {
  if (e.target && /^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
  if (!G.on) return;
  if (e.key === 'Escape' || e.key === 'p' || e.key === 'P') { pause(!G.paused); return; }
  if (G.paused || !R) return;
  if (/^[1-9]$/.test(e.key)) { if (!keysUsed) keysUsed = true; const p = R.pots.find(q => q.key === Number(e.key)); if (p) strike(p); }
  else if (e.key === 'h' || e.key === 'H') $('#btn-hint').click();
  else if ((e.key === ' ' || e.key === 'Enter') && R.state === 'won' && R.then) { e.preventDefault(); const then = R.then; R.until = 0; R.then = null; then(); }
});
$('#btn-hint').addEventListener('click', () => {
  if (!R || R.state !== 'play' || R.hintUsed) return;
  R.hintUsed = true; $('#btn-hint').disabled = true;
  const el = $('#leaf-hint'); el.textContent = '';
  const b = document.createElement('b'); b.textContent = latinOf(R.answer).charAt(0) + '…';
  el.append(b, R.answer[3] ? ` — ${R.answer[3]}` : ''); el.hidden = false; layout();
});
$('#leaf-meaning').addEventListener('click', () => { $('#leaf-meaning').classList.toggle('open'); layout(); });
$('#btn-pause').addEventListener('click', () => pause(true));
$('#btn-resume').addEventListener('click', () => pause(false));
$('#btn-quit').addEventListener('click', () => { $('#pause').hidden = true; if (G.log.length) endGame('quit'); else goHome(); });
$('#btn-sound').addEventListener('click', () => { S.sound = !S.sound; if (!S.sound) hush(); saveState(); renderHud(); });
$('#btn-again').addEventListener('click', () => startGame(G.mode, G.chapter));
$$('.mode').forEach(b => b.addEventListener('click', () => {
  const m = b.dataset.mode;
  if (m === 'chapters') { renderChapters(); show('chapters'); $('#chapters').scrollTop = 0; } else startGame(m);
}));
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-go="home"]'); if (b) goHome(); });
$('#sel-ui').addEventListener('change', e => { S.ui = e.target.value; saveState(); applyUi(); });
$('#sel-tr').addEventListener('change', e => { S.tr = e.target.value; saveState(); translation(S.tr).catch(() => {}); });
$('#sel-aid').addEventListener('change', e => { S.aid = e.target.value; saveState(); });
$('#chk-sound').addEventListener('change', e => { S.sound = e.target.checked; saveState(); if (S.sound) sfx.good(); });
$('#chk-voice').addEventListener('change', e => { S.voice = e.target.checked; saveState(); });
const DEBUG = /[?&]debug\b/.test(location.search);
document.addEventListener('visibilitychange', () => { if (document.hidden && G.on && !G.paused && !DEBUG) pause(true); });
if (DEBUG) {      // for the tests: the clock moved by hand, so that a page in the background can be played
  window.__ku = { G, S, geom, get R() { return R; }, strike, startGame, pause,
    step(secs) { const n = Math.ceil(secs / 0.016); for (let i = 0; i < n; i++) { now += 0.016; if (G.on && !G.paused && R) update(0.016); } render(0.016); } };
}
window.addEventListener('resize', () => { resize(); if (G.on && R) fitLeaf(); });
if (window.ResizeObserver) new ResizeObserver(() => { if (G.on) layout(); }).observe($('#hud'));

// ---------------------------------------------------------------- the start
async function boot() {
  loadState();
  $('#loading span').textContent = TEXT[S.ui].loading;
  resize(); requestAnimationFrame(frame);
  try { [META, SCRIPTS] = await Promise.all([json('corpus/meta.json'), json('corpus/scripts.json')]); }
  catch (e) { $('#loading span').textContent = TEXT[S.ui].load_fail; return; }
  if (!S.saved) {       // the first visit: the meaning in the language of the device, where the game has it
    const own = META.streams.find(s => s.code === S.navLang);
    if (own && S.navLang !== 'ta') S.tr = own.code;
  }
  if (!META.streams.some(s => s.code === S.tr)) S.tr = 'en';
  VOICE = findVoice();
  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => { VOICE = findVoice(); };
  applyUi(); show('home'); $('#loading').hidden = true;
  translation(S.tr).catch(() => {});
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (G.on) layout(); });
  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol) && !/^(localhost|127\.)/.test(location.hostname)) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}
boot();
})();
