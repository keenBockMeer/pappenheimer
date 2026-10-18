// Reine Rechen- und Spielregeln der Deckansicht (PLAN Phasen 62 und 63): ohne DOM, ohne Netz, geladen vor app.js als eigenes Skript und mit Node
// getestet (test_mtg.py, test_spieltisch_regeln, test_wahrscheinlichkeit_wie_der_server). Ideen von Archidekt, alles neu geschrieben (wie E36).
(function () {
  'use strict';

  // Wahrscheinlichkeit, unter n von N Karten (K davon „Treffer“) mindestens k Treffer zu ziehen: exakt wie deckbuild.mindestens
  const komb = (n, k) => { if (k < 0 || k > n) return 0; let r = 1; for (let i = 1; i <= k; i++) r = r * (n - k + i) / i; return r; };
  function mindestens(N, K, n, k) {
    if (N <= 0 || n <= 0) return k <= 0 ? 1 : 0;
    n = Math.min(n, N);
    let s = 0;
    for (let i = Math.max(k, 0); i <= Math.min(K, n); i++) s += komb(K, i) * komb(N - K, n - i);
    return s / komb(N, n);
  }

  // Spieltisch (Phase 62): ein Spiel allein, Zug für Zug. Zustand s = {bib, hand, feld, friedhof, exil, kommando, leben, zug, mull, gewirkt};
  // jede Karte ist ein eigenes Objekt {uid, karte, tapped}; nichts geht verloren, jede Regel verschiebt nur. rnd: Zufall (Tests geben ihn vor)
  const ZONEN = ['hand', 'feld', 'friedhof', 'exil', 'kommando', 'bib'];
  const mischen = s => { const b = s.bib; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(s.rnd() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return s; };
  const ziehen = (s, n = 1) => { for (let i = 0; i < n && s.bib.length; i++) s.hand.push(s.bib.shift()); return s; };
  function neu(karten, commander = [], rnd = Math.random) {  // karten: je Karte {qty, …} ohne Commander; commander: Liste
    let uid = 0;
    const s = {bib: karten.flatMap(k => Array.from({length: k.qty || 1}, () => ({uid: ++uid, karte: k, tapped: false}))), hand: [], feld: [], friedhof: [], exil: [],
      kommando: commander.map(k => ({uid: ++uid, karte: k, tapped: false, commander: true})), leben: 40, zug: 1, mull: 0, gewirkt: {}, rnd};
    return ziehen(mischen(s), 7);
  }
  const finden = (s, uid) => { for (const z of ZONEN) { const i = s[z].findIndex(c => c.uid === uid); if (i >= 0) return [z, i]; } return [null, -1]; };
  function bewegen(s, uid, ziel) {  // ziel: hand, feld, friedhof, exil, kommando (nur Commander), oben, unten (Bibliothek)
    const [von, i] = finden(s, uid);
    if (!von || (ziel === 'kommando' && !s[von][i].commander)) return s;
    const [c] = s[von].splice(i, 1);
    c.tapped = false;
    if (von === 'kommando' && ziel === 'feld') s.gewirkt[uid] = (s.gewirkt[uid] || 0) + 1;  // Commander-Steuer: 2 je früheres Wirken aus der Kommandozone
    if (ziel === 'oben') s.bib.unshift(c);
    else if (ziel === 'unten') s.bib.push(c);
    else s[ziel].push(c);
    return s;
  }
  const steuer = (s, uid) => 2 * (s.gewirkt[uid] || 0);
  const tappen = (s, uid) => { const c = s.feld.find(x => x.uid === uid); if (c) c.tapped = !c.tapped; return s; };
  function mulligan(s) {  // alles von Hand zurück, mischen, sieben neue; was unter die Bibliothek gehört, legt man selbst dorthin
    s.bib.push(...s.hand.splice(0));
    s.mull++;
    return ziehen(mischen(s), 7);
  }
  function naechsterZug(s) { s.zug++; s.feld.forEach(c => { c.tapped = false; }); return ziehen(s); }
  const Deck = {mindestens, Tisch: {neu, ziehen, mischen, bewegen, tappen, mulligan, naechsterZug, steuer, finden, ZONEN}};
  globalThis.Deck = Deck;
  if (typeof module !== 'undefined' && module.exports) module.exports = Deck;
})();
