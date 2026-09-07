"""Bulut egitimi icin veri paketi hazirlar.

Neden dosya yigini degil tek dizi
---------------------------------
100.000 kucuk JPEG bulutta kotu bir format:

  - Yukleme yavas (dosya basina ek yuk, adet basina).
  - Kaggle her oturumda arsivi acmak zorunda.
  - Egitim her epoch'ta 100k dosya aciyor ve JPEG cozuyor; is G/C'ye takiliyor,
    GPU bosta bekliyor.

Egitim zaten her goruntuyu 32x128 gri tonlamaya indiriyor. O halde donusumu
BIR KEZ burada yapip tek bir dizi olarak gondermek hem yuklemeyi kucultuyor
hem egitimi hizlandiriyor: 100k dosya acmak yerine tek dosya okunuyor.

Bedeli acikca yaziliyor: paket girdi boyutunu SABITLIYOR. Model girdisini
48x160'a cikarmak istersen paketi yeniden uretmen gerekir - JPEG'ler yerelde
duruyor, yeniden paketlemek birkac dakika.

Sira korunuyor
--------------
Sentetik ornekler ZORLUK SIRASINDA paketleniyor; o sira mufredat ve
karistirmak onu iptal eder. Gercek plakalarda ise her satirda plaka metni
duruyor cunku bolme PLAKAYA gore yapilacak, kirpmaya gore degil.

Kullanim:
    python scripts/paketle.py
    python scripts/paketle.py --yukseklik 48 --genislik 160
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: train_recognizer.py ile ayni olmali; paket girdi boyutunu sabitliyor.
YUKSEKLIK, GENISLIK = 32, 128


def oku(yol: Path, y: int, g: int) -> np.ndarray | None:
    im = cv2.imread(str(yol), cv2.IMREAD_GRAYSCALE)
    if im is None:
        return None
    return cv2.resize(im, (g, y), interpolation=cv2.INTER_AREA)


def sentetigi_paketle(kok: Path, tsv: Path, y: int, g: int):
    """Zorluk sirasini koruyarak paketler."""
    satirlar = [l.split("\t") for l in
                tsv.read_text(encoding="utf-8").splitlines() if l.strip()]
    goruntuler, metinler, atlanan = [], [], 0
    for i, s in enumerate(satirlar):
        im = oku(kok / s[0], y, g)
        if im is None:
            atlanan += 1
            continue
        goruntuler.append(im)
        metinler.append(s[1])
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1}/{len(satirlar)}", flush=True)
    if atlanan:
        print(f"  UYARI: {atlanan} sentetik goruntu okunamadi")
    return np.stack(goruntuler), metinler


def gercegi_paketle(kok: Path, manifest: Path, y: int, g: int):
    """Plaka metnini de tasir - bolme plakaya gore yapilacak."""
    goruntuler, metinler = [], []
    for satir in manifest.read_text(encoding="utf-8").splitlines():
        if not satir.strip():
            continue
        k = json.loads(satir)
        im = oku(kok / k["dosya"], y, g)
        if im is None:
            continue
        goruntuler.append(im)
        metinler.append(k["metin"])
    return np.stack(goruntuler), metinler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--synth", type=Path, default=ROOT / "data" / "synth")
    parser.add_argument("--real", type=Path, default=ROOT / "data" / "plates")
    parser.add_argument("--out", type=Path, default=ROOT / "paket")
    parser.add_argument("--yukseklik", type=int, default=YUKSEKLIK)
    parser.add_argument("--genislik", type=int, default=GENISLIK)
    args = parser.parse_args(argv)

    tsv = args.synth.parent / "synth.tsv"
    manifest = args.real.parent / "plates.jsonl"
    for yol, ad in ((tsv, "synth.tsv"), (manifest, "plates.jsonl")):
        if not yol.is_file():
            raise SystemExit(f"{ad} yok: {yol}")

    args.out.mkdir(parents=True, exist_ok=True)
    boyut = (args.yukseklik, args.genislik)

    print(f"sentetik paketleniyor ({boyut[0]}x{boyut[1]}, zorluk sirasi korunuyor)")
    sx, sy = sentetigi_paketle(args.synth, tsv, *boyut)
    print(f"gercek paketleniyor")
    gx, gy = gercegi_paketle(args.real, manifest, *boyut)

    np.savez_compressed(args.out / "sentetik.npz", x=sx,
                        y=np.array(sy, dtype=object), allow_pickle=True)
    np.savez_compressed(args.out / "gercek.npz", x=gx,
                        y=np.array(gy, dtype=object), allow_pickle=True)

    # Egitim betigi de pakete giriyor: Kaggle defterinde tek dosya kopyalamak
    # yerine veri setinin icinden calistirilabilsin.
    (args.out / "train_recognizer.py").write_bytes(
        (ROOT / "scripts" / "train_recognizer.py").read_bytes())

    def mb(p: Path) -> float:
        return p.stat().st_size / 1e6

    print(f"\n{'dosya':<26}{'boyut':>10}{'icerik':>26}")
    print("-" * 62)
    print(f"{'sentetik.npz':<26}{mb(args.out/'sentetik.npz'):>9.0f}M"
          f"{f'{len(sy)} ornek':>26}")
    print(f"{'gercek.npz':<26}{mb(args.out/'gercek.npz'):>9.0f}M"
          f"{f'{len(gy)} kirpma / {len(set(gy))} plaka':>26}")
    print(f"{'train_recognizer.py':<26}{mb(args.out/'train_recognizer.py'):>9.1f}M"
          f"{'egitim betigi':>26}")
    toplam = sum(mb(p) for p in args.out.iterdir() if p.is_file())
    print("-" * 62)
    print(f"{'TOPLAM':<26}{toplam:>9.0f}M")
    print(f"\npaket -> {args.out.resolve()}")
    print("\nKarsilastirma: ayni veri 100k JPEG olarak ~540 MB ve Kaggle her")
    print("oturumda hepsini acmak zorunda. Paket tek dosya, tek okuma.")
    print("\nSonraki adim: docs/kaggle.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
