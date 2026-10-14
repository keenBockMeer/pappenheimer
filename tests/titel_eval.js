// Phase 35 (PLAN E21): Wie oft liest der Server den Namen der Karte richtig (POST /api/scan/titel), und was wird damit aus der Suche? Nicht Teil
// von pytest. Am Rechner in der Browser-Konsole der App einfügen (Ansicht „Scannen“; der Server braucht Tesseract, die Kartenbilder müssen
// vorbereitet und die deutschen Namen geladen sein: mtg katalog --namen), dann zum Beispiel:
//   await titelEval(300)                      englische Karten, verzerrte Scryfall-Bilder, die Karte 420 px breit
//   await titelEval(300, {lang: 'de'})        deutsche Karten (Bilder deutscher Drucke bei Scryfall)
//   await titelEval(300, {karte: 280})        die Karte kleiner im Bild, wie auf den ersten Messbildern
//   await titelEval(300, {suche: true})       dazu die Suche ohne Namen, mit gelesenem Namen und mit dem wahren Namen (Obergrenze)
//   await titelEval(300, {suche: true, lesen: false})   nur die Obergrenze, ohne Tesseract
//   await titelEval(0, {messbilder: true, suche: true})   die Messbilder aus Phase 30, erkannt wie von der Kamera, ohne und mit Namen
// Ergebnis als JSON zum Ablegen und Vergleichen: copy(JSON.stringify(await titelEval(300), null, 1))
// varianten: dieselben Proben mit mehreren Einstellungen lesen, je {name, psm, sprache (Tesseract), versuche: [{box, breite, kontrast}] (titelBild;
// die Streifen gehen zusammen in einer Anfrage, ohne Angabe TITEL_VERSUCHE wie bei der Kamera)}; die erste gilt für Gruppen, Suche und
// Fehlerliste. licht und lage (0 bis 1) skalieren die Verzerrung wie in suche_eval.js; lage .3 = Karte gefunden.
// Je Variante: vorn = der richtige Name steht vorn, unterFuenf = unter den genannten, sicherRichtig und sicherFalsch = das Urteil des Servers
// (katalog.namen_sicher), nichts = keine Zeile führte zu einem Namen; msServer = Lesen und Abgleich im Server je Karte, kb = Größe der Streifen.
// gruppen (erste Variante): nach Rahmen (englische Proben aus dem Aussehen, andere Sprachen aus dem Druck, etwa de2015), Kunstkarten für sich
// (Set-Kürzel A…: Sie haben keine Namenszeile).
// suche: Klassen sicherRichtig, sicherFalsch, unsicherRichtig (richtige Karte vorn, die App fragt), unsicherFalsch, nichts, je ohne Namen, mit
// gelesenem Namen (wie die Kamera: karten und sicher aus der Antwort des Lesens) und mit wahrem Namen; uebergaenge = von ohne nach mit. Das
// Urteil fällt der Server (katalog.suche: BILD_MIN, SUCHE_ABSTAND). msLesenUndSuchen = Lesen und die Suche mit Namen zusammen, im Server.
// roh nennt je Probe Werte und Abstände, um die Schwellen neu zu wählen.
// bildMitWahremNamen: Wie oft steht mit dem wahren Namen das richtige Bild vorn (Proben mit bekanntem Aussehen, ohne Standardländer)?
// druckzeile: liest bei Karten im Rahmen von 2015 auch die Zeile unten links und zählt, wie oft Set-Kürzel und Sammlernummer darin stehen.
// sammeln(probe, bild, rahmen): bekommt jede verzerrte Probe vor dem Lesen, etwa um Streifen anzusehen oder abzulegen.
// proben: eigene Liste statt der Probe aus dem Katalog, je {name (englisch), image, oid, id (Aussehen), gruppe, text (gedruckter Name)}, etwa Karten
// der eigenen Sammlung mit Rahmen und Layout als Gruppe.
// Messbilder: Gelesen wird je Viereck aus karteFinden und im Rahmen, die beste Lesung gilt; mit suche läuft die Erkennung wie in erfServer
// (Vierecke, dann der Rahmen), einmal ohne und einmal mit den gelesenen Namen. Gruppen nach Sprache und Merkmal des Etiketts.
async function titelEval(n = 300, {seed = 7, licht = 1, lage = .3, karte = 420, lang = 'en', varianten = [{}], suche = false, lesen = true, druckzeile = false,
                                   messbilder = false, sammeln = null, proben = null} = {}) {
  let a = seed;
  const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const um = (x, f = licht) => (rnd() * 2 - 1) * x * f;
  const laden = (u, cors) => new Promise((ok, err) => { const im = new Image(); if (cors) im.crossOrigin = 'anonymous'; im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const vorne = s => s.split(' // ')[0], gleich = (x, y) => x === y || vorne(x) === vorne(y);
  const q = (xs, p) => { const s = [...xs].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(3) : null; };
  const leer = () => ({proben: 0, vorn: 0, unterFuenf: 0, sicherRichtig: 0, sicherFalsch: 0, nichts: 0});
  const quote = z => Object.fromEntries(Object.entries(z).map(([k, v]) => [k, k === 'proben' ? v : z.proben ? +(v / z.proben).toFixed(3) : 0]));
  const zaehl = (z, t, name) => {
    const pos = t.namen.findIndex(x => gleich(x.name, name));
    z.proben++; z.vorn += pos === 0; z.unterFuenf += pos >= 0; z.sicherRichtig += t.sicher && pos === 0; z.sicherFalsch += t.sicher && pos !== 0; z.nichts += !t.namen.length;
    return pos;
  };
  const lies = async (src, g, v) => {  // Streifen schneiden und zusammen lesen lassen -> Antwort des Servers, dazu die Größe der Streifen
    const streifen = (v.versuche || TITEL_VERSUCHE).map(wie => titelBild(src, g, wie).toDataURL('image/jpeg', .9).split(',')[1]);
    return {...await post('scan/titel', {streifen, ...(v.psm ? {psm: v.psm} : {}), ...(v.sprache ? {sprache: v.sprache} : {})}), kb: streifen.join('').length * .75 / 1024};
  };
  const mitNamen = t => t.karten?.length ? {karten: t.karten, sicher: t.sicher ? t.namen[0].karten : []} : null;  // was die Kamera der Suche mitgibt
  const var_ = varianten.map((v, i) => ({v, name: v.name || JSON.stringify(v) || String(i), z: leer(), ms: [], kb: []}));
  const fehler = [], gruppen = {}, klassen = {ohne: {}, mit: {}, wahr: {}}, ueber = {}, roh = [], zusammen = [], zeile = {proben: 0, set: 0, nummer: 0, beide: 0};
  const LAND = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest'], bild = {proben: 0, richtig: 0};
  const klasse = (r, name) => r.urteil === 'nichts' || !r.treffer.length ? 'nichts' : (r.urteil === 'sicher' ? 'sicher' : 'unsicher') + (gleich(r.treffer[0].druck.name, name) ? 'Richtig' : 'Falsch');
  const plus = (o, k) => { o[k] = (o[k] || 0) + 1; };
  const anteil = o => { const s = Object.values(o).reduce((x, y) => x + y, 0); return Object.fromEntries(Object.entries(o).map(([c, x]) => [c, +(x / s).toFixed(3)])); };
  const ergebnis = quelle => ({
    at: new Date().toISOString(), verfahren: 'Namen lesen (Server, Tesseract)', quelle, lang,
    varianten: var_.map(x => ({name: x.name, ...quote(x.z), msServer: {p50: q(x.ms, .5), p95: q(x.ms, .95)}, kb: q(x.kb, .5)})),
    gruppen: Object.fromEntries(Object.entries(gruppen).map(([k, z]) => [k, quote(z)])),
    ...(suche ? {suche: Object.fromEntries(Object.entries(klassen).filter(([, o]) => Object.keys(o).length).map(([k, o]) => [k, anteil(o)])), uebergaenge: ueber,
                 msLesenUndSuchen: {p50: q(zusammen, .5), p95: q(zusammen, .95)}, bildMitWahremNamen: quote(bild), roh} : {}),
    ...(druckzeile ? {druckzeile: quote(zeile)} : {}), fehler});

  if (messbilder) {
    const erkennen = async (im, g, vier, mehr) => {  // wie erfServer: erst die Vierecke, dann der Rahmen
      let r = await freiServer(im, vier, mehr);
      if (r?.urteil !== 'sicher') {
        const fp = fpLagen(...scanBild(im, g)), s = fp.length ? await post('scan/suche', {v: FP_V, fp, ...mehr}) : null;
        if (s && (s.urteil === 'sicher' || !(r?.treffer[0].wert >= s.treffer[0]?.wert))) r = s;
      }
      return r || {urteil: 'nichts', treffer: []};
    };
    for (const m of (await api('messbilder')).items.filter(x => x.scryfall_id)) {
      const im = await laden(`/api/messbild/${m.id}.jpg`), [x, y, w, h] = m.rahmen.length ? m.rahmen : Object.values(scanRahmen(m.breite, m.hoehe));
      const vier = karteFinden(im, m.breite, m.hoehe), g = {x, y, w, h}, merkmal = [m.language, ...(m.foil !== 'normal' ? ['foil'] : []), ...m.merkmale];
      let erste = null;
      for (const va of var_) {
        let best = {namen: [], sicher: false, text: [], karten: [], ms: 0};
        for (const ort of [...vier, g]) {  // wie die Kamera: jedes Viereck, dann der Rahmen; die beste Lesung gilt
          const t = await lies(im, ort, va.v);
          va.ms.push(t.ms); va.kb.push(t.kb);
          if ((t.namen[0]?.wert || 0) > (best.namen[0]?.wert || 0)) best = t;
        }
        const pos = zaehl(va.z, best, m.name);
        if (va !== var_[0]) continue;
        erste = best;
        for (const k of merkmal) zaehl(gruppen[k] = gruppen[k] || leer(), best, m.name);
        if (pos !== 0 && fehler.length < 30) fehler.push(`#${m.id} ${m.name} (${merkmal.join(' ')}): gelesen „${best.text.join(' | ')}“, vorn ${best.namen[0] ? `${best.namen[0].name} ${best.namen[0].wert}` : 'nichts'}`);
      }
      if (suche) {
        const ohne = await erkennen(im, g, vier, {}), mit = mitNamen(erste) ? await erkennen(im, g, vier, mitNamen(erste)) : ohne;
        const ko = klasse(ohne, m.name), km = klasse(mit, m.name);
        plus(klassen.ohne, ko); plus(klassen.mit, km); plus(ueber, `${ko} > ${km}`);
        if (km !== 'sicherRichtig' && fehler.length < 30) fehler.push(`#${m.id} ${m.name} (${merkmal.join(' ')}): ohne Namen ${ko}, mit Namen ${km}, vorn ${mit.treffer[0]?.druck.name || 'nichts'}`);
      }
    }
    return ergebnis('Messbilder');
  }

  const KH = Math.round(karte * 88 / 63), W = Math.round(karte * 1.3), H = Math.round(KH * 1.2), c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d', {willReadFrequently: true}), rahmen = {x: (W - karte) / 2, y: (H - KH) / 2, w: karte, h: KH};
  const probe = proben ? [...proben] : (await api(`scan/katalog?v=${FP_V}&probe=${Math.min(5000, n * 4)}${lang === 'en' ? '' : '&lang=' + lang}`)).probe;
  const gruppe = p => p.gruppe ? p.gruppe : lang !== 'en' ? lang + (p.frame === '2015' || p.frame === '2003' ? p.frame : 'AlterRahmen') : /^A[A-Z0-9]{3}$/.test(p.set_code) ? 'kunstkarte' : !p.id.includes(':') ? 'ohneBildKennung'
    : (r => r === '2015' ? 'rahmen2015' : r.startsWith('2015') ? 'rahmen2015besonders' : r.startsWith('2003') ? 'rahmen2003' : r.startsWith('199') ? 'alterRahmen' : 'sonst')(p.id.split(':')[1]);
  for (let k = 0; k < n && probe.length; k++) {
    const p = probe.splice(Math.floor(rnd() * probe.length), 1)[0];
    let im;
    try { im = await laden(p.image.replace('/normal/', '/large/'), true); } catch { continue; }
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = 'source-over'; g.filter = 'none';
    g.fillStyle = `rgb(${40 + rnd() * 60 | 0},${35 + rnd() * 50 | 0},${30 + rnd() * 40 | 0})`; g.fillRect(0, 0, W, H);  // Tisch
    g.filter = `brightness(${1 + um(.35)}) contrast(${1 + um(.2)}) saturate(${1 + um(.3)}) blur(${Math.abs(um(1.5)) * karte / 488}px)`;
    g.translate(W / 2 + um(.03, lage) * karte, H / 2 + um(.03, lage) * KH); g.rotate(um(4, lage) * Math.PI / 180); const s = 1 + um(.05, lage); g.scale(s, s);
    g.drawImage(im, -karte / 2, -KH / 2, karte, KH);
    g.setTransform(1, 0, 0, 1, 0, 0); g.filter = 'none';
    g.globalCompositeOperation = 'multiply';  // Farbstich der Lampe
    g.fillStyle = `rgb(${235 + um(20) | 0},${235 + um(20) | 0},${235 + um(20) | 0})`; g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = 'lighter';  // Spiegelung auf Hülle oder Foil
    const gx = rnd() * W, gy = rnd() * H * .6, gr = (60 + rnd() * 120) * karte / 488, gl = g.createRadialGradient(gx, gy, 0, gx, gy, gr);
    gl.addColorStop(0, `rgba(255,255,255,${(.15 + rnd() * .35) * licht})`); gl.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gl; g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = 'source-over';
    const d = g.getImageData(0, 0, W, H);
    for (let i = 0; i < d.data.length; i += 4) { const z = um(8); d.data[i] += z; d.data[i + 1] += z; d.data[i + 2] += z; }
    g.putImageData(d, 0, 0);

    let erste = {namen: [], sicher: false, text: [], karten: [], ms: 0};
    await sammeln?.({...p, gruppe: gruppe(p)}, c, rahmen);
    if (lesen) for (const va of var_) {
      const t = await lies(c, rahmen, va.v), pos = zaehl(va.z, t, p.name);
      va.ms.push(t.ms); va.kb.push(t.kb);
      if (va !== var_[0]) continue;
      erste = t;
      zaehl(gruppen[gruppe(p)] = gruppen[gruppe(p)] || leer(), t, p.name);
      if (pos !== 0 && fehler.length < 30) fehler.push(`${p.name}${p.text ? ` (${p.text})` : ''}, ${gruppe(p)}: gelesen „${t.text.join(' | ')}“, vorn ${t.namen[0] ? `${t.namen[0].name} ${t.namen[0].wert}` : 'nichts'}`);
    }
    if (suche) {
      const fp = fpLagen(...scanBild(c, rahmen));
      if (fp.length) {
        const frag = mehr => post('scan/suche', {v: FP_V, fp, ...mehr});
        const ohne = await frag({}), mit = mitNamen(erste) ? await frag(mitNamen(erste)) : ohne, wahr = p.oid ? await frag({karten: [p.oid], sicher: [p.oid]}) : ohne;
        const ko = klasse(ohne, p.name), km = klasse(mit, p.name), t = mit.treffer[0];
        plus(klassen.ohne, ko); plus(klassen.mit, km); plus(klassen.wahr, klasse(wahr, p.name)); plus(ueber, `${ko} > ${km}`);
        zusammen.push(erste.ms + mit.ms);
        // je Probe: Gruppe, Klasse ohne Namen; gelesen: sicher, Platz des richtigen Namens, Wert des ersten Namens und des nächsten einer anderen Karte;
        // Suche mit den gelesenen Namen: Bilder zur Wahl, Wert und Abstand des besten, ist es die richtige Karte; mit dem wahren Namen: Wert, Abstand
        const zweiter = erste.namen.find(x => x.name !== erste.namen[0].name);
        roh.push([gruppe(p), ko, +erste.sicher, erste.namen.findIndex(x => gleich(x.name, p.name)), erste.namen[0]?.wert ?? 0, zweiter?.wert ?? 0,
                  mit.karten ?? -1, t?.wert ?? 0, t?.abstand ?? 0, +(!!t && gleich(t.druck.name, p.name)), wahr.treffer[0]?.wert ?? 0, wahr.treffer[0]?.abstand ?? 0,
                  ohne.treffer[0]?.wert ?? 0, ohne.treffer[0]?.abstand ?? 0, km]);
        if (p.id && !LAND.includes(p.name)) { bild.proben++; bild.richtig += wahr.treffer[0]?.aussehen.split(':')[0] === p.id.split(':')[0]; }
        if (km.endsWith('Falsch') && fehler.length < 30) fehler.push(`${p.name}, ${gruppe(p)}: mit Namen ${km}, gelesen „${erste.text.join(' | ')}“ (${erste.namen[0]?.name} ${erste.namen[0]?.wert}), vorn ${t?.druck.name} ${t?.wert}`);
      }
    }
    if (druckzeile && lesen && p.set_code && gruppe(p).includes('2015')) {
      const t = await lies(c, rahmen, {versuche: [{box: [.03, .92, .6, .99], kontrast: true}], sprache: 'eng'});
      const worte = t.text.join(' ').toUpperCase().split(/[^0-9A-Z]+/), nr = String(p.number).toUpperCase().replace(/^0+/, '');
      const set = worte.includes(p.set_code), nummer = worte.some(w => w.replace(/^0+/, '') === nr);
      zeile.proben++; zeile.set += set; zeile.nummer += nummer; zeile.beide += set && nummer;
    }
    window.titelStand = `${k + 1} von ${n}`;
  }
  return ergebnis(`verzerrte Scryfall-Bilder (Karte ${karte} px breit, licht ${licht}, lage ${lage}, seed ${seed})`);
}
