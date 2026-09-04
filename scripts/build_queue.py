"""Etiketleme kuyrugunu keskinlige gore siralar.

Neden gerekti
-------------
Etiketleme ilerledikce isabet oranlari cikti ve kaynaga gore ucte bir
degisiyor: maltepe %39, yagmur %12. Kalan ~2000 kirpmayi rastgele sirayla
etiketlemek, saatlerin cogunu plaka olmayan ya da okunmayan kirpmalara
harcamak demek.

Keskinlik zayif bir ayirt edici ama sifir degil
-----------------------------------------------
Laplacian varyansi olculdu ve dagilimlar ORTUSUYOR - okunabilen ve okunamayan
kirpmalar ayni araligi paylasiyor:

    maltepe   ok 210 / okunmaz 189 / plakasiz 145   (ortanca)
    yagmur    ok  59 / okunmaz  45 / plakasiz  38

Yagmurda esik taramasi isabeti %12'den %19'a cikardi ama kirpmalarin yarisini
atarak. Yani keskinlik bir ELEME olcutu degil, bir SIRALAMA olcutu: en keskinden
basla, verim dustugunde birak. Karar esikte degil, insanda kalsin.

Bu ayrimi yapmak onemli. Sert bir esik koysaydik, esigin altinda kalan okunabilir
plakalar veri setine hic giremezdi ve bunu kimse fark etmezdi - onceki projede
modelin gormedigi levhalarin veri setine girmemesiyle ayni tuzak.

Kullanim:
    python scripts/build_queue.py --kaynak istanbul_gece
    python scripts/build_queue.py --kaynak istabul_yagmur istanbul_gece --limit 400
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent


def keskinlik(yol: Path) -> float:
    im = cv2.imread(str(yol), cv2.IMREAD_GRAYSCALE)
    if im is None:
        return 0.0
    return float(cv2.Laplacian(im, cv2.CV_64F).var())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    parser.add_argument("--labels", type=Path, default=ROOT / "data" / "labels.jsonl")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--kaynak", nargs="*", default=None,
                        help="Yalnizca bu kayitlardan (ornek: istanbul_gece)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Kuyruga en keskin bu kadar kirpma alinir")
    args = parser.parse_args(argv)

    islenmis: set[str] = set()
    if args.labels.is_file():
        for satir in args.labels.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                islenmis.add(json.loads(satir)["dosya"])

    adaylar = [p for p in sorted(args.crops.glob("*.jpg"))
               if p.name not in islenmis]
    if args.kaynak:
        adaylar = [p for p in adaylar
                   if any(p.name.startswith(k) for k in args.kaynak)]
    if not adaylar:
        raise SystemExit("Etiketlenmemis kirpma yok (ya da --kaynak eslesmedi).")

    print(f"{len(adaylar)} etiketlenmemis kirpma, keskinlik olculuyor...")
    olculen = [(keskinlik(p), p) for p in adaylar]
    olculen.sort(key=lambda kv: -kv[0])
    if args.limit:
        olculen = olculen[:args.limit]

    etiket = "-".join(args.kaynak) if args.kaynak else "hepsi"
    out = args.out or ROOT / "data" / f"kuyruk_{etiket}.txt"
    out.write_text(
        f"# {len(olculen)} kirpma, KESKINLIGE GORE SIRALI (en keskin once).\n"
        f"# Bu bir eleme degil siralama: asagi indikce okunabilirlik dusuyor\n"
        f"# ama sifirlanmiyor. Verim dustugunu hissettigin yerde birak - esigi\n"
        f"# betik degil sen belirle.\n"
        f"#\n"
        f"# Olculen isabet oranlari: maltepe %39, yagmur %12. Bu kuyruk o\n"
        f"# farki kapatmak icin var, ortadan kaldirmak icin degil.\n"
        + "\n".join(p.name for _, p in olculen) + "\n",
        encoding="utf-8",
    )

    degerler = [k for k, _ in olculen]
    print(f"\nkeskinlik: en yuksek {degerler[0]:.0f}, "
          f"ortanca {degerler[len(degerler)//2]:.0f}, en dusuk {degerler[-1]:.0f}")
    print(f"yazildi -> {out.name}")
    print(f"\n  python scripts/label_plates.py --only data/{out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
