"""C++ kisitli cozumleyicinin kazancini olcer.

Once DOGRULAMA: C++ tarafindaki kisitsiz greedy, Python'un greedy'siyle
birebir ayni cikmali. Ayni cikmiyorsa matris aktariminda hata var demektir
ve kisitin kazanci diye olculen sey aslinda o hatadir. Bu kontrol
gecmeden asil sayilar basilmiyor.

Sonra KARSILASTIRMA: ayni ornekler uzerinde greedy ve kisitli, kume kume.
Asil sayi `rapor` kumesinde ve PLAKA bazinda; `egitim` kumesi yalnizca
referans icin var (model onlari gordu, oradaki yuksek sayi bir sey
ifade etmez).
"""

from __future__ import annotations

import argparse
import struct
from collections import Counter
from pathlib import Path

import numpy as np

from train_recognizer import coz_greedy, duzenleme_mesafesi

ROOT = Path(__file__).resolve().parent.parent


def oku_bin(yol: Path):
    with yol.open("rb") as f:
        if f.read(4) != b"PLKA":
            raise SystemExit("bicim taninmadi")
        n, T, C = struct.unpack("<iii", f.read(12))
        veri = np.frombuffer(f.read(n * T * C * 4), dtype=np.float32)
    return veri.reshape(n, T, C)


def olc(ciftler):
    """ciftler: (tahmin, hedef, plaka) listesi."""
    if not ciftler:
        return None
    d = [duzenleme_mesafesi(t, h) for t, h, _ in ciftler]
    kt = sum(len(h) for _, h, _ in ciftler)
    kd = sum(max(0, len(h) - m) for m, (_, h, _) in zip(d, ciftler))
    plaka = {}
    for t, h, p in ciftler:
        plaka.setdefault(p, []).append((t, h))
    cog = sum(Counter(t for t, _ in v).most_common(1)[0][0] == v[0][1]
              for v in plaka.values())
    return {"tam": sum(t == h for t, h, _ in ciftler) / len(ciftler),
            "kar": kd / max(1, kt), "duz": float(np.mean(d)),
            "cog": cog / len(plaka), "n": len(ciftler), "np": len(plaka),
            "cog_n": cog}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paket", type=Path, default=ROOT / "paket")
    args = ap.parse_args(argv)

    L = oku_bin(args.paket / "logits.bin")
    etiket = [s.split("\t") for s in
              (args.paket / "logits.tsv").read_text(encoding="utf-8").splitlines()
              if s.strip()]
    cozum = {}
    for s in (args.paket / "cozum.tsv").read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        cozum[int(p[0])] = (p[1] if len(p) > 1 else "",
                            p[2] if len(p) > 2 else "")

    # --- DOGRULAMA -------------------------------------------------------
    fark = [i for i in range(len(L))
            if coz_greedy(L[i]) != cozum.get(i, ("", ""))[0]]
    print(f"dogrulama: C++ greedy ile Python greedy "
          f"{len(L) - len(fark)}/{len(L)} ornekte ayni")
    if fark:
        print("  UYUSMAYAN ilk 5:")
        for i in fark[:5]:
            print(f"    {i}: python='{coz_greedy(L[i])}' "
                  f"c++='{cozum.get(i, ('',''))[0]}'")
        raise SystemExit(
            "\nMatris aktariminda hata var. Kisitin kazanci diye olculecek\n"
            "sey bu hata olurdu; sayilar basilmiyor.")

    # --- KARSILASTIRMA ---------------------------------------------------
    kumeler = {}
    for i, kume, metin in ((int(a), b, c) for a, b, c in etiket):
        kumeler.setdefault(kume, []).append((i, metin))

    print()
    for kume in ("rapor", "secim", "egitim"):
        if kume not in kumeler:
            continue
        g = olc([(cozum[i][0], m, m) for i, m in kumeler[kume]])
        k = olc([(cozum[i][1], m, m) for i, m in kumeler[kume]])
        etiketi = {"rapor": "RAPOR  (hicbir karara girmedi)",
                   "secim": "secim  (epoch secimi buna bakti)",
                   "egitim": "egitim (model bunlari gordu - referans)"}[kume]
        print(f"{etiketi}   {g['n']} kirpma / {g['np']} plaka")
        print(f"  {'olcut':<24}{'greedy':>10}{'kisitli':>10}{'fark':>10}")
        for ad, anahtar, ters in (("kirpma tam dizi", "tam", False),
                                  ("karakter", "kar", False),
                                  ("duzenleme (dusuk iyi)", "duz", True),
                                  ("PLAKA cogunluk oyu", "cog", False)):
            d = k[anahtar] - g[anahtar]
            im = "+" if ((d < 0) if ters else (d > 0)) else (" " if d == 0 else "-")
            print(f"  {ad:<24}{g[anahtar]:>10.3f}{k[anahtar]:>10.3f}"
                  f"{d:>+10.3f} {im}")
        print(f"  {'PLAKA (adet)':<24}{g['cog_n']:>10}{k['cog_n']:>10}"
              f"{k['cog_n']-g['cog_n']:>+10}")
        print()

    # Kisit neyi degistirdi: yalnizca gecersiz plakalara mi dokundu?
    r = [(i, m) for i, m in kumeler.get("rapor", [])]
    degisen = [(cozum[i][0], cozum[i][1], m) for i, m in r
               if cozum[i][0] != cozum[i][1]]
    duzelen = [x for x in degisen if x[1] == x[2] and x[0] != x[2]]
    bozulan = [x for x in degisen if x[0] == x[2] and x[1] != x[2]]
    print(f"rapor kumesinde kisit {len(degisen)}/{len(r)} kirpmada "
          f"cikti degistirdi")
    print(f"  duzelen (yanlis -> dogru): {len(duzelen)}")
    print(f"  bozulan (dogru -> yanlis): {len(bozulan)}")
    for a, b, m in duzelen[:6]:
        print(f"    {m:<10} greedy '{a}'  ->  kisitli '{b}'")
    for a, b, m in bozulan[:6]:
        print(f"    BOZULAN {m:<10} '{a}' -> '{b}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
