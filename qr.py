"""QR-Code (Phase 51, PLAN E34): Adresse und Kopplungs-Code fürs Handy als Bild, ohne fremde Bibliothek. Nur was dafür nötig ist: Byte-Modus,
Fehlerkorrektur M, Versionen 1 bis 6 (bis 106 Bytes), Maske nach den Strafpunkten der Norm (ISO/IEC 18004). matrix gibt die Module (True =
dunkel), svg das Bild ohne Skript und ohne fremde Verweise. Geprüft gegen die Matrix eines fremden Kodierers (tests/fixtures/qr_referenz.json)."""

# Version -> (Datenbytes je Block, Blöcke, Korrekturbytes je Block) bei Fehlerkorrektur M; die Mitte des einen Ausrichtungsmusters ab Version 2
BLOECKE = {1: (16, 1, 10), 2: (28, 1, 16), 3: (44, 1, 26), 4: (32, 2, 18), 5: (43, 2, 24), 6: (27, 4, 16)}
RAND = 4  # Ruhezone in Modulen, wie die Norm sie verlangt

_EXP, _LOG = [0] * 512, [0] * 256  # GF(256) mit dem Polynom 0x11D
_x = 1
for _i in range(255):
    _EXP[_i], _LOG[_x] = _x, _i
    _x = _x << 1 ^ (0x11D if _x & 0x80 else 0)
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mal(a, b):
    return _EXP[_LOG[a] + _LOG[b]] if a and b else 0


def _korrektur(daten, n):
    """Reed-Solomon: die n Korrekturbytes zu daten (Rest der Division durch das Generatorpolynom mit den Nullstellen α^0 … α^(n-1))."""
    gen = [1]
    for i in range(n):
        gen = [a ^ _mal(b, _EXP[i]) for a, b in zip(gen + [0], [0] + gen)]
    rest = list(daten) + [0] * n
    for i in range(len(daten)):
        if rest[i]:
            f = rest[i]
            for j, g in enumerate(gen):
                rest[i + j] ^= _mal(g, f)
    return rest[-n:]


def _maske(m, r, c):
    return [(r + c) % 2, r % 2, c % 3, (r + c) % 3, (r // 2 + c // 3) % 2, r * c % 2 + r * c % 3, (r * c % 2 + r * c % 3) % 2,
            ((r + c) % 2 + r * c % 3) % 2][m] == 0


def _strafe(q):
    """Strafpunkte einer fertigen Matrix (Regeln 1 bis 4 der Norm); die Maske mit den wenigsten gilt."""
    n, p = len(q), 0
    for linie in [*q, *zip(*q)]:
        lauf = 1
        for a, b in zip(linie, linie[1:]):
            lauf = lauf + 1 if a == b else 1
            p += 3 if lauf == 5 else lauf > 5
        s = "0000" + "".join("1" if x else "0" for x in linie) + "0000"  # außerhalb ist hell
        p += 40 * sum(s.count(m) for m in ("00001011101", "10111010000"))
    p += 3 * sum(q[r][c] == q[r][c + 1] == q[r + 1][c] == q[r + 1][c + 1] for r in range(n - 1) for c in range(n - 1))
    dunkel = sum(map(sum, q))
    return p + 10 * (abs(dunkel * 20 - n * n * 10) // (n * n))


def matrix(text, maske=None):
    """Module des QR-Codes für text (UTF-8), Zeile für Zeile; maske 0 bis 7 oder None (die mit den wenigsten Strafpunkten). Passt text
    nicht in Version 6: ValueError."""
    roh = text.encode("utf-8")
    v = next((v for v, (d, b, _) in BLOECKE.items() if len(roh) <= d * b - 2), None)
    if v is None:
        raise ValueError(f"Zu lang für einen QR-Code bis Version 6 ({len(roh)} Bytes)")
    d, b, k = BLOECKE[v]
    bits = "0100" + f"{len(roh):08b}" + "".join(f"{x:08b}" for x in roh)
    bits += "0" * min(4, d * b * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    daten = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    daten += [0xEC, 0x11] * ((d * b - len(daten)) // 2) + [0xEC] * ((d * b - len(daten)) % 2)
    bl = [daten[i * d:(i + 1) * d] for i in range(b)]
    folge = [x for spalte in zip(*bl) for x in spalte] + [x for spalte in zip(*(_korrektur(x, k) for x in bl)) for x in spalte]

    n = 17 + 4 * v
    q, fest = [[False] * n for _ in range(n)], [[False] * n for _ in range(n)]

    def setz(r, c, dunkel):
        q[r][c], fest[r][c] = dunkel, True
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):  # Suchmuster mit hellem Rand
        for r in range(-1, 8):
            for c in range(-1, 8):
                if 0 <= r0 + r < n and 0 <= c0 + c < n:
                    setz(r0 + r, c0 + c, 0 <= r <= 6 and 0 <= c <= 6 and (r in (0, 6) or c in (0, 6) or 2 <= r <= 4 and 2 <= c <= 4))
    for i in range(8, n - 8):  # Taktlinien
        setz(6, i, i % 2 == 0)
        setz(i, 6, i % 2 == 0)
    if v > 1:
        m = n - 7
        for r in range(-2, 3):
            for c in range(-2, 3):
                setz(m + r, m + c, max(abs(r), abs(c)) != 1)
    # Formatbits, je Bit k (0 = niedrigstes) zweimal: oben links (Spalte 8 abwärts, dann Zeile 8 nach links, an der Taktlinie vorbei) und geteilt
    # auf Zeile 8 rechts und Spalte 8 unten. Gesetzt wird je Maske, hier nur der Platz; dazu das immer dunkle Modul.
    plaetze = [[(k, 8) for k in range(6)] + [(7, 8), (8, 8), (8, 7)] + [(8, 14 - k) for k in range(9, 15)],
               [(8, n - 1 - k) for k in range(8)] + [(n - 15 + k, 8) for k in range(8, 15)]]
    for r, c in plaetze[0] + plaetze[1]:
        setz(r, c, False)
    setz(n - 8, 8, True)

    i, rechts, alle = 0, n - 1, "".join(f"{x:08b}" for x in folge)
    while rechts >= 1:  # Daten im Zickzack, je zwei Spalten, von rechts unten
        if rechts == 6:
            rechts = 5
        for j in range(n):
            r = n - 1 - j if (rechts + 1) & 2 == 0 else j
            for c in (rechts, rechts - 1):
                if not fest[r][c]:
                    q[r][c] = i < len(alle) and alle[i] == "1"
                    i += 1
        rechts -= 2

    def mit(m):
        z = [[x ^ (not fest[r][c] and _maske(m, r, c)) for c, x in enumerate(zeile)] for r, zeile in enumerate(q)]
        f = m  # Fehlerkorrektur M = 00, dann die Maske; BCH(15,5) und die feste Maske 0x5412
        rest = f << 10
        for s in range(14, 9, -1):
            if rest >> s & 1:
                rest ^= 0x537 << (s - 10)
        f = (f << 10 | rest) ^ 0x5412
        for k in range(15):
            for r, c in (plaetze[0][k], plaetze[1][k]):
                z[r][c] = bool(f >> k & 1)
        return z
    if maske is not None:
        return mit(maske)
    return min((mit(m) for m in range(8)), key=_strafe)


def svg(text):
    """QR-Code als SVG: dunkle Module als ein Pfad auf weißem Grund (auch im dunklen Look der Seite), mit Ruhezone, ohne Skript und Verweise."""
    q = matrix(text)
    n = len(q) + 2 * RAND
    teile = []
    for r, zeile in enumerate(q):
        c = 0
        while c < len(zeile):
            if zeile[c]:
                lang = next((j for j in range(c, len(zeile)) if not zeile[j]), len(zeile)) - c
                teile.append(f"M{c + RAND} {r + RAND}h{lang}v1h-{lang}z")
                c += lang
            c += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" role="img" aria-label="QR-Code">'
            f'<rect width="{n}" height="{n}" fill="#fff"/><path fill="#000" d="{"".join(teile)}"/></svg>')
