// Phase 33: Findet die App die Karte frei im Bild, und erkennt sie sie danach so gut wie im Rahmen? Nicht Teil von pytest.
// Am Rechner in der Browser-Konsole der App einfügen (Ansicht „Scannen“, Erkennungsbilder vorbereitet), dann eins davon:
//   await findenEval(300)                      künstliche Szenen, Erkennung im Browser gegen die eigene Sammlung (wie Prüfen)
//   await findenEval(300, {server: true})      dieselben Szenen, Erkennung auf dem Server gegen alle Karten (wie „Alle Karten, ohne Set“)
//   await findenEval(0, {messbilder: true})    die Messbilder aus Phase 30 (echte Kamerabilder mit Etikett), auch mit server: true
// Ergebnis als JSON zum Ablegen und Vergleichen: copy(JSON.stringify(await findenEval(300), null, 1))
// Szene = ein großes Scryfall-Bild frei in einem Kamerabild (1280 × 720, quer oder hoch): 33 bis 80 % der kurzen Seite hoch, bis 25° gedreht und
// bis 25° gekippt (Trapez), irgendwo ganz im Bild, mit Schatten. Untergrund: dunkle Matte, Holz mit Maserung, heller Tisch, bunte Spielmatte oder
// grober Stoff, bei einem Teil dazu eine zweite Karte am Bildrand, eine Tischkante oder ein Daumen auf dem Rand der Karte (hand = Anteil). Licht,
// Farbstich, Unschärfe, Spiegelung und Rauschen wie in scan_eval.js (licht und lage von 0 bis 1 skalieren die Verzerrung). Zum Vergleich läuft
// dieselbe Karte mit demselben Licht „im Rahmen“ durch die Erkennung von vorher (verschoben, gedreht und skaliert wie in scan_eval.js).
// gefunden = eins der Vierecke trifft die Karte (als Kartenrand oder als innerer Rahmen, jede Ecke höchstens 4 % der Kartenbreite daneben),
// gefundenErstes = schon das erste. frei und rahmen: top1, top3 und das Urteil (zusammen 1): sicherRichtig, sicherFalsch, unsicher, nichts.
// ms: finden = karteFinden, frei = Entzerren und Erkennen danach, rahmen = Erkennung von vorher. zeig: N hängt die N-te Szene mit den gefundenen
// Vierecken unten an die Seite (zum Ansehen) und hört dort auf.
async function findenEval(n = 200, {seed = 7, licht = 1, lage = 1, hand = .25, server = false, messbilder = false, zeig = null} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = (x, f = licht) => (rnd() * 2 - 1) * x * f, zw = (lo, hi) => lo + rnd() * (hi - lo), grau = (lo, hi, t = 12) => { const g = zw(lo, hi); return [g + um(t, 1), g + um(t, 1), g + um(t, 1)].map(Math.round).join(); };
  const laden = (u, cors = true) => new Promise((ok, err) => { const im = new Image(); if (cors) im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(3) : null; };
  // Abbildung Einheitsquadrat -> Viereck (wie scanBild) und zurück
  const hin = ([[x0, y0], [x1, y1], [x2, y2], [x3, y3]]) => {
    const dx1 = x1 - x2, dx2 = x3 - x2, sx = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, sy = y0 - y1 + y2 - y3, den = dx1 * dy2 - dx2 * dy1, g = (sx * dy2 - dx2 * sy) / den, h = (dx1 * sy - sx * dy1) / den;
    return [x1 - x0 + g * x1, x3 - x0 + h * x3, x0, y1 - y0 + g * y1, y3 - y0 + h * y3, y0, g, h];
  };
  const ab = (m, u, v) => { const w = m[6] * u + m[7] * v + 1; return [(m[0] * u + m[1] * v + m[2]) / w, (m[3] * u + m[4] * v + m[5]) / w]; };
  const zurueck = ([a, b, c, d, e, f, g, h]) => { const i = a * e - b * d; return [(e - f * h) / i, (c * h - b) / i, (b * f - c * e) / i, (f * g - d) / i, (a - c * g) / i, (c * d - a * f) / i, (d * h - e * g) / i, (b * g - a * h) / i]; };
  const bild = x => x.split(':')[0];
  const FELDER = ['top1', 'top3', 'sicherRichtig', 'sicherFalsch', 'unsicher', 'nichts'], leer = () => Object.fromEntries([['n', 0], ...FELDER.map(k => [k, 0])]);
  const zaehl = (g, {pos, urteil}) => { g.n++; g.top1 += pos === 0; g.top3 += pos >= 0; g.sicherRichtig += urteil === 'sicher' && pos === 0; g.sicherFalsch += urteil === 'sicher' && pos !== 0; g.unsicher += urteil === 'unsicher'; g.nichts += urteil === 'nichts'; };
  const quote = g => g.n ? Object.fromEntries([['n', g.n], ...FELDER.map(k => [k, +(g[k] / g.n).toFixed(3)])]) : {n: 0};
  // Erkennung: im Browser gegen die eigene Sammlung (wahr = Karte) oder auf dem Server gegen alle Karten (wahr = Aussehen, es zählt das Bild)
  let ix = null, karten;
  if (!server && !messbilder) { const r = await api('scan?v=' + FP_V); ix = fpIndex(r); karten = ix.oids.map((oid, j) => ({wahr: oid, name: ix.karten[oid].name, image: ix.karten[oid].image})); }
  else if (!messbilder) karten = (await api(`scan/katalog?v=${FP_V}&probe=${Math.min(5000, n * 4)}`)).probe.map(p => ({wahr: p.id, name: p.name, image: p.image}));
  const lokal = (best, wahr) => ({pos: best.findIndex(b => b.oid === wahr), urteil: !best[0] || best[0].score < FP_NEIN ? 'nichts' : best[0].score >= FP_SICHER ? 'sicher' : 'unsicher', vorn: best[0] && `${ix.karten[best[0].oid].name} ${best[0].score.toFixed(2)}`});
  const fern = (r, passt) => ({pos: r ? r.treffer.findIndex(passt) : -1, urteil: r?.urteil || 'nichts', vorn: r?.treffer[0] && `${r.treffer[0].druck.name} ${r.treffer[0].wert.toFixed(2)}`});
  const erkennen = {
    rahmen: async (src, cx, cy, w, h, wahr) => server ? fern(await (async fp => fp.length ? post('scan/suche', {v: FP_V, fp}) : null)(fpLagen(src, cx, cy, w, h)), x => bild(x.aussehen) === bild(wahr)) : lokal(fpSuche(ix, src, cx, cy, w, h), wahr),
    frei: async (src, vier, wahr) => server ? fern(await freiServer(src, vier), x => bild(x.aussehen) === bild(wahr)) : lokal(freiSuche(ix, src, vier), wahr),
  };
  const res = {rahmen: leer(), frei: leer()}, gruende = {}, ms = {finden: [], frei: [], rahmen: []}, eckfehler = [], fehler = [];
  let proben = 0, gefunden = 0, erstes = 0, vierecke = 0;

  if (messbilder) {  // echte Kamerabilder: im Rahmen wie messbilder_eval.js bzw. suche_eval.js, frei über das ganze Bild; richtig ist die Karte des Etiketts
    const indexe = new Map(), index = async code => {
      if (!indexe.has(code)) { let r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(code)}`); if (r.fehlt.length) { await fpJob(r.fehlt); r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(code)}`); } indexe.set(code, r.ids.length ? fpIndex({...r, keys: r.ids}) : null); }
      return indexe.get(code);
    };
    const merkmale = {};
    for (const m of (await api('messbilder')).items.filter(x => x.scryfall_id)) {
      const im = await laden(`/api/messbild/${m.id}.jpg`, false), [x, y, w, h] = m.rahmen.length ? m.rahmen : Object.values(scanRahmen(m.breite, m.hoehe));
      if (!server && !(ix = await index(m.set_code))) continue;
      const passt = t => t.druck.name === m.name, urteil = (best, sicher) => !best[0] || best[0].score < FP_NEIN ? 'nichts' : sicher ? 'sicher' : 'unsicher';
      const set = best => ({pos: best.findIndex(b => b.oid === m.scryfall_id), urteil: urteil(best, best[0]?.score >= FP_SICHER && (!best[1] || best[0].score - best[1].score >= FP_ABSTAND)), vorn: best[0] && `${ix.drucke[best[0].oid].name} ${best[0].score.toFixed(2)}`});
      let t0 = performance.now();
      const r = server ? fern(await (async fp => fp.length ? post('scan/suche', {v: FP_V, fp, sets: [m.set_code]}) : null)(fpLagen(...scanBild(im, {x, y, w, h}))), passt) : set(scanSuche(ix, im, {x, y, w, h}));
      ms.rahmen.push(performance.now() - t0); t0 = performance.now();
      const vier = karteFinden(im, m.breite, m.hoehe);
      ms.finden.push(performance.now() - t0); t0 = performance.now();
      const f = server ? fern(await freiServer(im, vier, {sets: [m.set_code]}), passt) : set(freiSuche(ix, im, vier));
      ms.frei.push(performance.now() - t0);
      proben++; vierecke += vier.length; gefunden += f.pos >= 0;  // gefunden: Ein Viereck führt zur richtigen Karte (die Lage der Karte im Bild kennt das Etikett nicht)
      const mm = messMerkmale(m);
      for (const k of ['alle', ...(mm.length ? mm : ['normal'])]) { const g = merkmale[k] = merkmale[k] || {rahmen: leer(), frei: leer(), beides: leer()}; zaehl(g.rahmen, r); zaehl(g.frei, f); zaehl(g.beides, f.urteil !== 'nichts' ? f : r); }
      if (f.pos !== 0 && fehler.length < 30) fehler.push(`#${m.id} ${m.name} (${mm.join(' ') || 'normal'}): ${vier.length} Vierecke, frei ${f.urteil} ${f.vorn || ''}, im Rahmen ${r.urteil} ${r.vorn || ''}`);
    }
    return {at: new Date().toISOString(), verfahren: 'Karte frei im Bild', quelle: 'Messbilder', erkennung: server ? 'Server, alle Karten' : 'Browser, Set des Etiketts', fp: FP_V, proben,
            gefunden: proben ? +(gefunden / proben).toFixed(3) : 0, viereckeJeBild: proben ? +(vierecke / proben).toFixed(2) : 0,
            merkmale: Object.fromEntries(Object.entries(merkmale).map(([k, g]) => [k, {rahmen: quote(g.rahmen), frei: quote(g.frei), beides: quote(g.beides)}])),
            ms: Object.fromEntries(Object.entries(ms).map(([k, v]) => [k, {p50: q(v, .5), p95: q(v, .95)}])), fehler};
  }

  const S = document.createElement('canvas'), sg = S.getContext('2d', {willReadFrequently: true}), K = document.createElement('canvas'), kg = K.getContext('2d', {willReadFrequently: true});
  const P = document.createElement('canvas'), pg = P.getContext('2d', {willReadFrequently: true});
  P.width = 488; P.height = 680;
  const GRUENDE = ['matte', 'holz', 'hell', 'spielmatte', 'stoff'];
  const rauschen = (g, w, h) => { const d = g.getImageData(0, 0, w, h); for (let i = 0; i < d.data.length; i += 4) { const z = um(8); d.data[i] += z; d.data[i + 1] += z; d.data[i + 2] += z; } g.putImageData(d, 0, 0); };
  const vieleck = (g, e) => { g.beginPath(); e.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); };
  function szene(im, L, anderes) {
    const hoch = rnd() < .5, W = S.width = hoch ? 720 : 1280, H = S.height = hoch ? 1280 : 720, grund = GRUENDE[Math.floor(rnd() * GRUENDE.length)];
    sg.setTransform(1, 0, 0, 1, 0, 0); sg.filter = 'none'; sg.globalCompositeOperation = 'source-over'; sg.globalAlpha = 1;
    if (grund === 'matte') { sg.fillStyle = `rgb(${grau(14, 55, 8)})`; sg.fillRect(0, 0, W, H); }
    else if (grund === 'hell') { sg.fillStyle = `rgb(${grau(200, 245, 8)})`; sg.fillRect(0, 0, W, H); }
    else if (grund === 'spielmatte' && anderes) { sg.filter = `blur(8px) brightness(${zw(.45, 1)})`; sg.drawImage(anderes, 49, 82, 390, 285, -20, -20, W + 40, H + 40); sg.filter = 'none'; }
    else if (grund === 'stoff') {
      const g0 = zw(80, 150); sg.fillStyle = `rgb(${g0 | 0},${g0 + um(15, 1) | 0},${g0 + um(15, 1) | 0})`; sg.fillRect(0, 0, W, H);
      for (let i = 0; i < 5000; i++) { sg.fillStyle = `rgba(${rnd() < .5 ? '0,0,0' : '255,255,255'},${zw(.05, .2)})`; sg.fillRect(rnd() * W, rnd() * H, zw(2, 7), zw(2, 7)); }
    } else {  // Holz: Maserung als lange Striche in einer Richtung
      sg.fillStyle = `rgb(${zw(120, 185) | 0},${zw(85, 130) | 0},${zw(45, 90) | 0})`; sg.fillRect(0, 0, W, H);
      sg.translate(W / 2, H / 2); sg.rotate(rnd() * Math.PI);
      for (let i = 0; i < 220; i++) { const y = um(900, 1); sg.strokeStyle = `rgba(${rnd() < .6 ? '40,20,5' : '255,230,190'},${zw(.04, .22)})`; sg.lineWidth = zw(1, 7); sg.beginPath(); sg.moveTo(-1600, y); sg.lineTo(1600, y + um(12, 1)); sg.stroke(); }
      sg.setTransform(1, 0, 0, 1, 0, 0);
    }
    if (rnd() < .3) {  // Tischkante: eine Hälfte in anderer Farbe
      const w = rnd() * Math.PI, px = zw(.2, .8) * W, py = zw(.2, .8) * H, c = Math.cos(w) * 3000, s = Math.sin(w) * 3000;
      sg.fillStyle = `rgba(${grau(20, 235, 20)},${zw(.5, 1)})`; vieleck(sg, [[px - c, py - s], [px + c, py + s], [px + c - s, py + s + c], [px - c - s, py - s + c]]); sg.fill();
    }
    if (rnd() < .3 && anderes) {  // zweite Karte, zum größeren Teil außerhalb des Bilds
      const h2 = zw(.4, .8) * 720, seite = Math.floor(rnd() * 4), t = zw(.1, .9);
      sg.translate(...[[-.12 * h2, t * H], [W + .12 * h2, t * H], [t * W, -.2 * h2], [t * W, H + .2 * h2]][seite]); sg.rotate(um(30, 1) * Math.PI / 180);
      sg.drawImage(anderes, -h2 * 63 / 176, -h2 / 2, h2 * 63 / 88, h2); sg.setTransform(1, 0, 0, 1, 0, 0);
    }
    // Lage der Karte: gedreht (z), gekippt (x, y), dann perspektivisch auf das Bild
    const kh = zw(.33, .8) * 720 * (hoch ? 1.2 : 1), kw = kh * 63 / 88, F = 2.2 * kh, [rz, rx, ry] = [um(25, lage), um(25, lage), um(25, lage)].map(g => g * Math.PI / 180);
    let e = [[-kw / 2, -kh / 2], [kw / 2, -kh / 2], [kw / 2, kh / 2], [-kw / 2, kh / 2]].map(([x, y]) => {
      let X = x * Math.cos(rz) - y * Math.sin(rz), Y = x * Math.sin(rz) + y * Math.cos(rz), Z = Y * Math.sin(rx);
      Y *= Math.cos(rx); [X, Z] = [X * Math.cos(ry) + Z * Math.sin(ry), Z * Math.cos(ry) - X * Math.sin(ry)];
      return [X * F / (F + Z), Y * F / (F + Z)];
    });
    const xs = e.map(p => p[0]), ys = e.map(p => p[1]), f = Math.min(1, .94 * W / (Math.max(...xs) - Math.min(...xs)), .94 * H / (Math.max(...ys) - Math.min(...ys)));
    const ox = zw(.02 * W - Math.min(...xs) * f, .98 * W - Math.max(...xs) * f), oy = zw(.02 * H - Math.min(...ys) * f, .98 * H - Math.max(...ys) * f);
    e = e.map(([x, y]) => [x * f + ox, y * f + oy]);
    const breit = Math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]), lang = Math.hypot(e[3][0] - e[0][0], e[3][1] - e[0][1]);
    sg.filter = `blur(${(.012 * lang).toFixed(1)}px)`; sg.fillStyle = `rgba(0,0,0,${zw(.25, .5)})`;  // Schatten: Die Karte liegt fast auf
    const sdx = um(.015, 1) * lang, sdy = zw(0, .015) * lang; vieleck(sg, e.map(([x, y]) => [x + sdx, y + sdy])); sg.fill(); sg.filter = 'none';
    // Karte mit ihrem Licht auf Zielgröße, dann je Pixel der Szene aus ihr geholt (runde Ecken: 3 von 63 mm)
    const KW = K.width = Math.round(breit), KH = K.height = Math.round(lang);
    kg.filter = `brightness(${L.hell}) contrast(${L.kontrast}) saturate(${L.satt}) blur(${(L.unscharf * KW / 488).toFixed(2)}px)`; kg.drawImage(im, 0, 0, KW, KH); kg.filter = 'none';
    const kd = kg.getImageData(0, 0, KW, KH).data, inv = zurueck(hin(e)), x0 = Math.floor(Math.min(...e.map(p => p[0]))), y0 = Math.floor(Math.min(...e.map(p => p[1])));
    const bw = Math.ceil(Math.max(...e.map(p => p[0]))) - x0 + 1, bh = Math.ceil(Math.max(...e.map(p => p[1]))) - y0 + 1, sd = sg.getImageData(x0, y0, bw, bh), o = sd.data;
    for (let y = 0, p = 0; y < bh; y++) for (let x = 0; x < bw; x++, p += 4) {
      const [u, v] = ab(inv, x0 + x + .5, y0 + y + .5);
      if (u < 0 || v < 0 || u >= 1 || v >= 1) continue;
      const du = Math.min(u, 1 - u) * 63, dv = Math.min(v, 1 - v) * 88;
      if (du < 3 && dv < 3 && Math.hypot(3 - du, 3 - dv) > 3) continue;
      const X = Math.min(KW - 1.001, Math.max(0, u * KW - .5)), Y = Math.min(KH - 1.001, Math.max(0, v * KH - .5)), xi = X | 0, yi = Y | 0, ax = X - xi, ay = Y - yi, i = (yi * KW + xi) * 4;
      for (let k = 0; k < 3; k++) o[p + k] = (kd[i + k] * (1 - ax) + kd[i + 4 + k] * ax) * (1 - ay) + (kd[i + KW * 4 + k] * (1 - ax) + kd[i + KW * 4 + 4 + k] * ax) * ay;
    }
    sg.putImageData(sd, x0, y0);
    const m = hin(e);
    if (rnd() < hand) {  // Daumen: von unten auf den unteren Rand oder von der Seite auf die untere Hälfte des Seitenrands
      const unten = rnd() < .6, [hx, hy] = unten ? ab(m, zw(.2, .8), 1.12) : ab(m, rnd() < .5 ? -.1 : 1.1, zw(.6, .85));
      sg.fillStyle = `rgb(${zw(170, 230) | 0},${zw(125, 175) | 0},${zw(95, 145) | 0})`; sg.beginPath();
      sg.ellipse(hx, hy, (unten ? .1 : .28) * breit, (unten ? .22 : .1) * lang, Math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0]) + um(20, 1) * Math.PI / 180, 0, 2 * Math.PI); sg.fill();
    }
    sg.globalCompositeOperation = 'multiply'; sg.fillStyle = `rgb(${L.stich.join()})`; sg.fillRect(0, 0, W, H);  // Farbstich der Lampe
    sg.globalCompositeOperation = 'lighter';  // Spiegelung auf Hülle oder Foil
    const [gx, gy] = ab(m, L.glanz[0], L.glanz[1] * .6), gr = L.glanz[2] * breit / 488, gl = sg.createRadialGradient(gx, gy, 0, gx, gy, gr);
    gl.addColorStop(0, `rgba(255,255,255,${L.glanz[3]})`); gl.addColorStop(1, 'rgba(255,255,255,0)'); sg.fillStyle = gl; sg.fillRect(0, 0, W, H);
    sg.globalCompositeOperation = 'source-over';
    rauschen(sg, W, H);
    return {e, W, H, grund, breit};
  }
  function imRahmen(im, L) {  // wie scan_eval.js: die Karte füllt das Bild, leicht daneben
    const W = 488, H = 680;
    pg.setTransform(1, 0, 0, 1, 0, 0); pg.globalCompositeOperation = 'source-over'; pg.filter = 'none';
    pg.fillStyle = `rgb(${40 + rnd() * 60 | 0},${35 + rnd() * 50 | 0},${30 + rnd() * 40 | 0})`; pg.fillRect(0, 0, W, H);
    pg.filter = `brightness(${L.hell}) contrast(${L.kontrast}) saturate(${L.satt}) blur(${L.unscharf}px)`;
    pg.translate(W / 2 + um(.03, lage) * W, H / 2 + um(.03, lage) * H); pg.rotate(um(4, lage) * Math.PI / 180); const s = 1 + um(.05, lage); pg.scale(s, s);
    pg.drawImage(im, -W / 2, -H / 2, W, H);
    pg.setTransform(1, 0, 0, 1, 0, 0); pg.filter = 'none';
    pg.globalCompositeOperation = 'multiply'; pg.fillStyle = `rgb(${L.stich.join()})`; pg.fillRect(0, 0, W, H);
    pg.globalCompositeOperation = 'lighter';
    const gl = pg.createRadialGradient(L.glanz[0] * W, L.glanz[1] * H * .6, 0, L.glanz[0] * W, L.glanz[1] * H * .6, L.glanz[2]);
    gl.addColorStop(0, `rgba(255,255,255,${L.glanz[3]})`); gl.addColorStop(1, 'rgba(255,255,255,0)'); pg.fillStyle = gl; pg.fillRect(0, 0, W, H);
    pg.globalCompositeOperation = 'source-over';
    rauschen(pg, W, H);
  }
  let anderes = null;
  for (let k = 0; k < n && karten.length; k++) {
    const karte = karten.splice(Math.floor(rnd() * karten.length), 1)[0];
    let im;
    try { im = await laden(karte.image); } catch { continue; }
    const L = {hell: 1 + um(.35), kontrast: 1 + um(.2), satt: 1 + um(.3), unscharf: Math.abs(um(1.5)), stich: [235 + um(20) | 0, 235 + um(20) | 0, 235 + um(20) | 0], glanz: [rnd(), rnd(), 60 + rnd() * 120, (.15 + rnd() * .35) * licht]};
    imRahmen(im, L);
    let t0 = performance.now();
    const r = await erkennen.rahmen(P, 244, 340, 488, 680, karte.wahr);
    ms.rahmen.push(performance.now() - t0);
    const s = szene(im, L, anderes);
    anderes = im;
    t0 = performance.now();
    const vier = karteFinden(S, s.W, s.H);
    ms.finden.push(performance.now() - t0);
    // Abstand der Ecken zur Wahrheit, als Kartenrand und als innerer Rahmen (Karte um FIND_RAND größer)
    const [rs, ro, ru] = FIND_RAND, abstand = ecken => Math.max(...ecken.map(([x, y], i) => Math.hypot(x - s.e[i][0], y - s.e[i][1]))) / s.breit;
    const fehl = vier.map(v => { const m = hin(v.e); return Math.min(abstand(v.e), abstand([[-rs, -ro], [1 + rs, -ro], [1 + rs, 1 + ru], [-rs, 1 + ru]].map(([u, w]) => ab(m, u, w)))); });
    const da = fehl.some(x => x <= .04);
    if (zeig === k) {
      sg.lineWidth = 3; vier.forEach((v, i) => { sg.strokeStyle = ['#0f0', '#ff0', '#f0f'][i]; vieleck(sg, v.e); sg.stroke(); });
      sg.strokeStyle = '#0ff'; sg.lineWidth = 1; vieleck(sg, s.e); sg.stroke();
      S.style.cssText = 'display:block;max-width:100%;margin:1rem auto'; S.id = 'finden-szene'; document.getElementById('finden-szene')?.remove(); document.body.append(S);
      return {grund: s.grund, vierecke: vier, eckfehler: fehl, wahr: s.e, name: karte.name};
    }
    t0 = performance.now();
    const fr = await erkennen.frei(S, vier, karte.wahr);
    ms.frei.push(performance.now() - t0);
    proben++; vierecke += vier.length; gefunden += da; erstes += fehl[0] <= .04;
    if (da) eckfehler.push(Math.min(...fehl));
    zaehl(res.rahmen, r); zaehl(res.frei, fr);
    const g = gruende[s.grund] = gruende[s.grund] || {n: 0, gefunden: 0, top1: 0};
    g.n++; g.gefunden += da; g.top1 += fr.pos === 0;
    if ((!da || fr.pos !== 0) && fehler.length < 30) fehler.push(`${k} ${karte.name} (${s.grund}, ${s.W > s.H ? 'quer' : 'hoch'}): ${vier.length} Vierecke, ${da ? 'gefunden' : 'nicht gefunden' + (fehl.length ? ' (' + Math.min(...fehl).toFixed(3) + ')' : '')}, frei ${fr.urteil} ${fr.vorn || ''}, im Rahmen ${r.urteil}${r.pos === 0 ? ' richtig' : ''}`);
  }
  return {at: new Date().toISOString(), verfahren: 'Karte frei im Bild', quelle: `künstliche Szenen (licht ${licht}, lage ${lage}, hand ${hand}, seed ${seed})`, erkennung: server ? 'Server, alle Karten' : 'Browser, eigene Sammlung', fp: FP_V, proben,
          gefunden: +(gefunden / proben).toFixed(3), gefundenErstes: +(erstes / proben).toFixed(3), viereckeJeBild: +(vierecke / proben).toFixed(2), eckfehler: [.5, .9].map(p => q(eckfehler, p)),
          frei: quote(res.frei), rahmen: quote(res.rahmen), unterschiedTop1: +((res.frei.top1 - res.rahmen.top1) / proben).toFixed(3),
          gruende: Object.fromEntries(Object.entries(gruende).map(([k, g]) => [k, {n: g.n, gefunden: +(g.gefunden / g.n).toFixed(3), top1: +(g.top1 / g.n).toFixed(3)}])),
          ms: Object.fromEntries(Object.entries(ms).map(([k, v]) => [k, {p50: q(v, .5), p95: q(v, .95)}])), fehler};
}
