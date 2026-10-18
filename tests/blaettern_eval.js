// Phase 57: Prüfstand für „Kopien beim Durchblättern“ (Zaehler.Kopien in ui/zaehler.js, Mini-Bild miniBild in app.js). Nicht Teil von pytest.
// Am Rechner in der Browser-Konsole der App einfügen (Ansicht „Scannen“, Prüfen: die Bilder kommen aus dem Index der eigenen Sammlung), dann:
//   await blaetternEval(200)
// Ergebnis als JSON zum Ablegen und Vergleichen: copy(JSON.stringify(await blaetternEval(200), null, 1))
// Jede Folge ist eine Szene wie in finden_eval.js (Kamerabild 720 × 1280, dunkle Matte oder Holz, Licht und Rauschen), in der eine Karte gezählt
// ist (karte()) und dann etwas geschieht. Arten (art): stapel (1 bis 6 gleiche Karten, die oberste wird jeweils weggeschnippt: Daumen kommt,
// die Karte fliegt verwischt neben den Stapel oder aus dem Bild), gemischt (danach liegt eine andere Karte da), ablage (daneben ein
// Ablagestapel, der dieselbe Karte zeigt, die Karten fliegen darauf), geschoben (der Daumen schiebt den Stapel), hand (eine Hand fährt über
// die Karte), liegt (nichts geschieht). Dazu je Folge 2 bis 6 Karten je Sekunde und 15, 24 oder 30 Bilder je Sekunde. echt = so viele Kopien
// kamen wirklich dazu. Gezählt wird, was Kopien als 'kopie' meldet; 'frage' zählt nicht (die App fragt). genau = kopien === echt, ueber =
// kopien > echt, fragen = Folgen mit mindestens einer Frage, erkannt = Anteil der echten Kopien, die gezählt oder gefragt wurden, genauVorschlag =
// genau, wenn die App jede Kopie nur fragt (BLAETTERN_SELBST = false) und jede Frage mit „+1“ beantwortet wird, wo wirklich eine Kopie lag. ms = Mini-Bild und Zustandsautomat je Kamerabild (ohne das Zeichnen der Szene).
// ruhig (Phase 56): Zaehler.ruhigIn in der Zone der untersten Karte über die letzten RUHIG_BILDER + 1 Bilder; stillErkannt = Anteil der Bilder,
// in denen sich so lange nichts bewegte und ruhigIn ja sagt, bewegtFuerRuhig = Anteil der Bilder mit Bewegung, die trotzdem als ruhig gelten.
async function blaetternEval(n = 200, {seed = 56, opt = {}, spur = false, arten = null} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const zw = (lo, hi) => lo + rnd() * (hi - lo), um = x => (rnd() * 2 - 1) * x, wahl = xs => xs[Math.floor(rnd() * xs.length)];
  const laden = u => new Promise((ok, err) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(3) : null; };
  const r = await api('scan?v=' + FP_V), ix = fpIndex(r), bilder = [];
  for (const oid of [...new Set(ix.oids)].sort(() => rnd() - .5).slice(0, 24)) { try { bilder.push(await laden(ix.karten[oid].image)); } catch { /* fehlt */ } }
  const W = 720, H = 1280, S = document.createElement('canvas'), g = S.getContext('2d', {willReadFrequently: true});
  S.width = W; S.height = H;
  const KH = 520, KW = KH * 63 / 88;  // Karte im Kamerabild (gut 40 % der Höhe, wie in der Hand über dem Tisch)
  const ARTEN = ['stapel', 'stapel', 'stapel', 'gemischt', 'ablage', 'geschoben', 'hand', 'liegt'];
  const grundBild = () => {  // Untergrund einmal je Folge
    const c = document.createElement('canvas'); c.width = W; c.height = H; const k = c.getContext('2d');
    if (rnd() < .6) { k.fillStyle = `rgb(${zw(14, 55) | 0},${zw(14, 55) | 0},${zw(20, 60) | 0})`; k.fillRect(0, 0, W, H); }
    else { k.fillStyle = `rgb(${zw(120, 185) | 0},${zw(85, 130) | 0},${zw(45, 90) | 0})`; k.fillRect(0, 0, W, H); k.translate(W / 2, H / 2); k.rotate(rnd() * Math.PI);
      for (let i = 0; i < 160; i++) { const y = um(1400); k.strokeStyle = `rgba(${rnd() < .6 ? '40,20,5' : '255,230,190'},${zw(.04, .2)})`; k.lineWidth = zw(1, 7); k.beginPath(); k.moveTo(-1600, y); k.lineTo(1600, y + um(12)); k.stroke(); } }
    return c;
  };
  // ein Kamerabild: Grund, Dinge (Karten und Hand), Licht, Rauschen. Ding = {im | hand, x, y (Mitte), w, h, dreh, hell, spur: [[dx, dy], …]}
  const zeichnen = (grund, dinge, licht) => {
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.filter = 'none'; g.globalCompositeOperation = 'source-over'; g.drawImage(grund, 0, 0);
    for (const d of dinge) {
      const spur = d.spur || [[0, 0]];
      for (const [i, [sx, sy]] of spur.entries()) {
        g.globalAlpha = spur.length > 1 ? 1 / (spur.length - i) : 1;  // jede Lage über die vorigen: gleiche Anteile
        g.setTransform(1, 0, 0, 1, d.x + sx, d.y + sy); g.rotate((d.dreh || 0) * Math.PI / 180);
        if (d.hand) { g.fillStyle = 'rgb(205,150,120)'; g.beginPath(); g.ellipse(0, 0, d.w / 2, d.h / 2, 0, 0, 2 * Math.PI); g.fill(); }
        else { g.filter = `brightness(${1 + (d.hell || 0)})`; g.drawImage(d.im, -d.w / 2, -d.h / 2, d.w, d.h); g.filter = 'none'; }
      }
      g.globalAlpha = 1;
    }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'multiply'; g.fillStyle = `rgb(${licht.join()})`; g.fillRect(0, 0, W, H); g.globalCompositeOperation = 'source-over';
    const d = g.getImageData(0, 0, W, H);
    for (let i = 0; i < d.data.length; i += 16) { const z = um(10); for (let k = 0; k < 16; k += 4) { d.data[i + k] += z; d.data[i + k + 1] += z; d.data[i + k + 2] += z; } }
    g.putImageData(d, 0, 0);
  };
  const ergebnis = [], ms = [], ruhe = {still: [], bewegt: []};
  for (let k = 0; k < n; k++) {
    globalThis.evalStand = {k, n};  // Fortschritt, von außen lesbar
    await new Promise(r => setTimeout(r));  // die Seite bleibt zwischen den Folgen bedienbar
    const art = (arten || ARTEN)[k % (arten || ARTEN).length], fps = wahl([15, 24, 30]), rate = zw(2, 6), proKarte = Math.max(2, Math.round(fps / rate));
    const A = wahl(bilder), B = wahl(bilder.filter(x => x !== A)), grund = grundBild(), licht = [235 + um(20) | 0, 235 + um(20) | 0, 235 + um(20) | 0];
    const zx = zw(.35, .5) * W, zy = zw(.45, .6) * H, kopie = () => ({im: A, x: zx + um(.01) * KW, y: zy + um(.01) * KH, w: KW, h: KH, dreh: um(1.5), hell: um(.04)});
    const zahl = art === 'stapel' || art === 'ablage' || art === 'gemischt' ? 1 + Math.floor(rnd() * 6) : art === 'geschoben' ? 3 : 1;
    const stapel = Array.from({length: zahl}, kopie), ablage = art === 'ablage' ? {im: A, x: zx + 1.1 * KW, y: zy - .55 * KH, w: KW, h: KH, dreh: um(4)} : null;
    const folge = [], liegen = ablage ? [ablage] : [];
    const still = (dinge, m) => { for (let i = 0; i < m; i++) folge.push(dinge); };
    still([...liegen, ...stapel], 4);
    let echt = 0;
    if (art === 'stapel' || art === 'ablage' || art === 'gemischt') {
      for (let i = zahl - 1; i >= 1; i--) {  // die oberste wegschnippen
        const oben = stapel[i], unten = stapel.slice(0, i), raus = art === 'ablage' ? null : rnd() < .5;
        const ziel = art === 'ablage' ? {x: ablage.x + um(.03) * KW, y: ablage.y + um(.03) * KH} : raus ? {x: zx + 1.6 * KW, y: zy - .9 * KH} : {x: zx + wahl([-1, 1]) * zw(1.05, 1.3) * KW, y: zy + um(.4) * KH};
        const flug = Math.max(1, Math.round(proKarte / 2)), daumen = {hand: true, x: zx + .4 * KW, y: zy + .45 * KH, w: .35 * KW, h: .6 * KH};
        folge.push([...liegen, ...unten, oben, daumen]);
        let alt = 0;
        for (let f = 1; f <= flug; f++) {
          const t = f / flug, spur = [0, .25, .5, .75, 1].map(u => { const v = alt + (t - alt) * u; return [(ziel.x - oben.x) * v, (ziel.y - oben.y) * v]; });
          folge.push([...liegen, ...unten, {...oben, spur, dreh: oben.dreh + 20 * t}, {...daumen, x: daumen.x + .3 * KW * t, y: daumen.y + .5 * KH * t}]); alt = t;
        }
        if (!raus) liegen.push({...oben, x: ziel.x, y: ziel.y, dreh: oben.dreh + 20});
        still([...liegen, ...unten], Math.max(2, proKarte - flug - 1));
        echt++;
      }
      if (art === 'gemischt') { folge.push([...liegen, stapel[0], {hand: true, x: zx, y: zy + .2 * KH, w: .5 * KW, h: .8 * KH}]); still([...liegen, {...kopie(), im: B}], proKarte * 2); }
      else still([...liegen, stapel[0]], proKarte * 2);
    } else if (art === 'geschoben') {
      const d = zw(.08, .25) * KW, wohin = rnd() * 2 * Math.PI, m = Math.max(2, proKarte);
      for (let f = 1; f <= m; f++) folge.push([...stapel.map(c => ({...c, x: c.x + Math.cos(wohin) * d * f / m, y: c.y + Math.sin(wohin) * d * f / m})), {hand: true, x: zx + .45 * KW, y: zy + .45 * KH, w: .35 * KW, h: .6 * KH}]);
      still(stapel.map(c => ({...c, x: c.x + Math.cos(wohin) * d, y: c.y + Math.sin(wohin) * d})), proKarte * 3);
    } else if (art === 'hand') {
      const m = Math.max(3, proKarte * 2), von = -1.2 * KW, bis = 1.2 * KW;
      for (let f = 0; f <= m; f++) folge.push([...stapel, {hand: true, x: zx + von + (bis - von) * f / m, y: zy + um(.1) * KH, w: .9 * KW, h: 1.3 * KH, spur: [[0, 0], [(bis - von) / m / 2, 0]]}]);
      still(stapel, proKarte * 3);
    } else still(stapel, fps * 4);
    // abspielen: Mini-Bild je Kamerabild durch Kopien, die erste Karte gilt als gezählt (wie nach der Erkennung)
    const kop = new Zaehler.Kopien({...BLAETTERN_OPT, ...opt}), ev = [], verlauf = [], gang = [];
    const zone = c => blaetternZone(miniBild(S, W, H), {x: c.x - KW / 2, y: c.y - KH / 2, w: KW, h: KH}, W, H);
    folge.forEach((dinge, i) => {
      zeichnen(grund, dinge, licht);
      const t0 = performance.now(), m = miniBild(S, W, H);
      if (i === 0) kop.karte(m, zone(stapel.at(-1)));
      else { const r = kop.bild(m); if (r.ereignis) ev.push(r.ereignis); if (spur) gang.push(`${r.stand[0]}${r.wert != null ? r.wert.toFixed(2) : ''}${kop.brach ? 'B' : ''}${kop.zeugeDa ? 'Z' : ''}${r.ereignis ? '!' + r.ereignis[0] : ''}`); }
      ms.push(performance.now() - t0);
      // Phase 56: ruhig aus dem Mini-Bild (Zone der Karte, die letzten RUHIG_BILDER + 1 Bilder) gegen die Wahrheit (dieselbe Szene so lange)
      verlauf.push(m); if (verlauf.length > RUHIG_BILDER + 1) verlauf.shift();
      if (i >= RUHIG_BILDER) { const r = Zaehler.ruhigIn(verlauf, zone(stapel[0]), RUHIG_DIFF), still = folge.slice(i - RUHIG_BILDER, i + 1).every(x => x === dinge); ruhe[still ? 'still' : 'bewegt'].push(r); }
    });
    const kopien = ev.filter(e => e === 'kopie').length, fragen = ev.filter(e => e === 'frage').length;
    ergebnis.push({art, fps, rate: +rate.toFixed(1), zahl, echt, kopien, fragen, ...(spur && kopien !== echt ? {gang: gang.join(' ')} : {})});
  }
  // Vorschlag statt Zählen (Rückweg, BLAETTERN_SELBST = false): Jede Kopie wird gefragt; stimmt, wenn bei echten Kopien jede gefragt oder gezählt ist
  const vorschlag = e => e.echt ? e.kopien + e.fragen === e.echt : e.kopien === 0;
  const anteil = (xs, f) => xs.length ? +(xs.filter(f).length / xs.length).toFixed(3) : null;
  const jeArt = Object.fromEntries([...new Set(ergebnis.map(e => e.art))].map(art => { const xs = ergebnis.filter(e => e.art === art); return [art, {n: xs.length, genau: anteil(xs, e => e.kopien === e.echt), vorschlag: anteil(xs, vorschlag), ueber: anteil(xs, e => e.kopien > e.echt), fragen: anteil(xs, e => e.fragen > 0)}]; }));
  const jeFps = Object.fromEntries([15, 24, 30].map(f => { const xs = ergebnis.filter(e => e.fps === f); return [f, {n: xs.length, genau: anteil(xs, e => e.kopien === e.echt), ueber: anteil(xs, e => e.kopien > e.echt)}]; }));
  const echtGesamt = ergebnis.reduce((s, e) => s + e.echt, 0), kopienGesamt = ergebnis.reduce((s, e) => s + Math.min(e.kopien, e.echt), 0);
  const erkannt = ergebnis.reduce((s, e) => s + Math.min(e.kopien + e.fragen, e.echt), 0);
  return {at: new Date().toISOString(), verfahren: 'Kopien beim Durchblättern', mini: BLAETTERN_MINI, opt: {...BLAETTERN_OPT, ...opt}, seed, folgen: ergebnis.length,
          genau: anteil(ergebnis, e => e.kopien === e.echt), ueber: anteil(ergebnis, e => e.kopien > e.echt), fragen: anteil(ergebnis, e => e.fragen > 0),
          kopienGezaehlt: echtGesamt ? +(kopienGesamt / echtGesamt).toFixed(3) : null, erkannt: echtGesamt ? +(erkannt / echtGesamt).toFixed(3) : null,
          genauVorschlag: anteil(ergebnis, vorschlag), jeArt, jeFps, ms: {p50: q(ms, .5), p95: q(ms, .95), max: q(ms, 1)},
          ruhig: {stillErkannt: anteil(ruhe.still, x => x), bewegtFuerRuhig: anteil(ruhe.bewegt, x => x), still: ruhe.still.length, bewegt: ruhe.bewegt.length},
          falsch: ergebnis.filter(e => e.kopien !== e.echt).slice(0, 30)};
}
