"""Faz 5: bir aracin birden cok karesinden tek plaka - zamansal oylama.

Neden
-----
Ayni plaka onlarca karede geciyor ve her karede ayri okunuyor. Tek karede
%81.5 dogru olan bir okuyucu, kareleri birlestirdiginde daha iyi olmali:
farkli karelerde farkli karakterler bozuluyor.

Onemli sinir - bu deneyde takip YOK
-----------------------------------
Kirpmalar GERCEK plaka metnine gore gruplaniyor, yani kusursuz bir takipci
varsayiliyor. Gercek boru hattinda gruplari ByteTrack kuruyor ve takip
hatasi (iki araci birlestirmek, bir araci ikiye bolmek) buraya ek gurultu
katardi. O gurultu BU SAYIYA DAHIL DEGIL. Olculen sey oylamanin kendi
kazanci, boru hattinin ucu degil.

Olcum durustlugu
----------------
Strateji SECIM kumesinde seciliyor, sayi RAPOR kumesinde bildiriliyor.
Alti strateji arasindan rapor kumesine bakarak secmek, o kumeyi karara
sokmak olurdu.

Kullanim:
    python scripts/vote.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def oku(paket: Path, egri: Path):
    """(kume, plaka, tahmin, guven) satirlari."""
    etiket = {}
    for s in (paket / "logits.tsv").read_text(encoding="utf-8").splitlines():
        if s.strip():
            i, kume, metin = s.split("\t")
            etiket[int(i)] = (kume, metin)

    w = json.loads(egri.read_text(encoding="utf-8"))["agirliklar"]

    satirlar = []
    for s in (paket / "cozum.tsv").read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        i = int(p[0])
        kume, hedef = etiket[i]
        lp, ikinci_lp = float(p[3]), float(p[5])
        marj = 30.0 if not np.isfinite(ikinci_lp) else min(lp - ikinci_lp, 30.0)
        z = w["sabit"] + w["marj"] * marj + w["lp"] * max(lp, -30.0)
        guven = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        satirlar.append((kume, hedef, p[2], float(guven)))
    return satirlar


# --------------------------------------------------------------------------
# Stratejiler: her biri (tahmin, guven) listesinden tek bir plaka uretir
# --------------------------------------------------------------------------

def s_ilk(v):
    """Oylama yok - ilk kare. Taban cizgisi."""
    return v[0][0]


def s_en_guvenli(v):
    """Tek en guvenli kare. Oylama degil, secim."""
    return max(v, key=lambda x: x[1])[0]


def s_cogunluk(v):
    """Duz cogunluk - her kare esit oy."""
    return Counter(t for t, _ in v).most_common(1)[0][0]


def s_guven_agirlikli(v):
    """Her kare guveni kadar oy verir."""
    puan = defaultdict(float)
    for t, g in v:
        puan[t] += g
    return max(puan.items(), key=lambda x: x[1])[0]


def s_esikli(v, esik=0.7):
    """Dusuk guvenli kareler atilir, kalanlar guven agirlikli oylar.

    Hepsi esigin altindaysa atmak yerine en guvenlisi aliniyor: bir sey
    dondurmek zorundayiz.
    """
    kalan = [x for x in v if x[1] >= esik]
    return s_guven_agirlikli(kalan) if kalan else s_en_guvenli(v)


def s_karakter(v, esik=0.5):
    """Karakter karakter oylama.

    Dizgi oylamasinin yapamadigi seyi yapabilir: her karesi ayri ayri
    yanlis olan bir plakayi, dogru karakterleri farkli karelerden toplayarak
    kurtarmak. Bedeli, uzunlugu once kararlastirmak zorunda olmasi.
    """
    kalan = [x for x in v if x[1] >= esik] or v
    uzunluk = Counter()
    for t, g in kalan:
        uzunluk[len(t)] += g
    n = max(uzunluk.items(), key=lambda x: x[1])[0]
    ayni = [x for x in kalan if len(x[0]) == n]
    out = []
    for i in range(n):
        puan = defaultdict(float)
        for t, g in ayni:
            puan[t[i]] += g
        out.append(max(puan.items(), key=lambda x: x[1])[0])
    return "".join(out)


STRATEJILER = {
    "ilk kare (oylama yok)": s_ilk,
    "en guvenli tek kare": s_en_guvenli,
    "duz cogunluk": s_cogunluk,
    "guven agirlikli": s_guven_agirlikli,
    "esikli (0.7) agirlikli": s_esikli,
    "karakter oylama": s_karakter,
}


def olc(gruplar, strateji):
    dogru = sum(strateji(v) == plaka for plaka, v in gruplar.items())
    return dogru / max(1, len(gruplar)), dogru


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paket", type=Path, default=ROOT / "paket")
    ap.add_argument("--egri", type=Path, default=ROOT / "runs" / "kalibrasyon.json")
    args = ap.parse_args(argv)

    satirlar = oku(args.paket, args.egri)
    kume = defaultdict(lambda: defaultdict(list))
    for k, plaka, tahmin, guven in satirlar:
        kume[k][plaka].append((tahmin, guven))

    for ad in ("secim", "rapor"):
        g = kume[ad]
        cok = {p: v for p, v in g.items() if len(v) >= 2}
        print(f"{ad}: {len(g)} plaka, {sum(len(v) for v in g.values())} kirpma"
              f"   ({len(cok)} plakada birden fazla kare var)")
    print()

    # Tavan: bir plakanin karelerinden EN AZ BIRI dogruysa, mukemmel bir
    # oylayici onu bulabilirdi. Hicbiri dogru degilse dizgi oylamasi
    # kurtaramaz - karakter oylamasi kurtarabilir, tavani asabilir.
    for ad in ("secim", "rapor"):
        g = kume[ad]
        tavan = sum(any(t == p for t, _ in v) for p, v in g.items()) / len(g)
        print(f"{ad} dizgi oylamasi tavani (en az bir kare dogru): "
              f"{tavan:.3f}")
    print()

    for ad in ("secim", "rapor"):
        g = kume[ad]
        cok = {p: v for p, v in g.items() if len(v) >= 2}
        baslik = ("SECIM  - strateji burada secilir" if ad == "secim"
                  else "RAPOR  - hicbir karara girmez")
        print(f"{baslik}   ({len(g)} plaka)")
        print(f"  {'strateji':<26}{'tum plakalar':>16}"
              f"{'cok kareli':>16}")
        for sad, sf in STRATEJILER.items():
            o, n = olc(g, sf)
            oc, nc = olc(cok, sf) if cok else (float("nan"), 0)
            print(f"  {sad:<26}{o:>10.3f} ({n:>2}){oc:>10.3f} ({nc:>2})")
        print()

    print("'cok kareli' sutunu tek kareli plakalari disliyor: onlarda")
    print("oylanacak bir sey yok ve tum stratejiler ayni sonucu verir,")
    print("bu da stratejiler arasindaki farki seyreltir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
