"""Etiketli koseleri kullanarak plakalari dikleştirir ve olcer.

Iki isi birden yapiyor:

1. **Tanima modelinin gercek veri setini uretiyor.** Dort kose homografi ile
   sabit bir boyuta tasiniyor; model egik plakayla degil dik plakayla
   calisacak.
2. **Sentetik uretecin ayarlarini olcuyor.** Bozulma araliklari tahminle degil
   gercek veriye bakilarak secilecek - projenin sirasi bunun icin boyle
   kuruldu: once gercegi gor, sonra taklidini uret.

Neden 2x boyutta saklaniyor
---------------------------
Tanima modeli 32x128 gibi kucuk bir girdiyle calisacak ama depoda 64x256
tutuluyor. Sebep: girdi boyutu daha olculmedi ve degisebilir. Buyuk saklayip
kucultmek serbest, kucuk saklayip buyutmek bilgi uretmiyor.

Perspektif ne kadar bozuk
-------------------------
Dort kose, plakanin ne kadar egik gorundugunu de soyluyor. Sentetik uretecin
homografi araliklari (plan yatay +/-35, dikey +/-25 oneriyor) bu olcume gore
ayarlanacak - gercekte gorulenden genis bir aralik, modele hic karsilasmayacagi
goruntuler ogretmek olur.

Kullanim:
    python scripts/export_plates.py
    python scripts/export_plates.py --yukseklik 48 --genislik 192
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: Depolama boyutu. Tanima girdisi bundan kucuk olacak; buyuk saklamak
#: sonradan kucultme serbestligi biraktigi icin tercih edildi.
HEDEF_YUKSEKLIK = 64
HEDEF_GENISLIK = 256


def kose_uzunluklari(kose: list[list[int]]) -> tuple[float, float, float, float]:
    """Dortgenin ust, alt, sol, sag kenar uzunluklari."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = kose
    uzunluk = lambda a, b: math.dist(a, b)
    return (uzunluk((x0, y0), (x1, y1)),    # ust
            uzunluk((x3, y3), (x2, y2)),    # alt
            uzunluk((x0, y0), (x3, y3)),    # sol
            uzunluk((x1, y1), (x2, y2)))    # sag


def dikleştir(im: np.ndarray, kose: list[list[int]],
              genislik: int, yukseklik: int) -> np.ndarray:
    kaynak = np.array(kose, dtype=np.float32)
    hedef = np.array([[0, 0], [genislik - 1, 0],
                      [genislik - 1, yukseklik - 1], [0, yukseklik - 1]],
                     dtype=np.float32)
    M = cv2.getPerspectiveTransform(kaynak, hedef)
    return cv2.warpPerspective(im, M, (genislik, yukseklik),
                               flags=cv2.INTER_CUBIC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    parser.add_argument("--labels", type=Path, default=ROOT / "data" / "labels.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "plates")
    parser.add_argument("--genislik", type=int, default=HEDEF_GENISLIK)
    parser.add_argument("--yukseklik", type=int, default=HEDEF_YUKSEKLIK)
    args = parser.parse_args(argv)

    if not args.labels.is_file():
        raise SystemExit(f"Etiket yok: {args.labels}")

    kayitlar = [json.loads(l) for l in
                args.labels.read_text(encoding="utf-8").splitlines() if l.strip()]
    okunabilir = [k for k in kayitlar if k["durum"] == "ok" and len(k["kose"]) == 4]
    if not okunabilir:
        raise SystemExit("Kose bilgisi olan okunabilir kayit yok.")

    # Cikti klasoru temizlenerek yaziliyor: onceki calistirmadan kalan
    # dosyalar sessizce karisir ve olcumu bozar.
    if args.out.is_dir():
        for p in args.out.glob("*.jpg"):
            p.unlink()
    args.out.mkdir(parents=True, exist_ok=True)

    genislikler, yukseklikler, oranlar, egrilikler, keskinlikler = [], [], [], [], []
    yazilan = 0
    manifest = []

    for k in kayitlar:
        if k["durum"] != "ok" or len(k["kose"]) != 4:
            continue
        yol = args.crops / k["dosya"]
        im = cv2.imread(str(yol))
        if im is None:
            continue

        ust, alt, sol, sag = kose_uzunluklari(k["kose"])
        g = (ust + alt) / 2
        y = (sol + sag) / 2
        if g < 8 or y < 4:
            continue
        genislikler.append(g)
        yukseklikler.append(y)
        oranlar.append(g / y)
        # Egrilik: ust ve alt kenarin uzunluk farki perspektifi olcuyor.
        # Tam karsidan bakilsa ikisi esit olurdu; fark buyudukce plaka egik.
        egrilikler.append(abs(ust - alt) / max(ust, alt))

        duz = dikleştir(im, k["kose"], args.genislik, args.yukseklik)
        gri = cv2.cvtColor(duz, cv2.COLOR_BGR2GRAY)
        keskinlikler.append(float(cv2.Laplacian(gri, cv2.CV_64F).var()))

        ad = f"{Path(k['dosya']).stem}.jpg"
        cv2.imwrite(str(args.out / ad), duz, [cv2.IMWRITE_JPEG_QUALITY, 96])
        manifest.append({"dosya": ad, "metin": k["metin"],
                         "kaynak": k["dosya"],
                         "genislik_px": round(g, 1),
                         "keskinlik": round(keskinlikler[-1], 1)})
        yazilan += 1

    (args.out.parent / "plates.jsonl").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in manifest) + "\n",
        encoding="utf-8")

    def ozet(ad: str, v: list[float], birim: str = "") -> None:
        v = sorted(v)
        print(f"  {ad:<22}{v[len(v)//10]:>8.1f}{st.median(v):>9.1f}"
              f"{v[9*len(v)//10]:>9.1f}{birim:>6}")

    metinler = Counter(m["metin"] for m in manifest)
    print(f"{yazilan} plaka dikleştirildi -> {args.out}")
    print(f"{len(metinler)} farkli plaka\n")
    print(f"  {'olcu':<22}{'%10':>8}{'ortanca':>9}{'%90':>9}")
    print("  " + "-" * 48)
    ozet("kaynak genislik", genislikler, "px")
    ozet("kaynak yukseklik", yukseklikler, "px")
    ozet("en/boy orani", oranlar)
    ozet("perspektif egriligi", egrilikler)
    ozet("dik plaka keskinligi", keskinlikler)

    print("\nSENTETIK URETEC ICIN:")
    o = sorted(oranlar)
    print(f"  En/boy: gercek plaka 520x110 mm = 4.7:1, olculen ortanca "
          f"{st.median(o):.1f}:1")
    e = sorted(egrilikler)
    print(f"  Perspektif egriligi %90'lik dilimde {e[9*len(e)//10]:.2f} - "
          f"uretec bunun otesine gecmemeli")
    g = sorted(genislikler)
    print(f"  Plaka genisligi {g[len(g)//10]:.0f}-{g[9*len(g)//10]:.0f} px "
          f"araliginda; olcek varyasyonu buna gore ayarlanmali")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
