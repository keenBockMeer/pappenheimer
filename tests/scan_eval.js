// Phase 24: Trefferquote des Scanners an verzerrten Scryfall-Bildern. Nicht Teil von pytest.
// In der Browser-Konsole der App einfügen (nach dem Index-Job, Ansicht „Scannen“), dann: await scanEval(300)
// Set-Modus (Phase 25, Erfassen): erst unter Scannen, Erfassen die Sets vorbereiten, dann: await scanEval(300, {sets: 'DSK,DSC'})
// Dort zählt jeder Druck für sich (verschieden = anderer Druck), „gleicherDruck“ ist dann dasselbe wie top1.
// licht und lage (0 bis 1) skalieren die Verzerrung von Licht, Farbe, Unschärfe und Spiegelung bzw. von Versatz, Drehung und Größe.
// Probe = großes Scryfall-Bild (normal, andere Auflösung als der Index) gedreht, verschoben, skaliert, mit anderem Licht,
// Farbstich, Unschärfe, Spiegelung und Rauschen, so wie die Kamera es im Rahmen sieht. „Fremd“ = beste andere Karte, wenn die
// richtige aus dem Index ausgeblendet ist: so punktet eine Karte, die nicht in der Sammlung ist.
async function scanEval(n = 300, {seed = 7, licht = 1, lage = 1, sets = ''} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = (x, f = licht) => (rnd() * 2 - 1) * x * f;
  const laden = u => new Promise((ok, err) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = err; im.src = u; });
  const r = await api('scan?v=' + FP_V + (sets ? '&set=' + encodeURIComponent(sets) : ''));
  const ix = fpIndex(sets ? {...r, keys: r.ids} : r), key = ix.keys || ix.oids;
  const karte = j => sets ? r.drucke[ix.ids[j]] : ix.karten[ix.oids[j]];  // Name und Bild
  const W = 488, H = 680, c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d', {willReadFrequently: true});
  const res = {proben: 0, top1: 0, top3: 0, druck: 0, richtig: [], fremd: [], ms: 0, fehler: []};
  for (let k = 0; k < n; k++) {
    const j = Math.floor(rnd() * ix.n), oid = key[j];
    let im;
    try { im = await laden(karte(j).image); } catch { continue; }
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
    const t0 = performance.now(), best = fpSuche(ix, c, W / 2, H / 2, W, H, FP_KANDIDATEN);  // wie die Kamera, alle Kandidaten sortiert
    res.ms += performance.now() - t0;
    res.proben++;
    const pos = best.findIndex(b => b.oid === oid);
    if (pos && res.fehler.length < 12) res.fehler.push(`${karte(j).name} → ${karte(best[0].i).name} (${best[0].score.toFixed(2)}, richtig ${pos < 0 ? 'nicht dabei' : best[pos].score.toFixed(2)})`);
    res.top1 += pos === 0; res.top3 += pos >= 0 && pos < 3; res.druck += best[0].i === j;
    res.richtig.push(pos >= 0 ? best[pos].score : 0); res.fremd.push(best.find(b => b.oid !== oid).score);
  }
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(3); };
  const schwelle = q(res.fremd, .95);
  return {proben: res.proben, top1: +(res.top1 / res.proben).toFixed(3), top3: +(res.top3 / res.proben).toFixed(3), gleicherDruck: +(res.druck / res.proben).toFixed(3),
          richtig: [.05, .25, .5].map(p => q(res.richtig, p)), fremd: [.5, .95, .99].map(p => q(res.fremd, p)),
          schwelle, ueberSchwelle: +(res.richtig.filter(x => x > schwelle).length / res.proben).toFixed(3), msJeSuche: +(res.ms / res.proben).toFixed(1), fehler: res.fehler};
}
