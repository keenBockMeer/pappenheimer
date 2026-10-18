// Reine Zähl- und Vergleichslogik des Scanners (PLAN Ausbau v7, E37): ohne DOM, ohne Netz, geladen vor app.js als eigenes Skript und mit Node
// getestet (test_mtg.py, test_zaehler_*). Die Schwellen kommen aus app.js (gemessen, PLAN Phase 56), hier stehen nur die Regeln.
(function () {
  'use strict';

  // Liegt das Viereck dort, wo das der Folge lag? bei = [x, y, r] (Mitte und Spielraum in Pixeln des Kamerabilds) oder null (Rahmen)
  const amOrt = (alt, neu) => alt === neu || (!!alt && !!neu && Math.hypot(neu[0] - alt[0], neu[1] - alt[1]) < neu[2]);

  // Konsens über mehrere Kamerabilder (Phase 56). Je Bild bild({urteil, id, oid, wert, abstand, ruhig, bei}): urteil wie bisher (leer, nichts,
  // unsicher, zwilling, sicher), id = der erkannte Druck (Prüfen: die Karte), wert und abstand des besten Treffers (zum nächsten anderen),
  // ruhig = die Karte liegt dort, wo sie im Bild davor lag, bei = Mitte des Vierecks mit Spielraum oder null (Rahmen)
  // -> {zaehlen, stand}. stand ist die Stufe dieses Bilds:
  //   sofort     sicher, dazu Wert und Abstand weit über der Schwelle: zählt nach einem ruhigen Bild
  //   sicher     sicher wie bisher: zählt nach zwei übereinstimmenden Bildern
  //   gestuetzt  unsicher, aber Wert knapp unter der Schwelle und Abstand zum nächsten: zählt nach drei übereinstimmenden, eins davon sicher
  //   schwach    sonst unsicher oder Zwilling: keine Stimme, setzt nicht zurück, solange das Viereck dasselbe ist (bei)
  //   nichts     leer oder nichts: setzt zurück
  // Ein anderer Druck mit Stimme beginnt eine neue Folge, ebenso ein Bild mit Stimme, das nicht ruhig liegt (es ist dann ihre erste Stimme).
  // zaehlen ist je Folge höchstens einmal wahr; was danach mit einer gezählten Karte geschieht (ERF_FREI, „+1“), entscheidet app.js.
  // schnell = false: wie vor Phase 56, zwei sichere Bilder nacheinander (das zweite ruhig), jedes andere setzt zurück.
  class Konsens {
    constructor({schnell = false, sofortWert = Infinity, sofortAbstand = Infinity, gestuetztWert = Infinity, gestuetztAbstand = 0} = {}) {
      Object.assign(this, {schnell, sofortWert, sofortAbstand, gestuetztWert, gestuetztAbstand});
      this.neu();
    }

    neu() { this.id = null; this.bei = null; this.stimmen = []; this.gezaehlt = false; }

    stufe({urteil, wert = 0, abstand = 0}) {
      if (urteil === 'sicher') return wert >= this.sofortWert && abstand >= this.sofortAbstand ? 'sofort' : 'sicher';
      if (urteil === 'unsicher') return wert >= this.gestuetztWert && abstand >= this.gestuetztAbstand ? 'gestuetzt' : 'schwach';
      return urteil === 'zwilling' ? 'schwach' : 'nichts';
    }

    bild(b) {
      const stand = this.stufe(b);
      if (!this.schnell) {  // vorher: n === 2 in erfZeigen und scanZeigen
        const sicher = b.urteil === 'sicher', n = sicher && this.id === b.id && b.ruhig ? this.stimmen.length + 1 : sicher ? 1 : 0;
        this.id = sicher ? b.id : null;
        this.stimmen = Array(n).fill(stand);
        return {zaehlen: n === 2, stand};
      }
      if (stand === 'nichts') { this.neu(); return {zaehlen: false, stand}; }
      if (stand === 'schwach') {
        if (this.id === null || !amOrt(this.bei, b.bei ?? null)) this.neu();
        return {zaehlen: false, stand};
      }
      if (this.id !== b.id || !b.ruhig) { this.neu(); this.id = b.id; }
      this.bei = b.bei ?? null;
      this.stimmen.push(stand);
      const sicher = this.stimmen.filter(s => s !== 'gestuetzt').length;
      const genug = (stand === 'sofort' && b.ruhig) || sicher >= 2 || (this.stimmen.length >= 3 && sicher >= 1);
      if (!genug || this.gezaehlt) return {zaehlen: false, stand};
      this.gezaehlt = true;
      return {zaehlen: true, stand};
    }
  }

  // --- Kopien beim Durchblättern (Phase 57) ---------------------------------------------------------------------------------------------
  // Ein Mini-Bild ist das ganze Kamerabild als Graubild {w, h, px} (px: w × h Werte 0 bis 255, zeilenweise von oben), eine Zone ist
  // [x, y, w, h] in seinen Punkten. ncc = normierte Korrelation zweier gleich großer Ausschnitte (-1 bis 1, Helligkeit und Kontrast egal).
  const ausschnitt = (m, [x, y, w, h]) => {
    const out = new Float32Array(w * h);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) out[j * w + i] = m.px[(y + j) * m.w + x + i];
    return out;
  };
  const normiert = a => {
    let s = 0, q = 0;
    for (const v of a) { s += v; q += v * v; }
    const mu = s / a.length, sd = Math.sqrt(Math.max(q / a.length - mu * mu, 1e-6)), out = new Float32Array(a.length);
    for (let i = 0; i < a.length; i++) out[i] = (a[i] - mu) / sd;
    return Object.assign(out, {sd});
  };
  // Korrelation der Vorlage v (normiert, Größe der Zone) mit dem Ausschnitt von m an (x, y)
  const nccAn = (m, v, x, y, w, h) => {
    let s = 0, q = 0, sv = 0;
    for (let j = 0; j < h; j++) for (let i = 0, o = (y + j) * m.w + x; i < w; i++) { const p = m.px[o + i]; s += p; q += p * p; sv += p * v[j * w + i]; }
    const n = w * h, mu = s / n, sd = Math.sqrt(Math.max(q / n - mu * mu, 1e-6));
    return sv / n / sd;  // Σv = 0, deshalb fällt mu aus dem Produkt
  };
  const mittelDiff = (m, alt, [x, y, w, h]) => {
    let d = 0;
    for (let j = 0; j < h; j++) for (let i = 0, o = (y + j) * m.w + x; i < w; i++) d += Math.abs(m.px[o + i] - alt.px[o + i]);
    return d / (w * h);
  };

  // Lag in zone seit minis.length Bildern alles still? Mittlere Änderung von Bild zu Bild unter grenze (Phase 56: ruhig, ohne dass das Bild
  // der Erkennung davor die Karte kennen muss). Weniger als zwei Bilder oder eine zu kleine Zone: nein.
  const ruhigIn = (minis, zone, grenze) => {
    if (minis.length < 2) return false;
    const m = minis[0], x = Math.max(0, Math.round(zone[0])), y = Math.max(0, Math.round(zone[1]));
    const z = [x, y, Math.min(m.w - x, Math.round(zone[2])), Math.min(m.h - y, Math.round(zone[3]))];
    if (z[2] < 2 || z[3] < 2) return false;
    for (let i = 1; i < minis.length; i++) if (minis[i].w !== m.w || minis[i].h !== m.h || mittelDiff(minis[i], minis[i - 1], z) >= grenze) return false;
    return true;
  };

  // Zustandsautomat über Mini-Bilder jedes Kamerabilds. karte(mini, zone): Eine Karte ist gezählt (erkannt oder „+1“), sie liegt in zone (der
  // „Stapelzone“). Danach je Kamerabild bild(mini) -> {ereignis: null | 'kopie' | 'frage', stand, wert (Korrelation in der Zone)}.
  //   1. Bruch: Die Korrelation in der Zone mit der Karte fällt unter bruch (weggeschnippt, Hand, die nächste Karte). Bewegung allein (mittlere
  //      Änderung zum Bild davor ab ruheDiff) macht die Zone nur unruhig: So stößt man eine Karte an, ohne dass etwas geschieht.
  //   2. Die Zone beruhigt sich (ruhe Bilder kaum Änderung) auf ein Bild, das der Karte stark ähnelt (ab gleich, bis versatz daneben).
  //   3. Zeuge: Die Karte liegt an zwei Orten zugleich, in der Zone (ab zweiOrte) und mindestens versatz der Zonengröße daneben (ab zeuge), an
  //      einer Stelle, wo sie bei karte() nicht lag (ein Ablagestapel, der die Karte schon zeigt, ist kein Zeuge). Im Flug ist die Karte im
  //      Mini-Bild verwischt; deshalb gilt auch, wenn sie nach dem Beruhigen innerhalb von nachher Bildern daneben ruhig liegt.
  // 1, 2 und 3: 'kopie'. 1 und 2 ohne Zeugen: 'frage' (die App fragt, sie zählt nicht still). Nur Unruhe: nichts. Liegt nach einem Bruch etwas
  // anderes in der Zone (leer, Hand, andere Karte), endet es ohne Ereignis ('aus', die Erkennung übernimmt), ebenso nach dauer Bildern Unruhe.
  // Nur der Zeuge unterscheidet eine weggeschnippte Karte über ihrer Kopie von einer Hand, die über die Karte fährt, und von derselben Karte,
  // die herausgenommen und wieder hingelegt wird: Die liegt nie an zwei Orten. Nach 'kopie' und 'frage' ist die neue Kopie die Karte (die Zone
  // folgt ihr). weg(): nichts mehr verfolgen.
  class Kopien {
    constructor({bruch = .8, gleich = .75, zeuge = .7, zweiOrte = .6, ruhe = 1, ruheDiff = 4, nachher = 12, dauer = 90, versatz = .5, schieben = 1, schritt = 2} = {}) {
      Object.assign(this, {bruch, gleich, zeuge, zweiOrte, ruhe, ruheDiff, nachher, dauer, versatz, schieben, schritt});
      this.weg();
    }

    weg() { this.stand = 'aus'; this.zone = this.vorlage = this.basis = this.vor = null; }

    karte(mini, zone) {
      const [x, y] = zone.map(v => Math.max(0, Math.round(v)));
      this.zone = [x, y, Math.min(Math.round(zone[2]), mini.w - x), Math.min(Math.round(zone[3]), mini.h - y)];
      if (this.zone[2] < 4 || this.zone[3] < 4) return this.weg();
      this.vorlage = normiert(ausschnitt(mini, this.zone));
      if (this.vorlage.sd < 4) return this.weg();  // einfarbig: nichts zu verfolgen
      this.basis = this.daneben(mini);
      Object.assign(this, {stand: 'liegt', vor: mini, n: 0, ruhig: 0, brach: false, zeugeDa: false});
    }

    // beste Korrelation um die Zone (bis s Punkte versetzt) -> [Wert, x, y]
    umZone(m, s) {
      const [x, y, w, h] = this.zone;
      let best = [-1, x, y];
      for (let dy = -s; dy <= s; dy++) for (let dx = -s; dx <= s; dx++) {
        const X = x + dx, Y = y + dy;
        if (X < 0 || Y < 0 || X + w > m.w || Y + h > m.h) continue;
        const v = nccAn(m, this.vorlage, X, Y, w, h);
        if (v > best[0]) best = [v, X, Y];
      }
      return best;
    }

    // Korrelation an allen Stellen außerhalb der Zone (Raster schritt, mindestens versatz der Zonengröße entfernt) -> Map Stelle -> Wert
    daneben(m) {
      const [x, y, w, h] = this.zone, out = new Map();
      for (let Y = 0; Y + h <= m.h; Y += this.schritt) for (let X = 0; X + w <= m.w; X += this.schritt) {
        if (Math.abs(X - x) < this.versatz * w && Math.abs(Y - y) < this.versatz * h) continue;
        out.set(Y * m.w + X, nccAn(m, this.vorlage, X, Y, w, h));
      }
      return out;
    }

    zeugeSuchen(m) {
      for (const [p, v] of this.daneben(m)) if (v >= this.zeuge && !(this.basis.get(p) >= this.zeuge - .1)) return true;
      return false;
    }

    ende(m, ereignis, [x, y]) {
      if (ereignis) this.karte(m, [x, y, this.zone[2], this.zone[3]]);
      else Object.assign(this, {stand: 'liegt', brach: false, zeugeDa: false});
      return ereignis;
    }

    bild(m) {
      if (this.stand === 'aus') return {ereignis: null, stand: 'aus'};
      const [wert] = this.umZone(m, this.schieben), diff = mittelDiff(m, this.vor, this.zone), unruhe = diff >= this.ruheDiff || wert < this.bruch;
      this.vor = m;
      this.ruhig = diff >= this.ruheDiff ? 0 : this.ruhig + 1;  // ruhig heißt: nichts bewegt sich (die Kopie darf versetzt liegen)
      if (this.stand === 'liegt' && !unruhe) return {ereignis: null, stand: 'liegt', wert};
      if (this.stand === 'liegt' || (this.stand === 'wartet' && unruhe)) {  // neue Unruhe; wartete noch eine Kopie auf ihren Zeugen, fragt die App
        const offen = this.stand === 'wartet' && this.brach ? 'frage' : null;
        if (offen) this.ende(this.zielBild, offen, this.ziel);
        Object.assign(this, {stand: 'unruhig', n: 0, brach: false, zeugeDa: false});
        if (offen) return {ereignis: offen, stand: 'unruhig', wert};
      }
      if (wert < this.bruch) this.brach = true;
      if (!this.zeugeDa && wert >= this.zweiOrte && this.zeugeSuchen(m)) this.zeugeDa = true;
      if (this.stand === 'wartet') {  // die Kopie liegt, die weggeschnippte Karte kommt vielleicht noch daneben zur Ruhe
        if (this.zeugeDa) { this.ende(this.zielBild, 'kopie', this.ziel); return {ereignis: 'kopie', stand: 'liegt', wert}; }
        if (++this.n <= this.nachher) return {ereignis: null, stand: 'wartet', wert};
        const ereignis = this.ende(this.zielBild, this.brach ? 'frage' : null, this.ziel);
        return {ereignis, stand: 'liegt', wert};
      }
      if (++this.n > this.dauer) { this.weg(); return {ereignis: null, stand: 'aus', wert}; }
      if (this.ruhig < this.ruhe) return {ereignis: null, stand: 'unruhig', wert};
      const [w2, x2, y2] = this.umZone(m, Math.round(this.versatz * Math.min(this.zone[2], this.zone[3])));
      if (w2 < this.gleich) {  // etwas anderes liegt da (oder nichts): die Erkennung übernimmt
        if (this.brach) { this.weg(); return {ereignis: null, stand: 'aus', wert: w2}; }
        this.ende(m, null, [x2, y2]);
        return {ereignis: null, stand: 'liegt', wert: w2};
      }
      if (this.zeugeDa) return {ereignis: this.ende(m, 'kopie', [x2, y2]), stand: 'liegt', wert: w2};
      Object.assign(this, {stand: 'wartet', n: 0, ziel: [x2, y2], zielBild: m});
      return {ereignis: null, stand: 'wartet', wert: w2};
    }
  }

  const Zaehler = {Konsens, Kopien, amOrt, ruhigIn, ncc: (a, b) => { const x = normiert(a), y = normiert(b); let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * y[i]; return s / x.length; }};
  globalThis.Zaehler = Zaehler;
  if (typeof module !== 'undefined' && module.exports) module.exports = Zaehler;
})();
