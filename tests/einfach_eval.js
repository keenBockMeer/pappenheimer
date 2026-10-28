// Phase 61 (PLAN Ausbau v8, E40 bis E42): misst, wie einfach die App am Handy ist. Nicht Teil von pytest.
// Im Handy-Format (375 × 812, Geräte-Ansicht der Entwicklerwerkzeuge) in der Browser-Konsole der App einfügen, dann:
//   await einfachEval()
// Ergebnis zum Ablegen und Vergleichen: copy(JSON.stringify(await einfachEval(), null, 1))
// Je Ansicht: woerter (sichtbar im Inhalt), knoepfe (sichtbare Knöpfe, Links, Auswahlen), hoehen (Seite in Bildschirmhöhen). Mit Ziel dazu:
// tipps (vom Start „#/“ bis zum Ziel), woerterBis und knoepfeBis (vor dem Ziel), px und hoehenBis (Oberkante des Ziels). navZiele = Ziele
// in der Navigation. Gemessen wie ein neuer Browser: gemerkte Wahl (MERKER) wird für die Messung entfernt und danach zurückgelegt.
// Die Kamera startet die Messung nie, „Kamera starten“ ist nur das Ziel.
async function einfachEval({ansichten = null} = {}) {
  const ANSICHTEN = ansichten || [
    {name: 'Übersicht', hash: '#/'},
    {name: 'Scannen (Erfassen)', hash: '#/', tipps: ['#nav a[href^="#/scan"]', '[data-modus="erfassen"][aria-pressed="false"]'], ziel: '#cam-go'},
    {name: 'Karten', hash: '#/cards'}, {name: 'Serien', hash: '#/sets'}, {name: 'Sortieren', hash: '#/sort'}, {name: 'Verkaufen', hash: '#/sell'},
    {name: 'Decks', hash: '#/decks'}, {name: 'Wünsche', hash: '#/wuensche'}, {name: 'Spiele', hash: '#/spiele'}, {name: 'Hilfe', hash: '#/help'}, {name: 'Mehr', hash: '#/mehr'},
  ];
  const MERKER = ['mtg-scan-modus'];
  const sichtbar = el => el.checkVisibility ? el.checkVisibility({visibilityProperty: true, opacityProperty: true}) : !!el.offsetParent;
  const woerter = t => (t.match(/[\p{L}\p{N}][\p{L}\p{N}'’.,:%€-]*/gu) || []).length;
  const KNOPF = 'button, a[href], select, input:not([type=hidden]), [role=button]';
  const ruhe = async () => {  // fertig gezeichnet: kein Skelett mehr, der Inhalt ändert sich 600 ms lang nicht, kein Auftritt läuft mehr (sonst zählt Deckkraft 0 als unsichtbar)
    let vorher = '', gleich = 0;
    for (let i = 0; i < 100 && gleich < 6; i++) {
      await new Promise(r => setTimeout(r, 100));
      const jetzt = main.innerHTML;
      gleich = jetzt === vorher && !main.querySelector('.skel') ? gleich + 1 : 0;
      vorher = jetzt;
    }
    const auftritt = Promise.all(document.getAnimations().filter(a => a.effect?.getComputedTiming().iterations !== Infinity).map(a => a.finished.catch(() => {})));
    await Promise.race([auftritt, new Promise(r => setTimeout(r, 3000))]);  // im verdeckten Tab stehen Animationen still
  };
  const zaehlen = (bis) => {  // sichtbare Wörter und Knöpfe in #main, mit bis nur die vor diesem Element
    let w = 0;
    const gang = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
    for (let n; (n = gang.nextNode());) {
      if (bis && (bis === n.parentElement || bis.contains(n) || bis.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) break;
      if (n.parentElement && sichtbar(n.parentElement)) w += woerter(n.textContent);
    }
    const k = [...main.querySelectorAll(KNOPF)].filter(el => sichtbar(el) && (!bis || bis.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)).length;
    return {w, k};
  };
  const gemerkt = Object.fromEntries(MERKER.map(k => [k, localStorage.getItem(k)]));
  MERKER.forEach(k => localStorage.removeItem(k));
  const erg = {format: `${innerWidth} × ${innerHeight}`, navZiele: [...document.querySelectorAll('#nav a')].filter(sichtbar).length, ansichten: []};
  try {
    for (const a of ANSICHTEN) {
      location.hash = a.hash === location.hash ? a.hash + '?' : a.hash;  // gleiche Adresse: trotzdem neu zeichnen
      await ruhe();
      let tipps = 0;
      for (const sel of a.tipps || []) {
        const el = document.querySelector(sel);
        if (!el || !sichtbar(el)) continue;  // schon gewählt: kein Tipp nötig
        el.click(); tipps++;
        await ruhe();
      }
      scrollTo(0, 0);
      const alles = zaehlen(null), z = {name: a.name, adresse: location.hash, woerter: alles.w, knoepfe: alles.k, hoehen: +(document.documentElement.scrollHeight / innerHeight).toFixed(1)};
      if (a.ziel) {
        const ziel = document.querySelector(a.ziel);
        if (!ziel) z.ziel = 'fehlt';
        else {
          const bis = zaehlen(ziel), px = Math.round(ziel.getBoundingClientRect().top + scrollY);
          Object.assign(z, {tipps, woerterBis: bis.w, knoepfeBis: bis.k, px, hoehenBis: +(px / innerHeight).toFixed(1)});
        }
      }
      erg.ansichten.push(z);
    }
  } finally {
    MERKER.forEach(k => gemerkt[k] === null ? localStorage.removeItem(k) : localStorage.setItem(k, gemerkt[k]));
  }
  console.table(erg.ansichten);
  return erg;
}
