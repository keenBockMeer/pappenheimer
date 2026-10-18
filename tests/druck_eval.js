// Phase 58, Stufe 1: Lässt sich der Druck einer erkannten Karte an der Zeile unten links (Sammlernummer, Seltenheit, Set-Kürzel, Sprache)
// unter den wenigen Drucken mit demselben Bild bestimmen? Nur Messung, die App ändert sich nicht. Nicht Teil von pytest.
// Am Rechner in der Browser-Konsole der App einfügen (Ansicht „Scannen“, Erfassen, Katalog mit Fingerabdrücken vorbereitet), dann:
//   await druckEval(150)                    je Probe ein Aussehen mit Rahmen 2015, das es in mehreren Drucken gibt (dort rät die App heute)
//   await druckEval(150, {zeile: [5, 8, 12, 17]})
// Ergebnis als JSON: copy(JSON.stringify(await druckEval(150), null, 1))
// Zeilenhöhe zeile in Punkten des Kamerabilds (eine Zeile ist rund 1,1 mm hoch, an Scryfall-Bildern gemessen): 5 = Karte 280 px breit wie die
// Messbilder, 12 = 1080p quer mit der Karte im Rahmen, 17 = 1080p hochkant. Kamera-Streifen: das große Bild (672 px) des richtigen Drucks auf diese
// Größe, unscharf, mit Licht, Rauschen und Versatz unter einem Pixel, je Probe bilder Bilder (summiert, ein Bild entscheidet nichts).
// Kandidaten: die Drucke mit demselben Aussehen, wie sie die Suche nennt (der gewählte und bis zu sechs weitere, katalog.WAHL).
// Weg A: Kürzel und Nummer jedes Kandidaten als Text gezeichnet (weiß auf schwarz, fette serifenlose Schrift, Lage wie der Aufdruck).
// Weg B: derselbe Streifen aus dem normalen Bild (488 px) jedes Kandidaten. Vergleich: normierte Korrelation, bis zu 2 Punkte Versatz.
// richtig/falsch: der beste Kandidat liegt mindestens abstand vor dem zweiten, sonst offen (die App fragt wie heute).
// Grenze: Kamera und Referenz stammen bei B aus demselben Scan von Scryfall; echte Kamerabilder (Messbilder) fehlen, B ist hier eine obere Grenze.
async function druckEval(n = 150, {seed = 57, zeile = [5, 8, 12, 17], bilder = 3, abstand = .05} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = x => (rnd() * 2 - 1) * x;
  const laden = u => new Promise((ok, err) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const ZONE = [.04, .925, .4, .975], MM = 1.1;  // Streifen als Anteil der Karte (x0, y0, x1, y1), Zeilenhöhe in mm
  const breite = L => Math.round(63 * L / MM);  // Kartenbreite in Punkten bei Zeilenhöhe L
  // Streifen aus einem Kartenbild in Kartenbreite W -> {w, h, px} grau; verzerrt: wie die Kamera
  const streifen = (im, W, verzerrt) => {
    const H = Math.round(W * 88 / 63), c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d', {willReadFrequently: true});
    g.imageSmoothingQuality = 'high';
    if (verzerrt) { g.filter = `blur(${(.4 + rnd() * .8).toFixed(2)}px) brightness(${1 + um(.25)}) contrast(${1 + um(.2)})`; g.translate(um(.5), um(.5)); g.rotate(um(.6) * Math.PI / 180); }
    g.drawImage(im, 0, 0, W, H); g.setTransform(1, 0, 0, 1, 0, 0); g.filter = 'none';
    const x0 = Math.round(ZONE[0] * W), y0 = Math.round(ZONE[1] * H), w = Math.round((ZONE[2] - ZONE[0]) * W), h = Math.round((ZONE[3] - ZONE[1]) * H);
    const d = g.getImageData(x0, y0, w, h).data, px = new Float32Array(w * h);
    for (let i = 0; i < px.length; i++) px[i] = (d[i * 4] + d[i * 4 + 1] + d[i * 4 + 2]) / 3 + (verzerrt ? um(8) : 0);
    return {w, h, px};
  };
  // Weg A: Text an der Stelle des Aufdrucks (Zeile 1: Nummer, Zeile 2: Kürzel und Sprache), in derselben Größe wie streifen()
  const text = (d, W) => {
    const H = Math.round(W * 88 / 63), w = Math.round((ZONE[2] - ZONE[0]) * W), h = Math.round((ZONE[3] - ZONE[1]) * H), c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d', {willReadFrequently: true}), L = W * MM / 63;
    g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff'; g.font = `bold ${L.toFixed(1)}px sans-serif`; g.textBaseline = 'alphabetic';
    g.fillText(String(d.number).padStart(4, '0'), .005 * W, (.945 - ZONE[1]) * H); g.fillText(`${d.set_code} • EN`, .005 * W, (.966 - ZONE[1]) * H);
    const px = new Float32Array(w * h), dd = g.getImageData(0, 0, w, h).data;
    for (let i = 0; i < px.length; i++) px[i] = dd[i * 4];
    return {w, h, px};
  };
  const ncc = (k, r, dx, dy) => {  // Kamera k gegen Referenz r, r um (dx, dy) versetzt; nur die Überlappung
    let s1 = 0, s2 = 0, q1 = 0, q2 = 0, p = 0, n = 0;
    for (let y = Math.max(0, dy); y < Math.min(k.h, r.h + dy); y++) for (let x = Math.max(0, dx); x < Math.min(k.w, r.w + dx); x++) {
      const u = k.px[y * k.w + x], v = r.px[(y - dy) * r.w + x - dx]; s1 += u; s2 += v; q1 += u * u; q2 += v * v; p += u * v; n++;
    }
    const c = p / n - s1 / n * s2 / n, d = Math.sqrt(Math.max(q1 / n - (s1 / n) ** 2, 1e-6) * Math.max(q2 / n - (s2 / n) ** 2, 1e-6));
    return c / d;
  };
  const best = (k, r) => { let b = -1; for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) b = Math.max(b, ncc(k, r, dx, dy)); return b; };
  const druckId = u => u.match(/\/([0-9a-f-]{36})\.jpg/)?.[1];

  const probe = (await api(`scan/katalog?v=${FP_V}&probe=${Math.min(5000, n * 12)}`)).probe.filter(p => /:2015$/.test(p.id));
  const res = Object.fromEntries(zeile.map(L => [L, {A: {richtig: 0, falsch: 0, offen: 0}, B: {richtig: 0, falsch: 0, offen: 0}}])), kand = [], fehler = [];
  let proben = 0;
  for (const p of probe.sort(() => rnd() - .5)) {
    if (proben >= n) break;
    let im;
    try { im = await laden(p.image); } catch { continue; }
    const fp = fpLagen(im, im.naturalWidth / 2, im.naturalHeight / 2, im.naturalWidth, im.naturalHeight);
    if (!fp.length) continue;
    const r = await post('scan/suche', {v: FP_V, fp, pruef: p.id}), t = r.treffer.find(x => x.aussehen === p.id);
    const wahr = druckId(p.image), alle = t ? [t.druck, ...t.drucke].filter((d, i, xs) => d.aussehen === p.id && xs.findIndex(e => e.id === d.id) === i) : [];
    if (alle.length < 2 || !alle.some(d => d.id === wahr)) continue;
    let gross, refs;
    try { gross = await laden(p.image.replace('/normal/', '/large/')); refs = await Promise.all(alle.map(d => laden(d.image))); } catch { continue; }
    proben++; kand.push(alle.length);
    for (const L of zeile) {
      const W = breite(L), sumA = alle.map(() => 0), sumB = alle.map(() => 0), refB = refs.map(x => streifen(x, W, false)), refA = alle.map(d => text(d, W));
      for (let b = 0; b < bilder; b++) {
        const k = streifen(gross, W, true);
        alle.forEach((d, i) => { sumA[i] += best(k, refA[i]); sumB[i] += best(k, refB[i]); });
      }
      for (const [weg, sum] of [['A', sumA], ['B', sumB]]) {
        const o = sum.map((v, i) => [v / bilder, alle[i].id]).sort((x, y) => y[0] - x[0]);
        const urteil = o[0][0] - o[1][0] < abstand ? 'offen' : o[0][1] === wahr ? 'richtig' : 'falsch';
        res[L][weg][urteil]++;
        if (urteil === 'falsch' && fehler.length < 30) fehler.push(`${p.name} ${weg} bei ${L} px: ${alle.find(d => d.id === o[0][1]).set_code} statt ${alle.find(d => d.id === wahr).set_code} (${o[0][0].toFixed(2)} zu ${o[1][0].toFixed(2)})`);
      }
    }
  }
  const quote = g => Object.fromEntries(Object.entries(g).map(([k, v]) => [k, proben ? +(v / proben).toFixed(3) : 0]));
  const s = [...kand].sort((x, y) => x - y), q = f => s.length ? s[Math.min(s.length - 1, Math.floor(f * s.length))] : null;
  return {at: new Date().toISOString(), verfahren: 'Druck durch Ausschluss (Stufe 1)', seed, bilder, abstand, proben, kandidaten: {p50: q(.5), p90: q(.9), max: s.at(-1)},
          zeile: Object.fromEntries(zeile.map(L => [L, {kartenbreite: breite(L), A: quote(res[L].A), B: quote(res[L].B)}])), fehler};
}
