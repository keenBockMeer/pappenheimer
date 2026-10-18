// Phase 32: Trefferquote der Erkennung ohne Set-Wahl (Suche auf dem Server über alle Kartenbilder, POST /api/scan/suche). Nicht Teil von pytest.
// Am Rechner in der Browser-Konsole der App einfügen (Ansicht „Scannen“, Kartenbilder vorbereitet), dann eins von beiden:
//   await sucheEval(300)                     verzerrte Scryfall-Bilder wie in scan_eval.js: licht und lage (0 bis 1) skalieren die Verzerrung
//   await sucheEval(0, {messbilder: true})   die Messbilder aus Phase 30 (echte Kamerabilder mit Etikett), Ausschnitt wie die Kamera (scanBild)
// Ergebnis als JSON zum Ablegen und Vergleichen: copy(JSON.stringify(await sucheEval(300), null, 1))
// lagen: so viele Lagen je Anfrage (1 bis 5, Standard alle aus FP_VOR). Die Schwellen und das Urteil stehen im Server (katalog.suche).
// top1 = bestes Aussehen ist das richtige, top1Bild = es zeigt dasselbe Bild (anderer Rahmen erlaubt: Die Drucke stehen dann zur Wahl),
// top3Bild = das Bild ist unter den drei Treffern. Dazu das Urteil, zusammen 1: sicherRichtig (zählt von selbst), sicherFalsch („sicher, aber
// falsch“), unsicher (die App fragt), nichts. grob200 = das richtige Aussehen hat die Grobsuche überstanden. msServer = Rechenzeit der Suche,
// msAnfrage = mit Hin- und Rückweg. wert = Kosinus des richtigen Treffers, zweiter = der beste andere, abstand = dazwischen (je 5 %, 25 %, 50 %).
// Messbilder: Dort zählt die Karte (Name des Etiketts) als richtig, druck = genau der Druck des Etiketts mit seinem Set als Vorliebe.
// Phase 56: folge: N (2 bis 12) zeigt jede Karte N Bilder lang, wie sie ruhig im Rahmen liegt (das erste Bild ist die Probe von oben, die
// übrigen dieselbe Szene mit eigenem Rauschen und leichtem Wackeln, zitter skaliert es) und spielt die Folgen durch Konsens (ui/zaehler.js):
// konsens.aus = zwei sichere nacheinander (wie vor Phase 56), konsens.an = Schnell zählen mit den Schwellen KONS_*.server, je mit bilder bis
// zur Zählung (Median, 90 %), falsch (das gezählte Bild zeigt eine andere Karte) und nicht gezählt; msBild = eine Anfrage, bilderJeSekunde =
// Bilder, die scanLoop so schafft (Anfrage plus Pause von 120 ms). Die Folgen selbst stehen in folgen (für konsensMessen mit anderen Schwellen).
async function sucheEval(n = 300, {seed = 7, licht = 1, lage = 1, lagen = FP_VOR.length, messbilder = false, folge = 0, zitter = 1} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = (x, f = licht) => (rnd() * 2 - 1) * x * f;
  const laden = (u, cors) => new Promise((ok, err) => { const im = new Image(); if (cors) im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const bild = x => x.split(':')[0];
  const FELDER = ['top1', 'top1Bild', 'top3Bild', 'sicherRichtig', 'sicherFalsch', 'unsicher', 'nichts', 'grob200', 'druck'];
  const res = Object.fromEntries(FELDER.map(k => [k, 0])), ms = [], weg = [], wert = [], zweiter = [], abstand = [], fehler = [];
  let proben = 0, eintraege = 0;
  const folgen = [], msBild = [];
  const frage = async (fp, wahr, name, extra = {}, folgeBild = null) => {  // wahr: Aussehen (verzerrte Bilder) bzw. null (Messbilder: dort zählt der Name)
    if (folgeBild) {  // ein weiteres Bild der Folge: nur für Konsens, nicht in den Zahlen oben
      if (!fp.length) return folgeBild.push({urteil: 'leer', ruhig: true, bei: null, richtig: false});
      const t0 = performance.now(), r = await nochmal(() => post('scan/suche', {v: FP_V, fp: fp.slice(0, lagen), ...extra})), t = r.treffer[0];
      msBild.push(performance.now() - t0);
      return folgeBild.push({urteil: r.urteil, id: t?.druck.id, oid: t?.druck.oid, wert: t?.wert, abstand: t?.abstand, ruhig: true, bei: null, richtig: !!t && bild(t.aussehen) === bild(wahr)});
    }
    if (!fp.length) { proben++; res.nichts++; return; }
    const t0 = performance.now(), r = await nochmal(() => post('scan/suche', {v: FP_V, fp: fp.slice(0, lagen), ...(wahr ? {pruef: wahr} : {}), ...extra}));
    weg.push(performance.now() - t0); ms.push(r.ms); proben++; eintraege = r.n;
    const t = r.treffer, passt = x => wahr ? bild(x.aussehen) === bild(wahr) : x.druck.name === name, pos = t.findIndex(passt);
    res.top1 += wahr ? t[0]?.aussehen === wahr : pos === 0; res.top1Bild += pos === 0; res.top3Bild += pos >= 0; res.grob200 += r.grob != null;
    res.sicherRichtig += r.urteil === 'sicher' && pos === 0; res.sicherFalsch += r.urteil === 'sicher' && pos !== 0;
    res.unsicher += r.urteil === 'unsicher'; res.nichts += r.urteil === 'nichts';
    if (pos === 0) { wert.push(t[0].wert); abstand.push(t[0].abstand); if (t[1]) zweiter.push(t[1].wert); }
    else if (fehler.length < 30) fehler.push(`${name}: ${r.urteil}, vorn ${t[0] ? `${t[0].druck.name} (${t[0].druck.set_code}) ${t[0].wert.toFixed(2)}` : 'nichts'}, richtig ${pos < 0 ? 'nicht unter den drei' : t[pos].wert.toFixed(2)}${wahr ? `, grob ${r.grob ?? 'verloren'}` : ''}`);
    return r;
  };
  if (messbilder) {
    for (const m of (await api('messbilder')).items.filter(x => x.scryfall_id)) {
      const im = await laden(`/api/messbild/${m.id}.jpg`), [x, y, w, h] = m.rahmen.length ? m.rahmen : Object.values(scanRahmen(m.breite, m.hoehe));
      const r = await frage(fpLagen(...scanBild(im, {x, y, w, h})), null, m.name, {sets: [m.set_code]});
      res.druck += r?.treffer[0]?.druck.id === m.scryfall_id;
    }
  } else {
    const W = 488, H = 680, c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d', {willReadFrequently: true}), probe = (await api(`scan/katalog?v=${FP_V}&probe=${Math.min(5000, n * 4)}`)).probe;
    const zeichnen = im => {
      g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = 'source-over'; g.filter = 'none';
      g.fillStyle = `rgb(${40 + rnd() * 60 | 0},${35 + rnd() * 50 | 0},${30 + rnd() * 40 | 0})`; g.fillRect(0, 0, W, H);  // Tisch
      g.filter = `brightness(${1 + um(.35)}) contrast(${1 + um(.2)}) saturate(${1 + um(.3)}) blur(${Math.abs(um(1.5))}px)`;
      g.translate(W / 2 + um(.03, lage) * W, H / 2 + um(.03, lage) * H); g.rotate(um(4, lage) * Math.PI / 180); const s = 1 + um(.05, lage); g.scale(s, s);
      g.drawImage(im, -W / 2, -H / 2, W, H);
      g.setTransform(1, 0, 0, 1, 0, 0); g.filter = 'none';
      g.globalCompositeOperation = 'multiply';  // Farbstich der Lampe
      g.fillStyle = `rgb(${235 + um(20) | 0},${235 + um(20) | 0},${235 + um(20) | 0})`; g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = 'lighter';  // Spiegelung auf Hülle oder Foil
      const gx = rnd() * W, gy = rnd() * H * .6, gr = 60 + rnd() * 120, gl = g.createRadialGradient(gx, gy, 0, gx, gy, gr);
      gl.addColorStop(0, `rgba(255,255,255,${(.15 + rnd() * .35) * licht})`); gl.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gl; g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = 'source-over';
      const d = g.getImageData(0, 0, W, H);
      for (let i = 0; i < d.data.length; i += 4) { const z = um(8); d.data[i] += z; d.data[i + 1] += z; d.data[i + 2] += z; }
      g.putImageData(d, 0, 0);
    };
    for (let k = 0; k < n && probe.length; k++) {
      globalThis.evalStand = {k, n};  // Fortschritt, von außen lesbar
      const p = probe.splice(Math.floor(rnd() * probe.length), 1)[0];
      let im;
      try { im = await laden(p.image, true); } catch { continue; }
      const a0 = a;
      zeichnen(im);
      const r = await frage(fpLagen(c, W / 2, H / 2, W, H), p.id, p.name);
      if (!folge) continue;
      const a1 = a, f = [], t = r?.treffer[0];
      f.push(r ? {urteil: r.urteil, id: t?.druck.id, oid: t?.druck.oid, wert: t?.wert, abstand: t?.abstand, ruhig: true, bei: null, richtig: !!t && bild(t.aussehen) === bild(p.id)}
        : {urteil: 'leer', ruhig: true, bei: null, richtig: false});
      for (let i = 1; i < folge; i++) {
        a = a0; zeichnen(im); wackeln(c, g, seed * 7919 + k * 31 + i, zitter);  // dieselbe Szene, eigenes Rauschen
        await frage(fpLagen(c, W / 2, H / 2, W, H), p.id, p.name, {}, f);
      }
      folgen.push(f); a = a1;
    }
  }
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(3) : null; };
  return {at: new Date().toISOString(), verfahren: 'ohne Set-Wahl (Server)', quelle: messbilder ? 'Messbilder' : `verzerrte Scryfall-Bilder (licht ${licht}, lage ${lage}, seed ${seed})`,
          fp: FP_V, lagen, eintraege, proben, ...Object.fromEntries(FELDER.filter(k => messbilder ? k !== 'grob200' : k !== 'druck').map(k => [k, proben ? +(res[k] / proben).toFixed(3) : 0])),
          msServer: {p50: q(ms, .5), p95: q(ms, .95), max: q(ms, 1)}, msAnfrage: {p50: q(weg, .5), p95: q(weg, .95)},
          wert: [.05, .25, .5].map(p => q(wert, p)), zweiter: [.5, .95, .99].map(p => q(zweiter, p)), abstand: [.05, .25, .5].map(p => q(abstand, p)), fehler,
          ...(folge ? {folge, zitter, konsens: konsensMessen(folgen, 'server'), msBild: {p50: q(msBild, .5), p95: q(msBild, .95)},
                       bilderJeSekunde: msBild.length ? +(1000 / (120 + msBild.reduce((x, y) => x + y, 0) / msBild.length)).toFixed(1) : null, folgen} : {})};  // mit der Pause von scanLoop
}

// Phase 56, auch für finden_eval.js: eine Anfrage, die am Netz scheitert (der Server unter Last), bis zu viermal neu; anderes geht durch
async function nochmal(f) {
  for (let i = 0; ; i++) {
    try { return await f(); } catch (e) { if (i >= 4 || !(e instanceof TypeError)) throw e; await new Promise(r => setTimeout(r, 1500)); }
  }
}

// Phase 56, auch für finden_eval.js: dieselbe Szene als nächstes Bild der Kamera, die Karte liegt ruhig. Leichtes Wackeln der Hand
// (Versatz bis 0,4 % der Breite, Drehung bis 0,3°), Helligkeit bis 4 % und eigenes Rauschen; zitter skaliert es, r ist der Startwert.
function wackeln(c, g, r, zitter = 1) {
  const rnd = () => { r |= 0; r = r + 0x6D2B79F5 | 0; let t = Math.imul(r ^ r >>> 15, 1 | r); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = x => (rnd() * 2 - 1) * x * zitter, W = c.width, H = c.height, k = document.createElement('canvas');
  k.width = W; k.height = H; k.getContext('2d').drawImage(c, 0, 0);
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = 'source-over'; g.filter = `brightness(${1 + um(.04)})`;
  g.translate(W / 2 + um(.004) * W, H / 2 + um(.004) * W); g.rotate(um(.3) * Math.PI / 180); g.drawImage(k, -W / 2, -H / 2);
  g.setTransform(1, 0, 0, 1, 0, 0); g.filter = 'none';
  const d = g.getImageData(0, 0, W, H);
  for (let i = 0; i < d.data.length; i += 4) { const z = um(6); d.data[i] += z; d.data[i + 1] += z; d.data[i + 2] += z; }
  g.putImageData(d, 0, 0);
}

// Phase 56, auch für finden_eval.js: Bildfolgen ([{urteil, id, wert, abstand, ruhig, bei, richtig}] je Karte) durch Konsens, aus und an, mit
// den Schwellen von weg (lokal, server) oder eigenen (schwellen: sofortWert, sofortAbstand, gestuetztWert, gestuetztAbstand). Gezählt wird je
// Folge das erste Bild, bei dem Konsens zählt; falsch heißt, dieses Bild zeigt eine andere Karte. bilder = bis zur Zählung (Median, 90 %).
// sofort und gestuetzt: Anteil der Bilder dieser Stufe, falschSofort: Bilder der Stufe sofort mit falscher Karte (muss 0 sein).
function konsensMessen(folgen, weg, schwellen = {}) {
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : null; };
  const opt = schnell => ({schnell, sofortWert: KONS_SOFORT_WERT[weg], sofortAbstand: KONS_SOFORT_ABSTAND[weg], gestuetztWert: KONS_GESTUETZT_WERT[weg], gestuetztAbstand: KONS_GESTUETZT_ABSTAND[weg], ...schwellen});
  const aus = Object.fromEntries([['aus', false], ['an', true]].map(([name, schnell]) => {
    const bis = [], stufen = {sofort: 0, gestuetzt: 0, falschSofort: 0, falschGestuetzt: 0};
    let falsch = 0, nicht = 0;
    for (const f of folgen) {
      const kons = new Zaehler.Konsens(opt(schnell));
      let i = -1;
      f.forEach((b, j) => { const r = kons.bild(b); if (r.stand === 'sofort' || r.stand === 'gestuetzt') { stufen[r.stand]++; if (!b.richtig) stufen[r.stand === 'sofort' ? 'falschSofort' : 'falschGestuetzt']++; } if (r.zaehlen && i < 0) i = j; });
      if (i < 0) nicht++; else { bis.push(i + 1); falsch += !f[i].richtig; }
    }
    const bilder = folgen.flat().length || 1;
    return [name, {folgen: folgen.length, gezaehlt: bis.length, falsch, nicht, bilder: {p50: q(bis, .5), p90: q(bis, .9), mittel: bis.length ? +(bis.reduce((x, y) => x + y, 0) / bis.length).toFixed(2) : null},
                   ...(schnell ? {sofort: +(stufen.sofort / bilder).toFixed(3), gestuetzt: +(stufen.gestuetzt / bilder).toFixed(3), falschSofort: stufen.falschSofort, falschGestuetzt: stufen.falschGestuetzt} : {})}];
  }));
  return {...aus, schwellen: opt(true)};
}
