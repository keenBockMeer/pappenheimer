// Phase 30: Trefferquote des Scanners an echten Kamerabildern (Messbilder aus „Scannen, Erfassen“). Nicht Teil von pytest.
// Am Rechner in der Browser-Konsole der App einfügen (Sammlung mit den Messbildern), dann: await messbilderEval()
// Ergebnis als JSON zum Ablegen und Vergleichen: copy(JSON.stringify(await messbilderEval(), null, 1))
// Jedes Messbild mit Etikett läuft durch die Erkennung von heute (Set-Lock mit Rahmen): derselbe Ausschnitt wie die Kamera (scanSuche), dann
// das Urteil wie in erfZeigen. Sets: ohne Angabe je Bild das Set seines Etiketts (als wäre das richtige Set gewählt), mit {sets: 'DSK,DSC'}
// fest diese wie in einer Sitzung (höchstens 6). Bilder, deren Karte in diesen Sets fehlt, zählen getrennt unter nichtImIndex: Dort ist
// „nichts“ die richtige Antwort. Fehlende Sets und Erkennungsbilder lädt der Lauf nach wie „Erkennung vorbereiten“ (braucht Scryfall).
// Grenzen: Ein Messbild ist ein Einzelbild (die App zählt erst nach zwei gleichen nacheinander) und als JPEG gespeichert, also etwas
// gröber als das Kamerabild selbst (bis Phase 35 dazu auf 1280 px verkleinert, seitdem bis 1920 px).
// top1 = bester Kandidat ist der Druck des Etiketts, top1Bild = er zeigt dasselbe Bild (anderer Druck erlaubt), top3 = der Druck ist unter
// den drei, die die App zur Wahl stellt. Dazu das Urteil der App, zusammen 1: sicherRichtig (zählt von selbst), sicherFalsch („sicher,
// aber falsch“), unsicher (die App fragt), nichts (keine Karte erkannt). Alles gesamt und je Merkmal (normal = ohne Merkmal).
async function messbilderEval({sets = ''} = {}) {
  const laden = u => new Promise((ok, err) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => err(new Error('Bild fehlt: ' + u)); im.src = u; });
  const indexe = new Map();
  const index = async codes => {  // wie erfVorbereiten
    if (indexe.has(codes)) return indexe.get(codes);
    let r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(codes)}`);
    if (r.fehlt.length) { await fpJob(r.fehlt); r = await api(`scan?v=${FP_V}&set=${encodeURIComponent(codes)}`); }
    const ix = r.ids.length ? fpIndex({...r, keys: r.ids}) : null, bild = {};
    r.ids.forEach((id, j) => { const ill = r.drucke[id].ill; if (ill) (bild[ill] = bild[ill] || []).push(j); });
    indexe.set(codes, {ix, bild, r});
    return indexe.get(codes);
  };
  const FELDER = ['top1', 'top1Bild', 'top3', 'sicherRichtig', 'sicherFalsch', 'unsicher', 'nichts'];
  const leer = () => Object.fromEntries([['n', 0], ...FELDER.map(k => [k, 0])]);
  const gesamt = leer(), merkmale = {normal: leer(), ...Object.fromEntries(Object.keys(MESS_MERKMAL).map(k => [k, leer()]))};
  const fremd = {n: 0, nichts: 0, unsicher: 0, sicherFalsch: 0}, fehler = [];
  const {items} = await api('messbilder'), mit = items.filter(m => m.scryfall_id);
  let ms = 0;
  for (const m of mit) {
    const {ix, bild, r} = await index(sets || m.set_code), wahr = r.drucke[m.scryfall_id];
    const im = await laden(`/api/messbild/${m.id}.jpg`), [x, y, w, h] = m.rahmen.length ? m.rahmen : Object.values(scanRahmen(m.breite, m.hoehe));
    const t0 = performance.now(), best = ix ? scanSuche(ix, im, {x, y, w, h}) : [];
    ms += performance.now() - t0;
    const b = best[0], z = best[1], id = b && ix.ids[b.i], d = b && r.drucke[id];
    const zwilling = b && (bild[d.ill] || []).some(j => j !== b.i && r.drucke[ix.ids[j]].set !== d.set);
    const urteil = !b || b.score < FP_NEIN ? 'nichts' : b.score >= FP_SICHER && (!z || b.score - z.score >= FP_ABSTAND) && !zwilling ? 'sicher' : 'unsicher';
    if (!wahr) { fremd.n++; fremd[urteil === 'sicher' ? 'sicherFalsch' : urteil]++; continue; }
    const pos = best.findIndex(k => ix.ids[k.i] === m.scryfall_id);
    const treffer = {top1: pos === 0, top1Bild: !!b && (pos === 0 || (!!d.ill && d.ill === wahr.ill)), top3: pos >= 0,
                     sicherRichtig: urteil === 'sicher' && pos === 0, sicherFalsch: urteil === 'sicher' && pos !== 0, unsicher: urteil === 'unsicher', nichts: urteil === 'nichts'};
    const mm = messMerkmale(m);
    for (const g of [gesamt, ...(mm.length ? mm : ['normal']).map(k => merkmale[k])]) { g.n++; for (const k of FELDER) g[k] += treffer[k]; }
    if (pos !== 0 && fehler.length < 30) fehler.push(`#${m.id} ${wahr.name} (${wahr.set} ${wahr.number}${mm.length ? ', ' + mm.join(' ') : ''}): ${urteil}, `
      + (b ? `vorn ${d.name} (${d.set} ${d.number}) ${b.score.toFixed(2)}, richtig ${pos < 0 ? 'nicht unter den drei' : best[pos].score.toFixed(2)}` : 'kein Kandidat'));
  }
  const quote = g => g.n ? Object.fromEntries([['n', g.n], ...FELDER.map(k => [k, +(g[k] / g.n).toFixed(3)])]) : {n: 0};
  return {at: new Date().toISOString(), verfahren: 'Set-Lock mit Rahmen', fp: FP_V, schwellen: {sicher: FP_SICHER, nein: FP_NEIN, abstand: FP_ABSTAND},
          sets: sets || 'je Bild das Set des Etiketts', bilder: items.length, ohneEtikett: items.length - mit.length, nichtImIndex: fremd,
          gesamt: quote(gesamt), merkmale: Object.fromEntries(Object.entries(merkmale).map(([k, g]) => [k, quote(g)])),
          msJeBild: gesamt.n + fremd.n ? +(ms / (gesamt.n + fremd.n)).toFixed(1) : 0, fehler};
}
